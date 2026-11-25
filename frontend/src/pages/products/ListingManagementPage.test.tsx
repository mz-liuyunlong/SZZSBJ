import { listingSortFields, mergeListingSorts, nextListingColumnSort } from "@/pages/products/listingManagementSort";
// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import ListingManagementTable from "@/pages/products/components/ListingManagementTable";
import ListingManagementSummaryCards from "@/pages/products/components/ListingManagementSummaryCards";
import { toListingStartText } from "@/pages/products/listingManagementApi";
import {
  fixedListingColumnKeys,
  listingColumnFields,
  listingManagementMockData,
} from "@/pages/products/listingManagementData";

interface CapturedTableProps {
  columns: Array<{
    key?: string;
    fixed?: "left" | "right" | boolean;
    sorter?: boolean;
  }>;
  pagination: { pageSizeOptions: string[] };
  scroll?: { x?: number; y?: number | string };
  virtual?: boolean;
  listItemHeight?: number;
  rowSelection?: { fixed?: boolean };
  summary?: () => ReactNode;
}

let capturedTableProps: CapturedTableProps | undefined;

vi.mock("@ant-design/pro-components", () => ({
  ProTable: (props: CapturedTableProps) => {
    capturedTableProps = props;
    return (
      <>
        <table data-testid="listing-pro-table">
          <thead><tr>{props.columns.map((column) => <th key={column.key}>{column.key}</th>)}</tr></thead>
          {props.summary?.()}
        </table>
        <select aria-label="每页条数">
          {props.pagination.pageSizeOptions.map((size) => <option key={size}>{size}</option>)}
        </select>
      </>
    );
  },
}));

vi.mock("antd", () => {
  const Summary = Object.assign(
    ({ children, fixed }: { children: ReactNode; fixed?: string }) => (
      <tfoot data-fixed={fixed}>{children}</tfoot>
    ),
    {
      Row: ({ children, ...props }: { children: ReactNode; [key: string]: unknown }) => (
        <tr {...props}>{children}</tr>
      ),
      Cell: ({ children, index, ...props }: {
        children?: ReactNode;
        index: number;
        [key: string]: unknown;
      }) => <td data-index={index} {...props}>{children}</td>,
    },
  );
  return {
    Button: ({ children }: { children?: ReactNode }) => <button type="button">{children}</button>,
    Dropdown: ({ children }: { children: ReactNode }) => <>{children}</>,
    Empty: Object.assign(
      ({ description }: { description?: ReactNode }) => <span>{description}</span>,
      { PRESENTED_IMAGE_SIMPLE: "simple" },
    ),
    Popover: ({ children }: { children: ReactNode }) => <>{children}</>,
    Table: { Summary },
    Tag: ({ children }: { children: ReactNode }) => <span>{children}</span>,
    Tooltip: ({ children }: { children: ReactNode }) => <>{children}</>,
    Typography: { Text: ({ children }: { children: ReactNode }) => <span>{children}</span> },
  };
});

vi.mock("echarts-for-react", () => ({ default: () => null }));

afterEach(() => {
  cleanup();
  capturedTableProps = undefined;
});

describe("ListingManagementPage acceptance contract", () => {
  it("shows listing start values from MART only and never falls back to raw source dates", () => {
    expect(toListingStartText("2026-09-08T16:31:47Z")).toBe("2026-09-08");
    expect(toListingStartText(null)).toBe("");
  });

  it("keeps 100 local rows and the owner-approved column order", () => {
    expect(listingManagementMockData).toHaveLength(100);
    expect(new Set(listingManagementMockData.map((row) => row.id)).size).toBe(100);
    expect(listingColumnFields.map((field) => field.title)).toEqual([
      "图片", "商品ID/品名", "SKU/MSKU", "店铺/负责人",
      "标题", "图片数量", "划线价", "有无划线价",
      "在售价", "类目", "WFS可售库存", "在途库存",
      "上架时间", "近30天销量", "近30天广告费", "生命周期",
      "listing等级", "停用原因", "Listing状态", "购物车状态",
      "品牌", "Walmart卖家", "卖家数量", "卖家列表",
      "是否被跟卖", "监控日期", "评分", "评论数",
      "五点描述", "标签", "产品标签", "发货方式",
      "GTIN", "GPT分析", "归档原因"
    ]);
    expect(fixedListingColumnKeys).toEqual(["image", "productIdName", "skuMsku"]);
  });

  it("reports the selected summary filter when a statistics card is clicked", () => {
    const onCardClick = vi.fn();
    render(
      <ListingManagementSummaryCards
        summary={{
          total: listingManagementMockData.length,
          online: listingManagementMockData.filter((row) => row.listingStatus === "在线").length,
          buyboxException: listingManagementMockData.filter((row) => row.buyBoxStatus === "未拥有").length,
          ratingWarning: listingManagementMockData.filter((row) => row.rating != null && row.rating < 4).length,
          resoldWarning: listingManagementMockData.filter((row) => row.resold === "是").length,
          strikePriceException: listingManagementMockData.filter((row) => (
            row.listPrice != null && row.salePrice != null && row.listPrice > 0 && row.listPrice <= row.salePrice
          )).length,
        }}
        onCardClick={onCardClick}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: /在售商品/ }));
    expect(onCardClick).toHaveBeenCalledWith("online");
  });

  it("exposes all 20 native server sorters without local comparators", () => {
    const rows = listingManagementMockData.slice(0, 2);
    render(
      <ListingManagementTable
        rows={rows}
        total={listingManagementMockData.length}
        appliedColumnKeys={listingColumnFields.map((field) => field.key)}
        columnWidths={{}}
        currentPage={1}
        pageSize={50}
        selectedRowKeys={[]}
        onColumnWidthChange={() => undefined}
        onCurrentPageChange={() => undefined}
        onPageSizeChange={() => undefined}
        onSelectionChange={() => undefined}
        onOpenDetail={() => undefined}
        onBatchSetTags={() => undefined}
        onBulkExport={() => undefined}
      />,
    );

    const columns = capturedTableProps?.columns ?? [];
    expect(columns.filter(column => column.sorter).map(column => column.key).sort())
      .toEqual([...listingSortFields].sort());
    for (const column of columns.filter(column => column.sorter)) {
      expect(column.sorter).toBe(true);
    }

    expect(Array.from(screen.getByLabelText("每页条数").querySelectorAll("option"))
      .map((option) => option.textContent)).toEqual(["50", "100", "200", "500", "1000"]);
  });

  it.each([50, 100, 200, 500, 1000])("keeps pinned columns, sorting, selection and actions at %i rows with virtual scroll", (size) => {
    const rows = listingManagementMockData.slice(0, 2);
    render(
      <ListingManagementTable
        rows={rows}
        total={1000}
        appliedColumnKeys={listingColumnFields.map((field) => field.key)}
        columnWidths={{}}
        currentPage={1}
        pageSize={size}
        virtualScrollY={456}
        selectedRowKeys={[]}
        onColumnWidthChange={() => undefined}
        onCurrentPageChange={() => undefined}
        onPageSizeChange={() => undefined}
        onSelectionChange={() => undefined}
        onOpenDetail={() => undefined}
        onBatchSetTags={() => undefined}
        onBulkExport={() => undefined}
      />,
    );

    expect(capturedTableProps?.virtual).toBe(true);
    expect(capturedTableProps?.listItemHeight).toBe(61);
    expect(capturedTableProps?.scroll?.y).toBe(456);
    expect(capturedTableProps?.rowSelection?.fixed).toBe(true);
    expect(capturedTableProps?.columns.find((col) => col.key === "productIdName")?.fixed).toBe("left");
    expect(capturedTableProps?.columns.find((col) => col.key === "actions")?.fixed).toBe("right");
    expect(capturedTableProps?.columns.find((col) => col.key === "skuMsku")?.sorter).toBe(true);
    expect(Array.from(screen.getByLabelText("每页条数").querySelectorAll("option"))
      .map((option) => option.textContent)).toEqual(["50", "100", "200", "500", "1000"]);
  });

});

it("replaces the previous column sort and supports clearing", () => {
  const first = mergeListingSorts([], {
    columnKey: "rating", order: "ascend",
  });
  const second = mergeListingSorts(first, {
    columnKey: "sales90Days", order: "descend",
  });
  expect(second).toEqual([
    { key: "sales90Days", direction: "desc" },
  ]);
  expect(mergeListingSorts(second, {
    columnKey: "sales90Days", order: "ascend",
  })).toEqual([
    { key: "sales90Days", direction: "asc" },
  ]);
  expect(mergeListingSorts(second, {
    columnKey: "sales90Days", order: null,
  })).toEqual([]);
});

it("switches directly between every supported sorting column", () => {
  for (const first of listingSortFields) {
    const active = nextListingColumnSort([], first);

    expect(active).toEqual([{ key: first, direction: "asc" }]);

    const descending = nextListingColumnSort(active, first);

    expect(descending).toEqual([{ key: first, direction: "desc" }]);
    expect(nextListingColumnSort(descending, first)).toEqual([]);

    for (const second of listingSortFields) {
      if (second === first) continue;

      expect(nextListingColumnSort(active, second)).toEqual([
        { key: second, direction: "asc" },
      ]);

      expect(mergeListingSorts(active, [
        { columnKey: first, order: null },
        { columnKey: second, order: "ascend" },
      ])).toEqual([
        { key: second, direction: "asc" },
      ]);
    }
  }
});
