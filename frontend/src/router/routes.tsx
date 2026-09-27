import {
  Navigate,
  Route,
  Routes,
  useLocation,
  useNavigate,
} from 'react-router-dom'
import type { ReactNode } from 'react'
import AuthLayout from '@/layouts/auth/AuthLayout'
import MainLayout from '@/layouts/MainLayout'
import { readTabWorkspace } from '@/layouts/useTabWorkspace'
import ComingSoonPage from '@/pages/ComingSoonPage'
import ForgotPasswordPage from '@/pages/auth/ForgotPasswordPage'
import LoginPage from '@/pages/auth/LoginPage'
import NotFoundPage from '@/pages/errors/NotFoundPage'
import ListingManagementPage from '@/pages/products/ListingManagementPage'
import ProductManagementPage from '@/pages/products/ProductManagementPage'
import DailySalesPage from '@/pages/sales/DailySalesPage'
import OrderProfitPage from '@/pages/sales/OrderProfitPage'
import RefundManagementPage from '@/pages/aftersales/RefundManagementPage'
import OperationLogPage from '@/pages/operations/OperationLogPage'
import SyncTaskPage from '@/pages/data-center/SyncTaskPage'
import ApiDocsPage from '@/pages/data-center/ApiDocsPage'
import DataImportPage from '@/pages/data-center/DataImportPage'
import WfsFeeAlertPage from '@/pages/warehouse/WfsFeeAlertPage'
import PurchaseBoardPage from '@/pages/pmc/purchase-board/PurchaseBoardPage'
import UserManagementPage from "@/pages/settings/UserManagementPage";
import RoleManagementPage from "@/pages/settings/RoleManagementPage";
import FeeRulesPage from "@/pages/settings/FeeRulesPage";
import { DEFAULT_BUSINESS_PATH, resolveRoute } from '@/router/routeResolver'
import {
  DEFAULT_MOCK_AUTH_USER,
  type MockAuthUser,
} from "@/mocks/auth";
import { isMockPageAccessibleForRole } from "@/shared/permissions/mockAccess";

interface AppRoutesProps {
  mockLoggedIn: boolean
  currentUser?: MockAuthUser
  onLogin: (user: MockAuthUser) => void
  onLogout: () => void
}

function AuthRoute({
  children,
  mockLoggedIn,
}: {
  children: ReactNode
  mockLoggedIn: boolean
}) {
  return mockLoggedIn ? (
    <Navigate replace to={DEFAULT_BUSINESS_PATH} />
  ) : (
    <AuthLayout>{children}</AuthLayout>
  )
}

function LoginRoute({
  mockLoggedIn,
  onLogin,
}: Pick<AppRoutesProps, 'mockLoggedIn' | 'onLogin'>) {
  const navigate = useNavigate()

  return (
    <AuthRoute mockLoggedIn={mockLoggedIn}>
      <LoginPage
        onLogin={(user) => {
          const { activePath } = readTabWorkspace()
          onLogin(user)
          navigate(activePath, { replace: true })
        }}
      />
    </AuthRoute>
  )
}

function BusinessRoute({
  mockLoggedIn,
  currentUser,
  onLogout,
}: Pick<AppRoutesProps, 'mockLoggedIn' | 'currentUser' | 'onLogout'>) {
  const location = useLocation()
  const navigate = useNavigate()
  const resolution = resolveRoute(location.pathname)

  if (!mockLoggedIn) {
    return <Navigate replace to="/login" />
  }

  const activeUser = currentUser ?? DEFAULT_MOCK_AUTH_USER

  if (location.pathname === '/') {
    return <Navigate replace to={DEFAULT_BUSINESS_PATH} />
  }

  if (resolution.kind === 'unknown') {
    return <NotFoundPage />
  }

  if (resolution.kind === 'disabled') {
    return <Navigate replace to={DEFAULT_BUSINESS_PATH} />
  }

  if (!isMockPageAccessibleForRole(activeUser.role, resolution.route.page)) {
    return <Navigate replace to={DEFAULT_BUSINESS_PATH} />
  }

  return (
    <MainLayout
      currentUser={activeUser}
      onLogout={() => {
        onLogout()
        navigate('/login', { replace: true })
      }}
      renderPage={(page) =>
        page.key === 'products_product_management' ? (
          <ProductManagementPage page={page} preferenceScope={activeUser.username} />
        ) : page.key === 'products_listing_management' ? (
          <ListingManagementPage page={page} />
        ) : page.key === 'sales_daily_sales' ? (
          <DailySalesPage page={page} />
        ) : page.key === 'sales_order_profit' ? (
          <OrderProfitPage page={page} />
        ) : page.key === 'aftersales_refund_management' ? (
          <RefundManagementPage page={page} />
        ) : page.key === 'operations_log' ? (
          <OperationLogPage page={page} />
        ) : page.key === 'warehouse_wfs_fee_alert' ? (
          <WfsFeeAlertPage page={page} />
        ) : page.key === 'pmc_purchase_board' ? (
          <PurchaseBoardPage page={page} preferenceScope={activeUser.username} />
        ) : page.key === 'data_center_data_import' ? (
          <DataImportPage page={page} />
        ) : page.key === 'data_center_api_docs' ? (
          <ApiDocsPage page={page} />
        ) : page.key === 'data_center_task_center' ? (
          <SyncTaskPage page={page} />
        ) : page.key === 'settings_user_management' ? (
          <UserManagementPage page={page} />
        ) : page.key === 'settings_role_management' ? (
          <RoleManagementPage page={page} />
        ) : page.key === 'settings_fee_rules' ? (
          <FeeRulesPage page={page} />
        ) : (
          <ComingSoonPage page={page} />
        )
      }
    />
  )
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
  )
}

export default AppRoutes
