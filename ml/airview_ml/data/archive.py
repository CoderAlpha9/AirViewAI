"""OpenAQ archive audit, ranking, and deterministic download planning."""

from __future__ import annotations

from collections import defaultdict
from datetime import date
from typing import Any

CONFIDENCE_WEIGHT = {"high": 1.0, "medium": 0.7, "low": 0.35, "review": 0.0, "none": 0.0}


def rank_locations(
    locations: list[dict[str, Any]],
    mappings: list[dict[str, Any]],
    availability: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Score candidates without treating OpenAQ metadata as downloaded measurements."""
    by_id = {int(item["id"]): item for item in locations}
    availability_by_id = {int(item["location_id"]): item for item in availability}
    ranked: list[dict[str, Any]] = []
    for mapping in mappings:
        location = by_id.get(int(mapping["location_id"]), {})
        archive = availability_by_id.get(int(mapping["location_id"]), {})
        pollutants = _location_pollutants(location)
        months = len(archive.get("available_months", []))
        files = int(archive.get("estimated_file_count") or 0)
        coordinates = location.get("coordinates") or {}
        valid_coordinates = _valid_india_coordinates(
            coordinates.get("latitude"), coordinates.get("longitude")
        )
        score = (
            45 * ("pm2_5" in pollutants)
            + 22 * ("pm10" in pollutants)
            + 3 * min(len(pollutants), 7)
            + 1.5 * min(months, 36)
            + 8 * valid_coordinates
            + 10 * CONFIDENCE_WEIGHT.get(str(mapping.get("mapping_confidence")), 0)
            + min(len(location.get("sensors", [])), 12)
            + 5 * bool(archive.get("most_recent_file"))
            + min(files / 100, 8)
        )
        ranked.append(
            {
                **mapping,
                "available_pollutants": sorted(pollutants),
                "available_month_count": months,
                "estimated_file_count": files,
                "estimated_size_bytes": int(archive.get("estimated_size_bytes") or 0),
                "most_recent_file": archive.get("most_recent_file"),
                "valid_coordinates": valid_coordinates,
                "selection_score": round(score, 2),
                "selection_reasons": _selection_reasons(
                    pollutants, months, valid_coordinates, mapping
                ),
            }
        )
    return sorted(ranked, key=lambda item: (-item["selection_score"], item["station_id"]))


def build_download_plan(
    ranked: list[dict[str, Any]],
    *,
    start: date,
    end: date,
    max_cities: int | None = None,
    stations_per_city: int = 2,
    max_files: int | None = None,
    required_pollutant: str = "pm2_5",
    minimum_months: int = 12,
    minimum_confidence: str = "medium",
) -> dict[str, Any]:
    minimum_weight = CONFIDENCE_WEIGHT[minimum_confidence]
    candidates = [
        item
        for item in ranked
        if item["city_id"]
        and CONFIDENCE_WEIGHT.get(str(item["mapping_confidence"]), 0) >= minimum_weight
        and required_pollutant in item["available_pollutants"]
        and item["available_month_count"] >= minimum_months
    ]
    selected: list[dict[str, Any]] = []
    by_city: dict[str, int] = defaultdict(int)
    planned_files = 0
    for item in candidates:
        if max_cities is not None and item["city_id"] not in by_city and len(by_city) >= max_cities:
            continue
        if by_city[item["city_id"]] >= stations_per_city:
            continue
        count = int(item["estimated_file_count"])
        if max_files is not None and selected and planned_files + count > max_files:
            continue
        selected.append(
            {
                **item,
                "archive_start_requested": start.isoformat(),
                "archive_end_requested": end.isoformat(),
            }
        )
        by_city[item["city_id"]] += 1
        planned_files += count
    city_manifest = [
        {
            "city_id": city_id,
            "selected_stations": [
                item["station_id"] for item in selected if item["city_id"] == city_id
            ],
            "expected_files": sum(
                int(item["estimated_file_count"]) for item in selected if item["city_id"] == city_id
            ),
            "available_pollutants": sorted(
                {
                    pollutant
                    for item in selected
                    if item["city_id"] == city_id
                    for pollutant in item["available_pollutants"]
                }
            ),
            "intended_modelling_tier": "candidate_pending_downloaded_completeness_validation",
            "inclusion_reason": "ranked PM2.5-capable station with archive coverage and valid mapping",
        }
        for city_id in by_city
    ]
    return {
        "requested_range": {"start": start.isoformat(), "end": end.isoformat()},
        "required_pollutant": required_pollutant,
        "minimum_archive_months": minimum_months,
        "minimum_mapping_confidence": minimum_confidence,
        "selection_count": len(selected),
        "selected_city_count": len(by_city),
        "expected_file_count": planned_files,
        "expected_size_bytes": sum(int(item["estimated_size_bytes"]) for item in selected),
        "stations": selected,
        "cities": city_manifest,
        "excluded_candidate_count": len(ranked) - len(selected),
        "note": "File counts and sizes come from the unsigned archive index; provider sensor metadata is used only for pre-download pollutant capability.",
    }


def _location_pollutants(location: dict[str, Any]) -> set[str]:
    aliases = {"pm25": "pm2_5", "pm2.5": "pm2_5"}
    values = set()
    for sensor in location.get("sensors", []):
        name = str((sensor.get("parameter") or {}).get("name") or "").lower()
        values.add(aliases.get(name, name.replace(" ", "_")))
    return values


def _valid_india_coordinates(latitude: Any, longitude: Any) -> bool:
    try:
        return 6 <= float(latitude) <= 38 and 68 <= float(longitude) <= 98
    except (TypeError, ValueError):
        return False


def _selection_reasons(
    pollutants: set[str], months: int, valid_coordinates: bool, mapping: dict[str, Any]
) -> list[str]:
    reasons = [
        f"{months} archive months indexed",
        f"mapping confidence {mapping.get('mapping_confidence')}",
    ]
    if "pm2_5" in pollutants:
        reasons.append("PM2.5 sensor capability")
    if "pm10" in pollutants:
        reasons.append("PM10 sensor capability")
    if valid_coordinates:
        reasons.append("valid India coordinates")
    return reasons
