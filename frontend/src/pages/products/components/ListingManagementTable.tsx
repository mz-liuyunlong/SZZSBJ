import { RobotOutlined } from "@ant-design/icons";
import {
  Button,
  Space,
  Tag,
  Popconfirm,
  Popover,
  Tooltip } from "antd"; import { ProTable,
  type ProColumns } from "@ant-design/pro-components"; import type { Key } from "react"; import ReportTableShell,
  {   ReportTableSelectionBar,
  } from "@/components/report-table/ReportTableShell"; import {   REPORT_TABLE_PAGE_SIZE_OPTIONS,
  } from "@/components/report-table/pagination"; import ResizableColumnTitle from "@/components/report-table/ResizableColumnTitle"; import { ImageCell,
  ProductIdentityCell,
  SkuMskuIdentityCell,
  CopyableTextCell,
} from "@/components/report-table/cells";
import {
  listingColumnFields,
  type ListingManagementRow,
} from "@/pages/products/listingManagementData";

/** Match the observed two-line Listing row height without changing its visual size. */
const LISTING_VIRTUAL_ROW_HEIGHT_ESTIMATE = 61;

const minColumnWidths: Record<string, number> = {
  image: 72,
  productIdName: 240,
  skuMsku: 190,
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
  fulfillmentMethod: 120,
  gptAnalysis: 96,
  listedAt: 140,
  firstWfsAvailableAt: 150,
  category: 120,
  wfsAvailableInventory: 140,
  inboundInventory: 130,
  sales30Days: 130,
  adSpend30Days: 140,
  disabledReason: 130,
  listingStatus: 130,
  buyBoxStatus: 130,
  walmartSeller: 140,
  resold: 120,
  checkedAt: 160,
  dataUpdatedAt: 160,
  monitorSource: 140,
  monitorAgeHours: 150,
  monitorStatus: 130,
  monitorError: 150,
  monitorImageCount: 120,
  rating: 100,
  reviewCount: 110,
  brand: 130,
  tags: 130,
  gtin: 160,
  productGrade: 120,
  archiveReason: 180,
  actions: 190,
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
  tagColors?: Record<string, string>;
  total: number;
  appliedColumnKeys: string[];
  columnWidths: Record<string, number>;
  currentPage: number;
  pageSize: number;
  virtualScrollY?: number;
  selectedRowKeys: Key[];
  onColumnWidthChange: (key: string, width: number) => void;
  onCurrentPageChange: (page: number) => void;
  onPageSizeChange: (pageSize: number) => void;
  onSelectionChange: (keys: Key[]) => void;
  onOpenDetail: (row: ListingManagementRow) => void;
  onOpenGptAnalysis?: (row: ListingManagementRow) => void;
  onOpenEvaluation?: (row: ListingManagementRow) => void;
  onArchiveListing?: (row: ListingManagementRow) => void;
  onRestoreListing?: (row: ListingManagementRow) => void;
  onBatchSetTags: () => void;
  onBatchArchive?: () => void;
  onBatchRestore?: () => void;
  onBulkExport: () => void;
  exporting?: boolean;
}

function ListingManagementTable({
  rows,
  tagColors = {},
  total,
  appliedColumnKeys,
  columnWidths,
  currentPage,
  pageSize,
  virtualScrollY = 360,
  selectedRowKeys,
  onColumnWidthChange,
  onCurrentPageChange,
  onPageSizeChange,
  onSelectionChange,
  onOpenDetail,
  onOpenGptAnalysis,
  onOpenEvaluation,
  onArchiveListing,
  onRestoreListing,
  onBatchSetTags,
  onBatchArchive,
  onBatchRestore,
  onBulkExport,
  exporting = false,
}: ListingManagementTableProps) {
  // Only the large pages need row virtualization. Original columns, pinned columns,
  // sorters, selection and all per-row actions are kept unchanged in both modes.
  const virtual = pageSize >= 500;
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
        <Space size={2}>
          <ImageCell
            image={row.image}
            label={`Listing 图片：${row.productName}`}
            placement="right"
          />
          {(row.monitorImages?.length ?? 0) > 1 && (
            <Popover
              title="监控商品图片"
              content={
                <Space wrap>
                  {row.monitorImages?.map((image, index) => (
                    <ImageCell key={`${row.id}-image-${index}`} image={image} label={`监控图片 ${index + 1}`} placement="right" />
                  ))}
                </Space>
              }
            >
              <Button size="small" type="link">+{(row.monitorImages?.length ?? 1) - 1}</Button>
            </Popover>
          )}
        </Space>
      ),
    },
    productIdName: {
      key: "productIdName",
      title: title("productIdName", fieldTitle.productIdName ?? "商品ID/品名"),
      width: columnWidths.productIdName,
      fixed: "left",
      sorter: (a, b) => a.productId.localeCompare(b.productId),
      onHeaderCell: headerCell,
      render: (_, row) => (
        <ProductIdentityCell
          productId={row.productId}
          productName={row.productName}
        />
      ),
    },
    skuMsku: {
      key: "skuMsku",
      title: title("skuMsku", fieldTitle.skuMsku ?? "SKU/MSKU"),
      width: columnWidths.skuMsku,
      fixed: "left",
      sorter: (a, b) => (
        a.sku.localeCompare(b.sku)
        || a.msku.localeCompare(b.msku)
      ),
      onHeaderCell: headerCell,
      render: (_, row) => (
        <SkuMskuIdentityCell
          sku={row.sku}
          msku={row.msku}
        />
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
        <CopyableTextCell
          text={row.msku}
          label="MSKU"
          link
          onOpen={() => onOpenDetail(row)}
        />
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
      render: (_, row) => (
        <CopyableTextCell
          text={row.productId}
          label="商品ID"
        />
      ),
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
      sorter: (a, b) => a.sku.localeCompare(b.sku),
      onHeaderCell: headerCell,
      render: (_, row) => (
        <CopyableTextCell
          text={row.sku}
          label="SKU"
        />
      ),
    },
    productName: {
      key: "productName",
      dataIndex: "productName",
      title: title("productName", fieldTitle.productName),
      width: columnWidths.productName,
      ellipsis: true,
      sorter: (a, b) => a.productName.localeCompare(b.productName),
      onHeaderCell: headerCell,
      render: (_, row) => (
        <CopyableTextCell
          text={row.productName}
          label="商品名称"
          link
          onOpen={() => onOpenDetail(row)}
        />
      ),
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
      render: (_, row) => row.listPriceKnown === false ? "-" : `${row.listPriceCurrency || "USD"} ${row.listPrice.toFixed(2)}`,
    },
    salePrice: {
      key: "salePrice",
      dataIndex: "salePrice",
      title: title("salePrice", fieldTitle.salePrice),
      width: columnWidths.salePrice,
      sorter: (a, b) => a.salePrice - b.salePrice,
      onHeaderCell: headerCell,
      render: (_, row) => row.salePriceKnown === false ? "-" : `${row.salePriceCurrency || "USD"} ${row.salePrice.toFixed(2)}`,
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
    fulfillmentMethod: {
      key: "fulfillmentMethod",
      dataIndex: "fulfillmentMethod",
      title: title("fulfillmentMethod", fieldTitle.fulfillmentMethod),
      width: columnWidths.fulfillmentMethod,
      onHeaderCell: headerCell,
    },
    gptAnalysis: {
      key: "gptAnalysis",
      title: title("gptAnalysis", fieldTitle.gptAnalysis ?? "GPT分析"),
      width: columnWidths.gptAnalysis,
      align: "center",
      onHeaderCell: headerCell,
      render: (_, row) => (
        <Tooltip title="保存GPT关键词/广告分析链接">
          <Button
            type="text"
            size="small"
            className="listing-management__gpt-analysis-button"
            icon={<RobotOutlined />}
            onClick={() => onOpenGptAnalysis?.(row)}
          />
        </Tooltip>
      ),
    },
    listedAt: {
      key: "listedAt",
      dataIndex: "listedAt",
      title: title("listedAt", fieldTitle.listedAt),
      width: columnWidths.listedAt,
      sorter: (a, b) => a.listedAt.localeCompare(b.listedAt),
      onHeaderCell: headerCell,
      render: (_, row) => (
        <Tooltip title={`日期来源：${row.listingDateSource || "未知"}${row.listingStartRaw ? `；ERP原始值：${row.listingStartRaw}` : ""}`}>
          <span>{row.listedAt || "待核实"}</span>
        </Tooltip>
      ),
    },
    firstWfsAvailableAt: {
      key: "firstWfsAvailableAt",
      dataIndex: "firstWfsAvailableAt",
      title: title("firstWfsAvailableAt", fieldTitle.firstWfsAvailableAt),
      width: columnWidths.firstWfsAvailableAt,
      onHeaderCell: headerCell,
      render: (_, row) => row.firstWfsAvailableAt || "-",
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
    sales30Days: {
      key: "sales30Days",
      dataIndex: "sales30Days",
      title: title("sales30Days", fieldTitle.sales30Days),
      width: columnWidths.sales30Days,
      sorter: (a, b) => a.sales30Days - b.sales30Days,
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
    dataUpdatedAt: {
      key: "dataUpdatedAt",
      dataIndex: "dataUpdatedAt",
      title: title("dataUpdatedAt", fieldTitle.dataUpdatedAt),
      width: columnWidths.dataUpdatedAt,
      onHeaderCell: headerCell,
    },
    monitorSource: {
      key: "monitorSource",
      dataIndex: "monitorSource",
      title: title("monitorSource", fieldTitle.monitorSource),
      width: columnWidths.monitorSource,
      onHeaderCell: headerCell,
    },
    monitorAgeHours: {
      key: "monitorAgeHours",
      dataIndex: "monitorAgeHours",
      title: title("monitorAgeHours", fieldTitle.monitorAgeHours),
      width: columnWidths.monitorAgeHours,
      onHeaderCell: headerCell,
      render: (_, row) => row.monitorAgeHours == null
        ? <Tag>无监控记录</Tag>
        : row.monitorAgeHours >= 48
          ? <Tag color="orange">{row.monitorAgeHours}小时（超48小时）</Tag>
          : <Tag color="green">{row.monitorAgeHours}小时</Tag>,
    },
    monitorStatus: {
      key: "monitorStatus",
      dataIndex: "monitorStatus",
      title: title("monitorStatus", fieldTitle.monitorStatus),
      width: columnWidths.monitorStatus,
      onHeaderCell: headerCell,
    },
    monitorError: {
      key: "monitorError",
      dataIndex: "monitorError",
      title: title("monitorError", fieldTitle.monitorError),
      width: columnWidths.monitorError,
      onHeaderCell: headerCell,
      render: (_, row) => row.monitorError || "-",
    },
    monitorImageCount: {
      key: "monitorImageCount",
      dataIndex: "monitorImageCount",
      title: title("monitorImageCount", fieldTitle.monitorImageCount),
      width: columnWidths.monitorImageCount,
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
          {row.tags.map((tag) => <Tag key={tag} color={tagColors[tag] || "blue"}>{tag}</Tag>)}
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
    archiveReason: {
      key: "archiveReason",
      dataIndex: "archiveReason",
      title: title("archiveReason", fieldTitle.archiveReason ?? "归档原因"),
      width: columnWidths.archiveReason ?? 180,
      ellipsis: true,
      onHeaderCell: headerCell,
      render: (_, row) => {
        const reason = row.archiveReason?.trim();
        if (!reason) return "-";
        return (
          <Tooltip title={reason}>
            <span>{reason}</span>
          </Tooltip>
        );
      },
    },
    productGrade: {
      key: "productGrade",
      dataIndex: "productGrade",
      title: title("productGrade", fieldTitle.productGrade),
      width: columnWidths.productGrade,
      onHeaderCell: headerCell,
    },
  };

  const normalizedAppliedColumnKeys = appliedColumnKeys.reduce<string[]>((keys, key) => {
    const normalizedKey = key === "msku" || key === "productId"
      ? "productIdName"
      : key === "sku" || key === "productName"
        ? "skuMsku"
        : key;

    if (!keys.includes(normalizedKey)) keys.push(normalizedKey);
    return keys;
  }, []);

  const columns = normalizedAppliedColumnKeys
    .flatMap((key) => (allColumns[key] ? [allColumns[key]] : []))
    .concat({
      key: "actions",
      title: title("actions", "操作"),
      width: columnWidths.actions,
      fixed: "right",
      onHeaderCell: headerCell,
      render: (_, row) => (
        <Space size={2}>
          <Button type="link" onClick={() => onOpenEvaluation?.(row)}>试算</Button>
          <Tooltip title="打开 Listing 详情">
            <Button type="link" onClick={() => onOpenDetail(row)}>详情</Button>
          </Tooltip>
          <Popconfirm
            title={row.isArchived ? "确认恢复该 Listing？" : "确认归档该 Listing？"}
            description={
              row.isArchived
                ? "恢复后该 Listing 会重新回到正常状态。"
                : "归档后按钮会变为恢复，不会删除 Listing 数据。"
            }
            okText={row.isArchived ? "确认恢复" : "确认归档"}
            cancelText="取消"
            onConfirm={() => (
              row.isArchived ? onRestoreListing?.(row) : onArchiveListing?.(row)
            )}
          >
            <Button type="link" danger={!row.isArchived}>
              {row.isArchived ? "恢复" : "归档"}
            </Button>
          </Popconfirm>
        </Space>
      ),
    });

  // Avoid repainting unchanged row contents when selection or other page state
  // changes. Updated records are replaced immutably by the page's mutation handlers.
  const optimizedColumns = columns.map((column) => ({
    ...column,
    shouldCellUpdate: (record: ListingManagementRow, previous: ListingManagementRow) => (
      record !== previous
    ),
  }));
  const scrollX = columns.reduce((sum, column) => sum + Number(column.width ?? 112), 56);

  return (
    <ReportTableShell
      label="Listing 管理表格"
      className={virtual
        ? "listing-management__table-shell listing-management__table-shell--virtual"
        : "listing-management__table-shell"}
    >
      <ProTable<ListingManagementRow>
        rowKey="id"
        search={false}
        options={false}
        dataSource={rows}
        columns={optimizedColumns}
        tableAlertRender={false}
        toolBarRender={false}
        bordered
        size="small"
        scroll={{ x: scrollX, y: virtual ? virtualScrollY : "100%" }}
        virtual={virtual}
        {...(virtual ? { listItemHeight: LISTING_VIRTUAL_ROW_HEIGHT_ESTIMATE } : {})}
        tableLayout="fixed"
        rowSelection={{
          fixed: true,
          preserveSelectedRowKeys: true,
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
                key: "set-tags",
                label: "设置标签",
                onClick: onBatchSetTags,
              },
              {
                key: "batch-archive",
                label: "批量归档",
                disabled: selectedRowKeys.length === 0 || !onBatchArchive,
                onClick: () => onBatchArchive?.(),
              },
              {
                key: "batch-restore",
                label: "批量恢复",
                disabled: selectedRowKeys.length === 0 || !onBatchRestore,
                onClick: () => onBatchRestore?.(),
              },
              {
                key: "export",
                label: "导出已选",
                disabled: selectedRowKeys.length === 0 || exporting,
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
