export interface Coordinates {
  latitude: number;
  longitude: number;
}

export interface City {
  id: string;
  name: string;
  state: string;
  country: string;
  timezone: string;
}

export interface Ward {
  id: string;
  city_id: string;
  name: string;
  code?: string;
  centroid?: Coordinates;
  population?: number;
}

export interface MonitoringStation {
  id: string;
  city_id: string;
  ward_id?: string;
  name: string;
  location: Coordinates;
  operator?: string;
  station_type?: string;
  is_active: boolean;
}

export interface AirQualityObservation {
  station_id: string;
  observed_at: string;
  aqi?: number;
  pm25_ug_m3?: number;
  pm10_ug_m3?: number;
  no2_ug_m3?: number;
  so2_ug_m3?: number;
  co_mg_m3?: number;
  o3_ug_m3?: number;
  source: string;
  quality_flag?: string;
}

export interface WeatherObservation {
  location_id: string;
  observed_at: string;
  temperature_c?: number;
  relative_humidity_pct?: number;
  wind_speed_m_s?: number;
  wind_direction_deg?: number;
  precipitation_mm?: number;
  pressure_hpa?: number;
  boundary_layer_height_m?: number;
  source: string;
}

export interface AQIForecast {
  location_id: string;
  issued_at: string;
  valid_at: string;
  horizon_hours: number;
  predicted_aqi: number;
  lower_bound?: number;
  upper_bound?: number;
  model_version: string;
}

export type PollutionSourceCategory =
  | "traffic"
  | "construction"
  | "industrial"
  | "waste_burning"
  | "residential"
  | "dust"
  | "regional_transport"
  | "other";

export interface PollutionSourceAttribution {
  location_id: string;
  estimated_at: string;
  pollutant: string;
  contributions: Array<{
    category: PollutionSourceCategory;
    contribution_pct: number;
    confidence?: number;
  }>;
  method: string;
  model_version: string;
}

export interface InterventionRecommendation {
  id: string;
  location_id: string;
  created_at: string;
  title: string;
  rationale: string;
  recommended_actions: string[];
  priority: "low" | "medium" | "high" | "critical";
  responsible_agencies: string[];
  expected_impact?: string;
  evidence_refs: string[];
}

export interface CitizenAdvisory {
  id: string;
  location_id: string;
  issued_at: string;
  valid_until: string;
  language: string;
  risk_level: string;
  headline: string;
  guidance: string[];
  audience_groups: string[];
}

export type VulnerableLocationType =
  | "hospital"
  | "school"
  | "elder_care"
  | "child_care"
  | "outdoor_work_zone"
  | "other";

export interface VulnerableLocation {
  id: string;
  city_id: string;
  ward_id?: string;
  name: string;
  location: Coordinates;
  location_type: VulnerableLocationType;
  estimated_people_exposed?: number;
  data_source: string;
}

export interface HealthResponse {
  status: "ok";
  service: string;
  version: string;
}

export interface ProjectInfo {
  name: string;
  problem_statement: string;
  implementation_stage: string;
  planned_modules: string[];
}
