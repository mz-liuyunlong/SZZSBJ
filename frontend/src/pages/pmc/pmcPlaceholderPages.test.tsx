import { describe, expect, it } from "vitest";
import { navigation } from "@/config/navigation";
import { getPagePermissionKey } from "@/shared/permissions/mockAccess";
import { resolveRoute } from "@/router/routeResolver";

const pmc = navigation.find((group) => group.key === "pmc")!;

describe("PMC navigation", () => {
  it("keeps the logistics section alongside the domestic and WFS sections", () => {
    expect(pmc.children.map((page) => page.key)).toEqual([
      "pmc_overview", "pmc_purchase_board",
      "pmc_logistics", "pmc_logistics_forecast", "pmc_logistics_alerts", "pmc_logistics_carriers",
      "pmc_domestic_batches", "pmc_packing_approval", "pmc_packing_warehouse",
      "pmc_wfs_pending_packing", "pmc_wfs_board", "pmc_wfs_exceptions", "pmc_wfs_settings",
      "pmc_wfs_settings_fc", "pmc_wfs_settings_defaults", "pmc_wfs_settings_channels", "pmc_logistics_settings", "pmc_wfs_settings_stores",
      "pmc_wfs_settings_notes",
    ]);
  });

  it("serves the 物流 section as four read-only sidebar leaves; 时效与阈值设置 is in PMC 设置 (Rocky 2026-11-03)", () => {
    expect(pmc.sidebarSections?.[0]).toEqual({ key: "pmc-logistics", title: "物流" });
    const pages = pmc.children.filter((p) => p.sidebarSection === "pmc-logistics");
    expect(pages.map((p) => [p.title, p.path])).toEqual([
      ["物流总览", "/pmc/logistics"],
      ["到货预测", "/pmc/logistics/forecast"],
      ["异常与提醒", "/pmc/logistics/alerts"],
      ["货代看板", "/pmc/logistics/carriers"],
    ]);
    for (const page of pages) {
      expect(page).toMatchObject({ status: "testing", readOnly: true, viewPermissionKey: "page:pmc:wfs:view" });
      expect(getPagePermissionKey(page)).toBe("page:pmc:wfs:view");
      expect(resolveRoute(page.path)).toMatchObject({ kind: "allowed", route: { page: { key: page.key } } });
    }
  });
});
