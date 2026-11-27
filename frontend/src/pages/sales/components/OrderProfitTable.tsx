import { reportTotalValue, type ReportTableTotals } from "@/pages/sales/reportTotals";
import { orderProfitSortFields, nextSalesReportSort, type SalesReportSort } from "@/pages/sales/reportSort";
/** Product-ID order-profit report table with the daily-sales interaction model. */
import { ProTable, type ProColumns } from "@ant-design/pro-components";
import { Button, Empty, Table, Tooltip } from "antd";
import type { Key, MouseEvent as SortMouseEvent, KeyboardEvent as SortKeyboardEvent } from "react";
import ReportTableShell, {
  ReportTableSelectionBar,
} from "@/components/report-table/ReportTableShell";
import { REPORT_TABLE_PAGE_SIZE_OPTIONS } from "@/components/report-table/pagination";
import ResizableColumnTitle from "@/components/report-table/ResizableColumnTitle";
import {
  ImageCell,
  ProductIdentityCell,
  SkuMskuIdentityCell,
  MoneyCell,
  PercentCell,
  StatusTagCell,
  TrendPreviewCell,
} from "@/components/report-table/cells";
import {
  dynamicCurrencyTitle,
  renderCnySourceMoney,
  renderUsdSourceMoney,
  renderUsdSourceProfitMoney,
} from "@/components/report-table/moneyRenderers";
import {
  MOCK_USD_TO_CNY_RATE,
  orderProfitColumnFields,
  type OrderProfitCostStatus,
  type OrderProfitCurrency,
  type OrderProfitRow,
} from "@/pages/sales/orderProfitTypes";

interface OrderProfitTableProps {
  tableTotals?: ReportTableTotals | null;
  sort?: SalesReportSort | null;
  onSortChange?: (sort: SalesReportSort | null) => void;
  rows: OrderProfitRow[];
  total?: number;
  currency: OrderProfitCurrency;
  appliedColumnKeys: string[];
  columnWidths: Record<string, number>;
  currentPage: number;
  pageSize: number;
  selectedRowKeys: Key[];
  onColumnWidthChange: (key: string, width: number) => void;
  onCurrentPageChange: (page: number) => void;
  onPageSizeChange: (pageSize: number) => void;
  onSelectionChange: (keys: Key[]) => void;
  onBulkExport: () => void;
  onCopy: (text: string) => void;
  onOpenDetail: (row: OrderProfitRow) => void;
}

const statusColors: Record<OrderProfitCostStatus, string> = {
  已完成: "success",
  待补齐: "warning",
  异常: "error",
  部分缺失: "processing",
};


const money = (key: keyof OrderProfitRow, currency: OrderProfitCurrency) => (
  renderUsdSourceMoney<OrderProfitRow>(key, currency, MOCK_USD_TO_CNY_RATE)
);

const cnyMoney = (
  key: keyof OrderProfitRow,
  currency: OrderProfitCurrency,
) => (
  renderCnySourceMoney<OrderProfitRow>(
    key,
    currency,
    MOCK_USD_TO_CNY_RATE,
  )
);
const profitMoney = (key: keyof OrderProfitRow, currency: OrderProfitCurrency) => (
  renderUsdSourceProfitMoney<OrderProfitRow>(key, currency, MOCK_USD_TO_CNY_RATE)
);
const percent = (key: keyof OrderProfitRow) =>
  (_: unknown, row: OrderProfitRow) => {
    const value = row[key];
    return <PercentCell value={typeof value === "number" ? value : null} />;
  };


const roiValue = (_: unknown, row: OrderProfitRow) => {
  const value = row.roi;

  return (
    <span className="report-table-metric">
      {typeof value === "number" && Number.isFinite(value)
        ? value.toFixed(2)
        : "-"}
    </span>
  );
};

const totalMoneyKeys = new Set([
  "salesAmount",
  "sampleAmount",
  "refundLossAmount",
  "adSpend",
  "semAdSpend",
  "totalAdSpend",
  "wfsDeliveryFee",
  "wfsLowPriceSurcharge",
  "commission",
  "purchaseCost",
  "firstLegCost",
  "storageFee",
  "totalCost",
  "orderProfit",
]);
const totalIntegerKeys = new Set([
  "salesVolume",
  "orderCount",
  "sampleQuantity",
  "refundQuantity",
  "wfsAvailableInventory",
]);

function TotalCell({
  columnKey,
  currency,
  tableTotals,
}: {
  columnKey: string;
  currency: OrderProfitCurrency;
  tableTotals?: ReportTableTotals | null;
}) {
  if (columnKey === "image") return <span className="report-table-summary-label">总计</span>;
  const value = reportTotalValue(tableTotals, currency, columnKey);
  if (totalMoneyKeys.has(columnKey) || columnKey === "averagePrice" || columnKey === "averageProfitPerOrder") {
    const profit = columnKey === "orderProfit" || columnKey === "averageProfitPerOrder";
    return <MoneyCell value={value} currency={currency === "CNY" ? "¥" : "$"} tone={profit ? "profit" : undefined} />;
  }
  if (totalIntegerKeys.has(columnKey)) {
    return <span className="report-table-metric">{value == null ? "—" : value.toLocaleString("zh-CN")}</span>;
  }
  if (columnKey === "returnRate30Days") {
    return <Tooltip title="缺少完整的30天退货量及销量分母，暂不展示全量30天退货率"><span><PercentCell value={value} /></span></Tooltip>;
  }
  if (columnKey === "adRatio" || columnKey === "profitMargin") return <PercentCell value={value} />;
  if (columnKey === "roi") return <span className="report-table-metric">{value == null ? "-" : value.toFixed(2)}</span>;
  return null;
}

const dynamicCurrencyColumnTitles: Partial<Record<string, string>> = {
  wfsDeliveryUnitPrice: "WFS配送单价",
  purchaseUnitPriceCny: "采购单价",
  firstLegUnitPriceCny: "头程单价",
  storageUnitPrice: "仓储单价",
};

const columnTitle = (
  key: string,
  fallback: string,
  currency: OrderProfitCurrency,
) => {
  const dynamic = dynamicCurrencyColumnTitles[key];

  return dynamic
    ? dynamicCurrencyTitle(dynamic, currency)
    : fallback;
};

function createColumns(
  onCopy: (text: string) => void,
  onOpenDetail: (row: OrderProfitRow) => void,
  currency: OrderProfitCurrency,
): ProColumns<OrderProfitRow>[] {
  return [
    { title: "图片", key: "image", width: 72, fixed: "left", render: () => <ImageCell label="订单利润商品图片占位" /> },
    {
      title: "商品ID/品名",
      key: "productIdName",
      width: 188,
      fixed: "left",
            className: "report-table-product-identity-column",
render: (_, row) => (
        <ProductIdentityCell
            productId={row.productId}
            productName={row.productName}
            onCopy={onCopy}
          />
      ),
    },
    {
      title: "SKU/MSKU",
      key: "skuMsku",
      width: 188,
      fixed: "left",
            className: "report-table-sku-msku-identity-column",
render: (_, row) => (
        <SkuMskuIdentityCell
          sku={row.sku}
          msku={row.msku}
          onCopy={onCopy}
        />
      ),
    },
    { title: "平台", dataIndex: "platform", key: "platform", width: 96 },
    {
      title: "店铺",
      dataIndex: "store",
      key: "store",
      width: 160,
      render: (_, row) => {
        const fullText = row.storeFullText ?? row.store;
        return fullText && fullText !== row.store
          ? (
              <Tooltip title={fullText}>
                <span className="report-table-text-ellipsis">{row.store}</span>
              </Tooltip>
            )
          : row.store;
      },
    },
    { title: "负责人", dataIndex: "owner", key: "owner", width: 96 },
    {
      title: "前7天销量趋势",
      key: "sevenDaySales",
      width: 140,
      render: (_, row) => <TrendPreviewCell values={row.sevenDaySales} dates={row.sevenDayDates} />,
    },
    { title: "销量", dataIndex: "salesVolume", key: "salesVolume", width: 88 },
    { title: "订单量", dataIndex: "orderCount", key: "orderCount", width: 88 },
    { title: "销售额", key: "salesAmount", width: 112, render: money("salesAmount", currency) },
    { title: "平均售价", key: "averagePrice", width: 112, render: money("averagePrice", currency) },

    { title: "送样量", dataIndex: "sampleQuantity", key: "sampleQuantity", width: 88 },
    { title: "送样金额", key: "sampleAmount", width: 112, render: money("sampleAmount", currency) },

    { title: "退货量", dataIndex: "refundQuantity", key: "refundQuantity", width: 88 },
    { title: "退款金额", key: "refundLossAmount", width: 104, render: money("refundLossAmount", currency) },
    { title: "退货率30天", key: "returnRate30Days", width: 120, render: percent("returnRate30Days") },

    { title: "广告费", key: "adSpend", width: 104, render: money("adSpend", currency) },
    { title: "SEM费用", key: "semAdSpend", width: 104, render: money("semAdSpend", currency) },
    { title: "总广告费", key: "totalAdSpend", width: 112, render: money("totalAdSpend", currency) },
    { title: "广告占比", key: "adRatio", width: 104, render: percent("adRatio") },

    { title: "WFS总配送费", key: "wfsDeliveryFee", width: 132, render: money("wfsDeliveryFee", currency) },
    { title: "低价配送附加费", key: "wfsLowPriceSurcharge", width: 144, render: money("wfsLowPriceSurcharge", currency) },
    { title: "WFS配送单价", key: "wfsDeliveryUnitPrice", width: 148, render: money("wfsDeliveryUnitPrice", currency) },

    { title: "佣金", key: "commission", width: 104, render: money("commission", currency) },

    { title: "采购总成本", key: "purchaseCost", width: 128, render: money("purchaseCost", currency) },
    { title: "采购单价", key: "purchaseUnitPriceCny", width: 128, render: cnyMoney("purchaseUnitPriceCny", currency) },

    { title: "头程总成本", key: "firstLegCost", width: 128, render: money("firstLegCost", currency) },
    { title: "头程单价", key: "firstLegUnitPriceCny", width: 128, render: cnyMoney("firstLegUnitPriceCny", currency) },

    { title: "总仓储费", key: "storageFee", width: 112, render: money("storageFee", currency) },
    { title: "仓储单价", key: "storageUnitPrice", width: 128, render: money("storageUnitPrice", currency) },

    { title: "WFS可售库存", dataIndex: "wfsAvailableInventory", key: "wfsAvailableInventory", width: 128 },
    { title: "总成本", key: "totalCost", width: 112, render: money("totalCost", currency) },
    { title: "订单利润", key: "orderProfit", width: 112, render: profitMoney("orderProfit", currency) },
    { title: "平均利润/单", key: "averageProfitPerOrder", width: 128, render: profitMoney("averageProfitPerOrder", currency) },
    { title: "利润率", key: "profitMargin", width: 96, render: percent("profitMargin") },
    { title: "ROI", key: "roi", width: 88, render: roiValue },
    { title: "成本状态", key: "costStatus", width: 112, render: (_, row) => <StatusTagCell label={row.costStatus} color={statusColors[row.costStatus]} /> },
    {
      title: "操作",
      key: "actions",
      width: 96,
      fixed: "right",
      render: (_, row) => <Button type="link" onClick={() => onOpenDetail(row)}>详情</Button>,
    },
  ];
}

function OrderProfitTable({
  tableTotals,
  sort = null,
  onSortChange,
  rows,
  total = rows.length,
  currency,
  appliedColumnKeys,
  columnWidths,
  currentPage,
  pageSize,
  selectedRowKeys,
  onColumnWidthChange,
  onCurrentPageChange,
  onPageSizeChange,
  onSelectionChange,
  onBulkExport,
  onCopy,
  onOpenDetail,
}: OrderProfitTableProps) {
  const compactIdentityColumnWidths: Record<string, number> = {
    productIdName: 188,
    skuMsku: 188,
  };
  const columnMap = new Map(createColumns(onCopy, onOpenDetail, currency).map((column) => [String(column.key), column]));
  const columns = appliedColumnKeys.flatMap((key) => {
    const column = columnMap.get(key);
    if (!column) return [];
    const configuredTitle =
      orderProfitColumnFields.find((field) => field.key === key)?.title
      ?? key;

    const title = columnTitle(
      key,
      configuredTitle,
      currency,
    );

    const width = compactIdentityColumnWidths[key] ?? columnWidths[key] ?? (Number(column.width) || 96);
    const minWidth = Math.max(key === "image" ? 72 : 88, title.length * 14 + 28);
    const sortField = orderProfitSortFields[key];
    const sortable = Boolean(sortField && onSortChange);
    return [{
      ...column,
      ...(sortable ? {
        sorter: true,
        sortOrder: sort && sort.field === sortField
          ? (sort.direction === "asc" ? "ascend" as const : "descend" as const) : null,
      } : {}),
      align: "left" as const,
      width,
      onHeaderCell: () => ({
        className: "report-table-resizable-header-cell order-profit__resizable-header-cell",
        ...(sortable ? {
          onClickCapture: (event: SortMouseEvent<HTMLElement>) => {
            const target = event.target;
            if (!(target instanceof Element) || !event.currentTarget.contains(target)) return;
            if (target.closest(".report-table-resize-handle, button, input, textarea, select, a")) return;
            event.stopPropagation();
            onSortChange?.(nextSalesReportSort(sort, sortField));
          },
          onKeyDownCapture: (event: SortKeyboardEvent<HTMLElement>) => {
            if (event.target !== event.currentTarget || !["Enter", " "].includes(event.key)) return;
            event.preventDefault();
            event.stopPropagation();
            onSortChange?.(nextSalesReportSort(sort, sortField));
          },
        } : {}),
      }),
      title: (
        <ResizableColumnTitle
          label={title}
          minWidth={minWidth}
          width={width}
          onWidthChange={(nextWidth) => onColumnWidthChange(key, nextWidth)}
        />
      ),
    }];
  });

  return (
    <ReportTableShell className="order-profit__table" label="订单利润数据表">
      <ProTable<OrderProfitRow>
        columns={columns}
        dataSource={rows}
        rowKey="id"
        rowSelection={{ fixed: true, selectedRowKeys, onChange: onSelectionChange }}
        search={false}
        options={false}
        toolBarRender={false}
        tableAlertRender={false}
        tableAlertOptionRender={false}
        scroll={{ x: "max-content", y: "100%" }}
        summary={() => (
          <Table.Summary fixed="bottom">
            <Table.Summary.Row className="order-profit__total-row" data-testid="order-profit-total-row">
              <Table.Summary.Cell index={0} />
              {columns.map((column, index) => {
                const key = String(column.key);
                return (
                  <Table.Summary.Cell
                    key={key}
                    index={index + 1}
                    align="left"
                    className={`order-profit__total-cell order-profit__total-cell--${key}`}
                  >
                    <TotalCell columnKey={key} currency={currency} tableTotals={tableTotals} />
                  </Table.Summary.Cell>
                );
              })}
            </Table.Summary.Row>
          </Table.Summary>
        )}
        footer={() => (
          <ReportTableSelectionBar
            selectedCount={selectedRowKeys.length}
            actions={[{ key: "export", label: "批量导出", onClick: onBulkExport }]}
          />
        )}
        pagination={{
          current: currentPage,
          pageSize,
          total,
          showSizeChanger: true,
          showQuickJumper: true,
          pageSizeOptions: REPORT_TABLE_PAGE_SIZE_OPTIONS,
          showTotal: (total) => `共 ${total} 条`,
          onChange: (nextPage, nextPageSize) => {
            if (nextPageSize !== pageSize) {
              onPageSizeChange(nextPageSize);
              return;
            }
            onCurrentPageChange(nextPage);
          },
        }}
        locale={{
          emptyText: <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无匹配订单利润数据" />,
        }}
      />
    </ReportTableShell>
  );
}

export default OrderProfitTable;
