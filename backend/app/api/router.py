from fastapi import APIRouter

from app.api.routes import (
    copilot,
    dynamic,
    operations,
    system,
)

api_router = APIRouter()
api_router.include_router(system.router, tags=["system"])
api_router.include_router(operations.router, tags=["operations"])
api_router.include_router(dynamic.router, tags=["live cities"])
api_router.include_router(copilot.router, tags=["copilot"])
