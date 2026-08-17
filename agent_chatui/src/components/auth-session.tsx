"use client";

import {
  createContext,
  type ReactNode,
  useContext,
  useEffect,
  useState,
} from "react";
import { useRouter } from "next/navigation";
import { Loader2, LogOut } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  AUTH_UNAUTHORIZED_EVENT,
  AuthApiError,
  type AuthUser,
  getCurrentUser,
} from "@/lib/auth-client";
import { clearAuthToken, clearLegacyApiKey, getAuthToken } from "@/lib/api-key";

interface AuthSessionValue {
  user: AuthUser;
  logout: () => void;
}

const AuthSessionContext = createContext<AuthSessionValue | undefined>(
  undefined,
);

export function AuthSession({ children }: { children: ReactNode }) {
  const router = useRouter();
  const [user, setUser] = useState<AuthUser>();
  const [error, setError] = useState<string>();
  const [verificationAttempt, setVerificationAttempt] = useState(0);

  useEffect(() => {
    let active = true;
    clearLegacyApiKey();

    const goToLogin = () => {
      if (!active) return;
      setUser(undefined);
      router.replace("/login");
    };
    const handleUnauthorized = () => {
      toast.error("登录已过期，请重新登录");
      goToLogin();
    };

    window.addEventListener(AUTH_UNAUTHORIZED_EVENT, handleUnauthorized);

    if (!getAuthToken()) {
      goToLogin();
    } else {
      setError(undefined);
      void getCurrentUser()
        .then((currentUser) => {
          if (active) setUser(currentUser);
        })
        .catch((requestError: unknown) => {
          if (!active || requestError instanceof AuthApiError) {
            if (
              active &&
              requestError instanceof AuthApiError &&
              requestError.status !== 401
            ) {
              setError("无法验证登录状态，请检查 REST API 后重试。");
            }
            return;
          }
          setError("无法连接认证服务，请检查网络后重试。");
        });
    }

    return () => {
      active = false;
      window.removeEventListener(AUTH_UNAUTHORIZED_EVENT, handleUnauthorized);
    };
  }, [router, verificationAttempt]);

  const logout = () => {
    clearAuthToken();
    setUser(undefined);
    router.replace("/login");
  };

  if (error) {
    return (
      <div className="flex min-h-screen items-center justify-center p-4">
        <div className="flex max-w-md flex-col items-center gap-4 text-center">
          <p className="text-destructive">{error}</p>
          <div className="flex gap-2">
            <Button
              onClick={() => setVerificationAttempt((value) => value + 1)}
            >
              重试
            </Button>
            <Button
              variant="outline"
              onClick={logout}
            >
              退出登录
            </Button>
          </div>
        </div>
      </div>
    );
  }

  if (!user) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <Loader2
          className="size-8 animate-spin"
          aria-label="正在验证登录状态"
        />
      </div>
    );
  }

  return (
    <AuthSessionContext.Provider value={{ user, logout }}>
      {children}
    </AuthSessionContext.Provider>
  );
}

export function SessionControls() {
  const { user, logout } = useAuthSession();

  return (
    <div className="flex items-center gap-2">
      <span className="text-muted-foreground hidden max-w-32 truncate text-sm sm:inline">
        {user.username}
      </span>
      <Button
        type="button"
        variant="ghost"
        size="sm"
        onClick={logout}
        aria-label="退出登录"
      >
        <LogOut className="size-4" />
        <span className="hidden sm:inline">退出登录</span>
      </Button>
    </div>
  );
}

function useAuthSession(): AuthSessionValue {
  const context = useContext(AuthSessionContext);
  if (!context) {
    throw new Error("useAuthSession must be used within AuthSession");
  }
  return context;
}
