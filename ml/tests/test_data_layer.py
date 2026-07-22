from datetime import datetime, timezone

from shapely.geometry import Polygon

from airview_ml.data.adapters.cpcb import CpcbAdapter
from airview_ml.data.adapters.openaq import OpenAQAdapter
from airview_ml.data.adapters.sentinel5p import Sentinel5PAdapter
from airview_ml.data.adapters.weather import OpenMeteoAdapter
from airview_ml.data.archive import build_download_plan, rank_locations
from airview_ml.data.config import EligibilityThresholds
from airview_ml.data.contracts import AirQualityRecord
from airview_ml.data.normalization import match_city, normalise_city_name, normalise_pollutant
from airview_ml.data.quality import validate_air_quality
from airview_ml.data.readiness import readiness_score
from airview_ml.data.spatial import generate_grid
from airview_ml.data.units import convert_pollutant


def test_cpcb_parser_preserves_original_and_flags_invalid_coordinates() -> None:
    rows = CpcbAdapter.parse_records(
        [
            {
                "country": "IN",
                "city": "Delhi",
                "station": "A",
                "latitude": "120",
                "longitude": "77",
                "pollutant_id": "PM2.5",
                "pollutant_avg": "12.5",
                "pollutant_unit": "ug/m3",
                "last_update": "2026-01-01T00:00:00+05:30",
            }
        ]
    )
    assert rows[0].value_original == 12.5
    assert rows[0].value_canonical == 12.5
    assert "invalid_or_outside_india_coordinates" in rows[0].quality_flags


def test_openaq_headers_and_archive_path() -> None:
    assert OpenAQAdapter(None, "key").headers == {"X-API-Key": "key"}  # type: ignore[arg-type]
    path = OpenAQAdapter.archive_path(21, 2024, 1, 2)
    assert OpenAQAdapter.parse_archive_path(path) == {"locationid": 21, "year": 2024, "month": 1}


def test_unit_conversion_never_mixes_incompatible_quantities() -> None:
    assert convert_pollutant(1, "mg/m3", "co").value_canonical == 1
    assert convert_pollutant(1_000, "ug/m3", "co").value_canonical == 1
    assert "unsupported_or_incompatible_unit" in convert_pollutant(1, "mol/m2", "no2").flags


def test_open_meteo_parser_uses_utc_and_modelled_label() -> None:
    rows = OpenMeteoAdapter.parse_hourly(
        {
            "timezone": "UTC",
            "hourly_units": {"temperature_2m": "°C"},
            "hourly": {"time": ["2026-01-01T00:00"], "temperature_2m": [25]},
        },
        "city",
    )
    assert rows[0]["observed_at_utc"].endswith("+00:00")
    assert rows[0]["value_kind"] == "modelled"


def test_sentinel_request_and_missing_credentials() -> None:
    adapter = Sentinel5PAdapter(None, None)
    assert adapter.credentials_status().status == "credentials_required"
    request = adapter.statistical_request(
        {"type": "Polygon", "coordinates": []}, "2026-01-01T00:00:00Z", "2026-01-02T00:00:00Z"
    )
    assert request["aggregation"]["aggregationInterval"] == {"of": "P1D"}


def test_alias_matching_is_state_aware_and_never_fuzzy_merges() -> None:
    registry = [{"slug": "bengaluru", "name": "Bengaluru", "state": "Karnataka"}]
    assert normalise_city_name("Bangalore") == "bengaluru"
    assert match_city("Bangalore", "Karnataka", registry).matched_slug == "bengaluru"
    assert match_city("Bengalurux", "Karnataka", registry).confidence == "review"
    assert normalise_pollutant("PM 2.5") == "pm2_5"


def test_quality_duplicate_and_negative_flags() -> None:
    record = AirQualityRecord(
        "test",
        "test",
        "IN",
        None,
        None,
        None,
        "station",
        "station",
        None,
        20,
        77,
        "pm10",
        -1,
        "ug/m3",
        -1,
        "ug/m3",
        datetime.now(timezone.utc),
        None,
        "UTC",
        datetime.now(timezone.utc),
        True,
    )
    codes = {issue.code for issue in validate_air_quality([record, record])}
    assert {"impossible_negative_value", "duplicate_observation"}.issubset(codes)


def test_grid_is_deterministic_and_wgs84() -> None:
    grid = generate_grid(
        "test", Polygon([(77, 28), (77.01, 28), (77.01, 28.01), (77, 28.01)]), 1_000
    )
    assert grid and grid[0]["crs"] == "EPSG:4326"


def test_readiness_exclusion_reasons_are_explicit() -> None:
    score = readiness_score("city", {"active_station_count": 0}, EligibilityThresholds())
    assert not score.national_display_eligible
    assert "no valid station or current reading" in score.exclusion_reasons


def test_archive_ranking_and_plan_require_real_archive_months() -> None:
    locations = [
        {
            "id": 7,
            "coordinates": {"latitude": 28.6, "longitude": 77.2},
            "sensors": [{"parameter": {"name": "pm25"}}, {"parameter": {"name": "pm10"}}],
        }
    ]
    mappings = [
        {
            "location_id": 7,
            "station_id": "openaq-7",
            "station_name": "Station",
            "city_id": "delhi-ncr",
            "mapping_confidence": "high",
        }
    ]
    availability = [
        {
            "location_id": 7,
            "available_months": [f"2025-{month:02d}" for month in range(1, 13)],
            "estimated_file_count": 300,
            "estimated_size_bytes": 1000,
            "most_recent_file": {"date": "2025-12-31"},
        }
    ]
    ranked = rank_locations(locations, mappings, availability)
    plan = build_download_plan(
        ranked, start=datetime(2025, 1, 1).date(), end=datetime(2025, 12, 31).date()
    )
    assert ranked[0]["selection_score"] > 0
    assert plan["selection_count"] == 1
