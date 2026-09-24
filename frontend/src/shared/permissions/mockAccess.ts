import type { NavigationPage } from "@/config/navigation";
import type { MockUserRole } from "@/mocks/auth";

export const USER_VISIBLE_PAGE_KEYS = new Set([
  "products_product_management",
  "products_listing_management",
  "sales_daily_sales",
  "sales_order_profit",
  "aftersales_refund_management",
  "operations_log",
  "warehouse_wfs_fee_alert",
  "pmc_purchase_board",
  "data_center_data_import",
  "data_center_api_docs",
  "data_center_task_center",
  "settings_user_management",
  "settings_role_management",
  "settings_fee_rules",
]);

export function isMockImplementedPage(page: NavigationPage) {
  return USER_VISIBLE_PAGE_KEYS.has(page.key);
}

export function isMockPageVisibleForRole(role: MockUserRole, page: NavigationPage) {
  if (page.status === "hidden") return false;
  if (role === "admin") return true;
  return page.status !== "disabled" && isMockImplementedPage(page);
}

export function isMockPageAccessibleForRole(role: MockUserRole, page: NavigationPage) {
  if (page.status === "disabled") return false;
  if (role === "admin") return true;
  return page.status !== "hidden" && isMockImplementedPage(page);
}
