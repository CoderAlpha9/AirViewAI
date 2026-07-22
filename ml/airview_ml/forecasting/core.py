"""Leakage-safe classical forecasting primitives for AirView AI."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.impute import SimpleImputer
from sklearn.linear_model import Ridge
from sklearn.metrics import (
    mean_absolute_error,
    median_absolute_error,
    r2_score,
    root_mean_squared_error,
)
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

HORIZONS = (24, 48, 72)
TARGETS = ("pm2_5", "pm10")
LAGS = (1, 2, 3, 6, 12, 24, 48, 72, 168)
ROLLING_WINDOWS = (3, 6, 12, 24, 48, 72, 168)
SEED = 20260721


@dataclass(frozen=True)
class ForecastPaths:
    root: Path

    @property
    def processed(self) -> Path:
        return self.root / "data" / "processed" / "india"

    @property
    def reports(self) -> Path:
        return self.root / "outputs" / "reports"

    @property
    def models(self) -> Path:
        return self.root / "models" / "forecasting"


def load_data(paths: ForecastPaths) -> pd.DataFrame:
    frame = pd.read_parquet(paths.processed / "station_hourly_features.parquet")
    frame["timestamp_utc"] = pd.to_datetime(frame["timestamp_utc"], utc=True)
    return frame.sort_values(["station_id", "timestamp_utc"]).reset_index(drop=True)


def fingerprint(paths: ForecastPaths) -> str:
    digest = hashlib.sha256()
    for path in (
        paths.processed / "station_hourly_features.parquet",
        paths.processed / "model_split_manifest.json",
    ):
        digest.update(path.read_bytes())
    return digest.hexdigest()


def make_features(frame: pd.DataFrame, target: str, horizon: int) -> tuple[pd.DataFrame, list[str]]:
    """Build only causal predictors. Every rolling feature excludes the issue hour."""
    base = frame.copy().sort_values(["station_id", "timestamp_utc"])
    group = base.groupby("station_id", group_keys=False)
    for column in (target, "pm2_5", "pm10", "no2", "so2", "co", "o3"):
        if column not in base:
            continue
        for lag in LAGS:
            base[f"{column}_lag_{lag}"] = group[column].shift(lag)
        for window in ROLLING_WINDOWS:
            shifted = group[column].shift(1)
            minimum = max(2, window // 3)
            base[f"{column}_mean_{window}"] = shifted.groupby(base["station_id"]).transform(
                lambda value, window=window, minimum=minimum: value.rolling(
                    window, min_periods=minimum
                ).mean()
            )
            base[f"{column}_std_{window}"] = shifted.groupby(base["station_id"]).transform(
                lambda value, window=window, minimum=minimum: value.rolling(
                    window, min_periods=minimum
                ).std()
            )
    base["target"] = group[target].shift(-horizon)
    base["target_timestamp_utc"] = group["timestamp_utc"].shift(-horizon)
    weather = [
        column
        for column in (
            "temperature_2m",
            "relative_humidity_2m",
            "precipitation",
            "surface_pressure",
            "cloud_cover",
            "wind_speed_10m",
            "wind_direction_10m",
            "wind_gusts_10m",
            "shortwave_radiation",
        )
        if column in base
    ]
    calendar = [
        column
        for column in (
            "hour",
            "day_of_week",
            "day_of_year",
            "month",
            "weekend",
            "hour_sin",
            "hour_cos",
            "day_of_year_sin",
            "day_of_year_cos",
        )
        if column in base
    ]
    lags = [
        column for column in base if "_lag_" in column or "_mean_" in column or "_std_" in column
    ]
    features = ["city_id", "station_id", "latitude", "longitude", *weather, *calendar, *lags]
    features = [
        column
        for column in features
        if column in base and (column in {"city_id", "station_id"} or base[column].notna().any())
    ]
    # Target must be contained in the same split as its issue timestamp.
    return base.dropna(subset=["target", "target_timestamp_utc"]), features


def split(frame: pd.DataFrame, manifest: dict[str, Any]) -> dict[str, pd.DataFrame]:
    result = {}
    for name, values in manifest["splits"].items():
        start, end = pd.Timestamp(values["start"]), pd.Timestamp(values["end"])
        result[name] = frame[
            (frame["timestamp_utc"] >= start)
            & (frame["timestamp_utc"] <= end)
            & (frame["target_timestamp_utc"] <= end)
        ].copy()
    return result


def metrics(actual: pd.Series, predicted: np.ndarray) -> dict[str, float | int]:
    actual_array = actual.to_numpy(dtype=float)
    error = predicted - actual_array
    denominator = np.abs(actual_array) + np.abs(predicted)
    smape = float(
        np.mean(
            np.divide(
                2 * np.abs(error), denominator, out=np.zeros_like(error), where=denominator > 1e-9
            )
        )
        * 100
    )
    return {
        "n": len(actual),
        "mae": float(mean_absolute_error(actual_array, predicted)),
        "rmse": float(root_mean_squared_error(actual_array, predicted)),
        "r2": float(r2_score(actual_array, predicted)),
        "bias": float(error.mean()),
        "median_absolute_error": float(median_absolute_error(actual_array, predicted)),
        "smape": smape,
    }


def baseline_predictions(frame: pd.DataFrame, target: str) -> dict[str, np.ndarray]:
    group = frame.groupby("station_id")[target]
    return {
        "persistence": frame[f"{target}_lag_1"].to_numpy(),
        "daily_persistence": group.shift(24).to_numpy(),
        "weekly_persistence": group.shift(168).to_numpy(),
        "rolling_mean_24": frame[f"{target}_mean_24"].to_numpy(),
    }


def estimator(family: str, numeric: list[str], categorical: list[str]) -> Pipeline:
    preprocessor = ColumnTransformer(
        [
            (
                "numeric",
                Pipeline(
                    [
                        ("impute", SimpleImputer(strategy="median", add_indicator=True)),
                        ("scale", StandardScaler()),
                    ]
                ),
                numeric,
            ),
            (
                "categorical",
                Pipeline(
                    [
                        ("impute", SimpleImputer(strategy="most_frequent")),
                        ("encode", OneHotEncoder(handle_unknown="ignore")),
                    ]
                ),
                categorical,
            ),
        ]
    )
    model = (
        Ridge(alpha=3.0)
        if family == "ridge"
        else HistGradientBoostingRegressor(
            max_iter=160,
            max_leaf_nodes=20,
            learning_rate=0.08,
            l2_regularization=1.0,
            random_state=SEED,
        )
    )
    # HistGradientBoosting needs dense output; OneHotEncoder is sparse by default.
    if family != "ridge":
        preprocessor = ColumnTransformer(
            [("numeric", SimpleImputer(strategy="median", add_indicator=True), numeric)],
            remainder="drop",
        )
    return Pipeline([("preprocessor", preprocessor), ("model", model)])


def save_artifact(
    paths: ForecastPaths, model: Pipeline, metadata: dict[str, Any], feature_schema: list[str]
) -> str:
    folder = paths.models / metadata["pollutant"] / metadata["scope"] / str(metadata["horizon"])
    folder.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, folder / "model.joblib")
    (folder / "metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    (folder / "feature_schema.json").write_text(
        json.dumps(feature_schema, indent=2), encoding="utf-8"
    )
    return str(folder.relative_to(paths.root)).replace("\\", "/")


def now() -> str:
    return datetime.now(timezone.utc).isoformat()
