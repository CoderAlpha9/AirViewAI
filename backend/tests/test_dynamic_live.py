from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import pytest

from app.api.routes import dynamic as dynamic_routes
from app.services import city_support, dynamic_operational
from app.services.city_support import (
    ResolvedCity,
    generate_city_grid,
    rank_and_select_stations,
    resolve_indian_city,
)
from app.services.decision import AQI_COLOURS, aqi_result, intervention_priority

pytestmark = pytest.mark.anyio


async def test_missing_timestamp_is_not_serialized_as_nat() -> None:
    assert dynamic_operational._time(None) is None
    assert dynamic_operational._time("NaT") is None


async def test_live_api_accepts_numeric_horizon_query(
    client, monkeypatch: pytest.MonkeyPatch
) -> None:
    received: list[tuple[Any, ...]] = []

    async def snapshot(*args: Any, **__: Any) -> dict[str, Any]:
        received.append(args)
        return {"context": {"snapshot_id": "test"}, "current": {"value": 42}, "provider_status": {}}

    monkeypatch.setattr(dynamic_routes, "build_dynamic_snapshot", snapshot)
    response = await client.get(
        "/api/live/current", params={"city": "agra", "pollutant": "pm2_5", "horizon": 24}
    )
    assert response.status_code == 200
    assert response.json()["data"]["value"] == 42
    assert received == [("agra", "pm2_5", 24, 400, True)]


async def test_station_panel_reports_available_and_selected_counts(
    client, monkeypatch: pytest.MonkeyPatch
) -> None:
    received: list[tuple[Any, ...]] = []

    async def snapshot(*args: Any, **__: Any) -> dict[str, Any]:
        received.append(args)
        return {
            "context": {"snapshot_id": "test"},
            "stations": [{"station_id": "selected-1"}],
            "station_summary": {"available_count": 3, "selected_count": 1},
            "provider_status": {},
        }

    monkeypatch.setattr(dynamic_routes, "build_dynamic_snapshot", snapshot)
    response = await client.get("/api/live/stations", params={"city": "agra", "horizon": 24})
    assert response.status_code == 200
    assert response.json()["data"] == {
        "available_count": 3,
        "selected_count": 1,
        "stations": [{"station_id": "selected-1"}],
    }
    assert received == [("agra", "pm2_5", 24, 400, True)]


def city() -> ResolvedCity:
    return ResolvedCity(
        city_id="india-test-city-12345678",
        name="Test City",
        state="Test State",
        latitude=20.0,
        longitude=78.0,
        bounds=(19.96, 77.96, 20.04, 78.04),
        boundary_geojson=None,
        bounds_source="configured_radius",
    )


def test_city_grid_is_geojson_bounded_and_not_fixed_5x5() -> None:
    grid = generate_city_grid(city(), max_cells=80)
    assert grid["type"] == "FeatureCollection"
    assert 25 < len(grid["features"]) <= 80
    assert all(item["geometry"]["type"] in {"Polygon", "MultiPolygon"} for item in grid["features"])
    assert grid["metadata"]["resolution_m"] == 1000


def test_multi_station_selection_prefers_fresh_spatially_separated_sites() -> None:
    now = datetime.now(timezone.utc).isoformat()
    stations = [
        {
            "station_id": f"s{index}",
            "name": f"Station {index}",
            "provider": "CPCB/Data.gov.in",
            "latitude": 20 + index * 0.03,
            "longitude": 78 + index * 0.03,
            "distance_km": index * 4,
            "pollutants": ["pm2_5", "pm10"],
            "latest": {"pm2_5": {"value": 40 + index, "timestamp_utc": now}},
        }
        for index in range(6)
    ]
    selected = rank_and_select_stations(stations, "pm2_5", limit=5, separation_km=2)
    assert len(selected) == 5
    assert all(item["freshness"]["label"] == "recent" for item in selected)


def test_station_selection_rejects_stale_provider_values() -> None:
    stale = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
    stations = [
        {
            "station_id": "stale",
            "name": "Stale station",
            "provider": "OpenAQ",
            "latitude": 20.0,
            "longitude": 78.0,
            "distance_km": 1,
            "pollutants": ["pm2_5"],
            "latest": {"pm2_5": {"value": 80, "timestamp_utc": stale}},
        }
    ]
    assert rank_and_select_stations(stations, "pm2_5") == []


def test_multiple_station_residual_is_spatially_variable() -> None:
    now = datetime.now(timezone.utc).isoformat()
    stations = [
        {
            "latitude": 20.0,
            "longitude": 78.0,
            "freshness": {"age_hours": 1},
            "latest": {"pm2_5": {"value": 80, "timestamp_utc": now}},
        },
        {
            "latitude": 20.2,
            "longitude": 78.2,
            "freshness": {"age_hours": 1},
            "latest": {"pm2_5": {"value": 30, "timestamp_utc": now}},
        },
    ]
    near_first = dynamic_operational._weighted_residual(stations, "pm2_5", 50, 20.01, 78.01)[0]
    near_second = dynamic_operational._weighted_residual(stations, "pm2_5", 50, 20.19, 78.19)[0]
    assert near_first is not None and near_second is not None
    assert near_first > near_second


def test_canonical_aqi_and_priority_are_consistent() -> None:
    result = aqi_result(250, "pm2_5")
    assert result["category"] is not None
    assert intervention_priority(result["aqi"], 0.8) != "Unavailable"


@pytest.mark.parametrize("city_id", ["delhi-ncr", "agra", "amritsar", "lucknow", "ludhiana"])
async def test_all_five_pilot_cities_resolve_without_network(city_id: str) -> None:
    resolved = await dynamic_operational.resolve_city_reference(city_id)
    assert resolved.city_id == city_id
    assert resolved.bounds[0] < resolved.latitude < resolved.bounds[2]


async def test_unseen_city_search_returns_stable_identifier(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def search(*_: Any, **__: Any) -> list[dict[str, Any]]:
        return [
            {
                "osm_type": "relation",
                "osm_id": 1234,
                "lat": "12.9716",
                "lon": "77.5946",
                "boundingbox": ["12.8", "13.2", "77.4", "77.8"],
                "address": {"city": "Bengaluru", "state": "Karnataka", "country_code": "in"},
            }
        ]

    monkeypatch.setattr(city_support, "nominatim_city_search", search)
    first = await resolve_indian_city("Bengaluru")
    second = await resolve_indian_city("Bengaluru")
    assert first[0].city_id == second[0].city_id
    assert first[0].city_id.startswith("india-bengaluru-")


def _air(now: datetime) -> dict[str, Any]:
    times = [(now + timedelta(hours=index)).isoformat() for index in range(-24, 80)]
    return {
        "current": {"time": now.isoformat(), "pm2_5": 60.0, "pm10": 100.0},
        "hourly": {
            "time": times,
            "pm2_5": [60 + index * 0.1 for index in range(len(times))],
            "pm10": [100 + index * 0.2 for index in range(len(times))],
        },
    }


def _weather(now: datetime) -> dict[str, Any]:
    return {
        "current": {
            "time": now.isoformat(),
            "temperature_2m": 28,
            "relative_humidity_2m": 50,
            "surface_pressure": 995,
            "precipitation": 0,
            "wind_speed_10m": 2,
            "wind_direction_10m": 180,
            "boundary_layer_height": 600,
        }
    }


@pytest.mark.parametrize("pollutant", ["pm2_5", "pm10"])
@pytest.mark.parametrize("horizon", [24, 48, 72])
@pytest.mark.parametrize("city_id", ["delhi-ncr", "agra", "amritsar", "lucknow", "ludhiana"])
async def test_dynamic_snapshot_supports_five_cities_pollutants_and_horizons(
    monkeypatch: pytest.MonkeyPatch, pollutant: str, horizon: int, city_id: str
) -> None:
    now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)

    async def resolved(*_: Any, **__: Any) -> ResolvedCity:
        value = city()
        return ResolvedCity(**{**value.__dict__, "city_id": city_id, "name": city_id})

    async def air(*_: Any, **__: Any) -> dict[str, Any]:
        return _air(now)

    async def weather(*_: Any, **__: Any) -> dict[str, Any]:
        return _weather(now)

    async def stations(*_: Any, **__: Any) -> dict[str, Any]:
        return {
            "stations": [],
            "provider_status": {"cpcb_data_gov": "unavailable", "openaq": "unavailable"},
        }

    async def firms(*_: Any, **__: Any) -> list:
        return []

    async def osm(*_: Any, **__: Any) -> dict:
        return {"road_count": 0, "industrial_count": 0, "construction_count": 0}

    monkeypatch.setattr(dynamic_operational, "resolve_city_reference", resolved)
    monkeypatch.setattr(dynamic_operational, "open_meteo_air_quality", air)
    monkeypatch.setattr(dynamic_operational, "open_meteo_weather", weather)
    monkeypatch.setattr(dynamic_operational, "discover_stations", stations)
    monkeypatch.setattr(dynamic_operational, "firms_near_real_time", firms)
    monkeypatch.setattr(dynamic_operational, "osm_city_context", osm)
    payload = await dynamic_operational.build_dynamic_snapshot(
        f"unique-{city_id}-{pollutant}-{horizon}-{now.timestamp()}", pollutant, horizon, 30
    )
    assert payload["context"]["coverage_type"] == "model_based"
    assert payload["context"]["pollutant"] == pollutant
    assert payload["context"]["horizon"] == horizon
    assert payload["context"]["city"]["city_id"] == city_id
    assert len(payload["forecast"]["points"]) == horizon
    assert payload["current"]["provider"] == "CAMS via Open-Meteo"
    assert payload["advisory"]["category"] == payload["current"]["category"]
    assert payload["current"]["colour"] == AQI_COLOURS[payload["current"]["category"]]
    assert (
        payload["forecast"]["peak"]["colour"]
        == AQI_COLOURS[payload["forecast"]["peak"]["category"]]
    )
    assert all(
        point["colour"] == AQI_COLOURS[point["category"]]
        for point in payload["forecast"]["points"]
        if point["category"] is not None
    )
    assert all(
        action["priority"] == payload["intelligence"]["priority"] for action in payload["actions"]
    )
    assert payload["forecast"]["priority"] == intervention_priority(
        payload["forecast"]["peak"]["aqi"], payload["intelligence"]["confidence"]
    )
    assert all(
        item["properties"]["coverage_type"] == "model_based" for item in payload["map"]["features"]
    )
    assert payload["map"]["metadata"]["layer_kind"] == "current"
    assert payload["map"]["metadata"]["category_legend"] == [
        {"category": label, "colour": colour} for label, colour in AQI_COLOURS.items()
    ]
    assert all(
        item["properties"]["colour"] == AQI_COLOURS[item["properties"]["category"]]
        for item in payload["map"]["features"]
        if item["properties"]["category"] is not None
    )
    assert len({item["properties"]["current"] for item in payload["map"]["features"]}) > 1
    assert len({item["properties"]["forecast"] for item in payload["map"]["features"]}) > 1
    if city_id == "delhi-ncr" and pollutant == "pm2_5" and horizon == 24:
        core_only = await dynamic_operational.build_dynamic_snapshot(
            f"unique-{city_id}-{pollutant}-{horizon}-{now.timestamp()}",
            pollutant,
            horizon,
            31,
            False,
        )
        assert core_only["context"]["snapshot_id"] == payload["context"]["snapshot_id"]
        assert core_only["current"]["category"] == payload["current"]["category"]
        assert core_only["intelligence"]["priority"] == payload["intelligence"]["priority"]
        assert core_only["intelligence"]["confidence"] == payload["intelligence"]["confidence"]
        assert core_only["forecast"]["priority"] == payload["forecast"]["priority"]


async def test_partial_failure_never_uses_historical_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def resolved(*_: Any, **__: Any) -> ResolvedCity:
        return city()

    async def unavailable(*_: Any, **__: Any) -> Any:
        raise RuntimeError("unavailable")

    async def stations(*_: Any, **__: Any) -> dict[str, Any]:
        return {"stations": [], "provider_status": {}}

    monkeypatch.setattr(dynamic_operational, "resolve_city_reference", resolved)
    monkeypatch.setattr(dynamic_operational, "open_meteo_air_quality", unavailable)
    monkeypatch.setattr(dynamic_operational, "open_meteo_weather", unavailable)
    monkeypatch.setattr(dynamic_operational, "discover_stations", stations)
    monkeypatch.setattr(dynamic_operational, "firms_near_real_time", unavailable)
    monkeypatch.setattr(dynamic_operational, "osm_city_context", unavailable)
    payload = await dynamic_operational.build_dynamic_snapshot(
        "partial-failure-unique", "pm2_5", 24, 25
    )
    assert payload["current"] is None
    assert payload["forecast"]["status"] == "unavailable"
    assert payload["provider_status"]["cams"]["status"] == "unavailable"
    assert not any(item["properties"]["forecast"] for item in payload["map"]["features"])
    second = await dynamic_operational.build_dynamic_snapshot(
        "partial-failure-unique", "pm2_5", 24, 30
    )
    assert second["context"]["snapshot_id"] == payload["context"]["snapshot_id"]
