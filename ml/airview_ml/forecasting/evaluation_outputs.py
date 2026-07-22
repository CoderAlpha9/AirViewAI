"""Additional leakage-safe forecasting evaluation outputs."""

# ruff: noqa: E701, E702, E231, E501
from __future__ import annotations

import json
import time
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.inspection import permutation_importance

from airview_ml.forecasting.core import (
    HORIZONS,
    TARGETS,
    ForecastPaths,
    estimator,
    load_data,
    make_features,
    metrics,
    split,
)


def write(p: ForecastPaths, n: str, v: object) -> None:
    (p.reports / n).write_text(json.dumps(v, indent=2, default=str), encoding="utf-8")


def rolling(p: ForecastPaths, frame: pd.DataFrame, manifest: dict) -> None:
    rows = []
    folds = []
    bounds = [
        ("2025-05-31", "2025-06-01", "2025-06-30"),
        ("2025-07-31", "2025-08-01", "2025-08-31"),
        ("2025-09-30", "2025-10-01", "2025-10-31"),
    ]
    for i, (a, b, c) in enumerate(bounds, 1):
        folds.append(
            {
                "fold": i,
                "train_end": a,
                "validation_start": b,
                "validation_end": c,
                "strategy": "expanding; targets end within validation",
            }
        )
    for target in TARGETS:
        for h in HORIZONS:
            data, features = make_features(frame, target, h)
            num = [x for x in features if x not in {"city_id", "station_id"}]
            cat = [x for x in features if x in {"city_id", "station_id"}]
            for fold in folds:
                train = data[
                    (data.timestamp_utc <= pd.Timestamp(fold["train_end"], tz="UTC"))
                    & (data.target_timestamp_utc <= pd.Timestamp(fold["train_end"], tz="UTC"))
                ]
                val = data[
                    (data.timestamp_utc >= pd.Timestamp(fold["validation_start"], tz="UTC"))
                    & (data.timestamp_utc <= pd.Timestamp(fold["validation_end"], tz="UTC"))
                    & (data.target_timestamp_utc <= pd.Timestamp(fold["validation_end"], tz="UTC"))
                ].dropna(subset=[f"{target}_lag_1"])
                rows.append(
                    {
                        "fold": fold["fold"],
                        "pollutant": target,
                        "horizon": h,
                        "model": "persistence",
                        **metrics(val.target, val[f"{target}_lag_1"].to_numpy()),
                    }
                )
                m = estimator("ridge", num, cat)
                m.fit(train[features], train.target)
                rows.append(
                    {
                        "fold": fold["fold"],
                        "pollutant": target,
                        "horizon": h,
                        "model": "ridge",
                        **metrics(val.target, m.predict(val[features])),
                    }
                )
    write(p, "forecast_rolling_origin_folds.json", folds)
    write(p, "forecast_rolling_origin_metrics.json", rows)
    write(
        p,
        "forecast_model_stability.json",
        {
            "note": "Per-fold metrics retained in forecast_rolling_origin_metrics.json; grouped aggregate omitted because pandas multi-level columns are not JSON-safe."
        },
    )


def ablations(p: ForecastPaths, frame: pd.DataFrame, manifest: dict) -> None:
    data, features = make_features(frame, "pm2_5", 24)
    sets = split(data, manifest)
    train, val = sets["train"], sets["validation"].dropna(subset=["pm2_5_lag_1"])
    groups = {
        "pollutant_history": [x for x in features if "pm2_5_" in x],
        "history_calendar": [
            x for x in features if "pm2_5_" in x or x in {"hour", "day_of_week", "month", "weekend"}
        ],
        "history_weather": [
            x
            for x in features
            if "pm2_5_" in x or "temperature" in x or "humidity" in x or "wind" in x
        ],
        "full_available": features,
    }
    rows = []
    base = metrics(val.target, val.pm2_5_lag_1.to_numpy())
    for name, cols in groups.items():
        cols = [x for x in cols if x not in {"city_id", "station_id"}]
        start = time.perf_counter()
        m = estimator("ridge", cols, [])
        m.fit(train[cols], train.target)
        s = metrics(val.target, m.predict(val[cols]))
        rows.append(
            {
                "feature_group": name,
                "features": cols,
                "rows": len(val),
                "cities": sorted(val.city_id.unique()),
                "runtime_seconds": time.perf_counter() - start,
                "persistence_rmse": base["rmse"],
                "rmse_improvement_pct": 100 * (base["rmse"] - s["rmse"]) / base["rmse"],
                "unavailable_warnings": "FIRMS/OSM unavailable as aligned columns; Sentinel excluded because valid-pixel coverage is zero.",
                **s,
            }
        )
    write(p, "forecast_ablation_report.json", rows)
    pd.DataFrame([{**r, "features": "|".join(r["features"])} for r in rows]).to_csv(
        p.reports / "forecast_ablation_report.csv", index=False
    )


def importance(p: ForecastPaths, frame: pd.DataFrame, manifest: dict) -> None:
    registry = json.loads((p.models / "registry.json").read_text())
    out = []
    for e in registry:
        if e.get("family") != "ridge":
            continue
        folder = p.root / e["artifact"]
        m = joblib.load(folder / "model.joblib")
        features = json.loads((folder / "feature_schema.json").read_text())
        data, _ = make_features(frame, e["pollutant"], e["horizon"])
        v = split(data, manifest)["validation"].sample(750, random_state=20260721)
        r = permutation_importance(
            m,
            v[features],
            v.target,
            n_repeats=3,
            random_state=20260721,
            scoring="neg_root_mean_squared_error",
        )
        top = np.argsort(r.importances_mean)[-15:][::-1]
        out.extend(
            {
                "model_id": e["model_id"],
                "feature": features[i],
                "permutation_importance": float(r.importances_mean[i]),
                "meaning": "predictive association, not causal source attribution",
            }
            for i in top
        )
    write(p, "forecast_feature_importance.json", out)
    write(
        p,
        "forecast_shap_status.json",
        {
            "status": "not_run",
            "reason": "SHAP is not installed; permutation importance was executed.",
        },
    )
    (p.reports / "forecast_explainability_summary.md").write_text(
        "# Explainability\n\nImportance is predictive association, not causal source attribution.\n",
        encoding="utf-8",
    )


def main() -> int:
    p = ForecastPaths(Path.cwd())
    f = load_data(p)
    m = json.loads((p.processed / "model_split_manifest.json").read_text())
    rolling(p, f, m)
    ablations(p, f, m)
    importance(p, f, m)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
