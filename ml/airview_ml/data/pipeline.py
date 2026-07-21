"""Reproducible, source-honest data acquisition CLI for AirView AI."""

import argparse
import json
import os
from datetime import datetime, timezone
from importlib.resources import files
from pathlib import Path
from typing import Any

import pandas as pd
from dotenv import load_dotenv

from airview_ml.data.adapters import (
    CpcbAdapter,
    FirmsAdapter,
    GhslAdapter,
    OpenAQAdapter,
    OpenMeteoAdapter,
    OsmAdapter,
    Sentinel5PAdapter,
)
from airview_ml.data.config import PROFILES, PipelineSettings, find_repository_root
from airview_ml.data.contracts import AirQualityRecord, SourceResult, serialise
from airview_ml.data.http import CachedHttpClient
from airview_ml.data.quality import validate_air_quality
from airview_ml.data.readiness import readiness_score
from airview_ml.data.reporting import empty_run, inventory_entry, load_report, write_report


def _settings(args: argparse.Namespace) -> PipelineSettings:
    root = find_repository_root()
    load_dotenv(root / "backend" / ".env", override=False)
    return PipelineSettings(root, Path(args.cache_dir) if args.cache_dir else None, Path(args.output_dir) if args.output_dir else None)


def _registry() -> list[dict[str, Any]]:
    return json.loads(files("airview_ml.data.resources").joinpath("major_cities.json").read_text(encoding="utf-8"))


def _selected_cities(args: argparse.Namespace, profile_name: str) -> list[dict[str, Any]]:
    registry = _registry()
    if args.city:
        return [city for city in registry if city["slug"] == args.city]
    if args.cities == "all" or (profile_name != "smoke" and args.cities != "major"):
        return registry
    profile = PROFILES[profile_name]
    return [city for city in registry if city["slug"] in profile.cities] if profile.cities else registry


def credentials(args: argparse.Namespace) -> int:
    _settings(args)
    names = ["DATA_GOV_IN_API_KEY", "OPENAQ_API_KEY", "NASA_FIRMS_MAP_KEY", "COPERNICUS_CLIENT_ID", "COPERNICUS_CLIENT_SECRET"]
    print(json.dumps({name: {"configured": bool(os.getenv(name))} for name in names}, indent=2))
    return 0


def discover(args: argparse.Namespace) -> int:
    settings = _settings(args)
    registry = _registry()
    write_report(settings.reports_dir, "cities", {"source": "configured_major_city_registry", "count": len(registry), "cities": registry, "note": "Seed registry is a planning registry, not evidence of discovered live coverage."})
    client = CachedHttpClient(settings.cache_dir, settings.request_timeout_seconds)
    _, cpcb_result = CpcbAdapter(client, os.getenv("DATA_GOV_IN_API_KEY"), settings.request_limit).fetch_latest()
    _, openaq_result = OpenAQAdapter(client, os.getenv("OPENAQ_API_KEY")).fetch_locations_india()
    write_report(settings.reports_dir, "inventory", [inventory_entry(cpcb_result), inventory_entry(openaq_result)])
    write_report(settings.reports_dir, "failures", [inventory_entry(item) for item in (cpcb_result, openaq_result) if item.status in {"failed", "credentials_required"}])
    print(f"Wrote configured registry ({len(registry)} seed cities) and live-discovery status reports.")
    return 0


def fetch(args: argparse.Namespace) -> int:
    settings = _settings(args)
    profile_name = args.profile
    profile = PROFILES[profile_name]
    cities = _selected_cities(args, profile_name)
    client = CachedHttpClient(settings.cache_dir, settings.request_timeout_seconds)
    source = args.source
    results: list[SourceResult] = []
    weather_rows: list[dict[str, Any]] = []
    air_rows: list[AirQualityRecord] = []
    openaq_locations: list[dict[str, Any]] = []
    sources = [source] if source else list(profile.include_sources)
    for source_name in sources:
        if source_name == "weather":
            adapter = OpenMeteoAdapter(client)
            for city in cities:
                rows, result = adapter.fetch_historical(city["latitude"], city["longitude"], args.start_date or profile.start_date.isoformat(), args.end_date or profile.end_date.isoformat(), city["slug"])
                weather_rows.extend(rows)
                results.append(result)
        elif source_name == "cpcb":
            rows, result = CpcbAdapter(client, os.getenv("DATA_GOV_IN_API_KEY"), settings.request_limit).fetch_latest(args.state)
            air_rows.extend(rows)
            results.append(result)
        elif source_name == "openaq":
            adapter = OpenAQAdapter(client, os.getenv("OPENAQ_API_KEY"))
            openaq_locations, api_result = adapter.fetch_locations_india()
            results.extend([api_result, adapter.probe_archive()])
        elif source_name == "firms":
            _, result = FirmsAdapter(os.getenv("NASA_FIRMS_MAP_KEY")).fetch_area((68.0, 6.0, 98.0, 38.0))
            results.append(result)
        elif source_name == "sentinel5p":
            results.append(Sentinel5PAdapter(os.getenv("COPERNICUS_CLIENT_ID"), os.getenv("COPERNICUS_CLIENT_SECRET")).credentials_status())
        elif source_name == "osm":
            if cities:
                city = cities[0]
                _, result = OsmAdapter(client).fetch_city(city["latitude"] - 0.03, city["longitude"] - 0.03, city["latitude"] + 0.03, city["longitude"] + 0.03)
                results.append(result)
        elif source_name == "ghsl":
            results.append(GhslAdapter().status())
    _persist_fetch_outputs(settings, weather_rows, air_rows, openaq_locations)
    _write_source_reports(
        settings,
        profile_name,
        results,
        cities,
        air_rows,
        weather_rows,
        openaq_locations,
    )
    print(json.dumps(serialise([inventory_entry(result) for result in results]), indent=2))
    return 0


def _persist_fetch_outputs(
    settings: PipelineSettings,
    weather_rows: list[dict[str, Any]],
    air_rows: list[AirQualityRecord],
    openaq_locations: list[dict[str, Any]],
) -> None:
    target = settings.output_dir / "india"
    target.mkdir(parents=True, exist_ok=True)
    if weather_rows:
        pd.DataFrame(weather_rows).to_parquet(target / "weather_hourly.parquet", index=False)
    if air_rows:
        pd.DataFrame([serialise(row) for row in air_rows]).to_parquet(target / "air_quality_hourly.parquet", index=False)
    if openaq_locations:
        station_rows = []
        sensor_rows = []
        for location in openaq_locations:
            coordinates = location.get("coordinates") or {}
            station_rows.append(
                {
                    "station_id": f"openaq-{location['id']}",
                    "provider": "OpenAQ",
                    "name": location.get("name"),
                    "city_name": location.get("locality"),
                    "country_code": (location.get("country") or {}).get("code"),
                    "latitude": coordinates.get("latitude"),
                    "longitude": coordinates.get("longitude"),
                    "timezone": location.get("timezone"),
                }
            )
            for sensor in location.get("sensors", []):
                sensor_rows.append(
                    {
                        "sensor_id": f"openaq-{sensor['id']}",
                        "station_id": f"openaq-{location['id']}",
                        "name": sensor.get("name"),
                        "parameter": (sensor.get("parameter") or {}).get("name"),
                    }
                )
        pd.DataFrame(station_rows).to_parquet(target / "stations.parquet", index=False)
        pd.DataFrame(sensor_rows).to_parquet(target / "sensors.parquet", index=False)


def _write_source_reports(
    settings: PipelineSettings,
    profile_name: str,
    results: list[SourceResult],
    cities: list[dict[str, Any]],
    air_rows: list[AirQualityRecord],
    weather_rows: list[dict[str, Any]],
    openaq_locations: list[dict[str, Any]],
) -> None:
    now = datetime.now(timezone.utc)
    issues = validate_air_quality(air_rows)
    existing_inventory = load_report(settings.reports_dir, "inventory")
    inventory_by_source = {
        entry.get("source"): entry
        for entry in existing_inventory or []
        if isinstance(entry, dict) and entry.get("source")
    }
    inventory_by_source.update({result.source: inventory_entry(result) for result in results})
    processed_india = settings.output_dir / "india"
    persisted_weather_count = (
        len(pd.read_parquet(processed_india / "weather_hourly.parquet"))
        if (processed_india / "weather_hourly.parquet").is_file()
        else 0
    )
    readiness = [readiness_score(city["slug"], {"active_station_count": 0, "history_days": 0, "hourly_completeness": 0, "coordinate_validity": 0, "recency_hours": float("inf"), "weather_availability": float(any(row["location_id"] == city["slug"] for row in weather_rows)), "geometry_available": 0, "spatial_feature_availability": 0, "population_availability": 0}, settings.thresholds) for city in cities]
    write_report(settings.reports_dir, "inventory", list(inventory_by_source.values()))
    discovered_cities = sorted(
        {
            location["locality"].strip()
            for location in openaq_locations
            if isinstance(location.get("locality"), str) and location["locality"].strip()
        }
    )
    write_report(
        settings.reports_dir,
        "cities",
        {
            "source": "configured_major_city_registry",
            "count": len(_registry()),
            "cities": _registry(),
            "openaq_discovered_city_count": len(discovered_cities),
            "openaq_discovered_city_names": discovered_cities,
            "requested_city_slugs": [city["slug"] for city in cities],
            "note": "A configured seed city is not automatically a data-eligible city.",
        },
    )
    write_report(settings.reports_dir, "run", {"status": "completed", "profile": profile_name, "started_at_utc": now.isoformat(), "completed_at_utc": now.isoformat(), "source_results": [inventory_entry(result) for result in results], "weather_rows": len(weather_rows), "air_quality_rows": len(air_rows)})
    write_report(
        settings.reports_dir,
        "coverage",
        {
            "weather_hourly_rows": len(weather_rows) or persisted_weather_count,
            "air_quality_rows": len(air_rows),
            "cities_requested": [city["slug"] for city in cities],
            "date_range": {
                "weather_start": weather_rows[0]["observed_at_utc"] if weather_rows else None,
                "weather_end": weather_rows[-1]["observed_at_utc"] if weather_rows else None,
            },
        },
    )
    write_report(settings.reports_dir, "quality", {"issue_count": len(issues), "issues": issues})
    write_report(settings.reports_dir, "readiness", {"cities": readiness})
    write_report(
        settings.reports_dir,
        "stations",
        {
            "count": len(openaq_locations) or len({row.station_id for row in air_rows if row.station_id}),
            "sensor_count": sum(len(location.get("sensors", [])) for location in openaq_locations),
            "source": "OpenAQ v3" if openaq_locations else "no station registry retrieved",
        },
    )
    write_report(settings.reports_dir, "aliases", {"uncertain_mappings": [], "note": "No automatic fuzzy city merges are performed."})
    failures = [inventory_entry(result) for result in results if result.status in {"failed", "credentials_required", "partial"}]
    write_report(settings.reports_dir, "failures", failures)
    manual = [result.error for result in results if result.status == "credentials_required" and result.error]
    write_report(settings.reports_dir, "manual", {"actions": manual})
    latest_path = settings.output_dir / "india" / "latest_snapshot.json"
    latest_path.write_text(
        json.dumps(
            {
                "status": "not_ready" if not air_rows else "ready",
                "message": "No current air-quality observations were retrieved."
                if not air_rows
                else "Current observations are available in air_quality_hourly.parquet.",
                "retrieved_at_utc": now.isoformat(),
                "air_quality_row_count": len(air_rows),
            },
            indent=2,
        ),
        encoding="utf-8",
    )


def build(args: argparse.Namespace) -> int:
    settings = _settings(args)
    source = settings.output_dir / "india" / "air_quality_hourly.parquet"
    if not source.is_file():
        print("No real air-quality observations are available; integrated table was not fabricated.")
        return 0
    frame = pd.read_parquet(source)
    frame["hour"] = pd.to_datetime(frame["observed_at_utc"], utc=True).dt.hour
    frame["day_of_week"] = pd.to_datetime(frame["observed_at_utc"], utc=True).dt.dayofweek
    frame["month"] = pd.to_datetime(frame["observed_at_utc"], utc=True).dt.month
    frame.to_parquet(settings.output_dir / "india" / "station_hourly_features.parquet", index=False)
    print("Built station-hour features from available real observations only.")
    return 0


def report(args: argparse.Namespace) -> int:
    settings = _settings(args)
    run = load_report(settings.reports_dir, "run") or empty_run(args.profile)
    print(json.dumps(run, indent=2))
    return 0


def all_steps(args: argparse.Namespace) -> int:
    fetch(args)
    build(args)
    return report(args)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["credentials", "discover", "fetch", "validate", "build", "report", "all"])
    parser.add_argument("--profile", choices=PROFILES.keys(), default="smoke")
    parser.add_argument("--source", choices=["cpcb", "openaq", "weather", "sentinel5p", "firms", "osm", "ghsl"])
    parser.add_argument("--cities", choices=["all", "major"], default="major")
    parser.add_argument("--city")
    parser.add_argument("--states", choices=["all"], default="all")
    parser.add_argument("--state")
    parser.add_argument("--start-date")
    parser.add_argument("--end-date")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--max-workers", type=int)
    parser.add_argument("--cache-dir")
    parser.add_argument("--output-dir")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    actions = {"credentials": credentials, "discover": discover, "fetch": fetch, "validate": report, "build": build, "report": report, "all": all_steps}
    return actions[args.command](args)


if __name__ == "__main__":
    raise SystemExit(main())
