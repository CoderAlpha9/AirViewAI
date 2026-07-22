import axios from "axios";
import type { Feature, Geometry, MultiPolygon, Polygon } from "geojson";

import { apiClient } from "./client";

export type Pollutant = "pm2_5" | "pm10";
export type Horizon = 24 | 48 | 72;
export type LivePanel =
  | "current"
  | "stations"
  | "forecast"
  | "map"
  | "source-intelligence"
  | "actions"
  | "advisory";

export interface ResolvedCity {
  city_id: string;
  name: string;
  state: string | null;
  latitude: number;
  longitude: number;
  bounds: [number, number, number, number];
  boundary_geojson?: Geometry | null;
  bounds_source: string;
  provider: string;
}

export interface LiveContext {
  city: ResolvedCity;
  pollutant: Pollutant;
  horizon: Horizon;
  issue_timestamp: string;
  snapshot_id: string;
  schema_version: string;
  generated_at_utc: string;
  data_freshness: { label: string; age_hours: number | null; timestamp_utc?: string };
  coverage_type: "station_corrected" | "model_based";
}

export interface CurrentConditions {
  value: number;
  timestamp_utc: string | null;
  provider: string;
  station_id: string | null;
  station_name: string | null;
  freshness: { label: string; age_hours: number | null };
  fallback: boolean;
  value_kind: "observed" | "modelled_current";
  aqi: number | null;
  category: string | null;
  colour: string | null;
}

export interface LiveStation {
  station_id: string;
  name: string;
  provider: string;
  latitude: number;
  longitude: number;
  distance_km: number | null;
  pollutants: Pollutant[];
  freshness: { label: string; age_hours: number | null };
  selection_score: number;
  latest: Partial<Record<Pollutant, { value: number; timestamp_utc: string | null }>>;
}

export interface LiveStationPanel {
  available_count: number;
  selected_count: number;
  stations: LiveStation[];
}

export interface LiveForecastPoint {
  timestamp_utc: string;
  prediction: number;
  cams: number;
  global_residual_correction: number;
  station_residual_correction: number;
  rolling_24h: number | null;
  aqi: number | null;
  category: string | null;
  colour: string | null;
}

export interface LiveForecast {
  status: "available" | "unavailable";
  points: LiveForecastPoint[];
  peak: {
    value: number;
    timestamp_utc: string;
    aqi: number | null;
    category: string | null;
    colour: string | null;
  } | null;
  priority: string;
  model: Record<string, unknown>;
  method: string;
}

export interface GridProperties {
  cell_id: string;
  center: [number, number];
  resolution_m: number;
  current: number | null;
  forecast: number | null;
  coverage_type: "station_corrected" | "model_based";
  confidence: number;
  planning_spatial_adjustment?: number;
  aqi: number | null;
  category: string | null;
  colour: string | null;
}

export interface LiveMap {
  type: "FeatureCollection";
  features: Array<Feature<Polygon | MultiPolygon, GridProperties>>;
  metadata: {
    city_id: string;
    resolution_m: number;
    cell_count: number;
    eligible_cell_count: number;
    truncated: boolean;
    bounds_source: string;
    clipped_to_boundary: boolean;
    layer_kind: "current";
    category_legend: Array<{ category: string; colour: string }>;
  };
  firms: Array<{
    latitude: number;
    longitude: number;
    timestamp_utc: string;
    fire_radiative_power?: number | null;
    distance_km?: number | null;
  }>;
  osm: Record<string, number | string | null>;
  planning_method?: string;
}

export interface LiveIntelligence {
  priority: string;
  confidence: number;
  firms_count: number;
  osm: Record<string, number | string | null>;
}

export interface LiveAction {
  priority: string;
  action: string;
}

export interface LiveAdvisory {
  status: "available" | "unavailable";
  category: string | null;
  message: string | null;
}

export interface PanelResponse<T> {
  context: LiveContext;
  data: T;
  provider_status: Record<string, { status: string; provider: string; fallback: boolean; timestamp_utc?: string | null }>;
}

export interface PanelDataMap {
  current: CurrentConditions | null;
  stations: LiveStationPanel;
  forecast: LiveForecast;
  map: LiveMap;
  "source-intelligence": LiveIntelligence;
  actions: LiveAction[];
  advisory: LiveAdvisory;
}

const panelPaths: Record<LivePanel, string> = {
  current: "/live/current",
  stations: "/live/stations",
  forecast: "/live/forecast",
  map: "/live/map",
  "source-intelligence": "/live/source-intelligence",
  actions: "/live/actions",
  advisory: "/live/advisory",
};

export async function searchIndianCities(query: string, signal?: AbortSignal): Promise<ResolvedCity[]> {
  const response = await apiClient.get<{ data: ResolvedCity[] }>("/live/cities/search", {
    params: { q: query },
    signal,
  });
  return response.data.data;
}

export async function getLivePanel<P extends LivePanel>(
  panel: P,
  params: { city: string; pollutant: Pollutant; horizon: Horizon },
  signal?: AbortSignal,
): Promise<PanelResponse<PanelDataMap[P]>> {
  const response = await apiClient.get<PanelResponse<PanelDataMap[P]>>(panelPaths[panel], {
    params,
    signal,
  });
  return response.data;
}

export function contextMatches(
  context: LiveContext,
  expected: { cityId?: string; cityName: string; pollutant: Pollutant; horizon: Horizon },
): boolean {
  const cityMatches = expected.cityId
    ? context.city.city_id === expected.cityId
    : context.city.name.localeCompare(expected.cityName, undefined, { sensitivity: "base" }) === 0;
  return cityMatches && context.pollutant === expected.pollutant && context.horizon === expected.horizon;
}

export function snapshotsMatch(...contexts: Array<LiveContext | undefined>): boolean {
  const ids = contexts.filter((context): context is LiveContext => Boolean(context)).map((context) => context.snapshot_id);
  return ids.length < 2 || ids.every((value) => value === ids[0]);
}

export function liveError(error: unknown): string {
  if (axios.isCancel(error)) return "";
  return "Live data is temporarily unavailable.";
}
