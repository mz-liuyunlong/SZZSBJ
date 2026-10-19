import { Alert, Button } from "antd";
import { useCallback, useEffect, useRef, useState } from "react";
import { clearServerState } from "@/api/queryClient";
import AppErrorBoundary from "@/components/errors/AppErrorBoundary";
import AppFeedbackProvider from "@/shared/feedback/AppFeedbackProvider";
import { clearTabWorkspaceStorage } from "@/layouts/useTabWorkspace";
import {
  fetchCurrentUser,
  logoutCurrentUser,
  sessionRestoreErrorMessage,
} from "@/pages/auth/authApi";
import {
  clearAuthTokenIfCurrent,
  isCurrentAuthSessionEvent,
  readAuthToken,
  subscribeAuthSession,
} from "@/pages/auth/authSession";
import type { AuthUser } from "@/pages/auth/authTypes";
import AppRoutes from "@/router/routes";
import "@/styles/globalOverlay.css";
import "@/styles/globalShellPolish.css";
import "@/styles/developedPagesOrderProfitSkin.css";

function App() {
  const [currentUser, setCurrentUser] = useState<AuthUser>();
  const [bootstrapping, setBootstrapping] = useState(() => Boolean(readAuthToken()));
  const [restoreError, setRestoreError] = useState<string>();
  const restoreGenerationRef = useRef(0);
  const restoreRequestRef = useRef<{
    token: string;
    promise: ReturnType<typeof fetchCurrentUser>;
  } | undefined>(undefined);

  const restoreCurrentUser = useCallback(async () => {
    const token = readAuthToken();
    const generation = ++restoreGenerationRef.current;
    if (!token) {
      setCurrentUser(undefined);
      setRestoreError(undefined);
      setBootstrapping(false);
      return;
    }

    setBootstrapping(true);
    setRestoreError(undefined);
    const existingRequest = restoreRequestRef.current;
    const promise = existingRequest?.token === token
      ? existingRequest.promise
      : fetchCurrentUser();
    restoreRequestRef.current = { token, promise };

    try {
      const user = await promise;
      if (generation !== restoreGenerationRef.current) return;
      if (readAuthToken() !== token) {
        if (!readAuthToken()) setCurrentUser(undefined);
        return;
      }
      setCurrentUser(user);
    } catch (error) {
      if (generation !== restoreGenerationRef.current || readAuthToken() !== token) return;
      setCurrentUser(undefined);
      setRestoreError(sessionRestoreErrorMessage(error));
    } finally {
      if (restoreRequestRef.current?.promise === promise) {
        restoreRequestRef.current = undefined;
      }
      if (generation === restoreGenerationRef.current) setBootstrapping(false);
    }
  }, []);

  useEffect(() => {
    if (!readAuthToken()) return;

    const timer = window.setTimeout(() => {
      void restoreCurrentUser();
    }, 0);
    return () => window.clearTimeout(timer);
  }, [restoreCurrentUser]);

  useEffect(() => subscribeAuthSession((event) => {
    if (!isCurrentAuthSessionEvent(event)) return;
    clearServerState();
    clearTabWorkspaceStorage();
    if (event.type === "logged-out") {
      restoreGenerationRef.current += 1;
      setCurrentUser(undefined);
      setRestoreError(undefined);
      setBootstrapping(false);
      return;
    }
    void restoreCurrentUser();
  }), [restoreCurrentUser]);

  const clearLogoutSessionStorage = () => {
    try {
      sessionStorage.clear();
    } catch {
      // Ignore storage failures during logout cleanup.
    }
  };

  const logout = async () => {
    const logoutToken = readAuthToken();
    restoreGenerationRef.current += 1;
    setCurrentUser(undefined);
    setRestoreError(undefined);
    clearLogoutSessionStorage();
    queueMicrotask(clearLogoutSessionStorage);

    const logoutPromise = logoutCurrentUser(logoutToken).catch(() => {
      if (logoutToken) clearAuthTokenIfCurrent(logoutToken);
    });

    window.setTimeout(() => {
      clearServerState();
    }, 0);

    await logoutPromise;
  };

  if (bootstrapping) {
    return (
      <div style={{ padding: 32, color: "#667085" }}>
        正在恢复登录状态...
      </div>
    );
  }

  if (restoreError && readAuthToken()) {
    return (
      <div style={{ maxWidth: 520, margin: "96px auto", padding: 24 }}>
        <Alert
          type="warning"
          showIcon
          message="暂时无法验证登录状态"
          description={restoreError}
          action={(
            <Button onClick={() => void restoreCurrentUser()}>
              重试
            </Button>
          )}
        />
      </div>
    );
  }

  return (
    <AppErrorBoundary>
      <AppFeedbackProvider>
        <AppRoutes
          mockLoggedIn={Boolean(currentUser)}
          currentUser={currentUser}
          onLogin={(user) => {
            restoreGenerationRef.current += 1;
            setRestoreError(undefined);
            setCurrentUser(user);
          }}
          onLogout={logout}
        />
      </AppFeedbackProvider>
    </AppErrorBoundary>
  );
}

export default App;
