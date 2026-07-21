from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class AirViewSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Coordinates(AirViewSchema):
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)


class City(AirViewSchema):
    id: str
    name: str
    state: str
    country: str = "India"
    timezone: str = "Asia/Kolkata"


class Ward(AirViewSchema):
    id: str
    city_id: str
    name: str
    code: str | None = None
    centroid: Coordinates | None = None
    population: int | None = Field(default=None, ge=0)


class MonitoringStation(AirViewSchema):
    id: str
    city_id: str
    ward_id: str | None = None
    name: str
    location: Coordinates
    operator: str | None = None
    station_type: str | None = None
    is_active: bool = True


class AirQualityObservation(AirViewSchema):
    station_id: str
    observed_at: datetime
    aqi: float | None = Field(default=None, ge=0)
    pm25_ug_m3: float | None = Field(default=None, ge=0)
    pm10_ug_m3: float | None = Field(default=None, ge=0)
    no2_ug_m3: float | None = Field(default=None, ge=0)
    so2_ug_m3: float | None = Field(default=None, ge=0)
    co_mg_m3: float | None = Field(default=None, ge=0)
    o3_ug_m3: float | None = Field(default=None, ge=0)
    source: str
    quality_flag: str | None = None


class WeatherObservation(AirViewSchema):
    location_id: str
    observed_at: datetime
    temperature_c: float | None = None
    relative_humidity_pct: float | None = Field(default=None, ge=0, le=100)
    wind_speed_m_s: float | None = Field(default=None, ge=0)
    wind_direction_deg: float | None = Field(default=None, ge=0, lt=360)
    precipitation_mm: float | None = Field(default=None, ge=0)
    pressure_hpa: float | None = Field(default=None, ge=0)
    boundary_layer_height_m: float | None = Field(default=None, ge=0)
    source: str


class AQIForecast(AirViewSchema):
    location_id: str
    issued_at: datetime
    valid_at: datetime
    horizon_hours: int = Field(ge=1, le=72)
    predicted_aqi: float = Field(ge=0)
    lower_bound: float | None = Field(default=None, ge=0)
    upper_bound: float | None = Field(default=None, ge=0)
    model_version: str


class SourceCategory(str, Enum):
    TRAFFIC = "traffic"
    CONSTRUCTION = "construction"
    INDUSTRIAL = "industrial"
    WASTE_BURNING = "waste_burning"
    RESIDENTIAL = "residential"
    DUST = "dust"
    REGIONAL_TRANSPORT = "regional_transport"
    OTHER = "other"


class SourceContribution(AirViewSchema):
    category: SourceCategory
    contribution_pct: float = Field(ge=0, le=100)
    confidence: float | None = Field(default=None, ge=0, le=1)


class PollutionSourceAttribution(AirViewSchema):
    location_id: str
    estimated_at: datetime
    pollutant: str
    contributions: list[SourceContribution]
    method: str
    model_version: str


class InterventionPriority(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class InterventionRecommendation(AirViewSchema):
    id: str
    location_id: str
    created_at: datetime
    title: str
    rationale: str
    recommended_actions: list[str]
    priority: InterventionPriority
    responsible_agencies: list[str] = Field(default_factory=list)
    expected_impact: str | None = None
    evidence_refs: list[str] = Field(default_factory=list)


class CitizenAdvisory(AirViewSchema):
    id: str
    location_id: str
    issued_at: datetime
    valid_until: datetime
    language: str
    risk_level: str
    headline: str
    guidance: list[str]
    audience_groups: list[str] = Field(default_factory=list)


class VulnerableLocationType(str, Enum):
    HOSPITAL = "hospital"
    SCHOOL = "school"
    ELDER_CARE = "elder_care"
    CHILD_CARE = "child_care"
    OUTDOOR_WORK_ZONE = "outdoor_work_zone"
    OTHER = "other"


class VulnerableLocation(AirViewSchema):
    id: str
    city_id: str
    ward_id: str | None = None
    name: str
    location: Coordinates
    location_type: VulnerableLocationType
    estimated_people_exposed: int | None = Field(default=None, ge=0)
    data_source: str
