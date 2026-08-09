import { Client } from "@langchain/langgraph-sdk";

import { buildRequestHeaders } from "@/lib/api-key";

export function createClient(apiUrl: string, apiKey?: string | null) {
  const headers = buildRequestHeaders(apiKey);
  return new Client({
    apiKey: apiKey?.trim() || undefined,
    apiUrl,
    defaultHeaders: Object.keys(headers).length > 0 ? headers : undefined,
  });
}
