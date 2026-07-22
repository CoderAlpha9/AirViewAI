"""Production operational metadata and fixed five-city outlook."""

from __future__ import annotations

from fastapi import APIRouter

from app.core.config import get_settings
from app.services.city_registry import CITIES, POLLUTANTS, city_list
from app.services.network import build_network_overview

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
            "cpcb_data_gov": "configured" if settings.data_gov_in_api_key else "not_configured",
            "openaq": "configured" if settings.openaq_api_key else "not_configured",
            "cams_open_meteo": "available_without_key",
            "open_meteo_weather": "available_without_key",
            "nasa_firms": "configured" if settings.nasa_firms_map_key else "not_configured",
            "osm_overpass": "available_without_key",
            "osm_nominatim": "available_without_key",
        },
        "fallback": "per-panel unavailable state; archived values are never substituted",
    }


@router.get("/cities")
def operations_cities() -> dict[str, object]:
    return {"data": city_list(), "count": len(CITIES)}


@router.get("/network")
async def operations_network() -> dict[str, object]:
    return await build_network_overview()
