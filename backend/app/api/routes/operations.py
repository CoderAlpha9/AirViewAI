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
        "supported_cities": len(CITIES),
        "supported_pollutants": list(POLLUTANTS),
        "forecast_horizons": [24, 48, 72],
        "providers": {
            "openaq": "configured" if settings.openaq_api_key else "not_configured",
            "open_meteo_air_quality": "available_without_key",
            "open_meteo_weather": "available_without_key",
            "nasa_firms": "configured" if settings.nasa_firms_map_key else "not_configured",
        },
        "fallback": "per-panel unavailable state; historical artifacts are not served to operators",
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
                force_demo=False,
            ),
            timeout=max(settings.live_provider_timeout_seconds * 2.5, 35),
        )
    except TimeoutError as exc:
        raise HTTPException(
            status_code=504,
            detail="Live providers did not respond in time. Retry shortly.",
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return result


@router.get("/network")
async def operations_network(
) -> dict[str, object]:
    return await build_network_overview("live")


async def _panel(
    panel: Literal["current", "forecast", "map", "intelligence", "actions", "advisory"],
    city_id: str,
    pollutant: Literal["pm2_5", "pm10"],
    horizon: int,
    language: Literal["en", "hi", "pa"],
) -> dict[str, object]:
    """Return one independently refreshable operational panel.

    The shared provider TTL cache makes simultaneous panel requests inexpensive while
    keeping failures isolated at the HTTP boundary for the browser.
    """
    dashboard = await operations_dashboard(city_id, pollutant, horizon, language)
    return {
        "context": {
            "city": dashboard["city"],
            "generated_at_utc": dashboard["generated_at_utc"],
            "issue_timestamp": dashboard["forecast"]["issue_timestamp"],
            "pollutant": pollutant,
            "horizon": horizon,
        },
        "data": dashboard[panel],
        "provider_status": dashboard["provider_status"],
    }


@router.get("/current")
async def operations_current(
    city_id: str = Query(default="delhi-ncr"),
    pollutant: Literal["pm2_5", "pm10"] = Query(default="pm2_5"),
    horizon: int = Query(default=72, ge=24, le=72),
    language: Literal["en", "hi", "pa"] = Query(default="en"),
) -> dict[str, object]:
    return await _panel("current", city_id, pollutant, horizon, language)


@router.get("/forecast-panel")
async def operations_forecast_panel(
    city_id: str = Query(default="delhi-ncr"), pollutant: Literal["pm2_5", "pm10"] = Query(default="pm2_5"),
    horizon: int = Query(default=72, ge=24, le=72), language: Literal["en", "hi", "pa"] = Query(default="en"),
) -> dict[str, object]:
    return await _panel("forecast", city_id, pollutant, horizon, language)


@router.get("/map")
async def operations_map(
    city_id: str = Query(default="delhi-ncr"), pollutant: Literal["pm2_5", "pm10"] = Query(default="pm2_5"),
    horizon: int = Query(default=72, ge=24, le=72), language: Literal["en", "hi", "pa"] = Query(default="en"),
) -> dict[str, object]:
    return await _panel("map", city_id, pollutant, horizon, language)


@router.get("/intelligence")
async def operations_intelligence(
    city_id: str = Query(default="delhi-ncr"), pollutant: Literal["pm2_5", "pm10"] = Query(default="pm2_5"),
    horizon: int = Query(default=72, ge=24, le=72), language: Literal["en", "hi", "pa"] = Query(default="en"),
) -> dict[str, object]:
    return await _panel("intelligence", city_id, pollutant, horizon, language)


@router.get("/actions")
async def operations_actions(
    city_id: str = Query(default="delhi-ncr"), pollutant: Literal["pm2_5", "pm10"] = Query(default="pm2_5"),
    horizon: int = Query(default=72, ge=24, le=72), language: Literal["en", "hi", "pa"] = Query(default="en"),
) -> dict[str, object]:
    return await _panel("actions", city_id, pollutant, horizon, language)


@router.get("/advisory")
async def operations_advisory(
    city_id: str = Query(default="delhi-ncr"), pollutant: Literal["pm2_5", "pm10"] = Query(default="pm2_5"),
    horizon: int = Query(default=72, ge=24, le=72), language: Literal["en", "hi", "pa"] = Query(default="en"),
) -> dict[str, object]:
    return await _panel("advisory", city_id, pollutant, horizon, language)
