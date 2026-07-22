import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.anyio


async def test_health(client: AsyncClient) -> None:
    response = await client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "AirView AI API",
        "version": "0.1.0",
    }


async def test_project_info(client: AsyncClient) -> None:
    response = await client.get("/api/project-info")
    payload = response.json()

    assert response.status_code == 200
    assert payload["name"] == "AirView AI"
    assert "Problem Statement 5" in payload["problem_statement"]
    assert payload["implementation_stage"].startswith("Operational")
    assert "AQI forecasting" in payload["planned_modules"]
