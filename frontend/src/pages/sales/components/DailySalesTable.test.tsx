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
  it("does not present missing capture evidence as a confirmed zero", () => {
    render(<DailySalesSampleQuantityCell row={row(["sample_data_not_observed"])} />);
    expect(screen.getByText("未知")).toBeInTheDocument();
    expect(screen.queryByText("0")).not.toBeInTheDocument();
  });

  it("shows unverified candidates as pending", () => {
    render(<DailySalesSampleQuantityCell row={row(["sample_verification_pending"])} />);
    expect(screen.getByText("待核验")).toBeInTheDocument();
  });

  it("shows only the verified quantity as a number", () => {
    render(<DailySalesSampleQuantityCell row={row([], 5)} />);
    expect(screen.getByText("5")).toBeInTheDocument();
  });
});
