/** Daily-sales operating metrics plus refund-event totals from the selected date range. */
import {
  ArrowDownOutlined,
  ArrowUpOutlined,
  DollarCircleOutlined,
  LineChartOutlined,
  NotificationOutlined,
  PercentageOutlined,
  PieChartOutlined,
  RollbackOutlined,
  ShoppingOutlined,
} from "@ant-design/icons";
import { Card } from "antd";
import { useMemo } from "react";
import {
  MOCK_USD_TO_CNY_RATE,
  type DailySalesCurrency,
  type DailySalesRefundSummary,
  type DailySalesRow,
} from "@/pages/sales/dailySalesTypes";

interface DailySalesSummaryCardsProps {
  rows: DailySalesRow[];
  currency: DailySalesCurrency;
  refundSummary: DailySalesRefundSummary | null;
}

const formatAmount = (value: number, currency: DailySalesCurrency) => {
  const symbol = currency === "CNY" ? "¥" : "$";
  return `${symbol}${value.toLocaleString("en-US", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })}`;
};

interface AnimatedMetricValueProps {
  value: number | null;
  formatter: (value: number | null) => string;
}

function AnimatedMetricValue({ value, formatter }: AnimatedMetricValueProps) {
  return <strong className="daily-sales__summary-value">{formatter(value)}</strong>;
}

function DailySalesSummaryCards({ rows, currency, refundSummary }: DailySalesSummaryCardsProps) {
  const rate = currency === "CNY" ? MOCK_USD_TO_CNY_RATE : 1;
  const refundRate = refundSummary == null || refundSummary.currency === currency
    ? 1
    : refundSummary.currency === "USD"
      ? MOCK_USD_TO_CNY_RATE
      : 1 / MOCK_USD_TO_CNY_RATE;
  const totals = useMemo(() => {
    const incompleteProfit = rows.some((row) => row.orderProfit == null);
    return {
      salesVolume: rows.reduce((total, row) => total + row.salesVolume, 0),
      salesAmount: rows.reduce((total, row) => total + row.salesAmount, 0),
      orderProfit: incompleteProfit
        ? null
        : rows.reduce((total, row) => total + (row.orderProfit ?? 0), 0),
      adSpend: rows.reduce((total, row) => total + row.adSpend, 0),
    };
  }, [rows]);

  const metrics = [
    {
      title: "销量",
      value: totals.salesVolume,
      formatter: (value: number | null) => Math.round(value ?? 0).toLocaleString("zh-CN"),
      subtitle: "当前筛选销量",
      icon: <ShoppingOutlined />,
      tone: "blue",
      trend: "12.5%",
      trendDirection: "up",
    },
    {
      title: "销售额",
      value: totals.salesAmount * rate,
      formatter: (value: number | null) => value == null ? "—" : formatAmount(value, currency),
      subtitle: "销售金额合计",
      icon: <DollarCircleOutlined />,
      tone: "green",
      trend: "8.2%",
      trendDirection: "up",
    },
    {
      title: "订单利润",
      value: totals.orderProfit == null ? null : totals.orderProfit * rate,
      formatter: (value: number | null) => value == null ? "—" : formatAmount(value, currency),
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
      formatter: (value: number | null) => value == null ? "—" : `${value.toFixed(2)}%`,
      subtitle: "利润 / 销售额",
      icon: <PieChartOutlined />,
      tone: "purple",
      trend: "2.1%",
      trendDirection: "up",
    },
    {
      title: "广告费",
      value: totals.adSpend * rate,
      formatter: (value: number | null) => value == null ? "—" : formatAmount(value, currency),
      subtitle: "广告花费合计",
      icon: <NotificationOutlined />,
      tone: "red",
      trend: "6.8%",
      trendDirection: "cost-up",
    },
    {
      title: "广告占比",
      value: totals.salesAmount ? totals.adSpend / totals.salesAmount * 100 : null,
      formatter: (value: number | null) => value == null ? "—" : `${value.toFixed(2)}%`,
      subtitle: "广告费 / 销售额",
      icon: <PercentageOutlined />,
      tone: "cyan",
      trend: "1.2%",
      trendDirection: "down",
    },
    {
      title: "退款数量",
      value: refundSummary?.quantity ?? null,
      formatter: (value: number | null) => value == null ? "—" : Math.round(value).toLocaleString("zh-CN"),
      subtitle: "按退款发生日统计",
      icon: <RollbackOutlined />,
      tone: "red",
      trend: null,
      trendDirection: null,
    },
    {
      title: "退款金额",
      value: refundSummary == null ? null : refundSummary.amount * refundRate,
      formatter: (value: number | null) => value == null ? "—" : formatAmount(value, currency),
      subtitle: "按退款发生日统计",
      icon: <DollarCircleOutlined />,
      tone: "orange",
      trend: null,
      trendDirection: null,
    },
  ] as const;

  return (
    <section className="daily-sales__summary" aria-label="销售统计">
      {metrics.map((metric, index) => (
        <Card
          key={metric.title}
          size="small"
          className={`daily-sales__summary-card daily-sales__summary-card--${metric.tone}${metric.trendDirection ? ` daily-sales__summary-card--trend-${metric.trendDirection}` : ""}`}
          style={{ "--summary-card-index": index } as React.CSSProperties}
        >
          <span className={`daily-sales__summary-rising${metric.trendDirection ? ` daily-sales__summary-rising--${metric.trendDirection}` : ""}`} aria-hidden="true">
            <span />
            <span />
            <span />
          </span>
          <span className="daily-sales__summary-icon" aria-hidden="true">{metric.icon}</span>
          <span className="daily-sales__summary-content">
            <span className="daily-sales__summary-title">{metric.title}</span>
            <AnimatedMetricValue value={metric.value} formatter={metric.formatter} />
            <span className="daily-sales__summary-subtitle">{metric.subtitle}</span>
          </span>
          {metric.trend && metric.trendDirection && (
            <span
              className={`daily-sales__summary-comparison daily-sales__summary-comparison--${metric.trendDirection}`}
            >
              <span className="daily-sales__summary-trend">
                {metric.trendDirection === "down" ? <ArrowDownOutlined /> : <ArrowUpOutlined />}
                {metric.trend}
              </span>
            </span>
          )}
        </Card>
      ))}
    </section>
  );
}

export default DailySalesSummaryCards;
