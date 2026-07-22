"""Dynamic live-city API with canonical snapshot contexts."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException, Query

from app.services.city_support import resolve_indian_city
from app.services.dynamic_operational import build_dynamic_snapshot

router = APIRouter(prefix="/live")


@router.get("/cities/search")
async def city_search(
    q: str = Query(min_length=2), fallback_radius_km: float = Query(12, ge=3, le=50)
) -> dict:
    try:
        cities = await resolve_indian_city(q, fallback_radius_km)
    except RuntimeError as exc:
        raise HTTPException(503, "City search provider is temporarily unavailable") from exc
    return {"data": [city.dict() for city in cities], "count": len(cities)}


async def _snapshot(
    city: str,
    pollutant: Literal["pm2_5", "pm10"],
    horizon: int,
    max_cells: int,
    include_sources: bool = True,
) -> dict:
    try:
        return await build_dynamic_snapshot(city, pollutant, horizon, max_cells, include_sources)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.get("/snapshot")
async def snapshot(
    city: str = "delhi-ncr",
    pollutant: Literal["pm2_5", "pm10"] = "pm2_5",
    horizon: int = Query(24, ge=24, le=72),
    max_cells: int = Query(400, ge=25, le=800),
) -> dict:
    return await _snapshot(city, pollutant, horizon, max_cells)


async def _panel(
    panel: str,
    city: str,
    pollutant: Literal["pm2_5", "pm10"],
    horizon: int,
    max_cells: int = 400,
    include_sources: bool = True,
) -> dict:
    payload = await _snapshot(city, pollutant, horizon, max_cells, include_sources)
    return {
        "context": payload["context"],
        "data": payload[panel],
        "provider_status": payload["provider_status"],
    }


@router.get("/current")
async def current(
    city: str = "delhi-ncr",
    pollutant: Literal["pm2_5", "pm10"] = "pm2_5",
    horizon: int = Query(24, ge=24, le=72),
) -> dict:
    return await _panel("current", city, pollutant, horizon)


@router.get("/stations")
async def stations(
    city: str = "delhi-ncr",
    pollutant: Literal["pm2_5", "pm10"] = "pm2_5",
    horizon: int = Query(24, ge=24, le=72),
) -> dict:
    payload = await _snapshot(city, pollutant, horizon, 400, True)
    return {
        "context": payload["context"],
        "data": {**payload["station_summary"], "stations": payload["stations"]},
        "provider_status": payload["provider_status"],
    }


@router.get("/forecast")
async def forecast(
    city: str = "delhi-ncr",
    pollutant: Literal["pm2_5", "pm10"] = "pm2_5",
    horizon: int = Query(24, ge=24, le=72),
) -> dict:
    return await _panel("forecast", city, pollutant, horizon)


@router.get("/map")
async def map_grid(
    city: str = "delhi-ncr",
    pollutant: Literal["pm2_5", "pm10"] = "pm2_5",
    horizon: int = Query(24, ge=24, le=72),
    max_cells: int = Query(400, ge=25, le=800),
) -> dict:
    return await _panel("map", city, pollutant, horizon, max_cells, True)


@router.get("/source-intelligence")
async def source_intelligence(
    city: str = "delhi-ncr",
    pollutant: Literal["pm2_5", "pm10"] = "pm2_5",
    horizon: int = Query(24, ge=24, le=72),
) -> dict:
    return await _panel("intelligence", city, pollutant, horizon)


@router.get("/actions")
async def actions(
    city: str = "delhi-ncr",
    pollutant: Literal["pm2_5", "pm10"] = "pm2_5",
    horizon: int = Query(24, ge=24, le=72),
) -> dict:
    return await _panel("actions", city, pollutant, horizon)


@router.get("/advisory")
async def advisory(
    city: str = "delhi-ncr",
    pollutant: Literal["pm2_5", "pm10"] = "pm2_5",
    horizon: int = Query(24, ge=24, le=72),
) -> dict:
    return await _panel("advisory", city, pollutant, horizon)
