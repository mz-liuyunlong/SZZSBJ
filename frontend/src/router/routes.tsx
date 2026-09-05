import { Navigate, Route, Routes, useLocation, useNavigate } from "react-router-dom";
import MainLayout from "../layouts/MainLayout";
import LoginPage from "../pages/auth/LoginPage";
import { DEFAULT_BUSINESS_PATH, resolveRoute } from "./routeResolver";

interface AppRoutesProps {
  mockLoggedIn: boolean;
  onLogin: () => void;
  onLogout: () => void;
}

function LoginRoute({ mockLoggedIn, onLogin }: Pick<AppRoutesProps, "mockLoggedIn" | "onLogin">) {
  const navigate = useNavigate();

  if (mockLoggedIn) {
    return <Navigate replace to={DEFAULT_BUSINESS_PATH} />;
  }

  return (
    <LoginPage
      onLogin={() => {
        onLogin();
        navigate(DEFAULT_BUSINESS_PATH, { replace: true });
      }}
    />
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
      <Route path="*" element={<BusinessRoute mockLoggedIn={mockLoggedIn} onLogout={onLogout} />} />
    </Routes>
  );
}

export default AppRoutes;
