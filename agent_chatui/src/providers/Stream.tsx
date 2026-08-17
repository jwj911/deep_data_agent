import React, { ReactNode, useEffect } from "react";
import {
  isRemoveUIMessage,
  isUIMessage,
  uiMessageReducer,
} from "@langchain/langgraph-sdk/react-ui";
import { useQueryState } from "nuqs";
import { toast } from "sonner";

import { AGENT_API_URL, ASSISTANT_ID } from "@/config";
import { buildAgentAuthHeaders } from "@/lib/api-key";

import { useThreads } from "./thread-context";
import { StreamContext, useTypedStream } from "./stream-context";

async function sleep(ms = 4000) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function checkGraphStatus(): Promise<boolean> {
  try {
    const res = await fetch(`${AGENT_API_URL}/info`, {
      headers: buildAgentAuthHeaders(),
    });
    return res.ok;
  } catch (error) {
    console.error(error);
    return false;
  }
}

const StreamSession = ({ children }: { children: ReactNode }) => {
  const [threadId, setThreadId] = useQueryState("threadId");
  const { getThreads, setThreads } = useThreads();
  const headers = buildAgentAuthHeaders();
  const streamValue = useTypedStream({
    apiUrl: AGENT_API_URL,
    assistantId: ASSISTANT_ID,
    threadId: threadId ?? null,
    fetchStateHistory: true,
    defaultHeaders: Object.keys(headers).length > 0 ? headers : undefined,
    onCustomEvent: (event, options) => {
      if (isUIMessage(event) || isRemoveUIMessage(event)) {
        options.mutate((prev) => {
          const ui = uiMessageReducer(prev.ui ?? [], event);
          return { ...prev, ui };
        });
      }
    },
    onThreadId: (id) => {
      setThreadId(id);
      sleep().then(() => getThreads().then(setThreads).catch(console.error));
    },
  });

  useEffect(() => {
    void checkGraphStatus().then((ok) => {
      if (!ok) {
        toast.error("无法连接 Agent 服务", {
          description: "请检查 Agent 服务状态或重新登录。",
          duration: 10000,
          richColors: true,
          closeButton: true,
        });
      }
    });
  }, []);

  return (
    <StreamContext.Provider value={streamValue}>
      {children}
    </StreamContext.Provider>
  );
};

export const StreamProvider: React.FC<{ children: ReactNode }> = ({
  children,
}) => <StreamSession>{children}</StreamSession>;
