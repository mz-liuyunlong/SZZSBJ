/** Board table: one row per purchase-order line × plan, server-side paging, configurable columns. */
import { Button, Tooltip, Typography } from "antd";
import { ProTable, type ProColumns } from "@ant-design/pro-components";
import ReportTableShell from "@/components/report-table/ReportTableShell";
import ResizableColumnTitle from "@/components/report-table/ResizableColumnTitle";
import { CopyableTextCell, MoneyCell } from "@/components/report-table/cells";
import EmptyState from "@/shared/states/EmptyState";
import {
  ItemIdCell,
  SkuCycleBriefCell,
  StageCell,
} from "@/pages/pmc/purchase-board/components/PurchaseBoardCells";
import {
  EMPTY,
  currencySign,
  progressText,
  purchaseCycleText,
} from "@/pages/pmc/purchase-board/purchaseBoardDisplay";
import {
  PURCHASE_BOARD_PAGE_SIZE_OPTIONS,
  purchaseBoardColumnFields,
  purchaseBoardDefaultColumnWidths,
  type PurchaseBoardRow,
} from "@/pages/pmc/purchase-board/purchaseBoardTypes";

const minColumnWidths: Record<string, number> = {
  purchaseOrderSn: 150,
  stage: 180,
  store: 120,
  sku: 130,
  productName: 180,
  gtin: 130,
  itemId: 150,
  owner: 90,
  progress: 110,
  orderDate: 104,
  arrivalDate: 104,
  purchaseCycleDays: 104,
  approvalCycleDays: 90,
  skuCycle: 150,
  unitPrice: 96,
  amountAllocated: 104,
  planSn: 130,
  actions: 72,
};

interface PurchaseBoardTableProps {
  rows: PurchaseBoardRow[];
  total: number;
  appliedColumnKeys: string[];
  columnWidths: Record<string, number>;
  currentPage: number;
  pageSize: number;
  emptyText: string;
  onColumnWidthChange: (key: string, width: number) => void;
  onCurrentPageChange: (page: number) => void;
  onPageSizeChange: (pageSize: number) => void;
  onOpenDetail: (row: PurchaseBoardRow) => void;
}

function PurchaseBoardTable({
  rows,
  total,
  appliedColumnKeys,
  columnWidths,
  currentPage,
  pageSize,
  emptyText,
  onColumnWidthChange,
  onCurrentPageChange,
  onPageSizeChange,
  onOpenDetail,
}: PurchaseBoardTableProps) {
  const title = (key: string, label: string) => (
    <ResizableColumnTitle
      label={label}
      minWidth={minColumnWidths[key] ?? 96}
      width={columnWidths[key] ?? purchaseBoardDefaultColumnWidths[key] ?? 112}
      onWidthChange={(width) => onColumnWidthChange(key, width)}
    />
  );
  const headerCell = () => ({ className: "report-table-resizable-header-cell" });
  const fieldTitle = Object.fromEntries(purchaseBoardColumnFields.map((field) => [field.key, field.title]));
  const width = (key: string) => columnWidths[key] ?? purchaseBoardDefaultColumnWidths[key];

  const allColumns: Record<string, ProColumns<PurchaseBoardRow>> = {
    purchaseOrderSn: {
      key: "purchaseOrderSn",
      title: title("purchaseOrderSn", fieldTitle.purchaseOrderSn),
      width: width("purchaseOrderSn"),
      fixed: "left",
      onHeaderCell: headerCell,
      render: (_, row) => (
        <CopyableTextCell text={row.purchaseOrderSn} label="采购单号" link onOpen={() => onOpenDetail(row)} />
      ),
    },
    stage: {
      key: "stage",
      title: title("stage", fieldTitle.stage),
      width: width("stage"),
      onHeaderCell: headerCell,
      render: (_, row) => <StageCell stage={row.stage} wfsNotReady={row.itemId.wfsNotReady} />,
    },
    store: {
      key: "store",
      title: title("store", fieldTitle.store),
      width: width("store"),
      ellipsis: true,
      onHeaderCell: headerCell,
      render: (_, row) => (
        row.store.attributed
          ? (row.store.name ?? row.store.id ?? EMPTY)
          : <Typography.Text type="warning">未归属店铺</Typography.Text>
      ),
    },
    sku: {
      key: "sku",
      title: title("sku", fieldTitle.sku),
      width: width("sku"),
      onHeaderCell: headerCell,
      render: (_, row) => (row.sku ? <CopyableTextCell text={row.sku} label="SKU" /> : EMPTY),
    },
    productName: {
      key: "productName",
      title: title("productName", fieldTitle.productName),
      width: width("productName"),
      ellipsis: true,
      onHeaderCell: headerCell,
      render: (_, row) => row.productName ?? EMPTY,
    },
    gtin: {
      key: "gtin",
      title: title("gtin", fieldTitle.gtin),
      width: width("gtin"),
      onHeaderCell: headerCell,
      render: (_, row) => (row.itemId.gtin ? <CopyableTextCell text={row.itemId.gtin} label="GTIN" /> : EMPTY),
    },
    itemId: {
      key: "itemId",
      title: title("itemId", fieldTitle.itemId),
      width: width("itemId"),
      onHeaderCell: headerCell,
      render: (_, row) => <ItemIdCell row={row} />,
    },
    owner: {
      key: "owner",
      title: title("owner", fieldTitle.owner),
      width: width("owner"),
      onHeaderCell: headerCell,
      render: (_, row) => row.owner.name ?? EMPTY,
    },
    progress: {
      key: "progress",
      title: title("progress", fieldTitle.progress),
      width: width("progress"),
      onHeaderCell: headerCell,
      render: (_, row) => <span className="report-table-metric">{progressText(row)}</span>,
    },
    orderDate: {
      key: "orderDate",
      title: title("orderDate", fieldTitle.orderDate),
      width: width("orderDate"),
      onHeaderCell: headerCell,
      render: (_, row) => row.orderDate ?? EMPTY,
    },
    arrivalDate: {
      key: "arrivalDate",
      title: title("arrivalDate", fieldTitle.arrivalDate),
      width: width("arrivalDate"),
      onHeaderCell: headerCell,
      render: (_, row) => (
        row.arrivalDate
          ? <Tooltip title={row.arrivalReceiptOrderSn ? `到仓收货单：${row.arrivalReceiptOrderSn}` : undefined}>{row.arrivalDate}</Tooltip>
          : EMPTY
      ),
    },
    purchaseCycleDays: {
      key: "purchaseCycleDays",
      title: title("purchaseCycleDays", fieldTitle.purchaseCycleDays),
      width: width("purchaseCycleDays"),
      onHeaderCell: headerCell,
      render: (_, row) => purchaseCycleText(row.purchaseCycleDays),
    },
    approvalCycleDays: {
      key: "approvalCycleDays",
      title: title("approvalCycleDays", fieldTitle.approvalCycleDays),
      width: width("approvalCycleDays"),
      onHeaderCell: headerCell,
      render: (_, row) => (row.approvalCycleDays === null ? EMPTY : `${row.approvalCycleDays} 天`),
    },
    skuCycle: {
      key: "skuCycle",
      title: title("skuCycle", fieldTitle.skuCycle),
      width: width("skuCycle"),
      onHeaderCell: headerCell,
      render: (_, row) => (
        <Tooltip title="打开详情查看近 5 单样本">
          <span><SkuCycleBriefCell cycle={row.skuCycle} /></span>
        </Tooltip>
      ),
    },
    unitPrice: {
      key: "unitPrice",
      title: title("unitPrice", fieldTitle.unitPrice),
      width: width("unitPrice"),
      align: "right",
      onHeaderCell: headerCell,
      render: (_, row) => <MoneyCell value={row.unitPrice} currency={currencySign(row.currencyCode)} />,
    },
    amountAllocated: {
      key: "amountAllocated",
      title: title("amountAllocated", fieldTitle.amountAllocated),
      width: width("amountAllocated"),
      align: "right",
      onHeaderCell: headerCell,
      render: (_, row) => <MoneyCell value={row.amountAllocated} currency={currencySign(row.currencyCode)} />,
    },
    planSn: {
      key: "planSn",
      title: title("planSn", fieldTitle.planSn),
      width: width("planSn"),
      onHeaderCell: headerCell,
      render: (_, row) => (
        row.planSns.length > 0
          ? <span className="purchase-board__plan-sns">{row.planSns.map((sn) => <span key={sn}>{sn}</span>)}</span>
          : <Typography.Text type="secondary">无计划</Typography.Text>
      ),
    },
  };

  const columns = appliedColumnKeys
    .flatMap((key) => (allColumns[key] ? [allColumns[key]] : []))
    .concat({
      key: "actions",
      title: title("actions", "操作"),
      width: width("actions"),
      fixed: "right",
      onHeaderCell: headerCell,
      render: (_, row) => (
        <Button type="link" size="small" onClick={() => onOpenDetail(row)}>详情</Button>
      ),
    });
  const scrollX = columns.reduce((sum, column) => sum + Number(column.width ?? 112), 0);

  return (
    <ReportTableShell label="采购看板表格" className="purchase-board__table-shell">
      <ProTable<PurchaseBoardRow>
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
        locale={{ emptyText: <EmptyState title="暂无采购单" description={emptyText} compact /> }}
        pagination={{
          current: currentPage,
          pageSize,
          total,
          showSizeChanger: true,
          showQuickJumper: true,
          pageSizeOptions: PURCHASE_BOARD_PAGE_SIZE_OPTIONS,
          showTotal: (count) => `共 ${count.toLocaleString()} 条明细`,
          onChange: (page, nextPageSize) => {
            if (nextPageSize !== pageSize) {
              onPageSizeChange(nextPageSize);
              return;
            }
            onCurrentPageChange(page);
          },
        }}
      />
    </ReportTableShell>
  );
}

export default PurchaseBoardTable;
