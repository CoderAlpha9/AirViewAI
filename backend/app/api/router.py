from fastapi import APIRouter

from app.api.routes import data, forecast, intelligence, system

api_router = APIRouter()
api_router.include_router(system.router, tags=["system"])
api_router.include_router(data.router, tags=["data"])
api_router.include_router(forecast.router, tags=["forecast"])
api_router.include_router(intelligence.router, tags=["intelligence"])
