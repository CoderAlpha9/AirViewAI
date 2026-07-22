"""Live provider clients with bounded timeouts, retries and TTL caching."""

from __future__ import annotations

import asyncio
import csv
import io
import math
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

from app.core.config import get_settings


@dataclass
class CacheEntry:
    expires_at: float
    value: Any


class TTLCache:
    def __init__(self) -> None:
        self._items: dict[str, CacheEntry] = {}
        self._lock = asyncio.Lock()

    async def get(self, key: str) -> Any | None:
        async with self._lock:
            entry = self._items.get(key)
            if not entry or entry.expires_at <= time.monotonic():
                self._items.pop(key, None)
                return None
            return entry.value

    async def set(self, key: str, value: Any, ttl_seconds: int) -> None:
        async with self._lock:
            self._items[key] = CacheEntry(time.monotonic() + ttl_seconds, value)


cache = TTLCache()


async def _json_get(
    url: str,
    *,
    params: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    timeout_seconds: float = 15,
    attempts: int = 2,
) -> dict[str, Any] | list[Any]:
    last: Exception | None = None
    timeout = httpx.Timeout(connect=5, read=timeout_seconds, write=10, pool=5)
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
        for attempt in range(attempts):
            try:
                response = await client.get(url, params=params, headers=headers)
                response.raise_for_status()
                return response.json()
            except (
                Exception
            ) as exc:  # provider errors are returned as availability metadata upstream
                last = exc
                if attempt + 1 < attempts:
                    await asyncio.sleep(0.35 * (attempt + 1))
    assert last is not None
    raise last


async def open_meteo_air_quality(
    latitude: float, longitude: float, hours: int = 96
) -> dict[str, Any]:
    key = f"omaq:{latitude:.5f}:{longitude:.5f}:{hours}"
    cached = await cache.get(key)
    if cached is not None:
        return cached
    payload = await _json_get(
        "https://air-quality-api.open-meteo.com/v1/air-quality",
        params={
            "latitude": latitude,
            "longitude": longitude,
            "current": "pm2_5,pm10,nitrogen_dioxide,carbon_monoxide,ozone,dust",
            "hourly": "pm2_5,pm10,nitrogen_dioxide,carbon_monoxide,ozone,dust",
            "forecast_hours": max(72, min(hours, 120)),
            "past_days": 7,
            "timezone": "UTC",
        },
    )
    await cache.set(key, payload, 900)
    return payload


async def open_meteo_weather(latitude: float, longitude: float, hours: int = 96) -> dict[str, Any]:
    key = f"omwx:{latitude:.5f}:{longitude:.5f}:{hours}"
    cached = await cache.get(key)
    if cached is not None:
        return cached
    payload = await _json_get(
        "https://api.open-meteo.com/v1/forecast",
        params={
            "latitude": latitude,
            "longitude": longitude,
            "current": "temperature_2m,relative_humidity_2m,surface_pressure,wind_speed_10m,wind_direction_10m,weather_code",
            "hourly": "temperature_2m,relative_humidity_2m,surface_pressure,precipitation,cloud_cover,visibility,wind_speed_10m,wind_direction_10m,wind_gusts_10m,boundary_layer_height,weather_code",
            "forecast_hours": max(72, min(hours, 120)),
            "past_days": 7,
            "timezone": "UTC",
            "wind_speed_unit": "ms",
        },
    )
    await cache.set(key, payload, 900)
    return payload


def _sensor_parameter(sensor: dict[str, Any]) -> str | None:
    parameter = sensor.get("parameter") or {}
    name = str(parameter.get("name") or parameter.get("displayName") or "").lower().replace(".", "")
    mapping = {
        "pm25": "pm2_5",
        "pm2_5": "pm2_5",
        "pm10": "pm10",
        "o3": "o3",
        "no2": "no2",
        "co": "co",
        "so2": "so2",
    }
    return mapping.get(name.replace(" ", "").replace("-", "_"))


async def openaq_recent(location_id: int, hours: int = 168) -> dict[str, Any]:
    settings = get_settings()
    if not settings.openaq_api_key:
        raise RuntimeError("OPENAQ_API_KEY is not configured")
    key = f"openaq:{location_id}:{hours}"
    cached = await cache.get(key)
    if cached is not None:
        return cached
    headers = {"X-API-Key": settings.openaq_api_key}
    sensors_payload, latest_payload = await asyncio.gather(
        _json_get(f"https://api.openaq.org/v3/locations/{location_id}/sensors", headers=headers),
        _json_get(f"https://api.openaq.org/v3/locations/{location_id}/latest", headers=headers),
    )
    sensors = sensors_payload.get("results", []) if isinstance(sensors_payload, dict) else []
    sensor_map = {
        int(sensor["id"]): _sensor_parameter(sensor) for sensor in sensors if sensor.get("id")
    }
    sensor_map = {key_: value for key_, value in sensor_map.items() if value}
    end = datetime.now(timezone.utc)
    start = end - timedelta(hours=hours)

    async def history(sensor_id: int, parameter: str) -> tuple[str, list[dict[str, Any]]]:
        try:
            payload = await _json_get(
                f"https://api.openaq.org/v3/sensors/{sensor_id}/measurements/hourly",
                headers=headers,
                params={
                    "datetime_from": start.isoformat(),
                    "datetime_to": end.isoformat(),
                    "limit": 1000,
                },
                timeout_seconds=18,
            )
            return parameter, payload.get("results", []) if isinstance(payload, dict) else []
        except Exception:
            return parameter, []

    history_results = await asyncio.gather(
        *(history(sensor_id, parameter) for sensor_id, parameter in sensor_map.items())
    )
    histories: dict[str, list[dict[str, Any]]] = {}
    for parameter, rows in history_results:
        histories.setdefault(parameter, []).extend(rows)

    latest: dict[str, dict[str, Any]] = {}
    results = latest_payload.get("results", []) if isinstance(latest_payload, dict) else []
    for item in results:
        sensor_id = item.get("sensorsId") or item.get("sensorId") or item.get("sensors_id")
        parameter = sensor_map.get(int(sensor_id)) if sensor_id is not None else None
        if not parameter:
            continue
        dt = item.get("datetime") or {}
        stamp = dt.get("utc") if isinstance(dt, dict) else item.get("datetime")
        latest[parameter] = {
            "value": item.get("value"),
            "timestamp_utc": stamp,
            "sensor_id": sensor_id,
        }
    value = {"latest": latest, "history": histories, "sensor_map": sensor_map}
    await cache.set(key, value, 300)
    return value


def _parse_firms_time(row: dict[str, str]) -> datetime | None:
    date_text = row.get("acq_date")
    time_text = str(row.get("acq_time") or "").zfill(4)
    if not date_text or len(time_text) != 4:
        return None
    try:
        return datetime.fromisoformat(f"{date_text}T{time_text[:2]}:{time_text[2:]}:00+00:00")
    except ValueError:
        return None


def haversine_km(lat_a: float, lon_a: float, lat_b: float, lon_b: float) -> float:
    latitude_delta = math.radians(lat_b - lat_a)
    longitude_delta = math.radians(lon_b - lon_a)
    value = (
        math.sin(latitude_delta / 2) ** 2
        + math.cos(math.radians(lat_a))
        * math.cos(math.radians(lat_b))
        * math.sin(longitude_delta / 2) ** 2
    )
    return 6371 * 2 * math.asin(math.sqrt(value))


async def firms_near_real_time(
    latitude: float, longitude: float, radius_degrees: float = 3.0
) -> list[dict[str, Any]]:
    settings = get_settings()
    if not settings.nasa_firms_map_key:
        raise RuntimeError("NASA_FIRMS_MAP_KEY is not configured")
    key = f"firms:{latitude:.3f}:{longitude:.3f}:{radius_degrees:.2f}"
    cached = await cache.get(key)
    if cached is not None:
        return cached
    bbox = f"{longitude - radius_degrees},{latitude - radius_degrees},{longitude + radius_degrees},{latitude + radius_degrees}"
    url = f"https://firms.modaps.eosdis.nasa.gov/api/area/csv/{settings.nasa_firms_map_key}/VIIRS_SNPP_NRT/{bbox}/1"
    timeout = httpx.Timeout(connect=5, read=18, write=10, pool=5)
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
        response = await client.get(url)
        response.raise_for_status()
    rows: list[dict[str, Any]] = []
    for row in csv.DictReader(io.StringIO(response.text)):
        stamp = _parse_firms_time(row)
        if stamp is None:
            continue
        try:
            event_lat = float(row["latitude"])
            event_lon = float(row["longitude"])
        except (KeyError, TypeError, ValueError):
            continue
        rows.append(
            {
                "latitude": event_lat,
                "longitude": event_lon,
                "timestamp_utc": stamp.isoformat(),
                "satellite": row.get("satellite"),
                "instrument": row.get("instrument"),
                "confidence": row.get("confidence"),
                "fire_radiative_power": _number(row.get("frp")),
                "distance_km": haversine_km(latitude, longitude, event_lat, event_lon),
            }
        )
    rows.sort(
        key=lambda item: (item.get("distance_km") or 9999, -(item.get("fire_radiative_power") or 0))
    )
    await cache.set(key, rows, 1800)
    return rows


def _number(value: Any) -> float | None:
    try:
        number = float(value)
        return number if math.isfinite(number) else None
    except (TypeError, ValueError):
        return None
