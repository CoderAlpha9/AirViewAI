"""Canonical operational context and decision calculations."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from airview_ml.forecasting.aqi import category, sub_index

AQI_COLOURS = {
    "Good": "#2e7d32",
    "Satisfactory": "#689f38",
    "Moderate": "#f9a825",
    "Poor": "#ef6c00",
    "Very Poor": "#c62828",
    "Severe": "#6a1b4d",
}


def aqi_result(concentration: float | None, pollutant: str) -> dict[str, Any]:
    value = sub_index(concentration, pollutant) if concentration is not None else None
    label = category(value)
    return {"aqi": value, "category": label, "colour": AQI_COLOURS.get(label)}


def forecast_peak(points: list[dict[str, Any]], pollutant: str) -> dict[str, Any] | None:
    valid = [point for point in points if point.get("prediction") is not None]
    if not valid:
        return None
    point = max(valid, key=lambda item: float(item["prediction"]))
    result = aqi_result(point.get("rolling_24h") or point["prediction"], pollutant)
    return {
        "value": float(point["prediction"]),
        "timestamp_utc": point["timestamp_utc"],
        **result,
    }


def intervention_priority(aqi: int | None, confidence: float) -> str:
    if aqi is None:
        return "Unavailable"
    if confidence < 0.25:
        return "Watch"
    if aqi > 400:
        return "Critical"
    if aqi > 300:
        return "High"
    if aqi > 200:
        return "Elevated"
    return "Watch"


def coverage_confidence(
    station_count: int,
    freshest_age_hours: float | None,
    provider_fraction: float,
    feature_completeness: float,
) -> float:
    station_component = min(station_count / 3, 1) * 0.35
    freshness_component = (
        max(0.0, 1 - freshest_age_hours / 24) * 0.25 if freshest_age_hours is not None else 0.0
    )
    value = (
        station_component
        + freshness_component
        + 0.2 * provider_fraction
        + 0.2 * feature_completeness
    )
    return round(max(0.1, min(value, 0.95)), 3)


def canonical_context(
    *,
    city: dict[str, Any],
    pollutant: str,
    horizon: int,
    issue_timestamp: str,
    freshness: dict[str, Any],
    coverage_type: str,
    provider_versions: dict[str, Any] | None = None,
) -> dict[str, Any]:
    identity = {
        "city_id": city["city_id"],
        "pollutant": pollutant,
        "horizon": int(horizon),
        "issue_timestamp": issue_timestamp,
        "coverage_type": coverage_type,
    }
    snapshot = hashlib.sha256(
        json.dumps(identity, sort_keys=True, default=str).encode()
    ).hexdigest()[:16]
    return {
        "city": city,
        "pollutant": pollutant,
        "horizon": int(horizon),
        "issue_timestamp": issue_timestamp,
        "snapshot_id": snapshot,
        "schema_version": "2.0",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "data_freshness": freshness,
        "coverage_type": coverage_type,
        "provider_versions": provider_versions or {},
    }
