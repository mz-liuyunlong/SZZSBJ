/** Switchable local-data trend chart; no data leaves the browser. */
import { Radio } from "antd";
import ReactECharts from "echarts-for-react";
import dayjs from "dayjs";
import { useState } from "react";
import {
  MOCK_USD_TO_CNY_RATE,
  type DailySalesCurrency,
  type DailySalesRow,
} from "@/pages/sales/dailySalesTypes";

interface DailySalesChartsProps {
  rows: DailySalesRow[];
  currency: DailySalesCurrency;
}

const labels = Array.from({ length: 7 }, (_, index) => dayjs()
  .subtract(6 - index, "day")
  .format("MM-DD"));
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

function DailySalesCharts({ rows, currency }: DailySalesChartsProps) {
  const [metric, setMetric] = useState<ChartMetric>("salesVolume");
  const metricLabel = metricOptions.find((item) => item.value === metric)?.label ?? "销量";
  const rate = currency === "CNY" ? MOCK_USD_TO_CNY_RATE : 1;
  const symbol = currency === "CNY" ? "¥" : "$";
  const values = labels.map((label) => {
    const dateRows = rows.filter((row) => row.date.endsWith(label));
    const salesAmount = dateRows.reduce((sum, row) => sum + row.salesAmount, 0);
    const orderProfit = dateRows.reduce((sum, row) => sum + row.orderProfit, 0);
    const adSpend = dateRows.reduce((sum, row) => sum + row.adSpend, 0);
    if (metric === "profitMargin") return salesAmount ? orderProfit / salesAmount * 100 : 0;
    if (metric === "adRatio") return salesAmount ? adSpend / salesAmount * 100 : 0;
    const value = dateRows.reduce((sum, row) => sum + Number(row[metric]), 0);
    return amountMetrics.includes(metric) ? value * rate : value;
  });
  const formatValue = (value: number) => {
    if (amountMetrics.includes(metric)) return `${symbol}${value.toFixed(2)}`;
    if (percentMetrics.includes(metric)) return `${value.toFixed(2)}%`;
    return Math.round(value).toLocaleString("zh-CN");
  };
  const option = {
    animationDuration: 180,
    color: ["#1677ff"],
    tooltip: { trigger: "axis", valueFormatter: (value: number) => formatValue(Number(value)) },
    grid: { top: 28, right: 20, bottom: 28, left: 64 },
    xAxis: { type: "category", boundaryGap: false, axisLabel: { fontSize: 12 }, data: labels },
    yAxis: {
      type: "value",
      name: metricLabel,
      splitNumber: 3,
      axisLabel: { fontSize: 12, formatter: (value: number) => formatValue(Number(value)) },
    },
    series: [{
      name: metricLabel,
      type: "line",
      symbol: "circle",
      symbolSize: 6,
      smooth: true,
      lineStyle: { width: 2 },
      data: values,
    }],
  };

  return (
    <section className="daily-sales__charts" aria-label="销售趋势图">
      <div className="daily-sales__chart-card" aria-label={`${metricLabel}趋势`}>
        <div className="daily-sales__chart-header">
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

export default DailySalesCharts;
