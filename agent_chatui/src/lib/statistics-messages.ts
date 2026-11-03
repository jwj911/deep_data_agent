import type { AIMessage, Message } from "@langchain/langgraph-sdk";
import { DO_NOT_RENDER_ID_PREFIX } from "./ensure-tool-responses";
import {
  parseStatisticsContent,
  STATISTICS_TOOL_NAME,
  type StatisticsMessageResult,
} from "./statistics-result";

export interface MessageView {
  key: string;
  message: Message;
  statistics?: StatisticsMessageResult;
}

export function buildMessageViews(messages: Message[]): MessageView[] {
  const unique: Message[] = [];
  const identities = new Map<string, number>();
  for (const message of messages) {
    if (message.id?.startsWith(DO_NOT_RENDER_ID_PREFIX)) continue;
    const existing = message.id ? identities.get(message.id) : undefined;
    if (existing !== undefined) {
      unique[existing] = message;
    } else {
      if (message.id) identities.set(message.id, unique.length);
      unique.push(message);
    }
  }

  const calls = new Map<
    string,
    {
      call: NonNullable<AIMessage["tool_calls"]>[number];
      index: number;
    } | null
  >();
  for (const [index, message] of unique.entries()) {
    if (message.type === "ai") {
      for (const call of message.tool_calls ?? []) {
        if (typeof call.id !== "string" || !call.id.trim()) continue;
        // Reused call IDs are ambiguous, even when the arguments happen to match.
        calls.set(call.id, calls.has(call.id) ? null : { call, index });
      }
    }
  }
  const results = new Map<string, number>();
  const views: MessageView[] = [];
  for (const [index, message] of unique.entries()) {
    const match =
      message.type === "tool" ? calls.get(message.tool_call_id) : undefined;
    const call = match && match.index < index ? match.call : undefined;
    const view: MessageView = {
      key: message.id || `${message.type}-${index}`,
      message,
    };
    if (
      message.type === "tool" &&
      call?.name === STATISTICS_TOOL_NAME &&
      message.id?.trim()
    ) {
      view.key = `statistics-${message.tool_call_id}`;
      view.statistics = parseStatisticsContent(
        message.content,
        call.args,
        message.status,
      );
      const existing = results.get(message.tool_call_id);
      if (existing !== undefined) {
        views[existing] = view;
        continue;
      }
      results.set(message.tool_call_id, views.length);
    }
    views.push(view);
  }
  return views;
}
