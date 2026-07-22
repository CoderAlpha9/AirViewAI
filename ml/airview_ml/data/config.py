from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Literal

ProfileName = Literal["smoke", "hackathon", "full-india"]


@dataclass(frozen=True)
class EligibilityThresholds:
    minimum_history_days: int = 30
    minimum_hourly_completeness: float = 0.70
    minimum_hyperlocal_stations: int = 2
    recency_hours: int = 48


@dataclass(frozen=True)
class PipelineProfile:
    name: ProfileName
    start_date: date
    end_date: date
    cities: tuple[str, ...]
    include_sources: tuple[str, ...]
    max_workers: int = 3
    grid_resolution_m: int = 1_000


PROFILES: dict[ProfileName, PipelineProfile] = {
    "smoke": PipelineProfile(
        name="smoke",
        start_date=date(2026, 7, 1),
        end_date=date(2026, 7, 2),
        cities=("delhi-ncr", "mumbai", "bengaluru"),
        include_sources=("cpcb", "openaq", "weather", "osm", "ghsl", "firms", "sentinel5p"),
        max_workers=2,
    ),
    "hackathon": PipelineProfile(
        name="hackathon",
        start_date=date(2024, 1, 1),
        end_date=date.today(),
        cities=(),
        include_sources=("cpcb", "openaq", "weather", "osm", "ghsl", "firms", "sentinel5p"),
        max_workers=3,
    ),
    "full-india": PipelineProfile(
        name="full-india",
        start_date=date(2024, 1, 1),
        end_date=date.today(),
        cities=(),
        include_sources=("cpcb", "openaq", "weather", "osm", "ghsl", "firms", "sentinel5p"),
        max_workers=4,
    ),
}


@dataclass
class PipelineSettings:
    repository_root: Path
    cache_dir: Path | None = None
    output_dir: Path | None = None
    thresholds: EligibilityThresholds = field(default_factory=EligibilityThresholds)
    request_timeout_seconds: float = 30.0
    request_limit: int = 100

    def __post_init__(self) -> None:
        self.repository_root = self.repository_root.resolve()
        self.cache_dir = (self.cache_dir or self.repository_root / "data" / "raw").resolve()
        self.output_dir = (self.output_dir or self.repository_root / "data" / "processed").resolve()

    @property
    def reports_dir(self) -> Path:
        return self.repository_root / "outputs" / "reports"


def find_repository_root(start: Path | None = None) -> Path:
    current = (start or Path.cwd()).resolve()
    for candidate in (current, *current.parents):
        if (candidate / "ml" / "pyproject.toml").is_file() and (candidate / "data").is_dir():
            return candidate
    raise RuntimeError("Could not locate the AirView AI repository root")
