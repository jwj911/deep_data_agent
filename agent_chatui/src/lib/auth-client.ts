import { REST_API_URL } from "@/config";
import { clearAuthToken, getAuthToken, setAuthToken } from "@/lib/api-key";
import { createRequestId, REQUEST_ID_HEADER } from "@/lib/request-id";

export const AUTH_UNAUTHORIZED_EVENT = "auth:unauthorized";

export type UserRole = "user" | "admin";

export interface AuthUser {
  id: number;
  username: string;
  email: string;
  role: UserRole;
}

export interface LoginCredentials {
  username: string;
  password: string;
}

export interface RegistrationCredentials extends LoginCredentials {
  email: string;
}

export interface TokenResponse {
  access_token: string;
  token_type: "bearer";
  expires_in: number;
}

export class AuthApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly code: string,
    message: string,
    public readonly requestId?: string,
  ) {
    super(message);
    this.name = "AuthApiError";
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function buildRestApiUrl(path: string): URL {
  const baseUrl = new URL(`${REST_API_URL}/`);
  return new URL(path.replace(/^\/+/, ""), baseUrl);
}

export function isRestApiUrl(value: string | URL): boolean {
  try {
    const baseUrl = new URL(REST_API_URL);
    const targetUrl = new URL(value, baseUrl);
    if (targetUrl.origin !== baseUrl.origin) return false;

    const basePath = baseUrl.pathname.replace(/\/+$/, "");
    return (
      !basePath ||
      targetUrl.pathname === basePath ||
      targetUrl.pathname.startsWith(`${basePath}/`)
    );
  } catch {
    return false;
  }
}

function notifyUnauthorized(): void {
  clearAuthToken();
  if (typeof window !== "undefined") {
    window.dispatchEvent(new Event(AUTH_UNAUTHORIZED_EVENT));
  }
}

async function readJson(response: Response): Promise<unknown> {
  try {
    return await response.json();
  } catch {
    throw new AuthApiError(
      response.status || 502,
      "invalid_response",
      "Authentication service returned an invalid response",
      response.headers.get(REQUEST_ID_HEADER) ?? undefined,
    );
  }
}

async function createApiError(response: Response): Promise<AuthApiError> {
  let body: unknown;
  try {
    body = await response.json();
  } catch {
    body = undefined;
  }

  const detail = isRecord(body) ? body.detail : undefined;
  const error = isRecord(detail) ? detail : isRecord(body) ? body : undefined;
  const code =
    typeof error?.code === "string" ? error.code : `http_${response.status}`;
  const message =
    typeof error?.message === "string"
      ? error.message
      : typeof detail === "string"
        ? detail
        : `Authentication request failed with status ${response.status}`;

  return new AuthApiError(
    response.status,
    code,
    message,
    response.headers.get(REQUEST_ID_HEADER) ?? undefined,
  );
}

async function request(
  path: string,
  init: RequestInit,
  authenticated: boolean,
): Promise<Response> {
  const url = buildRestApiUrl(path);
  if (!isRestApiUrl(url)) {
    throw new AuthApiError(
      0,
      "invalid_rest_api_url",
      "Authentication request target is outside the configured REST API",
    );
  }

  const headers = new Headers(init.headers);
  const requestId = createRequestId();
  headers.set("Accept", "application/json");
  headers.set(REQUEST_ID_HEADER, requestId);
  if (authenticated) {
    const token = getAuthToken();
    if (token) {
      headers.set("Authorization", `Bearer ${token}`);
    }
  }

  let response: Response;
  try {
    response = await fetch(url, { ...init, headers });
  } catch {
    throw new AuthApiError(
      0,
      "network_error",
      "Authentication service is unreachable",
      requestId,
    );
  }
  if (response.status === 401 && isRestApiUrl(url)) {
    notifyUnauthorized();
  }
  if (!response.ok) {
    throw await createApiError(response);
  }

  return response;
}

function parseUser(value: unknown, requestId?: string): AuthUser {
  if (
    !isRecord(value) ||
    typeof value.id !== "number" ||
    typeof value.username !== "string" ||
    typeof value.email !== "string" ||
    (value.role !== "user" && value.role !== "admin")
  ) {
    throw new AuthApiError(
      502,
      "invalid_response",
      "Authentication service returned an invalid user",
      requestId,
    );
  }

  return {
    id: value.id,
    username: value.username,
    email: value.email,
    role: value.role,
  };
}

function parseToken(value: unknown, requestId?: string): TokenResponse {
  if (
    !isRecord(value) ||
    typeof value.access_token !== "string" ||
    value.access_token.length === 0 ||
    value.token_type !== "bearer" ||
    typeof value.expires_in !== "number" ||
    !Number.isFinite(value.expires_in)
  ) {
    throw new AuthApiError(
      502,
      "invalid_response",
      "Authentication service returned an invalid token",
      requestId,
    );
  }

  return {
    access_token: value.access_token,
    token_type: value.token_type,
    expires_in: value.expires_in,
  };
}

export async function registerUser(
  credentials: RegistrationCredentials,
): Promise<AuthUser> {
  const response = await request(
    "api/auth/register",
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(credentials),
    },
    false,
  );
  return parseUser(
    await readJson(response),
    response.headers.get(REQUEST_ID_HEADER) ?? undefined,
  );
}

export async function loginUser(
  credentials: LoginCredentials,
): Promise<TokenResponse> {
  const body = new URLSearchParams({
    username: credentials.username,
    password: credentials.password,
  });
  const response = await request(
    "api/auth/login",
    {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body,
    },
    false,
  );
  return parseToken(
    await readJson(response),
    response.headers.get(REQUEST_ID_HEADER) ?? undefined,
  );
}

export async function getCurrentUser(): Promise<AuthUser> {
  const response = await request(
    "api/auth/me",
    {
      method: "GET",
    },
    true,
  );
  return parseUser(
    await readJson(response),
    response.headers.get(REQUEST_ID_HEADER) ?? undefined,
  );
}

export async function establishSession(
  credentials: LoginCredentials,
): Promise<AuthUser> {
  const token = await loginUser(credentials);
  setAuthToken(token.access_token);

  try {
    return await getCurrentUser();
  } catch (error) {
    clearAuthToken();
    throw error;
  }
}
