// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";
import { cleanup, render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import ListingManagementTable from "@/pages/products/components/ListingManagementTable";
import {
  fixedListingColumnKeys,
  listingColumnFields,
  listingManagementMockData,
  type ListingManagementRow,
} from "@/pages/products/listingManagementData";

interface CapturedTableProps {
  columns: Array<{
    key?: string;
    sorter?: (left: ListingManagementRow, right: ListingManagementRow) => number;
  }>;
  pagination: { pageSizeOptions: string[] };
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
  it("keeps 128 local rows and the owner-approved column order", () => {
    expect(listingManagementMockData).toHaveLength(128);
    expect(new Set(listingManagementMockData.map((row) => row.id)).size).toBe(128);
    expect(listingColumnFields.map((field) => field.title)).toEqual([
      "图片", "MSKU", "商品ID", "店铺", "负责人", "SKU", "品名", "标题", "产品类型",
      "划线价", "在售价", "产品状态", "生命周期", "上架时间", "类目", "WFS可售库存",
      "在途库存", "近90天销量", "近30天广告费", "停用原因", "Listing状态", "购物车状态",
      "Walmart卖家", "是否被跟卖", "检查时间", "评分", "评论数", "品牌", "标签", "GTIN",
      "产品等级",
    ]);
    expect(fixedListingColumnKeys).toEqual(["image", "msku", "productId"]);
  });

  it("uses Ant table sorters without changing pagination options", () => {
    const rows = listingManagementMockData.slice(0, 2);
    render(
      <ListingManagementTable
        rows={rows}
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
        onBulkExport={() => undefined}
      />,
    );

    const sorterFor = (key: string) => capturedTableProps?.columns.find((column) => column.key === key)?.sorter;
    const skuSorter = sorterFor("sku");
    const priceSorter = sorterFor("salePrice");
    const dateSorter = sorterFor("checkedAt");
    expect(skuSorter).toBeTypeOf("function");
    expect(priceSorter).toBeTypeOf("function");
    expect(dateSorter).toBeTypeOf("function");
    expect(skuSorter?.(rows[0], rows[1])).toBeLessThan(0);
    expect(priceSorter?.(rows[0], rows[1])).toBeLessThan(0);
    expect(dateSorter?.(rows[0], rows[1])).toBeLessThan(0);

    expect(Array.from(screen.getByLabelText("每页条数").querySelectorAll("option"))
      .map((option) => option.textContent)).toEqual(["50", "100", "200", "500", "1000"]);
  });
});
