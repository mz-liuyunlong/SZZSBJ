/** Six no-API operating metrics derived from the currently filtered acceptance rows. */
import {
  ArrowDownOutlined,
  ArrowUpOutlined,
  DollarCircleOutlined,
  LineChartOutlined,
  NotificationOutlined,
  PercentageOutlined,
  PieChartOutlined,
  ShoppingOutlined,
} from "@ant-design/icons";
import { Card } from "antd";
import {
  MOCK_USD_TO_CNY_RATE,
  type DailySalesCurrency,
  type DailySalesRow,
} from "@/pages/sales/dailySalesTypes";

interface DailySalesSummaryCardsProps {
  rows: DailySalesRow[];
  currency: DailySalesCurrency;
}

const formatAmount = (value: number, currency: DailySalesCurrency) => {
  const symbol = currency === "CNY" ? "¥" : "$";
  return `${symbol}${value.toLocaleString("en-US", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })}`;
};

function DailySalesSummaryCards({ rows, currency }: DailySalesSummaryCardsProps) {
  const rate = currency === "CNY" ? MOCK_USD_TO_CNY_RATE : 1;
  const totals = rows.reduce((result, row) => ({
    salesVolume: result.salesVolume + row.salesVolume,
    salesAmount: result.salesAmount + row.salesAmount,
    orderProfit: result.orderProfit + row.orderProfit,
    adSpend: result.adSpend + row.adSpend,
  }), { salesVolume: 0, salesAmount: 0, orderProfit: 0, adSpend: 0 });
  const metrics = [
    {
      title: "销量",
      value: totals.salesVolume.toLocaleString("zh-CN"),
      icon: <ShoppingOutlined />,
      tone: "blue",
      trend: "12.5%",
      trendDirection: "up",
    },
    {
      title: "销售额",
      value: formatAmount(totals.salesAmount * rate, currency),
      icon: <DollarCircleOutlined />,
      tone: "green",
      trend: "8.2%",
      trendDirection: "up",
    },
    {
      title: "订单利润",
      value: formatAmount(totals.orderProfit * rate, currency),
      icon: <LineChartOutlined />,
      tone: "orange",
      trend: "15.3%",
      trendDirection: "up",
    },
    {
      title: "利润率",
      value: totals.salesAmount ? `${(totals.orderProfit / totals.salesAmount * 100).toFixed(2)}%` : "-",
      icon: <PieChartOutlined />,
      tone: "purple",
      trend: "2.1%",
      trendDirection: "up",
    },
    {
      title: "广告费",
      value: formatAmount(totals.adSpend * rate, currency),
      icon: <NotificationOutlined />,
      tone: "cyan",
      trend: "6.8%",
      trendDirection: "cost-up",
    },
    {
      title: "广告占比",
      value: totals.salesAmount ? `${(totals.adSpend / totals.salesAmount * 100).toFixed(2)}%` : "-",
      icon: <PercentageOutlined />,
      tone: "sky",
      trend: "1.2%",
      trendDirection: "down",
    },
  ] as const;

  return (
    <section className="daily-sales__summary" aria-label="销售统计">
      {metrics.map((metric) => (
        <Card
          key={metric.title}
          size="small"
          className={`daily-sales__summary-card daily-sales__summary-card--${metric.tone}`}
        >
          <span className="daily-sales__summary-icon" aria-hidden="true">{metric.icon}</span>
          <span className="daily-sales__summary-content">
            <span className="daily-sales__summary-title">{metric.title}</span>
            <strong>{metric.value}</strong>
          </span>
          <span
            className={`daily-sales__summary-comparison daily-sales__summary-comparison--${metric.trendDirection}`}
          >
            <span className="daily-sales__summary-trend">
              {metric.trendDirection === "down" ? <ArrowDownOutlined /> : <ArrowUpOutlined />}
              {metric.trend}
            </span>
            <span className="daily-sales__summary-period">较上期</span>
          </span>
        </Card>
      ))}
    </section>
  );
}

export default DailySalesSummaryCards;
