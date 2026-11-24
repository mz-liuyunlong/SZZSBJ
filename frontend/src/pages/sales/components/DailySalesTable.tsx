import { reportTotalValue, type ReportTableTotals } from "@/pages/sales/reportTotals";
import { dailySalesSortFields, nextSalesReportSort, type SalesReportSort } from "@/pages/sales/reportSort";
/** Dense daily-sales report table. */
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
  convertUsdSourceValue,
  dynamicCurrencyTitle,
  renderCnySourceMoney,
  renderCnyUnitTotalOrUsdSourceMoney,
  renderUsdSourceMoney,
  renderUsdSourceProfitMoney,
} from "@/components/report-table/moneyRenderers";
import {
  MOCK_USD_TO_CNY_RATE,
  dailySalesColumnFields,
  type DailySalesCostStatus,
  type DailySalesCurrency,
  type DailySalesRow,
} from "@/pages/sales/dailySalesTypes";

interface DailySalesTableProps {
  tableTotals?: ReportTableTotals | null;
  sort?: SalesReportSort | null;
  onSortChange?: (sort: SalesReportSort | null) => void;
  rows: DailySalesRow[];
  total?: number;
  loading?: boolean;
  currency: DailySalesCurrency;
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
  onOpenDetail: (row: DailySalesRow) => void;
  onOpenLog?: (row: DailySalesRow, kind: "system" | "manual") => void;
}

const statusColors: Record<DailySalesCostStatus, string> = {
  已完成: "success",
  待补齐: "warning",
  异常: "error",
  部分缺失: "processing",
};

const dailySalesFxRate = (row: DailySalesRow) => row.exchangeRate ?? MOCK_USD_TO_CNY_RATE;

function LogCell({ text, onClick, highlight = false }: { text: string; onClick?: () => void; highlight?: boolean }) {
  return (
    <Tooltip
      title={text}
      styles={{
        root: { maxWidth: "min(400px, calc(100vw - 32px))" },
        body: {
          width: 360,
          maxWidth: "100%",
          whiteSpace: "pre-wrap",
          overflowWrap: "anywhere",
          wordBreak: "break-word",
          lineHeight: 1.6,
        },
      }}
    >
      <span className="daily-sales__log-cell">
        <Button
          type="link"
          onClick={onClick}
          disabled={!onClick}
          className="daily-sales__log-button"
          style={{ color: highlight ? "#cf1322" : undefined }}
        >
          {text || "—"}
        </Button>
      </span>
    </Tooltip>
  );
}

const percent = (key: keyof DailySalesRow) =>
  (_: unknown, row: DailySalesRow) => {
    const value = row[key];
    return <PercentCell value={typeof value === "number" ? value : null} />;
  };

const formatRoiRatio = (value: number | null | undefined) => {
  if (typeof value !== "number" || !Number.isFinite(value)) return "—";
  return value.toLocaleString("zh-CN", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
};

function RoiCell({ value }: { value: number | null | undefined }) {
  return <span className="report-table-metric">{formatRoiRatio(value)}</span>;
}

const sampleEvidenceState = (row: DailySalesRow) => {
  const warnings = new Set(row.calculationWarnings ?? []);
  if (warnings.has("sample_verification_pending")) return "pending";
  if (warnings.has("sample_data_not_observed")) return "unknown";
  return "verified";
};

export function DailySalesSampleQuantityCell({ row }: { row: DailySalesRow }) {
  const state = sampleEvidenceState(row);
  if (state === "pending") {
    return (
      <Tooltip title="存在尚未完成商品归属或财务对账的零元订单；这里仅显示当前已归属的送样数量，异常请到数据中心处理">
        <span className="report-table-metric">
          {(row.sampleQuantity ?? 0).toLocaleString("zh-CN")}
        </span>
      </Tooltip>
    );
  }
  if (state === "unknown") {
    return (
      <Tooltip title="当前已记录的送样量；缺少该业务日商品维度的采集证据，数值不代表最终核实结果">
        <span className="report-table-metric">
          {(row.sampleQuantity ?? 0).toLocaleString("zh-CN")}
        </span>
      </Tooltip>
    );
  }
  return (
    <span className="report-table-metric">
      {(row.sampleQuantity ?? 0).toLocaleString("zh-CN")}
    </span>
  );
}

const roiRatio = (key: keyof DailySalesRow) =>
  (_: unknown, row: DailySalesRow) => {
    const value = row[key];
    return <RoiCell value={typeof value === "number" ? value / 100 : null} />;
  };

const numericRowValue = (row: DailySalesRow, key: keyof DailySalesRow) => {
  const value = row[key];
  return typeof value === "number" ? value : null;
};

const renderCostMatchedUsdMoney = (
  amountKey: keyof DailySalesRow,
  quantityKey: keyof DailySalesRow,
  currency: DailySalesCurrency,
) => (_: unknown, row: DailySalesRow) => {
  const amount = numericRowValue(row, amountKey);
  const quantity = numericRowValue(row, quantityKey) ?? 0;

  if (quantity > 0 && amount == null) {
    return (
      <Tooltip title="local_sku 未匹配完整成本">
        <span className="report-table-metric">未匹配</span>
      </Tooltip>
    );
  }

  return (
    <MoneyCell
      value={convertUsdSourceValue(amount, currency, dailySalesFxRate(row))}
      currency={currency === "CNY" ? "¥" : "$"}
    />
  );
};

const totalMoneyKeys = new Set([
  "salesAmount",
  "sampleExcludedAmount",
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
  "orderProfit",
]);
const totalIntegerKeys = new Set([
  "salesVolume",
  "orderCount",
  "sampleQuantity",
  "returnCount",
]);
function TotalCell({
  columnKey,
  currency,
  tableTotals,
}: {
  columnKey: string;
  currency: DailySalesCurrency;
  tableTotals?: ReportTableTotals | null;
}) {
  if (columnKey === "image") return <span className="report-table-summary-label">总计</span>;
  const value = reportTotalValue(tableTotals, currency, columnKey);
  if (totalMoneyKeys.has(columnKey) || columnKey === "averagePrice") {
    return <MoneyCell value={value} currency={currency === "CNY" ? "¥" : "$"} tone={columnKey === "orderProfit" ? "profit" : undefined} />;
  }
  if (totalIntegerKeys.has(columnKey) || columnKey === "wfsAvailableInventory") {
    const content = <span className="report-table-metric">{value == null ? "—" : value.toLocaleString("zh-CN")}</span>;
    if (columnKey === "sampleQuantity" && tableTotals?.sampleEvidence === "pending") {
      return <Tooltip title="合计仅包含已归属的送样数量；部分零元订单仍需在异常中心核对商品或财务数据">{content}</Tooltip>;
    }
    if (columnKey === "sampleQuantity" && tableTotals?.sampleEvidence === "unknown") {
      return <Tooltip title="当前已记录的送样量合计；部分商品缺少采集证据，数值可能不完整">{content}</Tooltip>;
    }
    return content;
  }
  if (columnKey === "returnRate30Days") {
    return <Tooltip title="缺少完整的30天退货量及销量分母，暂不展示全量30天退货率"><span><PercentCell value={value} /></span></Tooltip>;
  }
  if (columnKey === "adRatio" || columnKey === "profitMargin") return <PercentCell value={value} />;
  if (columnKey === "roi") return <RoiCell value={value} />;
  return null;
}

const dynamicCurrencyColumnTitles: Partial<Record<string, string>> = {
  wfsDeliveryUnitPrice: "WFS配送单价",
  purchaseUnitPriceCny: "采购单价",
  firstLegUnitPriceCny: "头程单价",
  storageUnitPrice: "仓储单价",
};

const columnTitle = (key: string, fallback: string, currency: DailySalesCurrency) => {
  const dynamic = dynamicCurrencyColumnTitles[key];
  return dynamic ? dynamicCurrencyTitle(dynamic, currency) : fallback;
};

function createColumns(
  onCopy: (text: string) => void,
  onOpenDetail: (row: DailySalesRow) => void,
  currency: DailySalesCurrency,
  onOpenLog?: (row: DailySalesRow, kind: "system" | "manual") => void,
): ProColumns<DailySalesRow>[] {
  return [
    { title: "图片", key: "image", width: 72, fixed: "left", render: () => <ImageCell label="每日销售商品图片占位" /> },
    { title: "日期", dataIndex: "date", key: "date", width: 112 },
    { title: "店铺", dataIndex: "store", key: "store", width: 120 },
    { title: "负责人", dataIndex: "owner", key: "owner", width: 96 },
    {
      title: "前7天销量趋势",
      key: "sevenDaySales",
      width: 140,
      render: (_, row) => <TrendPreviewCell values={row.sevenDaySales} dates={row.sevenDayDates} />,
    },
    {
      title: "商品ID/品名",
      key: "mskuProductId",
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
      key: "skuProductName",
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
    { title: "销量", dataIndex: "salesVolume", key: "salesVolume", width: 88 },
    { title: "订单量", dataIndex: "orderCount", key: "orderCount", width: 88 },
    { title: "销售额", key: "salesAmount", width: 112, render: renderUsdSourceMoney<DailySalesRow>("salesAmount", currency, dailySalesFxRate) },
    { title: "平均售价", key: "averagePrice", width: 112, render: renderUsdSourceMoney<DailySalesRow>("averagePrice", currency, dailySalesFxRate) },
    { title: "送样量", key: "sampleQuantity", width: 88, render: (_, row) => <DailySalesSampleQuantityCell row={row} /> },
    { title: "送样金额", key: "sampleExcludedAmount", width: 112, render: renderCostMatchedUsdMoney("sampleExcludedAmount", "sampleQuantity", currency) },
    { title: "退货量", dataIndex: "returnCount", key: "returnCount", width: 88 },
    { title: "退款金额", key: "refundLossAmount", width: 104, render: renderCostMatchedUsdMoney("refundLossAmount", "returnCount", currency) },
    { title: "退货率30天", key: "returnRate30Days", width: 120, render: percent("returnRate30Days") },
    { title: "广告费", key: "adSpend", width: 104, render: renderUsdSourceMoney<DailySalesRow>("adSpend", currency, dailySalesFxRate) },
    { title: "SEM费用", key: "semAdSpend", width: 104, render: renderUsdSourceMoney<DailySalesRow>("semAdSpend", currency, dailySalesFxRate) },
    { title: "总广告费", key: "totalAdSpend", width: 112, render: renderUsdSourceMoney("totalAdSpend", currency, dailySalesFxRate) },
    { title: "广告占比", key: "adRatio", width: 104, render: percent("adRatio") },
    { title: "WFS总配送费", key: "wfsDeliveryFee", width: 132, render: renderUsdSourceMoney<DailySalesRow>("wfsDeliveryFee", currency, dailySalesFxRate) },
    { title: "低价配送附加费", key: "wfsLowPriceSurcharge", width: 144, render: renderUsdSourceMoney<DailySalesRow>("wfsLowPriceSurcharge", currency, dailySalesFxRate) },
    { title: "WFS配送单价", key: "wfsDeliveryUnitPrice", width: 148, render: renderUsdSourceMoney<DailySalesRow>("wfsDeliveryUnitPrice", currency, dailySalesFxRate) },
    { title: "佣金", key: "commission", width: 104, render: renderUsdSourceMoney<DailySalesRow>("commission", currency, dailySalesFxRate) },
    { title: "采购总成本", key: "purchaseCost", width: 128, render: renderCnyUnitTotalOrUsdSourceMoney<DailySalesRow>("purchaseCost", "purchaseUnitPriceCny", "costQuantity", currency, dailySalesFxRate) },
    { title: "采购单价", key: "purchaseUnitPriceCny", width: 128, render: renderCnySourceMoney<DailySalesRow>("purchaseUnitPriceCny", currency, dailySalesFxRate) },
    { title: "头程总成本", key: "firstLegCost", width: 128, render: renderCnyUnitTotalOrUsdSourceMoney<DailySalesRow>("firstLegCost", "firstLegUnitPriceCny", "costQuantity", currency, dailySalesFxRate) },
    { title: "头程单价", key: "firstLegUnitPriceCny", width: 128, render: renderCnySourceMoney<DailySalesRow>("firstLegUnitPriceCny", currency, dailySalesFxRate) },
    { title: "总仓储费", key: "storageFee", width: 112, render: renderUsdSourceMoney<DailySalesRow>("storageFee", currency, dailySalesFxRate) },
    { title: "仓储单价", key: "storageUnitPrice", width: 128, render: renderUsdSourceMoney<DailySalesRow>("storageUnitPrice", currency, dailySalesFxRate) },
    {
      title: "WFS可售库存",
      key: "wfsAvailableInventory",
      width: 128,
      render: (_, row) => (
        <span className="report-table-metric">
          {row.wfsAvailableInventory == null
            ? "—"
            : row.wfsAvailableInventory.toLocaleString("zh-CN")}
        </span>
      ),
    },
    { title: "订单利润", key: "orderProfit", width: 112, render: renderUsdSourceProfitMoney<DailySalesRow>("orderProfit", currency, dailySalesFxRate) },
    { title: "利润率", key: "profitMargin", width: 96, render: percent("profitMargin") },
    { title: "ROI", key: "roi", width: 88, render: roiRatio("roi") },
    { title: "成本状态", key: "costStatus", width: 112, render: (_, row) => <StatusTagCell label={row.costStatus} color={statusColors[row.costStatus]} /> },
    { title: "系统运营日志", className: "daily-sales-log-column", key: "systemOperationLog", width: 180, render: (_, row) => <LogCell text={row.systemOperationLog} highlight={row.systemLogHighlight} onClick={onOpenLog ? () => onOpenLog(row, "system") : undefined} /> },
    { title: "运营日志", className: "daily-sales-log-column", key: "operationLog", width: 180, render: (_, row) => <LogCell text={row.operationLog} onClick={onOpenLog ? () => onOpenLog(row, "manual") : undefined} /> },
    {
      title: "操作",
      key: "actions",
      width: 96,
      fixed: "right",
      render: (_, row) => <Button type="link" onClick={() => onOpenDetail(row)}>详情</Button>,
    },
  ];
}

function DailySalesTable({
  tableTotals,
  sort = null,
  onSortChange,
  rows,
  total = rows.length,
  loading = false,
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
  onOpenLog,
}: DailySalesTableProps) {
  const compactIdentityColumnWidths: Record<string, number> = {
    mskuProductId: 188,
    skuProductName: 188,
  };
  const columnMap = new Map(createColumns(onCopy, onOpenDetail, currency, onOpenLog).map((column) => [String(column.key), column]));
  const columns = appliedColumnKeys.flatMap((key) => {
    const column = columnMap.get(key);
    if (!column) return [];
    const configuredTitle = dailySalesColumnFields.find((field) => field.key === key)?.title ?? key;
    const title = columnTitle(key, configuredTitle, currency);
    const width = compactIdentityColumnWidths[key] ?? columnWidths[key] ?? (Number(column.width) || 96);
    const minWidth = Math.max(key === "image" ? 72 : 88, title.length * 14 + 28);
    const sortField = dailySalesSortFields[key];
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
        className: "report-table-resizable-header-cell daily-sales__resizable-header-cell",
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
    <ReportTableShell className="daily-sales__table" label="每日销售数据表">
      <ProTable<DailySalesRow>
        columns={columns}
        dataSource={rows}
        loading={loading}
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
            <Table.Summary.Row className="daily-sales__total-row" data-testid="daily-sales-total-row">
              <Table.Summary.Cell index={0} />
              {columns.map((column, index) => {
                const key = String(column.key);
                return (
                  <Table.Summary.Cell
                    key={key}
                    index={index + 1}
                    align="left"
                    className={`daily-sales__total-cell daily-sales__total-cell--${key}`}
                  >
                    <TotalCell
                      columnKey={key}
                      currency={currency}
                      tableTotals={tableTotals}
                    />
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
          emptyText: <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无匹配销售数据" />,
        }}
      />
    </ReportTableShell>
  );
}

export default DailySalesTable;
