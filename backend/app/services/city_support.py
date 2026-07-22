"""Dynamic Indian-city resolution, station discovery, and bounded city grids."""

from __future__ import annotations

import asyncio
import hashlib
import math
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from shapely.geometry import box, mapping, shape

from app.services.live_providers import (
    cpcb_data_gov_stations,
    haversine_km,
    nominatim_city_search,
    openaq_nearby_locations,
    openaq_recent,
)


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")


def _number(value: Any) -> float | None:
    try:
        result = float(value)
        return result if math.isfinite(result) else None
    except (TypeError, ValueError):
        return None


def _stamp(value: Any) -> datetime | None:
    if not value:
        return None
    text = str(value).strip()
    for candidate in (text, text.replace("/", "-")):
        try:
            parsed = datetime.fromisoformat(candidate.replace("Z", "+00:00"))
            return parsed.replace(tzinfo=parsed.tzinfo or timezone.utc).astimezone(timezone.utc)
        except ValueError:
            pass
    for pattern in ("%d-%m-%Y %H:%M:%S", "%d-%m-%Y %H:%M", "%d/%m/%Y %H:%M:%S"):
        try:
            india_time = timezone(timedelta(hours=5, minutes=30))
            return (
                datetime.strptime(text, pattern).replace(tzinfo=india_time).astimezone(timezone.utc)
            )
        except ValueError:
            pass
    return None


def freshness(timestamp: datetime | None) -> dict[str, Any]:
    age_hours = None
    if timestamp:
        age_hours = max(0.0, (datetime.now(timezone.utc) - timestamp).total_seconds() / 3600)
    label = "unknown"
    if age_hours is not None:
        label = "recent" if age_hours <= 4 else "delayed" if age_hours <= 24 else "stale"
    return {"label": label, "age_hours": None if age_hours is None else round(age_hours, 2)}


@dataclass(frozen=True)
class ResolvedCity:
    city_id: str
    name: str
    state: str | None
    latitude: float
    longitude: float
    bounds: tuple[float, float, float, float]
    boundary_geojson: dict[str, Any] | None
    bounds_source: str
    provider: str = "OpenStreetMap Nominatim"

    def dict(self) -> dict[str, Any]:
        return asdict(self)


async def resolve_indian_city(query: str, fallback_radius_km: float = 12) -> list[ResolvedCity]:
    if len(query.strip()) < 2:
        raise ValueError("City search requires at least two characters")
    rows = await nominatim_city_search(query)
    result: list[ResolvedCity] = []
    for row in rows:
        address = row.get("address") or {}
        country_code = str(address.get("country_code") or "").lower()
        if country_code and country_code != "in":
            continue
        lat = _number(row.get("lat"))
        lon = _number(row.get("lon"))
        if lat is None or lon is None:
            continue
        raw_bounds = row.get("boundingbox") or []
        if len(raw_bounds) == 4 and all(_number(value) is not None for value in raw_bounds):
            south, north, west, east = (float(value) for value in raw_bounds)
            bounds = (south, west, north, east)
            source = "nominatim_boundary"
        else:
            lat_delta = fallback_radius_km / 111
            lon_delta = fallback_radius_km / (111 * max(math.cos(math.radians(lat)), 0.2))
            bounds = (lat - lat_delta, lon - lon_delta, lat + lat_delta, lon + lon_delta)
            source = "configured_radius"
        osm_identity = f"{row.get('osm_type', 'place')}-{row.get('osm_id', '')}"
        identifier = hashlib.sha1(osm_identity.encode(), usedforsecurity=False).hexdigest()[:8]
        name = (
            address.get("city")
            or address.get("town")
            or address.get("municipality")
            or address.get("county")
            or str(row.get("display_name") or query).split(",")[0]
        )
        result.append(
            ResolvedCity(
                city_id=f"india-{_slug(str(name))}-{identifier}",
                name=str(name),
                state=address.get("state"),
                latitude=lat,
                longitude=lon,
                bounds=bounds,
                boundary_geojson=row.get("geojson"),
                bounds_source=source,
            )
        )
    return result


def _normalise_cpcb(records: list[dict[str, Any]], city: ResolvedCity) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    for record in records:
        pollutant = str(record.get("pollutant_id") or record.get("pollutant") or "").lower()
        pollutant = "pm2_5" if pollutant.replace(".", "") in {"pm25", "pm2_5"} else pollutant
        if pollutant not in {"pm2_5", "pm10"}:
            continue
        name = str(record.get("station") or record.get("station_name") or "CPCB station")
        identifier = str(record.get("station_id") or f"cpcb-{_slug(name)}")
        item = grouped.setdefault(
            identifier,
            {
                "station_id": identifier,
                "name": name,
                "provider": "CPCB/Data.gov.in",
                "latitude": _number(record.get("latitude")),
                "longitude": _number(record.get("longitude")),
                "latest": {},
                "pollutants": [],
                "observations_24h": [],
            },
        )
        timestamp = _stamp(record.get("last_update") or record.get("timestamp"))
        value = _number(record.get("avg_value") or record.get("value"))
        if value is not None:
            item["latest"][pollutant] = {
                "value": value,
                "timestamp_utc": timestamp.isoformat() if timestamp else None,
            }
            item["observations_24h"].append(
                {
                    "pollutant": pollutant,
                    "value": value,
                    "timestamp_utc": timestamp.isoformat() if timestamp else None,
                }
            )
            item["pollutants"].append(pollutant)
    rows = list(grouped.values())
    for row in rows:
        row["pollutants"] = sorted(set(row["pollutants"]))
        if row["latitude"] is not None and row["longitude"] is not None:
            row["distance_km"] = haversine_km(
                city.latitude, city.longitude, row["latitude"], row["longitude"]
            )
        else:
            row["distance_km"] = None
    return rows


def _openaq_parameter(sensor: dict[str, Any]) -> str | None:
    parameter = sensor.get("parameter") or {}
    value = str(parameter.get("name") or parameter.get("displayName") or "").lower()
    normal = value.replace(".", "").replace("-", "").replace("_", "").replace(" ", "")
    return "pm2_5" if normal == "pm25" else "pm10" if normal == "pm10" else None


async def _normalise_openaq(
    locations: list[dict[str, Any]], city: ResolvedCity, candidate_limit: int = 5
) -> list[dict[str, Any]]:
    candidates = []
    for location in locations:
        coordinates = location.get("coordinates") or {}
        lat = _number(coordinates.get("latitude"))
        lon = _number(coordinates.get("longitude"))
        if lat is None or lon is None:
            continue
        pollutants = sorted(
            {
                value
                for sensor in location.get("sensors", [])
                if (value := _openaq_parameter(sensor))
            }
        )
        if not pollutants:
            continue
        candidates.append((haversine_km(city.latitude, city.longitude, lat, lon), location))
    candidates.sort(key=lambda item: item[0])
    selected = candidates[:candidate_limit]
    histories = await asyncio.gather(
        *(openaq_recent(int(item[1]["id"]), 24) for item in selected), return_exceptions=True
    )
    rows: list[dict[str, Any]] = []
    for (distance, location), recent in zip(selected, histories, strict=True):
        if isinstance(recent, Exception):
            continue
        coordinates = location.get("coordinates") or {}
        latest = recent.get("latest", {})
        observations = []
        for parameter, items in (recent.get("history") or {}).items():
            if parameter not in {"pm2_5", "pm10"}:
                continue
            for item in items:
                period = item.get("period") or {}
                start = period.get("datetimeFrom") or period.get("datetime_from") or {}
                stamp = (
                    (start.get("utc") or start.get("local")) if isinstance(start, dict) else start
                )
                value = _number(item.get("value"))
                if stamp and value is not None:
                    observations.append(
                        {"pollutant": parameter, "value": value, "timestamp_utc": str(stamp)}
                    )
        rows.append(
            {
                "station_id": f"openaq-{location['id']}",
                "name": str(location.get("name") or f"OpenAQ {location['id']}"),
                "provider": "OpenAQ",
                "latitude": float(coordinates["latitude"]),
                "longitude": float(coordinates["longitude"]),
                "distance_km": round(distance, 2),
                "pollutants": sorted(key for key in latest if key in {"pm2_5", "pm10"}),
                "latest": latest,
                "observations_24h": observations,
            }
        )
    return rows


def rank_and_select_stations(
    stations: list[dict[str, Any]], pollutant: str, limit: int = 5, separation_km: float = 2
) -> list[dict[str, Any]]:
    ranked: list[dict[str, Any]] = []
    provider_score = {"CPCB/Data.gov.in": 1.0, "OpenAQ": 0.85}
    for station in stations:
        latest = (station.get("latest") or {}).get(pollutant)
        if not latest or _number(latest.get("value")) is None:
            continue
        timestamp = _stamp(latest.get("timestamp_utc"))
        fresh = freshness(timestamp)
        if fresh["age_hours"] is None or fresh["age_hours"] > 48:
            continue
        freshness_score = math.exp(-(fresh["age_hours"] or 48) / 24)
        completeness = len(station.get("pollutants") or []) / 2
        distance = _number(station.get("distance_km"))
        distance_score = math.exp(-(distance or 50) / 40)
        score = (
            0.45 * freshness_score
            + 0.25 * completeness
            + 0.2 * distance_score
            + 0.1 * provider_score.get(str(station.get("provider")), 0.5)
        )
        ranked.append({**station, "freshness": fresh, "selection_score": round(score, 4)})
    ranked.sort(key=lambda item: item["selection_score"], reverse=True)
    chosen: list[dict[str, Any]] = []
    for station in ranked:
        lat, lon = _number(station.get("latitude")), _number(station.get("longitude"))
        if lat is None or lon is None:
            continue
        separated = all(
            haversine_km(lat, lon, item["latitude"], item["longitude"]) >= separation_km
            for item in chosen
        )
        if separated or not chosen:
            chosen.append(station)
        if len(chosen) >= max(1, min(limit, 5)):
            break
    return chosen


async def discover_stations(city: ResolvedCity, pollutant: str, limit: int = 5) -> dict[str, Any]:
    cpcb_result, openaq_result = await asyncio.gather(
        asyncio.wait_for(cpcb_data_gov_stations(city.name), 7),
        asyncio.wait_for(openaq_nearby_locations(city.latitude, city.longitude), 7),
        return_exceptions=True,
    )
    stations: list[dict[str, Any]] = []
    statuses: dict[str, str] = {}
    if isinstance(cpcb_result, Exception):
        statuses["cpcb_data_gov"] = "unavailable"
    else:
        stations.extend(_normalise_cpcb(cpcb_result, city))
        statuses["cpcb_data_gov"] = "available"
    if isinstance(openaq_result, Exception):
        statuses["openaq"] = "unavailable"
    else:
        try:
            stations.extend(await asyncio.wait_for(_normalise_openaq(openaq_result, city), 10))
            statuses["openaq"] = "available"
        except Exception:
            statuses["openaq"] = "unavailable"
    selected_stations = rank_and_select_stations(stations, pollutant, limit)
    available_count = 0
    for station in stations:
        latest = (station.get("latest") or {}).get(pollutant)
        age = freshness(_stamp((latest or {}).get("timestamp_utc")))["age_hours"]
        if latest and age is not None and age <= 48:
            available_count += 1
    return {
        "stations": selected_stations,
        "provider_status": statuses,
        "candidate_count": available_count,
    }


def generate_city_grid(
    city: ResolvedCity, max_cells: int = 400, resolution_m: int = 1000
) -> dict[str, Any]:
    """Build approximately 1 km cells clipped to the resolved AOI and bounded by count."""
    south, west, north, east = city.bounds
    lat_step = resolution_m / 111000
    lon_step = resolution_m / (111000 * max(math.cos(math.radians(city.latitude)), 0.2))
    boundary = None
    if city.boundary_geojson:
        try:
            boundary = shape(city.boundary_geojson)
        except (TypeError, ValueError):
            boundary = None
    used_provider_boundary = bool(
        boundary is not None
        and boundary.is_valid
        and boundary.geom_type in {"Polygon", "MultiPolygon"}
    )
    boundary = boundary if used_provider_boundary else box(west, south, east, north)
    candidates: list[tuple[float, Any]] = []
    row = 0
    lat = south
    while lat < north:
        column = 0
        lon = west
        while lon < east:
            raw = box(lon, lat, min(lon + lon_step, east), min(lat + lat_step, north))
            clipped = raw.intersection(boundary)
            if not clipped.is_empty and clipped.area >= raw.area * 0.15:
                centroid = clipped.centroid
                distance = haversine_km(city.latitude, city.longitude, centroid.y, centroid.x)
                candidates.append((distance, (row, column, clipped, centroid)))
            column += 1
            lon += lon_step
        row += 1
        lat += lat_step
    truncated = len(candidates) > max_cells
    candidates.sort(key=lambda item: item[0])
    features = []
    for _, (row, column, geometry, centroid) in candidates[:max_cells]:
        features.append(
            {
                "type": "Feature",
                "id": f"{city.city_id}-{row}-{column}",
                "geometry": mapping(geometry),
                "properties": {
                    "cell_id": f"{city.city_id}-{row}-{column}",
                    "center": [centroid.x, centroid.y],
                    "resolution_m": resolution_m,
                },
            }
        )
    return {
        "type": "FeatureCollection",
        "features": features,
        "metadata": {
            "city_id": city.city_id,
            "resolution_m": resolution_m,
            "cell_count": len(features),
            "eligible_cell_count": len(candidates),
            "truncated": truncated,
            "bounds_source": city.bounds_source,
            "clipped_to_boundary": used_provider_boundary,
        },
    }
