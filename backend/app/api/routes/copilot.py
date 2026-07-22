"""Grounded, read-only Ask AirView API."""

from __future__ import annotations

from collections import defaultdict, deque
from time import monotonic

from fastapi import APIRouter, HTTPException, Request

from app.core.config import get_settings
from app.schemas.copilot import CopilotChatRequest, CopilotReply
from app.services.copilot_snapshots import matching_snapshot
from app.services.gemini_copilot import (
    CopilotNotConfigured,
    CopilotProviderUnavailable,
    ask_gemini,
)

router = APIRouter(prefix="/copilot")


class SlidingWindowRateLimiter:
    def __init__(self, limit: int, window_seconds: int = 60) -> None:
        self.limit = limit
        self.window_seconds = window_seconds
        self.events: dict[str, deque[float]] = defaultdict(deque)

    def allow(self, key: str) -> bool:
        now = monotonic()
        events = self.events[key]
        while events and now - events[0] >= self.window_seconds:
            events.popleft()
        if len(events) >= self.limit:
            return False
        events.append(now)
        if len(self.events) > 1000:
            self.events = defaultdict(deque, {key: events})
        return True


_rate_limiter: SlidingWindowRateLimiter | None = None


def _limiter() -> SlidingWindowRateLimiter:
    global _rate_limiter
    settings = get_settings()
    if _rate_limiter is None or _rate_limiter.limit != settings.copilot_rate_limit_per_minute:
        _rate_limiter = SlidingWindowRateLimiter(settings.copilot_rate_limit_per_minute)
    return _rate_limiter


@router.get("/status")
async def status() -> dict[str, str | bool]:
    settings = get_settings()
    configured = bool(settings.gemini_api_key)
    return {
        "enabled": settings.copilot_enabled,
        "provider": "Google Gemini",
        "model": settings.gemini_model,
        "configured": configured,
    }


@router.post("/chat", response_model=CopilotReply)
async def chat(payload: CopilotChatRequest, request: Request) -> CopilotReply:
    settings = get_settings()
    client_host = request.client.host if request.client else "unknown"
    if not _limiter().allow(f"{client_host}:{payload.session_id}"):
        raise HTTPException(429, "Ask AirView is receiving too many requests. Please wait briefly.")
    snapshot = matching_snapshot(
        payload.snapshot_id,
        payload.city_id,
        payload.pollutant,
        payload.horizon,
    )
    if snapshot is None:
        raise HTTPException(
            409, "The dashboard context changed. Please retry with the current snapshot."
        )
    try:
        return await ask_gemini(
            settings=settings,
            snapshot=snapshot,
            message=payload.message,
            history=payload.history,
            language=payload.language,
        )
    except CopilotNotConfigured as exc:
        raise HTTPException(503, "Ask AirView is not configured on this deployment.") from exc
    except CopilotProviderUnavailable as exc:
        raise HTTPException(
            503, "Ask AirView is temporarily unavailable. Please try again."
        ) from exc
