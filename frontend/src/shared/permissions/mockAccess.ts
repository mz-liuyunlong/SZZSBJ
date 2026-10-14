import type { NavigationPage } from "@/config/navigation";
import type { MockUserRole } from "@/mocks/auth";

const PAGE_PERMISSION_OVERRIDES: Partial<Record<string, string>> = {
  products_product_management: "products:read",
  products_listing_management: "products:read",
  sales_daily_sales: "sales:daily-sales:read",
  sales_order_profit: "sales:daily-sales:read",
  aftersales_refund_management: "aftersales:refund-management:read",
  operations_log: "operations:plan:read",
  operations_plan: "operations:plan:read",
  warehouse_wfs_fee_alert: "warehouse:wfs-fee-alert:read",
  pmc_purchase_board: "pmc:purchase:read",
  data_center_data_import: "integrations:read",
  data_center_api_docs: "integrations:read",
  data_center_task_center: "integrations:read",
  settings_user_management: "settings:users:read",
  settings_role_management: "settings:roles:read",
  settings_fee_rules: "business-rules:read",
};

export function isMockImplementedPage(page: NavigationPage) {
  return page.status !== "hidden" && page.status !== "disabled";
}

export function getPagePermissionKey(page: NavigationPage) {
  return PAGE_PERMISSION_OVERRIDES[page.key] ?? page.permissionKey;
}

export function hasPermission(
  permissions: readonly string[] | undefined,
  permissionKey: string,
) {
  return Boolean(
    permissions?.includes("*") || permissions?.includes(permissionKey),
  );
}

export function isMockPageVisibleForRole(
  role: MockUserRole,
  page: NavigationPage,
  permissions?: readonly string[],
) {
  if (page.status === "hidden" || page.status === "disabled") return false;
  if (role === "admin" || hasPermission(permissions, "*")) return true;
  return isMockImplementedPage(page) && hasPermission(permissions, getPagePermissionKey(page));
}

export function isMockPageAccessibleForRole(
  role: MockUserRole,
  page: NavigationPage,
  permissions?: readonly string[],
) {
  if (page.status === "disabled") return false;
  if (role === "admin" || hasPermission(permissions, "*")) return true;
  if (page.status === "hidden") return false;
  return isMockImplementedPage(page) && hasPermission(permissions, getPagePermissionKey(page));
}
