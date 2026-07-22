import { apiClient } from "./client";

export interface NetworkCitySummary {
  city_id: string;
  city_name: string;
  state: string;
  value_24h: number | null;
  aqi: number | null;
  category: string | null;
  colour: string | null;
  priority: string;
  mode: "fixed_next_24h_pm2_5_outlook";
  pollutant: "pm2_5";
  horizon: 24;
  issue_timestamp: string | null;
  valid_timestamp: string | null;
  snapshot_id: string | null;
}

export interface NetworkOverview {
  generated_at_utc: string;
  pollutant: "pm2_5";
  unit: string;
  cities: NetworkCitySummary[];
  methodology: string;
}

export async function getNetworkOverview(signal?: AbortSignal): Promise<NetworkOverview> {
  const response = await apiClient.get<NetworkOverview>("/operations/network", { signal });
  return response.data;
}
