"""Fixed five-city PM2.5 24-hour operational outlook."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any

from app.services.city_registry import CITIES
from app.services.dynamic_operational import build_dynamic_snapshot


async def _city_summary(city_id: str) -> dict[str, Any]:
    city = CITIES[city_id]
    try:
        snapshot = await build_dynamic_snapshot(city_id, "pm2_5", 24, 400, True)
        forecast = snapshot.get("forecast") or {}
        peak = forecast.get("peak") or {}
        context = snapshot["context"]
        return {
            "city_id": city.city_id,
            "city_name": city.name,
            "state": city.state,
            "value_24h": peak.get("value"),
            "aqi": peak.get("aqi"),
            "category": peak.get("category"),
            "colour": peak.get("colour"),
            "priority": forecast.get("priority", "Unavailable"),
            "mode": "fixed_next_24h_pm2_5_outlook",
            "pollutant": context.get("pollutant"),
            "horizon": context.get("horizon"),
            "issue_timestamp": context.get("issue_timestamp"),
            "valid_timestamp": peak.get("timestamp_utc"),
            "snapshot_id": context.get("snapshot_id"),
        }
    except Exception:
        return {
            "city_id": city.city_id,
            "city_name": city.name,
            "state": city.state,
            "value_24h": None,
            "aqi": None,
            "category": None,
            "colour": None,
            "priority": "Unavailable",
            "mode": "fixed_next_24h_pm2_5_outlook",
            "pollutant": "pm2_5",
            "horizon": 24,
            "issue_timestamp": None,
            "valid_timestamp": None,
            "snapshot_id": None,
        }


async def build_network_overview() -> dict[str, Any]:
    cities = await asyncio.gather(*(_city_summary(city_id) for city_id in CITIES))
    return {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "pollutant": "pm2_5",
        "unit": "µg/m³",
        "cities": cities,
        "methodology": "Fixed next-24-hour PM2.5 peak outlook; value, AQI, category, colour and forecast priority come from one canonical city snapshot.",
    }
