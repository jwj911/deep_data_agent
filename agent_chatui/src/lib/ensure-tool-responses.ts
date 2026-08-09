import { Message, ToolMessage } from "@langchain/langgraph-sdk";
import { v4 as uuidv4 } from "uuid";

export const DO_NOT_RENDER_ID_PREFIX = "do-not-render-";

export function ensureToolCallsHaveResponses(messages: Message[]): Message[] {
  const newMessages: ToolMessage[] = [];

  messages.forEach((message, index) => {
    if (message.type !== "ai" || message.tool_calls?.length === 0) {
      return;
    }

    const followingMessage = messages[index + 1];
    if (followingMessage?.type === "tool") {
      return;
    }

    newMessages.push(
      ...(message.tool_calls?.map((toolCall) => ({
        type: "tool" as const,
        tool_call_id: toolCall.id ?? "",
        id: `${DO_NOT_RENDER_ID_PREFIX}${uuidv4()}`,
        name: toolCall.name,
        content: "Successfully handled tool call.",
      })) ?? []),
    );
  });

  return newMessages;
}
