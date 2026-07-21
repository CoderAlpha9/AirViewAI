import type { HealthResponse, ProjectInfo } from "../types/domain";
import { apiClient } from "./client";

export async function getHealth(signal?: AbortSignal): Promise<HealthResponse> {
  const response = await apiClient.get<HealthResponse>("/health", { signal });
  return response.data;
}

export async function getProjectInfo(signal?: AbortSignal): Promise<ProjectInfo> {
  const response = await apiClient.get<ProjectInfo>("/project-info", { signal });
  return response.data;
}

