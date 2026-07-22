from __future__ import annotations

from typing import Any

import pytest
from httpx import AsyncClient

from app.api.routes import operations
from app.services import network as network_service

pytestmark = pytest.mark.anyio


async def test_operational_status_describes_live_provider_behavior(client: AsyncClient) -> None:
    response = await client.get("/api/operations/status")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ready"
    assert payload["supported_cities"] == 5
    assert payload["providers"]["cams_open_meteo"] == "available_without_key"
    assert "archived values are never substituted" in payload["fallback"]


async def test_city_registry_uses_correct_ludhiana_station(client: AsyncClient) -> None:
    response = await client.get("/api/operations/cities")
    assert response.status_code == 200
    ludhiana = next(item for item in response.json()["data"] if item["city_id"] == "ludhiana")
    assert ludhiana["openaq_location_id"] == 5569
    assert "Ludhiana" in ludhiana["station_name"]


async def test_network_endpoint_returns_fixed_five_city_outlook(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def overview() -> dict[str, Any]:
        return {"pollutant": "pm2_5", "cities": [{"city_id": str(index)} for index in range(5)]}

    monkeypatch.setattr(operations, "build_network_overview", overview)
    response = await client.get("/api/operations/network")
    assert response.status_code == 200
    assert response.json()["pollutant"] == "pm2_5"
    assert len(response.json()["cities"]) == 5


async def test_network_row_uses_one_24_hour_forecast_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    received: list[tuple[Any, ...]] = []

    async def snapshot(*args: Any, **__: Any) -> dict[str, Any]:
        received.append(args)
        return {
            "context": {
                "pollutant": "pm2_5",
                "horizon": 24,
                "issue_timestamp": "2026-07-22T04:00:00+00:00",
                "snapshot_id": "canonical-24h",
            },
            "forecast": {
                "peak": {
                    "value": 88.5,
                    "aqi": 166,
                    "category": "Moderate",
                    "colour": "#f9a825",
                    "timestamp_utc": "2026-07-23T04:00:00+00:00",
                },
                "priority": "Watch",
            },
        }

    monkeypatch.setattr(network_service, "build_dynamic_snapshot", snapshot)
    row = await network_service._city_summary("delhi-ncr")
    assert row["mode"] == "fixed_next_24h_pm2_5_outlook"
    assert row["value_24h"] == 88.5
    assert row["aqi"] == 166
    assert row["category"] == "Moderate"
    assert row["colour"] == "#f9a825"
    assert row["priority"] == "Watch"
    assert row["snapshot_id"] == "canonical-24h"
    assert received == [("delhi-ncr", "pm2_5", 24, 400, True)]


@pytest.mark.parametrize(
    "path", ["/api/dashboard/status", "/api/forecast/replay", "/api/orchestration/status"]
)
async def test_archived_demo_routes_are_not_exposed(client: AsyncClient, path: str) -> None:
    assert (await client.get(path)).status_code == 404
