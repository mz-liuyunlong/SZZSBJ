// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import OperationLogTable from "@/pages/operations/components/OperationLogTable";
import { operationLogRows } from "@/pages/operations/operationLogMockData";
import type { OperationLogRow } from "@/pages/operations/operationLogTypes";

afterEach(() => { cleanup(); vi.restoreAllMocks(); });

function props(row: OperationLogRow) {
  return {
    rows: [row],
    systemRecords: [],
    appliedColumnKeys: ["productIdShortcut"],
    columnWidths: {},
    currentPage: 1,
    pageSize: 50,
    selectedRowKeys: [],
    onColumnWidthChange: vi.fn(),
    onCurrentPageChange: vi.fn(),
    onPageSizeChange: vi.fn(),
    onSelectionChange: vi.fn(),
    onCopy: vi.fn(),
    onOpenProduct: vi.fn(),
    onOpenEntryEditor: vi.fn(),
    onManualLogChange: vi.fn(),
    onSaveRow: vi.fn(),
    onViewEntries: vi.fn(),
    onBulkSaveDraft: vi.fn(),
    onSubmitAll: vi.fn(),
  };
}

describe("operation log shortcut clicks", () => {
  it("opens an internal route when its saved URL updates the row", () => {
    const open = vi.spyOn(window, "open").mockImplementation(() => null);
    const original: OperationLogRow = {
      ...operationLogRows[0]!, keywordEntryStatus: "missing", keywordUrl: null,
    };
    const initial = props(original);
    const { rerender } = render(<OperationLogTable {...initial} />);
    fireEvent.click(screen.getByTitle("词页面缺失，点击补录"));
    expect(initial.onOpenEntryEditor).toHaveBeenCalledWith(original, "keyword");
    rerender(<OperationLogTable {...props({
      ...original, keywordEntryStatus: "ok", keywordUrl: "/ads/keyword-library",
    })} />);
    fireEvent.click(screen.getByTitle("打开词页面"));
    expect(open).toHaveBeenCalledWith("/ads/keyword-library", "_blank", "noopener,noreferrer");
  });

  it("opens external HTTPS ads URLs", () => {
    const open = vi.spyOn(window, "open").mockImplementation(() => null);
    const row: OperationLogRow = { ...operationLogRows[0]!, adEntryStatus: "ok", adUrl: "https://example.com/ads" };
    const inputs = props(row);
    render(<OperationLogTable {...inputs} />);
    fireEvent.click(screen.getByTitle("打开广页面"));
    expect(open).toHaveBeenCalledWith("https://example.com/ads", "_blank", "noopener,noreferrer");
    expect(inputs.onOpenEntryEditor).not.toHaveBeenCalled();
  });
});
