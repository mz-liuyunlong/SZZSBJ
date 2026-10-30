// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { navigation } from "@/config/navigation";
import ComingSoonPage from "@/pages/ComingSoonPage";
import { resolveRoute } from "@/router/routeResolver";

const placeholders = [
  { key: "pmc_logistics", title: "物流", path: "/pmc/logistics" },
] as const;

describe("PMC placeholder pages", () => {
  it("keeps logistics alongside the non-routable domestic and WFS sections", () => {
    const pmc = navigation.find((group) => group.key === "pmc");

    expect(pmc?.children.map((page) => page.key)).toEqual([
      "pmc_purchase_board",
      "pmc_logistics", "pmc_domestic_batches", "pmc_packing_approval", "pmc_packing_warehouse",
      "pmc_wfs_pending_packing", "pmc_wfs_board", "pmc_wfs_exceptions", "pmc_wfs_settings",
    ]);
    for (const item of placeholders) {
      expect(pmc?.children.find((page) => page.key === item.key)).toMatchObject({
        title: item.title,
        path: item.path,
        status: "planned",
        readOnly: true,
        sourceTables: [],
      });
      expect(resolveRoute(item.path)).toMatchObject({
        kind: "allowed",
        route: { page: { key: item.key } },
      });
    }
  });

  it("shows the construction notice without business actions", () => {
    const pmc = navigation.find((group) => group.key === "pmc");
    for (const item of placeholders) {
      const page = pmc?.children.find((entry) => entry.key === item.key);
      if (!page) throw new Error(`${item.title} navigation entry is required`);

      const view = render(<ComingSoonPage page={page} />);
      expect(screen.getByRole("region", { name: item.title })).toBeInTheDocument();
      expect(screen.getByText("功能建设中")).toBeInTheDocument();
      expect(screen.getByText("此页面暂不请求业务数据，也不提供业务操作。")).toBeInTheDocument();
      expect(screen.queryByRole("button")).not.toBeInTheDocument();
      view.unmount();
    }
  });
});
