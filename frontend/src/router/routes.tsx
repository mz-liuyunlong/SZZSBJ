import {
  Navigate,
  Route,
  Routes,
  useLocation,
  useNavigate,
} from "react-router-dom";
import type { ReactNode } from "react";
import AuthLayout from "@/layouts/auth/AuthLayout";
import MainLayout from "@/layouts/MainLayout";
import { readTabWorkspace } from "@/layouts/useTabWorkspace";
import ComingSoonPage from "@/pages/ComingSoonPage";
import ForgotPasswordPage from "@/pages/auth/ForgotPasswordPage";
import PasswordSetupPage from "@/pages/auth/PasswordSetupPage";
import OnboardingGuidePage from "@/pages/help/OnboardingGuidePage";
import LoginPage from "@/pages/auth/LoginPage";
import NotFoundPage from "@/pages/errors/NotFoundPage";
import ListingManagementPage from "@/pages/products/ListingManagementPage";
import ProductManagementPage from "@/pages/products/ProductManagementPage";
import DailySalesPage from "@/pages/sales/DailySalesPage";
import OrderProfitPage from "@/pages/sales/OrderProfitPage";
import RefundManagementPage from "@/pages/aftersales/RefundManagementPage";
import AdsCampaignsPage from "@/pages/ads/campaigns/AdsCampaignsPage";
import KeywordLaunchPage from "@/pages/ai-center/keyword-launch/KeywordLaunchPage";
import KeywordLibraryPage from "@/pages/ads/keyword-library/KeywordLibraryPage";
import OperationLogPage from "@/pages/operations/OperationLogPage";
import OperationPlanPage from "@/pages/operations/OperationPlanPage";
import SyncTaskPage from "@/pages/data-center/SyncTaskPage";
import ApprovalWorkspacePage from "@/pages/data-center/approval-workspace/ApprovalWorkspacePage";
import ApiDocsPage from "@/pages/data-center/ApiDocsPage";
import DataImportPage from "@/pages/data-center/DataImportPage";
import WfsFeeAlertPage from "@/pages/warehouse/WfsFeeAlertPage";
import PurchaseBoardPage from "@/pages/pmc/purchase-board/PurchaseBoardPage";
import DomesticWarehousePage from "@/pages/pmc/domestic-warehouse/DomesticWarehousePage";
import UserManagementPage from "@/pages/settings/UserManagementPage";
import RoleManagementPage from "@/pages/settings/RoleManagementPage";
import FeeRulesPage from "@/pages/settings/FeeRulesPage";
import BusinessConfigPage from "@/pages/settings/BusinessConfigPage";
import { navigation, navigationRedirects } from "@/config/navigation";
import { DEFAULT_BUSINESS_PATH, resolveRoute } from "@/router/routeResolver";
import { DEFAULT_AUTH_USER, type AuthUser } from "@/pages/auth/authTypes";
import { isMockPageAccessibleForRole } from "@/shared/permissions/mockAccess";

interface AppRoutesProps {
  mockLoggedIn: boolean;
  currentUser?: AuthUser;
  onLogin: (user: AuthUser) => void;
  onLogout: () => void | Promise<void>;
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

function PublicAuthRoute({ children }: { children: ReactNode }) {
  return <AuthLayout>{children}</AuthLayout>;
}

function shouldShowOnboardingAfterLogin() {
  if (typeof window === "undefined") return false;
  return window.sessionStorage.getItem("szzsbj_show_onboarding_after_login") === "1";
}

function clearShowOnboardingAfterLogin(): void {
  try {
    sessionStorage.removeItem("szzsbj_show_onboarding_after_login");
  } catch {
    // Ignore storage failures.
  }
}

function firstAccessibleBusinessPath(user: AuthUser): string {
  const page = navigation
    .flatMap((group) => group.children)
    .find((item) =>
      isMockPageAccessibleForRole(user.role, item, user.permissions),
    );

  return page?.path ?? "/help/onboarding";
}

function LoginRoute({
  mockLoggedIn,
  onLogin,
}: Pick<AppRoutesProps, "mockLoggedIn" | "onLogin">) {
  const navigate = useNavigate();

  return (
    <AuthRoute mockLoggedIn={mockLoggedIn}>
      <LoginPage
        onLogin={(user) => {
          const { activePath } = readTabWorkspace();
          const shouldOpenOnboarding = shouldShowOnboardingAfterLogin();
          const resolution = resolveRoute(activePath);
          const canRestore = resolution.kind === "allowed" &&
            isMockPageAccessibleForRole(
              user.role,
              resolution.route.page,
              user.permissions,
            );

          onLogin(user);
          clearShowOnboardingAfterLogin();

          navigate(
            shouldOpenOnboarding
              ? "/help/onboarding"
              : canRestore
                ? activePath
                : firstAccessibleBusinessPath(user),
            { replace: true },
          );
        }}
      />
    </AuthRoute>
  );
}

function BusinessRoute({
  mockLoggedIn,
  currentUser,
  onLogout,
}: Pick<AppRoutesProps, "mockLoggedIn" | "currentUser" | "onLogout">) {
  const location = useLocation();
  const navigate = useNavigate();
  const resolution = resolveRoute(location.pathname);

  if (!mockLoggedIn) {
    return <Navigate replace to="/login" />;
  }

  const activeUser = currentUser ?? DEFAULT_AUTH_USER;
  const defaultPath = firstAccessibleBusinessPath(activeUser);

  const redirect = navigationRedirects[location.pathname];
  if (redirect) return <Navigate replace to={redirect} />;

  if (location.pathname === "/") {
    return <Navigate replace to={defaultPath} />;
  }

  if (resolution.kind === "unknown") {
    return <NotFoundPage />;
  }

  if (resolution.kind === "disabled") {
    return <Navigate replace to={defaultPath} />;
  }

  if (
    !isMockPageAccessibleForRole(
      activeUser.role,
      resolution.route.page,
      activeUser.permissions,
    )
  ) {
    return <Navigate replace to={defaultPath} />;
  }

  return (
    <MainLayout
      currentUser={activeUser}
      onLogout={() => {
        void onLogout();
        navigate("/login", { replace: true });
      }}
      renderPage={(page) =>
        page.key === "products_product_management" ? (
          <ProductManagementPage page={page} preferenceScope={activeUser.username} />
        ) : page.key === "products_listing_management" ? (
          <ListingManagementPage page={page} />
        ) : page.key === "sales_daily_sales" ? (
          <DailySalesPage page={page} />
        ) : page.key === "sales_order_profit" ? (
          <OrderProfitPage page={page} />
        ) : page.key === "ai_center_keyword_launch" ? (
          <KeywordLaunchPage page={page} />
        ) : page.key === "ads_keyword_library" ? (
          <KeywordLibraryPage page={page} />
        ) : page.key === "ads_campaigns" ? (
          <AdsCampaignsPage page={page} />
        ) : page.key === "aftersales_refund_management" ? (
          <RefundManagementPage page={page} />
        ) : page.key === "operations_log" ? (
          <OperationLogPage page={page} />
        ) : page.key === "operations_plan" ? (
          <OperationPlanPage page={page} />
        ) : page.key === "warehouse_wfs_fee_alert" ? (
          <WfsFeeAlertPage page={page} permissions={activeUser.permissions} />
        ) : page.key === "pmc_purchase_board" ? (
          <PurchaseBoardPage page={page} preferenceScope={activeUser.username} />
        ) : ["pmc_domestic_batches", "pmc_packing_approval", "pmc_packing_warehouse"].includes(page.key) ? (
          <DomesticWarehousePage page={page} preferenceScope={activeUser.username}
            view={page.key === "pmc_packing_approval" ? "approval" : page.key === "pmc_packing_warehouse" ? "packing" : "batches"} />
        ) : page.key === "data_center_approval_workspace" ? (
          <ApprovalWorkspacePage page={page} permissions={activeUser.permissions} />
        ) : page.key === "data_center_data_import" ? (
          <DataImportPage page={page} />
        ) : page.key === "data_center_api_docs" ? (
          <ApiDocsPage page={page} />
        ) : page.key === "data_center_task_center" ? (
          <SyncTaskPage page={page} />
        ) : page.key === "settings_user_management" ? (
          <UserManagementPage page={page} />
        ) : page.key === "settings_role_management" ? (
          <RoleManagementPage page={page} />
        ) : page.key === "settings_business_config" ? (
          <BusinessConfigPage page={page} />
        ) : page.key === "settings_fee_rules" ? (
          <FeeRulesPage page={page} />
        ) : (
          <ComingSoonPage page={page} />
        )
      }
    />
  );
}

function AppRoutes({ mockLoggedIn, currentUser, onLogin, onLogout }: AppRoutesProps) {
  return (
    <Routes>
      <Route
        path="/login"
        element={<LoginRoute mockLoggedIn={mockLoggedIn} onLogin={onLogin} />}
      />
      <Route
        path="/forgot-password"
        element={
          <AuthRoute mockLoggedIn={mockLoggedIn}>
            <ForgotPasswordPage />
          </AuthRoute>
        }
      />
      <Route
        path="/password/setup"
        element={
          <PublicAuthRoute>
            <PasswordSetupPage />
          </PublicAuthRoute>
        }
      />
      <Route
        path="/help/onboarding"
        element={<OnboardingGuidePage />}
      />
      <Route
        path="*"
        element={
          <BusinessRoute
            mockLoggedIn={mockLoggedIn}
            currentUser={currentUser}
            onLogout={onLogout}
          />
        }
      />
    </Routes>
  );
}

export default AppRoutes;
