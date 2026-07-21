from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    project_name: str = "AirView AI"
    service_name: str = "AirView AI API"
    problem_statement: str = (
        "ET AI Hackathon 2.0, Problem Statement 5: AI-Powered Urban Air Quality "
        "Intelligence for Smart City Intervention"
    )
    environment: str = "development"
    api_prefix: str = "/api"
    api_host: str = "127.0.0.1"
    api_port: int = 8000
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    log_level: str = "INFO"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="AIRVIEW_",
        extra="ignore",
    )

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()

