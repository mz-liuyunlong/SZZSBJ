// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { DailySalesSampleQuantityCell } from "@/pages/sales/components/DailySalesTable";
import type { DailySalesRow } from "@/pages/sales/dailySalesTypes";

afterEach(cleanup);

const row = (warnings: string[], sampleQuantity = 0) => ({
  sampleQuantity,
  calculationWarnings: warnings,
}) as DailySalesRow;

describe("daily sales sample evidence", () => {
  it("displays the current recorded quantity as zero when sample capture evidence is absent", () => {
    render(<DailySalesSampleQuantityCell row={row(["sample_data_not_observed"])} />);
    expect(screen.getByText("0")).toBeInTheDocument();
    expect(screen.queryByText("未知")).not.toBeInTheDocument();
  });

  it("shows unverified candidates as numeric quantity without a pending text label", () => {
    render(<DailySalesSampleQuantityCell row={row(["sample_verification_pending"])} />);
    expect(screen.getByText("0")).toBeInTheDocument();
    expect(screen.queryByText("待核验")).not.toBeInTheDocument();
  });

  it("shows only the verified quantity as a number", () => {
    render(<DailySalesSampleQuantityCell row={row([], 5)} />);
    expect(screen.getByText("5")).toBeInTheDocument();
  });
});
