import { describe, expect, it } from "vitest";
import { navigation } from "@/config/navigation";
import { isMockPageAccessibleForRole, isMockPageVisibleForRole } from "@/shared/permissions/mockAccess";

const pages = navigation.find((group) => group.key === "finance")?.children ?? [];

describe("finance entries follow permissions", () => {
  it("shows no finance entry and opens no finance page without a permission", () => {
    expect(pages.length).toBeGreaterThan(0);
    pages.forEach((page) => {
      expect(isMockPageVisibleForRole("user", page, [])).toBe(false);
      expect(isMockPageAccessibleForRole("user", page, [])).toBe(false);
      expect(isMockPageVisibleForRole("user", page, undefined)).toBe(false);
    });
  });

  it("does not open the cash pages for someone who only has another finance page", () => {
    const cash = pages.filter((page) => page.key.startsWith("finance_cash_"));
    expect(cash.length).toBeGreaterThan(0);
    cash.forEach((page) => expect(isMockPageAccessibleForRole("user", page, ["page:finance:profit-center:view"])).toBe(false));
  });

  it("opens the cash pages for a super admin", () => {
    pages.filter((page) => page.key.startsWith("finance_cash_")).forEach((page) => {
      expect(isMockPageAccessibleForRole("admin", page, ["*"])).toBe(true);
    });
  });
});
