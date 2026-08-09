import { validate } from "uuid";
import { getApiKey } from "@/lib/api-key";
import { AGENT_API_URL, ASSISTANT_ID } from "@/config";
import { Thread } from "@langchain/langgraph-sdk";
import { useQueryState } from "nuqs";
import {
  createContext,
  useContext,
  ReactNode,
  useCallback,
  useState,
  Dispatch,
  SetStateAction,
} from "react";
import { createClient } from "./client";
import { resolveConnectionConfig } from "./connection";

interface ThreadContextType {
  getThreads: () => Promise<Thread[]>;
  threads: Thread[];
  setThreads: Dispatch<SetStateAction<Thread[]>>;
  threadsLoading: boolean;
  setThreadsLoading: Dispatch<SetStateAction<boolean>>;
}

const ThreadContext = createContext<ThreadContextType | undefined>(undefined);

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
  const [apiUrl] = useQueryState("apiUrl", {
    defaultValue: AGENT_API_URL,
  });
  const [assistantId] = useQueryState("assistantId", {
    defaultValue: ASSISTANT_ID,
  });
  const [threads, setThreads] = useState<Thread[]>([]);
  const [threadsLoading, setThreadsLoading] = useState(false);
  const connection = resolveConnectionConfig(apiUrl, assistantId);

  const getThreads = useCallback(async (): Promise<Thread[]> => {
    const client = createClient(connection.apiUrl, getApiKey());

    const threads = await client.threads.search({
      metadata: {
        ...getThreadSearchMetadata(connection.assistantId),
      },
      limit: 100,
    });

    return threads;
  }, [connection.apiUrl, connection.assistantId]);

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

export function useThreads() {
  const context = useContext(ThreadContext);
  if (context === undefined) {
    throw new Error("useThreads must be used within a ThreadProvider");
  }
  return context;
}
