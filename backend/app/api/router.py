from fastapi import APIRouter

from app.api.routes import data, system

api_router = APIRouter()
api_router.include_router(system.router, tags=["system"])
api_router.include_router(data.router, tags=["data"])
