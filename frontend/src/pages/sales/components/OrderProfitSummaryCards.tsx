/** Six no-API product-ID profit metrics derived from the currently filtered rows. */
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
  type OrderProfitCurrency,
  type OrderProfitRow,
} from "@/pages/sales/orderProfitTypes";

interface OrderProfitSummaryCardsProps {
  rows: OrderProfitRow[];
  currency: OrderProfitCurrency;
}

const formatAmount = (value: number, currency: OrderProfitCurrency) => {
  const symbol = currency === "CNY" ? "¥" : "$";
  return `${symbol}${value.toLocaleString("en-US", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })}`;
};

function OrderProfitSummaryCards({ rows, currency }: OrderProfitSummaryCardsProps) {
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
      subtitle: "当前筛选销量",
      icon: <ShoppingOutlined />,
      tone: "blue",
      trend: "12.5%",
      trendDirection: "up",
    },
    {
      title: "销售额",
      value: formatAmount(totals.salesAmount * rate, currency),
      subtitle: "销售金额合计",
      icon: <DollarCircleOutlined />,
      tone: "green",
      trend: "8.2%",
      trendDirection: "up",
    },
    {
      title: "订单利润",
      value: formatAmount(totals.orderProfit * rate, currency),
      subtitle: "商品ID利润合计",
      icon: <LineChartOutlined />,
      tone: "orange",
      trend: "15.3%",
      trendDirection: "up",
    },
    {
      title: "利润率",
      value: totals.salesAmount ? `${(totals.orderProfit / totals.salesAmount * 100).toFixed(2)}%` : "-",
      subtitle: "利润 / 销售额",
      icon: <PieChartOutlined />,
      tone: "purple",
      trend: "2.1%",
      trendDirection: "up",
    },
    {
      title: "广告费",
      value: formatAmount(totals.adSpend * rate, currency),
      subtitle: "广告花费合计",
      icon: <NotificationOutlined />,
      tone: "red",
      trend: "6.8%",
      trendDirection: "cost-up",
    },
    {
      title: "广告占比",
      value: totals.salesAmount ? `${(totals.adSpend / totals.salesAmount * 100).toFixed(2)}%` : "-",
      subtitle: "广告费 / 销售额",
      icon: <PercentageOutlined />,
      tone: "cyan",
      trend: "1.2%",
      trendDirection: "down",
    },
  ] as const;

  return (
    <section className="order-profit__summary" aria-label="订单利润统计">
      {metrics.map((metric) => (
        <Card
          key={metric.title}
          size="small"
          className={`order-profit__summary-card order-profit__summary-card--${metric.tone}`}
        >
          <span className="order-profit__summary-icon" aria-hidden="true">{metric.icon}</span>
          <span className="order-profit__summary-content">
            <span className="order-profit__summary-title">{metric.title}</span>
            <strong>{metric.value}</strong>
            <span className="order-profit__summary-subtitle">{metric.subtitle}</span>
          </span>
          <span
            className={`order-profit__summary-comparison order-profit__summary-comparison--${metric.trendDirection}`}
          >
            <span className="order-profit__summary-trend">
              {metric.trendDirection === "down" ? <ArrowDownOutlined /> : <ArrowUpOutlined />}
              {metric.trend}
            </span>
          </span>
        </Card>
      ))}
    </section>
  );
}

export default OrderProfitSummaryCards;
