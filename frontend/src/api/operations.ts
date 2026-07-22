import axios, { AxiosError } from "axios";

import { apiClient } from "./client";

export type Pollutant = "pm2_5" | "pm10";
export type Language = "en" | "hi" | "pa";

export interface CityConfig {
  city_id: string;
  name: string;
  state: string;
  station_id: string;
  station_name: string;
  openaq_location_id: number;
  latitude: number;
  longitude: number;
  pollutants: Pollutant[];
  live_capable: boolean;
  forecast_horizons: Array<24 | 48 | 72>;
  requested_city_name?: string;
  coverage_note?: string | null;
}

export interface CurrentObservation {
  value: number;
  timestamp_utc: string;
  source: string;
  value_kind: "observed" | "modelled_current" | "historical";
  freshness: "recent" | "delayed" | "historical";
}

export interface ForecastPoint {
  timestamp_utc: string;
  prediction: number;
  provider_baseline: number | null;
  actual?: number | null;
  lower: number;
  upper: number;
  rolling_24h: number | null;
  aqi: number | null;
  aqi_category: string | null;
  weather: {
    wind_speed?: number | null;
    wind_direction?: number | null;
    boundary_layer_height?: number | null;
    precipitation?: number | null;
  };
}

export interface ForecastEndpoint {
  horizon: number;
  prediction: number;
  model: string;
  scope: string;
  feature_completeness: number;
}

export interface ForecastResult {
  issue_timestamp: string;
  pollutant: Pollutant;
  pollutant_label: string;
  unit: string;
  horizon_hours: number;
  points: ForecastPoint[];
  peak: {
    value: number;
    timestamp_utc: string;
    aqi: number | null;
    category: string | null;
  };
  endpoints: ForecastEndpoint[];
  method: string;
  interval_method: string;
}

export interface SourceRanking {
  category_id: string;
  label: string;
  influence: number | null;
  confidence: number;
  evidence: string[];
  availability: "available" | "unavailable";
}

export interface InterventionAction {
  rank: number;
  source_category: string;
  action: string;
  agency: string;
  response_time: string;
  cost_tier: string;
  estimated_sensitivity_range_percent: [number, number] | null;
  caveat: string;
}

export interface GridCell {
  cell_id: string;
  center: { latitude: number; longitude: number };
  bounds: [[number, number], [number, number]];
  forecast_peak: number;
  aqi: number | null;
  category: string | null;
  resolution_m: number;
  method: string;
}

export interface FirmsMarker {
  latitude: number;
  longitude: number;
  timestamp_utc: string;
  satellite?: string | null;
  instrument?: string | null;
  confidence?: string | number | null;
  fire_radiative_power?: number | null;
  distance_km?: number | null;
}

export interface NetworkCitySummary {
  city_id: string;
  city_name: string;
  state: string;
  current: number | null;
  peak_24h: number | null;
  category: string | null;
  priority: string;
  mode: "live_numerical_outlook";
  timestamp_utc: string | null;
}

export interface NetworkOverview {
  generated_at_utc: string;
  pollutant: "pm2_5";
  unit: string;
  cities: NetworkCitySummary[];
  methodology: string;
}

export interface OperationsDashboard {
  mode: "operational_forecast";
  live: boolean;
  generated_at_utc: string;
  city: CityConfig;
  current: CurrentObservation;
  forecast: ForecastResult;
  weather: {
    current?: Record<string, number | string | null>;
    source?: string;
  };
  map: {
    station: { latitude: number; longitude: number; name: string };
    grid: GridCell[];
    firms: FirmsMarker[];
    hotspot: { latitude: number; longitude: number; label: string } | null;
    wind: { speed?: number | null; direction?: number | null };
    osm_available: boolean;
    grid_methodology?: string;
  };
  intelligence: {
    rankings: SourceRanking[];
    priority: string;
    confidence: number;
    methodology: string;
    osm_available: boolean;
    firms_event_count: number;
  };
  actions: InterventionAction[];
  advisory: {
    language: Language;
    severity: string;
    headline: string;
    summary: string;
    actions: string[];
    disclaimer: string;
  };
  provider_status: Record<string, string>;
  coverage_note?: string | null;
  disclaimer: string;
}

export async function getOperationalCities(
  signal?: AbortSignal,
): Promise<CityConfig[]> {
  const response = await apiClient.get<{ data: CityConfig[] }>(
    "/operations/cities",
    { signal },
  );
  return response.data.data;
}

export async function getOperationsDashboard(
  params: {
    cityId: string;
    pollutant: Pollutant;
    horizon: 24 | 48 | 72;
    language: Language;
  },
  signal?: AbortSignal,
): Promise<OperationsDashboard> {
  const response = await apiClient.get<OperationsDashboard>(
    "/operations/dashboard",
    {
      params: {
        city_id: params.cityId,
        pollutant: params.pollutant,
        horizon: params.horizon,
        language: params.language,
      },
      signal,
    },
  );
  return response.data;
}

export async function getNetworkOverview(
  signal?: AbortSignal,
): Promise<NetworkOverview> {
  const response = await apiClient.get<NetworkOverview>("/operations/network", { signal });
  return response.data;
}

export function operationsError(error: unknown): string {
  if (axios.isCancel(error)) return "";
  const axiosError = error as AxiosError<{ detail?: string }>;
  if (!axiosError.response) {
    return "The AirView service is not reachable. Check that the demo service is running, then retry.";
  }
  if (axiosError.response.status === 504) {
    return "Live data providers are taking longer than expected. Retry shortly.";
  }
  return (
    axiosError.response.data?.detail ??
    "AirView could not assemble this dashboard. Please retry."
  );
}
