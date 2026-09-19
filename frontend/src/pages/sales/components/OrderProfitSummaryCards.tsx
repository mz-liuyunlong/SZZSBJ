/** Product-ID profit metrics from server summary or currently filtered rows. */
import {
  DollarCircleOutlined,
  LineChartOutlined,
  NotificationOutlined,
  PercentageOutlined,
  PieChartOutlined,
  RollbackOutlined,
  ShoppingOutlined,
} from "@ant-design/icons";
import { useMemo } from "react";
import ReportSummaryCards, {
  type ReportSummaryMetric,
} from "@/components/report-table/ReportSummaryCards";
import type { OrderProfitServerSummary } from "@/pages/sales/orderProfitApi";
import {
  MOCK_USD_TO_CNY_RATE,
  type OrderProfitCurrency,
  type OrderProfitRow,
} from "@/pages/sales/orderProfitTypes";

interface OrderProfitSummaryCardsProps {
  rows: OrderProfitRow[];
  currency: OrderProfitCurrency;
  serverSummary?: OrderProfitServerSummary | null;
}

const formatAmount = (value: number, currency: OrderProfitCurrency) => {
  const symbol = currency === "CNY" ? "¥" : "$";
  return `${symbol}${value.toLocaleString("en-US", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })}`;
};

const currencyRate = (
  sourceCurrency: OrderProfitCurrency,
  targetCurrency: OrderProfitCurrency,
) => {
  if (sourceCurrency === targetCurrency) return 1;
  return sourceCurrency === "USD" ? MOCK_USD_TO_CNY_RATE : 1 / MOCK_USD_TO_CNY_RATE;
};

function OrderProfitSummaryCards({
  rows,
  currency,
  serverSummary,
}: OrderProfitSummaryCardsProps) {
  const totals = useMemo(() => {
    if (serverSummary) {
      return {
        salesVolume: serverSummary.salesQuantity,
        salesAmount: serverSummary.salesAmount
          * currencyRate(serverSummary.salesCurrency, currency),
        refundQuantity: serverSummary.refundQuantity,
        refundAmount: serverSummary.refundAmount
          * currencyRate(serverSummary.refundCurrency, currency),
        orderProfit: serverSummary.orderProfitAmount
          * currencyRate(serverSummary.orderProfitCurrency, currency),
        adSpend: serverSummary.adSpendAmount
          * currencyRate(serverSummary.adSpendCurrency, currency),
      };
    }

    const rate = currency === "CNY" ? MOCK_USD_TO_CNY_RATE : 1;
    const incompleteProfit = rows.some((row) => row.orderProfit == null);

    return {
      salesVolume: rows.reduce((total, row) => total + row.salesVolume, 0),
      salesAmount: rows.reduce((total, row) => total + row.salesAmount, 0) * rate,
      refundQuantity: rows.reduce((total, row) => total + row.refundQuantity, 0),
      refundAmount: rows.reduce((total, row) => total + row.refundAmount, 0) * rate,
      orderProfit: incompleteProfit
        ? null
        : rows.reduce((total, row) => total + (row.orderProfit ?? 0), 0) * rate,
      adSpend: rows.reduce((total, row) => total + row.adSpend, 0) * rate,
    };
  }, [currency, rows, serverSummary]);

  const metrics: ReportSummaryMetric[] = [
    {
      title: "销量",
      value: totals.salesVolume,
      formatter: (value) => Math.round(value ?? 0).toLocaleString("zh-CN"),
      subtitle: "当前筛选销量",
      icon: <ShoppingOutlined />,
      tone: "blue",
      trend: "12.5%",
      trendDirection: "up",
    },
    {
      title: "销售额",
      value: totals.salesAmount,
      formatter: (value) => value == null ? "—" : formatAmount(value, currency),
      subtitle: "销售金额合计",
      icon: <DollarCircleOutlined />,
      tone: "green",
      trend: "8.2%",
      trendDirection: "up",
    },
    {
      title: "订单利润",
      value: totals.orderProfit,
      formatter: (value) => value == null ? "—" : formatAmount(value, currency),
      subtitle: "SKU 订单利润",
      icon: <LineChartOutlined />,
      tone: "orange",
      trend: "15.3%",
      trendDirection: "up",
    },
    {
      title: "利润率",
      value: totals.salesAmount && totals.orderProfit != null
        ? totals.orderProfit / totals.salesAmount * 100
        : null,
      formatter: (value) => value == null ? "—" : `${value.toFixed(2)}%`,
      subtitle: "利润 / 销售额",
      icon: <PieChartOutlined />,
      tone: "purple",
      trend: "2.1%",
      trendDirection: "up",
    },
    {
      title: "广告费",
      value: totals.adSpend,
      formatter: (value) => value == null ? "—" : formatAmount(value, currency),
      subtitle: "广告花费合计",
      icon: <NotificationOutlined />,
      tone: "red",
      trend: "6.8%",
      trendDirection: "cost-up",
    },
    {
      title: "广告占比",
      value: totals.salesAmount ? totals.adSpend / totals.salesAmount * 100 : null,
      formatter: (value) => value == null ? "—" : `${value.toFixed(2)}%`,
      subtitle: "广告费 / 销售额",
      icon: <PercentageOutlined />,
      tone: "cyan",
      trend: "1.2%",
      trendDirection: "down",
    },
    {
      title: "退款数量",
      value: totals.refundQuantity,
      formatter: (value) => value == null ? "—" : Math.round(value).toLocaleString("zh-CN"),
      subtitle: "按退款发生日统计",
      icon: <RollbackOutlined />,
      tone: "red",
      trend: null,
      trendDirection: null,
    },
    {
      title: "退款金额",
      value: totals.refundAmount,
      formatter: (value) => value == null ? "—" : formatAmount(value, currency),
      subtitle: "按退款发生日统计",
      icon: <DollarCircleOutlined />,
      tone: "orange",
      trend: null,
      trendDirection: null,
    },
  ];

  return (
    <ReportSummaryCards
      className="order-profit__summary"
      ariaLabel="订单利润统计"
      metrics={metrics}
    />
  );
}

export default OrderProfitSummaryCards;
