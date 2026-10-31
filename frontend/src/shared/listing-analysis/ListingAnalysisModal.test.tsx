// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ListingAnalysisModal } from "./ListingAnalysisModal";

vi.mock("echarts-for-react", () => ({ default: () => null }));

afterEach(cleanup);

describe("Listing analysis business data boundary", () => {
  it("never renders prototype metrics for a real product without verified facts", () => {
    render(
      <ListingAnalysisModal
        open
        onClose={() => undefined}
        source={{ productId: "SYNTHETIC-ITEM", title: "Synthetic product" }}
      />,
    );

    expect(screen.getByRole("status")).toHaveTextContent("尚无经过核实的经营分析数据");
    expect(screen.queryByText("Multipurpose Storage Bags")).not.toBeInTheDocument();
    expect(screen.queryByText("AX1042")).not.toBeInTheDocument();
  });

  it("shows only verified fields when they are available", () => {
    render(
      <ListingAnalysisModal
        open
        onClose={() => undefined}
        source={{ productId: "SYNTHETIC-ITEM" }}
        verifiedListing={{
          sales30Days: 4,
          adSpend30Days: null,
          salePrice: 12.5,
          priceCurrency: "",
          wfsAvailableInventory: 0,
          monitorObservedAt: null,
        }}
      />,
    );

    expect(screen.getByText("币种未知 12.50")).toBeInTheDocument();
    expect(screen.getByText("未监控")).toBeInTheDocument();
    expect(screen.getByText("未同步")).toBeInTheDocument();
  });
});
