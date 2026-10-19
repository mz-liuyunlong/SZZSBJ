import { describe, expect, it } from "vitest";
import { resolveOperationLogLink } from "@/pages/operations/operationLogLinks";
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
  it("opens safe internal routes and external HTTPS destinations", () => {
    expect(resolveOperationLogLink("/ads/keyword-library")).toBe("/ads/keyword-library");
    expect(resolveOperationLogLink("https://example.com/ads")).toBe("https://example.com/ads");
    expect(resolveOperationLogLink("  /ads/search-terms  ")).toBe("/ads/search-terms");
  });

  it.each([
    "", "relative/path", "//evil.example/path", "javascript:alert(1)",
    "data:text/html,bad", "https://user:pass@example.com/",
    "https://example.com/\\nnext",
  ])("rejects unsafe shortcut URL: %s", (url) => {
    expect(resolveOperationLogLink(url)).toBeNull();
  });

  it("defaults to today and product ID search", () => {
    const filters = createOperationLogInitialFilters();

    expect(filters.dateRange).toEqual(createOperationLogDateRange("today"));
    expect(filters.searchField).toBe("productId");
  });

  it("filters locally by product ID and system-log state", () => {
    const rowWithSystem = operationLogRows.find((row) => row.systemLogCount > 0);
    expect(rowWithSystem).toBeDefined();

    const result = filterOperationLogRows(operationLogRows, {
      ...createOperationLogInitialFilters(),
      dateRange: ["2026-09-01", "2026-09-30"],
      keyword: rowWithSystem?.productId.slice(0, 8) ?? "",
      systemLog: "has",
    });

    expect(result.length).toBeGreaterThan(0);
    expect(result.every((row) => row.systemLogCount > 0)).toBe(true);
  });

  it("creates system draft text from matched records", () => {
    const rowWithSystem = operationLogRows.find((row) => row.systemLogCount > 0);
    const records = operationSystemRecords.filter((record) => record.productId === rowWithSystem?.productId);

    expect(createSystemDraft(records)).toContain("系统检测");
    expect(createSystemDraft([])).toBe("系统未抓到调整记录，待人工确认。");
  });
});
