import { Navigate, Route, Routes, useLocation, useNavigate } from "react-router-dom";
import type { ReactNode } from "react";
import AuthLayout from "../layouts/auth/AuthLayout";
import MainLayout from "../layouts/MainLayout";
import ForgotPasswordPage from "../pages/auth/ForgotPasswordPage";
import LoginPage from "../pages/auth/LoginPage";
import { DEFAULT_BUSINESS_PATH, resolveRoute } from "./routeResolver";

interface AppRoutesProps {
  mockLoggedIn: boolean;
  onLogin: () => void;
  onLogout: () => void;
}

function AuthRoute({
  children,
  mockLoggedIn,
}: {
  children: ReactNode;
  mockLoggedIn: boolean;
}) {
  return mockLoggedIn ? (
    <Navigate replace to={DEFAULT_BUSINESS_PATH} />
  ) : (
    <AuthLayout>{children}</AuthLayout>
  );
}

function LoginRoute({ mockLoggedIn, onLogin }: Pick<AppRoutesProps, "mockLoggedIn" | "onLogin">) {
  const navigate = useNavigate();

  return (
    <AuthRoute mockLoggedIn={mockLoggedIn}>
      <LoginPage
        onLogin={() => {
          onLogin();
          navigate(DEFAULT_BUSINESS_PATH, { replace: true });
        }}
      />
    </AuthRoute>
  );
}

function BusinessRoute({ mockLoggedIn, onLogout }: Pick<AppRoutesProps, "mockLoggedIn" | "onLogout">) {
  const location = useLocation();
  const navigate = useNavigate();
  const resolution = resolveRoute(location.pathname);

  if (!mockLoggedIn) {
    return <Navigate replace to="/login" />;
  }

  if (resolution.kind !== "allowed") {
    return <Navigate replace to={DEFAULT_BUSINESS_PATH} />;
  }

  return (
    <MainLayout
      onLogout={() => {
        onLogout();
        navigate("/login", { replace: true });
      }}
    />
  );
}

function AppRoutes({ mockLoggedIn, onLogin, onLogout }: AppRoutesProps) {
  return (
    <Routes>
      <Route path="/login" element={<LoginRoute mockLoggedIn={mockLoggedIn} onLogin={onLogin} />} />
      <Route
        path="/forgot-password"
        element={
          <AuthRoute mockLoggedIn={mockLoggedIn}>
            <ForgotPasswordPage />
          </AuthRoute>
        }
      />
      <Route path="*" element={<BusinessRoute mockLoggedIn={mockLoggedIn} onLogout={onLogout} />} />
    </Routes>
  );
}

export default AppRoutes;
