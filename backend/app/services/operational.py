"""Operational dashboard assembly for AirView AI.

The service attempts live station observations, CAMS air-quality forecasts, numerical
weather forecasts and near-real-time FIRMS detections. If providers are unreachable it
falls back to a clearly labelled validated historical replay so the demo remains usable.
"""

from __future__ import annotations

import asyncio
import json
import math
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
from airview_ml.forecasting.aqi import category, sub_index

from app.services.artifacts import REPOSITORY_ROOT, artifacts
from app.services.live_providers import (
    firms_near_real_time,
    haversine_km,
    open_meteo_air_quality,
    open_meteo_weather,
    openaq_recent,
)


@dataclass(frozen=True)
class CityConfig:
    city_id: str
    name: str
    state: str
    station_id: str
    station_name: str
    openaq_location_id: int
    latitude: float
    longitude: float


CITIES: dict[str, CityConfig] = {
    "delhi-ncr": CityConfig(
        "delhi-ncr",
        "Delhi NCR",
        "Delhi",
        "openaq-235",
        "Anand Vihar, Delhi",
        235,
        28.646835,
        77.316032,
    ),
    "agra": CityConfig(
        "agra",
        "Agra",
        "Uttar Pradesh",
        "openaq-860",
        "Sanjay Palace, Agra",
        860,
        27.19865833,
        78.00598056,
    ),
    "amritsar": CityConfig(
        "amritsar",
        "Amritsar",
        "Punjab",
        "openaq-5551",
        "Golden Temple, Amritsar",
        5551,
        31.62,
        74.876512,
    ),
    "lucknow": CityConfig(
        "lucknow",
        "Lucknow",
        "Uttar Pradesh",
        "openaq-2456",
        "Talkatora, Lucknow",
        2456,
        26.83399722,
        80.8917361,
    ),
    # Historical v1 used location 5542 (Jalandhar). Live mode intentionally uses the correct
    # Ludhiana CAAQMS location while keeping the old replay artifacts immutable.
    "ludhiana": CityConfig(
        "ludhiana", "Ludhiana", "Punjab", "openaq-5569", "PAU, Ludhiana", 5569, 30.9028, 75.8086
    ),
}

# The immutable v1 replay labelled “Ludhiana” was built from OpenAQ location 5542
# (Civil Line, Jalandhar). Live operations use the correct PAU Ludhiana station above.
# Keeping the two coordinate contexts explicit prevents spatial evidence from being
# silently attached to the wrong city when a live provider falls back to replay.
HISTORICAL_REPLAY_CITIES: dict[str, CityConfig] = {
    "ludhiana": CityConfig(
        "ludhiana",
        "Ludhiana regional pilot",
        "Punjab",
        "openaq-5542",
        "Civil Line, Jalandhar (validated v1 regional replay)",
        5542,
        31.321907,
        75.578914,
    )
}

POLLUTANTS = {"pm2_5": "PM2.5", "pm10": "PM10"}
SOURCE_LABELS = {
    "traffic_and_transport": "Traffic and transport",
    "industrial_activity": "Industrial activity",
    "construction_and_resuspended_road_dust": "Construction and road dust",
    "waste_or_biomass_burning_activity": "Waste or biomass burning activity",
    "regional_thermal_anomaly_influence": "Regional thermal anomaly influence",
    "secondary_formation_and_meteorological_accumulation": "Meteorological accumulation",
    "background_or_unresolved_pollution": "Background or unresolved pollution",
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _finite(value: Any) -> float | None:
    try:
        number = float(value)
        return number if math.isfinite(number) else None
    except (TypeError, ValueError):
        return None


def _parse_time(value: Any) -> datetime | None:
    if value is None:
        return None
    try:
        stamp = pd.Timestamp(value)
        if stamp.tzinfo is None:
            stamp = stamp.tz_localize("UTC")
        return stamp.tz_convert("UTC").to_pydatetime()
    except Exception:
        return None


def _hourly_rows(payload: dict[str, Any], keys: list[str]) -> list[dict[str, Any]]:
    hourly = payload.get("hourly") or {}
    times = hourly.get("time") or []
    rows: list[dict[str, Any]] = []
    for index, time_value in enumerate(times):
        row: dict[str, Any] = {"timestamp_utc": str(time_value)}
        for key in keys:
            values = hourly.get(key) or []
            row[key] = _finite(values[index]) if index < len(values) else None
        rows.append(row)
    return rows


def _measurement_time(item: dict[str, Any]) -> datetime | None:
    period = item.get("period") or {}
    start = period.get("datetimeFrom") or period.get("datetime_from") or {}
    value = (start.get("utc") or start.get("local")) if isinstance(start, dict) else start
    value = value or item.get("datetime") or item.get("timestamp")
    if isinstance(value, dict):
        value = value.get("utc") or value.get("local")
    return _parse_time(value)


def _recent_history(openaq: dict[str, Any] | None, air_rows: list[dict[str, Any]]) -> pd.DataFrame:
    records: list[dict[str, Any]] = []
    if openaq:
        for pollutant, items in openaq.get("history", {}).items():
            for item in items:
                stamp = _measurement_time(item)
                value = _finite(item.get("value"))
                if stamp and value is not None:
                    records.append({"timestamp_utc": stamp, pollutant: value, "source": "OpenAQ"})
    observed = pd.DataFrame(records)
    if not observed.empty:
        observed = (
            observed.groupby("timestamp_utc", as_index=False).last().set_index("timestamp_utc")
        )
    model_records = []
    for row in air_rows:
        stamp = _parse_time(row["timestamp_utc"])
        if stamp:
            model_records.append(
                {
                    "timestamp_utc": stamp,
                    "pm2_5": row.get("pm2_5"),
                    "pm10": row.get("pm10"),
                    "o3": row.get("ozone"),
                    "source": "CAMS",
                }
            )
    model = pd.DataFrame(model_records)
    if model.empty:
        return (
            observed.reset_index()
            if not observed.empty
            else pd.DataFrame(columns=["timestamp_utc", "pm2_5", "pm10", "o3"])
        )
    model = model.groupby("timestamp_utc", as_index=False).last().set_index("timestamp_utc")
    if observed.empty:
        return model.reset_index().sort_values("timestamp_utc")
    combined = model.copy()
    for column in ("pm2_5", "pm10", "o3"):
        if column in observed:
            combined[column] = observed[column].combine_first(combined.get(column))
    combined["source"] = np.where(combined.index.isin(observed.index), "OpenAQ+CAMS", "CAMS")
    return combined.reset_index().sort_values("timestamp_utc")


def _latest_observation(
    pollutant: str,
    openaq: dict[str, Any] | None,
    aq_payload: dict[str, Any],
) -> dict[str, Any]:
    latest = (openaq or {}).get("latest", {}).get(pollutant)
    if latest:
        stamp = _parse_time(latest.get("timestamp_utc"))
        value = _finite(latest.get("value"))
        if stamp and value is not None and _now() - stamp <= timedelta(hours=18):
            return {
                "value": value,
                "timestamp_utc": stamp.isoformat(),
                "source": "OpenAQ station observation",
                "value_kind": "observed",
                "freshness": "recent" if _now() - stamp <= timedelta(hours=4) else "delayed",
            }
    current = aq_payload.get("current") or {}
    value = _finite(current.get(pollutant))
    stamp = _parse_time(current.get("time")) or _now()
    if value is not None:
        return {
            "value": value,
            "timestamp_utc": stamp.isoformat(),
            "source": "CAMS via Open-Meteo",
            "value_kind": "modelled_current",
            "freshness": "recent",
        }
    raise RuntimeError(f"No current {pollutant} value was returned")


def _calendar_features(stamp: datetime) -> dict[str, float | int]:
    hour = stamp.hour
    day = stamp.timetuple().tm_yday
    return {
        "hour": hour,
        "day_of_week": stamp.weekday(),
        "day_of_year": day,
        "month": stamp.month,
        "weekend": int(stamp.weekday() >= 5),
        "hour_sin": math.sin(2 * math.pi * hour / 24),
        "hour_cos": math.cos(2 * math.pi * hour / 24),
        "day_of_year_sin": math.sin(2 * math.pi * day / 365.25),
        "day_of_year_cos": math.cos(2 * math.pi * day / 365.25),
    }


def _feature_row(
    city: CityConfig,
    issue: datetime,
    weather_current: dict[str, Any],
    history: pd.DataFrame,
    schema: list[str],
) -> tuple[pd.DataFrame, float]:
    values: dict[str, Any] = {
        "city_id": city.city_id,
        "station_id": city.station_id,
        "latitude": city.latitude,
        "longitude": city.longitude,
        **_calendar_features(issue),
    }
    weather_map = {
        "temperature_2m": "temperature_2m",
        "relative_humidity_2m": "relative_humidity_2m",
        "surface_pressure": "surface_pressure",
        "precipitation": "precipitation",
        "cloud_cover": "cloud_cover",
        "wind_speed_10m": "wind_speed_10m",
        "wind_direction_10m": "wind_direction_10m",
        "wind_gusts_10m": "wind_gusts_10m",
        "shortwave_radiation": "shortwave_radiation",
    }
    for feature, source in weather_map.items():
        values[feature] = _finite(weather_current.get(source))
    recent = history.copy()
    if not recent.empty:
        recent["timestamp_utc"] = pd.to_datetime(recent["timestamp_utc"], utc=True)
        recent = recent[recent["timestamp_utc"] <= pd.Timestamp(issue)].sort_values("timestamp_utc")
    for feature in schema:
        if "_lag_" in feature:
            column, lag_text = feature.rsplit("_lag_", 1)
            lag = int(lag_text)
            series = recent[column].dropna() if column in recent else pd.Series(dtype=float)
            values[feature] = float(series.iloc[-lag]) if len(series) >= lag else None
        elif "_mean_" in feature or "_std_" in feature:
            marker = "_mean_" if "_mean_" in feature else "_std_"
            column, window_text = feature.rsplit(marker, 1)
            window = int(window_text)
            series = (
                recent[column].dropna().tail(window) if column in recent else pd.Series(dtype=float)
            )
            if len(series) >= max(2, window // 3):
                values[feature] = float(series.mean() if marker == "_mean_" else series.std())
            else:
                values[feature] = None
    frame = pd.DataFrame([{feature: values.get(feature) for feature in schema}])
    numeric = [feature for feature in schema if feature not in {"city_id", "station_id"}]
    completeness = float(frame[numeric].notna().sum(axis=1).iloc[0] / max(len(numeric), 1))
    return frame, completeness


def _model_candidate(
    city: CityConfig, pollutant: str, horizon: int
) -> tuple[Path | None, dict[str, Any]]:
    matrix = artifacts.json("outputs/reports/forecast_champion_matrix.json", default=[])
    selected = next(
        (
            item
            for item in matrix
            if item.get("city_id") == city.city_id
            and item.get("pollutant") == pollutant
            and int(item.get("horizon", 0)) == horizon
        ),
        None,
    )
    if selected and selected.get("selected_model") == "ridge" and selected.get("artifact"):
        return REPOSITORY_ROOT / selected["artifact"], {"scope": "city-local", **selected}
    registry = artifacts.json("models/forecasting/registry.json", default=[])
    global_model = next(
        (
            item
            for item in registry
            if item.get("pollutant") == pollutant
            and int(item.get("horizon", 0)) == horizon
            and item.get("family") == "ridge"
        ),
        None,
    )
    if global_model and global_model.get("artifact"):
        return REPOSITORY_ROOT / global_model["artifact"], {"scope": "global", **global_model}
    return None, {"scope": "persistence", "family": "persistence"}


@lru_cache(maxsize=24)
def _load_model(path: str) -> Any:
    return joblib.load(path)


def _endpoint_prediction(
    city: CityConfig,
    pollutant: str,
    horizon: int,
    issue: datetime,
    weather_current: dict[str, Any],
    history: pd.DataFrame,
    current_value: float,
) -> dict[str, Any]:
    folder, metadata = _model_candidate(city, pollutant, horizon)
    if folder is None or not (folder / "model.joblib").is_file():
        return {
            "value": current_value,
            "model": "persistence",
            "scope": "baseline",
            "feature_completeness": 0.0,
            "interval_half_width_90": max(20.0, current_value * 0.45),
        }
    schema = json.loads((folder / "feature_schema.json").read_text(encoding="utf-8"))
    row, completeness = _feature_row(city, issue, weather_current, history, schema)
    model = _load_model(str(folder / "model.joblib"))
    value = max(0.0, float(model.predict(row)[0]))
    width = _finite(metadata.get("interval_half_width_90"))
    if width is None:
        meta_file = folder / "metadata.json"
        meta = json.loads(meta_file.read_text(encoding="utf-8")) if meta_file.is_file() else {}
        width = _finite(meta.get("interval_half_width_90"))
    return {
        "value": value,
        "model": metadata.get("model_id") or metadata.get("selected_model") or "ridge",
        "scope": metadata.get("scope", "global"),
        "feature_completeness": completeness,
        "interval_half_width_90": width or max(20.0, value * 0.4),
    }


def _build_forecast(
    city: CityConfig,
    pollutant: str,
    horizon: int,
    current: dict[str, Any],
    air_rows: list[dict[str, Any]],
    weather_rows: list[dict[str, Any]],
    weather_current: dict[str, Any],
    history: pd.DataFrame,
) -> dict[str, Any]:
    issue = _parse_time(current["timestamp_utc"]) or _now()
    future_air = [row for row in air_rows if (_parse_time(row["timestamp_utc"]) or issue) > issue][
        :horizon
    ]
    if len(future_air) < min(24, horizon):
        raise RuntimeError("CAMS did not return enough future air-quality hours")
    weather_by_time = {str(row["timestamp_utc"]): row for row in weather_rows}
    current_model = next(
        (
            row.get(pollutant)
            for row in reversed(air_rows)
            if (_parse_time(row["timestamp_utc"]) or issue) <= issue
            and row.get(pollutant) is not None
        ),
        None,
    )
    live_bias = current["value"] - (
        float(current_model) if current_model is not None else current["value"]
    )
    endpoint_models = {
        end: _endpoint_prediction(
            city, pollutant, end, issue, weather_current, history, current["value"]
        )
        for end in (24, 48, 72)
        if end <= max(72, horizon)
    }
    endpoint_corrections: dict[int, float] = {}
    for end, model_info in endpoint_models.items():
        if len(future_air) >= end and future_air[end - 1].get(pollutant) is not None:
            base = float(future_air[end - 1][pollutant])
            model_weight = 0.35 if model_info["feature_completeness"] >= 0.55 else 0.18
            endpoint_corrections[end] = model_weight * (model_info["value"] - base)
    points: list[dict[str, Any]] = []
    recent_values = (
        [float(value) for value in history.get(pollutant, pd.Series(dtype=float)).dropna().tail(23)]
        if not history.empty and pollutant in history
        else []
    )
    rolling = recent_values[:]
    for index, row in enumerate(future_air, start=1):
        base = _finite(row.get(pollutant))
        if base is None:
            continue
        left = 0
        right = 24
        if index > 24:
            left, right = (24, 48) if index <= 48 else (48, 72)
        left_corr = endpoint_corrections.get(left, 0.0)
        right_corr = endpoint_corrections.get(right, endpoint_corrections.get(left, 0.0))
        ratio = (index - left) / max(right - left, 1)
        model_correction = left_corr + ratio * (right_corr - left_corr)
        bias_correction = live_bias * math.exp(-index / 18)
        prediction = max(0.0, base + bias_correction + model_correction)
        rolling.append(prediction)
        rolling = rolling[-24:]
        rolling_24h = float(np.mean(rolling)) if len(rolling) >= 18 else None
        index_value = sub_index(rolling_24h, pollutant) if rolling_24h is not None else None
        nearest = min((24, 48, 72), key=lambda value: abs(value - min(index, 72)))
        width = endpoint_models.get(nearest, {}).get(
            "interval_half_width_90", max(20.0, prediction * 0.4)
        )
        width = float(width) * (0.55 + 0.45 * min(index, nearest) / nearest)
        weather = weather_by_time.get(str(row["timestamp_utc"]), {})
        points.append(
            {
                "timestamp_utc": str(row["timestamp_utc"]),
                "prediction": round(prediction, 2),
                "provider_baseline": round(base, 2),
                "lower": round(max(0.0, prediction - width), 2),
                "upper": round(prediction + width, 2),
                "rolling_24h": round(rolling_24h, 2) if rolling_24h is not None else None,
                "aqi": index_value,
                "aqi_category": category(index_value),
                "weather": {
                    "wind_speed": weather.get("wind_speed_10m"),
                    "wind_direction": weather.get("wind_direction_10m"),
                    "boundary_layer_height": weather.get("boundary_layer_height"),
                    "precipitation": weather.get("precipitation"),
                },
            }
        )
    endpoint_summary = []
    for end in (24, 48, 72):
        if end <= len(points):
            model = endpoint_models[end]
            endpoint_summary.append(
                {
                    "horizon": end,
                    "prediction": points[end - 1]["prediction"],
                    "model": model["model"],
                    "scope": model["scope"],
                    "feature_completeness": round(model["feature_completeness"], 2),
                }
            )
    peak = max(points, key=lambda item: item["prediction"])
    return {
        "issue_timestamp": issue.isoformat(),
        "pollutant": pollutant,
        "pollutant_label": POLLUTANTS[pollutant],
        "unit": "µg/m³",
        "horizon_hours": horizon,
        "points": points,
        "peak": {
            "value": peak["prediction"],
            "timestamp_utc": peak["timestamp_utc"],
            "aqi": peak["aqi"],
            "category": peak["aqi_category"],
        },
        "endpoints": endpoint_summary,
        "method": "CAMS atmospheric forecast fused with live station bias and validated local/global Ridge endpoint models",
        "interval_method": "historical 90% residual calibration scaled by lead time",
    }


def _osm_row(city: CityConfig) -> dict[str, Any] | None:
    """Return spatial evidence only when it belongs to the selected station context."""

    try:
        frame = artifacts.parquet("data/processed/india/osm_city_features.parquet")
    except FileNotFoundError:
        return None
    rows = frame[frame["city_id"] == city.city_id]
    if rows.empty:
        return None
    row = {
        key: (None if pd.isna(value) else value) for key, value in rows.iloc[0].to_dict().items()
    }
    latitude = _finite(row.get("latitude"))
    longitude = _finite(row.get("longitude"))
    if latitude is None or longitude is None:
        return None
    # Prevent the old Jalandhar evidence row from being presented as live Ludhiana
    # evidence. Station-centred source proxies are intentionally local.
    if haversine_km(city.latitude, city.longitude, latitude, longitude) > 35:
        return None
    return row


def _stagnation(weather_current: dict[str, Any]) -> float:
    wind = _finite(weather_current.get("wind_speed_10m")) or 0.0
    boundary = _finite(weather_current.get("boundary_layer_height"))
    wind_score = max(0.0, 1.0 - wind / 6.0)
    boundary_score = max(0.0, 1.0 - (boundary or 700.0) / 1600.0)
    return min(1.0, 0.65 * wind_score + 0.35 * boundary_score)


def _source_intelligence(
    city: CityConfig,
    weather_current: dict[str, Any],
    firms: list[dict[str, Any]],
    forecast: dict[str, Any],
) -> dict[str, Any]:
    osm = _osm_row(city)
    candidates: list[dict[str, Any]] = []
    proxy_map = [
        ("traffic_and_transport", "traffic_emission_pressure_proxy"),
        ("industrial_activity", "industrial_activity_proxy"),
        ("construction_and_resuspended_road_dust", "construction_activity_proxy"),
        ("waste_or_biomass_burning_activity", "waste_activity_proxy"),
    ]
    for category_id, field in proxy_map:
        value = _finite((osm or {}).get(field))
        if value is not None:
            candidates.append(
                {
                    "category_id": category_id,
                    "raw": math.log1p(max(value, 0)),
                    "evidence": ["OpenStreetMap proximity/density proxy"],
                    "availability": "available",
                }
            )
        else:
            candidates.append(
                {
                    "category_id": category_id,
                    "raw": None,
                    "evidence": [],
                    "availability": "unavailable",
                }
            )
    nearby = [event for event in firms if (event.get("distance_km") or 9999) <= 300]
    thermal_raw = (
        math.log1p(sum((event.get("fire_radiative_power") or 1.0) for event in nearby))
        if nearby
        else 0.0
    )
    candidates.append(
        {
            "category_id": "regional_thermal_anomaly_influence",
            "raw": thermal_raw,
            "evidence": [f"{len(nearby)} near-real-time thermal anomalies within 300 km"]
            if nearby
            else ["No near-real-time thermal anomaly returned in the current lookback"],
            "availability": "available",
        }
    )
    stagnation_score = _stagnation(weather_current)
    candidates.append(
        {
            "category_id": "secondary_formation_and_meteorological_accumulation",
            "raw": 1.5 * stagnation_score,
            "evidence": ["Low-wind/boundary-layer accumulation indicator"],
            "availability": "available",
        }
    )
    candidates.append(
        {
            "category_id": "background_or_unresolved_pollution",
            "raw": 0.35,
            "evidence": [
                "Residual/background component retained because inventories are incomplete"
            ],
            "availability": "available",
        }
    )
    available_raw = [item["raw"] for item in candidates if item["raw"] is not None]
    maximum = max(available_raw, default=1.0)
    rankings = []
    for item in candidates:
        score = None if item["raw"] is None else float(item["raw"]) / max(maximum, 1e-9)
        confidence = (
            0.78
            if item["availability"] == "available"
            and item["category_id"]
            in {
                "regional_thermal_anomaly_influence",
                "secondary_formation_and_meteorological_accumulation",
            }
            else 0.62
            if item["availability"] == "available"
            else 0.0
        )
        rankings.append(
            {
                "category_id": item["category_id"],
                "label": SOURCE_LABELS[item["category_id"]],
                "influence": round(score, 3) if score is not None else None,
                "confidence": confidence,
                "evidence": item["evidence"],
                "availability": item["availability"],
            }
        )
    rankings.sort(
        key=lambda item: item["influence"] if item["influence"] is not None else -1, reverse=True
    )
    severity = forecast["peak"].get("aqi") or 0
    priority = (
        "Critical"
        if severity > 400
        else "High"
        if severity > 300
        else "Elevated"
        if severity > 200
        else "Watch"
    )
    return {
        "rankings": rankings,
        "priority": priority,
        "confidence": round(
            float(
                np.mean(
                    [item["confidence"] for item in rankings if item["availability"] == "available"]
                )
            ),
            2,
        ),
        "methodology": "Evidence-weighted source influence screening; not regulatory source apportionment",
        "osm_available": bool(osm and osm.get("osm_feature_available")),
        "firms_event_count": len(nearby),
    }


def _interventions(intelligence: dict[str, Any], forecast: dict[str, Any]) -> list[dict[str, Any]]:
    catalogue = artifacts.json("outputs/reports/intervention_catalogue.json", default=[])
    by_category = {item.get("source_category"): item for item in catalogue}
    actions = []
    for rank, item in enumerate(
        [entry for entry in intelligence["rankings"] if entry.get("influence") is not None][:3],
        start=1,
    ):
        catalogue_item = by_category.get(item["category_id"])
        if catalogue_item:
            action = catalogue_item.get("action")
            agency = catalogue_item.get("agency_type")
            response_time = catalogue_item.get("response_time")
            cost_tier = catalogue_item.get("cost_tier")
            caveat = catalogue_item.get("caveat")
        else:
            action = "Targeted field verification and source-control review"
            agency = "municipal and pollution-control authority"
            response_time = "within 24 hours"
            cost_tier = "low"
            caveat = "Confirm local evidence before enforcement action"
        reduction = min(12.0, max(2.0, (item["influence"] or 0) * 10))
        actions.append(
            {
                "rank": rank,
                "source_category": item["label"],
                "action": action,
                "agency": agency,
                "response_time": response_time,
                "cost_tier": cost_tier,
                "estimated_sensitivity_range_percent": [
                    round(reduction * 0.45, 1),
                    round(reduction, 1),
                ],
                "caveat": caveat,
            }
        )
    return actions


def _advisory(city: CityConfig, forecast: dict[str, Any], language: str) -> dict[str, Any]:
    peak = forecast["peak"]
    category_text = peak.get("category") or "Unclassified"
    pollutant = forecast["pollutant_label"]
    period_stamp = pd.Timestamp(peak["timestamp_utc"])
    if period_stamp.tzinfo is None:
        period_stamp = period_stamp.tz_localize("UTC")
    period = period_stamp.tz_convert("Asia/Kolkata").strftime("%d %b, %I:%M %p")
    texts = {
        "en": {
            "headline": f"{category_text} air-quality conditions are forecast in {city.name}",
            "summary": f"{pollutant} may peak near {peak['value']:.0f} µg/m³ around {period}.",
            "actions": [
                "Reduce prolonged outdoor exertion during the forecast peak.",
                "Schools and outdoor-work supervisors should reschedule strenuous activity where practical.",
                "People with heart or lung conditions should follow their clinician's existing advice and official local alerts.",
            ],
            "disclaimer": "Public-information guidance based on a model forecast. It is not medical advice.",
        },
        "hi": {
            "headline": f"{city.name} में वायु गुणवत्ता {category_text} श्रेणी तक पहुँचने का पूर्वानुमान है",
            "summary": f"{pollutant} लगभग {peak['value']:.0f} µg/m³ तक {period} के आसपास पहुँच सकता है।",
            "actions": [
                "पूर्वानुमानित चरम समय में लंबे समय तक बाहरी मेहनत कम करें।",
                "स्कूल और बाहरी कार्य पर्यवेक्षक संभव हो तो कठिन गतिविधियाँ पुनर्निर्धारित करें।",
                "हृदय या फेफड़ों की बीमारी वाले लोग अपने चिकित्सक की मौजूदा सलाह और आधिकारिक स्थानीय चेतावनियों का पालन करें।",
            ],
            "disclaimer": "यह मॉडल पूर्वानुमान पर आधारित सार्वजनिक सूचना है; यह चिकित्सीय सलाह नहीं है।",
        },
        "pa": {
            "headline": f"{city.name} ਵਿੱਚ ਹਵਾ ਦੀ ਗੁਣਵੱਤਾ {category_text} ਸ਼੍ਰੇਣੀ ਤੱਕ ਪਹੁੰਚਣ ਦੀ ਭਵਿੱਖਬਾਣੀ ਹੈ",
            "summary": f"{pollutant} ਲਗਭਗ {peak['value']:.0f} µg/m³ ਤੱਕ {period} ਦੇ ਨੇੜੇ ਪਹੁੰਚ ਸਕਦਾ ਹੈ।",
            "actions": [
                "ਭਵਿੱਖਬਾਣੀ ਕੀਤੇ ਚਰਮ ਸਮੇਂ ਦੌਰਾਨ ਲੰਬੀ ਬਾਹਰੀ ਮਿਹਨਤ ਘਟਾਓ।",
                "ਸਕੂਲ ਅਤੇ ਬਾਹਰੀ ਕੰਮ ਦੇ ਨਿਗਰਾਨ ਸੰਭਵ ਹੋਵੇ ਤਾਂ ਭਾਰੀ ਗਤੀਵਿਧੀਆਂ ਦਾ ਸਮਾਂ ਬਦਲਣ।",
                "ਦਿਲ ਜਾਂ ਫੇਫੜਿਆਂ ਦੀ ਬਿਮਾਰੀ ਵਾਲੇ ਲੋਕ ਆਪਣੇ ਡਾਕਟਰ ਦੀ ਮੌਜੂਦਾ ਸਲਾਹ ਅਤੇ ਸਰਕਾਰੀ ਸਥਾਨਕ ਚੇਤਾਵਨੀਆਂ ਦੀ ਪਾਲਣਾ ਕਰਨ।",
            ],
            "disclaimer": "ਇਹ ਮਾਡਲ ਭਵਿੱਖਬਾਣੀ ਅਧਾਰਿਤ ਜਨਤਕ ਜਾਣਕਾਰੀ ਹੈ; ਇਹ ਡਾਕਟਰੀ ਸਲਾਹ ਨਹੀਂ ਹੈ।",
        },
    }
    selected = texts.get(language, texts["en"])
    return {
        "language": language if language in texts else "en",
        "severity": category_text,
        **selected,
    }


def _grid(
    city: CityConfig, forecast: dict[str, Any], weather_current: dict[str, Any]
) -> list[dict[str, Any]]:
    peak = float(forecast["peak"]["value"])
    wind_direction = _finite(weather_current.get("wind_direction_10m")) or 0.0
    stagnation = _stagnation(weather_current)
    cells: list[dict[str, Any]] = []
    lat_step = 1.0 / 111.0
    lon_step = 1.0 / (111.0 * math.cos(math.radians(city.latitude)))
    for row in range(-2, 3):
        for column in range(-2, 3):
            lat = city.latitude + row * lat_step
            lon = city.longitude + column * lon_step
            distance = math.sqrt(row**2 + column**2)
            bearing_to_cell = (
                (math.degrees(math.atan2(column, row)) + 360) % 360 if distance else wind_direction
            )
            angular = abs((bearing_to_cell - wind_direction + 180) % 360 - 180)
            downwind = max(0.0, math.cos(math.radians(angular)))
            multiplier = (
                1
                + 0.08 * stagnation * math.exp(-distance / 2.2)
                + 0.05 * downwind * math.exp(-distance / 2.8)
            )
            value = max(0.0, peak * multiplier)
            idx = sub_index(value, forecast["pollutant"])
            cells.append(
                {
                    "cell_id": f"{city.city_id}-{row + 2}-{column + 2}",
                    "center": {"latitude": lat, "longitude": lon},
                    "bounds": [
                        [lat - lat_step / 2, lon - lon_step / 2],
                        [lat + lat_step / 2, lon + lon_step / 2],
                    ],
                    "forecast_peak": round(value, 1),
                    "aqi": idx,
                    "category": category(idx),
                    "resolution_m": 1000,
                    "method": "prototype_downscaled_intervention_grid",
                }
            )
    return cells


def _historical_context(
    city: CityConfig, pollutant: str, issue: datetime
) -> tuple[list[dict[str, Any]], dict[str, Any], list[dict[str, Any]]]:
    """Resolve replay source rankings, weather and mapped FIRMS events."""

    rankings: list[dict[str, Any]] = []
    try:
        attribution = artifacts.parquet(
            "data/processed/india/source_attribution/source_attribution.parquet"
        )
        subset = attribution[
            (attribution["city_id"] == city.city_id)
            & (attribution["pollutant"] == pollutant)
            & (attribution["forecast_horizon"] == 24)
        ].copy()
        if not subset.empty:
            subset["timestamp_utc"] = pd.to_datetime(subset["timestamp_utc"], utc=True)
            nearest_time = subset.iloc[
                (subset["timestamp_utc"] - pd.Timestamp(issue)).abs().argsort()[:1]
            ]["timestamp_utc"].iloc[0]
            rows = subset[subset["timestamp_utc"] == nearest_time].sort_values(
                "likelihood_score", ascending=False
            )
            for _, row in rows.iterrows():
                category_id = str(row["source_category"])
                evidence = row.get("dominant_evidence")
                rankings.append(
                    {
                        "category_id": category_id,
                        "label": SOURCE_LABELS.get(
                            category_id, category_id.replace("_", " ").title()
                        ),
                        "influence": _finite(row.get("likelihood_score")),
                        "confidence": _finite(row.get("confidence_score")) or 0.0,
                        "evidence": [str(evidence)] if evidence else [],
                        "availability": "available"
                        if (_finite(row.get("evidence_availability")) or 0) > 0
                        else "unavailable",
                    }
                )
    except (FileNotFoundError, KeyError):
        rankings = []

    weather_current: dict[str, Any] = {}
    try:
        features = artifacts.parquet("data/processed/india/station_hourly_features.parquet")
        subset = features[features["city_id"] == city.city_id].copy()
        if not subset.empty:
            subset["timestamp_utc"] = pd.to_datetime(subset["timestamp_utc"], utc=True)
            row = subset.iloc[
                (subset["timestamp_utc"] - pd.Timestamp(issue)).abs().argsort()[:1]
            ].iloc[0]
            for key in (
                "temperature_2m",
                "relative_humidity_2m",
                "surface_pressure",
                "wind_speed_10m",
                "wind_direction_10m",
                "boundary_layer_height",
            ):
                value = _finite(row.get(key))
                if value is not None:
                    weather_current[key] = value
    except (FileNotFoundError, KeyError):
        weather_current = {}

    firms: list[dict[str, Any]] = []
    try:
        events = artifacts.parquet("data/processed/india/firms_events.parquet")
        times = pd.to_datetime(events["timestamp_utc"], utc=True)
        start = pd.Timestamp(issue - timedelta(hours=24))
        subset = events[(times >= start) & (times <= pd.Timestamp(issue))].copy()
        if not subset.empty:
            lat_delta = 300 / 111
            lon_delta = 300 / (111 * max(math.cos(math.radians(city.latitude)), 0.2))
            subset = subset[
                subset["latitude"].between(city.latitude - lat_delta, city.latitude + lat_delta)
                & subset["longitude"].between(
                    city.longitude - lon_delta, city.longitude + lon_delta
                )
            ].copy()
            if not subset.empty:
                lat1 = np.radians(city.latitude)
                lon1 = np.radians(city.longitude)
                lat2 = np.radians(subset["latitude"].astype(float).to_numpy())
                lon2 = np.radians(subset["longitude"].astype(float).to_numpy())
                value = (
                    np.sin((lat2 - lat1) / 2) ** 2
                    + np.cos(lat1) * np.cos(lat2) * np.sin((lon2 - lon1) / 2) ** 2
                )
                subset["distance_km"] = 6371 * 2 * np.arcsin(np.sqrt(value))
                subset = subset[subset["distance_km"] <= 300]
                subset = subset.sort_values(
                    ["fire_radiative_power", "distance_km"],
                    ascending=[False, True],
                    na_position="last",
                ).head(100)
                for _, row in subset.iterrows():
                    firms.append(
                        {
                            "latitude": float(row["latitude"]),
                            "longitude": float(row["longitude"]),
                            "timestamp_utc": str(row["timestamp_utc"]),
                            "satellite": None
                            if pd.isna(row.get("satellite"))
                            else str(row.get("satellite")),
                            "instrument": None
                            if pd.isna(row.get("instrument"))
                            else str(row.get("instrument")),
                            "confidence": _finite(row.get("confidence")),
                            "fire_radiative_power": _finite(row.get("fire_radiative_power")),
                            "distance_km": round(float(row["distance_km"]), 1),
                        }
                    )
    except (FileNotFoundError, KeyError):
        firms = []
    return rankings, weather_current, firms


def _historical_replay(
    city: CityConfig, pollutant: str, horizon: int, language: str, error: str | None = None
) -> dict[str, Any]:
    replay_city = HISTORICAL_REPLAY_CITIES.get(city.city_id, city)
    coverage_note = (
        "The validated v1 fallback for Ludhiana uses a Punjab regional station at Civil Line, "
        "Jalandhar. Live mode targets PAU, Ludhiana; the two spatial contexts are not mixed."
        if city.city_id == "ludhiana"
        else None
    )
    replay_path = (
        REPOSITORY_ROOT
        / "outputs"
        / "examples"
        / "forecast_replays"
        / city.city_id
        / f"{pollutant}_{horizon}h.json"
    )
    if not replay_path.is_file():
        replay_path = (
            REPOSITORY_ROOT
            / "outputs"
            / "examples"
            / "forecast_replays"
            / city.city_id
            / f"{pollutant}_24h.json"
        )
    replay = json.loads(replay_path.read_text(encoding="utf-8"))
    points = []
    for point in replay.get("points", []):
        prediction = _finite(point.get("prediction"))
        if prediction is None:
            continue
        width = max(20.0, prediction * 0.35)
        idx = sub_index(prediction, pollutant)
        points.append(
            {
                "timestamp_utc": str(point.get("timestamp_utc")),
                "prediction": prediction,
                "provider_baseline": _finite(point.get("baseline")),
                "actual": _finite(point.get("actual")),
                "lower": max(0.0, prediction - width),
                "upper": prediction + width,
                "rolling_24h": prediction,
                "aqi": idx,
                "aqi_category": category(idx),
                "weather": {},
            }
        )
    peak = max(points, key=lambda item: item["prediction"])
    # Some early replay artifacts carried a placeholder issue_time. Derive the
    # operational replay issue from the first target timestamp so the UI and
    # evidence filters remain time-consistent.
    first_target = _parse_time(points[0]["timestamp_utc"]) if points else None
    replay_issue = first_target - timedelta(hours=1) if first_target else _parse_time(replay.get("issue_time")) or _now()
    forecast = {
        "issue_timestamp": replay_issue.isoformat(),
        "artifact_issue_timestamp": str(replay.get("issue_time")),
        "pollutant": pollutant,
        "pollutant_label": POLLUTANTS[pollutant],
        "unit": "µg/m³",
        "horizon_hours": len(points),
        "points": points,
        "peak": {
            "value": peak["prediction"],
            "timestamp_utc": peak["timestamp_utc"],
            "aqi": peak["aqi"],
            "category": peak["aqi_category"],
        },
        "endpoints": [],
        "method": "Validated historical replay",
        "interval_method": "illustrative replay interval",
    }
    priority_report = artifacts.json(
        "outputs/reports/enforcement_priority_report.json", default={"items": []}
    )
    priority_item = next(
        (item for item in priority_report.get("items", []) if item.get("city_id") == city.city_id),
        None,
    )
    issue = _parse_time(forecast["issue_timestamp"]) or _now()
    rankings, weather_current, replay_firms = _historical_context(replay_city, pollutant, issue)
    intelligence = {
        "rankings": rankings,
        "priority": (priority_item or {}).get("priority_tier", "Watch"),
        "confidence": (priority_item or {}).get("confidence", 0.55),
        "methodology": "Historical source-influence screening; not regulatory source apportionment",
        "osm_available": bool((_osm_row(replay_city) or {}).get("osm_feature_available")),
        "firms_event_count": len(replay_firms),
    }
    actions = _interventions(intelligence, forecast)
    if not actions:
        actions = [
            {
                "rank": 1,
                "source_category": "Field verification",
                "action": (priority_item or {}).get(
                    "recommended_inspection",
                    "Review high-priority locations and verify local conditions before action",
                ),
                "agency": "municipal and pollution-control authority",
                "response_time": "within 24 hours",
                "cost_tier": "low",
                "estimated_sensitivity_range_percent": None,
                "caveat": "Historical replay evidence; verify current conditions before enforcement",
            }
        ]
    return {
        "mode": "historical_replay",
        "live": False,
        "generated_at_utc": _now().isoformat(),
        "city": {
            **replay_city.__dict__,
            "requested_city_name": city.name,
            "coverage_note": coverage_note,
        },
        "current": {
            "value": points[0]["actual"]
            if points and points[0].get("actual") is not None
            else points[0]["prediction"],
            "timestamp_utc": forecast["issue_timestamp"],
            "source": "validated historical replay",
            "value_kind": "historical",
            "freshness": "historical",
        },
        "forecast": forecast,
        "weather": {"current": weather_current, "source": "historical station-aligned weather"},
        "map": {
            "station": {
                "latitude": replay_city.latitude,
                "longitude": replay_city.longitude,
                "name": replay_city.station_name,
            },
            "grid": _grid(replay_city, forecast, weather_current),
            "firms": replay_firms,
            "hotspot": None,
            "wind": {
                "speed": _finite(weather_current.get("wind_speed_10m")),
                "direction": _finite(weather_current.get("wind_direction_10m")),
            },
            "osm_available": intelligence["osm_available"],
            "grid_methodology": "Downscaled intervention grid derived from city-scale forecast, station correction, wind and stagnation; not an independently resolved 1 km atmospheric model.",
        },
        "intelligence": intelligence,
        "actions": actions,
        "advisory": _advisory(city, forecast, language),
        "provider_status": {
            "live_pipeline": "unavailable",
            "fallback": "validated historical replay",
            "reason": (
                "One or more operational feeds were unavailable; validated replay was loaded."
                if error
                else "Validated replay was selected by the operator."
            ),
        },
        "coverage_note": coverage_note,
        "disclaimer": "Historical replay fallback. This view is not a current operational forecast."
        + (f" {coverage_note}" if coverage_note else ""),
    }


async def build_dashboard(
    city_id: str, pollutant: str, horizon: int, language: str = "en", force_demo: bool = False
) -> dict[str, Any]:
    if city_id not in CITIES:
        raise ValueError("Unsupported city")
    if pollutant not in POLLUTANTS:
        raise ValueError("Unsupported pollutant")
    horizon = max(24, min(int(horizon), 72))
    city = CITIES[city_id]
    if force_demo:
        return _historical_replay(city, pollutant, horizon, language)
    try:
        aq_task = open_meteo_air_quality(city.latitude, city.longitude, 120)
        weather_task = open_meteo_weather(city.latitude, city.longitude, 120)
        openaq_task = openaq_recent(city.openaq_location_id, 168)
        firms_task = firms_near_real_time(city.latitude, city.longitude)
        results = await asyncio.gather(
            aq_task, weather_task, openaq_task, firms_task, return_exceptions=True
        )
        aq_payload, weather_payload, openaq_result, firms_result = results
        if isinstance(aq_payload, Exception) or isinstance(weather_payload, Exception):
            raise RuntimeError(
                f"Forecast providers unavailable: {aq_payload if isinstance(aq_payload, Exception) else weather_payload}"
            )
        air_rows = _hourly_rows(
            aq_payload, ["pm2_5", "pm10", "nitrogen_dioxide", "carbon_monoxide", "ozone", "dust"]
        )
        weather_rows = _hourly_rows(
            weather_payload,
            [
                "temperature_2m",
                "relative_humidity_2m",
                "surface_pressure",
                "precipitation",
                "cloud_cover",
                "visibility",
                "wind_speed_10m",
                "wind_direction_10m",
                "wind_gusts_10m",
                "boundary_layer_height",
                "weather_code",
            ],
        )
        openaq_payload = None if isinstance(openaq_result, Exception) else openaq_result
        firms = [] if isinstance(firms_result, Exception) else firms_result
        current = _latest_observation(pollutant, openaq_payload, aq_payload)
        weather_current = weather_payload.get("current") or {}
        history = _recent_history(openaq_payload, air_rows)
        forecast = _build_forecast(
            city, pollutant, horizon, current, air_rows, weather_rows, weather_current, history
        )
        intelligence = _source_intelligence(city, weather_current, firms, forecast)
        actions = _interventions(intelligence, forecast)
        map_events = [event for event in firms if (event.get("distance_km") or 9999) <= 300][:120]
        provider_status = {
            "air_quality_forecast": "Current CAMS numerical forecast",
            "weather_forecast": "Current numerical weather forecast",
            "station_observations": (
                "Recent OpenAQ station observation"
                if current["value_kind"] == "observed"
                else "Station feed unavailable or delayed; CAMS modelled current used"
            ),
            "thermal_anomalies": (
                "Near-real-time NASA FIRMS detections"
                if firms
                else (
                    "FIRMS feed unavailable"
                    if isinstance(firms_result, Exception)
                    else "No detections returned in the current lookback"
                )
            ),
        }
        return {
            "mode": "operational_forecast",
            "live": True,
            "generated_at_utc": _now().isoformat(),
            "city": {**city.__dict__, "coverage_note": None},
            "coverage_note": None,
            "current": current,
            "forecast": forecast,
            "weather": {
                "current": weather_current,
                "source": "Open-Meteo best-match numerical weather forecast",
            },
            "map": {
                "station": {
                    "latitude": city.latitude,
                    "longitude": city.longitude,
                    "name": city.station_name,
                },
                "grid": _grid(city, forecast, weather_current),
                "firms": map_events,
                "hotspot": {
                    "latitude": city.latitude,
                    "longitude": city.longitude,
                    "label": "Station-centred intervention hotspot",
                },
                "wind": {
                    "speed": _finite(weather_current.get("wind_speed_10m")),
                    "direction": _finite(weather_current.get("wind_direction_10m")),
                },
                "osm_available": intelligence["osm_available"],
            },
            "intelligence": intelligence,
            "actions": actions,
            "advisory": _advisory(city, forecast, language),
            "provider_status": provider_status,
            "disclaimer": "Operational prototype forecast. Source influence is screening, not regulatory source apportionment; intervention effects are sensitivity estimates, not causal claims.",
        }
    except Exception as exc:
        return _historical_replay(city, pollutant, horizon, language, str(exc))


def city_list() -> list[dict[str, Any]]:
    result = []
    for city in CITIES.values():
        result.append(
            {
                **city.__dict__,
                "pollutants": ["pm2_5", "pm10"],
                "live_capable": True,
                "forecast_horizons": [24, 48, 72],
            }
        )
    return result


async def build_network_overview(mode: str = "live") -> dict[str, Any]:
    """Return a compact five-city comparison without invoking the full heavy workflow."""

    async def one(city: CityConfig) -> dict[str, Any]:
        if mode == "demo":
            replay = _historical_replay(city, "pm2_5", 24, "en")
            return {
                "city_id": city.city_id,
                "city_name": city.name,
                "state": city.state,
                "current": replay["current"]["value"],
                "peak_24h": replay["forecast"]["peak"]["value"],
                "category": replay["forecast"]["peak"]["category"],
                "priority": replay["intelligence"]["priority"],
                "mode": "historical_replay",
                "timestamp_utc": replay["forecast"]["issue_timestamp"],
            }
        try:
            payload = await open_meteo_air_quality(city.latitude, city.longitude, 48)
            current = _latest_observation("pm2_5", None, payload)
            rows = _hourly_rows(payload, ["pm2_5"])
            issue = _parse_time(current["timestamp_utc"]) or _now()
            future = [
                row
                for row in rows
                if (_parse_time(row["timestamp_utc"]) or issue) > issue
                and row.get("pm2_5") is not None
            ][:24]
            if not future:
                raise RuntimeError("No 24-hour PM2.5 outlook was returned")
            peak = max(float(row["pm2_5"]) for row in future)
            rolling_index = sub_index(peak, "pm2_5")
            priority = (
                "Critical"
                if (rolling_index or 0) > 400
                else "High"
                if (rolling_index or 0) > 300
                else "Elevated"
                if (rolling_index or 0) > 200
                else "Watch"
            )
            return {
                "city_id": city.city_id,
                "city_name": city.name,
                "state": city.state,
                "current": current["value"],
                "peak_24h": round(peak, 1),
                "category": category(rolling_index),
                "priority": priority,
                "mode": "live_numerical_outlook",
                "timestamp_utc": current["timestamp_utc"],
            }
        except Exception:
            replay = _historical_replay(city, "pm2_5", 24, "en")
            return {
                "city_id": city.city_id,
                "city_name": city.name,
                "state": city.state,
                "current": replay["current"]["value"],
                "peak_24h": replay["forecast"]["peak"]["value"],
                "category": replay["forecast"]["peak"]["category"],
                "priority": replay["intelligence"]["priority"],
                "mode": "historical_replay",
                "timestamp_utc": replay["forecast"]["issue_timestamp"],
            }

    cities = await asyncio.gather(*(one(city) for city in CITIES.values()))
    return {
        "generated_at_utc": _now().isoformat(),
        "pollutant": "pm2_5",
        "unit": "µg/m³",
        "cities": cities,
        "methodology": "Compact city-scale 24-hour numerical outlook with validated replay fallback",
    }
