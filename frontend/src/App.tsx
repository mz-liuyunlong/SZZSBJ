import { useState } from "react";
import { clearServerState } from "@/api/queryClient";
import AppErrorBoundary from "@/components/errors/AppErrorBoundary";
import AppFeedbackProvider from "@/shared/feedback/AppFeedbackProvider";
import type { MockAuthUser } from "@/mocks/auth";
import AppRoutes from "@/router/routes";
import "@/styles/globalOverlay.css";
import "@/styles/globalShellPolish.css";
import "@/styles/developedPagesOrderProfitSkin.css";

function App() {
  const [mockUser, setMockUser] = useState<MockAuthUser>();

  const clearLogoutSessionStorage = () => {
    try {
      sessionStorage.clear();
    } catch {
      // Ignore storage failures during logout cleanup.
    }
  };

  const logout = () => {
    clearServerState();
    setMockUser(undefined);
    clearLogoutSessionStorage();
    queueMicrotask(clearLogoutSessionStorage);
  };

  return (
    <AppErrorBoundary>
      <AppFeedbackProvider>
        <AppRoutes
          mockLoggedIn={Boolean(mockUser)}
          currentUser={mockUser}
          onLogin={setMockUser}
          onLogout={logout}
        />
      </AppFeedbackProvider>
    </AppErrorBoundary>
  );
}

export default App;
