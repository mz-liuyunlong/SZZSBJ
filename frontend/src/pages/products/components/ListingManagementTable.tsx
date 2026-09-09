/** Dense Listing Management table built on the shared report-table shell. */
import { ProTable, type ProColumns } from "@ant-design/pro-components";
import { Empty, Table, Tag, Tooltip } from "antd";
import type { Key } from "react";
import ReportTableShell, {
  ReportTableSelectionBar,
} from "@/components/report-table/ReportTableShell";
import { REPORT_TABLE_PAGE_SIZE_OPTIONS } from "@/components/report-table/pagination";
import ResizableColumnTitle from "@/components/report-table/ResizableColumnTitle";
import {
  CopyableTextCell,
  ImageCell,
  MoneyCell,
  StatusTagCell,
} from "@/components/report-table/cells";
import {
  fixedListingColumnKeys,
  listingColumnFields,
  type ListingManagementRow,
} from "@/pages/products/listingManagementData";

interface ListingManagementTableProps {
  rows: ListingManagementRow[];
  appliedColumnKeys: string[];
  columnWidths: Record<string, number>;
  currentPage: number;
  pageSize: number;
  selectedRowKeys: Key[];
  onColumnWidthChange: (key: string, width: number) => void;
  onCurrentPageChange: (page: number) => void;
  onPageSizeChange: (pageSize: number) => void;
  onSelectionChange: (keys: Key[]) => void;
  onBulkMark: () => void;
  onCopy: (text: string) => void;
}

const widths: Record<string, number> = {
  image: 72,
  msku: 118,
  productId: 136,
  store: 120,
  owner: 96,
  sku: 120,
  productName: 180,
  title: 240,
  productType: 112,
  disabledReason: 140,
  checkedAt: 152,
  tags: 132,
};

const moneyKeys = new Set(["listPrice", "salePrice", "adSpend30Days"]);
const totalNumberKeys = new Set([
  "wfsAvailableInventory",
  "inboundInventory",
  "sales90Days",
  "reviewCount",
]);
const sortableKeys = new Set<keyof ListingManagementRow>([
  "msku",
  "productId",
  "store",
  "owner",
  "sku",
  "productName",
  "title",
  "productType",
  "listPrice",
  "salePrice",
  "productStatus",
  "lifecycle",
  "listedAt",
  "category",
  "wfsAvailableInventory",
  "inboundInventory",
  "sales90Days",
  "adSpend30Days",
  "listingStatus",
  "buyBoxStatus",
  "walmartSeller",
  "resold",
  "checkedAt",
  "rating",
  "reviewCount",
  "brand",
  "gtin",
  "productGrade",
]);
const dateKeys = new Set<keyof ListingManagementRow>(["listedAt", "checkedAt"]);
const statusColors: Record<string, string> = {
  启用: "success",
  停用: "error",
  在线: "success",
  离线: "default",
  拥有: "processing",
  未拥有: "warning",
};

const sum = (rows: ListingManagementRow[], key: keyof ListingManagementRow) => rows
  .reduce((total, row) => total + Number(row[key]), 0);

const listingSorter = (key: keyof ListingManagementRow) => (
  left: ListingManagementRow,
  right: ListingManagementRow,
) => {
  const leftValue = left[key];
  const rightValue = right[key];
  if (typeof leftValue === "number") return leftValue - Number(rightValue);
  if (dateKeys.has(key)) {
    return Date.parse(String(leftValue).replace(" ", "T"))
      - Date.parse(String(rightValue).replace(" ", "T"));
  }
  return String(leftValue).localeCompare(String(rightValue), "zh-CN");
};

function TotalCell({ columnKey, rows }: { columnKey: string; rows: ListingManagementRow[] }) {
  if (columnKey === "image") return <span className="report-table-summary-label">总计</span>;
  if (columnKey === "adSpend30Days") {
    return <MoneyCell value={sum(rows, "adSpend30Days")} />;
  }
  if (totalNumberKeys.has(columnKey)) {
    return <span className="report-table-metric">
      {sum(rows, columnKey as keyof ListingManagementRow).toLocaleString("zh-CN")}
    </span>;
  }
  return null;
}

function cell(row: ListingManagementRow, key: keyof ListingManagementRow, onCopy: (text: string) => void) {
  const value = row[key];
  if (key === "image") return <ImageCell label="Listing 商品图片占位" />;
  if (["msku", "productId", "sku", "productName"].includes(key)) {
    return <CopyableTextCell text={String(value)} label={listingColumnFields.find((field) => field.key === key)?.title ?? key} onCopy={onCopy} />;
  }
  if (moneyKeys.has(key)) return <MoneyCell value={Number(value)} />;
  if (key === "tags") {
    return value instanceof Array
      ? <span>{value.map((tag) => <Tag key={tag}>{tag}</Tag>)}</span>
      : null;
  }
  if (key === "productStatus" || key === "listingStatus" || key === "buyBoxStatus") {
    return <StatusTagCell label={String(value)} color={statusColors[String(value)] ?? "default"} />;
  }
  return <Tooltip title={String(value)}><span>{String(value)}</span></Tooltip>;
}

function ListingManagementTable({
  rows,
  appliedColumnKeys,
  columnWidths,
  currentPage,
  pageSize,
  selectedRowKeys,
  onColumnWidthChange,
  onCurrentPageChange,
  onPageSizeChange,
  onSelectionChange,
  onBulkMark,
  onCopy,
}: ListingManagementTableProps) {
  const fieldMap = new Map(listingColumnFields.map((field) => [field.key, field]));
  const columns = appliedColumnKeys.flatMap((key): ProColumns<ListingManagementRow>[] => {
    const field = fieldMap.get(key as typeof listingColumnFields[number]["key"]);
    if (!field) return [];
    const width = columnWidths[key] ?? widths[key] ?? 112;
    const fixed = fixedListingColumnKeys.includes(key) ? "left" as const : undefined;
    return [{
      key,
      dataIndex: key,
      align: "left",
      fixed,
      width,
      ellipsis: true,
      sorter: sortableKeys.has(key as keyof ListingManagementRow)
        ? listingSorter(key as keyof ListingManagementRow)
        : undefined,
      onHeaderCell: () => ({ className: "report-table-resizable-header-cell" }),
      title: (
        <ResizableColumnTitle
          label={field.title}
          minWidth={key === "image" ? 72 : 88}
          width={width}
          onWidthChange={(nextWidth) => onColumnWidthChange(key, nextWidth)}
        />
      ),
      render: (_, row) => cell(row, key as keyof ListingManagementRow, onCopy),
    }];
  });

  return (
    <ReportTableShell className="listing-management__table" label="Listing 管理主表">
      <ProTable<ListingManagementRow>
        columns={columns}
        dataSource={rows}
        rowKey="id"
        rowSelection={{ fixed: true, selectedRowKeys, onChange: onSelectionChange }}
        search={false}
        options={false}
        toolBarRender={false}
        tableAlertRender={false}
        tableAlertOptionRender={false}
        showSorterTooltip={{ target: "sorter-icon" }}
        scroll={{ x: "max-content", y: "100%" }}
        summary={() => (
          <Table.Summary fixed="bottom">
            <Table.Summary.Row className="listing-management__total-row" data-testid="listing-management-total-row">
              <Table.Summary.Cell index={0} />
              {columns.map((column, index) => {
                const key = String(column.key);
                return (
                  <Table.Summary.Cell
                    key={key}
                    index={index + 1}
                    align="left"
                    className={`listing-management__total-cell listing-management__total-cell--${key}`}
                  >
                    <TotalCell columnKey={key} rows={rows} />
                  </Table.Summary.Cell>
                );
              })}
            </Table.Summary.Row>
          </Table.Summary>
        )}
        footer={() => (
          <ReportTableSelectionBar
            selectedCount={selectedRowKeys.length}
            actions={[{ key: "mark", label: "批量标记", onClick: onBulkMark }]}
          />
        )}
        pagination={{
          current: currentPage,
          pageSize,
          total: rows.length,
          showSizeChanger: true,
          showQuickJumper: true,
          pageSizeOptions: REPORT_TABLE_PAGE_SIZE_OPTIONS,
          showTotal: (total) => `共 ${total} 条`,
          onChange: (nextPage, nextPageSize) => {
            if (nextPageSize !== pageSize) onPageSizeChange(nextPageSize);
            else onCurrentPageChange(nextPage);
          },
        }}
        locale={{
          emptyText: <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无匹配 Listing 数据" />,
        }}
      />
    </ReportTableShell>
  );
}

export default ListingManagementTable;
