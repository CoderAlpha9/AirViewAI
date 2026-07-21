"""Reproducible, source-honest data acquisition CLI for AirView AI."""

import argparse
import json
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timezone
from importlib.resources import files
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from airview_ml.data.adapters import (
    CpcbAdapter,
    FirmsAdapter,
    GhslAdapter,
    OpenAQAdapter,
    OpenMeteoAdapter,
    OsmAdapter,
    Sentinel5PAdapter,
)
from airview_ml.data.archive import build_download_plan, rank_locations
from airview_ml.data.config import PROFILES, PipelineSettings, find_repository_root
from airview_ml.data.contracts import AirQualityRecord, SourceResult, serialise
from airview_ml.data.environment import credential_status, load_environment
from airview_ml.data.http import CachedHttpClient
from airview_ml.data.mapping import map_locations
from airview_ml.data.quality import validate_air_quality
from airview_ml.data.readiness import readiness_score
from airview_ml.data.reporting import empty_run, inventory_entry, load_report, write_report


def _settings(args: argparse.Namespace) -> PipelineSettings:
    root = find_repository_root()
    load_environment(root)
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
    settings = _settings(args)
    print(json.dumps(credential_status(settings.repository_root), indent=2))
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


def inspect_archive(args: argparse.Namespace) -> int:
    """Cache a zero-download availability audit for every resolved OpenAQ location."""
    settings = _settings(args)
    client = CachedHttpClient(settings.cache_dir, settings.request_timeout_seconds)
    adapter = OpenAQAdapter(client, os.getenv("OPENAQ_API_KEY"))
    locations, result = adapter.fetch_locations_india()
    if result.status != "success":
        write_report(settings.reports_dir, "openaq_india_archive_availability", {"status": result.status, "error": result.error, "locations": []})
        print(json.dumps(inventory_entry(result), indent=2))
        return 1
    mappings = map_locations(locations, _registry())
    _write_mapping_reports(settings, mappings)
    start, end = _range(args)
    resolved = [item for item in mappings if item["city_id"] and item["mapping_confidence"] in {"high", "medium"}]
    if args.max_audit_locations is not None:
        resolved = resolved[: args.max_audit_locations]
    by_id = {int(item["id"]): item for item in locations}
    audit: list[dict[str, Any]] = []
    # Bounded pool keeps S3 listing respectful while avoiding an hours-long serial audit.
    with ThreadPoolExecutor(max_workers=args.max_workers or PROFILES[args.profile].max_workers) as pool:
        futures = {pool.submit(adapter.audit_archive_location, int(item["location_id"]), start, end, by_id[int(item["location_id"])]): item for item in resolved}
        for future in as_completed(futures):
            mapping = futures[future]
            try:
                audit.append({**mapping, **future.result()})
            except Exception as exc:
                audit.append({**mapping, "requested_start": start.isoformat(), "requested_end": end.isoformat(), "index_status": "failed", "error": str(exc), "available_years": [], "available_months": [], "estimated_file_count": 0, "estimated_size_bytes": 0})
    audit.sort(key=lambda item: int(item["location_id"]))
    payload = {"status": "partial" if any(item["index_status"] != "success" for item in audit) else "success", "requested_range": {"start": start.isoformat(), "end": end.isoformat()}, "resolved_locations_total": len([item for item in mappings if item["city_id"]]), "audited_location_count": len(audit), "audit_limit": args.max_audit_locations, "locations": audit, "note": "S3 object indexes only; no measurement files are downloaded during audit."}
    write_report(settings.reports_dir, "openaq_india_archive_availability", payload)
    print(json.dumps({key: payload[key] for key in ("status", "audited_location_count", "requested_range")}, indent=2))
    return 0


def plan(args: argparse.Namespace) -> int:
    settings = _settings(args)
    availability = load_report(settings.reports_dir, "openaq_india_archive_availability")
    if not isinstance(availability, dict) or not availability.get("locations"):
        print("No archive audit is available. Run inspect-archive before plan.")
        return 1
    client = CachedHttpClient(settings.cache_dir, settings.request_timeout_seconds)
    locations, result = OpenAQAdapter(client, os.getenv("OPENAQ_API_KEY")).fetch_locations_india()
    if result.status != "success":
        print(json.dumps(inventory_entry(result), indent=2))
        return 1
    mappings = map_locations(locations, _registry())
    ranked = rank_locations(locations, mappings, list(availability["locations"]))
    start, end = _range(args)
    payload = build_download_plan(ranked, start=start, end=end, max_cities=args.max_cities, stations_per_city=args.stations_per_city, max_files=args.max_archive_files, required_pollutant=args.required_pollutant, minimum_months=args.minimum_archive_months, minimum_confidence=args.minimum_mapping_confidence)
    payload["ranked_locations"] = ranked
    write_report(settings.reports_dir, "openaq_download_plan", payload)
    print(json.dumps({key: payload[key] for key in ("selected_city_count", "selection_count", "expected_file_count", "expected_size_bytes")}, indent=2))
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
    history_rows = pd.DataFrame()
    sources = [source] if source else list(profile.include_sources)
    for source_name in sources:
        if source_name == "weather":
            adapter = OpenMeteoAdapter(client)
            for city in cities:
                rows, result = adapter.fetch_historical(city["latitude"], city["longitude"], args.start_date or profile.start_date.isoformat(), args.end_date or profile.end_date.isoformat(), city["slug"])
                weather_rows.extend(rows)
                results.append(result)
        elif source_name == "cpcb":
            cpcb = CpcbAdapter(client, os.getenv("DATA_GOV_IN_API_KEY"), settings.request_limit)
            rows, result = cpcb.fetch_latest(args.state)
            air_rows.extend(rows)
            results.append(result)
            write_report(settings.reports_dir, "cpcb_recovery_report", {**cpcb.last_recovery, "source_result": inventory_entry(result)})
            write_report(settings.reports_dir, "cpcb_openaq_station_crosswalk", _cpcb_openaq_crosswalk(rows))
        elif source_name in {"openaq", "openaq-metadata"}:
            adapter = OpenAQAdapter(client, os.getenv("OPENAQ_API_KEY"))
            openaq_locations, api_result = adapter.fetch_locations_india()
            results.extend([api_result, adapter.probe_archive()])
        elif source_name == "openaq-history":
            adapter = OpenAQAdapter(client, os.getenv("OPENAQ_API_KEY"))
            openaq_locations, metadata_result = adapter.fetch_locations_india()
            results.append(metadata_result)
            history_rows, history_result, mappings = _fetch_openaq_history(adapter, openaq_locations, cities, args)
            results.append(history_result)
            _write_mapping_reports(settings, mappings)
        elif source_name == "firms":
            events, result = FirmsAdapter(os.getenv("NASA_FIRMS_MAP_KEY")).fetch_area((68.0, 6.0, 98.0, 38.0), days=30)
            results.append(result)
            write_report(settings.reports_dir, "firms_validation_report", {"source_result": inventory_entry(result), "product": "VIIRS_SNPP_NRT", "days": 30, "bbox": [68.0, 6.0, 98.0, 38.0], "returned_schema": sorted(events[0]) if events else [], "term": "satellite-detected thermal anomaly"})
            write_report(settings.reports_dir, "firms_city_coverage_report", _firms_city_coverage(events, cities))
        elif source_name == "sentinel5p":
            sentinel = Sentinel5PAdapter(os.getenv("COPERNICUS_CLIENT_ID"), os.getenv("COPERNICUS_CLIENT_SECRET"))
            validation: list[dict[str, Any]] = []
            for city in [item for item in cities if item["slug"] in {"delhi-ncr", "mumbai", "bengaluru"}]:
                aoi = _small_city_aoi(city)
                payload, result = sentinel.validate_statistics(aoi, "2026-07-01T00:00:00Z", "2026-07-02T00:00:00Z")
                results.append(result)
                validation.append({"city_id": city["slug"], "aoi": aoi, "source_result": inventory_entry(result), "metrics": _sentinel_metrics(payload), "response": payload if result.status == "success" else None})
            if not validation:
                results.append(sentinel.credentials_status())
            write_report(settings.reports_dir, "sentinel5p_validation_report", {"validations": validation, "note": "Real response bodies are retained only when authentication and processing succeed; failures are explicit."})
            write_report(settings.reports_dir, "sentinel5p_coverage_report", {"cities_attempted": [item["city_id"] for item in validation], "successful_cities": [item["city_id"] for item in validation if item["source_result"]["status"] == "success"]})
        elif source_name == "osm":
            saved_plan = load_report(settings.reports_dir, "openaq_download_plan")
            if profile_name != "smoke" and isinstance(saved_plan, dict) and saved_plan.get("cities"):
                selected_ids = {item["city_id"] for item in saved_plan["cities"]}
                cities = [item for item in cities if item["slug"] in selected_ids]
            osm_coverage = []
            for city in cities:
                _, result = OsmAdapter(client).fetch_city(city["latitude"] - 0.03, city["longitude"] - 0.03, city["latitude"] + 0.03, city["longitude"] + 0.03)
                results.append(result)
                osm_coverage.append({"city_id": city["slug"], "source_result": inventory_entry(result)})
            write_report(settings.reports_dir, "osm_city_coverage_report", {"cities": osm_coverage, "note": "Static OSM features are spatial context, not live emissions."})
        elif source_name == "ghsl":
            results.append(GhslAdapter().status())
            write_report(settings.reports_dir, "ghsl_ingestion_report", {"status": "manual_download_required", "official_product": "GHS-POP R2023A", "destination": "data/raw/ghsl/", "manual_action": "Download only the official European Commission/Copernicus GHS-POP R2023A India-intersecting tile for the chosen reference epoch, verify its checksum, then run the GHSL clip stage. No unofficial mirror is used."})
    _persist_fetch_outputs(settings, weather_rows, air_rows, openaq_locations, history_rows)
    _write_source_reports(
        settings,
        profile_name,
        results,
        cities,
        air_rows,
        weather_rows,
        openaq_locations,
        history_rows,
    )
    print(json.dumps(serialise([inventory_entry(result) for result in results]), indent=2))
    return 0


def _persist_fetch_outputs(
    settings: PipelineSettings,
    weather_rows: list[dict[str, Any]],
    air_rows: list[AirQualityRecord],
    openaq_locations: list[dict[str, Any]],
    history_rows: pd.DataFrame,
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
    if not history_rows.empty:
        history_rows.to_parquet(target / "air_quality_sensor_hourly.parquet", index=False)
        station = _station_hourly(history_rows)
        station.to_parquet(target / "air_quality_station_hourly.parquet", index=False)
        station.to_parquet(target / "air_quality_hourly.parquet", index=False)


def _write_source_reports(
    settings: PipelineSettings,
    profile_name: str,
    results: list[SourceResult],
    cities: list[dict[str, Any]],
    air_rows: list[AirQualityRecord],
    weather_rows: list[dict[str, Any]],
    openaq_locations: list[dict[str, Any]],
    history_rows: pd.DataFrame,
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
    readiness = _readiness_from_history(cities, history_rows, settings)
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
    write_report(settings.reports_dir, "run", {"status": "completed", "profile": profile_name, "started_at_utc": now.isoformat(), "completed_at_utc": now.isoformat(), "source_results": [inventory_entry(result) for result in results], "weather_rows": len(weather_rows), "air_quality_rows": len(air_rows) + len(history_rows)})
    write_report(
        settings.reports_dir,
        "coverage",
        {
            "weather_hourly_rows": len(weather_rows) or persisted_weather_count,
            "air_quality_rows": len(air_rows) + len(history_rows),
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
                "status": "not_ready" if not air_rows and history_rows.empty else "ready",
                "message": "No current air-quality observations were retrieved."
                if not air_rows and history_rows.empty
                else "Current observations are available in air_quality_hourly.parquet.",
                "retrieved_at_utc": now.isoformat(),
                "air_quality_row_count": len(air_rows) + len(history_rows),
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
    frame["timestamp_utc"] = pd.to_datetime(frame["timestamp_utc"], utc=True)
    weather_frames = []
    adapter = OpenMeteoAdapter(CachedHttpClient(settings.cache_dir, settings.request_timeout_seconds))
    for station_id, station in frame.groupby("station_id"):
        rows, _ = adapter.fetch_historical(float(station["latitude"].iloc[0]), float(station["longitude"].iloc[0]), frame["timestamp_utc"].min().date().isoformat(), frame["timestamp_utc"].max().date().isoformat(), station_id)
        weather_frames.append(pd.DataFrame(rows))
    weather = pd.concat(weather_frames, ignore_index=True) if weather_frames else pd.DataFrame()
    if not weather.empty:
        weather = weather.rename(columns={"location_id": "station_id", "observed_at_utc": "timestamp_utc"})
        weather["timestamp_utc"] = pd.to_datetime(weather["timestamp_utc"], utc=True)
        frame = frame.merge(weather.drop(columns=["units", "source_timezone"], errors="ignore"), on=["station_id", "timestamp_utc"], how="left")
    frame["hour"] = frame["timestamp_utc"].dt.hour
    frame["day_of_week"] = frame["timestamp_utc"].dt.dayofweek
    frame["day_of_year"] = frame["timestamp_utc"].dt.dayofyear
    frame["month"] = frame["timestamp_utc"].dt.month
    frame["weekend"] = frame["day_of_week"] >= 5
    frame["season"] = frame["month"].map(_indian_season).astype("string")
    frame["hour_sin"] = np.sin(2 * np.pi * frame["hour"] / 24)
    frame["hour_cos"] = np.cos(2 * np.pi * frame["hour"] / 24)
    frame["day_of_year_sin"] = np.sin(2 * np.pi * frame["day_of_year"] / 366)
    frame["day_of_year_cos"] = np.cos(2 * np.pi * frame["day_of_year"] / 366)
    for pollutant in ("pm2_5", "pm10", "no2", "so2", "co", "o3", "nh3", "bc"):
        if pollutant not in frame:
            frame[pollutant] = float("nan")
        frame[f"{pollutant}_available"] = frame[pollutant].notna()
    frame.to_parquet(settings.output_dir / "india" / "station_hourly_features.parquet", index=False)
    partitioned = settings.output_dir / "india" / "station_hourly_features"
    partitioned.mkdir(parents=True, exist_ok=True)
    for city_id, city_frame in frame.groupby("city_id", dropna=False):
        safe_city = str(city_id or "unmapped").replace("/", "_")
        city_frame.to_parquet(partitioned / f"city_id={safe_city}.parquet", index=False)
    split_manifest = _write_split_manifest(frame, settings)
    latest = frame.sort_values("timestamp_utc").tail(1).to_dict("records")[0]
    latest["freshness"] = "stale" if (datetime.now(timezone.utc) - latest["timestamp_utc"].to_pydatetime()).total_seconds() > 48 * 3600 else "current"
    latest["source_provider"] = "OpenAQ archive"
    (settings.output_dir / "india" / "latest_snapshot.json").write_text(json.dumps(serialise({"status": "ready", "reading": latest}), indent=2), encoding="utf-8")
    write_report(settings.reports_dir, "model_data_readiness", _model_readiness(frame, split_manifest))
    print("Built station-hour features from available real observations only.")
    return 0


def _fetch_openaq_history(adapter: OpenAQAdapter, locations: list[dict[str, Any]], cities: list[dict[str, Any]], args: argparse.Namespace) -> tuple[pd.DataFrame, SourceResult, list[dict[str, Any]]]:
    start, end = _range(args)
    mappings = map_locations(locations, _registry())
    frames: list[pd.DataFrame] = []
    manifest: list[dict[str, Any]] = []
    saved_plan = load_report(_settings(args).reports_dir, "openaq_download_plan")
    if isinstance(saved_plan, dict) and saved_plan.get("stations"):
        candidates = list(saved_plan["stations"])
    else:
        wanted = {city["slug"] for city in cities}
        candidates = [item for item in mappings if item["city_id"] in wanted and item["mapping_confidence"] in {"high", "medium"}]
        candidates.sort(key=lambda item: int(item["location_id"]))
    file_jobs: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for mapping in candidates:
        try:
            file_jobs.extend((mapping, item) for item in adapter.list_archive_files(int(mapping["location_id"]), start, end))
        except Exception as exc:
            manifest.append({"location_id": mapping["location_id"], "status": "failed", "error": str(exc)})
    # Interleave cities by date so a bounded/resumed run produces usable history
    # across the whole plan instead of completing one city before touching another.
    file_jobs.sort(key=lambda job: (job[1]["date"], job[0]["city_id"], job[0]["location_id"]))
    if args.max_archive_files is not None:
        file_jobs = file_jobs[: args.max_archive_files]
    def download(job: tuple[dict[str, Any], dict[str, Any]]) -> tuple[pd.DataFrame, dict[str, Any]]:
        mapping, item = job
        content, cached_path = adapter.download_archive_file(item["key"], int(item.get("size") or 0) or None)
        return adapter.archive_sensor_hourly(adapter.decompress_csv(content), mapping), {**item, "location_id": mapping["location_id"], "city_id": mapping["city_id"], "cache_path": cached_path, "status": "downloaded"}
    with ThreadPoolExecutor(max_workers=args.max_workers or PROFILES[args.profile].max_workers) as pool:
        futures = [pool.submit(download, job) for job in file_jobs]
        for future in as_completed(futures):
            try:
                parsed, entry = future.result()
                frames.append(parsed)
                manifest.append(entry)
            except Exception as exc:
                manifest.append({"status": "failed", "error": str(exc)})
    write_report(_settings(args).reports_dir, "openaq_archive_manifest", manifest)
    combined = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    result = SourceResult(source="openaq_history", status="success" if not combined.empty else "partial", retrieved_at_utc=datetime.now(timezone.utc), row_count=len(combined), geographic_coverage="selected mapped Indian OpenAQ archive locations", variables=sorted(combined["pollutant"].dropna().unique().tolist()) if not combined.empty else [], official_url="https://docs.openaq.org/aws/about", licence="Provider-specific licences preserved in OpenAQ metadata")
    return combined, result, mappings


def _write_mapping_reports(settings: PipelineSettings, mappings: list[dict[str, Any]]) -> None:
    unresolved = [item for item in mappings if not item["city_id"]]
    write_report(settings.reports_dir, "openaq_location_mapping_report", {"resolved_count": len(mappings) - len(unresolved), "unresolved_count": len(unresolved), "locations": mappings})
    write_report(settings.reports_dir, "unresolved_openaq_locations", unresolved)
    write_report(settings.reports_dir, "ambiguous_station_matches", [item for item in mappings if item["mapping_confidence"] == "review"])


def _cpcb_openaq_crosswalk(records: list[AirQualityRecord]) -> dict[str, Any]:
    """Conservative crosswalk: only normalized exact station-name and coordinate evidence."""
    stations = {}
    for record in records:
        if not record.station_id:
            continue
        key = str(record.station_id).strip().lower()
        stations[key] = {"cpcb_station_id": record.station_id, "city_name": record.city_name, "latitude": record.latitude, "longitude": record.longitude, "match_status": "pending_openaq_metadata_exact_name_coordinate_review"}
    return {"method": "CPCB records retained independently; no fuzzy station identity merges", "candidate_count": len(stations), "candidates": list(stations.values())}


def _small_city_aoi(city: dict[str, Any]) -> dict[str, Any]:
    latitude, longitude, delta = float(city["latitude"]), float(city["longitude"]), 0.04
    return {"type": "Polygon", "coordinates": [[[longitude - delta, latitude - delta], [longitude + delta, latitude - delta], [longitude + delta, latitude + delta], [longitude - delta, latitude + delta], [longitude - delta, latitude - delta]]]}


def _firms_city_coverage(events: list[dict[str, Any]], cities: list[dict[str, Any]]) -> dict[str, Any]:
    adapter = FirmsAdapter(None)
    rows = []
    for city in cities:
        features = adapter.influence_features(events, float(city["latitude"]), float(city["longitude"]))
        rows.append({"city_id": city["slug"], **features})
    return {"term": "satellite-detected thermal anomaly", "cities": rows}


def _sentinel_metrics(payload: dict[str, Any]) -> list[dict[str, Any]]:
    metrics = []
    geometry_pixels = int(payload.get("geometryPixelCount") or 0)
    for item in payload.get("data", []):
        stats = (((item.get("outputs") or {}).get("default") or {}).get("bands") or {}).get("B0", {}).get("stats", {})
        samples, no_data = int(stats.get("sampleCount") or 0), int(stats.get("noDataCount") or 0)
        metrics.append({"interval": item.get("interval"), "valid_pixel_count": samples - no_data, "coverage_percentage": round(100 * (samples - no_data) / geometry_pixels, 2) if geometry_pixels else 0.0, "mean": stats.get("mean"), "median": (stats.get("percentiles") or {}).get("50.0"), "standard_deviation": stats.get("stDev"), "percentiles": stats.get("percentiles"), "qa_note": "NoData pixels are excluded by the provider dataMask."})
    return metrics


def _station_hourly(sensor: pd.DataFrame) -> pd.DataFrame:
    sensor = sensor.dropna(subset=["value", "timestamp_utc"]).copy()
    sensor["timestamp_utc"] = pd.to_datetime(sensor["timestamp_utc"], utc=True).dt.floor("h")
    grouped = sensor.groupby(["city_id", "state_id", "station_id", "station_name", "timestamp_utc", "pollutant"], dropna=False)
    long = grouped.agg(value=("value", "mean"), observation_count=("value", "count"), latitude=("latitude", "first"), longitude=("longitude", "first")).reset_index()
    return long.pivot(index=["city_id", "state_id", "station_id", "station_name", "timestamp_utc", "latitude", "longitude"], columns="pollutant", values="value").reset_index()


def _readiness_from_history(cities: list[dict[str, Any]], history: pd.DataFrame, settings: PipelineSettings) -> list[Any]:
    result = []
    for city in cities:
        subset = history[history["city_id"] == city["slug"]] if not history.empty else pd.DataFrame()
        history_days = int((pd.to_datetime(subset["timestamp_utc"]).max() - pd.to_datetime(subset["timestamp_utc"]).min()).days + 1) if not subset.empty else 0
        result.append(readiness_score(city["slug"], {"active_station_count": subset["station_id"].nunique() if not subset.empty else 0, "history_days": history_days, "hourly_completeness": _hourly_completeness(subset), "coordinate_validity": 1 if not subset.empty else 0, "recency_hours": 0 if not subset.empty else float("inf"), "weather_availability": 0, "geometry_available": 0, "spatial_feature_availability": 0, "population_availability": 0}, settings.thresholds))
    return result


def _range(args: argparse.Namespace) -> tuple[date, date]:
    profile = PROFILES[args.profile]
    return date.fromisoformat(args.start_date or profile.start_date.isoformat()), date.fromisoformat(args.end_date or profile.end_date.isoformat())


def _indian_season(month: int) -> str:
    if month in {12, 1, 2}:
        return "winter"
    if month in {3, 4, 5}:
        return "pre_monsoon"
    if month in {6, 7, 8, 9}:
        return "monsoon"
    return "post_monsoon"


def _hourly_completeness(frame: pd.DataFrame) -> float:
    if frame.empty:
        return 0.0
    timestamps = pd.to_datetime(frame["timestamp_utc"], utc=True).dt.floor("h")
    elapsed_hours = max(int((timestamps.max() - timestamps.min()).total_seconds() // 3600) + 1, 1)
    return min(1.0, frame.drop_duplicates(["station_id", "timestamp_utc"]).shape[0] / (frame["station_id"].nunique() * elapsed_hours))


def _write_split_manifest(frame: pd.DataFrame, settings: PipelineSettings) -> dict[str, Any]:
    timestamps = pd.to_datetime(frame["timestamp_utc"], utc=True)
    boundaries = {
        "train": (None, pd.Timestamp("2025-09-30 23:59:59", tz="UTC")),
        "validation": (pd.Timestamp("2025-10-01", tz="UTC"), pd.Timestamp("2026-01-31 23:59:59", tz="UTC")),
        "test": (pd.Timestamp("2026-02-01", tz="UTC"), None),
    }
    splits: dict[str, Any] = {}
    for name, (start, end) in boundaries.items():
        mask = pd.Series(True, index=frame.index)
        if start is not None:
            mask &= timestamps >= start
        if end is not None:
            mask &= timestamps <= end
        subset = frame[mask]
        splits[name] = {"start": start.isoformat() if start is not None else timestamps.min().isoformat(), "end": end.isoformat() if end is not None else timestamps.max().isoformat(), "rows": len(subset), "stations": sorted(subset["station_id"].dropna().unique().tolist()), "cities": sorted(subset["city_id"].dropna().unique().tolist())}
    manifest = {"strategy": "strict_chronological_no_random_rows", "source_start": timestamps.min().isoformat(), "source_end": timestamps.max().isoformat(), "splits": splits, "cold_start_stations": sorted(set(splits["validation"]["stations"]) - set(splits["train"]["stations"]))}
    (settings.output_dir / "india" / "model_split_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def _model_readiness(frame: pd.DataFrame, splits: dict[str, Any]) -> dict[str, Any]:
    station_rows = []
    for station_id, subset in frame.groupby("station_id"):
        span_days = int((pd.to_datetime(subset["timestamp_utc"]).max() - pd.to_datetime(subset["timestamp_utc"]).min()).days + 1)
        target = "pm2_5" if subset["pm2_5"].notna().any() else "pm10" if subset["pm10"].notna().any() else None
        eligible = bool(target and span_days >= 365 and _hourly_completeness(subset) >= 0.60 and subset["temperature_2m"].notna().any() and station_id in splits["splits"]["validation"]["stations"] and station_id in splits["splits"]["test"]["stations"])
        station_rows.append({"station_id": station_id, "city_id": subset["city_id"].iloc[0], "target_pollutant": target, "history_days": span_days, "hourly_completeness": round(_hourly_completeness(subset), 4), "forecast_eligible": eligible, "exclusion_reason": None if eligible else "requires >=12 months, >=60% hourly coverage, target pollutant, weather, validation, and test observations"})
    return {"forecast_eligible_cities": sorted({row["city_id"] for row in station_rows if row["forecast_eligible"]}), "forecast_eligible_stations": [row for row in station_rows if row["forecast_eligible"]], "excluded_stations": [row for row in station_rows if not row["forecast_eligible"]], "split_strategy": splits["strategy"]}


def report(args: argparse.Namespace) -> int:
    settings = _settings(args)
    run = load_report(settings.reports_dir, "run") or empty_run(args.profile)
    print(json.dumps(run, indent=2))
    return 0


def all_steps(args: argparse.Namespace) -> int:
    if args.profile != "smoke":
        inspect_archive(args)
        plan(args)
    fetch(args)
    build(args)
    return report(args)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["credentials", "discover", "inspect-archive", "plan", "fetch", "validate", "build", "report", "all"])
    parser.add_argument("--profile", choices=PROFILES.keys(), default="smoke")
    parser.add_argument("--source", choices=["cpcb", "openaq", "openaq-metadata", "openaq-history", "weather", "sentinel5p", "firms", "osm", "ghsl"])
    parser.add_argument("--cities", choices=["all", "major"], default="major")
    parser.add_argument("--city")
    parser.add_argument("--states", choices=["all"], default="all")
    parser.add_argument("--state")
    parser.add_argument("--start-date")
    parser.add_argument("--end-date")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--max-workers", type=int)
    parser.add_argument("--max-audit-locations", type=int, help="Optional diagnostic cap; omit to audit every resolved location.")
    parser.add_argument("--max-cities", type=int, help="Optional plan cap; omit for all suitable cities.")
    parser.add_argument("--stations-per-city", type=int, default=2)
    parser.add_argument("--max-archive-files", type=int, help="Optional execution cap; omit for the complete selected plan.")
    parser.add_argument("--required-pollutant", default="pm2_5", choices=["pm2_5", "pm10", "no2", "so2", "co", "o3", "nh3", "bc"])
    parser.add_argument("--minimum-archive-months", type=int, default=12)
    parser.add_argument("--minimum-mapping-confidence", choices=["high", "medium", "low"], default="medium")
    parser.add_argument("--cache-dir")
    parser.add_argument("--output-dir")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    actions = {"credentials": credentials, "discover": discover, "inspect-archive": inspect_archive, "plan": plan, "fetch": fetch, "validate": report, "build": build, "report": report, "all": all_steps}
    return actions[args.command](args)


if __name__ == "__main__":
    raise SystemExit(main())
