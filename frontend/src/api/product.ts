import { AxiosError } from "axios";

import { apiClient } from "./client";

export type Mode = "historical_replay" | "operational";
export type Priority = { city_id: string; station_id: string; timestamp_utc: string; priority_tier: string; confidence: number; source_category: string; recommended_inspection: string };
export type DashboardSummary = { mode: Mode; city_id: string; priority: Priority; hotspots: Array<Record<string, unknown>>; scenarios: Array<Record<string, unknown>>; limitations: string[] };
export type Advisory = { mode: Mode; city_id: string; station_id: string; issue_timestamp: string; headline: string; severity: string; rendered_text: string; confidence: number; disclaimer: string; warnings: string[] };
export type Agent = { agent_name: string; status: string; duration_ms: number; evidence_references: string[]; warnings: string[]; skipped_reason?: string | null };
export type Run = { run_id: string; mode: Mode; city_id: string; station_id: string; issue_timestamp: string; pollutant: string; horizon: number; priority: Priority; agents: Agent[]; limitations: string[]; safety_result: string };

export type Pollutant = "pm2_5" | "pm10";
export type ForecastRequest = { cityId: string; pollutant: Pollutant; horizon: 24 | 48 | 72 };
export type ForecastTrajectoryPoint = { timestamp_utc: string; prediction: number | null; persistence: number | null; lower: number | null; upper: number | null; actual: number | null };
export type ForecastAvailability = { actual: boolean; prediction: boolean; persistence: boolean; uncertainty: boolean };
export type DashboardForecast = { mode: "historical_replay"; city_id: string; station_id: string; issue_timestamp: string; pollutant: Pollutant; horizon: number; unit: string; points: ForecastTrajectoryPoint[]; model: string; limitations: string[] };
export type MapRequest = { cityId: string; firmsLookbackHours?: number; firmsLimit?: number };
export type Coordinate = { latitude: number; longitude: number };
export type StationMarker = Coordinate & { id: string };
export type HotspotMarker = { city_id: string; station_id: string; timestamp_utc: string; pollutant: string; severity: number; source_category: string; confidence: number; priority_tier: string; recommended_inspection: string; hotspot_type: string; limitations: string[] };
export type FirmsMarker = Coordinate & { timestamp_utc: string; satellite: string | null; instrument: string | null; confidence: string | number | null; fire_radiative_power: number | null; distance_km: number | null };
export type OsmEvidence = Coordinate & { osm_feature_available: boolean; traffic_emission_pressure_proxy?: number | null; industrial_activity_proxy?: number | null; construction_activity_proxy?: number | null; waste_activity_proxy?: number | null; vulnerable_location_proxy?: number | null; railway_proxy?: number | null; licence?: string | null };
export type WindContext = { speed: number | null; direction: number | null };
export type DashboardMap = { mode: "historical_replay"; city_id: string; issue_timestamp: string; station: StationMarker | null; hotspot: HotspotMarker | null; firms_markers: FirmsMarker[]; osm_features: OsmEvidence[]; wind: WindContext; availability: { firms: boolean; osm: boolean }; returned_firms_count: number; total_eligible_firms_count: number; truncated: boolean; limitations: string[] };

export function apiError(error: unknown): string {
  if (error instanceof AxiosError) return typeof error.response?.data?.detail === "string" ? error.response.data.detail : error.message;
  return "The replay service could not be reached.";
}
export function forecastAvailability(data: DashboardForecast): ForecastAvailability {
  return { actual: data.points.some((point) => point.actual !== null), prediction: data.points.some((point) => point.prediction !== null), persistence: data.points.some((point) => point.persistence !== null), uncertainty: data.points.some((point) => point.lower !== null || point.upper !== null) };
}
export async function dashboardSummary(cityId: string, signal?: AbortSignal) { return (await apiClient.get<DashboardSummary>("/dashboard/summary", { params: { city_id: cityId }, signal })).data; }
export async function pilotCities(signal?: AbortSignal) { return (await apiClient.get<{ data: Array<{ city_id: string; station_ids: string[] }> }>("/dashboard/pilot-cities", { signal })).data; }
export async function advisory(cityId: string, language: string, format: string, signal?: AbortSignal) { return (await apiClient.get<Advisory>("/advisories/generate", { params: { city_id: cityId, language, format }, signal })).data; }
export async function runWorkflow(cityId: string, pollutant: string, horizon: number, language: string) { return (await apiClient.post<Run>("/orchestration/run", undefined, { params: { city_id: cityId, pollutant, horizon, language } })).data; }
export async function getDashboardForecast(request: ForecastRequest, signal?: AbortSignal) { return (await apiClient.get<DashboardForecast>("/dashboard/forecast", { params: { city_id: request.cityId, pollutant: request.pollutant, horizon: request.horizon }, signal })).data; }
export async function getDashboardMap(request: MapRequest, signal?: AbortSignal) { return (await apiClient.get<DashboardMap>("/dashboard/map", { params: { city_id: request.cityId, firms_lookback_hours: request.firmsLookbackHours ?? 24, firms_limit: request.firmsLimit ?? 100 }, signal })).data; }
export async function runs() { return (await apiClient.get<{ data: Run[] }>("/orchestration/runs")).data; }
export type DemoPreset = { preset_id: string; label: string; city_id: string; city_name: string; station_id: string; pollutant: Pollutant; issue_timestamp: string; horizon: 24 | 48 | 72; language: string; audience: string; format: string; scenario_strength: string; case_type: string; mode: Mode; evidence: Record<string, boolean>; provenance: string[] };
export type AuditRun = { run_id: string; city_id: string; station_id: string; pollutant: string; horizon: number; issue_timestamp: string; mode: Mode; safety_result: string; created_at_utc: string; overall_status: string; duration_ms: number };
export async function demoPresets(signal?: AbortSignal) { return (await apiClient.get<{ data: DemoPreset[]; total: number }>("/dashboard/demo-presets", { signal })).data; }
export async function auditRuns(params: Record<string, string | number> = {}, signal?: AbortSignal) { return (await apiClient.get<{ total: number; items: AuditRun[] }>("/orchestration/runs", { params, signal })).data; }
export async function auditRun(runId: string, signal?: AbortSignal) { return (await apiClient.get<Run & { created_at_utc: string; overall_status: string; advisory: Record<string, string> }>(`/orchestration/runs/${runId}`, { signal })).data; }
export function exportUrl(runId: string, format: "json" | "html") { return `${apiClient.defaults.baseURL}/dashboard/export/${runId}?format=${format}`; }
