const API_KEY_STORAGE_KEY = "lg:chat:apiKey";
const AUTH_TOKEN_STORAGE_KEY = "auth_token";

function getLocalStorageItem(key: string): string | null {
  try {
    if (typeof window === "undefined") return null;
    const value = window.localStorage.getItem(key)?.trim();
    return value || null;
  } catch {
    return null;
  }
}

export function getApiKey(): string | null {
  return getLocalStorageItem(API_KEY_STORAGE_KEY);
}

export function setApiKey(apiKey: string): void {
  if (typeof window === "undefined") return;

  try {
    const value = apiKey.trim();
    if (value) {
      window.localStorage.setItem(API_KEY_STORAGE_KEY, value);
    } else {
      window.localStorage.removeItem(API_KEY_STORAGE_KEY);
    }
  } catch {
    // Storage can be unavailable in restricted browser contexts.
  }
}

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

export function buildRequestHeaders(
  apiKey?: string | null,
): Record<string, string> {
  const headers: Record<string, string> = {};
  const normalizedApiKey = apiKey?.trim();

  if (normalizedApiKey) {
    headers["X-Api-Key"] = normalizedApiKey;
  }

  return headers;
}
