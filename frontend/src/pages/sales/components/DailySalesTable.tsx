/** Dense no-API report table with the approved 35-column order. */
import { BarChartOutlined } from "@ant-design/icons";
import { ProTable, type ProColumns } from "@ant-design/pro-components";
import { Button, Empty, Space, Table, Tooltip, Typography } from "antd";
import type { Key } from "react";
import ReportTableShell from "../../../components/report-table/ReportTableShell";
import ResizableColumnTitle from "../../../components/report-table/ResizableColumnTitle";
import {
  CopyableTextCell,
  ImageCell,
  MoneyCell,
  PercentCell,
  StatusTagCell,
  TrendPreviewCell,
} from "../../../components/report-table/cells";
import {
  MOCK_USD_TO_CNY_RATE,
  dailySalesColumnFields,
  type DailySalesCostStatus,
  type DailySalesCurrency,
  type DailySalesRow,
} from "../dailySalesTypes";

interface DailySalesTableProps {
  rows: DailySalesRow[];
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
  onCopy: (text: string) => void;
  onOpenDetail: (row: DailySalesRow) => void;
}

const statusColors: Record<DailySalesCostStatus, string> = {
  已完成: "success",
  待补齐: "warning",
  异常: "error",
  部分缺失: "processing",
};

const compareText = (left: string, right: string) => left.localeCompare(right, "zh-CN");
const numberSorter = (key: keyof DailySalesRow) => (left: DailySalesRow, right: DailySalesRow) =>
  Number(left[key]) - Number(right[key]);

function LogCell({ text }: { text: string }) {
  return (
    <Tooltip title={text}>
      <span className="daily-sales__log-cell">{text}</span>
    </Tooltip>
  );
}

const money = (key: keyof DailySalesRow, currency: DailySalesCurrency) => {
  const rate = currency === "CNY" ? MOCK_USD_TO_CNY_RATE : 1;
  const symbol = currency === "CNY" ? "¥" : "$";
  return (_: unknown, row: DailySalesRow) => (
    <MoneyCell value={Number(row[key]) * rate} currency={symbol} />
  );
};
const percent = (key: keyof DailySalesRow) =>
  (_: unknown, row: DailySalesRow) => <PercentCell value={Number(row[key])} />;

const sum = (rows: DailySalesRow[], key: keyof DailySalesRow) => rows
  .reduce((total, row) => total + Number(row[key]), 0);

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
  "legacyGrossProfit",
  "orderProfit",
]);
const totalIntegerKeys = new Set([
  "salesVolume",
  "orderCount",
  "returnCount",
  "wfsAvailableInventory",
]);
const totalNumericKeys = new Set([
  ...totalMoneyKeys,
  ...totalIntegerKeys,
  "returnRate30Days",
  "adRatio",
  "profitMargin",
  "roi",
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
  if (totalMoneyKeys.has(columnKey)) {
    const rate = currency === "CNY" ? MOCK_USD_TO_CNY_RATE : 1;
    return <MoneyCell value={sum(rows, columnKey as keyof DailySalesRow) * rate} currency={currency === "CNY" ? "¥" : "$"} />;
  }
  if (totalIntegerKeys.has(columnKey)) {
    return <span className="report-table-metric">{sum(rows, columnKey as keyof DailySalesRow).toLocaleString("zh-CN")}</span>;
  }
  const salesVolume = sum(rows, "salesVolume");
  const salesAmount = sum(rows, "salesAmount");
  const adSpend = sum(rows, "adSpend");
  if (columnKey === "returnRate30Days") {
    return salesVolume ? <PercentCell value={sum(rows, "returnCount") / salesVolume * 100} /> : <>-</>;
  }
  if (columnKey === "adRatio") {
    return salesAmount ? <PercentCell value={adSpend / salesAmount * 100} /> : <>-</>;
  }
  if (columnKey === "profitMargin") {
    return salesAmount ? <PercentCell value={sum(rows, "orderProfit") / salesAmount * 100} /> : <>-</>;
  }
  if (columnKey === "roi") {
    return adSpend ? <span className="report-table-metric">{(salesAmount / adSpend).toFixed(2)}</span> : <>-</>;
  }
  return <>-</>;
}

const currencyColumnTitles: Partial<Record<string, string>> = {
  wfsDeliveryUnitPrice: "WFS配送单价",
  purchaseUnitPriceCny: "采购单价",
  firstLegUnitPriceCny: "头程单价",
  storageUnitPrice: "仓储单价",
};

const columnTitle = (key: string, fallback: string, currency: DailySalesCurrency) => {
  const base = currencyColumnTitles[key];
  return base ? `${base}(${currency === "CNY" ? "¥" : "$"})` : fallback;
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
    { title: "日期", dataIndex: "date", key: "date", width: 112, fixed: "left", sorter: (a, b) => compareText(a.date, b.date) },
    { title: "店铺", dataIndex: "store", key: "store", width: 120, sorter: (a, b) => compareText(a.store, b.store) },
    { title: "负责人", dataIndex: "owner", key: "owner", width: 96, sorter: (a, b) => compareText(a.owner, b.owner) },
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
    { title: "平台", dataIndex: "platform", key: "platform", width: 96, sorter: (a, b) => compareText(a.platform, b.platform) },
    { title: "销量", dataIndex: "salesVolume", key: "salesVolume", width: 88, sorter: numberSorter("salesVolume") },
    { title: "订单量", dataIndex: "orderCount", key: "orderCount", width: 88, sorter: numberSorter("orderCount") },
    { title: "销售额", key: "salesAmount", width: 112, sorter: numberSorter("salesAmount"), render: money("salesAmount", currency) },
    { title: "剔除送样额", key: "sampleExcludedAmount", width: 128, sorter: numberSorter("sampleExcludedAmount"), render: money("sampleExcludedAmount", currency) },
    { title: "退货量", dataIndex: "returnCount", key: "returnCount", width: 88, sorter: numberSorter("returnCount") },
    { title: "退款额", key: "refundAmount", width: 104, sorter: numberSorter("refundAmount"), render: money("refundAmount", currency) },
    { title: "退货率30天", key: "returnRate30Days", width: 120, sorter: numberSorter("returnRate30Days"), render: percent("returnRate30Days") },
    { title: "广告费", key: "adSpend", width: 104, sorter: numberSorter("adSpend"), render: money("adSpend", currency) },
    { title: "广告占比", key: "adRatio", width: 104, sorter: numberSorter("adRatio"), render: percent("adRatio") },
    { title: "WFS配送费", key: "wfsDeliveryFee", width: 120, sorter: numberSorter("wfsDeliveryFee"), render: money("wfsDeliveryFee", currency) },
    { title: "WFS配送单价", key: "wfsDeliveryUnitPrice", width: 148, sorter: numberSorter("wfsDeliveryUnitPrice"), render: money("wfsDeliveryUnitPrice", currency) },
    { title: "佣金", key: "commission", width: 104, sorter: numberSorter("commission"), render: money("commission", currency) },
    { title: "采购成本", key: "purchaseCost", width: 112, sorter: numberSorter("purchaseCost"), render: money("purchaseCost", currency) },
    { title: "采购单价", key: "purchaseUnitPriceCny", width: 128, sorter: numberSorter("purchaseUnitPriceCny"), render: money("purchaseUnitPriceCny", currency) },
    { title: "头程成本", key: "firstLegCost", width: 112, sorter: numberSorter("firstLegCost"), render: money("firstLegCost", currency) },
    { title: "头程单价", key: "firstLegUnitPriceCny", width: 128, sorter: numberSorter("firstLegUnitPriceCny"), render: money("firstLegUnitPriceCny", currency) },
    { title: "仓储费", key: "storageFee", width: 104, sorter: numberSorter("storageFee"), render: money("storageFee", currency) },
    { title: "仓储单价", key: "storageUnitPrice", width: 128, sorter: numberSorter("storageUnitPrice"), render: money("storageUnitPrice", currency) },
    { title: "WFS可售库存", dataIndex: "wfsAvailableInventory", key: "wfsAvailableInventory", width: 128, sorter: numberSorter("wfsAvailableInventory") },
    { title: "毛利润(旧)", key: "legacyGrossProfit", width: 120, sorter: numberSorter("legacyGrossProfit"), render: money("legacyGrossProfit", currency) },
    { title: "订单利润", key: "orderProfit", width: 112, sorter: numberSorter("orderProfit"), render: money("orderProfit", currency) },
    { title: "利润率", key: "profitMargin", width: 96, sorter: numberSorter("profitMargin"), render: percent("profitMargin") },
    { title: "ROI", key: "roi", width: 88, sorter: numberSorter("roi"), render: percent("roi") },
    { title: "成本状态", key: "costStatus", width: 112, render: (_, row) => <StatusTagCell label={row.costStatus} color={statusColors[row.costStatus]} /> },
    { title: "系统运营日志", key: "systemOperationLog", width: 180, render: (_, row) => <LogCell text={row.systemOperationLog} /> },
    { title: "运营日志", key: "operationLog", width: 180, render: (_, row) => <LogCell text={row.operationLog} /> },
  ];
}

function DailySalesTable({
  rows,
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
            <Table.Summary.Row className="daily-sales__total-row" data-testid="daily-sales-total-row">
              <Table.Summary.Cell index={0} />
              {columns.map((column, index) => {
                const key = String(column.key);
                return (
                  <Table.Summary.Cell
                    key={key}
                    index={index + 1}
                    align={totalNumericKeys.has(key) ? "right" : "left"}
                    className={`daily-sales__total-cell daily-sales__total-cell--${key}`}
                  >
                    <TotalCell columnKey={key} currency={currency} rows={rows} />
                  </Table.Summary.Cell>
                );
              })}
            </Table.Summary.Row>
          </Table.Summary>
        )}
        footer={() => selectedRowKeys.length > 0
          ? <Typography.Text strong>已选择 {selectedRowKeys.length} 项</Typography.Text>
          : null}
        pagination={{
          current: currentPage,
          pageSize,
          total: rows.length,
          showSizeChanger: true,
          showQuickJumper: true,
          pageSizeOptions: ["10", "20", "50", "100"],
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
