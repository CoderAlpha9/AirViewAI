from fastapi import APIRouter

from app.api.routes import (
    advisories,
    dashboard,
    data,
    forecast,
    intelligence,
    orchestration,
    system,
)

api_router = APIRouter()
api_router.include_router(system.router, tags=["system"])
api_router.include_router(data.router, tags=["data"])
api_router.include_router(forecast.router, tags=["forecast"])
api_router.include_router(intelligence.router, tags=["intelligence"])
api_router.include_router(advisories.router, tags=["advisories"])
api_router.include_router(orchestration.router, tags=["orchestration"])
api_router.include_router(dashboard.router, tags=["dashboard"])
