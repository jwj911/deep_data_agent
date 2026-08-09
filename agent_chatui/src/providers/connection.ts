import { AGENT_API_URL, ASSISTANT_ID } from "@/config";

export interface ConnectionConfig {
  apiUrl: string;
  assistantId: string;
}

export function resolveConnectionConfig(
  apiUrl?: string | null,
  assistantId?: string | null,
): ConnectionConfig {
  return {
    apiUrl: normalizeApiUrl(apiUrl?.trim() || AGENT_API_URL),
    assistantId: assistantId?.trim() || ASSISTANT_ID,
  };
}

function normalizeApiUrl(apiUrl: string): string {
  return apiUrl.replace(/\/+$/, "");
}
