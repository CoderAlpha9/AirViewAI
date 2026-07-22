from __future__ import annotations

import json
from typing import Any

import httpx
import pytest
from httpx import AsyncClient

from app.api.routes import copilot as copilot_routes
from app.core.config import Settings
from app.schemas.copilot import CopilotReply
from app.services.copilot_snapshots import clear_snapshot_registry, remember_snapshot
from app.services.gemini_copilot import (
    SYSTEM_INSTRUCTION,
    CopilotProviderUnavailable,
    ask_gemini,
)


def _snapshot(snapshot_id: str = "snapshot-123") -> dict[str, Any]:
    return {
        "context": {
            "snapshot_id": snapshot_id,
            "issue_timestamp": "2026-07-22T12:00:00+00:00",
            "city": {"city_id": "ludhiana", "name": "Ludhiana", "state": "Punjab"},
            "pollutant": "pm2_5",
            "horizon": 24,
            "coverage_type": "station_corrected",
        },
        "current": {
            "value": 52.3,
            "timestamp_utc": "2026-07-22T12:00:00+00:00",
            "value_kind": "observed",
            "provider": "CPCB/Data.gov.in",
            "category": "Satisfactory",
            "aqi": 87,
            "freshness": {"label": "recent"},
        },
        "stations": [
            {
                "name": "Civil Lines",
                "provider": "CPCB/Data.gov.in",
                "distance_km": 2.1,
                "freshness": {"label": "recent"},
                "latest": {"pm2_5": {"value": 52.3, "timestamp_utc": "2026-07-22T12:00:00+00:00"}},
            }
        ],
        "forecast": {
            "status": "available",
            "points": [
                {
                    "timestamp_utc": "2026-07-23T12:00:00+00:00",
                    "prediction": 61.7,
                    "category": "Moderate",
                }
            ],
            "peak": {
                "value": 61.7,
                "timestamp_utc": "2026-07-23T12:00:00+00:00",
                "category": "Moderate",
            },
            "priority": "Watch",
        },
        "map": {
            "metadata": {"cell_count": 1},
            "features": [
                {
                    "properties": {
                        "cell_id": "cell-1",
                        "center": [75.85, 30.9],
                        "current": 52.3,
                        "forecast": 61.7,
                        "category": "Satisfactory",
                    }
                }
            ],
            "firms": [],
            "osm": {"road_count": 15, "industrial_count": 2, "construction_count": 1},
        },
        "intelligence": {
            "sources": [
                {
                    "source_id": "road",
                    "label": "Road and traffic influence",
                    "score": 55,
                    "evidence_strength": "High",
                    "significant": True,
                }
            ]
        },
        "actions": [{"source_id": "road", "title": "Reduce traffic and road-dust exposure"}],
        "advisory": {"status": "available", "category": "Moderate"},
        "provider_status": {
            "stations": {"status": "available", "provider": "CPCB/Data.gov.in"},
            "firms": {"status": "unavailable", "provider": "NASA FIRMS"},
            "osm": {"status": "available", "provider": "OpenStreetMap/Overpass"},
        },
    }


def _request(**overrides: Any) -> dict[str, Any]:
    payload = {
        "message": "Why is the forecast rising?",
        "city_id": "ludhiana",
        "pollutant": "pm2_5",
        "horizon": 24,
        "snapshot_id": "snapshot-123",
        "session_id": "session-123",
        "history": [],
    }
    payload.update(overrides)
    return payload


@pytest.fixture(autouse=True)
def reset_copilot_state() -> None:
    clear_snapshot_registry()
    copilot_routes._rate_limiter = None


@pytest.mark.anyio
async def test_valid_grounded_request(client: AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    remember_snapshot(_snapshot())

    async def fake_ask(**kwargs: Any) -> CopilotReply:
        assert kwargs["snapshot"]["context"]["snapshot_id"] == "snapshot-123"
        return CopilotReply(
            answer="The forecast peak is 61.7 µg/m³.",
            evidence=["The selected 24-hour forecast peaks at 61.7 µg/m³."],
            data_status="station-corrected",
            limitations=[],
            suggested_questions=["Which areas need attention?"],
        )

    monkeypatch.setattr(copilot_routes, "ask_gemini", fake_ask)
    response = await client.post("/api/copilot/chat", json=_request())
    assert response.status_code == 200
    assert response.json()["data_status"] == "station-corrected"


@pytest.mark.anyio
async def test_missing_gemini_key_is_sanitised(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    remember_snapshot(_snapshot())

    async def missing(**_: Any) -> CopilotReply:
        from app.services.gemini_copilot import CopilotNotConfigured

        raise CopilotNotConfigured

    monkeypatch.setattr(copilot_routes, "ask_gemini", missing)
    response = await client.post("/api/copilot/chat", json=_request())
    assert response.status_code == 503
    assert response.json() == {"detail": "Ask AirView is not configured on this deployment."}


@pytest.mark.anyio
@pytest.mark.parametrize(
    "override",
    [
        {"snapshot_id": "unknown-snapshot"},
        {"city_id": "delhi-ncr"},
        {"pollutant": "pm10"},
        {"horizon": 48},
    ],
)
async def test_invalid_or_stale_snapshot_is_rejected(
    client: AsyncClient, override: dict[str, Any]
) -> None:
    remember_snapshot(_snapshot())
    response = await client.post("/api/copilot/chat", json=_request(**override))
    assert response.status_code == 409
    assert "context changed" in response.json()["detail"]


@pytest.mark.anyio
async def test_oversized_message_is_rejected(client: AsyncClient) -> None:
    response = await client.post("/api/copilot/chat", json=_request(message="x" * 801))
    assert response.status_code == 422


@pytest.mark.anyio
async def test_rate_limit(client: AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    remember_snapshot(_snapshot())
    settings = Settings(copilot_rate_limit_per_minute=1)
    monkeypatch.setattr(copilot_routes, "get_settings", lambda: settings)

    async def fake_ask(**_: Any) -> CopilotReply:
        return CopilotReply(answer="Grounded.", data_status="station-corrected")

    monkeypatch.setattr(copilot_routes, "ask_gemini", fake_ask)
    assert (await client.post("/api/copilot/chat", json=_request())).status_code == 200
    response = await client.post("/api/copilot/chat", json=_request())
    assert response.status_code == 429
    assert "wait briefly" in response.json()["detail"]


class _MockResponse:
    def __init__(self, body: dict[str, Any], status_code: int = 200) -> None:
        self.body = body
        self.status_code = status_code

    def json(self) -> dict[str, Any]:
        return self.body


class _MockClient:
    response: _MockResponse | None = None
    error: Exception | None = None

    def __init__(self, **_: Any) -> None:
        pass

    async def __aenter__(self) -> _MockClient:
        return self

    async def __aexit__(self, *_: Any) -> None:
        return None

    async def post(self, *_: Any, **__: Any) -> _MockResponse:
        if self.error:
            raise self.error
        assert self.response is not None
        return self.response


@pytest.mark.anyio
async def test_gemini_timeout_is_sanitised(monkeypatch: pytest.MonkeyPatch) -> None:
    _MockClient.error = httpx.ReadTimeout("timed out")
    monkeypatch.setattr(httpx, "AsyncClient", _MockClient)
    with pytest.raises(CopilotProviderUnavailable):
        await ask_gemini(
            settings=Settings(GEMINI_API_KEY="test-secret"),
            snapshot=_snapshot(),
            message="Summarise.",
            history=[],
            language=None,
        )
    _MockClient.error = None


@pytest.mark.anyio
async def test_malformed_gemini_response_uses_safe_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _MockClient.response = _MockResponse(
        {"candidates": [{"content": {"parts": [{"text": "not-json"}]}}]}
    )
    monkeypatch.setattr(httpx, "AsyncClient", _MockClient)
    reply = await ask_gemini(
        settings=Settings(GEMINI_API_KEY="test-secret"),
        snapshot=_snapshot(),
        message="Summarise.",
        history=[],
        language=None,
    )
    assert "could not prepare a grounded answer" in reply.answer


@pytest.mark.anyio
async def test_gemini_reply_is_normalised_before_validation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    verbose = {
        "answer": "Forecast values rise because the selected snapshot shows a higher 24-hour peak.",
        "evidence": [
            "Peak concentration is 61.7 ug/m3.",
            "Current value is 52.3 ug/m3.",
            "Road evidence is high.",
            "FIRMS is unavailable.",
            "Station coverage is active.",
            "Extra evidence should be trimmed.",
        ],
        "dataStatus": "model_based",
        "data_notes": "NASA FIRMS is unavailable for this snapshot.",
        "suggestedQuestions": [
            "Which mapped cells are highest?",
            "What action should be first?",
            "Explain this in Hindi.",
            "What is the station status?",
            "Extra question should be trimmed.",
        ],
    }
    _MockClient.response = _MockResponse(
        {"candidates": [{"content": {"parts": [{"text": json.dumps(verbose)}]}}]}
    )
    monkeypatch.setattr(httpx, "AsyncClient", _MockClient)
    reply = await ask_gemini(
        settings=Settings(GEMINI_API_KEY="test-secret"),
        snapshot=_snapshot(),
        message="Summarise.",
        history=[],
        language=None,
    )
    assert reply.data_status == "model-based"
    assert len(reply.evidence) == 5
    assert len(reply.limitations) == 1
    assert len(reply.suggested_questions) == 4


@pytest.mark.anyio
async def test_secret_path_and_unsupported_claims_are_not_returned(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    unsafe = {
        "answer": "Key test-secret from C:\\Users\\Admin; road traffic is 60% of emissions.",
        "evidence": [],
        "data_status": "station-corrected",
        "limitations": [],
        "suggested_questions": [],
    }
    _MockClient.response = _MockResponse(
        {"candidates": [{"content": {"parts": [{"text": json.dumps(unsafe)}]}}]}
    )
    monkeypatch.setattr(httpx, "AsyncClient", _MockClient)
    reply = await ask_gemini(
        settings=Settings(GEMINI_API_KEY="test-secret"),
        snapshot=_snapshot(),
        message="Summarise.",
        history=[],
        language=None,
    )
    serialised = reply.model_dump_json()
    assert "test-secret" not in serialised
    assert "C:\\Users" not in serialised
    assert "% of emissions" not in serialised
    assert "never call them emission shares" in SYSTEM_INSTRUCTION.lower()
    assert "do not diagnose" in SYSTEM_INSTRUCTION.lower()
