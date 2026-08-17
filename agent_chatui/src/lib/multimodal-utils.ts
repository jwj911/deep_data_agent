import { ContentBlock } from "@langchain/core/messages";

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
