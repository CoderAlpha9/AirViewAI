import { apiClient } from "./client";

export interface DataReport<T = unknown> {
  status: "ready" | "not_ready" | "not_found";
  data?: T;
  message?: string;
}

export async function getDataReport<T>(path: string): Promise<DataReport<T>> {
  const response = await apiClient.get<DataReport<T>>(path);
  return response.data;
}
