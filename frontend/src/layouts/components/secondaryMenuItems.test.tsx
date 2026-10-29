import { describe, expect, it } from "vitest";
import { navigation } from "@/config/navigation";
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
    "operations_plan",
    "operations_calendar",
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
