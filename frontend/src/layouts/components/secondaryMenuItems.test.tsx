import { describe, expect, it } from "vitest";
import { navigation } from "@/config/navigation";
import { isMockPageAccessibleForRole, isMockPageVisibleForRole } from "@/shared/permissions/mockAccess";
import {
  SECONDARY_MENU_HIDDEN_PAGE_KEYS,
  secondaryMenuItems,
} from "./secondaryMenuItems";

const expected = {
  products: [
    "products_product_management",
    "products_listing_management",
    "products_clearance_center",
    "products_new_product_analysis",
  ],
  sales: [
    "sales_daily_sales",
    "sales_order_profit",
  ],
  aftersales: [
    "aftersales_refund_management",
  ],
  warehouse: [
    "warehouse_wfs_fee_alert",
    "warehouse_removal_disposal",
    "warehouse_inbound_difference",
    "warehouse_inventory_age",
  ],
  operations: [
    "operations_log",
    "operations_plan",
  ],
  finance: [
    "finance_profit_center",
    "finance_sku_cash_profit",
    "finance_settlement_profit",
    "finance_settlement_reconciliation",
    "finance_performance_report",
    "finance_balance_sheet",
    "finance-cash",
    "finance-settings",
    "finance_cost_exception",
    "finance_settings",
    "finance_data_import",
  ],
};

describe("secondary menu cleanup", () => {
  it("hides exactly 21 requested menu entries", () => {
    expect(SECONDARY_MENU_HIDDEN_PAGE_KEYS.size).toBe(21);
  });

  it.each(Object.entries(expected))(
    "shows the expected entries for %s",
    (groupKey, expectedKeys) => {
      const group = navigation.find(
        (item) => item.key === groupKey,
      );

      expect(group).toBeDefined();
      if (!group) return;

      const items = secondaryMenuItems(group, group.children);

      const keys = (items ?? []).flatMap((item) =>
        item && "key" in item
          ? [String(item.key)]
          : [],
      );

      expect(keys).toEqual(expectedKeys);
    },
  );

  it("places the finance cash-flow section after the balance sheet with its 3 pages in order (异常 removed)", () => {
    const group = navigation.find((item) => item.key === "finance");
    expect(group).toBeDefined();
    if (!group) return;
    const section = (secondaryMenuItems(group, group.children) ?? []).find(
      (item) => item && "key" in item && item.key === "finance-cash",
    );
    const children = section && "children" in section ? section.children ?? [] : [];
    expect(children.flatMap((item) => (item && "key" in item ? [String(item.key)] : []))).toEqual([
      "finance_cash_accounts",
      "finance_cash_journal",
      "finance_cash_stock",
    ]);
  });

  it("lists the exchange-rate page under the finance settings section", () => {
    const group = navigation.find((item) => item.key === "finance");
    if (!group) throw new Error("finance group missing");
    const section = (secondaryMenuItems(group, group.children) ?? []).find(
      (item) => item && "key" in item && item.key === "finance-settings",
    );
    const children = section && "children" in section ? section.children ?? [] : [];
    expect(children.flatMap((item) => (item && "key" in item ? [String(item.key)] : []))).toEqual(["finance_fx_rates"]);
  });

  it("shows the exchange-rate page to super admins only, even for finance users", () => {
    const group = navigation.find((item) => item.key === "finance");
    if (!group) throw new Error("finance group missing");
    const fxPage = group.children.find((item) => item.key === "finance_fx_rates");
    if (!fxPage) throw new Error("fx page missing");
    const financeUser = ["page:finance:cash-flow:view", "finance:read"];
    expect(isMockPageVisibleForRole("user", fxPage, financeUser)).toBe(false);
    expect(isMockPageAccessibleForRole("user", fxPage, financeUser)).toBe(false);
    expect(isMockPageVisibleForRole("admin", fxPage, ["*"])).toBe(true);
    expect(isMockPageAccessibleForRole("admin", fxPage, ["*"])).toBe(true);

    const keysFor = (permissions: string[]) =>
      (secondaryMenuItems(group, group.children.filter((item) => isMockPageVisibleForRole("user", item, permissions))) ?? [])
        .flatMap((item) => (item && "key" in item ? [String(item.key)] : []));
    expect(keysFor(financeUser)).toContain("finance-cash");
    expect(keysFor(financeUser)).not.toContain("finance-settings");
    expect(keysFor(["*"])).toContain("finance-settings");
  });

  it("restores operation logs and hides calendar only in the secondary menu", () => {
    expect(SECONDARY_MENU_HIDDEN_PAGE_KEYS.has("operations_log")).toBe(false);
    expect(SECONDARY_MENU_HIDDEN_PAGE_KEYS.has("operations_calendar")).toBe(true);
    const pages = navigation.flatMap((group) => group.children);
    expect(pages.find((page) => page.key === "operations_log")?.path).toBe("/operations/log");
    expect(pages.find((page) => page.key === "operations_calendar")?.path).toBe("/operations/calendar");
  });

  it("preserves the original page route metadata", () => {
    const pages = navigation.flatMap(
      (group) => group.children,
    );

    for (const key of SECONDARY_MENU_HIDDEN_PAGE_KEYS) {
      expect(pages.find((page) => page.key === key))
        .toBeDefined();
    }
  });

  it("does not hide the independent PMC module", () => {
    const group = navigation.find(
      (item) => item.key === "pmc",
    );

    expect(group).toBeDefined();
    if (!group) return;

    const items = secondaryMenuItems(group, group.children);

    expect(items?.some(
      (item) =>
        item &&
        "key" in item &&
        item.key === "pmc_purchase_board",
    )).toBe(true);
  });
});
