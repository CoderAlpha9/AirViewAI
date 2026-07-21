from fastapi import APIRouter

from app import __version__
from app.core.config import get_settings
from app.schemas.project import HealthResponse, ProjectInfoResponse

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    settings = get_settings()
    return HealthResponse(status="ok", service=settings.service_name, version=__version__)


@router.get("/project-info", response_model=ProjectInfoResponse)
async def project_info() -> ProjectInfoResponse:
    settings = get_settings()
    return ProjectInfoResponse(
        name=settings.project_name,
        problem_statement=settings.problem_statement,
        implementation_stage="Foundation: architecture, contracts, and health integration",
        planned_modules=[
            "Data ingestion and validation",
            "Spatial-temporal feature engineering",
            "AQI forecasting",
            "Hotspot detection",
            "Pollution source attribution",
            "Vulnerable-population analysis",
            "Enforcement prioritisation",
            "Intervention impact estimation",
            "Multilingual citizen advisories",
            "Multi-city command dashboard",
            "Model evaluation and monitoring",
        ],
    )

