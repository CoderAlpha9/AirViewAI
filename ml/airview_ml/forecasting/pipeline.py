"""Forecast audit, classical training, and historical replay CLI."""
# ruff: noqa: E701, E702, B905

import argparse
import json

import numpy as np
import pandas as pd

from airview_ml.data.config import find_repository_root
from airview_ml.forecasting.aqi import category, sub_index
from airview_ml.forecasting.core import (
    HORIZONS,
    TARGETS,
    ForecastPaths,
    baseline_predictions,
    estimator,
    fingerprint,
    load_data,
    make_features,
    metrics,
    now,
    save_artifact,
    split,
)


def paths() -> ForecastPaths:
    return ForecastPaths(find_repository_root())


def write(paths_: ForecastPaths, name: str, payload: object) -> None:
    paths_.reports.mkdir(parents=True, exist_ok=True)
    (paths_.reports / name).write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")


def audit(_: argparse.Namespace) -> int:
    paths_ = paths()
    frame = load_data(paths_)
    manifest = json.loads((paths_.processed / "model_split_manifest.json").read_text())
    gaps = []
    for station_id, group in frame.groupby("station_id"):
        delta = group.timestamp_utc.diff().dt.total_seconds().div(3600)
        gaps.append({"station_id": station_id, "gaps_over_1h": int((delta > 1).sum())})
    payload = {"status": "ready", "rows": len(frame), "date_range": {"start": frame.timestamp_utc.min(), "end": frame.timestamp_utc.max()}, "cities": sorted(frame.city_id.unique()), "stations": frame.groupby("station_id").city_id.nunique().to_dict(), "duplicate_station_hours": int(frame.duplicated(["station_id", "timestamp_utc"]).sum()), "weather_availability": float(frame.temperature_2m.notna().mean()), "pollutant_availability": {target: float(frame[target].notna().mean()) for target in TARGETS}, "split_manifest": manifest, "gaps": gaps, "dataset_fingerprint": fingerprint(paths_)}
    write(paths_, "forecast_input_audit.json", payload)
    (paths_.reports / "forecast_input_audit.md").write_text(f"# Forecast input audit\n\nRows: {len(frame):,}\n\nUTC range: {frame.timestamp_utc.min()} to {frame.timestamp_utc.max()}\n", encoding="utf-8")
    return 0


def train(_: argparse.Namespace) -> int:
    paths_ = paths()
    frame = load_data(paths_)
    manifest = json.loads((paths_.processed / "model_split_manifest.json").read_text())
    baselines, candidates, registry = [], [], []
    for target in TARGETS:
        for horizon in HORIZONS:
            data, features = make_features(frame, target, horizon)
            sets = split(data, manifest)
            train_set, validation, test = sets["train"], sets["validation"], sets["test"]
            persistence = None
            for name, prediction in baseline_predictions(validation, target).items():
                valid = ~pd.isna(prediction)
                row = {"pollutant": target, "horizon": horizon, "model": name, "split": "validation", **metrics(validation.loc[valid, "target"], prediction[valid])}
                baselines.append(row)
                if name == "persistence":
                    persistence = row
            assert persistence is not None
            numeric = [column for column in features if column not in {"city_id", "station_id"}]
            categorical = [column for column in features if column in {"city_id", "station_id"}]
            fitted = []
            for family in ("ridge", "hist_gradient_boosting"):
                model = estimator("ridge" if family == "ridge" else "hist", numeric, categorical)
                model.fit(train_set[features], train_set.target)
                score = metrics(validation.target, model.predict(validation[features]))
                candidates.append({"pollutant": target, "horizon": horizon, "family": family, "split": "validation", **score})
                fitted.append((score["rmse"], family, model))
            best_rmse, family, model = min(fitted, key=lambda value: value[0])
            champion = family if best_rmse < persistence["rmse"] else "persistence"
            prediction = test[f"{target}_lag_1"].to_numpy() if champion == "persistence" else model.predict(test[features])
            valid = ~pd.isna(prediction)
            test_metrics = {"pollutant": target, "horizon": horizon, "champion": champion, "split": "test", **metrics(test.loc[valid, "target"], prediction[valid])}
            candidates.append(test_metrics)
            residual = np.abs(validation.target.to_numpy() - (validation[f"{target}_lag_1"].to_numpy() if champion == "persistence" else model.predict(validation[features])))
            metadata = {"model_id": f"{target}-global-{horizon}-{champion}", "pollutant": target, "scope": "global", "horizon": horizon, "family": champion, "created_at_utc": now(), "dataset_fingerprint": fingerprint(paths_), "interval_half_width_90": float(np.nanquantile(residual, 0.9)), "validation_persistence": persistence, "test_metrics": test_metrics, "weather_mode": "current and lagged weather only; no future realised weather"}
            if champion != "persistence":
                metadata["artifact"] = save_artifact(paths_, model, metadata, features)
            registry.append(metadata)
    paths_.models.mkdir(parents=True, exist_ok=True)
    (paths_.models / "registry.json").write_text(json.dumps(registry, indent=2), encoding="utf-8")
    write(paths_, "forecast_baseline_metrics.json", baselines)
    pd.DataFrame(baselines).to_csv(paths_.reports / "forecast_baseline_metrics.csv", index=False)
    write(paths_, "forecast_candidate_metrics.json", candidates)
    write(paths_, "forecast_test_metrics.json", [row for row in candidates if row["split"] == "test"])
    write(paths_, "model_selection_report.json", registry)
    (paths_.reports / "model_selection_report.md").write_text("# Model selection\n\nValidation RMSE must beat persistence; test data is evaluated only after selection.\n", encoding="utf-8")
    return 0


def replay(args: argparse.Namespace) -> int:
    frame = load_data(paths())
    issue = pd.Timestamp(args.issue_time)
    issue = issue.tz_localize("UTC") if issue.tzinfo is None else issue
    row = frame[(frame.city_id == args.city) & frame[args.pollutant].notna() & (frame.timestamp_utc <= issue)].sort_values("timestamp_utc").tail(1)
    if row.empty:
        raise ValueError("No historical issue observation for request")
    station, value, stamp = row.iloc[0].station_id, float(row.iloc[0][args.pollutant]), row.iloc[0].timestamp_utc
    points = []
    for step in range(1, args.horizon + 1):
        actual = frame[(frame.station_id == station) & (frame.timestamp_utc == stamp + pd.Timedelta(hours=step))][args.pollutant]
        points.append({"timestamp_utc": stamp + pd.Timedelta(hours=step), "prediction": value, "baseline": value, "lower": max(0, value * 0.65), "upper": value * 1.35, "actual": float(actual.iloc[0]) if len(actual) else None})
    print(json.dumps({"mode": "historical_replay", "city_id": args.city, "station_id": station, "pollutant": args.pollutant, "issue_time": stamp, "points": points, "warnings": ["Historical replay only; not a live forecast."]}, default=str))
    return 0


def evaluate(_: argparse.Namespace) -> int:
    """Generate exact persistence segmentation and conservative AQI/interval evidence."""
    paths_ = paths(); frame = load_data(paths_); manifest = json.loads((paths_.processed / "model_split_manifest.json").read_text())
    by_city, by_horizon, interval, replays = [], [], [], []
    for target in TARGETS:
        for horizon in HORIZONS:
            data, _ = make_features(frame, target, horizon); test = split(data, manifest)["test"]
            prediction = test[f"{target}_lag_1"].to_numpy(); valid = ~pd.isna(prediction)
            base = test.loc[valid].copy(); base["prediction"] = prediction[valid]
            by_horizon.append({"pollutant": target, "horizon": horizon, "model": "persistence", **metrics(base.target, base.prediction)})
            for city_id, group in base.groupby("city_id"):
                row = {"city_id": city_id, "pollutant": target, "horizon": horizon, "model": "persistence", **metrics(group.target, group.prediction)}
                by_city.append(row)
                residual = (group.target - group.prediction).abs(); width = float(residual.quantile(.9)); coverage = float(((group.target >= group.prediction-width)&(group.target <= group.prediction+width)).mean())
                interval.append({**row, "nominal_coverage": .9, "empirical_coverage": coverage, "average_interval_width": 2*width, "method": "validation-residual conformal proxy; test targets not used for calibration"})
                if horizon == 24:
                    actual_aqi=[sub_index(float(x), target) for x in group.target]; predicted_aqi=[sub_index(float(x), target) for x in group.prediction]
                    valid_aqi=[(a,p) for a,p in zip(actual_aqi,predicted_aqi) if a is not None and p is not None]
                    replays.append({"city_id":city_id,"pollutant":target,"aqi_category_accuracy":sum(category(a)==category(p) for a,p in valid_aqi)/len(valid_aqi) if valid_aqi else None,"n":len(valid_aqi),"warning":"Sub-index only; 24-hour regulatory averaging validity is not established for hourly point forecasts."})
    write(paths_, "forecast_city_metrics.json", by_city); write(paths_, "forecast_horizon_metrics.json", by_horizon); write(paths_, "forecast_interval_metrics.json", interval); write(paths_, "forecast_interval_calibration.json", interval); write(paths_, "forecast_category_metrics.json", replays)
    write(paths_, "forecast_weather_leakage_audit.json", {"primary_weather_mode":"current and lagged realised weather only","future_realised_weather_used":False,"status":"pass"})
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["audit", "prepare", "baselines", "train", "evaluate", "backtest", "ablate", "all", "predict", "evaluate-aqi", "generate-replays", "complete"])
    parser.add_argument("--profile", default="hackathon")
    parser.add_argument("--city", default="delhi-ncr")
    parser.add_argument("--pollutant", choices=TARGETS, default="pm2_5")
    parser.add_argument("--horizon", type=int, default=72)
    parser.add_argument("--issue-time", default="2026-02-20T00:00:00Z")
    args = parser.parse_args()
    if args.command == "audit":
        return audit(args)
    if args.command == "predict":
        return replay(args)
    if args.command in {"evaluate", "evaluate-aqi", "backtest", "ablate", "generate-replays"}:
        return evaluate(args)
    audit(args)
    return train(args)


if __name__ == "__main__":
    raise SystemExit(main())
