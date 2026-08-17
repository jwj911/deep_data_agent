import { REST_API_URL } from "@/config";
import { AUTH_UNAUTHORIZED_EVENT, isRestApiUrl } from "@/lib/auth-client";
import { clearAuthToken, getAuthToken } from "@/lib/api-key";
import { createRequestId, REQUEST_ID_HEADER } from "@/lib/request-id";

export const FILE_MAX_COUNT = 5;
export const FILE_MAX_BYTES = 5 * 1024 * 1024;
export const FILE_BATCH_MAX_BYTES = 10 * 1024 * 1024;
export const MANAGED_FILE_ACCEPT =
  ".txt,.md,.csv,.json,text/plain,text/markdown,text/csv,application/json";

const SUPPORTED_MEDIA_TYPES = new Set([
  "text/plain",
  "text/markdown",
  "text/csv",
  "application/json",
]);
const UUID_PATTERN =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;

export interface ManagedFileReference {
  fileId: string;
  originalName: string;
  mediaType: string;
  sizeBytes: number;
  createdAt: string;
  expiresAt: string;
}

export class ManagedFileApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly code: string,
    message: string,
    public readonly requestId?: string,
  ) {
    super(message);
    this.name = "ManagedFileApiError";
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function buildFileUrl(path = ""): URL {
  const base = new URL(`${REST_API_URL}/`);
  return new URL(`api/files${path}`, base);
}

function notifyUnauthorized(): void {
  clearAuthToken();
  if (typeof window !== "undefined") {
    window.dispatchEvent(new Event(AUTH_UNAUTHORIZED_EVENT));
  }
}

async function createError(response: Response): Promise<ManagedFileApiError> {
  let payload: unknown;
  try {
    payload = await response.json();
  } catch {
    payload = undefined;
  }
  const detail = isRecord(payload) ? payload.detail : undefined;
  const error = isRecord(detail) ? detail : undefined;
  const code =
    typeof error?.code === "string" ? error.code : `http_${response.status}`;
  const message =
    typeof error?.message === "string"
      ? error.message
      : "Managed file request failed";
  return new ManagedFileApiError(
    response.status,
    code,
    message,
    response.headers.get(REQUEST_ID_HEADER) ?? undefined,
  );
}

async function request(path: string, init: RequestInit): Promise<Response> {
  const url = buildFileUrl(path);
  if (!isRestApiUrl(url)) {
    throw new ManagedFileApiError(
      0,
      "invalid_rest_api_url",
      "Managed file target is outside the configured REST API",
    );
  }
  const headers = new Headers(init.headers);
  headers.set("Accept", "application/json");
  headers.set(REQUEST_ID_HEADER, createRequestId());
  const token = getAuthToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);

  let response: Response;
  try {
    response = await fetch(url, { ...init, headers });
  } catch {
    throw new ManagedFileApiError(
      0,
      "network_error",
      "Managed file service is unreachable",
    );
  }
  if (response.status === 401 && isRestApiUrl(url)) notifyUnauthorized();
  if (!response.ok) throw await createError(response);
  return response;
}

function parseManagedFile(value: unknown): ManagedFileReference {
  if (
    !isRecord(value) ||
    typeof value.file_id !== "string" ||
    !UUID_PATTERN.test(value.file_id) ||
    typeof value.original_name !== "string" ||
    value.original_name.length === 0 ||
    typeof value.media_type !== "string" ||
    !SUPPORTED_MEDIA_TYPES.has(value.media_type) ||
    typeof value.size_bytes !== "number" ||
    !Number.isSafeInteger(value.size_bytes) ||
    value.size_bytes <= 0 ||
    typeof value.created_at !== "string" ||
    typeof value.expires_at !== "string"
  ) {
    throw new ManagedFileApiError(
      502,
      "invalid_response",
      "Managed file service returned invalid metadata",
    );
  }
  return {
    fileId: value.file_id,
    originalName: value.original_name,
    mediaType: value.media_type,
    sizeBytes: value.size_bytes,
    createdAt: value.created_at,
    expiresAt: value.expires_at,
  };
}

export async function uploadManagedFiles(
  files: File[],
): Promise<ManagedFileReference[]> {
  const form = new FormData();
  for (const file of files) form.append("files", file, file.name);
  const response = await request("", { method: "POST", body: form });
  const payload: unknown = await response.json();
  if (!Array.isArray(payload)) {
    throw new ManagedFileApiError(
      502,
      "invalid_response",
      "Managed file service returned an invalid upload response",
    );
  }
  return payload.map(parseManagedFile);
}

export async function deleteManagedFile(fileId: string): Promise<void> {
  await request(`/${encodeURIComponent(fileId)}`, { method: "DELETE" });
}

export function validateManagedFileSelection(
  files: File[],
  existing: ManagedFileReference[],
): string | null {
  if (files.length === 0) return null;
  if (existing.length + files.length > FILE_MAX_COUNT) {
    return `每条消息最多上传 ${FILE_MAX_COUNT} 个文件。`;
  }
  if (files.some((file) => file.size <= 0)) {
    return "不能上传空文件。";
  }
  if (files.some((file) => file.size > FILE_MAX_BYTES)) {
    return "单个文件不能超过 5 MiB。";
  }
  const total =
    existing.reduce((sum, file) => sum + file.sizeBytes, 0) +
    files.reduce((sum, file) => sum + file.size, 0);
  if (total > FILE_BATCH_MAX_BYTES) {
    return "本条消息的文件总量不能超过 10 MiB。";
  }
  const names = new Set(existing.map((file) => file.originalName));
  for (const file of files) {
    const normalized = file.name.trim();
    const parts = normalized.split(".");
    if (parts.length !== 2 || !parts[0] || !parts[1]) {
      return "文件名只能包含一个受支持的扩展名。";
    }
    const extension = `.${parts[1].toLowerCase()}`;
    if (![".txt", ".md", ".csv", ".json"].includes(extension)) {
      return "仅支持 TXT、Markdown、CSV 和 JSON 文件。";
    }
    if (names.has(normalized)) return "同一条消息不能上传重名文件。";
    names.add(normalized);
  }
  return null;
}
