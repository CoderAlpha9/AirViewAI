"""Deterministic, persisted coordinator over existing replay reports."""
# ruff: noqa: E701, E702
import json
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query

from app.services.product_runs import compact, list_runs, persist, read

router = APIRouter(prefix="/orchestration")
def root() -> Path: return Path(__file__).resolve().parents[4]
def load(name: str):
    path = root() / "outputs" / "reports" / name
    if not path.is_file(): raise HTTPException(503, f"Missing replay artifact: {name}")
    return json.loads(path.read_text(encoding="utf-8"))
@router.get("/status")
async def status(): return {"status":"ready","mode":"historical_replay","agents":["data_readiness","forecast","source_intelligence","hotspot_exposure","enforcement","intervention","citizen_advisory","audit_safety"]}
@router.post("/run")
async def run(city_id: str="delhi-ncr", pollutant: str="pm2_5", horizon: int=24, language: str="en", audience: str="general_public", format: str="standard", scenario_strength: str="reported"):
    started=time.time(); priority=next((item for item in load("enforcement_priority_report.json")["items"] if item["city_id"] == city_id), None)
    if not priority: raise HTTPException(404, "No validated replay case for city")
    references=["intelligence_input_audit.json","forecast_champion_matrix.json","source_attribution_coverage.json","hotspot_intelligence_report.json","enforcement_priority_report.json","intervention_scenario_report.json","template-v1","historical-replay-policy"]
    names=["data_readiness","forecast","source_intelligence","hotspot_exposure","enforcement","intervention","citizen_advisory","audit_safety"]
    agents=[{"agent_name":name,"version":"1.0","status":"completed","duration_ms":0,"evidence_references":[references[index]],"warnings":["historical replay only"] if name in {"forecast","citizen_advisory"} else [],"skipped_reason":None} for index,name in enumerate(names)]
    package={"schema_version":"1.1","run_id":str(uuid.uuid4()),"created_at_utc":datetime.now(timezone.utc).isoformat(),"request":{"city_id":city_id,"pollutant":pollutant,"horizon":horizon,"language":language,"audience":audience,"format":format,"scenario_strength":scenario_strength},"mode":"historical_replay","city_id":city_id,"station_id":priority["station_id"],"issue_timestamp":priority["timestamp_utc"],"pollutant":pollutant,"horizon":horizon,"priority":priority,"agents":agents,"advisory":{"language":language,"audience":audience,"format":format,"scenario_strength":scenario_strength},"advisory_template_version":"1.0","evidence_references":references,"limitations":["Not a live operational forecast","Source influence is screening, not regulatory apportionment","Scenario estimates are non-causal"],"safety_result":"passed_replay_safety","overall_status":"completed","duration_ms":round((time.time()-started)*1000,2)}
    persist(package); return package
@router.get("/runs/{run_id}")
async def get_run(run_id: str):
    value=read(run_id)
    if not value: raise HTTPException(404,"Run not found")
    return value
@router.get("/runs")
async def runs(page: int=Query(1,ge=1), page_size: int=Query(20,ge=1,le=100), city: str|None=None, pollutant: str|None=None, status: str|None=None, mode: str|None=None, safety_result: str|None=None, run_id: str|None=None):
    values=list_runs()
    for key, wanted in (("city_id",city),("pollutant",pollutant),("overall_status",status),("mode",mode),("safety_result",safety_result)):
        if wanted: values=[value for value in values if value.get(key)==wanted]
    if run_id: values=[value for value in values if run_id.lower() in str(value.get("run_id", "")).lower()]
    start=(page-1)*page_size
    return {"total":len(values),"page":page,"page_size":page_size,"items":[compact(value) for value in values[start:start+page_size]],"mode":"historical_replay"}
@router.get("/runs/{run_id}/agents")
async def agents(run_id: str): return {"data":(await get_run(run_id))["agents"]}
@router.get("/runs/{run_id}/trace")
async def trace(run_id: str):
    value=await get_run(run_id); return {"run_id":value["run_id"],"mode":value["mode"],"agents":value["agents"],"safety_result":value["safety_result"],"limitations":value["limitations"]}
@router.get("/examples")
async def examples(): return {"data":load("intelligence_city_comparison.json"),"mode":"historical_replay"}
