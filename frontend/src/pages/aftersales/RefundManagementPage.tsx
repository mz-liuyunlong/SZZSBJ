import {
  CloudDownloadOutlined,
  EditOutlined,
  SettingOutlined,
} from "@ant-design/icons";
import { ProTable, type ProColumns } from "@ant-design/pro-components";
import {
  Button,
  Card,
  DatePicker,
  Empty,
  Modal,
  Segmented,
  Select,
  Space,
  Tabs,
  Tag,
  Tooltip,
  Typography,
  message,
} from "antd";
import datePickerZhCN from "antd/es/date-picker/locale/zh_CN";
import dayjs, { type Dayjs } from "dayjs";
import ReactECharts from "echarts-for-react";
import { useEffect, useMemo, useState } from "react";

import PageShell from "@/components/page/PageShell";
import CommittedSearch from "@/components/report-table/CommittedSearch";
import ResetButton from "@/components/report-table/ResetButton";
import ReportTableShell from "@/components/report-table/ReportTableShell";
import ResizableColumnTitle from "@/components/report-table/ResizableColumnTitle";
import RuntimeColumnConfigDrawer from "@/components/report-table/RuntimeColumnConfigDrawer";
import {
  CopyableTextCell,
  ProductIdentityCell,
  SkuMskuIdentityCell,
} from "@/components/report-table/cells";
import {
  REPORT_TABLE_DEFAULT_PAGE_SIZE,
  REPORT_TABLE_PAGE_SIZE_OPTIONS,
  normalizeReportTablePageSize,
} from "@/components/report-table/pagination";
import type { NavigationPage } from "@/config/navigation";
import {
  useRefundItemsQuery,
  useRefundOverviewQuery,
  useRefundProductAnalysisQuery,
} from "@/pages/aftersales/refundManagementQueries";
import type {
  RefundAnalysisView,
  RefundDetailRow,
  RefundFilters,
  RefundLagAnalysis,
  RefundMetric,
  RefundSearchField,
  RefundProductDetail,
  RefundProductSort,
} from "@/pages/aftersales/refundManagementTypes";
import { disableFutureDate } from "@/shared/date/disableFutureDate";
import ReportFacetSelect from "@/shared/report-filters";

import "@/pages/aftersales/RefundManagementPage.css";

interface RefundManagementPageProps {
  page: NavigationPage;
}

type DetailColumnKey =
  | "store"
  | "product"
  | "sku"
  | "owner"
  | "orderId"
  | "orderedAt"
  | "refundedAt"
  | "refundLag"
  | "qty"
  | "loss"
  | "reason"
  | "responsibility";

const refundDetailColumnFields: { key: DetailColumnKey; title: string }[] = [
  { key: "store", title: "店铺" },
  { key: "product", title: "商品ID / 品名" },
  { key: "sku", title: "SKU / MSKU" },
  { key: "owner", title: "负责人" },
  { key: "orderId", title: "平台订单号" },
  { key: "orderedAt", title: "订购时间" },
  { key: "refundedAt", title: "退款时间" },
  { key: "refundLag", title: "退款周期" },
  { key: "qty", title: "退款数量" },
  { key: "loss", title: "退款损失" },
  { key: "reason", title: "售后原因" },
  { key: "responsibility", title: "责任归属" },
];

const defaultColumnKeys = refundDetailColumnFields.map((item) => item.key);

const defaultColumnWidths: Record<DetailColumnKey, number> = {
  store: 176,
  product: 190,
  sku: 190,
  owner: 110,
  orderId: 185,
  orderedAt: 150,
  refundedAt: 150,
  refundLag: 100,
  qty: 100,
  loss: 110,
  reason: 190,
  responsibility: 150,
};

const createInitialFilters = (): RefundFilters => ({
  owners: [],
  stores: [],
  reasons: [],
  responsibilities: [],
  currency: "USD",
  datePreset: "custom",
  // 2026-09-01 is the production acceptance day already imported and verified.
  dateRange: ["2026-09-01", "2026-09-01"],
  searchField: "sku",
  keyword: "",
});

const rangePresets = (): { label: string; value: [Dayjs, Dayjs] }[] => {
  const today = dayjs();
  return [
    { label: "今天", value: [today, today] },
    { label: "昨天", value: [today.subtract(1, "day"), today.subtract(1, "day")] },
    { label: "最近7天", value: [today.subtract(6, "day"), today] },
    { label: "最近30天", value: [today.subtract(29, "day"), today] },
    { label: "本月", value: [today.startOf("month"), today] },
    {
      label: "上月",
      value: [
        today.subtract(1, "month").startOf("month"),
        today.subtract(1, "month").endOf("month"),
      ],
    },
    { label: "本年", value: [today.startOf("year"), today] },
    {
      label: "去年",
      value: [
        today.subtract(1, "year").startOf("year"),
        today.subtract(1, "year").endOf("year"),
      ],
    },
  ];
};

const trendMetricMeta: Record<
  RefundMetric,
  { label: string; suffix: string; prefix: string }
> = {
  qty: { label: "退款数量", suffix: "件", prefix: "" },
  rate: { label: "退款率", suffix: "%", prefix: "" },
  loss: { label: "退款损失", suffix: "", prefix: "$" },
};

const formatRefundMoney = (value: number) => (
  `-$${Math.abs(value).toLocaleString("en-US", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })}`
);

const formatRefundMoneyCompact = (value: number) => (
  `-$${Math.abs(value).toLocaleString("en-US", {
    maximumFractionDigits: 2,
  })}`
);

const formatCount = (value: number) => value.toLocaleString("en-US", {
  maximumFractionDigits: 4,
});

const formatPercent = (value: number | null, digits = 2) => (
  value == null ? "-" : `${value.toFixed(digits)}%`
);

const formatDays = (value: number | null) => {
  if (value == null) return "-";
  const rounded = Math.round(value * 10) / 10;
  return `${rounded.toLocaleString("en-US", { maximumFractionDigits: 1 })}天`;
};

const changeStyle = (value: number | null): { color: string } => ({
  color: value == null || value === 0
    ? "#98a2b3"
    : value > 0
      ? "#e5484d"
      : "#16a36a",
});

const formatChange = (value: number | null, unit: "%" | "pp") => {
  if (value == null) return "暂无上期基准";
  const arrow = value > 0 ? "↑" : value < 0 ? "↓" : "→";
  return `${arrow} ${Math.abs(value).toFixed(2)}${unit}`;
};

function trendOption(
  metric: RefundMetric,
  dates: string[],
  trend: { qty: number[]; rate: number[]; loss: number[] },
) {
  const values = metric === "loss"
    ? trend.loss.map((value) => -Math.abs(value))
    : trend[metric];
  const meta = trendMetricMeta[metric];

  const formatTrendValue = (value: number) => {
    if (metric === "loss") {
      return `-$${Math.abs(value).toLocaleString("en-US", { maximumFractionDigits: 2 })}`;
    }
    return `${meta.prefix}${value}${meta.suffix}`;
  };

  return {
    animationDuration: 250,
    tooltip: {
      trigger: "axis",
      backgroundColor: "#172033",
      borderWidth: 0,
      textStyle: { color: "#fff", fontSize: 15 },
      valueFormatter: (value: number) => formatTrendValue(value),
    },
    grid: { left: 46, right: 18, top: 18, bottom: 32 },
    xAxis: {
      type: "category",
      data: dates,
      boundaryGap: false,
      axisLine: { lineStyle: { color: "#dfe6ee" } },
      axisTick: { show: false },
      axisLabel: { color: "#8a95a6", fontSize: 14 },
    },
    yAxis: {
      type: "value",
      splitLine: { lineStyle: { color: "#edf1f5" } },
      axisLine: { show: false },
      axisTick: { show: false },
      axisLabel: {
        color: "#8a95a6",
        fontSize: 14,
        formatter: (value: number) => formatTrendValue(value),
      },
    },
    series: [
      {
        name: meta.label,
        type: "line",
        smooth: 0.25,
        symbol: "circle",
        symbolSize: 6,
        lineStyle: { width: 3, color: "#1677ff" },
        itemStyle: {
          color: "#fff",
          borderColor: "#1677ff",
          borderWidth: 2,
        },
        areaStyle: {
          color: {
            type: "linear",
            x: 0,
            y: 0,
            x2: 0,
            y2: 1,
            colorStops: [
              { offset: 0, color: "rgba(22,119,255,.18)" },
              { offset: 1, color: "rgba(22,119,255,0)" },
            ],
          },
        },
        data: values,
      },
    ],
  };
}

function heatOption(
  dates: string[],
  products: { productId: string; msku: string; name: string }[],
  heat: number[][],
) {
  const data: [number, number, number][] = [];
  heat.forEach((row, yIndex) => {
    row.forEach((value, xIndex) => {
      data.push([xIndex, yIndex, value]);
    });
  });
  const maxValue = Math.max(1, ...data.map((item) => item[2]));

  return {
    tooltip: {
      position: "top",
      backgroundColor: "#172033",
      borderWidth: 0,
      textStyle: { color: "#fff", fontSize: 15 },
      formatter: (params: { value: [number, number, number] }) => {
        const [x, y, value] = params.value;
        const product = products[y];
        const identity = product ? `${product.productId} / ${product.msku}` : "-";
        return `${identity}<br/>${dates[x] ?? "-"} · ${value}件`;
      },
    },
    grid: { left: 95, right: 18, top: 12, bottom: 38 },
    xAxis: {
      type: "category",
      data: dates,
      axisLine: { show: false },
      axisTick: { show: false },
      axisLabel: { color: "#8a95a6", fontSize: 14 },
    },
    yAxis: {
      type: "category",
      data: products.map((item) => item.productId),
      axisLine: { show: false },
      axisTick: { show: false },
      axisLabel: { color: "#667085", fontSize: 14 },
    },
    visualMap: {
      min: 0,
      max: maxValue,
      calculable: false,
      orient: "horizontal",
      left: "center",
      bottom: 0,
      inRange: {
        color: ["#f5f9ff", "#dbeaff", "#9bc5fb", "#4f96ee"],
      },
      textStyle: { fontSize: 13, color: "#98a2b3" },
    },
    series: [
      {
        type: "heatmap",
        data,
        label: { show: true, fontSize: 13, color: "#344054" },
      },
    ],
  };
}

function productTrendOption(dates: string[], product: RefundProductDetail) {
  const base = trendOption("qty", dates, {
    qty: product.trend,
    rate: product.trend.map(() => 0),
    loss: product.trend.map(() => 0),
  });
  return {
    ...base,
    series: [
      {
        name: "退款数量",
        type: "line",
        smooth: 0.25,
        symbol: "circle",
        symbolSize: 6,
        lineStyle: { width: 3, color: "#1677ff" },
        itemStyle: {
          color: "#fff",
          borderColor: "#1677ff",
          borderWidth: 2,
        },
        areaStyle: {
          color: {
            type: "linear",
            x: 0,
            y: 0,
            x2: 0,
            y2: 1,
            colorStops: [
              { offset: 0, color: "rgba(22,119,255,.16)" },
              { offset: 1, color: "rgba(22,119,255,0)" },
            ],
          },
        },
        data: product.trend,
      },
    ],
  };
}

function productReasonOption(product: RefundProductDetail) {
  return {
    animationDuration: 220,
    tooltip: {
      trigger: "axis",
      axisPointer: { type: "shadow" },
      backgroundColor: "#172033",
      borderWidth: 0,
      textStyle: { color: "#fff", fontSize: 13 },
    },
    grid: { left: 88, right: 38, top: 8, bottom: 8 },
    xAxis: { type: "value", show: false },
    yAxis: {
      type: "category",
      inverse: true,
      data: product.reasons.map((item) => item.name),
      axisLine: { show: false },
      axisTick: { show: false },
      axisLabel: { color: "#667085", fontSize: 14 },
    },
    series: [
      {
        name: "退款单数",
        type: "bar",
        barWidth: 10,
        data: product.reasons.map((item) => ({
          value: item.count,
          itemStyle: { color: item.color, borderRadius: [0, 8, 8, 0] },
        })),
        label: {
          show: true,
          position: "right",
          color: "#475467",
          fontSize: 14,
        },
      },
    ],
  };
}

function lagOption(lag: RefundLagAnalysis) {
  return {
    animationDuration: 220,
    tooltip: {
      trigger: "axis",
      axisPointer: { type: "shadow" },
      backgroundColor: "#172033",
      borderWidth: 0,
      textStyle: { color: "#fff", fontSize: 13 },
      formatter: (params: Array<{ dataIndex: number }>) => {
        const index = params[0]?.dataIndex ?? 0;
        const bucket = lag.buckets[index];
        if (!bucket) return "";
        return [
          bucket.name,
          `退款单：${bucket.orders}`,
          `退款数量：${formatCount(bucket.count)}件`,
          `数量占比：${formatPercent(bucket.ratio)}`,
          `退款金额：$${bucket.amount.toFixed(2)}`,
          `退款损失：${formatRefundMoney(bucket.loss)}`,
        ].join("<br/>");
      },
    },
    grid: { left: 72, right: 34, top: 10, bottom: 22 },
    xAxis: {
      type: "value",
      axisLine: { show: false },
      axisTick: { show: false },
      axisLabel: { color: "#98a2b3", fontSize: 13 },
      splitLine: { show: false },
    },
    yAxis: {
      type: "category",
      inverse: true,
      data: lag.buckets.map((item) => item.name),
      axisLine: { show: false },
      axisTick: { show: false },
      axisLabel: { color: "#667085", fontSize: 14 },
    },
    series: [
      {
        name: "退款数量",
        type: "bar",
        barWidth: 10,
        data: lag.buckets.map((item) => item.count),
        itemStyle: { color: "#78aef1", borderRadius: [0, 8, 8, 0] },
        label: {
          show: true,
          position: "right",
          formatter: "{c}件",
          color: "#475467",
          fontSize: 13,
        },
      },
    ],
  };
}

function RefundManagementPage({ page }: RefundManagementPageProps) {
  const [messageApi, messageContextHolder] = message.useMessage();
  const [filters, setFilters] = useState<RefundFilters>(createInitialFilters);
  const [activeTab, setActiveTab] = useState("analysis");
  const [metric, setMetric] = useState<RefundMetric>("qty");
  const [analysisView, setAnalysisView] = useState<RefundAnalysisView>("trend");
  const [breakdownView, setBreakdownView] = useState<"reason" | "responsibility">("reason");
  const [productSort, setProductSort] = useState<RefundProductSort>("rate");
  const [selectedProductKey, setSelectedProductKey] = useState("");
  const [detailProductKey, setDetailProductKey] = useState("");
  const [columnConfigOpen, setColumnConfigOpen] = useState(false);
  const [appliedColumnKeys, setAppliedColumnKeys] = useState<string[]>(defaultColumnKeys);
  const [columnWidths, setColumnWidths] = useState<Record<DetailColumnKey, number>>(
    defaultColumnWidths,
  );
  const [currentPage, setCurrentPage] = useState(1);
  const [pageSize, setPageSize] = useState(REPORT_TABLE_DEFAULT_PAGE_SIZE);
  const [orderTimeEditorRowId, setOrderTimeEditorRowId] = useState<string | null>(null);
  const [orderTimeDraft, setOrderTimeDraft] = useState<Dayjs | null>(null);
  const [orderTimeError, setOrderTimeError] = useState("");
  const [orderTimeAudit, setOrderTimeAudit] = useState<
    Record<string, { original: string; corrected: string; updatedAt: string }>
  >({});

  const overviewQuery = useRefundOverviewQuery(filters);
  const productQuery = useRefundProductAnalysisQuery(filters, selectedProductKey);
  const itemsQuery = useRefundItemsQuery(filters, currentPage, pageSize, detailProductKey);

  const overview = overviewQuery.data;
  const productAnalysis = productQuery.data;
  const itemResult = itemsQuery.data;

  const queryError = overviewQuery.error ?? productQuery.error ?? itemsQuery.error;
  useEffect(() => {
    if (!queryError) return;
    void messageApi.error("退款数据读取失败，请稍后重试");
  }, [messageApi, queryError]);

  const selectedProduct = productAnalysis?.selected ?? null;
  const overviewReasons = overview?.reasons ?? [];
  const overviewResponsibilities = overview?.responsibilities ?? [];
  const breakdownRows = breakdownView === "reason" ? overviewReasons : overviewResponsibilities;
  const sortedProducts = useMemo(() => {
    const rows = [...(productAnalysis?.items ?? [])];
    const value = (item: (typeof rows)[number]) => {
      if (productSort === "rate") return item.rate ?? Number.NEGATIVE_INFINITY;
      if (productSort === "loss") return item.loss;
      return item.qty;
    };
    return rows.sort((left, right) => value(right) - value(left));
  }, [productAnalysis?.items, productSort]);

  const detailRows = useMemo(() => (
    (itemResult?.rows ?? []).map((row) => {
      const override = orderTimeAudit[row.id];
      if (!override) return row;
      const refundAt = dayjs(row.refundedAt);
      const correctedAt = dayjs(override.corrected);
      const lagDays = refundAt.isValid() && correctedAt.isValid() && !refundAt.isBefore(correctedAt)
        ? refundAt.diff(correctedAt, "minute") / 1440
        : null;
      return {
        ...row,
        orderedAt: override.corrected,
        refundLagDays: lagDays,
      };
    })
  ), [itemResult?.rows, orderTimeAudit]);

  const resetProductScope = () => {
    setSelectedProductKey("");
    setDetailProductKey("");
    setCurrentPage(1);
  };

  const resetFilters = () => {
    setFilters(createInitialFilters());
    resetProductScope();
  };

  const copyText = async (value: string) => {
    try {
      await navigator.clipboard.writeText(value);
      void messageApi.success("已复制");
    } catch {
      void messageApi.error("复制失败，请手动复制");
    }
  };

  const exportCsv = () => {
    const rows = [
      refundDetailColumnFields.map((item) => item.title),
      ...detailRows.map((row) => [
        row.store,
        `${row.productId} / ${row.productName}`,
        `${row.sku} / ${row.msku}`,
        row.owner,
        row.orderId,
        row.orderedAt,
        row.refundedAt,
        row.refundLagDays == null ? "" : row.refundLagDays.toFixed(2),
        row.qty,
        row.loss == null ? "" : -Math.abs(row.loss),
        row.reason.name,
        row.responsibility.name,
      ]),
    ];

    const csv = rows
      .map((row) => row.map((cell) => `"${String(cell).replaceAll('"', '""')}"`).join(","))
      .join("\n");
    const blob = new Blob(["\uFEFF", csv], { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = "退款明细-当前页.csv";
    anchor.click();
    URL.revokeObjectURL(url);
  };

  const openProductDetails = () => {
    if (!selectedProduct) return;
    setDetailProductKey(selectedProduct.productKey);
    setCurrentPage(1);
    setActiveTab("details");
  };

  const parseOrderedAt = (value: string) => {
    const parsed = dayjs(value);
    return parsed.isValid() ? parsed : null;
  };

  const editingOrderTimeRow = orderTimeEditorRowId === null
    ? null
    : detailRows.find((row) => row.id === orderTimeEditorRowId) ?? null;

  const openOrderTimeEditor = (row: RefundDetailRow) => {
    setOrderTimeEditorRowId(row.id);
    setOrderTimeDraft(parseOrderedAt(row.orderedAt));
    setOrderTimeError("");
  };

  const closeOrderTimeEditor = () => {
    setOrderTimeEditorRowId(null);
    setOrderTimeDraft(null);
    setOrderTimeError("");
  };

  const saveOrderTimeEditor = () => {
    if (!editingOrderTimeRow) return;
    if (!orderTimeDraft) {
      setOrderTimeError("请选择实际订购日期和时间。");
      return;
    }
    const refundTime = dayjs(editingOrderTimeRow.refundedAt);
    if (refundTime.isValid() && orderTimeDraft.isAfter(refundTime)) {
      setOrderTimeError("订购时间不能晚于退款时间。");
      return;
    }

    const corrected = orderTimeDraft.format("YYYY-MM-DD HH:mm");
    setOrderTimeAudit((current) => ({
      ...current,
      [editingOrderTimeRow.id]: {
        original: current[editingOrderTimeRow.id]?.original ?? editingOrderTimeRow.orderedAt,
        corrected,
        updatedAt: dayjs().format("YYYY-MM-DD HH:mm:ss"),
      },
    }));
    closeOrderTimeEditor();
    void messageApi.success("已临时校正；当前未写入数据库");
  };

  const summary = overview?.summary;
  const kpis = [
    {
      key: "orders",
      title: "退款订单",
      badge: "较上一周期",
      value: summary ? formatCount(summary.refundOrders) : "-",
      footerLabel: "订单数",
      change: summary?.ordersChangeRate ?? null,
      changeUnit: "%" as const,
      extra: summary ? `${formatCount(summary.refundItemRows)} 条明细` : "",
      tone: "blue",
    },
    {
      key: "qty",
      title: "退款数量",
      badge: "较上一周期",
      value: summary ? formatCount(summary.refundQty) : "-",
      footerLabel: "退款件数",
      change: summary?.qtyChangeRate ?? null,
      changeUnit: "%" as const,
      extra: summary ? `销售 ${formatCount(summary.salesQty)} 件` : "",
      tone: "purple",
    },
    {
      key: "loss",
      title: "退款损失",
      badge: "公司实际损失成本",
      value: summary ? formatRefundMoney(summary.refundLossAmount) : "-",
      footerLabel: "损失",
      change: summary?.lossChangeRate ?? null,
      changeUnit: "%" as const,
      extra: summary?.avgRefundLossPerUnit == null
        ? ""
        : `件均 ${formatRefundMoney(summary.avgRefundLossPerUnit)}`,
      tone: "green",
    },
    {
      key: "rate",
      title: "退款率",
      badge: "退款数量 / 销售数量",
      value: summary ? formatPercent(summary.refundRate) : "-",
      footerLabel: "较上期",
      change: summary?.refundRateChangePp ?? null,
      changeUnit: "pp" as const,
      extra: summary ? `退款金额 $${summary.refundAmount.toFixed(2)}` : "",
      tone: "orange",
    },
  ];

  const baseColumns: ProColumns<RefundDetailRow>[] = [
    { title: "店铺", dataIndex: "store", key: "store" },
    {
      title: "商品ID / 品名",
      key: "product",
      render: (_, row) => (
        <ProductIdentityCell
          productId={row.productId}
          productName={row.productName}
          onCopy={(value) => void copyText(value)}
        />
      ),
    },
    {
      title: "SKU / MSKU",
      key: "sku",
      render: (_, row) => (
        <SkuMskuIdentityCell
          sku={row.sku}
          msku={row.msku}
          onCopy={(value) => void copyText(value)}
        />
      ),
    },
    {
      title: "负责人",
      dataIndex: "owner",
      key: "owner",
      render: (_, row) => (
        <Tag bordered={false} className="refund-management__owner-tag">
          {row.owner}
        </Tag>
      ),
    },
    {
      title: "平台订单号",
      key: "orderId",
      render: (_, row) => (
        <CopyableTextCell
          text={row.orderId}
          label="平台订单号"
          onCopy={(value) => void copyText(value)}
        />
      ),
    },
    {
      title: "订购时间",
      key: "orderedAt",
      render: (_, row) => (
        <span className="refund-management__order-time-cell">
          <span>{row.orderedAt}</span>
          <Tooltip title="人工校正订购时间（当前仅页面临时值）">
            <Button
              type="text"
              size="small"
              className="refund-management__time-edit-button"
              aria-label={`人工校正订购时间：${row.orderId}`}
              icon={<EditOutlined aria-hidden="true" />}
              onClick={() => openOrderTimeEditor(row)}
            />
          </Tooltip>
          {orderTimeAudit[row.id] ? (
            <Tag bordered={false} className="refund-management__manual-time-tag">
              临时校正
            </Tag>
          ) : null}
        </span>
      ),
    },
    { title: "退款时间", dataIndex: "refundedAt", key: "refundedAt" },
    {
      title: "退款周期",
      key: "refundLag",
      render: (_, row) => formatDays(row.refundLagDays),
    },
    {
      title: "退款数量",
      dataIndex: "qty",
      key: "qty",
      render: (_, row) => formatCount(row.qty),
    },
    {
      title: "退款损失",
      key: "loss",
      render: (_, row) => (
        <span className="report-table-metric">
          {row.loss == null ? "-" : formatRefundMoney(row.loss)}
        </span>
      ),
    },
    {
      title: "售后原因",
      key: "reason",
      render: (_, row) => (
        <Tooltip
          title={(
            <div>
              <div>原始 Code：{row.rawReasonCode || "-"}</div>
              <div>原始描述：{row.rawDescription || "-"}</div>
              <div>标准分类：{row.reason.categoryName}</div>
            </div>
          )}
        >
          <span style={{ display: "flex", minWidth: 0, flexDirection: "column", gap: 2 }}>
            <Tag bordered={false} color={row.reason.color} style={{ width: "fit-content" }}>
              {row.reason.name}
            </Tag>
            {row.rawDescription && row.rawDescription !== row.reason.name ? (
              <Typography.Text
                type="secondary"
                ellipsis={{ tooltip: row.rawDescription }}
                style={{ maxWidth: 170, fontSize: 11 }}
              >
                {row.rawDescription}
              </Typography.Text>
            ) : null}
          </span>
        </Tooltip>
      ),
    },
    {
      title: "责任归属",
      key: "responsibility",
      render: (_, row) => (
        <Tooltip title={`判定来源：${row.responsibility.source} · 置信度：${row.responsibility.confidence}`}>
          <Tag bordered={false} color={row.responsibility.color}>
            {row.responsibility.name}
          </Tag>
        </Tooltip>
      ),
    },
  ];

  const columnMap = new Map(baseColumns.map((column) => [String(column.key), column]));
  const detailColumns = appliedColumnKeys.flatMap((key) => {
    const column = columnMap.get(key);
    const field = refundDetailColumnFields.find((item) => item.key === key);
    if (!column || !field) return [];
    const typedKey = key as DetailColumnKey;
    const width = columnWidths[typedKey] ?? defaultColumnWidths[typedKey];
    const minWidth = Math.max(88, field.title.length * 14 + 32);
    return [
      {
        ...column,
        width,
        align: "left" as const,
        onHeaderCell: () => ({ className: "report-table-resizable-header-cell" }),
        title: (
          <ResizableColumnTitle
            label={field.title}
            width={width}
            minWidth={minWidth}
            onWidthChange={(nextWidth) => setColumnWidths((current) => ({
              ...current,
              [typedKey]: nextWidth,
            }))}
          />
        ),
      },
    ];
  });

  const analysisPanel = (
    <div className="refund-management__analysis">
      <div className="refund-management__overview-grid">
        <Card
          size="small"
          className="refund-management__analysis-card"
          loading={overviewQuery.isLoading}
        >
          <div className="refund-management__card-head">
            <div>
              <h3>退款监控</h3>
              <p>退款时间按 returnOrderDate；商品风险退款率按店铺ID + 商品ID + MSKU对齐同期销量</p>
            </div>
            <Space size={8}>
              <Segmented
                className="refund-management__metric-segment"
                size="small"
                value={metric}
                options={[
                  { label: "退款数量", value: "qty" },
                  { label: "退款率", value: "rate" },
                  { label: "退款损失", value: "loss" },
                ]}
                onChange={(value) => setMetric(value as RefundMetric)}
              />
              <Segmented
                className="refund-management__view-segment"
                size="small"
                value={analysisView}
                options={[
                  { label: "趋势", value: "trend" },
                  { label: "商品集中", value: "heat" },
                ]}
                onChange={(value) => setAnalysisView(value as RefundAnalysisView)}
              />
            </Space>
          </div>
          {overview && productAnalysis ? (
            <ReactECharts
              className="refund-management__overview-chart"
              option={analysisView === "trend"
                ? trendOption(metric, overview.dates, overview.trend)
                : heatOption(productAnalysis.dates, productAnalysis.items, productAnalysis.heat)}
              notMerge
              lazyUpdate
            />
          ) : (
            <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无退款趋势数据" />
          )}
        </Card>

        <Card
          size="small"
          className="refund-management__analysis-card"
          loading={overviewQuery.isLoading}
        >
          <div className="refund-management__card-head refund-management__card-head--compact">
            <div><h3>{breakdownView === "reason" ? "售后原因 TOP" : "责任归属 TOP"}</h3></div>
            <Segmented
              size="small"
              value={breakdownView}
              options={[
                { label: "售后原因", value: "reason" },
                { label: "责任归属", value: "responsibility" },
              ]}
              onChange={(value) => setBreakdownView(value as "reason" | "responsibility")}
            />
          </div>
          <div className="refund-management__reason-list">
            {breakdownRows.length > 0 ? (
              breakdownRows.map((item) => {
                const maxCount = Math.max(1, ...breakdownRows.map((row) => row.count));
                return (
                  <div key={item.code} className="refund-management__reason-row">
                    <Tag bordered={false} color={item.color}>{item.name}</Tag>
                    <div className="refund-management__reason-track">
                      <i
                        style={{
                          width: `${(item.count / maxCount) * 100}%`,
                          backgroundColor: item.color,
                        }}
                      />
                    </div>
                    <strong>{item.count}单</strong>
                    <em>{formatRefundMoneyCompact(item.loss)}</em>
                  </div>
                );
              })
            ) : (
              <Empty
                image={Empty.PRESENTED_IMAGE_SIMPLE}
                description={breakdownView === "reason" ? "暂无原因数据" : "暂无责任数据"}
              />
            )}
          </div>
        </Card>
      </div>

      <div className="refund-management__diagnosis-grid">
        <Card
          size="small"
          className="refund-management__risk-card refund-management__analysis-card"
          loading={productQuery.isLoading}
        >
          <div className="refund-management__card-head refund-management__risk-card-head">
            <div>
              <h3>商品风险列表</h3>
              <p>选择商品后右侧即时诊断</p>
            </div>
            <Segmented
              className="refund-management__sku-sort-segment"
              size="small"
              value={productSort}
              options={[
                { label: "退款率", value: "rate" },
                { label: "损失", value: "loss" },
                { label: "数量", value: "qty" },
              ]}
              onChange={(value) => setProductSort(value as RefundProductSort)}
            />
          </div>
          <div className="refund-management__risk-list">
            {sortedProducts.length > 0 ? sortedProducts.map((product) => {
              const active = product.productKey === selectedProduct?.productKey;
              return (
                <button
                  key={product.productKey}
                  type="button"
                  className={[
                    "refund-management__risk-item",
                    active ? "is-active" : "",
                  ].filter(Boolean).join(" ")}
                  onClick={() => setSelectedProductKey(product.productKey)}
                >
                  <div className="refund-management__risk-top">
                    <div>
                      <strong>{product.name}</strong>
                      <span>{product.productId} / {product.msku} · {product.store}</span>
                    </div>
                    <Space size={4} wrap>
                      {product.topReason ? (
                        <Tag bordered={false} color={product.topReason.color}>
                          {product.topReason.name}
                        </Tag>
                      ) : null}
                      {product.topResponsibility ? (
                        <Tag bordered={false} color={product.topResponsibility.color}>
                          {product.topResponsibility.name}
                        </Tag>
                      ) : null}
                    </Space>
                  </div>
                  <div className="refund-management__risk-metrics">
                    <span>
                      <small>退款率</small>
                      <b>{product.sales > 0 ? formatPercent(product.rate) : "—"}</b>
                      {product.sales <= 0 && product.qty > 0 ? <small>无同期销量</small> : null}
                    </span>
                    <span><small>退款/销量</small><b>{formatCount(product.qty)}/{formatCount(product.sales)}</b></span>
                    <span><small>损失</small><b>{formatRefundMoneyCompact(product.loss)}</b></span>
                  </div>
                </button>
              );
            }) : (
              <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无商品退款数据" />
            )}
          </div>
        </Card>

        <div className="refund-management__diagnosis-center">
          <Card
            size="small"
            className="refund-management__analysis-card refund-management__sku-focus"
            loading={productQuery.isLoading}
          >
            {selectedProduct ? (
              <div className="refund-management__sku-focus-inner">
                <div className="refund-management__sku-name">
                  <strong>{selectedProduct.name}</strong>
                  <span>商品ID {selectedProduct.productId} · MSKU {selectedProduct.msku} · {selectedProduct.store}</span>
                </div>
                <div className="refund-management__sku-stats">
                  <span>
                    <small>退款率</small>
                    <b>{selectedProduct.sales > 0 ? formatPercent(selectedProduct.rate) : "—"}</b>
                    {selectedProduct.sales <= 0 && selectedProduct.qty > 0 ? <small>无同期销量</small> : null}
                  </span>
                  <span><small>退款数量</small><b>{formatCount(selectedProduct.qty)}件</b></span>
                  <span><small>退款损失</small><b>{formatRefundMoneyCompact(selectedProduct.loss)}</b></span>
                  <span><small>销量</small><b>{formatCount(selectedProduct.sales)}</b></span>
                </div>
                <Button type="primary" onClick={openProductDetails}>查看退款明细</Button>
              </div>
            ) : (
              <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无商品数据" />
            )}
          </Card>

          <Card
            size="small"
            className="refund-management__analysis-card"
            loading={productQuery.isLoading}
          >
            <div className="refund-management__card-head refund-management__card-head--compact">
              <div>
                <h3>该商品退款趋势</h3>
                <p>单商品的退款数量随退款时间变化</p>
              </div>
            </div>
            {selectedProduct && productAnalysis ? (
              <ReactECharts
                className="refund-management__sku-trend-chart"
                option={productTrendOption(productAnalysis.dates, selectedProduct)}
                notMerge
                lazyUpdate
              />
            ) : (
              <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无趋势数据" />
            )}
          </Card>

          <div className="refund-management__diagnosis-bottom">
            <Card size="small" className="refund-management__analysis-card" loading={productQuery.isLoading}>
              <div className="refund-management__card-head refund-management__card-head--compact">
                <div><h3>该商品主要售后原因</h3></div>
              </div>
              {selectedProduct && selectedProduct.reasons.length > 0 ? (
                <ReactECharts
                  className="refund-management__sku-reason-chart"
                  option={productReasonOption(selectedProduct)}
                  notMerge
                  lazyUpdate
                />
              ) : (
                <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无原因数据" />
              )}
            </Card>

            <Card size="small" className="refund-management__analysis-card" loading={productQuery.isLoading}>
              <div className="refund-management__card-head refund-management__card-head--compact">
                <div><h3>诊断摘要</h3></div>
              </div>
              {selectedProduct ? (
                <div className="refund-management__insight">
                  <strong>
                    {selectedProduct.topReason?.name ?? "未分类"} 是当前主要原因
                    {selectedProduct.topResponsibility
                      ? ` · ${selectedProduct.topResponsibility.name}`
                      : ""}
                  </strong>
                  <p>
                    {selectedProduct.sales > 0
                      ? `该商品当前退款率 ${formatPercent(selectedProduct.rate)}`
                      : "该商品当前无同期销量，退款率不可计算"}
                    ，退款数量 {formatCount(selectedProduct.qty)} 件，
                    退款损失 {formatRefundMoneyCompact(selectedProduct.loss)}。原因与责任均由后端标准化规则返回，
                    可结合退款周期与明细中的原始描述继续核查。
                  </p>
                </div>
              ) : (
                <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无诊断数据" />
              )}
            </Card>
          </div>
        </div>

        <Card
          size="small"
          className="refund-management__period-card refund-management__analysis-card"
          loading={productQuery.isLoading}
        >
          <div className="refund-management__card-head refund-management__card-head--compact">
            <div>
              <h3>退款发生周期</h3>
              <p>退款周期 = 退款时间 - 订购时间；按退款数量计算区间占比</p>
            </div>
          </div>
          {selectedProduct ? (
            <>
              <ReactECharts
                className="refund-management__period-chart"
                option={lagOption(selectedProduct.lag)}
                notMerge
                lazyUpdate
              />
              <div className="refund-management__period-stats">
                <span><small>平均退款周期</small><b>{formatDays(selectedProduct.lag.averageDays)}</b></span>
                <span><small>中位数</small><b>{formatDays(selectedProduct.lag.medianDays)}</b></span>
                <span>
                  <small>主要区间</small>
                  <b>{selectedProduct.lag.buckets.find((item) => item.key === selectedProduct.lag.mainBucket)?.name ?? "-"}</b>
                </span>
                <span><small>区间占比</small><b>{formatPercent(selectedProduct.lag.mainBucketRatio)}</b></span>
              </div>
              <div className="refund-management__period-note">
                <strong>周期数据说明</strong>
                <p>
                  当前 {selectedProduct.lag.eligibleItemRows} 条明细可计算退款周期；
                  {selectedProduct.lag.missingTimeRows > 0
                    ? `另有 ${selectedProduct.lag.missingTimeRows} 条缺少有效订购时间或退款时间，未计入周期比例。`
                    : "订购时间与退款时间均完整。"}
                </p>
              </div>
            </>
          ) : (
            <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无退款周期数据" />
          )}
        </Card>
      </div>
    </div>
  );

  const detailPanel = (
    <ReportTableShell label="退款明细数据表" className="refund-management__detail-shell">
      <ProTable<RefundDetailRow>
        columns={detailColumns}
        dataSource={detailRows}
        rowKey="id"
        search={false}
        options={false}
        toolBarRender={false}
        tableAlertRender={false}
        tableAlertOptionRender={false}
        bordered
        size="small"
        loading={itemsQuery.isLoading || itemsQuery.isFetching}
        scroll={{ x: "max-content", y: "100%" }}
        pagination={{
          current: currentPage,
          pageSize,
          total: itemResult?.total ?? 0,
          showSizeChanger: true,
          showQuickJumper: true,
          pageSizeOptions: REPORT_TABLE_PAGE_SIZE_OPTIONS,
          showTotal: (total) => `共 ${total} 条`,
          onChange: (nextPage, nextPageSize) => {
            if (nextPageSize !== pageSize) {
              setPageSize(normalizeReportTablePageSize(nextPageSize));
              setCurrentPage(1);
              return;
            }
            setCurrentPage(nextPage);
          },
        }}
        locale={{
          emptyText: (
            <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无匹配退款数据" />
          ),
        }}
      />
    </ReportTableShell>
  );

  return (
    <PageShell page={page}>
      {messageContextHolder}
      <div
        className={`refund-management ${
          activeTab === "details"
            ? "refund-management--details"
            : "refund-management--analysis"
        }`}
      >
        <section className="refund-management__page-head">
          <Typography.Title level={3}>售后退款</Typography.Title>
          <Typography.Paragraph type="secondary">
            查看退款趋势、商品异常、售后原因、退款发生周期与公司实际退款损失。
          </Typography.Paragraph>
        </section>

        <Card size="small" className="refund-management__toolbar-card">
          <div className="refund-management__toolbar">
            <ReportFacetSelect
              mode="multiple"
              ariaLabel="店铺"
              placeholder="全部店铺"
              unit="个店铺"
              value={filters.stores}
              options={overview?.stores ?? []}
              triggerWidth={126}
              popupWidth={360}
              onChange={(value) => {
                setFilters((current) => ({ ...current, stores: Array.isArray(value) ? value : [] }));
                resetProductScope();
              }}
            />
            <ReportFacetSelect
              mode="multiple"
              ariaLabel="负责人"
              placeholder="全部负责人"
              unit="人"
              value={filters.owners}
              options={overview?.owners ?? []}
              triggerWidth={126}
              onChange={(value) => {
                setFilters((current) => ({ ...current, owners: Array.isArray(value) ? value : [] }));
                resetProductScope();
              }}
            />
            <ReportFacetSelect
              mode="multiple"
              ariaLabel="售后原因"
              placeholder="全部售后原因"
              unit="个原因"
              value={filters.reasons}
              options={overview?.reasonOptions ?? []}
              triggerWidth={140}
              onChange={(value) => {
                setFilters((current) => ({ ...current, reasons: Array.isArray(value) ? value : [] }));
                resetProductScope();
              }}
            />
            <ReportFacetSelect
              mode="multiple"
              ariaLabel="责任归属"
              placeholder="全部责任归属"
              unit="项"
              value={filters.responsibilities}
              options={overview?.responsibilityOptions ?? []}
              triggerWidth={140}
              onChange={(value) => {
                setFilters((current) => ({
                  ...current,
                  responsibilities: Array.isArray(value) ? value : [],
                }));
                resetProductScope();
              }}
            />
            <DatePicker.RangePicker
              className="refund-management__date-range"
              aria-label="日期范围"
              locale={datePickerZhCN}
              presets={rangePresets()}
              value={filters.dateRange
                ? [dayjs(filters.dateRange[0]), dayjs(filters.dateRange[1])]
                : undefined}
              format="YYYY-MM-DD"
              separator="~"
              allowClear={false}
              disabledDate={disableFutureDate}
              onChange={(dates) => {
                const [start, end] = dates ?? [];
                if (!start || !end) return;
                setFilters((current) => ({
                  ...current,
                  datePreset: "custom",
                  dateRange: [
                    start.format("YYYY-MM-DD"),
                    end.format("YYYY-MM-DD"),
                  ],
                }));
                resetProductScope();
              }}
            />
            <Select
              className="report-filter-select refund-management__currency-select"
              classNames={{ popup: { root: "report-filter-select-dropdown" } }}
              aria-label="币种"
              value="USD"
              options={[{ label: "USD", value: "USD" }]}
              disabled
            />
            <CommittedSearch
              className="refund-management__search"
              typeAriaLabel="搜索类型"
              typeOptions={[
                { label: "SKU", value: "sku" },
                { label: "MSKU", value: "msku" },
                { label: "商品ID", value: "productId" },
                { label: "品名", value: "productName" },
                { label: "订单号", value: "orderId" },
              ]}
              typeValue={filters.searchField}
              inputAriaLabel="搜索内容"
              inputPlaceholder="搜索 MSKU / SKU / 商品ID / 品名 / 订单号"
              inputValue={filters.keyword}
              batch={{
                ariaLabel: "批量搜索",
                placeholder: "请输入 SKU / MSKU / 商品ID / 平台订单号，一行一个",
                unsupportedMessage: "品名暂不支持批量搜索",
                isSupported: (field) => field !== "productName",
                onMessage: (content) => void messageApi.info(content),
                onCommit: (values, field) => {
                  setFilters((current) => ({
                    ...current,
                    searchField: field as RefundSearchField,
                    keyword: "",
                    batchValues: values,
                  }));
                  resetProductScope();
                },
              }}
              onCommit={({ searchField, keyword }) => {
                setFilters((current) => ({
                  ...current,
                  searchField: searchField as RefundSearchField,
                  keyword,
                  batchValues: undefined,
                }));
                resetProductScope();
              }}
            />
            <ResetButton onClick={resetFilters} />
            <span className="refund-management__toolbar-spacer" />
            <Tooltip title="列配置">
              <Button
                aria-label="列配置"
                icon={<SettingOutlined aria-hidden="true" />}
                onClick={() => setColumnConfigOpen(true)}
              />
            </Tooltip>
            <Tooltip title="下载当前页CSV">
              <Button
                aria-label="下载"
                icon={<CloudDownloadOutlined aria-hidden="true" />}
                onClick={exportCsv}
                disabled={detailRows.length === 0}
              />
            </Tooltip>
          </div>
        </Card>

        <section className="refund-management__kpis" aria-label="退款统计">
          {kpis.map((item) => (
            <Card
              key={item.key}
              size="small"
              loading={overviewQuery.isLoading}
              className={`refund-management__kpi refund-management__kpi--${item.tone}`}
            >
              <div className="refund-management__kpi-head">
                <span>{item.title}</span><em>{item.badge}</em>
              </div>
              <strong>{item.value}</strong>
              <div className="refund-management__kpi-foot">
                {item.footerLabel}{" "}
                <b style={changeStyle(item.change)}>{formatChange(item.change, item.changeUnit)}</b>
                {item.extra ? ` · ${item.extra}` : ""}
              </div>
            </Card>
          ))}
        </section>

        <Tabs
          className="refund-management__tabs"
          activeKey={activeTab}
          onChange={setActiveTab}
          items={[
            { key: "analysis", label: "退款分析", children: analysisPanel },
            { key: "details", label: "退款明细", children: detailPanel },
          ]}
        />

        <Modal
          className="refund-management__time-modal"
          title="人工校正订购时间"
          open={orderTimeEditorRowId !== null}
          width={520}
          centered
          destroyOnClose
          maskClosable={false}
          footer={null}
          onCancel={closeOrderTimeEditor}
        >
          {editingOrderTimeRow ? (
            <div className="refund-management__time-editor">
              <div className="refund-management__time-editor-card">
                <div className="refund-management__time-editor-card-row refund-management__time-editor-card-row--stack">
                  <span className="refund-management__time-editor-label">平台订单号</span>
                  <strong className="refund-management__time-editor-order-id">
                    {editingOrderTimeRow.orderId}
                  </strong>
                </div>
                <div className="refund-management__time-editor-card-grid">
                  <div className="refund-management__time-editor-card-row">
                    <span className="refund-management__time-editor-label">店铺</span>
                    <span className="refund-management__time-editor-value">{editingOrderTimeRow.store}</span>
                  </div>
                  <div className="refund-management__time-editor-card-row">
                    <span className="refund-management__time-editor-label">商品ID</span>
                    <span className="refund-management__time-editor-value">{editingOrderTimeRow.productId}</span>
                  </div>
                  <div className="refund-management__time-editor-card-row refund-management__time-editor-card-row--full">
                    <span className="refund-management__time-editor-label">当前订购时间</span>
                    <span className="refund-management__time-editor-value">{editingOrderTimeRow.orderedAt}</span>
                  </div>
                  <div className="refund-management__time-editor-card-row refund-management__time-editor-card-row--full">
                    <span className="refund-management__time-editor-label">退款时间</span>
                    <span className="refund-management__time-editor-value">{editingOrderTimeRow.refundedAt}</span>
                  </div>
                </div>
              </div>
              <div className="refund-management__time-editor-field">
                <label className="refund-management__time-editor-field-label">实际订购时间</label>
                <DatePicker
                  className="refund-management__order-time-picker"
                  locale={datePickerZhCN}
                  placeholder="请选择订购日期"
                  format="YYYY-MM-DD HH:mm"
                  showTime={{ format: "HH:mm" }}
                  allowClear={false}
                  disabledDate={disableFutureDate}
                  value={orderTimeDraft}
                  style={{ width: "100%" }}
                  onChange={(value) => {
                    setOrderTimeDraft(value);
                    if (value) setOrderTimeError("");
                  }}
                />
                <div className="refund-management__time-editor-hint">
                  当前仅用于页面临时核对退款周期，不会写回数据库；持久化校正接口后续单独接入。
                </div>
                {orderTimeError ? (
                  <div className="refund-management__time-editor-error">{orderTimeError}</div>
                ) : null}
              </div>
              <div className="refund-management__time-editor-footer">
                <Button onClick={closeOrderTimeEditor}>取消</Button>
                <Button type="primary" onClick={saveOrderTimeEditor}>临时应用</Button>
              </div>
            </div>
          ) : null}
        </Modal>

        <RuntimeColumnConfigDrawer
          open={columnConfigOpen}
          groups={[{ title: "退款明细字段", fields: refundDetailColumnFields }]}
          fixedKeys={[]}
          defaultKeys={defaultColumnKeys}
          appliedKeys={appliedColumnKeys}
          onApply={setAppliedColumnKeys}
          onClose={() => setColumnConfigOpen(false)}
          onSaveTemplate={() => void messageApi.info("列模板接口待接入")}
        />
      </div>
    </PageShell>
  );
}

export default RefundManagementPage;
