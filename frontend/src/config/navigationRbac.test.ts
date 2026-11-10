import { describe, expect, it } from "vitest";
import { navigation } from "@/config/navigation";
import { getPagePermissionKey } from "@/shared/permissions/mockAccess";
import manifestSource from "../../../backend/app/modules/iam/navigation_permissions.json?raw";

interface ManifestPage {
  page_key: string;
  permission_key: string;
  name: string;
}
interface ManifestModule {
  module_key: string;
  name: string;
  pages: ManifestPage[];
}
const modules = (JSON.parse(manifestSource) as { modules: ManifestModule[] }).modules;
const registered = new Set(modules.flatMap((module) =>
  module.pages.map((page) => page.permission_key),
));

describe("navigation and RBAC catalogue share one generated registry", () => {
  it("covers every visible/disabled navigation permission", () => {
    const missing = navigation.flatMap((group) =>
      group.children.flatMap((page) => {
        if (page.status === "hidden") return [];
        const key = getPagePermissionKey(page);
        return registered.has(key) ? [] : [page.key + " => " + key];
      }),
    );
    expect(missing).toEqual([]);
  });

  it("makes finance FX rate access role-managed, not super-admin-only", () => {
    expect(registered.has("page:finance:fx-rates:view")).toBe(true);
    expect(registered.has("page:finance:cash-flow:view")).toBe(true);
  });

  it("preserves intentional sharing of existing menu permissions", () => {
    const pages = navigation.flatMap((group) => group.children);
    for (const key of ["finance_cash_accounts", "finance_cash_journal",
      "finance_cash_account_admin", "finance_cash_stock"]) {
      const page = pages.find((item) => item.key === key);
      expect(page).toBeDefined();
      expect(getPagePermissionKey(page!)).toBe("page:finance:cash-flow:view");
    }
  });
});
