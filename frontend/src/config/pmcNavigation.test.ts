import { describe, expect, it } from "vitest";
import { navigation, navigationRedirects } from "./navigation";
import { resolveRoute } from "@/router/routeResolver";
import { restoreTabWorkspace, TAB_WORKSPACE_VERSION } from "@/layouts/useTabWorkspace";
import { getPagePermissionKey, isMockPageAccessibleForRole, isMockPageVisibleForRole } from "@/shared/permissions/mockAccess";

const pmc = navigation.find((g) => g.key === "pmc")!;
const grants = ["page:pmc:domestic-warehouse-board:view"];
describe("PMC navigation contract", () => {
  it("preserves existing domestic grants while splitting page routes", () => {
    const pages = pmc.children.filter((p) => p.sidebarSection === "pmc-domestic" && p.status !== "disabled");
    expect(pages.map((p) => p.title)).toEqual(["批次看板", "打包单审批", "打包单（仓库）"]);
    for (const page of pages) {
      expect(getPagePermissionKey(page)).toBe(grants[0]);
      expect(isMockPageAccessibleForRole("user", page, grants)).toBe(true);
      expect(isMockPageAccessibleForRole("user", page, [])).toBe(false);
    }
  });
  it("shows planned leaves only to authorized users and never makes them routable", () => {
    const planned = pmc.children.filter((p) => p.status === "disabled");
    expect(planned).toHaveLength(2);
    for (const page of planned) {
      expect(isMockPageVisibleForRole("user", page, ["*"])).toBe(true);
      expect(isMockPageVisibleForRole("user", page, [])).toBe(false);
      expect(isMockPageAccessibleForRole("user", page, ["*"])).toBe(false);
      expect(resolveRoute(page.path).kind).toBe("disabled");
    }
  });
  it("does not restore removed container tabs or register navigable groups", () => {
    expect(navigationRedirects["/pmc/domestic-warehouse-board"]).toBe("/pmc/domestic/batches");
    expect(resolveRoute("/pmc/domestic-warehouse-board").kind).toBe("unknown");
    expect(resolveRoute("/pmc/wfs").kind).toBe("unknown");
    const restored = restoreTabWorkspace(JSON.stringify({ version: TAB_WORKSPACE_VERSION,
      openPaths: ["/pmc/domestic-warehouse-board", "/pmc/wfs", "/pmc/domestic/packing-approval"],
      activePath: "/pmc/domestic/packing-approval" }));
    expect(restored.openPaths).not.toContain("/pmc/domestic-warehouse-board");
    expect(restored.openPaths).not.toContain("/pmc/wfs");
    expect(restored.activePath).toBe("/pmc/domestic/packing-approval");
  });
});
