from fastapi import APIRouter

from app.services.data_status import city_or_not_ready, latest_or_not_ready, report_or_not_ready

router = APIRouter(prefix="/data")


@router.get("/sources")
async def sources() -> dict:
    return report_or_not_ready("sources")


@router.get("/coverage")
async def coverage() -> dict:
    return report_or_not_ready("coverage")


@router.get("/quality")
async def quality() -> dict:
    return report_or_not_ready("quality")


@router.get("/cities")
async def cities() -> dict:
    return report_or_not_ready("cities")


@router.get("/cities/{city_id}")
async def city(city_id: str) -> dict:
    return city_or_not_ready(city_id)


@router.get("/stations")
async def stations() -> dict:
    return report_or_not_ready("stations")


@router.get("/latest")
async def latest() -> dict:
    return latest_or_not_ready()


@router.get("/readiness")
async def readiness() -> dict:
    return report_or_not_ready("readiness")


@router.get("/pipeline/latest-run")
async def latest_pipeline_run() -> dict:
    return report_or_not_ready("pipeline")
