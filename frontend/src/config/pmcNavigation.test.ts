import { describe, expect, it } from "vitest";
import { navigation, navigationRedirects } from "./navigation";
import { resolveRoute } from "@/router/routeResolver";
import { restoreTabWorkspace, TAB_WORKSPACE_VERSION } from "@/layouts/useTabWorkspace";
import { getPagePermissionKey, isMockPageAccessibleForRole } from "@/shared/permissions/mockAccess";

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
  it("opens each WFS leaf from the sidebar with one shared page permission", () => {
    const pages = pmc.children.filter((p) => p.sidebarSection === "pmc-wfs");
    expect(pages.map((p) => p.title)).toEqual([
      "待发货打包单", "WFS 货件看板", "异常中心",
    ]);
    expect(pmc.children.filter((p) => p.status === "disabled")).toHaveLength(0);
    for (const page of pages) {
      expect(page.status).toBe(page.key === "pmc_wfs_pending_packing" ? "testing" : "building");
      expect(getPagePermissionKey(page)).toBe("page:pmc:wfs:view");
      expect(isMockPageAccessibleForRole("user", page, ["page:pmc:wfs:view"])).toBe(true);
      expect(isMockPageAccessibleForRole("user", page, [])).toBe(false);
      expect(resolveRoute(page.path).kind).toBe("allowed");
    }
  });
  it("groups settings under PMC 设置, one sidebar leaf and tab per section", () => {
    expect(pmc.sidebarSections?.map((s) => s.title)).toEqual(["物流", "国内仓", "WFS", "PMC 设置"]);
    const pages = pmc.children.filter((p) => p.sidebarSection === "pmc-settings");
    expect(pages.map((p) => p.title)).toEqual([
      "WFS 异常与提醒规则", "WFS 仓库地区", "WFS 创建货件默认值", "物流渠道字典", "物流 时效与阈值设置", "WFS 店铺设置", "WFS 通知与口径说明",
    ]);
    expect(new Set(pages.map((p) => p.path)).size).toBe(pages.length);
    for (const page of pages) expect(page.path.startsWith("/pmc/settings/")).toBe(true);
    expect(navigationRedirects["/pmc/wfs/settings"]).toBe("/pmc/settings/wfs/rules");
    expect(navigationRedirects["/pmc/wfs/settings/fc-regions"]).toBe("/pmc/settings/wfs/fc-regions");
    for (const page of pages) {
      expect(page.readOnly).toBe(true);
      expect(getPagePermissionKey(page)).toBe("page:pmc:wfs:view");
      expect(isMockPageAccessibleForRole("user", page, ["page:pmc:wfs:view"])).toBe(true);
      expect(isMockPageAccessibleForRole("user", page, [])).toBe(false);
      expect(resolveRoute(page.path)).toMatchObject({ kind: "allowed", route: { page: { key: page.key } } });
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
