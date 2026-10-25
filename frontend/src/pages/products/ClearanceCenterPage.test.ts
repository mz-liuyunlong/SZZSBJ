import { describe, it, expect } from "vitest";
import { navigation } from "@/config/navigation";
import { resolveRoute } from "@/router/routeResolver";
import { getPagePermissionKey } from "@/shared/permissions/mockAccess";

describe("clearance center demo route", () => {
  it("appears exactly once in Products navigation and resolves", () => {
    const page = navigation.find(g => g.key === "products")?.children.find(p => p.key === "products_clearance_center");
    expect(page).toMatchObject({ title: "清货中心", path: "/products/clearance-center", readOnly: true, status: "testing" });
    expect(page && getPagePermissionKey(page)).toBe("page:products:product-management:view");
    expect(resolveRoute("/products/clearance-center").kind).toBe("allowed");
  });
});
