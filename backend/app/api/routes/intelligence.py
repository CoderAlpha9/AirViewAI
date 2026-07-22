# ruff: noqa: E701, E702
import json
from pathlib import Path

import pandas as pd
from fastapi import APIRouter, HTTPException, Query

router = APIRouter(prefix="/intelligence")


def root() -> Path:
    return Path(__file__).resolve().parents[4]


def report(name: str):
    path = root() / "outputs" / "reports" / name
    if not path.is_file():
        raise HTTPException(503, "Intelligence outputs are unavailable")
    return json.loads(path.read_text(encoding="utf-8"))


def rows(city: str | None = None, pollutant: str | None = None, source_category: str | None = None, confidence: float | None = None):
    path = root() / "data" / "processed" / "india" / "source_attribution" / "source_attribution.parquet"
    if not path.is_file():
        raise HTTPException(503, "Attribution output is unavailable")
    frame = pd.read_parquet(path)
    if city: frame = frame[frame.city_id == city]
    if pollutant: frame = frame[frame.pollutant == pollutant]
    if source_category: frame = frame[frame.source_category == source_category]
    if confidence is not None: frame = frame[frame.confidence_score >= confidence]
    return frame.sort_values("likelihood_score", ascending=False).head(500).to_dict("records")


@router.get("/status")
async def status() -> dict:
    return {"status": "ready", "mode": "historical_replay", "methodology_version": "0.1.0-screening", "limitations": report("intelligence_failures.json")}


@router.get("/cities")
async def cities() -> dict:
    audit = report("intelligence_input_audit.json")
    return {"status": "ready", "mode": "historical_replay", "data": audit["cities"]}


@router.get("/attribution")
async def attribution(city: str | None = None, pollutant: str | None = Query(None, pattern="^(pm2_5|pm10)$"), source_category: str | None = None, confidence: float | None = Query(None, ge=0, le=1)) -> dict:
    return {"status": "ready", "mode": "historical_replay", "methodology_version": "0.1.0-screening", "data": rows(city, pollutant, source_category, confidence), "limitations": ["Evidence-supported source likelihood, not a confirmed source or source apportionment."]}


@router.get("/attribution/{attribution_id}")
async def attribution_one(attribution_id: str) -> dict:
    found = [x for x in rows() if x["attribution_id"] == attribution_id]
    if not found: raise HTTPException(404, "Attribution indicator not found")
    return {"status": "ready", "mode": "historical_replay", "data": found[0]}


@router.get("/episodes")
async def episodes(city: str | None = None) -> dict:
    data = report("pollution_episode_report.json")
    return {"status": "ready", "mode": "historical_replay", "data": data}


@router.get("/hotspots")
async def hotspots(city: str | None = None) -> dict:
    data = report("hotspot_intelligence_report.json"); items = data["items"]
    return {"status": "ready", "mode": "historical_replay", "data": [x for x in items if not city or x["city_id"] == city]}


@router.get("/priorities")
async def priorities(city: str | None = None, priority_tier: str | None = None) -> dict:
    data = report("enforcement_priority_report.json")["items"]
    return {"status": "ready", "mode": "historical_replay", "data": [x for x in data if (not city or x["city_id"] == city) and (not priority_tier or x["priority_tier"] == priority_tier)]}


@router.get("/interventions")
async def interventions(source_category: str | None = None) -> dict:
    data = report("intervention_catalogue.json")
    return {"status": "ready", "data": [x for x in data if not source_category or x["source_category"] == source_category]}


@router.get("/scenarios")
async def scenarios(city: str | None = None) -> dict:
    data = report("intervention_scenario_report.json")["items"]
    return {"status": "ready", "mode": "historical_replay", "data": [x for x in data if not city or x["city_id"] == city]}


@router.get("/evidence")
async def evidence() -> dict: return {"status": "ready", "data": report("source_attribution_methodology.json")}
@router.get("/case-studies")
async def case_studies() -> dict: return {"status": "ready", "mode": "historical_replay", "data": report("intelligence_city_comparison.json")}
@router.get("/comparison")
async def comparison() -> dict: return {"status": "ready", "mode": "historical_replay", "data": report("intelligence_city_comparison.json")}
