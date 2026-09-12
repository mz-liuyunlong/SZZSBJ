import { Button, Space, Tag, Tooltip, Typography } from "antd";
import { ProTable, type ProColumns } from "@ant-design/pro-components";
import type { Key } from "react";
import ReportTableShell, {
  ReportTableSelectionBar,
} from "@/components/report-table/ReportTableShell";
import {
  REPORT_TABLE_PAGE_SIZE_OPTIONS,
} from "@/components/report-table/pagination";
import ResizableColumnTitle from "@/components/report-table/ResizableColumnTitle";
import {
  listingColumnFields,
  type ListingManagementRow,
} from "@/pages/products/listingManagementData";

const minColumnWidths: Record<string, number> = {
  image: 72,
  msku: 130,
  productId: 150,
  store: 120,
  owner: 110,
  sku: 130,
  productName: 190,
  title: 260,
  productType: 130,
  listPrice: 110,
  salePrice: 110,
  productStatus: 120,
  lifecycle: 120,
  listedAt: 140,
  category: 120,
  wfsAvailableInventory: 140,
  inboundInventory: 130,
  sales90Days: 130,
  adSpend30Days: 140,
  disabledReason: 130,
  listingStatus: 130,
  buyBoxStatus: 130,
  walmartSeller: 140,
  resold: 120,
  checkedAt: 160,
  rating: 100,
  reviewCount: 110,
  brand: 130,
  tags: 130,
  gtin: 160,
  productGrade: 120,
  actions: 110,
};

const statusColorMap: Record<string, string> = {
  启用: "green",
  停用: "red",
  在线: "green",
  离线: "red",
  拥有: "green",
  未拥有: "orange",
  是: "orange",
  否: "default",
};

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
  onOpenDetail: (row: ListingManagementRow) => void;
  onBulkExport: () => void;
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
  onOpenDetail,
  onBulkExport,
}: ListingManagementTableProps) {
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

  const fieldTitle = Object.fromEntries(listingColumnFields.map((field) => [field.key, field.title]));

  const allColumns: Record<string, ProColumns<ListingManagementRow>> = {
    image: {
      key: "image",
      dataIndex: "image",
      title: title("image", fieldTitle.image),
      width: columnWidths.image,
      fixed: "left",
      onHeaderCell: headerCell,
      render: (_, row) => (
        <div className="listing-management__image-cell" aria-label={`Listing 图片：${row.productName}`}>
          {row.image}
        </div>
      ),
    },
    msku: {
      key: "msku",
      dataIndex: "msku",
      title: title("msku", fieldTitle.msku),
      width: columnWidths.msku,
      fixed: "left",
      sorter: (a, b) => a.msku.localeCompare(b.msku),
      onHeaderCell: headerCell,
      render: (_, row) => (
        <Typography.Link strong onClick={() => onOpenDetail(row)}>
          {row.msku}
        </Typography.Link>
      ),
    },
    productId: {
      key: "productId",
      dataIndex: "productId",
      title: title("productId", fieldTitle.productId),
      width: columnWidths.productId,
      fixed: "left",
      sorter: (a, b) => a.productId.localeCompare(b.productId),
      onHeaderCell: headerCell,
      render: (_, row) => <Typography.Link>{row.productId}</Typography.Link>,
    },
    store: {
      key: "store",
      dataIndex: "store",
      title: title("store", fieldTitle.store),
      width: columnWidths.store,
      onHeaderCell: headerCell,
    },
    owner: {
      key: "owner",
      dataIndex: "owner",
      title: title("owner", fieldTitle.owner),
      width: columnWidths.owner,
      onHeaderCell: headerCell,
    },
    sku: {
      key: "sku",
      dataIndex: "sku",
      title: title("sku", fieldTitle.sku),
      width: columnWidths.sku,
      onHeaderCell: headerCell,
      render: (_, row) => <Typography.Link>{row.sku}</Typography.Link>,
    },
    productName: {
      key: "productName",
      dataIndex: "productName",
      title: title("productName", fieldTitle.productName),
      width: columnWidths.productName,
      ellipsis: true,
      sorter: (a, b) => a.productName.localeCompare(b.productName),
      onHeaderCell: headerCell,
      render: (_, row) => <Typography.Link strong onClick={() => onOpenDetail(row)}>{row.productName}</Typography.Link>,
    },
    title: {
      key: "title",
      dataIndex: "title",
      title: title("title", fieldTitle.title),
      width: columnWidths.title,
      ellipsis: true,
      onHeaderCell: headerCell,
    },
    productType: {
      key: "productType",
      dataIndex: "productType",
      title: title("productType", fieldTitle.productType),
      width: columnWidths.productType,
      onHeaderCell: headerCell,
    },
    listPrice: {
      key: "listPrice",
      dataIndex: "listPrice",
      title: title("listPrice", fieldTitle.listPrice),
      width: columnWidths.listPrice,
      sorter: (a, b) => a.listPrice - b.listPrice,
      onHeaderCell: headerCell,
      render: (_, row) => `$${row.listPrice.toFixed(2)}`,
    },
    salePrice: {
      key: "salePrice",
      dataIndex: "salePrice",
      title: title("salePrice", fieldTitle.salePrice),
      width: columnWidths.salePrice,
      sorter: (a, b) => a.salePrice - b.salePrice,
      onHeaderCell: headerCell,
      render: (_, row) => `$${row.salePrice.toFixed(2)}`,
    },
    productStatus: {
      key: "productStatus",
      dataIndex: "productStatus",
      title: title("productStatus", fieldTitle.productStatus),
      width: columnWidths.productStatus,
      onHeaderCell: headerCell,
      render: (_, row) => <Tag color={statusColorMap[row.productStatus]}>{row.productStatus}</Tag>,
    },
    lifecycle: {
      key: "lifecycle",
      dataIndex: "lifecycle",
      title: title("lifecycle", fieldTitle.lifecycle),
      width: columnWidths.lifecycle,
      onHeaderCell: headerCell,
    },
    listedAt: {
      key: "listedAt",
      dataIndex: "listedAt",
      title: title("listedAt", fieldTitle.listedAt),
      width: columnWidths.listedAt,
      sorter: (a, b) => a.listedAt.localeCompare(b.listedAt),
      onHeaderCell: headerCell,
    },
    category: {
      key: "category",
      dataIndex: "category",
      title: title("category", fieldTitle.category),
      width: columnWidths.category,
      onHeaderCell: headerCell,
    },
    wfsAvailableInventory: {
      key: "wfsAvailableInventory",
      dataIndex: "wfsAvailableInventory",
      title: title("wfsAvailableInventory", fieldTitle.wfsAvailableInventory),
      width: columnWidths.wfsAvailableInventory,
      sorter: (a, b) => a.wfsAvailableInventory - b.wfsAvailableInventory,
      onHeaderCell: headerCell,
    },
    inboundInventory: {
      key: "inboundInventory",
      dataIndex: "inboundInventory",
      title: title("inboundInventory", fieldTitle.inboundInventory),
      width: columnWidths.inboundInventory,
      sorter: (a, b) => a.inboundInventory - b.inboundInventory,
      onHeaderCell: headerCell,
    },
    sales90Days: {
      key: "sales90Days",
      dataIndex: "sales90Days",
      title: title("sales90Days", fieldTitle.sales90Days),
      width: columnWidths.sales90Days,
      sorter: (a, b) => a.sales90Days - b.sales90Days,
      onHeaderCell: headerCell,
    },
    adSpend30Days: {
      key: "adSpend30Days",
      dataIndex: "adSpend30Days",
      title: title("adSpend30Days", fieldTitle.adSpend30Days),
      width: columnWidths.adSpend30Days,
      sorter: (a, b) => a.adSpend30Days - b.adSpend30Days,
      onHeaderCell: headerCell,
      render: (_, row) => `$${row.adSpend30Days.toFixed(2)}`,
    },
    disabledReason: {
      key: "disabledReason",
      dataIndex: "disabledReason",
      title: title("disabledReason", fieldTitle.disabledReason),
      width: columnWidths.disabledReason,
      onHeaderCell: headerCell,
      render: (_, row) => row.disabledReason || "-",
    },
    listingStatus: {
      key: "listingStatus",
      dataIndex: "listingStatus",
      title: title("listingStatus", fieldTitle.listingStatus),
      width: columnWidths.listingStatus,
      onHeaderCell: headerCell,
      render: (_, row) => <Tag color={statusColorMap[row.listingStatus]}>{row.listingStatus}</Tag>,
    },
    buyBoxStatus: {
      key: "buyBoxStatus",
      dataIndex: "buyBoxStatus",
      title: title("buyBoxStatus", fieldTitle.buyBoxStatus),
      width: columnWidths.buyBoxStatus,
      onHeaderCell: headerCell,
      render: (_, row) => <Tag color={statusColorMap[row.buyBoxStatus]}>{row.buyBoxStatus}</Tag>,
    },
    walmartSeller: {
      key: "walmartSeller",
      dataIndex: "walmartSeller",
      title: title("walmartSeller", fieldTitle.walmartSeller),
      width: columnWidths.walmartSeller,
      onHeaderCell: headerCell,
    },
    resold: {
      key: "resold",
      dataIndex: "resold",
      title: title("resold", fieldTitle.resold),
      width: columnWidths.resold,
      onHeaderCell: headerCell,
      render: (_, row) => <Tag color={statusColorMap[row.resold]}>{row.resold}</Tag>,
    },
    checkedAt: {
      key: "checkedAt",
      dataIndex: "checkedAt",
      title: title("checkedAt", fieldTitle.checkedAt),
      width: columnWidths.checkedAt,
      sorter: (a, b) => a.checkedAt.localeCompare(b.checkedAt),
      onHeaderCell: headerCell,
    },
    rating: {
      key: "rating",
      dataIndex: "rating",
      title: title("rating", fieldTitle.rating),
      width: columnWidths.rating,
      sorter: (a, b) => a.rating - b.rating,
      onHeaderCell: headerCell,
    },
    reviewCount: {
      key: "reviewCount",
      dataIndex: "reviewCount",
      title: title("reviewCount", fieldTitle.reviewCount),
      width: columnWidths.reviewCount,
      sorter: (a, b) => a.reviewCount - b.reviewCount,
      onHeaderCell: headerCell,
    },
    brand: {
      key: "brand",
      dataIndex: "brand",
      title: title("brand", fieldTitle.brand),
      width: columnWidths.brand,
      onHeaderCell: headerCell,
    },
    tags: {
      key: "tags",
      dataIndex: "tags",
      title: title("tags", fieldTitle.tags),
      width: columnWidths.tags,
      onHeaderCell: headerCell,
      render: (_, row) => (
        <Space size={4} wrap>
          {row.tags.map((tag) => <Tag key={tag} color="blue">{tag}</Tag>)}
        </Space>
      ),
    },
    gtin: {
      key: "gtin",
      dataIndex: "gtin",
      title: title("gtin", fieldTitle.gtin),
      width: columnWidths.gtin,
      onHeaderCell: headerCell,
    },
    productGrade: {
      key: "productGrade",
      dataIndex: "productGrade",
      title: title("productGrade", fieldTitle.productGrade),
      width: columnWidths.productGrade,
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
        <Tooltip title="打开 Listing 详情">
          <Button type="link" onClick={() => onOpenDetail(row)}>详情</Button>
        </Tooltip>
      ),
    });

  const scrollX = columns.reduce((sum, column) => sum + Number(column.width ?? 112), 56);

  return (
    <ReportTableShell label="Listing 管理表格" className="listing-management__table-shell">
      <ProTable<ListingManagementRow>
        rowKey="id"
        search={false}
        options={false}
        dataSource={rows}
        columns={columns}
        tableAlertRender={false}
        toolBarRender={false}
        bordered
        size="small"
        scroll={{ x: scrollX }}
        rowSelection={{
          fixed: true,
          selectedRowKeys,
          columnWidth: 48,
          onChange: onSelectionChange,
        }}
        pagination={{
          current: currentPage,
          pageSize,
          total: rows.length,
          showSizeChanger: true,
          showQuickJumper: true,
          pageSizeOptions: REPORT_TABLE_PAGE_SIZE_OPTIONS.map(String),
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

export default ListingManagementTable;
