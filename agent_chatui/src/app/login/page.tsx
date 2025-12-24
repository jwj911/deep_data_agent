"use client";

import { Suspense, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { Card } from "@/components/ui/card";
import { Loader2 } from "lucide-react";
import { AGENT_API_URL } from "@/config";

export default function LoginPage() {
  return (
    <Suspense fallback={<div>Loading...</div>}>
      <LoginContent />
    </Suspense>
  );
}

function LoginContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [isLoading, setIsLoading] = useState(false);
  const code = searchParams.get("code");

  useEffect(() => {
    if (!code) return;

    const login = async () => {
      setIsLoading(true);
      try {
        const response = await fetch(`${AGENT_API_URL}/login?code=${code}`);
        if (response.ok) {
          const data = await response.json();
          if (data.token) localStorage.setItem("auth_token", data.token);
          router.push(`/?apiUrl=${AGENT_API_URL}&assistantId=agent`);
        } else {
          throw new Error("登录失败");
        }
      } catch (error) {
        alert("登录失败，请重试");
        setIsLoading(false);
      }
    };

    setTimeout(login, 1000);
  }, [code, router]);

  return (
    <div className="flex min-h-screen items-center justify-center p-4">
      <Card className="w-full max-w-md p-6 text-center">
        <Loader2 className="mx-auto h-8 w-8 animate-spin mb-4" />
        <h2 className="text-lg font-semibold mb-2">正在登录</h2>
        <p className="text-muted-foreground">使用授权码: {code}</p>
      </Card>
    </div>
  );
}