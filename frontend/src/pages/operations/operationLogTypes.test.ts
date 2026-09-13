import { describe, expect, it } from "vitest";
import {
  createOperationLogDateRange,
  createOperationLogInitialFilters,
  createSystemDraft,
  filterOperationLogRows,
} from "@/pages/operations/operationLogTypes";
import {
  operationLogRows,
  operationSystemRecords,
} from "@/pages/operations/operationLogMockData";

describe("operation log helpers", () => {
  it("defaults to today and product ID search", () => {
    const filters = createOperationLogInitialFilters();

    expect(filters.dateRange).toEqual(["2026-09-13", "2026-09-13"]);
    expect(filters.searchField).toBe("productId");
  });

  it("filters locally by product ID and system-log state", () => {
    const rowWithSystem = operationLogRows.find((row) => row.systemLogCount > 0);
    expect(rowWithSystem).toBeDefined();

    const result = filterOperationLogRows(operationLogRows, {
      ...createOperationLogInitialFilters(),
      dateRange: createOperationLogDateRange("last30"),
      keyword: rowWithSystem?.productId.slice(0, 8) ?? "",
      systemLog: "has",
    });

    expect(result.length).toBeGreaterThan(0);
    expect(result.every((row) => row.systemLogCount > 0)).toBe(true);
  });

  it("creates system draft text from matched records", () => {
    const rowWithSystem = operationLogRows.find((row) => row.systemLogCount > 0);
    const records = operationSystemRecords.filter((record) => record.productId === rowWithSystem?.productId);

    expect(createSystemDraft(records)).toContain("调整人");
    expect(createSystemDraft([])).toBe("系统未抓到调整记录，待人工确认。");
  });
});
