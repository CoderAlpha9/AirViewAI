"""Live provider clients with bounded timeouts, retries and TTL caching."""

from __future__ import annotations

import asyncio
import csv
import io
import math
import re
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

DATA_GOV_RESOURCE_ID = "3b01bcb8-0b14-4abf-b6f2-c1bfd384ba69"
USER_AGENT = "AirViewAI/0.2 (urban-air-quality-research)"


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
            except httpx.HTTPStatusError as exc:
                # Invalid requests and unavailable credentials will not improve on retry.
                # Rate limits remain retryable because providers can clear them quickly.
                last = exc
                if 400 <= exc.response.status_code < 500 and exc.response.status_code != 429:
                    raise
                if attempt + 1 < attempts:
                    await asyncio.sleep(0.35 * (attempt + 1))
            except Exception as exc:  # availability metadata is assembled upstream
                last = exc
                if attempt + 1 < attempts:
                    await asyncio.sleep(0.35 * (attempt + 1))
    assert last is not None
    raise last


async def _text_get(
    url: str,
    *,
    headers: dict[str, str] | None = None,
    timeout_seconds: float = 18,
    attempts: int = 2,
) -> str:
    last: Exception | None = None
    timeout = httpx.Timeout(connect=5, read=timeout_seconds, write=10, pool=5)
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
        for attempt in range(attempts):
            try:
                response = await client.get(url, headers=headers)
                response.raise_for_status()
                return response.text
            except Exception as exc:
                last = exc
                if attempt + 1 < attempts:
                    await asyncio.sleep(0.4 * (attempt + 1))
    assert last is not None
    raise last


async def _json_post(
    url: str,
    *,
    data: dict[str, str],
    headers: dict[str, str] | None = None,
    timeout_seconds: float = 30,
    attempts: int = 2,
) -> dict[str, Any] | list[Any]:
    last: Exception | None = None
    timeout = httpx.Timeout(connect=6, read=timeout_seconds, write=10, pool=6)
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
        for attempt in range(attempts):
            try:
                response = await client.post(url, data=data, headers=headers)
                response.raise_for_status()
                return response.json()
            except Exception as exc:
                last = exc
                if attempt + 1 < attempts:
                    await asyncio.sleep(0.5 * (attempt + 1))
    assert last is not None
    raise last


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")


async def nominatim_city_search(query: str, limit: int = 5) -> list[dict[str, Any]]:
    """Resolve Indian settlements with Nominatim, including AOI geometry when available."""
    key = f"nominatim:{_slug(query)}:{limit}"
    cached = await cache.get(key)
    if cached is not None:
        return cached
    payload = await _json_get(
        "https://nominatim.openstreetmap.org/search",
        params={
            "q": query,
            "countrycodes": "in",
            "format": "jsonv2",
            "addressdetails": 1,
            "polygon_geojson": 1,
            "limit": max(1, min(limit, 10)),
        },
        headers={"User-Agent": USER_AGENT},
        timeout_seconds=12,
        attempts=3,
    )
    rows = payload if isinstance(payload, list) else []
    await cache.set(key, rows, 86400)
    return rows


async def openaq_nearby_locations(
    latitude: float, longitude: float, radius_km: float = 50, limit: int = 100
) -> list[dict[str, Any]]:
    """Discover OpenAQ locations near a coordinate; measurements remain provider data."""
    settings = get_settings()
    if not settings.openaq_api_key:
        raise RuntimeError("OPENAQ_API_KEY is not configured")
    # OpenAQ v3 caps coordinate searches at 25 km.
    radius_m = int(max(1000, min(radius_km * 1000, 25000)))
    key = f"openaq-locations:{latitude:.4f}:{longitude:.4f}:{radius_m}:{limit}"
    cached = await cache.get(key)
    if cached is not None:
        return cached
    payload = await _json_get(
        "https://api.openaq.org/v3/locations",
        params={
            "coordinates": f"{latitude},{longitude}",
            "radius": radius_m,
            "limit": max(1, min(limit, 1000)),
        },
        headers={"X-API-Key": settings.openaq_api_key},
        timeout_seconds=18,
        attempts=3,
    )
    rows = payload.get("results", []) if isinstance(payload, dict) else []
    await cache.set(key, rows, 900)
    return rows


async def cpcb_data_gov_stations(city_name: str, limit: int = 500) -> list[dict[str, Any]]:
    """Fetch current CAAQMS records from the official Data.gov.in CPCB resource."""
    settings = get_settings()
    if not settings.data_gov_in_api_key:
        raise RuntimeError("DATA_GOV_IN_API_KEY is not configured")
    key = f"cpcb:{_slug(city_name)}:{limit}"
    cached = await cache.get(key)
    if cached is not None:
        return cached
    payload = await _json_get(
        f"https://api.data.gov.in/resource/{DATA_GOV_RESOURCE_ID}",
        params={
            "api-key": settings.data_gov_in_api_key,
            "format": "json",
            "limit": max(1, min(limit, 1000)),
            "filters[city]": city_name,
        },
        timeout_seconds=20,
        attempts=3,
    )
    records = payload.get("records", []) if isinstance(payload, dict) else []
    await cache.set(key, records, 300)
    return records


async def osm_city_context(south: float, west: float, north: float, east: float) -> dict[str, Any]:
    """Fetch bounded road/industrial/land-use evidence from Overpass."""
    key = f"overpass:{south:.3f}:{west:.3f}:{north:.3f}:{east:.3f}"
    cached = await cache.get(key)
    if cached is not None:
        return cached
    query = (
        f"[out:json][timeout:25];(way[highway]({south},{west},{north},{east});"
        f'way[landuse~"industrial|construction|commercial"]({south},{west},{north},{east});'
        f'node[amenity~"hospital|clinic|school"]({south},{west},{north},{east}););'
        "out tags center 3000;"
    )
    payload = await _json_post(
        "https://overpass-api.de/api/interpreter",
        data={"data": query},
        headers={"User-Agent": USER_AGENT},
        timeout_seconds=30,
        attempts=2,
    )
    elements = payload.get("elements", []) if isinstance(payload, dict) else []
    tags = [item.get("tags", {}) for item in elements]
    value = {
        "retrieved_at_utc": _utc_now().isoformat(),
        "road_count": sum("highway" in tag for tag in tags),
        "industrial_count": sum(tag.get("landuse") == "industrial" for tag in tags),
        "construction_count": sum(tag.get("landuse") == "construction" for tag in tags),
        "commercial_count": sum(tag.get("landuse") == "commercial" for tag in tags),
        "sensitive_location_count": sum(
            tag.get("amenity") in {"hospital", "clinic", "school"} for tag in tags
        ),
        "feature_count": len(elements),
        "provider": "OpenStreetMap/Overpass",
    }
    await cache.set(key, value, 86400)
    return value


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

    latest: dict[str, dict[str, Any]] = {}
    results = latest_payload.get("results", []) if isinstance(latest_payload, dict) else []
    for item in results:
        sensor_id = item.get("sensorsId") or item.get("sensorId") or item.get("sensors_id")
        parameter = sensor_map.get(int(sensor_id)) if sensor_id is not None else None
        if not parameter:
            continue
        dt = item.get("datetime") or {}
        stamp = dt.get("utc") if isinstance(dt, dict) else item.get("datetime")
        try:
            observed = datetime.fromisoformat(str(stamp).replace("Z", "+00:00"))
            if observed.tzinfo is None:
                observed = observed.replace(tzinfo=timezone.utc)
        except (TypeError, ValueError):
            continue
        if end - observed.astimezone(timezone.utc) > timedelta(hours=48):
            continue
        latest[parameter] = {
            "value": item.get("value"),
            "timestamp_utc": stamp,
            "sensor_id": sensor_id,
        }

    fresh_parameters = set(latest)
    fresh_sensor_map = {
        sensor_id: parameter
        for sensor_id, parameter in sensor_map.items()
        if parameter in fresh_parameters
    }

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
        *(history(sensor_id, parameter) for sensor_id, parameter in fresh_sensor_map.items())
    )
    histories: dict[str, list[dict[str, Any]]] = {}
    for parameter, rows in history_results:
        histories.setdefault(parameter, []).extend(rows)

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
    text = await _text_get(url, timeout_seconds=18, attempts=3)
    rows: list[dict[str, Any]] = []
    for row in csv.DictReader(io.StringIO(text)):
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
