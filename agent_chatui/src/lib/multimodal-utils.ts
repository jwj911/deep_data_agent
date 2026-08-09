import { ContentBlock } from "@langchain/core/messages";

const SUPPORTED_IMAGE_TYPES = [
  "image/jpeg",
  "image/png",
  "image/gif",
  "image/webp",
];
const SUPPORTED_FILE_TYPES = [...SUPPORTED_IMAGE_TYPES, "application/pdf"];

export async function fileToContentBlock(
  file: File,
): Promise<ContentBlock.Multimodal.Data> {
  if (!SUPPORTED_FILE_TYPES.includes(file.type)) {
    throw new Error(`Unsupported file type: ${file.type}`);
  }

  const data = await fileToBase64(file);
  if (SUPPORTED_IMAGE_TYPES.includes(file.type)) {
    return {
      type: "image",
      mimeType: file.type,
      data,
      metadata: { name: file.name },
    };
  }

  return {
    type: "file",
    mimeType: "application/pdf",
    data,
    metadata: { filename: file.name },
  };
}

export async function fileToBase64(file: File): Promise<string> {
  return new Promise<string>((resolve, reject) => {
    const reader = new FileReader();
    reader.onloadend = () => {
      if (typeof reader.result !== "string") {
        reject(new Error("Unable to read file as a data URL"));
        return;
      }

      const encodedData = reader.result.split(",", 2)[1];
      if (!encodedData) {
        reject(new Error("Unable to extract Base64 file content"));
        return;
      }
      resolve(encodedData);
    };
    reader.onerror = () =>
      reject(reader.error ?? new Error("File read failed"));
    reader.readAsDataURL(file);
  });
}

export function isBase64ContentBlock(
  block: unknown,
): block is ContentBlock.Multimodal.Data {
  if (typeof block !== "object" || block === null || !("type" in block)) {
    return false;
  }

  if (
    block.type === "file" &&
    "mimeType" in block &&
    typeof block.mimeType === "string" &&
    (block.mimeType.startsWith("image/") ||
      block.mimeType === "application/pdf")
  ) {
    return true;
  }

  return (
    block.type === "image" &&
    "mimeType" in block &&
    typeof block.mimeType === "string" &&
    block.mimeType.startsWith("image/")
  );
}
