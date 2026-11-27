import { describe, expect, it } from "vitest";
import { decodeReportTableTotals, reportTotalValue } from "./reportTotals";

describe("full-filter report footer", () => {
  const totals = decodeReportTableTotals({
    usd: { sales_qty: "1280", sales_amount: "10000.00", order_profit: "-30", purchase_cost_total: null, sample_qty: "0", wfs_inventory: "100" },
    cny: { sales_qty: "1280", sales_amount: "66010.00", order_profit: "-200", purchase_cost_total: null, sample_qty: "0", wfs_inventory: "100" },
    sample_evidence: "pending",
  });
  it("uses the server values in both currencies, including exact zero and negatives", () => {
    expect(reportTotalValue(totals, "USD", "salesVolume")).toBe(1280);
    expect(reportTotalValue(totals, "CNY", "salesVolume")).toBe(1280);
    expect(reportTotalValue(totals, "USD", "salesAmount")).toBe(10000);
    expect(reportTotalValue(totals, "CNY", "salesAmount")).toBe(66010);
    expect(reportTotalValue(totals, "USD", "orderProfit")).toBe(-30);
    expect(reportTotalValue(totals, "USD", "sampleQuantity")).toBe(0);
    expect(reportTotalValue(totals, "USD", "wfsAvailableInventory")).toBe(100);
    expect(totals?.sampleEvidence).toBe("pending");
  });
  it("never substitutes current page values or zero for missing totals", () => {
    expect(reportTotalValue(totals, "USD", "purchaseCost")).toBeNull();
    expect(reportTotalValue(totals, "USD", "returnRate30Days")).toBeNull();
    expect(reportTotalValue(null, "USD", "salesVolume")).toBeNull();
    expect(reportTotalValue(totals, "USD", "skuMsku")).toBeNull();
  });
});
