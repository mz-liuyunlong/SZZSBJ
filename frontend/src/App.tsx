import { useEffect, useState } from "react";
import { clearServerState } from "@/api/queryClient";
import AppErrorBoundary from "@/components/errors/AppErrorBoundary";
import AppFeedbackProvider from "@/shared/feedback/AppFeedbackProvider";
import { fetchCurrentUser, logoutCurrentUser } from "@/pages/auth/authApi";
import { clearAuthToken, readAuthToken } from "@/pages/auth/authSession";
import type { AuthUser } from "@/pages/auth/authTypes";
import AppRoutes from "@/router/routes";
import "@/styles/globalOverlay.css";
import "@/styles/globalShellPolish.css";
import "@/styles/developedPagesOrderProfitSkin.css";

function App() {
  const [currentUser, setCurrentUser] = useState<AuthUser>();
  const [bootstrapping, setBootstrapping] = useState(() => Boolean(readAuthToken()));

  useEffect(() => {
    if (!readAuthToken()) return;

    let cancelled = false;

    void fetchCurrentUser()
      .then((user) => {
        if (!cancelled) setCurrentUser(user);
      })
      .finally(() => {
        if (!cancelled) setBootstrapping(false);
      });

    return () => {
      cancelled = true;
    };
  }, []);

  const clearLogoutSessionStorage = () => {
    try {
      sessionStorage.clear();
    } catch {
      // Ignore storage failures during logout cleanup.
    }
  };

  const logout = async () => {
    setCurrentUser(undefined);
    clearLogoutSessionStorage();
    queueMicrotask(clearLogoutSessionStorage);

    const logoutPromise = logoutCurrentUser().catch(() => clearAuthToken());

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

  return (
    <AppErrorBoundary>
      <AppFeedbackProvider>
        <AppRoutes
          mockLoggedIn={Boolean(currentUser)}
          currentUser={currentUser}
          onLogin={setCurrentUser}
          onLogout={logout}
        />
      </AppFeedbackProvider>
    </AppErrorBoundary>
  );
}

export default App;
