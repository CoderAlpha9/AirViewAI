from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import pytest
from httpx import AsyncClient

from app.services import operational

pytestmark = pytest.mark.anyio


def _air_payload(now: datetime) -> dict[str, Any]:
    times = [(now + timedelta(hours=index)).isoformat() for index in range(-168, 121)]
    length = len(times)
    return {
        "current": {"time": now.isoformat(), "pm2_5": 82.0, "pm10": 136.0},
        "hourly": {
            "time": times,
            "pm2_5": [72 + 0.09 * index for index in range(length)],
            "pm10": [121 + 0.13 * index for index in range(length)],
            "nitrogen_dioxide": [19.0] * length,
            "carbon_monoxide": [310.0] * length,
            "ozone": [43.0] * length,
            "dust": [11.0] * length,
        },
    }


def _weather_payload(now: datetime) -> dict[str, Any]:
    times = [(now + timedelta(hours=index)).isoformat() for index in range(-168, 121)]
    values = {
        "temperature_2m": 27.0,
        "relative_humidity_2m": 52.0,
        "surface_pressure": 998.0,
        "precipitation": 0.0,
        "cloud_cover": 25.0,
        "visibility": 10000.0,
        "wind_speed_10m": 2.4,
        "wind_direction_10m": 275.0,
        "wind_gusts_10m": 4.2,
        "boundary_layer_height": 720.0,
        "weather_code": 1,
    }
    hourly = {"time": times, **{key: [value] * len(times) for key, value in values.items()}}
    return {"current": {"time": now.isoformat(), **values}, "hourly": hourly}


def _openaq_payload(now: datetime) -> dict[str, Any]:
    history = [
        {
            "value": 67 + index * 0.08,
            "period": {"datetimeFrom": {"utc": (now - timedelta(hours=167 - index)).isoformat()}},
        }
        for index in range(168)
    ]
    return {
        "latest": {
            "pm2_5": {"value": 82.0, "timestamp_utc": now.isoformat()},
            "pm10": {"value": 136.0, "timestamp_utc": now.isoformat()},
        },
        "history": {"pm2_5": history, "pm10": history},
        "sensor_map": {},
    }


async def test_live_dashboard_returns_future_forecast(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)

    async def air(*_: Any, **__: Any) -> dict[str, Any]:
        return _air_payload(now)

    async def weather(*_: Any, **__: Any) -> dict[str, Any]:
        return _weather_payload(now)

    async def openaq(*_: Any, **__: Any) -> dict[str, Any]:
        return _openaq_payload(now)

    async def firms(*_: Any, **__: Any) -> list[dict[str, Any]]:
        return [
            {
                "latitude": 28.8,
                "longitude": 77.4,
                "timestamp_utc": now.isoformat(),
                "fire_radiative_power": 12.0,
                "distance_km": 24.0,
            }
        ]

    monkeypatch.setattr(operational, "open_meteo_air_quality", air)
    monkeypatch.setattr(operational, "open_meteo_weather", weather)
    monkeypatch.setattr(operational, "openaq_recent", openaq)
    monkeypatch.setattr(operational, "firms_near_real_time", firms)

    response = await client.get(
        "/api/operations/dashboard",
        params={
            "city_id": "delhi-ncr",
            "pollutant": "pm2_5",
            "horizon": 72,
            "language": "en",
            "mode": "live",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["mode"] == "operational_forecast"
    assert payload["live"] is True
    assert len(payload["forecast"]["points"]) == 72
    assert payload["forecast"]["points"][-1]["timestamp_utc"] > now.isoformat()
    assert len(payload["map"]["grid"]) == 25
    assert payload["current"]["value_kind"] == "observed"


async def test_live_failure_falls_back_to_labelled_replay(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def unavailable(*_: Any, **__: Any) -> dict[str, Any]:
        raise RuntimeError("provider unavailable")

    monkeypatch.setattr(operational, "open_meteo_air_quality", unavailable)
    monkeypatch.setattr(operational, "open_meteo_weather", unavailable)
    monkeypatch.setattr(operational, "openaq_recent", unavailable)
    monkeypatch.setattr(operational, "firms_near_real_time", unavailable)

    response = await client.get(
        "/api/operations/dashboard",
        params={"city_id": "agra", "pollutant": "pm10", "horizon": 24, "mode": "live"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["mode"] == "historical_replay"
    assert payload["live"] is False
    assert "not a current operational forecast" in payload["disclaimer"]


async def test_live_ludhiana_uses_pau_station(client: AsyncClient) -> None:
    response = await client.get("/api/operations/cities")
    assert response.status_code == 200
    ludhiana = next(item for item in response.json()["data"] if item["city_id"] == "ludhiana")
    assert ludhiana["openaq_location_id"] == 5569
    assert "Ludhiana" in ludhiana["station_name"]


async def test_invalid_horizon_is_explicit(client: AsyncClient) -> None:
    response = await client.get(
        "/api/operations/dashboard",
        params={"city_id": "delhi-ncr", "pollutant": "pm2_5", "horizon": 36},
    )
    assert response.status_code == 422


async def test_ludhiana_replay_discloses_regional_station(client: AsyncClient) -> None:
    response = await client.get(
        "/api/operations/dashboard",
        params={"city_id": "ludhiana", "pollutant": "pm2_5", "horizon": 24, "mode": "demo"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["city"]["station_id"] == "openaq-5542"
    assert "Jalandhar" in payload["city"]["station_name"]
    assert "Live mode targets PAU" in payload["coverage_note"]
    assert payload["map"]["station"]["latitude"] == pytest.approx(31.321907)


async def test_live_ludhiana_does_not_reuse_jalandhar_osm() -> None:
    city = operational.CITIES["ludhiana"]
    assert operational._osm_row(city) is None


async def test_network_demo_returns_all_pilot_cities(client: AsyncClient) -> None:
    response = await client.get("/api/operations/network", params={"mode": "demo"})
    assert response.status_code == 200
    payload = response.json()
    assert {item["city_id"] for item in payload["cities"]} == set(operational.CITIES)
    assert all(item["mode"] == "historical_replay" for item in payload["cities"])
