import { describe, expect, it } from "vitest";
import { navigation } from "@/config/navigation";
import { resolveRoute } from "@/router/routeResolver";

describe("PMC navigation", () => {
  it("keeps logistics alongside the domestic and WFS sections", () => {
    const pmc = navigation.find((group) => group.key === "pmc");

    expect(pmc?.children.map((page) => page.key)).toEqual([
      "pmc_purchase_board",
      "pmc_logistics", "pmc_domestic_batches", "pmc_packing_approval", "pmc_packing_warehouse",
      "pmc_wfs_pending_packing", "pmc_wfs_board", "pmc_wfs_exceptions", "pmc_wfs_settings",
      "pmc_wfs_settings_fc", "pmc_wfs_settings_defaults", "pmc_wfs_settings_channels", "pmc_wfs_settings_stores",
      "pmc_wfs_settings_notes",
    ]);
  });

  it("serves logistics as a read-only testing page (8088 logistics board, no longer a placeholder)", () => {
    const page = navigation.find((group) => group.key === "pmc")?.children.find((p) => p.key === "pmc_logistics");
    expect(page).toMatchObject({
      title: "物流",
      path: "/pmc/logistics",
      status: "testing",
      readOnly: true,
      viewPermissionKey: "page:pmc:wfs:view",
    });
    expect(resolveRoute("/pmc/logistics")).toMatchObject({ kind: "allowed", route: { page: { key: "pmc_logistics" } } });
  });
});
