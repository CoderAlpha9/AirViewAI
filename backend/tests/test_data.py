from pathlib import Path

import pytest
from httpx import AsyncClient

from app.services import data_status

pytestmark = pytest.mark.anyio


async def test_data_endpoint_is_honest_before_pipeline_run(client: AsyncClient, monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(data_status, "reports_directory", lambda: tmp_path)

    response = await client.get("/api/data/sources")

    assert response.status_code == 200
    assert response.json()["status"] == "not_ready"


async def test_city_not_found_is_explicit(client: AsyncClient, monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(data_status, "reports_directory", lambda: tmp_path)
    (tmp_path / "india_city_registry.json").write_text('{"cities": []}', encoding="utf-8")

    response = await client.get("/api/data/cities/no-such-city")

    assert response.status_code == 200
    assert response.json()["status"] == "not_found"


async def test_archive_and_model_reports_are_explicit_before_generation(client: AsyncClient, monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(data_status, "reports_directory", lambda: tmp_path)

    archive = await client.get("/api/data/archive/plan")
    model = await client.get("/api/data/model-readiness")

    assert archive.json()["status"] == "not_ready"
    assert model.json()["status"] == "not_ready"
