/** Product-ID order-profit report table with the daily-sales interaction model. */
import { BarChartOutlined } from "@ant-design/icons";
import { ProTable, type ProColumns } from "@ant-design/pro-components";
import { Button, Empty, Table } from "antd";
import type { Key } from "react";
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

const sum = (rows: OrderProfitRow[], key: keyof OrderProfitRow) => rows
  .reduce((total, row) => total + Number(row[key] ?? 0), 0);
const sumNullable = (rows: OrderProfitRow[], key: keyof OrderProfitRow) => (
  rows.some((row) => row[key] == null) ? null : sum(rows, key)
);

const totalMoneyKeys = new Set([
  "salesAmount",
  "sampleAmount",
  "refundAmount",
  "adSpend",
  "wfsDeliveryFee",
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
  rows,
}: {
  columnKey: string;
  currency: OrderProfitCurrency;
  rows: OrderProfitRow[];
}) {
  if (columnKey === "image") return <span className="report-table-summary-label">总计</span>;
  if (columnKey === "orderProfit") {
    const rate = currency === "CNY" ? MOCK_USD_TO_CNY_RATE : 1;
    const total = sumNullable(rows, "orderProfit");
    return (
      <MoneyCell
        value={total == null ? null : total * rate}
        currency={currency === "CNY" ? "¥" : "$"}
        tone="profit"
      />
    );
  }
  if (totalMoneyKeys.has(columnKey)) {
    const rate = currency === "CNY" ? MOCK_USD_TO_CNY_RATE : 1;
    const total = sumNullable(rows, columnKey as keyof OrderProfitRow);
    return <MoneyCell value={total == null ? null : total * rate} currency={currency === "CNY" ? "¥" : "$"} />;
  }
  if (totalIntegerKeys.has(columnKey)) {
    return <span className="report-table-metric">{sum(rows, columnKey as keyof OrderProfitRow).toLocaleString("zh-CN")}</span>;
  }
  const salesAmount = sum(rows, "salesAmount");
  const orderCount = sum(rows, "orderCount");
  const adSpend = sum(rows, "adSpend");
  const orderProfit = sumNullable(rows, "orderProfit");
  if (columnKey === "averageProfitPerOrder") {
    const rate = currency === "CNY" ? MOCK_USD_TO_CNY_RATE : 1;
    return orderCount && orderProfit != null
      ? <MoneyCell value={orderProfit / orderCount * rate} currency={currency === "CNY" ? "¥" : "$"} tone="profit" />
      : <MoneyCell value={null} currency={currency === "CNY" ? "¥" : "$"} tone="profit" />;
  }
  if (columnKey === "returnRate30Days") {
    const refundQuantity = sum(rows, "refundQuantity");
    return salesAmount && sum(rows, "salesVolume") > 0
      ? (
          <PercentCell
            value={refundQuantity / sum(rows, "salesVolume") * 100}
          />
        )
      : <PercentCell value={null} />;
  }

  if (columnKey === "adRatio") {
    return salesAmount
      ? <PercentCell value={adSpend / salesAmount * 100} />
      : null;
  }
  if (columnKey === "profitMargin") {
    return salesAmount && orderProfit != null
      ? <PercentCell value={orderProfit / salesAmount * 100} />
      : <PercentCell value={null} />;
  }
  if (columnKey === "roi") {
    const purchaseCost = sumNullable(rows, "purchaseCost");
    const firstLegCost = sumNullable(rows, "firstLegCost");
    const denominator = purchaseCost != null && firstLegCost != null
      ? purchaseCost + firstLegCost
      : null;

    return orderProfit != null && denominator != null && denominator > 0
      ? (
          <span className="report-table-metric">
            {(orderProfit / denominator).toFixed(2)}
          </span>
        )
      : <span className="report-table-metric">-</span>;
  }
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
      title: "分析",
      key: "analysis",
      width: 72,
      fixed: "left",
      render: (_, row) => (
        <Button
          type="text"
          aria-label={`查看订单利润详情：${row.productId}`}
          icon={<BarChartOutlined aria-hidden="true" />}
          onClick={() => onOpenDetail(row)}
        />
      ),
    },
    {
      title: "商品ID/品名",
      key: "productIdName",
      width: 240,
      fixed: "left",
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
      width: 190,
      render: (_, row) => (
        <SkuMskuIdentityCell
          sku={row.sku}
          msku={row.msku}
          onCopy={onCopy}
        />
      ),
    },
    { title: "平台", dataIndex: "platform", key: "platform", width: 96 },
    { title: "店铺", dataIndex: "store", key: "store", width: 120 },
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

    { title: "送样量", dataIndex: "sampleQuantity", key: "sampleQuantity", width: 88 },
    { title: "送样金额", key: "sampleAmount", width: 112, render: money("sampleAmount", currency) },

    { title: "退货量", dataIndex: "refundQuantity", key: "refundQuantity", width: 88 },
    { title: "退款损失", key: "refundAmount", width: 104, render: money("refundAmount", currency) },
    { title: "退货率30天", key: "returnRate30Days", width: 120, render: percent("returnRate30Days") },

    { title: "广告费", key: "adSpend", width: 104, render: money("adSpend", currency) },
    { title: "广告占比", key: "adRatio", width: 104, render: percent("adRatio") },

    { title: "WFS总配送费", key: "wfsDeliveryFee", width: 132, render: money("wfsDeliveryFee", currency) },
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

    const width = columnWidths[key] ?? (Number(column.width) || 96);
    const minWidth = Math.max(key === "image" || key === "analysis" ? 72 : 88, title.length * 14 + 28);
    return [{
      ...column,
      align: "left" as const,
      width,
      onHeaderCell: () => ({ className: "report-table-resizable-header-cell order-profit__resizable-header-cell" }),
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
          emptyText: <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无匹配订单利润数据" />,
        }}
      />
    </ReportTableShell>
  );
}

export default OrderProfitTable;
