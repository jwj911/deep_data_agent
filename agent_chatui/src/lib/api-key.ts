const LEGACY_API_KEY_STORAGE_KEY = "lg:chat:apiKey";
const AUTH_TOKEN_STORAGE_KEY = "auth_token";

export function getAuthToken(): string | null {
  try {
    if (typeof window === "undefined") return null;
    const value = window.sessionStorage.getItem(AUTH_TOKEN_STORAGE_KEY)?.trim();
    return value || null;
  } catch {
    return null;
  }
}

export function setAuthToken(authToken: string): void {
  if (typeof window === "undefined") return;

  const value = authToken.trim();
  if (!value) {
    throw new Error("Authentication token cannot be empty");
  }

  window.sessionStorage.setItem(AUTH_TOKEN_STORAGE_KEY, value);
}

export function clearAuthToken(): void {
  try {
    if (typeof window === "undefined") return;
    window.sessionStorage.removeItem(AUTH_TOKEN_STORAGE_KEY);
  } catch {
    // Storage can be unavailable in restricted browser contexts.
  }
}

export function clearLegacyApiKey(): void {
  try {
    if (typeof window === "undefined") return;
    window.localStorage.removeItem(LEGACY_API_KEY_STORAGE_KEY);
  } catch {
    // Storage can be unavailable in restricted browser contexts.
  }
}

export function buildAgentAuthHeaders(): Record<string, string> {
  const headers: Record<string, string> = {};
  const authToken = getAuthToken();

  if (authToken) {
    headers.Authorization = `Bearer ${authToken}`;
  }

  return headers;
}
