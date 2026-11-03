import { Message, ToolMessage } from "@langchain/langgraph-sdk";
import { v4 as uuidv4 } from "uuid";

export const DO_NOT_RENDER_ID_PREFIX = "do-not-render-";

export class MissingToolCallIdError extends Error {
  constructor() {
    super(
      "工具调用缺少标识，暂时无法发送。输入和附件已保留，请恢复对话或新建对话后重试。",
    );
    this.name = "MissingToolCallIdError";
  }
}

export function ensureToolCallsHaveResponses(messages: Message[]): Message[] {
  const newMessages: ToolMessage[] = [];
  const added = new Set<string>();

  messages.forEach((message, index) => {
    if (message.type !== "ai") return;
    for (const toolCall of message.tool_calls ?? []) {
      if (typeof toolCall.id !== "string" || !toolCall.id.trim()) {
        throw new MissingToolCallIdError();
      }
      const hasResponse = messages
        .slice(index + 1)
        .some(
          (following) =>
            following.type === "tool" && following.tool_call_id === toolCall.id,
        );
      if (hasResponse || added.has(toolCall.id)) continue;
      added.add(toolCall.id);
      newMessages.push({
        type: "tool",
        tool_call_id: toolCall.id,
        id: `${DO_NOT_RENDER_ID_PREFIX}${uuidv4()}`,
        name: toolCall.name,
        status: "error",
        content: "没有取得工具结果",
      });
    }
  });

  return newMessages;
}
