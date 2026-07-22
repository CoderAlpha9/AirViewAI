"""Configured quick-select cities for the production dashboard."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


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
    "ludhiana": CityConfig(
        "ludhiana", "Ludhiana", "Punjab", "openaq-5569", "PAU, Ludhiana", 5569, 30.9028, 75.8086
    ),
}

POLLUTANTS = {"pm2_5": "PM2.5", "pm10": "PM10"}


def city_list() -> list[dict[str, Any]]:
    return [
        {
            **asdict(city),
            "pollutants": list(POLLUTANTS),
            "forecast_horizons": [24, 48, 72],
            "live_capable": True,
        }
        for city in CITIES.values()
    ]
