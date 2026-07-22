import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from airview_ml.data.contracts import SourceResult, serialise

REPORT_NAMES = {
    "inventory": "data_source_inventory.json",
    "run": "data_pipeline_run.json",
    "cities": "india_city_registry.json",
    "stations": "india_station_registry.json",
    "coverage": "data_coverage_report.json",
    "quality": "data_quality_report.json",
    "readiness": "city_readiness_report.json",
    "aliases": "city_alias_review.json",
    "failures": "source_failures.json",
    "manual": "manual_actions_required.json",
    "openaq_archive_manifest": "openaq_archive_manifest.json",
    "openaq_location_mapping_report": "openaq_location_mapping_report.json",
    "unresolved_openaq_locations": "unresolved_openaq_locations.json",
    "ambiguous_station_matches": "ambiguous_station_matches.json",
    "openaq_india_archive_availability": "openaq_india_archive_availability.json",
    "openaq_download_plan": "openaq_download_plan.json",
    "model_data_readiness": "model_data_readiness.json",
    "cpcb_recovery_report": "cpcb_recovery_report.json",
    "cpcb_openaq_station_crosswalk": "cpcb_openaq_station_crosswalk.json",
    "sentinel5p_validation_report": "sentinel5p_validation_report.json",
    "sentinel5p_coverage_report": "sentinel5p_coverage_report.json",
    "firms_validation_report": "firms_validation_report.json",
    "firms_city_coverage_report": "firms_city_coverage_report.json",
    "ghsl_ingestion_report": "ghsl_ingestion_report.json",
    "osm_city_coverage_report": "osm_city_coverage_report.json",
}


def write_report(reports_dir: Path, name: str, payload: Any) -> Path:
    reports_dir.mkdir(parents=True, exist_ok=True)
    target = reports_dir / REPORT_NAMES.get(name, f"{name}.json")
    target.write_text(
        json.dumps(serialise(payload), ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return target


def load_report(reports_dir: Path, name: str) -> dict[str, Any] | list[Any] | None:
    target = reports_dir / REPORT_NAMES.get(name, f"{name}.json")
    if not target.is_file():
        return None
    return json.loads(target.read_text(encoding="utf-8"))


def inventory_entry(result: SourceResult) -> dict[str, Any]:
    return result.to_dict()


def empty_run(profile: str) -> dict[str, Any]:
    return {
        "status": "not_ready",
        "profile": profile,
        "started_at_utc": datetime.now(timezone.utc).isoformat(),
        "message": "No completed data pipeline run is available yet.",
    }
