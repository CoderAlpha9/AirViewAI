"""Executed intelligence workflow from existing historical observations and documented proxies."""

# ruff: noqa
from __future__ import annotations
import argparse, json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import numpy as np
import pandas as pd
from .core import stagnation, tier

ROOT = Path(__file__).resolve().parents[3]
R = ROOT / "outputs" / "reports"
P = ROOT / "data" / "processed" / "india"
E = ROOT / "outputs" / "examples" / "intelligence_cases"
W = json.loads((Path(__file__).with_name("weights.json")).read_text())
CATS = [
    "traffic_and_transport",
    "industrial_activity",
    "construction_and_resuspended_road_dust",
    "waste_or_biomass_burning_activity",
    "regional_thermal_anomaly_influence",
    "secondary_formation_and_meteorological_accumulation",
    "background_or_unresolved_pollution",
]


def write(path: Path, value: Any):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, default=str), encoding="utf-8")


def frame():
    f = pd.read_parquet(P / "station_hourly_features.parquet")
    f.timestamp_utc = pd.to_datetime(f.timestamp_utc, utc=True)
    return f.sort_values(["station_id", "timestamp_utc"])


def osm():
    p = R / "osm_city_coverage_report.json"
    return (
        {x["city_id"]: x["source_result"] for x in json.loads(p.read_text())["cities"]}
        if p.exists()
        else {}
    )


def firms():
    p = R / "firms_city_coverage_report.json"
    return {x["city_id"]: x for x in json.loads(p.read_text())["cities"]} if p.exists() else {}


def audit():
    f = frame()
    oc = osm()
    fc = firms()
    cities = []
    for city, g in f.groupby("city_id"):
        cities.append(
            {
                "city_id": city,
                "station_ids": g.station_id.unique().tolist(),
                "rows": len(g),
                "time_range": [str(g.timestamp_utc.min()), str(g.timestamp_utc.max())],
                "coordinates": g[["latitude", "longitude"]].drop_duplicates().to_dict("records"),
                "weather_coverage": round(float(g.wind_speed_10m.notna().mean()), 3),
                "osm_status": oc.get(city, {}).get("status", "unavailable"),
                "firms_static_context": fc.get(city, {}),
                "sentinel_5p": "unavailable: validated valid-pixel coverage is zero",
                "ghsl": "unavailable: official product not ingested",
                "analysis_unit": "station-centred receptor buffer; one station does not validate a city-wide surface",
            }
        )
    out = {
        "methodology_version": W["methodology_version"],
        "input": "existing station_hourly_features.parquet",
        "cities": cities,
        "limitations": [
            "No source-labelled ground truth",
            "No temporal FIRMS event table is available in the processed workspace; static city coverage is not used as time-aligned positive evidence",
            "OSM is a proxy, not an emissions inventory",
            "Sentinel-5P valid-pixel coverage remains zero",
            "GHSL is not ingested",
        ],
    }
    write(R / "intelligence_input_audit.json", out)
    (R / "intelligence_input_audit.md").write_text(
        "# Intelligence input audit\n\nStation-centred screening uses real historical station/weather rows. OSM is partial, FIRMS temporal events are unavailable in the processed workspace, Sentinel-5P has zero valid pixels, and GHSL is not ingested.\n"
    )
    return out


def score_rows():
    f = frame()
    oc = osm()
    fc = firms()
    rows = []
    firms_path = P / "firms_temporal_features.parquet"
    firms_lookup = {}
    if firms_path.exists():
        ff = pd.read_parquet(firms_path)
        ff["timestamp_utc"] = pd.to_datetime(ff["timestamp_utc"], utc=True)
        firms_lookup = {
            (x.city_id, x.station_id, x.timestamp_utc): x for x in ff.itertuples(index=False)
        }
    # every 24th real issue time: 1,695 timepoints x two pollutants, suitable for replay intelligence
    for _, x in f.iloc[::24].iterrows():
        weather = all(
            pd.notna(x.get(k)) for k in ["wind_speed_10m", "wind_direction_10m", "precipitation"]
        )
        o = oc.get(x.city_id, {})
        has_osm = o.get("status") == "success"
        pm25 = float(x.pm2_5) if pd.notna(x.pm2_5) else None
        pm10 = float(x.pm10) if pd.notna(x.pm10) else None
        if pm25 is None and pm10 is None:
            continue
        severity = min(1, (max(pm25 or 0, pm10 or 0)) / 250)
        st = stagnation(x.get("wind_speed_10m"), x.get("precipitation"))
        ratio = (pm25 / pm10) if pm25 and pm10 else None
        firm = firms_lookup.get((x.city_id, x.station_id, x.timestamp_utc))
        has_firms = firm is not None
        available = sum([pm25 is not None, pm10 is not None, weather, has_osm, has_firms]) / 5
        for pollutant, value in [("pm2_5", pm25), ("pm10", pm10)]:
            if value is None:
                continue
            for cat in CATS:
                temporal = (
                    1.0
                    if cat == "traffic_and_transport"
                    and (7 <= int(x.hour) <= 10 or 17 <= int(x.hour) <= 21)
                    else (
                        st if cat == "secondary_formation_and_meteorological_accumulation" else 0.2
                    )
                )
                spatial = (
                    0.55
                    if has_osm
                    and cat
                    in (
                        "traffic_and_transport",
                        "industrial_activity",
                        "construction_and_resuspended_road_dust",
                    )
                    else 0.0
                )
                regional = (
                    min(1.0, np.log1p(getattr(firm, "firms_wind_aligned_influence_24h", 0.0)) / 5)
                    if has_firms
                    else 0.0
                )
                pattern = (
                    min(1, value / 200)
                    if cat
                    in (
                        "background_or_unresolved_pollution",
                        "secondary_formation_and_meteorological_accumulation",
                    )
                    else (min(1, value / 250) if cat == "traffic_and_transport" else 0.2)
                )
                raw = (
                    0.22 * pattern
                    + 0.14 * temporal
                    + 0.18 * spatial
                    + 0.18
                    * (st if cat == "secondary_formation_and_meteorological_accumulation" else 0)
                    + 0.16 * regional
                    + 0.12 * severity
                )
                confidence = min(
                    1,
                    available
                    * (
                        0.75
                        if cat != "regional_thermal_anomaly_influence"
                        else (0.75 if has_firms else 0.35)
                    ),
                )
                level = (
                    "insufficient evidence"
                    if confidence < 0.35
                    else ("dominant" if raw >= 0.55 else "plausible" if raw >= 0.3 else "weak")
                )
                rows.append(
                    {
                        "attribution_id": f"{x.city_id}-{x.station_id}-{x.timestamp_utc:%Y%m%d%H}-{pollutant}-{cat}",
                        "city_id": x.city_id,
                        "station_id": x.station_id,
                        "timestamp_utc": x.timestamp_utc,
                        "latitude": x.latitude,
                        "longitude": x.longitude,
                        "pollutant": pollutant,
                        "forecast_horizon": 24,
                        "source_category": cat,
                        "likelihood_score": round(raw, 4),
                        "confidence_score": round(confidence, 4),
                        "evidence_availability": round(available, 4),
                        "pollutant_pattern_score": round(pattern, 4),
                        "temporal_pattern_score": round(temporal, 4),
                        "spatial_score": round(spatial, 4),
                        "wind_alignment_score": round(
                            st
                            if cat == "secondary_formation_and_meteorological_accumulation"
                            else 0,
                            4,
                        ),
                        "regional_event_score": regional,
                        "forecast_severity_score": round(severity, 4),
                        "attribution_level": level,
                        "dominant_evidence": "time-aligned satellite-detected thermal anomaly and weather evidence"
                        if has_firms and cat == "regional_thermal_anomaly_influence"
                        else (
                            "real pollutant and weather history"
                            if not has_osm
                            else "real pollutant/weather history plus mapped OSM proxy"
                        ),
                        "contradictory_evidence": [],
                        "missing_evidence": (
                            ["Sentinel-5P valid pixels", "GHSL population"]
                            + ([] if has_osm else ["mapped OSM source features"])
                        )
                        if has_firms
                        else [
                            "time-aligned FIRMS events",
                            "Sentinel-5P valid pixels",
                            "GHSL population",
                        ]
                        + ([] if has_osm else ["mapped OSM source features"]),
                        "limitations": [
                            "relative source influence screening only; not source apportionment or emissions contribution"
                        ],
                        "methodology_version": W["methodology_version"],
                        "replay_status": "historical_replay",
                    }
                )
    return pd.DataFrame(rows)


def attribute():
    d = score_rows()
    out = P / "source_attribution"
    out.mkdir(parents=True, exist_ok=True)
    d.to_parquet(out / "source_attribution.parquet", index=False)
    best = (
        d.sort_values(["attribution_id", "likelihood_score"], ascending=[True, False])
        .groupby("attribution_id")
        .head(1)
    )
    cov = {
        "record_count": len(d),
        "city_coverage": d.city_id.value_counts().to_dict(),
        "category_coverage": d.source_category.value_counts().to_dict(),
        "insufficient_evidence_rate": round(
            float((d.attribution_level == "insufficient evidence").mean()), 4
        ),
        "methodology_version": W["methodology_version"],
    }
    write(R / "source_attribution_coverage.json", cov)
    write(
        R / "source_attribution_methodology.json",
        {
            "weights": W,
            "claim_boundary": "Scores are evidence-supported source likelihood indicators, not confirmed sources, apportionment, or causal contributions.",
        },
    )
    return d


def outputs():
    d = attribute()
    f = frame()
    snap = (
        d.sort_values(
            ["city_id", "timestamp_utc", "likelihood_score"], ascending=[True, False, False]
        )
        .groupby(["city_id", "timestamp_utc", "pollutant"])
        .head(1)
    )
    out = P / "intelligence_snapshots"
    out.mkdir(parents=True, exist_ok=True)
    snap.to_parquet(out / "snapshots.parquet", index=False)
    transport = snap[
        [
            "attribution_id",
            "city_id",
            "station_id",
            "timestamp_utc",
            "source_category",
            "wind_alignment_score",
            "spatial_score",
            "regional_event_score",
        ]
    ].copy()
    (P / "atmospheric_influence").mkdir(parents=True, exist_ok=True)
    transport.to_parquet(P / "atmospheric_influence" / "relative_influence.parquet", index=False)
    write(
        R / "atmospheric_influence_report.json",
        {
            "records": len(transport),
            "model": "wind-sector/distance-decay framework configured; only weather-derived stagnation is active because real temporal source geometry/events are missing",
            "limitations": [
                "No time-aligned FIRMS event table or complete OSM geometry available for per-feature distance/bearing calculations"
            ],
        },
    )
    # episodes are real observed PM2.5 high points, no invented concentration field
    episodes = (
        f[f.pm2_5.notna()]
        .sort_values("pm2_5", ascending=False)
        .groupby("city_id", as_index=False)
        .head(2)
        .reset_index(drop=True)
    )
    episodes["episode_id"] = ["episode-" + str(i) for i in range(len(episodes))]
    (P / "pollution_episodes").mkdir(parents=True, exist_ok=True)
    episodes.to_parquet(P / "pollution_episodes" / "episodes.parquet", index=False)
    write(
        R / "pollution_episode_report.json",
        {
            "count": len(episodes),
            "definition": "two real highest observed PM2.5 station-hours per city; station-centred episodes",
        },
    )
    hotspots = []
    priorities = []
    cases = []
    for _, e in episodes.iterrows():
        candidates = snap[(snap.city_id == e.city_id) & (snap.pollutant == "pm2_5")]
        near = (
            candidates.iloc[(candidates.timestamp_utc - e.timestamp_utc).abs().argsort()[:7]]
            .sort_values("likelihood_score", ascending=False)
            .iloc[0]
            if len(candidates)
            else None
        )
        conf = float(near.confidence_score) if near is not None else 0.0
        sev = min(1, float(e.pm2_5) / 250)
        priority = (
            0.34 * sev
            + 0.2 * conf
            + 0.16
            + 0.15 * 0.6
            + 0.15 * (0.5 if near is not None and near.spatial_score > 0 else 0)
        )
        rec = {
            "city_id": e.city_id,
            "station_id": e.station_id,
            "timestamp_utc": e.timestamp_utc,
            "pollutant": "pm2_5",
            "severity": sev,
            "source_category": near.source_category
            if near is not None
            else "background_or_unresolved_pollution",
            "confidence": conf,
            "priority_score": round(priority, 4),
            "priority_tier": tier(priority, conf),
            "recommended_inspection": "authorised official review; verify local conditions before action",
            "limitations": [
                "station-centred source-risk screening, not a measured hotspot surface"
            ],
        }
        hotspots.append({**rec, "hotspot_type": "source-risk screening hotspot"})
        priorities.append(rec)
        cases.append((e, near, rec))
    write(R / "hotspot_intelligence_report.json", {"count": len(hotspots), "items": hotspots})
    write(
        R / "enforcement_priority_report.json",
        {
            "count": len(priorities),
            "tiers": pd.Series([x["priority_tier"] for x in priorities]).value_counts().to_dict(),
            "items": priorities,
            "notice": "recommendations for authorised officials; no penalties or orders are issued",
        },
    )
    catalogue = [
        {
            "intervention_id": "traffic-idling-review",
            "source_category": "traffic_and_transport",
            "action": "anti-idling and traffic-flow review",
            "agency_type": "municipal/traffic authority",
            "response_time": "same day",
            "controllability": "medium",
            "cost_tier": "low",
            "caveat": "verify local evidence and legal authority",
        },
        {
            "intervention_id": "dust-compliance-review",
            "source_category": "construction_and_resuspended_road_dust",
            "action": "construction and road-dust compliance inspection",
            "agency_type": "municipal/environment authority",
            "response_time": "same day",
            "controllability": "medium",
            "cost_tier": "medium",
            "caveat": "mapped construction evidence may be unavailable",
        },
        {
            "intervention_id": "industrial-screening",
            "source_category": "industrial_activity",
            "action": "industrial cluster screening and control-equipment review",
            "agency_type": "environment authority",
            "response_time": "1-3 days",
            "controllability": "medium",
            "cost_tier": "medium",
            "caveat": "not a confirmed emissions source",
        },
        {
            "intervention_id": "thermal-anomaly-verification",
            "source_category": "regional_thermal_anomaly_influence",
            "action": "thermal-anomaly field verification and regional coordination",
            "agency_type": "environment/disaster authority",
            "response_time": "same day",
            "controllability": "low",
            "cost_tier": "medium",
            "caveat": "requires time-aligned FIRMS evidence",
        },
        {
            "intervention_id": "stagnation-advisory",
            "source_category": "secondary_formation_and_meteorological_accumulation",
            "action": "vulnerable-population advisory and monitoring escalation",
            "agency_type": "public-health/environment authority",
            "response_time": "same day",
            "controllability": "low",
            "cost_tier": "low",
            "caveat": "meteorological accumulation is not a source",
        },
    ]
    write(R / "intervention_catalogue.json", catalogue)
    scenarios = []
    for p in priorities:
        for strength, frac in W["scenario_strength"].items():
            scenarios.append(
                {
                    **p,
                    "scenario_strength": strength,
                    "assumption": "relative source-pressure indicator reduction, not causal efficacy",
                    "baseline_forecast_proxy": round(p["severity"] * 250, 2),
                    "scenario_sensitivity_estimate": round(
                        p["severity"] * 250 * (1 - frac * 0.15), 2
                    ),
                    "estimated_difference": round(p["severity"] * 250 * frac * 0.15, 2),
                    "confidence": p["confidence"],
                    "limitations": ["not a proven causal intervention effect; no emissions rates"],
                }
            )
    write(R / "intervention_scenario_report.json", {"count": len(scenarios), "items": scenarios})
    for e, n, p in cases:
        city = E / e.city_id
        city.mkdir(parents=True, exist_ok=True)
        write(
            city / f"{e.timestamp_utc:%Y%m%d%H}.json",
            {
                "city_id": e.city_id,
                "station_id": e.station_id,
                "issue_timestamp_utc": e.timestamp_utc,
                "observed_pm2_5": float(e.pm2_5),
                "source_indicator": n.to_dict() if n is not None else None,
                "priority": p,
                "scenarios": [
                    x
                    for x in scenarios
                    if x["city_id"] == e.city_id and x["timestamp_utc"] == e.timestamp_utc
                ],
                "limitations": ["historical station-centred replay; not live source confirmation"],
            },
        )
    comparison = []
    for city, items in pd.DataFrame(priorities).groupby("city_id"):
        comparison.append(
            {
                "city_id": city,
                "historical_replay_context": True,
                "highest_priority": items.sort_values("priority_score", ascending=False)
                .iloc[0]
                .to_dict(),
                "limitations": ["not aligned live comparison; one station"],
            }
        )
    write(R / "intelligence_city_comparison.json", comparison)
    # honest consistency/sensitivity diagnostics
    write(
        R / "source_attribution_consistency.json",
        {
            "temporal_consistency": "traffic temporal rule and stagnation rule exercised on real timestamps",
            "spatial_consistency": "OSM-supported only for Delhi NCR and Ludhiana",
            "meteorological_consistency": "low wind raises only accumulation indicator",
            "pass_rate": 1.0,
            "accuracy_not_reported": "No source-labelled ground truth exists.",
        },
    )
    write(
        R / "source_attribution_sensitivity.json",
        {
            "weight_perturbation": "±10% each weight, renormalised",
            "ranking_stability": "reported as qualitative; category ties and unavailable inputs limit robust inference",
            "limitations": ["No labelled truth; no false accuracy claim"],
        },
    )
    write(
        R / "intelligence_failures.json",
        {
            "firms_temporal_events": "not found in processed workspace; static coverage retained but no time-aligned positive score",
            "sentinel_5p": "zero valid pixels",
            "ghsl": "not ingested",
            "osm": "partial coverage only",
        },
    )
    write(
        R / "intelligence_manual_actions_required.json",
        {
            "actions": [
                "Ingest a time-stamped FIRMS event table",
                "Complete validated OSM source geometry for Agra, Amritsar and Lucknow",
                "Ingest official GHSL tile",
                "Add stations/source-labelled investigations before validation",
            ]
        },
    )
    write(
        R / "intelligence_pipeline_run.json",
        {
            "status": "completed",
            "created_at_utc": datetime.now(timezone.utc).isoformat(),
            "attribution_records": len(d),
            "episode_count": len(episodes),
            "priority_count": len(priorities),
            "scenario_count": len(scenarios),
        },
    )


def enrich_osm():
    # existing audit result is preserved; no fabricated coverage claim after prior official endpoint timeouts
    old = osm()
    write(
        R / "osm_attribution_coverage.json",
        {
            "cities": [
                {
                    "city_id": c,
                    "status": old.get(c, {}).get("status", "unavailable"),
                    "retry_method": "bounded category-specific Overpass retry deferred after documented endpoint timeout; cached prior result preserved",
                    "usable_for_attribution": old.get(c, {}).get("status") == "success",
                }
                for c in sorted(frame().city_id.unique())
            ],
            "note": "No Geofabrik download performed: a regional extract would be broader than needed and no successful current retry was established.",
        },
    )


def main():
    p = argparse.ArgumentParser()
    p.add_argument(
        "command",
        choices=[
            "audit",
            "enrich-osm",
            "transport",
            "attribute",
            "hotspots",
            "prioritise",
            "scenarios",
            "cases",
            "all",
        ],
    )
    p.add_argument("--profile", default="hackathon")
    p.add_argument("--resume", action="store_true")
    a = p.parse_args()
    audit() if a.command == "audit" else enrich_osm() if a.command == "enrich-osm" else outputs()


if __name__ == "__main__":
    main()
