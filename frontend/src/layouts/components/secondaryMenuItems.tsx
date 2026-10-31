/** Navigation-only sections remain non-routable; leaf permissions are filtered by MainLayout. */
import type { MenuProps } from "antd";
import type { NavigationGroup, NavigationPage } from "@/config/navigation";
import { isRoutableStatus } from "@/router/routeResolver";


/**
 * Hide selected entries only from the second-level menu.
 * Routes, permissions and page implementations remain unchanged.
 */
export const SECONDARY_MENU_HIDDEN_PAGE_KEYS =
  new Set<string>([
    // Products
    "products_lifecycle",
    "products_grade",
    "products_claim_center",

    // Sales
    "sales_review_dashboard",
    "sales_restock_suggestion",
    "sales_shipping_plan",
    "sales_trend",

    // After-sales
    "aftersales_return_management",
    "aftersales_customer_messages",
    "aftersales_case_management",
    "aftersales_claims",
    "aftersales_negative_feedback",
    "aftersales_statistics",

    // Warehouse
    "warehouse_inventory_alert",
    "warehouse_inventory_detail",
    "warehouse_storage_fee",
    "warehouse_inbound_transport",
    "warehouse_pmc_dashboard",

    // Operations
    "operations_todo",
    "operations_log",
    "operations_promotion_center",
  ]);

export function secondaryMenuItems(group: NavigationGroup, pages: NavigationPage[]): MenuProps["items"] {
  const leaf = (page: NavigationPage) => ({
    key: page.key,
    className: page.sidebarSection ? "main-layout__section-leaf" : undefined,
    label: page.description || page.showWhenDisabled ? <span className="main-layout__menu-label"><span>{page.title}</span>{page.description && <small>{page.description}</small>}{page.status === "disabled" && <small>待开发</small>}</span> : page.title,
    disabled: !isRoutableStatus(page.status),
  });
  const visiblePages = pages.filter(
    (page) => !SECONDARY_MENU_HIDDEN_PAGE_KEYS.has(page.key),
  );
  const root = visiblePages.filter(
    (p) => !p.sidebarSection,
  ).map(leaf);
  const sections = (group.sidebarSections ?? []).flatMap((section) => {
    const children = visiblePages.filter(
      (p) => p.sidebarSection === section.key,
    ).map(leaf);
    return children.length ? [{ type: "group" as const, key: section.key, className: "main-layout__menu-section", label: section.title, children }] : [];
  });
  return [...root, ...sections];
}
