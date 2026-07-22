"""Live, partial-failure-safe operations for pilot and dynamically resolved Indian cities."""

from __future__ import annotations

import asyncio
import json
import math
from datetime import datetime, timezone
from functools import lru_cache
from typing import Any

import joblib
import pandas as pd

from app.services.artifacts import REPOSITORY_ROOT
from app.services.city_registry import CITIES
from app.services.city_support import (
    ResolvedCity,
    discover_stations,
    freshness,
    generate_city_grid,
    resolve_indian_city,
)
from app.services.decision import (
    AQI_COLOURS,
    aqi_result,
    canonical_context,
    coverage_confidence,
    forecast_peak,
    intervention_priority,
)
from app.services.live_providers import (
    cache,
    firms_near_real_time,
    open_meteo_air_quality,
    open_meteo_weather,
    osm_city_context,
)

_snapshot_locks: dict[str, asyncio.Lock] = {}


def _finite(value: Any) -> float | None:
    try:
        number = float(value)
        return number if math.isfinite(number) else None
    except (TypeError, ValueError):
        return None


def _time(value: Any) -> datetime | None:
    try:
        stamp = pd.Timestamp(value)
        if pd.isna(stamp):
            return None
        if stamp.tzinfo is None:
            stamp = stamp.tz_localize("UTC")
        return stamp.tz_convert("UTC").to_pydatetime()
    except Exception:
        return None


async def resolve_city_reference(query: str) -> ResolvedCity:
    slug = query.lower().strip().replace(" ", "-")
    if slug in CITIES:
        item = CITIES[slug]
        radius = 12.0
        lat_delta = radius / 111
        lon_delta = radius / (111 * max(math.cos(math.radians(item.latitude)), 0.2))
        return ResolvedCity(
            city_id=item.city_id,
            name=item.name,
            state=item.state,
            latitude=item.latitude,
            longitude=item.longitude,
            bounds=(
                item.latitude - lat_delta,
                item.longitude - lon_delta,
                item.latitude + lat_delta,
                item.longitude + lon_delta,
            ),
            boundary_geojson=None,
            bounds_source="configured_radius",
        )
    found = await resolve_indian_city(query)
    if not found:
        raise ValueError("No matching Indian city was found")
    return found[0]


def _hourly(payload: dict[str, Any], key: str) -> list[dict[str, Any]]:
    hourly = payload.get("hourly") or {}
    times, values = hourly.get("time") or [], hourly.get(key) or []
    return [
        {
            "timestamp_utc": str(stamp),
            "value": _finite(values[index]) if index < len(values) else None,
        }
        for index, stamp in enumerate(times)
    ]


def _station_current(stations: list[dict[str, Any]], pollutant: str) -> dict[str, Any] | None:
    for provider in ("CPCB/Data.gov.in", "OpenAQ"):
        for station in stations:
            latest = (station.get("latest") or {}).get(pollutant)
            if (
                station.get("provider") == provider
                and latest
                and _finite(latest.get("value")) is not None
            ):
                return {
                    "value": float(latest["value"]),
                    "timestamp_utc": latest.get("timestamp_utc"),
                    "provider": provider,
                    "station_id": station["station_id"],
                    "station_name": station["name"],
                    "freshness": station["freshness"],
                    "fallback": provider != "CPCB/Data.gov.in",
                    "value_kind": "observed",
                }
    return None


@lru_cache(maxsize=12)
def _load_global_model(pollutant: str, horizon: int) -> tuple[Any | None, dict[str, Any]]:
    folder = (
        REPOSITORY_ROOT / "models" / "forecasting" / "global_residual" / pollutant / str(horizon)
    )
    metadata_path = folder / "metadata.json"
    model_path = folder / "model.joblib"
    if not metadata_path.is_file() or not model_path.is_file():
        return None, {"status": "unavailable"}
    return joblib.load(model_path), json.loads(metadata_path.read_text(encoding="utf-8"))


def _residual_features(
    *,
    pollutant: str,
    current: float,
    target: float,
    latitude: float,
    longitude: float,
    issue: datetime,
    weather: dict[str, Any],
    station_residual: float | None,
    station_distance: float | None,
    station_age: float | None,
    station_count: int,
    firms: list[dict[str, Any]],
    osm: dict[str, Any],
) -> dict[str, float | None]:
    direction = math.radians(_finite(weather.get("wind_direction_10m")) or 0)
    return {
        "camps_current": current,
        "camps_target": target,
        "pollutant_lag_1": current,
        "pollutant_lag_6": current,
        "pollutant_lag_24": current,
        "pollutant_mean_6": current,
        "pollutant_mean_24": current,
        "other_pm_current": None,
        "temperature_2m": _finite(weather.get("temperature_2m")),
        "relative_humidity_2m": _finite(weather.get("relative_humidity_2m")),
        "surface_pressure": _finite(weather.get("surface_pressure")),
        "precipitation": _finite(weather.get("precipitation")),
        "wind_speed_10m": _finite(weather.get("wind_speed_10m")),
        "wind_direction_sin": math.sin(direction),
        "wind_direction_cos": math.cos(direction),
        "boundary_layer_height": _finite(weather.get("boundary_layer_height")),
        "latitude": latitude,
        "longitude": longitude,
        "hour_sin": math.sin(2 * math.pi * issue.hour / 24),
        "hour_cos": math.cos(2 * math.pi * issue.hour / 24),
        "day_of_year_sin": math.sin(2 * math.pi * issue.timetuple().tm_yday / 365.25),
        "day_of_year_cos": math.cos(2 * math.pi * issue.timetuple().tm_yday / 365.25),
        "month_sin": math.sin(2 * math.pi * issue.month / 12),
        "month_cos": math.cos(2 * math.pi * issue.month / 12),
        "nearby_station_residual": station_residual,
        "nearby_station_distance_km": station_distance,
        "nearby_station_age_hours": station_age,
        "nearby_station_count": station_count,
        "firms_count_24h": len(firms),
        "firms_frp_24h": sum(_finite(item.get("fire_radiative_power")) or 0 for item in firms),
        "road_count": _finite(osm.get("road_count")) or 0,
        "industrial_count": _finite(osm.get("industrial_count")) or 0,
        "construction_count": _finite(osm.get("construction_count")) or 0,
        "wind_relative_source_score": 0,
    }


def _weighted_residual(
    stations: list[dict[str, Any]],
    pollutant: str,
    camps_current: float,
    latitude: float,
    longitude: float,
) -> tuple[float | None, float | None, float | None]:
    weighted = 0.0
    total = 0.0
    nearest = None
    youngest = None
    for station in stations:
        latest = (station.get("latest") or {}).get(pollutant)
        value = _finite((latest or {}).get("value"))
        age = _finite((station.get("freshness") or {}).get("age_hours"))
        lat, lon = _finite(station.get("latitude")), _finite(station.get("longitude"))
        if value is None or lat is None or lon is None:
            continue
        distance = math.dist((latitude, longitude), (lat, lon)) * 111
        weight = math.exp(-distance / 25) * math.exp(-(age or 24) / 24)
        weighted += weight * (value - camps_current)
        total += weight
        nearest = distance if nearest is None else min(nearest, distance)
        youngest = age if youngest is None else min(youngest, age or 999)
    return (weighted / total if total else None, nearest, youngest)


def _wind_planning_adjustment(
    *,
    latitude: float,
    longitude: float,
    city: ResolvedCity,
    base: float,
    weather: dict[str, Any],
) -> float:
    """Return a bounded wind-aligned planning gradient around a city forecast.

    The value is modelled planning downscaling, not an observation or a calibrated
    street-scale dispersion estimate.
    """
    direction = _finite(weather.get("wind_direction_10m"))
    speed = _finite(weather.get("wind_speed_10m"))
    if direction is None or speed is None or speed <= 0:
        return 0.0
    east_km = (longitude - city.longitude) * 111 * max(math.cos(math.radians(city.latitude)), 0.2)
    north_km = (latitude - city.latitude) * 111
    downwind = math.radians((direction + 180) % 360)
    projected_km = east_km * math.sin(downwind) + north_km * math.cos(downwind)
    amplitude = min(max(base * 0.04, 0.6), 5.0) * min(speed / 4.0, 1.0)
    return amplitude * math.tanh(projected_km / 5.0)


async def build_dynamic_snapshot(
    query: str, pollutant: str, horizon: int, max_cells: int = 400, include_sources: bool = True
) -> dict[str, Any]:
    cache_key = (
        f"dynamic-snapshot:{query.lower()}:{pollutant}:{horizon}:{max_cells}:{include_sources}"
    )
    cached = await cache.get(cache_key)
    if cached is not None:
        return cached
    lock = _snapshot_locks.setdefault(cache_key, asyncio.Lock())
    async with lock:
        cached = await cache.get(cache_key)
        if cached is not None:
            return cached
        return await _build_dynamic_snapshot(query, pollutant, horizon, max_cells, include_sources)


async def _build_dynamic_snapshot(
    query: str, pollutant: str, horizon: int, max_cells: int = 400, include_sources: bool = True
) -> dict[str, Any]:
    if pollutant not in {"pm2_5", "pm10"} or horizon not in {24, 48, 72}:
        raise ValueError("Pollutant must be pm2_5/pm10 and horizon must be 24/48/72")
    cache_key = (
        f"dynamic-snapshot:{query.lower()}:{pollutant}:{horizon}:{max_cells}:{include_sources}"
    )
    city = await resolve_city_reference(query)
    south, west, north, east = city.bounds
    air_result, weather_result, station_result, firms_result, osm_result = await asyncio.gather(
        asyncio.wait_for(open_meteo_air_quality(city.latitude, city.longitude, 120), 12),
        asyncio.wait_for(open_meteo_weather(city.latitude, city.longitude, 120), 12),
        asyncio.wait_for(discover_stations(city, pollutant), 18),
        asyncio.wait_for(firms_near_real_time(city.latitude, city.longitude), 10)
        if include_sources
        else asyncio.sleep(0, result=RuntimeError("not requested")),
        asyncio.wait_for(osm_city_context(south, west, north, east), 10)
        if include_sources
        else asyncio.sleep(0, result=RuntimeError("not requested")),
        return_exceptions=True,
    )
    provider_status = {
        "cams": {
            "status": "unavailable" if isinstance(air_result, Exception) else "available",
            "provider": "CAMS via Open-Meteo",
            "fallback": False,
        },
        "weather": {
            "status": "unavailable" if isinstance(weather_result, Exception) else "available",
            "provider": "Open-Meteo",
            "fallback": False,
        },
        "stations": {
            "status": "unavailable" if isinstance(station_result, Exception) else "available",
            "provider": "CPCB/Data.gov.in and OpenAQ",
            "fallback": False,
        },
        "firms": {
            "status": "unavailable" if isinstance(firms_result, Exception) else "available",
            "provider": "NASA FIRMS",
            "fallback": False,
        },
        "osm": {
            "status": "unavailable" if isinstance(osm_result, Exception) else "available",
            "provider": "OpenStreetMap/Overpass",
            "fallback": False,
        },
    }
    stations = [] if isinstance(station_result, Exception) else station_result["stations"]
    station_candidate_count = (
        0
        if isinstance(station_result, Exception)
        else int(station_result.get("candidate_count", len(stations)))
    )
    firms = [] if isinstance(firms_result, Exception) else firms_result[:120]
    osm = {} if isinstance(osm_result, Exception) else osm_result
    if not isinstance(station_result, Exception):
        station_sources = station_result.get("provider_status", {})
        available_sources = sum(value == "available" for value in station_sources.values())
        provider_status["stations"]["status"] = (
            "available"
            if available_sources == len(station_sources) and available_sources
            else "partial"
            if available_sources
            else "unavailable"
        )
        provider_status["stations"]["sources"] = station_sources
    air = {} if isinstance(air_result, Exception) else air_result
    weather = {} if isinstance(weather_result, Exception) else weather_result
    station_current = _station_current(stations, pollutant)
    cams_current = _finite((air.get("current") or {}).get(pollutant))
    cams_time = (air.get("current") or {}).get("time")
    current = station_current
    if current is None and cams_current is not None:
        current = {
            "value": cams_current,
            "timestamp_utc": cams_time,
            "provider": "CAMS via Open-Meteo",
            "station_id": None,
            "station_name": None,
            "freshness": freshness(_time(cams_time)),
            "fallback": True,
            "value_kind": "modelled_current",
        }
    issue = _time((current or {}).get("timestamp_utc"))
    if issue is None:
        now = datetime.now(timezone.utc)
        issue = now.replace(minute=(now.minute // 15) * 15, second=0, microsecond=0)
    current_assessment = aqi_result(_finite((current or {}).get("value")), pollutant)
    if current is not None:
        current = {**current, **current_assessment}
    coverage_type = "station_corrected" if stations else "model_based"
    context = canonical_context(
        city=city.dict(),
        pollutant=pollutant,
        horizon=horizon,
        issue_timestamp=issue.isoformat(),
        freshness=(current or {}).get("freshness") or {"label": "unavailable", "age_hours": None},
        coverage_type=coverage_type,
        provider_versions=provider_status,
    )
    forecast_rows = _hourly(air, pollutant) if air else []
    future = [row for row in forecast_rows if (_time(row["timestamp_utc"]) or issue) > issue][
        :horizon
    ]
    weather_current = weather.get("current") or {}
    provider_status["cams"]["timestamp_utc"] = (air.get("current") or {}).get("time")
    provider_status["weather"]["timestamp_utc"] = weather_current.get("time")
    provider_status["firms"]["timestamp_utc"] = max(
        (str(item.get("timestamp_utc")) for item in firms if item.get("timestamp_utc")),
        default=None,
    )
    provider_status["osm"]["timestamp_utc"] = osm.get("retrieved_at_utc")
    centre_residual, nearest, youngest = (
        _weighted_residual(stations, pollutant, cams_current, city.latitude, city.longitude)
        if cams_current is not None
        else (None, None, None)
    )
    model, metadata = _load_global_model(pollutant, horizon)
    endpoint_correction = 0.0
    if model is not None and cams_current is not None and len(future) >= horizon:
        features = _residual_features(
            pollutant=pollutant,
            current=cams_current,
            target=float(future[horizon - 1]["value"]),
            latitude=city.latitude,
            longitude=city.longitude,
            issue=issue,
            weather=weather_current,
            station_residual=centre_residual,
            station_distance=nearest,
            station_age=youngest,
            station_count=len(stations),
            firms=firms,
            osm=osm,
        )
        scale = 1.0 if metadata.get("champion") == "hist_gradient_boosting_residual" else 0.0
        endpoint_correction = scale * float(model.predict(pd.DataFrame([features]))[0])
    points = []
    for index, row in enumerate(future, 1):
        base = _finite(row["value"])
        if base is None:
            continue
        ml_correction = endpoint_correction * index / max(horizon, 1)
        station_correction = (centre_residual or 0) * math.exp(-index / 18)
        prediction = max(0.0, base + ml_correction + station_correction)
        rolling = prediction if index >= 24 else None
        points.append(
            {
                "timestamp_utc": row["timestamp_utc"],
                "prediction": round(prediction, 2),
                "cams": base,
                "global_residual_correction": round(ml_correction, 2),
                "station_residual_correction": round(station_correction, 2),
                "rolling_24h": rolling,
                **aqi_result(rolling, pollutant),
            }
        )
    peak = forecast_peak(points, pollutant)
    feature_completeness = 1.0 if weather_current else 0.55
    core_provider_status = [provider_status[key] for key in ("cams", "weather", "stations")]
    provider_fraction = sum(
        1.0 if value["status"] == "available" else 0.5 if value["status"] == "partial" else 0.0
        for value in core_provider_status
    ) / len(core_provider_status)
    confidence = coverage_confidence(
        len(stations), youngest, provider_fraction, feature_completeness
    )
    priority = intervention_priority(current_assessment.get("aqi"), confidence)
    forecast_priority = intervention_priority((peak or {}).get("aqi"), confidence)
    observations = sorted(
        [
            {**item, "station_id": station["station_id"], "provider": station["provider"]}
            for station in stations
            for item in station.get("observations_24h", [])
            if item.get("pollutant") == pollutant and item.get("timestamp_utc")
        ],
        key=lambda item: item["timestamp_utc"],
    )
    grid = generate_city_grid(city, max_cells=max_cells)
    grid_features = []
    endpoint_base = (
        float(future[-1]["value"]) if future and future[-1]["value"] is not None else None
    )
    cell_inputs: list[tuple[dict[str, Any], float | None, dict[str, float | None] | None]] = []
    for feature in grid["features"]:
        lon, lat = feature["properties"]["center"]
        residual, distance, age = (
            _weighted_residual(stations, pollutant, cams_current, lat, lon)
            if cams_current is not None
            else (None, None, None)
        )
        values = None
        if model is not None and cams_current is not None and endpoint_base is not None:
            values = _residual_features(
                pollutant=pollutant,
                current=cams_current,
                target=endpoint_base,
                latitude=lat,
                longitude=lon,
                issue=issue,
                weather=weather_current,
                station_residual=residual,
                station_distance=distance,
                station_age=age,
                station_count=len(stations),
                firms=firms,
                osm=osm,
            )
        cell_inputs.append((feature, residual, values))
    corrections = [endpoint_correction] * len(cell_inputs)
    model_rows = [values for _, _, values in cell_inputs if values is not None]
    if model is not None and model_rows:
        scale = 1.0 if metadata.get("champion") == "hist_gradient_boosting_residual" else 0.0
        predictions = model.predict(pd.DataFrame(model_rows))
        prediction_index = 0
        for index, (_, _, values) in enumerate(cell_inputs):
            if values is not None:
                corrections[index] = scale * float(predictions[prediction_index])
                prediction_index += 1
    for (feature, residual, _), correction in zip(cell_inputs, corrections, strict=True):
        longitude, latitude = feature["properties"]["center"]
        spatial_adjustment = (
            _wind_planning_adjustment(
                latitude=latitude,
                longitude=longitude,
                city=city,
                base=endpoint_base,
                weather=weather_current,
            )
            if endpoint_base is not None
            else 0.0
        )
        forecast_station_correction = (residual or 0) * math.exp(-horizon / 18)
        forecast_value = (
            max(
                0.0,
                endpoint_base + correction + forecast_station_correction + spatial_adjustment,
            )
            if endpoint_base is not None
            else None
        )
        current_spatial_adjustment = (
            _wind_planning_adjustment(
                latitude=latitude,
                longitude=longitude,
                city=city,
                base=cams_current,
                weather=weather_current,
            )
            if cams_current is not None
            else 0.0
        )
        current_value = (
            max(0.0, cams_current + (residual or 0) + current_spatial_adjustment)
            if cams_current is not None
            else None
        )
        feature["properties"].update(
            {
                "current": None if current_value is None else round(current_value, 2),
                "forecast": None if forecast_value is None else round(forecast_value, 2),
                "station_residual_correction": round(forecast_station_correction, 2),
                "planning_spatial_adjustment": round(spatial_adjustment, 2),
                "coverage_type": "station_corrected" if residual is not None else "model_based",
                "confidence": confidence if residual is not None else round(confidence * 0.7, 3),
                **aqi_result(current_value, pollutant),
            }
        )
        grid_features.append(feature)
    response = {
        "context": context,
        "current": current,
        "observations_24h": observations,
        "stations": stations,
        "station_summary": {
            "available_count": station_candidate_count,
            "selected_count": len(stations),
        },
        "forecast": {
            "status": "available" if points else "unavailable",
            "points": points,
            "peak": peak,
            "priority": forecast_priority,
            "model": metadata,
            "method": "Live CAMS + validation-selected persistence-residual transfer + freshness-weighted station residual",
        },
        "map": {
            **grid,
            "features": grid_features,
            "metadata": {
                **grid["metadata"],
                "layer_kind": "current",
                "category_legend": [
                    {"category": label, "colour": colour} for label, colour in AQI_COLOURS.items()
                ],
            },
            "firms": firms,
            "osm": osm,
            "planning_method": "Live CAMS plus validation-selected persistence-residual transfer, lead-decayed station interpolation and bounded wind-aligned planning downscaling",
        },
        "intelligence": {
            "priority": priority,
            "confidence": confidence,
            "firms_count": len(firms),
            "osm": osm,
        },
        "actions": []
        if priority == "Unavailable"
        else [
            {
                "priority": priority,
                "action": "Verify leading source indicators in the highest forecast cells before field action.",
            }
        ],
        "advisory": {
            "status": "unavailable" if current is None else "available",
            "category": current_assessment.get("category"),
            "message": "Follow current local authority guidance and reduce prolonged outdoor exposure during elevated periods."
            if current
            else None,
        },
        "provider_status": provider_status,
    }
    await cache.set(cache_key, response, 300)
    return response
