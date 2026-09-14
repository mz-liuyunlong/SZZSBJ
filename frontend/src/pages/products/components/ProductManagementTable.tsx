import { Button, Space, Tag, Tooltip, Typography } from "antd";
import { ProTable, type ProColumns } from "@ant-design/pro-components";
import type { Key, ReactNode } from "react";
import ReportTableShell, {
  ReportTableSelectionBar,
} from "@/components/report-table/ReportTableShell";
import ResizableColumnTitle from "@/components/report-table/ResizableColumnTitle";
import { CopyableTextCell, ImageCell } from "@/components/report-table/cells";
import type { ProductManagementRow } from "@/pages/products/productManagementTypes";
import { productColumnFields } from "@/pages/products/productManagementTypes";

const minColumnWidths: Record<string, number> = {
  image: 72,
  sku: 160,
  productName: 220,
  tags: 120,
  sourceTags: 120,
  productGrade: 110,
  wfsFee: 110,
  suggestedPrice: 120,
  minimumPrice: 120,
  clearancePrice: 120,
  category: 120,
  purchasePrice: 120,
  firstLegFreight: 120,
  wfsDeliveryFee: 120,
  purchaseLeadTime: 120,
  storageFee: 110,
  linkedPlatformSkuCount: 120,
  dataCompleteness: 120,
  updatedAt: 160,
  actions: 110,
};

const tagColorMap: Record<string, string> = {
  测品: "blue",
  清货: "orange",
  停售: "red",
};

const empty = <Typography.Text type="secondary">-</Typography.Text>;
const missingRootCodes = new Set([
  "missing_purchase_cost",
  "missing_gross_weight",
  "missing_package_dimensions",
]);

function calculatedValue(value: ReactNode, row: ProductManagementRow) {
  if (value) return value;
  const label = row.rootMissingCodes.some((code) => missingRootCodes.has(code))
    ? "缺基础数据"
    : row.calculationStatus === "invalid_denominator"
      ? "规则异常"
      : "无法计算";
  return <Typography.Text type="secondary">{label}</Typography.Text>;
}

interface ProductManagementTableProps {
  rows: ProductManagementRow[];
  total: number;
  appliedColumnKeys: string[];
  columnWidths: Record<string, number>;
  currentPage: number;
  pageSize: number;
  selectedRowKeys: Key[];
  onColumnWidthChange: (key: string, width: number) => void;
  onCurrentPageChange: (page: number) => void;
  onPageSizeChange: (pageSize: number) => void;
  onSelectionChange: (keys: Key[]) => void;
  onOpenDetail: (row: ProductManagementRow) => void;
  onBulkExport: () => void;
}

function ProductManagementTable({
  rows,
  total,
  appliedColumnKeys,
  columnWidths,
  currentPage,
  pageSize,
  selectedRowKeys,
  onColumnWidthChange,
  onCurrentPageChange,
  onPageSizeChange,
  onSelectionChange,
  onOpenDetail,
  onBulkExport,
}: ProductManagementTableProps) {
  const title = (key: string, label: string) => (
    <ResizableColumnTitle
      label={label}
      minWidth={minColumnWidths[key] ?? 96}
      width={columnWidths[key] ?? minColumnWidths[key] ?? 112}
      onWidthChange={(width) => onColumnWidthChange(key, width)}
    />
  );

  const headerCell = () => ({
    className: "report-table-resizable-header-cell",
  });

  const fieldTitle = Object.fromEntries(productColumnFields.map((field) => [field.key, field.title]));

  const allColumns: Record<string, ProColumns<ProductManagementRow>> = {
    image: {
      key: "image",
      dataIndex: "image",
      title: title("image", fieldTitle.image),
      width: columnWidths.image,
      fixed: "left",
      onHeaderCell: headerCell,
      render: (_, row) => (
        <ImageCell
          image={row.image ?? undefined}
          label={`产品图片：${row.productName ?? "未命名"}`}
          placement="right"
        />
      ),
    },
    sku: {
      key: "sku",
      dataIndex: "sku",
      title: title("sku", fieldTitle.sku),
      width: columnWidths.sku,
      fixed: "left",
      sorter: (a, b) => (a.sku ?? "").localeCompare(b.sku ?? ""),
      onHeaderCell: headerCell,
      render: (_, row) => (
        <CopyableTextCell
          text={row.sku ?? "-"}
          label="SKU"
          link
          onOpen={() => onOpenDetail(row)}
        />
      ),
    },
    productName: {
      key: "productName",
      dataIndex: "productName",
      title: title("productName", fieldTitle.productName),
      width: columnWidths.productName,
      sorter: (a, b) => (a.productName ?? "").localeCompare(b.productName ?? ""),
      ellipsis: true,
      onHeaderCell: headerCell,
      render: (_, row) => (
        <CopyableTextCell
          text={row.productName ?? "-"}
          label="产品名称"
          link
          onOpen={() => onOpenDetail(row)}
        />
      ),
    },
    tags: {
      key: "tags",
      dataIndex: "tags",
      title: title("tags", fieldTitle.tags),
      width: columnWidths.tags,
      onHeaderCell: headerCell,
      render: (_, row) => (
        <Space size={4} wrap>
          {row.tags.length > 0 ? row.tags.map((tag) => (
            <Tag key={tag} color={tagColorMap[tag]}>{tag}</Tag>
          )) : <Typography.Text type="secondary">-</Typography.Text>}
        </Space>
      ),
    },
    sourceTags: {
      key: "sourceTags",
      dataIndex: "sourceTags",
      title: title("sourceTags", fieldTitle.sourceTags),
      width: columnWidths.sourceTags,
      onHeaderCell: headerCell,
      render: (_, row) => (
        <Space size={4} wrap>
          {row.sourceTags.length > 0 ? row.sourceTags.map((tag) => (
            <Tag key={tag}>{tag}</Tag>
          )) : <Typography.Text type="secondary">-</Typography.Text>}
        </Space>
      ),
    },
    productGrade: {
      key: "productGrade",
      dataIndex: "productGrade",
      title: title("productGrade", fieldTitle.productGrade),
      width: columnWidths.productGrade,
      sorter: (a, b) => (a.productGrade ?? "").localeCompare(b.productGrade ?? ""),
      render: (_, row) => row.productGrade ?? empty,
      onHeaderCell: headerCell,
    },
    wfsFee: {
      key: "wfsFee",
      dataIndex: "wfsFee",
      title: title("wfsFee", fieldTitle.wfsFee),
      width: columnWidths.wfsFee,
      onHeaderCell: headerCell,
      render: (_, row) => calculatedValue(row.wfsFee, row),
    },
    suggestedPrice: {
      key: "suggestedPrice",
      dataIndex: "suggestedPrice",
      title: title("suggestedPrice", fieldTitle.suggestedPrice),
      width: columnWidths.suggestedPrice,
      onHeaderCell: headerCell,
      render: (_, row) => calculatedValue(row.suggestedPrice, row),
    },
    minimumPrice: {
      key: "minimumPrice",
      dataIndex: "minimumPrice",
      title: title("minimumPrice", fieldTitle.minimumPrice),
      width: columnWidths.minimumPrice,
      onHeaderCell: headerCell,
      render: (_, row) => calculatedValue(row.minimumPrice, row),
    },
    clearancePrice: {
      key: "clearancePrice",
      dataIndex: "clearancePrice",
      title: title("clearancePrice", fieldTitle.clearancePrice),
      width: columnWidths.clearancePrice,
      onHeaderCell: headerCell,
      render: (_, row) => calculatedValue(row.clearancePrice, row),
    },
    category: {
      key: "category",
      dataIndex: "category",
      title: title("category", fieldTitle.category),
      width: columnWidths.category,
      onHeaderCell: headerCell,
    },
    purchasePrice: {
      key: "purchasePrice",
      dataIndex: "purchasePrice",
      title: title("purchasePrice", fieldTitle.purchasePrice),
      width: columnWidths.purchasePrice,
      onHeaderCell: headerCell,
      render: (_, row) => row.purchasePrice ?? empty,
    },
    firstLegFreight: {
      key: "firstLegFreight",
      dataIndex: "firstLegFreight",
      title: title("firstLegFreight", fieldTitle.firstLegFreight),
      width: columnWidths.firstLegFreight,
      onHeaderCell: headerCell,
      render: (_, row) => calculatedValue(row.firstLegFreight, row),
    },
    wfsDeliveryFee: {
      key: "wfsDeliveryFee",
      dataIndex: "wfsDeliveryFee",
      title: title("wfsDeliveryFee", fieldTitle.wfsDeliveryFee),
      width: columnWidths.wfsDeliveryFee,
      onHeaderCell: headerCell,
      render: (_, row) => calculatedValue(row.wfsDeliveryFee, row),
    },
    purchaseLeadTime: {
      key: "purchaseLeadTime",
      dataIndex: "purchaseLeadTime",
      title: title("purchaseLeadTime", fieldTitle.purchaseLeadTime),
      width: columnWidths.purchaseLeadTime,
      onHeaderCell: headerCell,
    },
    storageFee: {
      key: "storageFee",
      dataIndex: "storageFee",
      title: title("storageFee", fieldTitle.storageFee),
      width: columnWidths.storageFee,
      onHeaderCell: headerCell,
      render: (_, row) => calculatedValue(row.storageFee, row),
    },
    linkedPlatformSkuCount: {
      key: "linkedPlatformSkuCount",
      dataIndex: "linkedPlatformSkuCount",
      title: title("linkedPlatformSkuCount", fieldTitle.linkedPlatformSkuCount),
      width: columnWidths.linkedPlatformSkuCount,
      sorter: (a, b) => a.linkedPlatformSkuCount - b.linkedPlatformSkuCount,
      onHeaderCell: headerCell,
    },
    dataCompleteness: {
      key: "dataCompleteness",
      dataIndex: "dataCompleteness",
      title: title("dataCompleteness", fieldTitle.dataCompleteness),
      width: columnWidths.dataCompleteness,
      sorter: (a, b) => (a.dataCompleteness ?? -1) - (b.dataCompleteness ?? -1),
      onHeaderCell: headerCell,
      render: (_, row) => row.dataCompleteness === null ? empty : `${row.dataCompleteness}%`,
    },
    updatedAt: {
      key: "updatedAt",
      dataIndex: "updatedAt",
      title: title("updatedAt", fieldTitle.updatedAt),
      width: columnWidths.updatedAt,
      sorter: (a, b) => (a.updatedAt ?? "").localeCompare(b.updatedAt ?? ""),
      render: (_, row) => row.updatedAt ?? empty,
      onHeaderCell: headerCell,
    },
  };

  const columns = appliedColumnKeys
    .flatMap((key) => (allColumns[key] ? [allColumns[key]] : []))
    .concat({
      key: "actions",
      title: title("actions", "操作"),
      width: columnWidths.actions,
      fixed: "right",
      onHeaderCell: headerCell,
      render: (_, row) => (
        <Tooltip title="打开产品详情">
          <Button type="link" onClick={() => onOpenDetail(row)}>详情</Button>
        </Tooltip>
      ),
    });

  const scrollX = columns.reduce((sum, column) => sum + Number(column.width ?? 112), 56);

  return (
    <ReportTableShell label="产品管理表格" className="product-management__table-shell">
      <ProTable<ProductManagementRow>
        rowKey="id"
        search={false}
        options={false}
        dataSource={rows}
        columns={columns}
        tableAlertRender={false}
        toolBarRender={false}
        bordered
        size="small"
        scroll={{ x: scrollX, y: "100%" }}
        rowSelection={{
          fixed: true,
          selectedRowKeys,
          columnWidth: 48,
          onChange: onSelectionChange,
        }}
        pagination={{
          current: currentPage,
          pageSize,
          total,
          showSizeChanger: true,
          showQuickJumper: true,
          pageSizeOptions: ["50", "100"],
          showTotal: (total) => `共 ${total.toLocaleString()} 条数据`,
          onChange: (page, nextPageSize) => {
            onCurrentPageChange(page);
            if (nextPageSize !== pageSize) onPageSizeChange(nextPageSize);
          },
        }}
        footer={() => (
          <ReportTableSelectionBar
            selectedCount={selectedRowKeys.length}
            actions={[
              {
                key: "export",
                label: "导出已选",
                disabled: selectedRowKeys.length === 0,
                onClick: onBulkExport,
              },
            ]}
          />
        )}
      />
    </ReportTableShell>
  );
}

export default ProductManagementTable;
