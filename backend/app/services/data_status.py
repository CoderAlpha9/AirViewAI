import json
from pathlib import Path
from typing import Any

REPORT_NAMES = {
    "sources": "data_source_inventory.json",
    "coverage": "data_coverage_report.json",
    "quality": "data_quality_report.json",
    "cities": "india_city_registry.json",
    "stations": "india_station_registry.json",
    "readiness": "city_readiness_report.json",
    "pipeline": "data_pipeline_run.json",
}


def reports_directory() -> Path:
    return Path(__file__).resolve().parents[3] / "outputs" / "reports"


def report_or_not_ready(report: str) -> dict[str, Any]:
    path = reports_directory() / REPORT_NAMES[report]
    if not path.is_file():
        return {
            "status": "not_ready",
            "message": "No completed data pipeline report is available. Run the AirView data pipeline first.",
            "report": report,
        }
    payload = json.loads(path.read_text(encoding="utf-8"))
    return {"status": "ready", "data": payload}


def city_or_not_ready(city_id: str) -> dict[str, Any]:
    report = report_or_not_ready("cities")
    if report["status"] != "ready":
        return report
    payload = report["data"]
    cities = payload.get("cities", []) if isinstance(payload, dict) else []
    for city in cities:
        if city.get("slug") == city_id or city.get("id") == city_id:
            return {"status": "ready", "data": city}
    return {"status": "not_found", "message": "City is not present in the current report.", "city_id": city_id}


def latest_or_not_ready() -> dict[str, Any]:
    path = reports_directory().parents[1] / "data" / "processed" / "india" / "latest_snapshot.json"
    if not path.is_file():
        return {
            "status": "not_ready",
            "message": "No generated latest snapshot is available. Run the data pipeline first.",
        }
    return {"status": "ready", "data": json.loads(path.read_text(encoding="utf-8"))}
