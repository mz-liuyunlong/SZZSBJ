import { describe, expect, it } from "vitest";
import { navigation } from "@/config/navigation";
import { getPagePermissionKey } from "@/shared/permissions/mockAccess";
import backendCatalogSource from "../../../backend/app/modules/iam/permission_catalog_v2.py?raw";

// Backend deploys separately. Reject new menu pages without a registered grant.
const catalogSource = backendCatalogSource;
const registeredPages = new Set(
  Array.from(
    catalogSource.matchAll(/_page\(\s*"([^"]+)"\s*,\s*"([^"]+)"\s*,/g),
    ([, moduleKey, localKey]) =>
      `page:${moduleKey.replaceAll("_", "-")}:${localKey.replaceAll("_", "-")}:view`,
  ),
);
const superAdminOnly = new Set(["page:finance:fx-rates:view"]);

describe("navigation/RBAC catalog contract", () => {
  it("registers every grantable navigation permission", () => {
    const missing = navigation.flatMap((group) =>
      group.children.flatMap((page) => {
        if (page.status === "hidden" || page.status === "disabled") return [];
        const key = getPagePermissionKey(page);
        if (registeredPages.has(key) || superAdminOnly.has(key)) return [];
        return [`${group.title} / ${page.title}: ${key}`];
      }),
    );
    expect(missing).toEqual([]);
  });

  it("keeps finance FX rates outside normal role grants", () => {
    const fxRates = navigation
      .flatMap((group) => group.children)
      .find((page) => page.key === "finance_fx_rates");
    expect(fxRates).toBeDefined();
    expect(getPagePermissionKey(fxRates!)).toBe("page:finance:fx-rates:view");
    expect(registeredPages.has("page:finance:fx-rates:view")).toBe(false);
  });

  it("keeps shared finance and domestic PMC page grants", () => {
    const pages = navigation.flatMap((group) => group.children);
    const groups = [
      [["finance_cash_accounts", "finance_cash_journal",
        "finance_cash_account_admin", "finance_cash_stock"], "page:finance:cash-flow:view"],
      [["pmc_domestic_batches", "pmc_packing_approval",
        "pmc_packing_warehouse"], "page:pmc:domestic-warehouse-board:view"],
    ] as const;
    for (const [pageKeys, expectedPermission] of groups) {
      for (const pageKey of pageKeys) {
        const page = pages.find((item) => item.key === pageKey);
        expect(page).toBeDefined();
        expect(getPagePermissionKey(page!)).toBe(expectedPermission);
      }
    }
  });
});
