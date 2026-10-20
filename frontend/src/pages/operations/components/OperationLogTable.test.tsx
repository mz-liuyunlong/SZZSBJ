// @vitest-environment jsdom
import { cleanup, render, screen } from "@testing-library/react";
import { afterAll, afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import OperationLogTable from "@/pages/operations/components/OperationLogTable";
import { operationLogRows } from "@/pages/operations/operationLogMockData";
import type { OperationLogRow } from "@/pages/operations/operationLogTypes";


// Ant Design ProTable requires matchMedia; jsdom does not implement it.
const originalMatchMedia = window.matchMedia;

beforeAll(() => {
  Object.defineProperty(window, "matchMedia", {
    configurable: true,
    writable: true,
    value: (query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addListener: () => {},
      removeListener: () => {},
      addEventListener: () => {},
      removeEventListener: () => {},
      dispatchEvent: () => false,
    }),
  });
});

afterAll(() => {
  if (originalMatchMedia) {
    Object.defineProperty(window, "matchMedia", {
      configurable: true,
      writable: true,
      value: originalMatchMedia,
    });
  } else {
    Reflect.deleteProperty(window, "matchMedia");
  }
});

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

describe("operation log table columns", () => {
  const createInputs = () => {
    const row: OperationLogRow = {
      ...operationLogRows[0]!,
      profit7d: 12.5,
      wfsAvailableInventory: 18,
    };

    return {
      ...props(row),
      appliedColumnKeys: [
        "productIdShortcut",
        "skuMsku",
        "owner",
        "profit7d",
        "wfsAvailableInventory",
        "conversionRate",
        "adRatio",
        "salePrice",
      ],
    };
  };

  it("renders the unified identity columns and owner", () => {
    render(<OperationLogTable {...createInputs()} />);

    expect(screen.getAllByText("商品ID/品名").length).toBeGreaterThan(0);
    expect(screen.getAllByText("SKU/MSKU").length).toBeGreaterThan(0);
    expect(screen.getAllByText("负责人").length).toBeGreaterThan(0);

    expect(screen.queryByText("运营")).toBeNull();
    expect(screen.queryByText("转化率")).toBeNull();
    expect(screen.queryByText("广告占比")).toBeNull();
    expect(screen.queryByText("销售价")).toBeNull();
  });

  it("shows profit and WFS inventory without shortcuts", () => {
    render(<OperationLogTable {...createInputs()} />);

    expect(screen.getAllByText("近7天利润").length).toBeGreaterThan(0);
    expect(screen.getAllByText("WFS可售库存").length).toBeGreaterThan(0);
    expect(screen.getByText("$12.50")).toBeTruthy();
    expect(screen.getByText("18")).toBeTruthy();

    expect(
      screen.queryByTitle("词页面缺失，点击补录")
    ).toBeNull();
    expect(
      screen.queryByTitle("打开广页面")
    ).toBeNull();
  });
});
