import { validate } from "uuid";
import { AGENT_API_URL, ASSISTANT_ID } from "@/config";
import { Thread } from "@langchain/langgraph-sdk";
import { ReactNode, useCallback, useState } from "react";
import { createClient } from "./client";
import { ThreadContext } from "./thread-context";

function getThreadSearchMetadata(
  assistantId: string,
): { graph_id: string } | { assistant_id: string } {
  if (validate(assistantId)) {
    return { assistant_id: assistantId };
  } else {
    return { graph_id: assistantId };
  }
}

export function ThreadProvider({ children }: { children: ReactNode }) {
  const [threads, setThreads] = useState<Thread[]>([]);
  const [threadsLoading, setThreadsLoading] = useState(false);

  const getThreads = useCallback(async (): Promise<Thread[]> => {
    const client = createClient(AGENT_API_URL);

    const threads = await client.threads.search({
      metadata: {
        ...getThreadSearchMetadata(ASSISTANT_ID),
      },
      limit: 100,
    });

    return threads;
  }, []);

  const value = {
    getThreads,
    threads,
    setThreads,
    threadsLoading,
    setThreadsLoading,
  };

  return (
    <ThreadContext.Provider value={value}>{children}</ThreadContext.Provider>
  );
}
