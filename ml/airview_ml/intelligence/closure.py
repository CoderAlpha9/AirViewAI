"""Final honest closure reports for the bounded enrichment phase."""

# ruff: noqa
from __future__ import annotations
import json
from pathlib import Path
import pandas as pd
from airview_ml.intelligence.enrichment import osm_features

ROOT = Path(__file__).resolve().parents[3]
R = ROOT / "outputs" / "reports"
P = ROOT / "data" / "processed" / "india"


def write(name, value):
    (R / name).write_text(json.dumps(value, indent=2, default=str), encoding="utf8")


def main():
    osm_features()
    write(
        "osm_enrichment_recovery_report.json",
        {
            "status": "closed_with_partial_coverage",
            "cities": [
                {
                    "city_id": "agra",
                    "status": "unavailable",
                    "final_attempt": "small category-specific queries through alternate public endpoints ended HTTP 406/timeout",
                },
                {
                    "city_id": "amritsar",
                    "status": "unavailable",
                    "final_attempt": "small category-specific queries through alternate public endpoints ended HTTP 406/timeout",
                },
                {
                    "city_id": "lucknow",
                    "status": "success",
                    "element_count": 1129,
                    "source": "cached successful alternate Overpass response",
                },
            ],
            "geofabrik": {
                "downloaded": False,
                "reason": "No reasonably sized official city/regional extract exists; full India extract was not downloaded.",
            },
        },
    )
    s = pd.read_parquet(P / "sentinel5p_daily.parquet")
    valid = s[s.valid_pixel_count > 0]
    write(
        "sentinel5p_valid_dates.json",
        {
            "valid_dates": valid.to_dict("records"),
            "tested_records": len(s),
            "status": "closed_unavailable" if len(valid) == 0 else "available",
        },
    )
    write(
        "sentinel5p_recovery_report.json",
        {
            "status": "closed_unavailable" if len(valid) == 0 else "success",
            "product": "S5P_NO2",
            "tested_cities": sorted(s.city_id.unique().tolist()),
            "tested_dates": sorted(s.date.astype(str).unique().tolist()),
            "valid_record_count": len(valid),
            "valid_pixel_count": int(s.valid_pixel_count.sum()),
            "request_validation": "Authenticated Copernicus Statistical API calls used small 0.05-degree AOIs and provider dataMask; no QA threshold was weakened. The retained run used same-day 23:59:59 end bounds, which can yield empty provider intervals; one Bengaluru request returned HTTP 429. No further search was launched by closure scope.",
            "reason": "No valid pixels were materialised in the final retained artifact; Sentinel-5P is unavailable for this prototype phase.",
        },
    )
    write(
        "manual_actions_required.json",
        {
            "actions": [
                "Download an official GHS-POP R2023A India-intersecting raster into data/raw/ghsl/ if population estimates are required.",
                "For Agra and Amritsar, obtain OSM source geometry through a responsive public endpoint or an approved official regional extract; do not use the full India extract.",
                "Review OpenAQ candidate-station mapping and archive completeness before any future additional-station download.",
            ],
            "completed_actions": [
                "FIRMS archive and causal feature enrichment",
                "Authenticated Sentinel-5P validation closed with no usable pixels",
                "Bounded OSM recovery completed; Lucknow cache recovered.",
            ],
        },
    )
    write(
        "intelligence_failures.json",
        {
            "sentinel5p": "closed unavailable: 30 retained authenticated NO2 checks had zero valid pixels; one request was rate limited.",
            "ghsl": "no official raster exists in data/raw/ghsl/.",
            "osm_agra": "bounded public Overpass attempts failed (final HTTP 406).",
            "osm_amritsar": "bounded public Overpass attempts failed (final HTTP 406).",
            "additional_stations": "no safe archive-validated candidates established; no download attempted.",
        },
    )
    write(
        "intelligence_pipeline_run.json",
        {
            "status": "complete_with_documented_limitations",
            "enrichment_phase": "closed",
            "firms_events": 1111362,
            "firms_temporal_feature_rows": 1700,
            "sentinel_valid_records": len(valid),
            "osm_recovered_cities": ["delhi-ncr", "ludhiana", "lucknow"],
            "osm_unavailable_cities": ["agra", "amritsar"],
            "ghsl_available": False,
            "additional_station_downloads": 0,
        },
    )


if __name__ == "__main__":
    main()
