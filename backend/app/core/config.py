from functools import lru_cache
from pathlib import Path

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

_BACKEND_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    project_name: str = "AirView AI"
    service_name: str = "AirView AI API"
    problem_statement: str = (
        "ET AI Hackathon 2.0, Problem Statement 5: AI-Powered Urban Air Quality "
        "Intelligence for Smart City Intervention"
    )
    environment: str = "production"
    api_prefix: str = "/api"
    api_host: str = "127.0.0.1"
    api_port: int = 8000
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    log_level: str = "INFO"
    openaq_api_key: str | None = Field(default=None, validation_alias=AliasChoices("OPENAQ_API_KEY", "AIRVIEW_OPENAQ_API_KEY"))
    data_gov_in_api_key: str | None = Field(default=None, validation_alias=AliasChoices("DATA_GOV_IN_API_KEY", "AIRVIEW_DATA_GOV_IN_API_KEY"))
    nasa_firms_map_key: str | None = Field(default=None, validation_alias=AliasChoices("NASA_FIRMS_MAP_KEY", "AIRVIEW_NASA_FIRMS_MAP_KEY"))
    copernicus_client_id: str | None = Field(default=None, validation_alias=AliasChoices("COPERNICUS_CLIENT_ID", "AIRVIEW_COPERNICUS_CLIENT_ID"))
    copernicus_client_secret: str | None = Field(default=None, validation_alias=AliasChoices("COPERNICUS_CLIENT_SECRET", "AIRVIEW_COPERNICUS_CLIENT_SECRET"))
    live_provider_timeout_seconds: int = 20
    operational_cache_seconds: int = 600

    model_config = SettingsConfigDict(
        env_file=(_BACKEND_DIR / ".env", _BACKEND_DIR.parent / ".env"),
        env_prefix="AIRVIEW_",
        extra="ignore",
    )

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
