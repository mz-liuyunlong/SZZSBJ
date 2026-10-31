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
  type ListingManagementRow,
} from "@/pages/products/listingManagementData";

interface CapturedTableProps {
  columns: Array<{
    key?: string;
    fixed?: "left" | "right" | boolean;
    sorter?: boolean;
    render?: (_: unknown, row: ListingManagementRow) => ReactNode;
  }>;
  pagination: { pageSizeOptions: string[] };
  scroll?: { x?: number; y?: number | string };
  virtual?: boolean;
  listItemHeight?: number;
  rowSelection?: { fixed?: boolean };
  onChange?: (_pagination: unknown, _filters: unknown, sorter: { columnKey: string; order: "ascend" | "descend" | null }) => void;
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
  it("shows the raw Listing date only when normalized time is missing", () => {
    expect(toListingStartText("2026-09-08T16:31:47Z")).toBe("2026-09-08");
    expect(toListingStartText(null, "2026-09-08 09:31:47")).toBe("2026-09-08");
    expect(toListingStartText(null, "2026-09-08")).toBe("2026-09-08");
    expect(toListingStartText(null, "unverified")).toBe("unverified");
    expect(toListingStartText(null)).toBe("");
  });

  it("keeps 100 local rows and the owner-approved column order", () => {
    expect(listingManagementMockData).toHaveLength(100);
    expect(new Set(listingManagementMockData.map((row) => row.id)).size).toBe(100);
    expect(listingColumnFields.map((field) => field.title)).toEqual([
      "图片", "商品ID/本地品名", "SKU/MSKU", "店铺", "负责人", "平台标题", "平台类目",
      "划线价", "在售价", "产品状态", "生命周期", "发货方式", "GPT分析", "平台上架时间", "首次WFS有货日", "类目", "WFS可售库存",
      "在途库存", "近30天销量", "近30天广告费", "停用原因", "Listing状态", "购物车状态",
      "Walmart卖家", "是否被跟卖", "监控检查时间", "数据更新时间", "监控来源", "监控时效", "监控状态", "监控错误码", "监控图片数", "评分", "评论数", "品牌", "标签", "GTIN",
      "产品等级",
      "归档状态", "归档原因",
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
          ratingWarning: listingManagementMockData.filter((row) => row.rating < 4).length,
          resoldWarning: listingManagementMockData.filter((row) => row.resold === "是").length,
          strikePriceException: listingManagementMockData.filter((row) => (
            row.listPrice > 0 && row.listPrice <= row.salePrice
          )).length,
        }}
        onCardClick={onCardClick}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: /在售商品/ }));
    expect(onCardClick).toHaveBeenCalledWith("online");
  });

  it("requests remote sorting without sorting only the loaded page", () => {
    const rows = listingManagementMockData.slice(0, 2);
    const onSortChange = vi.fn();
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
        onSortChange={onSortChange}
        onOpenDetail={() => undefined}
        onBatchSetTags={() => undefined}
        onBulkExport={() => undefined}
      />,
    );

    const sorterFor = (key: string) => capturedTableProps?.columns.find((column) => column.key === key)?.sorter;
    const skuSorter = sorterFor("skuMsku");
    const priceSorter = sorterFor("salePrice");
    const dateSorter = sorterFor("checkedAt");
    expect(skuSorter).toBe(true);
    expect(priceSorter).toBe(true);
    expect(dateSorter).toBe(true);
    capturedTableProps?.onChange?.({}, {}, { columnKey: "salePrice", order: "descend" });
    expect(onSortChange).toHaveBeenCalledWith("salePrice", "desc");

    expect(Array.from(screen.getByLabelText("每页条数").querySelectorAll("option"))
      .map((option) => option.textContent)).toEqual(["50", "100", "200", "500", "1000"]);
  });

  it("does not invent USD when a Listing price has no currency evidence", () => {
    render(
      <ListingManagementTable
        rows={listingManagementMockData.slice(0, 1)}
        total={1}
        appliedColumnKeys={["listPrice", "salePrice"]}
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
    const row = {
      ...listingManagementMockData[0],
      listPriceKnown: true,
      salePriceKnown: true,
      listPriceCurrency: "",
      salePriceCurrency: "",
    };
    for (const key of ["listPrice", "salePrice"]) {
      const value = capturedTableProps?.columns.find((column) => column.key === key)?.render?.(null, row);
      expect(value).toContain("币种未知");
      expect(value).not.toContain("USD");
    }
  });

  it("keeps pinned columns, sorting, selection and actions at 1000 rows with virtual scroll", () => {
    const rows = listingManagementMockData.slice(0, 2);
    render(
      <ListingManagementTable
        rows={rows}
        total={1000}
        appliedColumnKeys={listingColumnFields.map((field) => field.key)}
        columnWidths={{}}
        currentPage={1}
        pageSize={1000}
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
