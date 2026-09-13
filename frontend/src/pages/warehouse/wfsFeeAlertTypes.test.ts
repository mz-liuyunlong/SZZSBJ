import { describe, expect, it } from "vitest";
import { wfsFeeAlertRows } from "@/pages/warehouse/wfsFeeAlertMockData";
import {
  createWfsFeeAlertInitialFilters,
  filterWfsFeeAlertRows,
  getPendingWfsAmount,
  getWfsFeeAlertSummary,
} from "@/pages/warehouse/wfsFeeAlertTypes";

describe("wfsFeeAlertTypes", () => {
  it("calculates WFS overcharge summary with fixed no-API rows", () => {
    const summary = getWfsFeeAlertSummary(wfsFeeAlertRows);

    expect(wfsFeeAlertRows).toHaveLength(12);
    expect(summary.alertSkuCount).toBe(12);
    expect(summary.totalOverFee).toBeCloseTo(1248.7);
    expect(summary.totalRecoveredAmount).toBeCloseTo(347.8);
    expect(summary.pendingAmount).toBeCloseTo(900.9);
    expect(summary.openedCaseCount).toBe(9);
    expect(summary.unopenedCaseCount).toBe(3);
  });

  it("filters locally by store, status, reason and search field", () => {
    const filters = {
      ...createWfsFeeAlertInitialFilters(),
      stores: ["美国一店"],
      statuses: ["跟进中"],
      reasons: ["尺寸重量异常"],
      searchField: "sku" as const,
      keyword: "KIT-BAKE",
    };

    const rows = filterWfsFeeAlertRows(wfsFeeAlertRows, filters);

    expect(rows).toHaveLength(1);
    expect(rows[0].sku).toBe("KIT-BAKE-001");
    expect(getPendingWfsAmount(rows[0])).toBeCloseTo(160.8);
  });
});
