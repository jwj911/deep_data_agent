"use client";

import { Thread } from "@/components/thread";
import { StreamProvider } from "@/providers/Stream";
import { ThreadProvider } from "@/providers/Thread";
import { ArtifactProvider } from "@/components/thread/artifact";
import { Toaster } from "@/components/ui/sonner";
import React from "react";
import { toast } from "sonner";
import { LOGIN_API_URL } from "@/config";

if (typeof window !== "undefined") {
  const originalFetch = globalThis.fetch.bind(globalThis);
  const interceptor = async (...args: Parameters<typeof fetch>) => {
    const res = await originalFetch(...args);
    if (res && res.status === 403) {
      try {
        localStorage.removeItem("auth_token");
        const onLogin = location.pathname.startsWith("/login");
        toast.error("未授权或登录过期，请重新登录");
        if (!onLogin) {
          window.location.href = LOGIN_API_URL;
        }
      } catch {}
    }
    return res;
  };
  globalThis.fetch = interceptor as typeof fetch;
  window.fetch = interceptor as typeof fetch;
}

export default function DemoPage(): React.ReactNode {
  return (
    <React.Suspense fallback={<div>Loading (layout)...</div>}>
      <Toaster />
      <ThreadProvider>
        <StreamProvider>
          <ArtifactProvider>
            <Thread />
          </ArtifactProvider>
        </StreamProvider>
      </ThreadProvider>
    </React.Suspense>
  );
}
