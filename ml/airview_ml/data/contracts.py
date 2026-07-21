from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any, Literal

ValueKind = Literal["observed", "provider_derived", "airview_derived", "modelled", "proxy"]
SourceStatus = Literal["success", "partial", "skipped", "failed", "credentials_required", "not_ready"]


@dataclass(frozen=True)
class CityRecord:
    id: str
    name: str
    state: str
    country_code: str = "IN"
    latitude: float | None = None
    longitude: float | None = None
    source: str = "configured_major_city_registry"


@dataclass(frozen=True)
class DataProvenance:
    id: str
    source: str
    official_url: str
    retrieved_at_utc: datetime
    licence: str | None
    processing_steps: list[str]
    value_kind: ValueKind


@dataclass(frozen=True)
class AirQualityRecord:
    source: str
    provider: str
    country_code: str
    state: str | None
    city_id: str | None
    city_name: str | None
    station_id: str | None
    station_name: str | None
    sensor_id: str | None
    latitude: float | None
    longitude: float | None
    pollutant: str
    value_original: float | None
    unit_original: str | None
    value_canonical: float | None
    unit_canonical: str | None
    observed_at_utc: datetime | None
    observed_at_local: str | None
    source_timezone: str | None
    retrieval_time_utc: datetime
    is_valid: bool
    quality_flags: list[str] = field(default_factory=list)
    licence: str | None = None
    provenance_id: str | None = None


@dataclass(frozen=True)
class DataQualityIssue:
    code: str
    severity: Literal["info", "warning", "error"]
    message: str
    source: str | None = None
    record_id: str | None = None
    field: str | None = None


@dataclass(frozen=True)
class SourceResult:
    source: str
    status: SourceStatus
    retrieved_at_utc: datetime
    row_count: int = 0
    cache_path: str | None = None
    date_range: dict[str, str | None] = field(default_factory=dict)
    geographic_coverage: str = "not available"
    variables: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    error: str | None = None
    value_kind: ValueKind = "observed"
    official_url: str = ""
    credential_requirement: str = "none"
    licence: str | None = None
    processing_steps: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class CityReadinessScore:
    city_id: str
    score: float
    national_display_eligible: bool
    forecast_eligible: bool
    hyperlocal_eligible: bool
    intervention_intelligence_eligible: bool
    components: dict[str, float]
    exclusion_reasons: list[str]


def serialise(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if hasattr(value, "__dataclass_fields__"):
        return {key: serialise(item) for key, item in asdict(value).items()}
    if isinstance(value, dict):
        return {key: serialise(item) for key, item in value.items()}
    if isinstance(value, list):
        return [serialise(item) for item in value]
    return value
