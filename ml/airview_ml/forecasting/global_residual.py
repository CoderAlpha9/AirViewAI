"""Persistence-residual models transferred onto operational CAMS forecasts."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.impute import SimpleImputer
from sklearn.metrics import mean_absolute_error, root_mean_squared_error
from sklearn.pipeline import Pipeline

HORIZONS = (24, 48, 72)
POLLUTANTS = ("pm2_5", "pm10")
FEATURES = [
    "camps_current",
    "camps_target",
    "pollutant_lag_1",
    "pollutant_lag_6",
    "pollutant_lag_24",
    "pollutant_mean_6",
    "pollutant_mean_24",
    "other_pm_current",
    "temperature_2m",
    "relative_humidity_2m",
    "surface_pressure",
    "precipitation",
    "wind_speed_10m",
    "wind_direction_sin",
    "wind_direction_cos",
    "boundary_layer_height",
    "latitude",
    "longitude",
    "hour_sin",
    "hour_cos",
    "day_of_year_sin",
    "day_of_year_cos",
    "month_sin",
    "month_cos",
    "nearby_station_residual",
    "nearby_station_distance_km",
    "nearby_station_age_hours",
    "nearby_station_count",
    "firms_count_24h",
    "firms_frp_24h",
    "road_count",
    "industrial_count",
    "construction_count",
    "wind_relative_source_score",
]


def _features(frame: pd.DataFrame, pollutant: str, horizon: int) -> pd.DataFrame:
    base = frame.sort_values(["station_id", "timestamp_utc"]).copy()
    group = base.groupby("station_id")[pollutant]
    other = "pm10" if pollutant == "pm2_5" else "pm2_5"
    output = pd.DataFrame(index=base.index)
    # These legacy artifact keys are retained for compatibility. Both contain the
    # issue-time station observation during training; neither contains CAMS data.
    output["camps_current"] = base[pollutant]
    output["camps_target"] = base[pollutant]
    for lag in (1, 6, 24):
        output[f"pollutant_lag_{lag}"] = group.shift(lag)
    shifted = group.shift(1)
    output["pollutant_mean_6"] = shifted.groupby(base["station_id"]).transform(
        lambda values: values.rolling(6, min_periods=3).mean()
    )
    output["pollutant_mean_24"] = shifted.groupby(base["station_id"]).transform(
        lambda values: values.rolling(24, min_periods=8).mean()
    )
    output["other_pm_current"] = base.get(other)
    for name in (
        "temperature_2m",
        "relative_humidity_2m",
        "surface_pressure",
        "precipitation",
        "wind_speed_10m",
        "boundary_layer_height",
        "latitude",
        "longitude",
        "hour_sin",
        "hour_cos",
        "day_of_year_sin",
        "day_of_year_cos",
    ):
        output[name] = base.get(name)
    direction = np.radians(pd.to_numeric(base.get("wind_direction_10m"), errors="coerce"))
    output["wind_direction_sin"] = np.sin(direction)
    output["wind_direction_cos"] = np.cos(direction)
    month = pd.to_numeric(base.get("month"), errors="coerce")
    output["month_sin"] = np.sin(2 * np.pi * month / 12)
    output["month_cos"] = np.cos(2 * np.pi * month / 12)
    for name in FEATURES:
        if name not in output:
            output[name] = 0.0
    future = group.shift(-horizon)
    output["target_residual"] = future - base[pollutant]
    output["future_observed"] = future
    output["persistence"] = base[pollutant]
    output["city_id"] = base["city_id"].astype(str)
    output["timestamp_utc"] = base["timestamp_utc"]
    return output


def _model() -> Pipeline:
    return Pipeline(
        [
            ("impute", SimpleImputer(strategy="median", add_indicator=True)),
            (
                "regressor",
                HistGradientBoostingRegressor(
                    loss="absolute_error",
                    learning_rate=0.06,
                    max_iter=120,
                    max_leaf_nodes=24,
                    l2_regularization=1.0,
                    random_state=20260722,
                ),
            ),
        ]
    )


def train_global_residual_models(root: Path) -> dict[str, Any]:
    data_path = root / "data" / "processed" / "india" / "station_hourly_features.parquet"
    try:
        frame = pd.read_parquet(data_path)
    except OSError:
        partition_paths = sorted(data_path.with_suffix("").glob("city_id=*.parquet"))
        if not partition_paths:
            raise
        frame = pd.concat((pd.read_parquet(path) for path in partition_paths), ignore_index=True)
    frame["timestamp_utc"] = pd.to_datetime(frame["timestamp_utc"], utc=True)
    registry_path = root / "models" / "forecasting" / "registry.json"
    registry = (
        json.loads(registry_path.read_text(encoding="utf-8")) if registry_path.is_file() else []
    )
    records: list[dict[str, Any]] = []
    deployed: list[dict[str, Any]] = []
    for pollutant in POLLUTANTS:
        for horizon in HORIZONS:
            data = _features(frame, pollutant, horizon).dropna(
                subset=["target_residual", "future_observed", "persistence"]
            )
            city_metrics = []
            predictions: list[np.ndarray] = []
            truths: list[np.ndarray] = []
            persistence_values: list[np.ndarray] = []
            for held_out in sorted(data["city_id"].unique()):
                train = data[data["city_id"] != held_out]
                test = data[data["city_id"] == held_out]
                estimator = _model().fit(train[FEATURES], train["target_residual"])
                predicted = test["persistence"].to_numpy() + estimator.predict(test[FEATURES])
                truth = test["future_observed"].to_numpy()
                baseline = test["persistence"].to_numpy()
                predictions.append(predicted)
                truths.append(truth)
                persistence_values.append(baseline)
                city_metrics.append(
                    {
                        "held_out_city": held_out,
                        "n": len(test),
                        "global_residual_mae": float(mean_absolute_error(truth, predicted)),
                        "global_residual_rmse": float(root_mean_squared_error(truth, predicted)),
                        "persistence_mae": float(mean_absolute_error(truth, baseline)),
                        "persistence_rmse": float(root_mean_squared_error(truth, baseline)),
                    }
                )
            truth_all = np.concatenate(truths)
            predicted_all = np.concatenate(predictions)
            baseline_all = np.concatenate(persistence_values)
            global_rmse = float(root_mean_squared_error(truth_all, predicted_all))
            persistence_rmse = float(root_mean_squared_error(truth_all, baseline_all))
            champion = (
                "hist_gradient_boosting_residual"
                if global_rmse < persistence_rmse
                else "persistence"
            )
            final_model = _model().fit(data[FEATURES], data["target_residual"])
            folder = root / "models" / "forecasting" / "global_residual" / pollutant / str(horizon)
            folder.mkdir(parents=True, exist_ok=True)
            joblib.dump(final_model, folder / "model.joblib")
            metadata = {
                "model_id": f"{pollutant}-global-residual-hgb-{horizon}",
                "family": "HistGradientBoostingRegressor",
                "pollutant": pollutant,
                "horizon": horizon,
                "features": FEATURES,
                "target": "future observed concentration minus causal persistence baseline",
                "training_target_formula": "target_residual(t,h) = observed_station(t+h) - observed_station(t)",
                "historical_cams_values_present": False,
                "feature_name_note": "Legacy keys camps_current and camps_target are retained for artifact compatibility; during training both equal observed_station(t), not CAMS values.",
                "operational_application": "validation-selected persistence-residual transfer onto live CAMS, followed by live-station residual interpolation",
                "live_inference_formula": "forecast(i)=max(0,CAMS(i)+I[champion=hist_gradient_boosting_residual]*(i/h)*model(x_live)+station_residual*exp(-i/18)); h is the artifact horizon",
                "live_grid_formula": "grid_forecast(cell,h)=max(0,CAMS(h)+I[champion=hist_gradient_boosting_residual]*model(x_live_cell)+station_residual_cell*exp(-h/18)+bounded_wind_planning_adjustment_cell)",
                "training_baseline_limitation": "Archived cell-level CAMS was not retained in v1; persistence is used as the causal training baseline.",
                "supports_unseen_cities": True,
                "created_at_utc": datetime.now(timezone.utc).isoformat(),
                "champion": champion,
                "grouped_validation": city_metrics,
                "global_residual_rmse": global_rmse,
                "persistence_rmse": persistence_rmse,
                "existing_ridge_test_rmse": next(
                    (
                        item.get("test_metrics", {}).get("rmse")
                        for item in registry
                        if item.get("pollutant") == pollutant
                        and int(item.get("horizon", 0)) == horizon
                        and item.get("family") == "ridge"
                    ),
                    None,
                ),
            }
            (folder / "metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
            (folder / "feature_schema.json").write_text(
                json.dumps(FEATURES, indent=2), encoding="utf-8"
            )
            records.append(metadata)
            deployed.append(
                {
                    "pollutant": pollutant,
                    "horizon": horizon,
                    "artifact": str(folder.relative_to(root)).replace("\\", "/"),
                    "champion": champion,
                }
            )
    report = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "validation": "leave-one-city-out grouped validation",
        "raw_cams_evaluation": "unavailable because archived cell-level CAMS was not retained in v1",
        "models": records,
        "deployed": deployed,
    }
    reports = root / "outputs" / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    (reports / "global_residual_validation.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8"
    )
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[3])
    args = parser.parse_args()
    report = train_global_residual_models(args.root.resolve())
    print(
        json.dumps(
            {
                "trained": len(report["models"]),
                "report": "outputs/reports/global_residual_validation.json",
            }
        )
    )


if __name__ == "__main__":
    main()
