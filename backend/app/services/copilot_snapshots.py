"""Bounded in-memory access to canonical dashboard snapshots for the copilot."""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
from time import monotonic
from typing import Any


@dataclass(frozen=True)
class _Entry:
    stored_at: float
    payload: dict[str, Any]


_MAX_SNAPSHOTS = 128
_TTL_SECONDS = 900
_snapshots: OrderedDict[str, _Entry] = OrderedDict()


def remember_snapshot(payload: dict[str, Any]) -> None:
    context = payload.get("context") or {}
    snapshot_id = context.get("snapshot_id")
    if not isinstance(snapshot_id, str) or not snapshot_id:
        return
    _snapshots[snapshot_id] = _Entry(monotonic(), payload)
    _snapshots.move_to_end(snapshot_id)
    while len(_snapshots) > _MAX_SNAPSHOTS:
        _snapshots.popitem(last=False)


def matching_snapshot(
    snapshot_id: str,
    city_id: str,
    pollutant: str,
    horizon: int,
) -> dict[str, Any] | None:
    entry = _snapshots.get(snapshot_id)
    if entry is None:
        return None
    if monotonic() - entry.stored_at > _TTL_SECONDS:
        _snapshots.pop(snapshot_id, None)
        return None
    context = entry.payload.get("context") or {}
    city = context.get("city") or {}
    if (
        city.get("city_id") != city_id
        or context.get("pollutant") != pollutant
        or context.get("horizon") != horizon
    ):
        return None
    _snapshots.move_to_end(snapshot_id)
    return entry.payload


def clear_snapshot_registry() -> None:
    """Reset process-local state for deterministic tests."""
    _snapshots.clear()
