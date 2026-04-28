import { Client } from "@langchain/langgraph-sdk";
import { getAuthToken } from "@/lib/api-key";

export function createClient(apiUrl: string, apiKey: string | undefined) {
  const token = getAuthToken();
  const headers: Record<string, string> = {};
  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }

  return new Client({
    apiKey,
    apiUrl,
    defaultHeaders: Object.keys(headers).length > 0 ? headers : undefined,
  });
}