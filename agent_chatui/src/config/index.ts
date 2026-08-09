/**
 * Browser-accessible LangGraph deployment URL.
 *
 * NEXT_PUBLIC_API_URL is embedded into the static frontend at build time, so
 * it must not use a hostname that is only resolvable inside Docker.
 */
export const AGENT_API_URL =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:2024";

export const ASSISTANT_ID = process.env.NEXT_PUBLIC_ASSISTANT_ID ?? "agent";

export const REST_API_URL = (
  process.env.NEXT_PUBLIC_REST_API_URL ?? "http://localhost:8000"
).replace(/\/+$/, "");
