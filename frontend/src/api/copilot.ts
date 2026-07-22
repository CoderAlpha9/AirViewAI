import axios from "axios";

import type { Horizon, Pollutant } from "./live";
import { apiClient } from "./client";

export interface CopilotHistoryMessage {
  role: "user" | "assistant";
  content: string;
}

export interface CopilotRequest {
  message: string;
  city_id: string;
  pollutant: Pollutant;
  horizon: Horizon;
  snapshot_id: string;
  session_id: string;
  language?: string;
  history: CopilotHistoryMessage[];
}

export interface CopilotReply {
  answer: string;
  evidence: string[];
  data_status: "station-corrected" | "model-based" | "partial";
  limitations: string[];
  suggested_questions: string[];
}

export interface CopilotStatus {
  enabled: boolean;
  provider: string;
  model: string;
  configured: boolean;
}

export async function getCopilotStatus(signal?: AbortSignal): Promise<CopilotStatus> {
  const response = await apiClient.get<CopilotStatus>("/copilot/status", { signal });
  return response.data;
}

export async function askCopilot(
  request: CopilotRequest,
  signal?: AbortSignal,
): Promise<CopilotReply> {
  const response = await apiClient.post<CopilotReply>("/copilot/chat", request, { signal });
  return response.data;
}

export function copilotError(error: unknown): string {
  if (axios.isCancel(error)) return "";
  if (axios.isAxiosError(error) && error.response?.status === 409) {
    return "The dashboard context changed. Please retry with the current snapshot.";
  }
  if (axios.isAxiosError(error) && error.response?.status === 429) {
    return "Ask AirView is busy. Please wait briefly and try again.";
  }
  return "Ask AirView is temporarily unavailable. Please try again.";
}
