import type { Message } from "@langchain/langgraph-sdk";

import type { ManagedFileReference } from "@/lib/managed-file-client";

const PREFIX = "__managed_file_v1__:";
const UUID_PATTERN =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;
const MEDIA_TYPES = new Set([
  "text/plain",
  "text/markdown",
  "text/csv",
  "application/json",
]);

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

export function createManagedFileContentBlock(file: ManagedFileReference): {
  type: "text";
  text: string;
} {
  return {
    type: "text",
    text: `${PREFIX}${JSON.stringify({
      file_id: file.fileId,
      name: file.originalName,
      media_type: file.mediaType,
      size_bytes: file.sizeBytes,
    })}`,
  };
}

export function parseManagedFileReference(
  value: unknown,
): ManagedFileReference | null {
  if (typeof value !== "string" || !value.startsWith(PREFIX)) return null;
  try {
    const payload: unknown = JSON.parse(value.slice(PREFIX.length));
    if (
      !isRecord(payload) ||
      typeof payload.file_id !== "string" ||
      !UUID_PATTERN.test(payload.file_id) ||
      typeof payload.name !== "string" ||
      payload.name.length === 0 ||
      typeof payload.media_type !== "string" ||
      !MEDIA_TYPES.has(payload.media_type) ||
      typeof payload.size_bytes !== "number" ||
      !Number.isSafeInteger(payload.size_bytes) ||
      payload.size_bytes <= 0
    ) {
      return null;
    }
    return {
      fileId: payload.file_id,
      originalName: payload.name,
      mediaType: payload.media_type,
      sizeBytes: payload.size_bytes,
      createdAt: "",
      expiresAt: "",
    };
  } catch {
    return null;
  }
}

export function getManagedFileReferences(
  content: Message["content"],
): ManagedFileReference[] {
  if (!Array.isArray(content)) return [];
  return content.flatMap((block) => {
    if (block.type !== "text" || typeof block.text !== "string") return [];
    const reference = parseManagedFileReference(block.text);
    return reference ? [reference] : [];
  });
}

export function withoutManagedFileReferences(
  content: Message["content"],
): Message["content"] {
  if (!Array.isArray(content)) return content;
  return content.filter(
    (block) =>
      block.type !== "text" ||
      typeof block.text !== "string" ||
      parseManagedFileReference(block.text) === null,
  );
}
