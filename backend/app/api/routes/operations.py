"""Production-facing operational dashboard endpoints."""

from __future__ import annotations

import asyncio
from typing import Literal

from fastapi import APIRouter, HTTPException, Query

from app.core.config import get_settings
from app.services.operational import (
    CITIES,
    POLLUTANTS,
    build_dashboard,
    build_network_overview,
    city_list,
)

router = APIRouter(prefix="/operations")


@router.get("/status")
def operations_status() -> dict[str, object]:
    settings = get_settings()
    return {
        "service": "AirView AI operational intelligence",
        "status": "ready",
        "default_mode": "live",
        "supported_modes": ["live", "demo"],
        "supported_cities": len(CITIES),
        "supported_pollutants": list(POLLUTANTS),
        "forecast_horizons": [24, 48, 72],
        "providers": {
            "openaq": "configured" if settings.openaq_api_key else "not_configured",
            "open_meteo_air_quality": "available_without_key",
            "open_meteo_weather": "available_without_key",
            "nasa_firms": "configured" if settings.nasa_firms_map_key else "not_configured",
        },
        "fallback": "validated historical replay",
    }


@router.get("/cities")
def operations_cities() -> dict[str, object]:
    return {"data": city_list(), "count": len(CITIES)}


@router.get("/dashboard")
async def operations_dashboard(
    city_id: str = Query(default="delhi-ncr"),
    pollutant: Literal["pm2_5", "pm10"] = Query(default="pm2_5"),
    horizon: int = Query(default=72, ge=24, le=72),
    language: Literal["en", "hi", "pa"] = Query(default="en"),
    mode: Literal["live", "demo"] = Query(default="live"),
) -> dict[str, object]:
    if city_id not in CITIES:
        raise HTTPException(status_code=404, detail="The selected city is not configured.")
    if horizon not in {24, 48, 72}:
        raise HTTPException(status_code=422, detail="Forecast horizon must be 24, 48, or 72 hours.")
    settings = get_settings()
    try:
        result = await asyncio.wait_for(
            build_dashboard(
                city_id=city_id,
                pollutant=pollutant,
                horizon=horizon,
                language=language,
                force_demo=mode == "demo",
            ),
            timeout=max(settings.live_provider_timeout_seconds * 2.5, 35),
        )
    except TimeoutError as exc:
        raise HTTPException(
            status_code=504,
            detail="Live providers did not respond in time. Retry or switch to validated replay mode.",
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return result


@router.get("/network")
async def operations_network(
    mode: Literal["live", "demo"] = Query(default="live"),
) -> dict[str, object]:
    return await build_network_overview(mode)
