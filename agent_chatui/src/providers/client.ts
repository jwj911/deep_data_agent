import { Client } from "@langchain/langgraph-sdk";

import { buildAgentAuthHeaders } from "@/lib/api-key";

export function createClient(apiUrl: string) {
  const headers = buildAgentAuthHeaders();
  return new Client({
    apiUrl,
    defaultHeaders: Object.keys(headers).length > 0 ? headers : undefined,
  });
}
