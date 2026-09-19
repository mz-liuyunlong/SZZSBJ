/** Dense daily-sales report table. */
import { BarChartOutlined } from "@ant-design/icons";
import { ProTable, type ProColumns } from "@ant-design/pro-components";
import { Button, Empty, Space, Table, Tooltip } from "antd";
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
  PercentCell,
  StatusTagCell,
  TrendPreviewCell,
} from "@/components/report-table/cells";
import {
  convertCnyUnitTotalOrUsdSourceValue,
  convertUsdSourceValue,
  dynamicCurrencyTitle,
  renderCnySourceMoney,
  renderCnyUnitTotalOrUsdSourceMoney,
  renderUsdSourceMoney,
} from "@/components/report-table/moneyRenderers";
import {
  MOCK_USD_TO_CNY_RATE,
  dailySalesColumnFields,
  type DailySalesCostStatus,
  type DailySalesCurrency,
  type DailySalesRow,
} from "@/pages/sales/dailySalesTypes";

interface DailySalesTableProps {
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
}

const statusColors: Record<DailySalesCostStatus, string> = {
  已完成: "success",
  待补齐: "warning",
  异常: "error",
  部分缺失: "processing",
};

const dailySalesFxRate = (row: DailySalesRow) => row.exchangeRate ?? MOCK_USD_TO_CNY_RATE;

function LogCell({ text }: { text: string }) {
  return (
    <Tooltip title={text}>
      <span className="daily-sales__log-cell">{text}</span>
    </Tooltip>
  );
}

const percent = (key: keyof DailySalesRow) =>
  (_: unknown, row: DailySalesRow) => {
    const value = row[key];
    return <PercentCell value={typeof value === "number" ? value : null} />;
  };

const sum = (rows: DailySalesRow[], key: keyof DailySalesRow) => rows
  .reduce((total, row) => total + Number(row[key] ?? 0), 0);
const sumNullable = (rows: DailySalesRow[], key: keyof DailySalesRow) => (
  rows.some((row) => row[key] == null) ? null : sum(rows, key)
);
const sumUsdSourceMoney = (rows: DailySalesRow[], key: keyof DailySalesRow, currency: DailySalesCurrency) => {
  if (rows.some((row) => row[key] == null)) return null;
  return rows.reduce((total, row) => {
    const value = row[key];
    const numeric = typeof value === "number" ? value : 0;
    return total + (convertUsdSourceValue(numeric, currency, dailySalesFxRate(row)) ?? 0);
  }, 0);
};

const numericRowValue = (row: DailySalesRow, key: keyof DailySalesRow) => {
  const value = row[key];
  return typeof value === "number" ? value : null;
};

const sumCnyUnitTotalOrUsdSourceMoney = (
  rows: DailySalesRow[],
  usdTotalKey: keyof DailySalesRow,
  cnyUnitKey: keyof DailySalesRow,
  quantityKey: keyof DailySalesRow,
  currency: DailySalesCurrency,
) => {
  let hasMissingValue = false;
  const total = rows.reduce((currentTotal, row) => {
    const value = convertCnyUnitTotalOrUsdSourceValue(
      numericRowValue(row, usdTotalKey),
      numericRowValue(row, cnyUnitKey),
      numericRowValue(row, quantityKey),
      currency,
      dailySalesFxRate(row),
    );

    if (value == null) {
      hasMissingValue = true;
      return currentTotal;
    }

    return currentTotal + value;
  }, 0);

  return hasMissingValue ? null : total;
};


const totalMoneyKeys = new Set([
  "salesAmount",
  "sampleExcludedAmount",
  "refundAmount",
  "adSpend",
  "wfsDeliveryFee",
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
  "wfsAvailableInventory",
]);
function TotalCell({
  columnKey,
  currency,
  rows,
}: {
  columnKey: string;
  currency: DailySalesCurrency;
  rows: DailySalesRow[];
}) {
  if (columnKey === "image") return <span className="report-table-summary-label">总计</span>;
  if (columnKey === "purchaseCost") {
    return (
      <MoneyCell
        value={sumCnyUnitTotalOrUsdSourceMoney(
          rows,
          "purchaseCost",
          "purchaseUnitPriceCny",
          "costQuantity",
          currency,
        )}
        currency={currency === "CNY" ? "¥" : "$"}
      />
    );
  }
  if (columnKey === "firstLegCost") {
    return (
      <MoneyCell
        value={sumCnyUnitTotalOrUsdSourceMoney(
          rows,
          "firstLegCost",
          "firstLegUnitPriceCny",
          "costQuantity",
          currency,
        )}
        currency={currency === "CNY" ? "¥" : "$"}
      />
    );
  }
  if (totalMoneyKeys.has(columnKey)) {
    const total = sumUsdSourceMoney(rows, columnKey as keyof DailySalesRow, currency);
    return <MoneyCell value={total} currency={currency === "CNY" ? "¥" : "$"} />;
  }
  if (totalIntegerKeys.has(columnKey)) {
    return <span className="report-table-metric">{sum(rows, columnKey as keyof DailySalesRow).toLocaleString("zh-CN")}</span>;
  }
  const salesVolume = sum(rows, "salesVolume");
  const salesAmount = sum(rows, "salesAmount");
  const adSpend = sum(rows, "adSpend");
  if (columnKey === "returnRate30Days") {
    return salesVolume ? <PercentCell value={sum(rows, "returnCount") / salesVolume * 100} /> : null;
  }
  if (columnKey === "adRatio") {
    return salesAmount ? <PercentCell value={adSpend / salesAmount * 100} /> : null;
  }
  if (columnKey === "profitMargin") {
    const orderProfit = sumNullable(rows, "orderProfit");
    return salesAmount && orderProfit != null
      ? <PercentCell value={orderProfit / salesAmount * 100} />
      : <PercentCell value={null} />;
  }
  if (columnKey === "roi") {
    const orderProfit = sumNullable(rows, "orderProfit");
    const purchaseCost = sumNullable(rows, "purchaseCost");
    const firstLegCost = sumNullable(rows, "firstLegCost");
    const denominator = purchaseCost != null && firstLegCost != null
      ? purchaseCost + firstLegCost
      : null;
    return orderProfit != null && denominator != null && denominator > 0
      ? <PercentCell value={orderProfit / denominator * 100} />
      : <PercentCell value={null} />;
  }
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
): ProColumns<DailySalesRow>[] {
  return [
    { title: "图片", key: "image", width: 72, fixed: "left", render: () => <ImageCell label="每日销售商品图片占位" /> },
    {
      title: "分析",
      key: "analysis",
      width: 72,
      fixed: "left",
      render: (_, row) => (
        <Button
          type="text"
          aria-label={`查看销售详情：${row.sku}`}
          icon={<BarChartOutlined aria-hidden="true" />}
          onClick={() => onOpenDetail(row)}
        />
      ),
    },
    { title: "日期", dataIndex: "date", key: "date", width: 112, fixed: "left" },
    { title: "店铺", dataIndex: "store", key: "store", width: 120 },
    { title: "负责人", dataIndex: "owner", key: "owner", width: 96 },
    {
      title: "前7天销量趋势",
      key: "sevenDaySales",
      width: 140,
      render: (_, row) => <TrendPreviewCell values={row.sevenDaySales} dates={row.sevenDayDates} />,
    },
    {
      title: "MSKU/商品ID",
      key: "mskuProductId",
      width: 190,
      render: (_, row) => (
        <Space direction="vertical" size={0} className="daily-sales__identifier-stack">
          <CopyableTextCell text={row.msku} label="MSKU" onCopy={onCopy} />
          <CopyableTextCell text={row.productId} label="商品ID" onCopy={onCopy} />
        </Space>
      ),
    },
    {
      title: "SKU/品名",
      key: "skuProductName",
      width: 230,
      render: (_, row) => (
        <Space direction="vertical" size={0} className="daily-sales__identifier-stack">
          <CopyableTextCell text={row.sku} label="SKU" onCopy={onCopy} />
          <CopyableTextCell text={row.productName} label="品名" onCopy={onCopy} />
        </Space>
      ),
    },
    { title: "平台", dataIndex: "platform", key: "platform", width: 96 },
    { title: "销量", dataIndex: "salesVolume", key: "salesVolume", width: 88 },
    { title: "订单量", dataIndex: "orderCount", key: "orderCount", width: 88 },
    { title: "销售额", key: "salesAmount", width: 112, render: renderUsdSourceMoney<DailySalesRow>("salesAmount", currency, dailySalesFxRate) },
    { title: "送样量", dataIndex: "sampleQuantity", key: "sampleQuantity", width: 88 },
    { title: "送样金额", key: "sampleExcludedAmount", width: 112, render: renderUsdSourceMoney<DailySalesRow>("sampleExcludedAmount", currency, dailySalesFxRate) },
    { title: "退货量", dataIndex: "returnCount", key: "returnCount", width: 88 },
    { title: "退款额", key: "refundAmount", width: 104, render: renderUsdSourceMoney<DailySalesRow>("refundAmount", currency, dailySalesFxRate) },
    { title: "退货率30天", key: "returnRate30Days", width: 120, render: percent("returnRate30Days") },
    { title: "广告费", key: "adSpend", width: 104, render: renderUsdSourceMoney<DailySalesRow>("adSpend", currency, dailySalesFxRate) },
    { title: "广告占比", key: "adRatio", width: 104, render: percent("adRatio") },
    { title: "WFS总配送费", key: "wfsDeliveryFee", width: 132, render: renderUsdSourceMoney<DailySalesRow>("wfsDeliveryFee", currency, dailySalesFxRate) },
    { title: "WFS配送单价", key: "wfsDeliveryUnitPrice", width: 148, render: renderUsdSourceMoney<DailySalesRow>("wfsDeliveryUnitPrice", currency, dailySalesFxRate) },
    { title: "佣金", key: "commission", width: 104, render: renderUsdSourceMoney<DailySalesRow>("commission", currency, dailySalesFxRate) },
    { title: "采购总成本", key: "purchaseCost", width: 128, render: renderCnyUnitTotalOrUsdSourceMoney<DailySalesRow>("purchaseCost", "purchaseUnitPriceCny", "costQuantity", currency, dailySalesFxRate) },
    { title: "采购单价", key: "purchaseUnitPriceCny", width: 128, render: renderCnySourceMoney<DailySalesRow>("purchaseUnitPriceCny", currency, dailySalesFxRate) },
    { title: "头程总成本", key: "firstLegCost", width: 128, render: renderCnyUnitTotalOrUsdSourceMoney<DailySalesRow>("firstLegCost", "firstLegUnitPriceCny", "costQuantity", currency, dailySalesFxRate) },
    { title: "头程单价", key: "firstLegUnitPriceCny", width: 128, render: renderCnySourceMoney<DailySalesRow>("firstLegUnitPriceCny", currency, dailySalesFxRate) },
    { title: "总仓储费", key: "storageFee", width: 112, render: renderUsdSourceMoney<DailySalesRow>("storageFee", currency, dailySalesFxRate) },
    { title: "仓储单价", key: "storageUnitPrice", width: 128, render: renderUsdSourceMoney<DailySalesRow>("storageUnitPrice", currency, dailySalesFxRate) },
    { title: "WFS可售库存", dataIndex: "wfsAvailableInventory", key: "wfsAvailableInventory", width: 128 },
    { title: "订单利润", key: "orderProfit", width: 112, render: renderUsdSourceMoney<DailySalesRow>("orderProfit", currency, dailySalesFxRate) },
    { title: "利润率", key: "profitMargin", width: 96, render: percent("profitMargin") },
    { title: "ROI", key: "roi", width: 88, render: percent("roi") },
    { title: "成本状态", key: "costStatus", width: 112, render: (_, row) => <StatusTagCell label={row.costStatus} color={statusColors[row.costStatus]} /> },
    { title: "系统运营日志", key: "systemOperationLog", width: 180, render: (_, row) => <LogCell text={row.systemOperationLog} /> },
    { title: "运营日志", key: "operationLog", width: 180, render: (_, row) => <LogCell text={row.operationLog} /> },
  ];
}

function DailySalesTable({
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
}: DailySalesTableProps) {
  const columnMap = new Map(createColumns(onCopy, onOpenDetail, currency).map((column) => [String(column.key), column]));
  const columns = appliedColumnKeys.flatMap((key) => {
    const column = columnMap.get(key);
    if (!column) return [];
    const configuredTitle = dailySalesColumnFields.find((field) => field.key === key)?.title ?? key;
    const title = columnTitle(key, configuredTitle, currency);
    const width = columnWidths[key] ?? (Number(column.width) || 96);
    const minWidth = Math.max(key === "image" || key === "analysis" ? 72 : 88, title.length * 14 + 28);
    return [{
      ...column,
      align: "left" as const,
      width,
      onHeaderCell: () => ({ className: "report-table-resizable-header-cell daily-sales__resizable-header-cell" }),
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
                    <TotalCell columnKey={key} currency={currency} rows={rows} />
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
