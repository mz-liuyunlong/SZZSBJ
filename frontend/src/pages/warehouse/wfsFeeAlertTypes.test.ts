import { describe, expect, it } from "vitest";
import { wfsFeeAlertRows } from "@/pages/warehouse/wfsFeeAlertMockData";
import {
  createWfsFeeAlertInitialFilters,
  defaultWfsDetectionWindow,
  filterWfsFeeAlertRows,
  getPendingWfsAmount,
  getWfsFeeAlertSummary,
  wfsFeeAlertColumnFields,
  fixedWfsFeeAlertColumnKeys,
} from "@/pages/warehouse/wfsFeeAlertTypes";

describe("wfsFeeAlertTypes", () => {
  it("builds the default T-2 60-day window from Los Angeles business time", () => {
    expect(defaultWfsDetectionWindow(new Date("2026-10-20T06:30:00Z"))).toEqual([
      "2026-08-19",
      "2026-10-17",
    ]);
  });
  it("combines SKU and MSKU into one fixed table column", () => {
    const keys = wfsFeeAlertColumnFields.map((field) => field.key);
    expect(keys.slice(0, 3)).toEqual([
      "image",
      "productIdName",
      "skuMsku",
    ]);
    expect(keys).not.toContain("sku");
    expect(keys).not.toContain("msku");
    expect(fixedWfsFeeAlertColumnKeys).toEqual(["image", "productIdName", "skuMsku"]);
  });

  it("calculates WFS overcharge summary with fixed no-API rows", () => {
    const summary = getWfsFeeAlertSummary(wfsFeeAlertRows);

    expect(wfsFeeAlertRows).toHaveLength(100);
    expect(summary.alertSkuCount).toBe(100);
    expect(summary.totalOverFee).toBeCloseTo(
      wfsFeeAlertRows.reduce((total, row) => total + row.overFee, 0),
    );
    expect(summary.totalRecoveredAmount).toBeCloseTo(
      wfsFeeAlertRows.reduce((total, row) => total + row.recoveredAmount, 0),
    );
    expect(summary.openedCaseCount).toBe(wfsFeeAlertRows.filter((row) => row.caseNo).length);
    expect(summary.unopenedCaseCount).toBe(100 - summary.openedCaseCount);
  });

  it("filters locally by store, status, reason and search field", () => {
    const filters = {
      ...createWfsFeeAlertInitialFilters(),
      dateRange: ["2026-09-01", "2026-09-30"] as [string, string],
      stores: ["美国一店"],
      statuses: ["跟进中"],
      reasons: ["尺寸重量异常"],
      searchField: "sku" as const,
      keyword: "KIT-BAKE",
    };

    const rows = filterWfsFeeAlertRows(wfsFeeAlertRows, filters);

    expect(rows).toHaveLength(9);
    expect(rows[0].sku).toBe("KIT-BAKE-001-001");
    expect(rows.every((row) => row.store === "美国一店"
      && row.status === "跟进中"
      && row.reason === "尺寸重量异常"
      && row.sku.includes("KIT-BAKE"))).toBe(true);
    expect(getPendingWfsAmount(rows[0])).toBeCloseTo(160.8);
  });
});
