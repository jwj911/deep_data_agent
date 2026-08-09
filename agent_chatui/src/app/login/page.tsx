"use client";

import { type FormEvent, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Loader2 } from "lucide-react";

import { Logo } from "@/components/icons/logo";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { PasswordInput } from "@/components/ui/password-input";
import {
  AuthApiError,
  establishSession,
  getCurrentUser,
  registerUser,
} from "@/lib/auth-client";
import { getAuthToken } from "@/lib/api-key";

type AuthMode = "login" | "register";

function getErrorMessage(error: unknown, mode: AuthMode): string {
  if (!(error instanceof AuthApiError)) {
    return "无法连接认证服务，请检查网络后重试。";
  }

  if (error.code === "invalid_credentials") {
    return "用户名或密码错误。";
  }
  if (error.code === "registration_conflict") {
    return "用户名或邮箱已被注册。";
  }
  if (error.code === "auth_not_configured") {
    return "认证服务尚未完成配置。";
  }
  if (error.status === 422) {
    return mode === "register"
      ? "请检查用户名、邮箱和密码是否符合要求。"
      : "请填写有效的用户名和密码。";
  }
  if (error.code === "invalid_response") {
    return "认证服务返回了无效响应，请稍后重试。";
  }

  return `认证请求失败（${error.status || "网络错误"}）。`;
}

export default function LoginPage() {
  const router = useRouter();
  const [mode, setMode] = useState<AuthMode>("login");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string>();

  useEffect(() => {
    if (!getAuthToken()) return;

    void getCurrentUser()
      .then(() => router.replace("/"))
      .catch(() => {
        // Invalid tokens are cleared by the first-party REST client.
      });
  }, [router]);

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setErrorMessage(undefined);
    setIsSubmitting(true);

    const formData = new FormData(event.currentTarget);
    const username = String(formData.get("username") ?? "").trim();
    const password = String(formData.get("password") ?? "");

    try {
      if (mode === "register") {
        const email = String(formData.get("email") ?? "").trim();
        await registerUser({ username, email, password });
      }
      await establishSession({ username, password });
      router.replace("/");
    } catch (error) {
      setErrorMessage(getErrorMessage(error, mode));
    } finally {
      setIsSubmitting(false);
    }
  };

  const changeMode = (nextMode: AuthMode) => {
    setMode(nextMode);
    setErrorMessage(undefined);
  };

  return (
    <main className="bg-muted/30 flex min-h-screen items-center justify-center p-4">
      <Card className="w-full max-w-md">
        <CardHeader className="items-center text-center">
          <Logo className="mb-2 h-10" />
          <CardTitle className="text-2xl">Deep Data Agent</CardTitle>
          <CardDescription>
            {mode === "login" ? "使用用户名和密码登录" : "创建账号后将自动登录"}
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="bg-muted mb-6 grid grid-cols-2 rounded-lg p-1">
            <Button
              type="button"
              variant={mode === "login" ? "default" : "ghost"}
              onClick={() => changeMode("login")}
              disabled={isSubmitting}
            >
              登录
            </Button>
            <Button
              type="button"
              variant={mode === "register" ? "default" : "ghost"}
              onClick={() => changeMode("register")}
              disabled={isSubmitting}
            >
              注册
            </Button>
          </div>

          <form
            className="space-y-4"
            onSubmit={handleSubmit}
          >
            <div className="space-y-2">
              <Label htmlFor="username">用户名</Label>
              <Input
                id="username"
                name="username"
                autoComplete="username"
                minLength={mode === "register" ? 3 : undefined}
                maxLength={50}
                required
                autoFocus
              />
            </div>

            {mode === "register" && (
              <div className="space-y-2">
                <Label htmlFor="email">邮箱</Label>
                <Input
                  id="email"
                  name="email"
                  type="email"
                  autoComplete="email"
                  required
                />
              </div>
            )}

            <div className="space-y-2">
              <Label htmlFor="password">密码</Label>
              <PasswordInput
                id="password"
                name="password"
                autoComplete={
                  mode === "login" ? "current-password" : "new-password"
                }
                minLength={mode === "register" ? 8 : undefined}
                required
              />
              {mode === "register" && (
                <p className="text-muted-foreground text-xs">
                  用户名为 3-50 个字符，密码至少 8 个字符。
                </p>
              )}
            </div>

            {errorMessage && (
              <p
                className="text-destructive text-sm"
                role="alert"
              >
                {errorMessage}
              </p>
            )}

            <Button
              type="submit"
              className="w-full"
              disabled={isSubmitting}
            >
              {isSubmitting && <Loader2 className="size-4 animate-spin" />}
              {mode === "login" ? "登录" : "注册并登录"}
            </Button>
          </form>
        </CardContent>
      </Card>
    </main>
  );
}
