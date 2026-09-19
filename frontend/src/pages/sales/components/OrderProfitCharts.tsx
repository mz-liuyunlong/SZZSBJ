/** Switchable server-aggregated product-ID profit chart; chart requests do not load detail rows. */
import { Radio } from "antd";
import ReactECharts from "echarts-for-react";
import dayjs from "dayjs";
import { useState } from "react";
import type { OrderProfitTrendPoint } from "@/pages/sales/orderProfitApi";
import {
  MOCK_USD_TO_CNY_RATE,
  type OrderProfitCurrency,
} from "@/pages/sales/orderProfitTypes";

interface OrderProfitChartsProps {
  points: OrderProfitTrendPoint[];
  currency: OrderProfitCurrency;
  endDate?: string;
}

type ChartMetric = "salesVolume" | "salesAmount" | "orderProfit" | "profitMargin" | "adSpend" | "adRatio";

const metricOptions: { label: string; value: ChartMetric }[] = [
  { label: "销量", value: "salesVolume" },
  { label: "销售额", value: "salesAmount" },
  { label: "订单利润", value: "orderProfit" },
  { label: "利润率", value: "profitMargin" },
  { label: "广告费", value: "adSpend" },
  { label: "广告占比", value: "adRatio" },
];

const amountMetrics: ChartMetric[] = ["salesAmount", "orderProfit", "adSpend"];
const percentMetrics: ChartMetric[] = ["profitMargin", "adRatio"];

function OrderProfitCharts({ points, currency, endDate }: OrderProfitChartsProps) {
  const [metric, setMetric] = useState<ChartMetric>("salesVolume");
  const metricLabel = metricOptions.find((item) => item.value === metric)?.label ?? "销量";
  const rate = currency === "CNY" ? MOCK_USD_TO_CNY_RATE : 1;
  const symbol = currency === "CNY" ? "¥" : "$";

  const trendEndDate = endDate ? dayjs(endDate) : dayjs();
  const dateKeys = Array.from({ length: 7 }, (_, index) => trendEndDate
    .subtract(6 - index, "day")
    .format("YYYY-MM-DD"));
  const labels = dateKeys.map((dateKey) => dayjs(dateKey).format("MM-DD"));
  const pointMap = new Map(points.map((point) => [point.date, point]));

  const values = dateKeys.map((dateKey) => {
    const point = pointMap.get(dateKey);
    if (!point) return 0;

    if (metric === "profitMargin") return point.profitMargin ?? 0;
    if (metric === "adRatio") return point.adRatio ?? 0;

    const value = point[metric];
    return amountMetrics.includes(metric) ? value * rate : value;
  });

  const formatValue = (value: number | null | undefined) => {
    if (value == null || !Number.isFinite(value)) return "—";
    if (amountMetrics.includes(metric)) return `${symbol}${value.toFixed(2)}`;
    if (percentMetrics.includes(metric)) return `${value.toFixed(2)}%`;
    return Math.round(value).toLocaleString("zh-CN");
  };

  const option = {
    animationDuration: 240,
    color: ["#1677ff"],
    tooltip: {
      trigger: "axis",
      backgroundColor: "#fff",
      borderColor: "#e5eaf3",
      borderWidth: 1,
      padding: [8, 10],
      textStyle: { color: "#1f2937", fontSize: 12 },
      valueFormatter: (value: number | null | undefined) => formatValue(value),
    },
    grid: { top: 28, right: 20, bottom: 28, left: 60 },
    xAxis: {
      type: "category",
      boundaryGap: false,
      axisLine: { lineStyle: { color: "#cbd5e1" } },
      axisTick: { show: false },
      axisLabel: { color: "#667085", fontSize: 12 },
      splitLine: { show: true, lineStyle: { color: "#e5eaf3", type: "dashed" } },
      data: labels,
    },
    yAxis: {
      type: "value",
      name: metricLabel,
      splitNumber: 3,
      nameTextStyle: { color: "#667085", fontSize: 12, align: "right" },
      axisLine: { show: false },
      axisTick: { show: false },
      axisLabel: {
        color: "#667085",
        fontSize: 12,
        formatter: (value: number) => formatValue(value),
      },
      splitLine: { lineStyle: { color: "#e5eaf3", type: "dashed" } },
    },
    series: [{
      name: metricLabel,
      type: "line",
      symbol: "circle",
      symbolSize: 7,
      smooth: true,
      lineStyle: { width: 2.5, color: "#1677ff" },
      itemStyle: { color: "#1677ff", borderColor: "#fff", borderWidth: 2 },
      areaStyle: {
        color: {
          type: "linear",
          x: 0,
          y: 0,
          x2: 0,
          y2: 1,
          colorStops: [
            { offset: 0, color: "rgba(22, 119, 255, 0.20)" },
            { offset: 1, color: "rgba(22, 119, 255, 0.02)" },
          ],
        },
      },
      data: values,
    }],
  };

  return (
    <section className="order-profit__charts" aria-label="订单利润趋势图">
      <div className="order-profit__chart-card" aria-label={`${metricLabel}趋势`}>
        <div className="order-profit__chart-header">
          <h3>{metricLabel}趋势</h3>
          <Radio.Group
            aria-label="图表指标"
            size="small"
            optionType="button"
            buttonStyle="solid"
            value={metric}
            options={metricOptions}
            onChange={(event) => setMetric(event.target.value as ChartMetric)}
          />
        </div>
        <ReactECharts option={option} notMerge lazyUpdate />
      </div>
    </section>
  );
}

export default OrderProfitCharts;
