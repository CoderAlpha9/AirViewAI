import json
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query

router = APIRouter(prefix="/forecast")


def root() -> Path:
    return Path(__file__).resolve().parents[4]


@router.get("/status")
async def status() -> dict:
    registry = root() / "models" / "forecasting" / "registry.json"
    if not registry.is_file():
        return {"status": "not_ready", "message": "No forecasting artifacts are available."}
    latest = root() / "data" / "processed" / "india" / "latest_snapshot.json"
    return {"status": "ready", "mode": "historical_replay", "operational_ready": False, "message": "Historical data ends in March 2026; operational forecasts are refused until fresh observations are available.", "models": len(json.loads(registry.read_text(encoding="utf-8"))), "latest_snapshot": json.loads(latest.read_text(encoding="utf-8")) if latest.is_file() else None}


@router.get("/models")
async def models() -> dict:
    path = root() / "models" / "forecasting" / "registry.json"
    return {"status": "ready", "data": json.loads(path.read_text(encoding="utf-8"))} if path.is_file() else {"status": "not_ready"}


@router.get("/metrics")
async def metrics() -> dict:
    path = root() / "outputs" / "reports" / "forecast_test_metrics.json"
    return {"status": "ready", "data": json.loads(path.read_text(encoding="utf-8"))} if path.is_file() else {"status": "not_ready"}


@router.get("/latest")
async def latest() -> dict:
    return {"status": "stale", "mode": "operational", "message": "Operational forecast rejected: latest available observations are historical, not fresh."}


@router.get("/replay")
async def replay(city_id: str = "delhi-ncr", pollutant: str = Query("pm2_5", pattern="^(pm2_5|pm10)$"), horizon: int = Query(24, ge=1, le=72)) -> dict:
    frame_path = root() / "data" / "processed" / "india" / "station_hourly_features.parquet"
    if not frame_path.is_file():
        raise HTTPException(503, "Forecasting input is unavailable")
    import pandas as pd
    frame = pd.read_parquet(frame_path)
    frame["timestamp_utc"] = pd.to_datetime(frame["timestamp_utc"], utc=True)
    row = frame[(frame.city_id == city_id) & frame[pollutant].notna()].sort_values("timestamp_utc").iloc[-horizon-1]
    points=[]
    for step in range(1,horizon+1):
        actual=frame[(frame.station_id==row.station_id)&(frame.timestamp_utc==row.timestamp_utc+pd.Timedelta(hours=step))][pollutant]
        points.append({"timestamp_utc":row.timestamp_utc+pd.Timedelta(hours=step),"prediction":float(row[pollutant]),"baseline":float(row[pollutant]),"lower":max(0,float(row[pollutant])*0.65),"upper":float(row[pollutant])*1.35,"actual":float(actual.iloc[0]) if len(actual) else None})
    return {"status":"ready","mode":"historical_replay","city_id":city_id,"station_id":row.station_id,"pollutant":pollutant,"issue_time":row.timestamp_utc,"points":points,"warning":"Replay only; not a current live forecast."}
