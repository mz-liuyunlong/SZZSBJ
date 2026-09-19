/** Daily-sales operating metrics from server summary plus refund-event totals. */
import { useMemo } from "react";
import ReportSummaryCards, {
  type ReportSummaryCard,
  type ReportSummaryMetricComparison,
  type ReportSummaryTrendDirection,
  type ReportSummaryTrendTone,
} from "@/components/report-table/ReportSummaryCards";
import type { DailySalesServerSummary } from "@/pages/sales/dailySalesApi";
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
  serverSummary?: DailySalesServerSummary | null;
  previousServerSummary?: DailySalesServerSummary | null;
  previousSummaryRange?: string | null;
}

interface SummaryTotals {
  salesVolume: number | null;
  salesAmount: number | null;
  orderProfit: number | null;
  profitRate: number | null;
  adSpend: number | null;
  adRatio: number | null;
  refundQuantity: number | null;
  refundAmount: number | null;
}

const formatAmount = (value: number, currency: DailySalesCurrency) => {
  const symbol = currency === "CNY" ? "¥" : "$";
  return `${symbol}${value.toLocaleString("en-US", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })}`;
};

const formatAmountOrDash = (value: number | null, currency: DailySalesCurrency) => (
  value == null ? "—" : formatAmount(value, currency)
);

const formatInteger = (value: number | null) => (
  value == null ? "—" : Math.round(value).toLocaleString("zh-CN")
);

const formatPercent = (value: number | null) => (
  value == null ? "—" : `${value.toFixed(2)}%`
);

const currencyRate = (
  sourceCurrency: DailySalesCurrency,
  targetCurrency: DailySalesCurrency,
) => {
  if (sourceCurrency === targetCurrency) return 1;
  return sourceCurrency === "USD" ? MOCK_USD_TO_CNY_RATE : 1 / MOCK_USD_TO_CNY_RATE;
};

const toServerTotals = (
  summary: DailySalesServerSummary,
  currency: DailySalesCurrency,
): SummaryTotals => {
  const salesAmount = summary.salesAmount * currencyRate(summary.salesCurrency, currency);
  const orderProfit = summary.orderProfitAmount
    * currencyRate(summary.orderProfitCurrency, currency);
  const adSpend = summary.adSpendAmount * currencyRate(summary.adSpendCurrency, currency);
  const refundAmount = summary.refundEventAmount
    * currencyRate(summary.refundEventCurrency, currency);

  return {
    salesVolume: summary.salesQuantity,
    salesAmount,
    orderProfit,
    profitRate: salesAmount ? orderProfit / salesAmount * 100 : null,
    adSpend,
    adRatio: salesAmount ? adSpend / salesAmount * 100 : null,
    refundQuantity: summary.refundEventQuantity,
    refundAmount,
  };
};

const toFallbackTotals = (
  rows: DailySalesRow[],
  currency: DailySalesCurrency,
  refundSummary: DailySalesRefundSummary | null,
): SummaryTotals => {
  const incompleteProfit = rows.some((row) => row.orderProfit == null);
  const rate = currency === "CNY" ? MOCK_USD_TO_CNY_RATE : 1;
  const refundRate = refundSummary == null || refundSummary.currency === currency
    ? 1
    : refundSummary.currency === "USD"
      ? MOCK_USD_TO_CNY_RATE
      : 1 / MOCK_USD_TO_CNY_RATE;

  const salesVolume = rows.reduce((total, row) => total + row.salesVolume, 0);
  const salesAmount = rows.reduce((total, row) => total + row.salesAmount, 0) * rate;
  const orderProfit = incompleteProfit
    ? null
    : rows.reduce((total, row) => total + (row.orderProfit ?? 0), 0) * rate;
  const adSpend = rows.reduce((total, row) => total + row.adSpend, 0) * rate;
  const refundAmount = refundSummary == null ? null : refundSummary.amount * refundRate;

  return {
    salesVolume,
    salesAmount,
    orderProfit,
    profitRate: salesAmount && orderProfit != null ? orderProfit / salesAmount * 100 : null,
    adSpend,
    adRatio: salesAmount ? adSpend / salesAmount * 100 : null,
    refundQuantity: refundSummary?.quantity ?? null,
    refundAmount,
  };
};

const trendTone = (
  direction: ReportSummaryTrendDirection,
  change: number | null,
): ReportSummaryTrendTone => {
  if (change == null || direction === "flat") return "neutral";
  return direction === "up" ? "good" : "bad";
};

const buildComparison = (
  current: number | null,
  previous: number | null,
  formatter: (value: number | null) => string,
): ReportSummaryMetricComparison => {
  const currentText = formatter(current);
  const previousText = formatter(previous);

  if (current == null || previous == null) {
    return {
      current: currentText,
      previous: previous == null ? "暂无数据" : previousText,
      change: null,
      direction: "flat",
      tone: "neutral",
      status: "暂无对比",
    };
  }

  const direction: ReportSummaryTrendDirection = current === previous
    ? "flat"
    : current > previous
      ? "up"
      : "down";

  const change = previous === 0
    ? current === 0 ? 0 : null
    : (current - previous) / Math.abs(previous) * 100;

  const tone = trendTone(direction, change);

  return {
    current: currentText,
    previous: previousText,
    change: change == null ? null : `${Math.abs(change).toFixed(1)}%`,
    direction,
    tone,
    status: direction === "up" ? "上涨" : direction === "down" ? "下降" : "持平",
  };
};

function DailySalesSummaryCards({
  rows,
  currency,
  refundSummary,
  serverSummary,
  previousServerSummary,
  previousSummaryRange,
}: DailySalesSummaryCardsProps) {
  const { totals, previousTotals } = useMemo(() => {
    const currentTotals = serverSummary
      ? toServerTotals(serverSummary, currency)
      : toFallbackTotals(rows, currency, refundSummary);

    return {
      totals: currentTotals,
      previousTotals: previousServerSummary
        ? toServerTotals(previousServerSummary, currency)
        : null,
    };
  }, [currency, refundSummary, rows, serverSummary, previousServerSummary]);

  const previous = previousTotals;
  const comparisonBadge = previousSummaryRange ? `较 ${previousSummaryRange}` : "较昨日";

  const cards: ReportSummaryCard[] = [
    {
      id: "sales",
      title: "销售表现",
      badge: comparisonBadge,
      accent: "#1677FF",
      metrics: [
        {
          label: "销售额",
          value: formatAmountOrDash(totals.salesAmount, currency),
          comparison: buildComparison(
            totals.salesAmount,
            previous?.salesAmount ?? null,
            (value) => formatAmountOrDash(value, currency)
          ),
        },
        {
          label: "销量",
          value: formatInteger(totals.salesVolume),
          comparison: buildComparison(
            totals.salesVolume,
            previous?.salesVolume ?? null,
            formatInteger
          ),
        },
      ],
    },
    {
      id: "ads",
      title: "广告投入",
      badge: comparisonBadge,
      accent: "#7C3AED",
      metrics: [
        {
          label: "广告费",
          value: formatAmountOrDash(totals.adSpend, currency),
          comparison: buildComparison(
            totals.adSpend,
            previous?.adSpend ?? null,
            (value) => formatAmountOrDash(value, currency)
          ),
        },
        {
          label: "广告占比",
          value: formatPercent(totals.adRatio),
          comparison: buildComparison(
            totals.adRatio,
            previous?.adRatio ?? null,
            formatPercent
          ),
        },
      ],
    },
    {
      id: "profit",
      title: "利润表现",
      badge: comparisonBadge,
      accent: "#10B981",
      metrics: [
        {
          label: "利润",
          value: formatAmountOrDash(totals.orderProfit, currency),
          comparison: buildComparison(
            totals.orderProfit,
            previous?.orderProfit ?? null,
            (value) => formatAmountOrDash(value, currency)
          ),
        },
        {
          label: "利润率",
          value: formatPercent(totals.profitRate),
          comparison: buildComparison(
            totals.profitRate,
            previous?.profitRate ?? null,
            formatPercent
          ),
        },
      ],
    },
    {
      id: "refund",
      title: "退款风险",
      badge: comparisonBadge,
      accent: "#F97316",
      metrics: [
        {
          label: "退款金额",
          value: formatAmountOrDash(totals.refundAmount, currency),
          comparison: buildComparison(
            totals.refundAmount,
            previous?.refundAmount ?? null,
            (value) => formatAmountOrDash(value, currency)
          ),
        },
        {
          label: "退款量",
          value: formatInteger(totals.refundQuantity),
          comparison: buildComparison(
            totals.refundQuantity,
            previous?.refundQuantity ?? null,
            formatInteger
          ),
        },
      ],
    },
  ];

  return (
    <ReportSummaryCards
      className="daily-sales__summary"
      ariaLabel="销售统计"
      cards={cards}
    />
  );
}

export default DailySalesSummaryCards;
