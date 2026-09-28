import {
  CheckCircleOutlined,
  DownloadOutlined,
  EditOutlined,
  FileExcelOutlined,
  HistoryOutlined,
  MoreOutlined,
  UploadOutlined,
  } from "@ant-design/icons"; import { useMutation,
  useQuery,
  useQueryClient } from "@tanstack/react-query"; import {   Alert,
  Button,
  ConfigProvider,
  DatePicker,
  Divider,
  Drawer,
  Dropdown,
  Form,
  Input,
  InputNumber,
  Modal,
  Segmented,
  Space,
  Steps,
  Tag,
  Upload,
  message,
  Tooltip,
} from "antd";
import { ProTable, type ProColumns } from "@ant-design/pro-components";
import dayjs, { type Dayjs } from "dayjs";
import { useMemo, useState, type Key } from "react";
import PageShell from "@/components/page/PageShell";
import CommittedSearch, { type CommittedSearchPayload } from "@/components/report-table/CommittedSearch";
import ReportTableShell, { ReportTableSelectionBar } from "@/components/report-table/ReportTableShell";
import RuntimeColumnConfigDrawer, { type RuntimeColumnGroup } from "@/components/report-table/RuntimeColumnConfigDrawer";
import { CopyableTextCell, WalmartProductIdCell } from "@/components/report-table/cells";
import type { NavigationPage } from "@/config/navigation";
import {
  clearOperationPlanProduct,
  downloadOperationPlanFailedRows,
  downloadOperationPlanTemplate,
  fetchOperationPlanEvents,
  fetchOperationPlanOptions,
  fetchOperationPlanProducts,
  fetchOperationPlanSummary,
  importOperationPlans,
  updateOperationPlanTargets,
  type ConflictPolicy,
  type OperationPlanImportData,
  type OperationPlanOwnerRow,
  type OperationPlanPeriodType,
  type OperationPlanProductRow,
  type OperationPlanImportRowResult,
  type OperationPlanSummary,
  type OperationStatus,
  type PlanStatus,
  type SearchField,
  type StockStatus,
} from "@/api/operationPlansApi";
import ReportFacetSelect, { type ReportFacetSelectValue } from "@/shared/report-filters/ReportFacetSelect";
import "@/pages/operations/OperationPlanPage.css";

type PeriodMode = "月度" | "季度";
type TabKey = "dashboard" | "products";
type SearchTypeLabel = "SKU" | "MSKU" | "商品ID" | "品名";

interface OperationPlanPageProps {
  page: NavigationPage;
}

interface ProductFilters {
  owner: string[];
  store: string[];
  operation: string[];
  planStatus: string[];
  stockStatus: string[];
  search: string;
  searchType: SearchTypeLabel;
  batchValues: string[];
}

interface TargetFormValues {
  salesTarget: number;
  profitTarget: number;
  reason?: string;
}

const emptySummary: OperationPlanSummary = {
  sales_target_amount: 0,
  sales_actual_amount: 0,
  sales_forecast_amount: 0,
  gross_profit_target_amount: 0,
  gross_profit_actual_amount: 0,
  gross_profit_forecast_amount: 0,
  product_count: 0,
  unplanned_count: 0,
  lagging_count: 0,
  severe_lagging_count: 0,
  adjusted_product_count: 0,
  sales_target_adjust_amount: 0,
  gross_profit_target_adjust_amount: 0,
  clearance_count: 0,
  period_label: "本期",
  period_progress_rate: 0,
};

const forecastFormulaTitle = (
  <div>
    <div>预计 = 当前累计 + 预测日均 × 剩余天数</div>
    <div>预测日均 = 近7日均 × 70% + 近14日均 × 30%</div>
    <div>近7/14日均按有效数据天数计算，0销量日期也计入有效日。</div>
  </div>
);

const targetSupportFormulaTitle = (
  <div>
    <div>目标支撑 = 可支撑库存 / 剩余目标销量</div>
    <div>可支撑库存 = WFS + 在途 + 本期到仓</div>
    <div>剩余目标销量 = (销售目标 - 当前销售额) / 当前平均售价</div>
    <div>当前平均售价 = 当前销售额 / 当前销量</div>
  </div>
);

const importTemplateGuide = [
  { field: "商品ID", rule: "必填；填写 Listing 管理中的 Walmart 商品ID；需要和 MSKU 组合匹配", example: "20277220088" },
  { field: "MSKU", rule: "必填；填写 Listing 管理中的 MSKU；和商品ID组合后必须唯一命中", example: "YC00002-1A" },
  { field: "销售额（$）", rule: "必填；填写本周期计划销售额，美元数字，必须大于 0", example: "22000" },
  { field: "毛利润（$）", rule: "必填；填写本周期计划毛利润，美元数字，不能小于 0，不能大于销售额", example: "4200" },
  { field: "备注", rule: "可空；记录重点商品、活动说明或调整原因", example: "本月重点商品" },
];

const productColumnFields = [
  { key: "product", title: "商品" },
  { key: "lastPerformance", title: "上月表现" },
  { key: "salesPlan", title: "销售计划" },
  { key: "profitPlan", title: "毛利润计划" },
  { key: "inventory", title: "库存支撑" },
  { key: "status", title: "状态" },
  { key: "actions", title: "操作" },
];

const productColumnGroup: RuntimeColumnGroup[] = [{ title: "商品计划字段", fields: productColumnFields }];
const defaultProductColumnKeys = productColumnFields.map((field) => field.key);
const fixedProductColumnKeys = ["product"];

const money = (value: number | string | null | undefined) => `$${Number(value || 0).toLocaleString("en-US", { maximumFractionDigits: 0 })}`;
const pct = (value: number | string | null | undefined) => `${Number(value || 0).toFixed(1)}%`;

const periodTypeOf = (mode: PeriodMode): OperationPlanPeriodType => mode === "月度" ? "month" : "quarter";
const quarterKeyOf = (value: Dayjs) => `${value.year()}-Q${Math.floor(value.month() / 3) + 1}`;
const periodKeyOf = (mode: PeriodMode, value: Dayjs) => mode === "月度" ? value.format("YYYY-MM") : quarterKeyOf(value);
const periodLabelOf = (mode: PeriodMode, value: Dayjs) => mode === "月度" ? value.format("YYYY-MM") : quarterKeyOf(value);

const searchFieldOptions = [
  { label: "SKU", value: "SKU" },
  { label: "MSKU", value: "MSKU" },
  { label: "商品ID", value: "商品ID" },
  { label: "品名", value: "品名" },
];

const searchFieldMap: Record<SearchTypeLabel, SearchField> = {
  SKU: "sku",
  MSKU: "msku",
  商品ID: "item_id",
  品名: "product_name",
};

const operationLabel: Record<OperationStatus, string> = {
  normal: "正常运营",
  new_product: "新品培育",
  clearance: "清货中",
};

const planStatusLabel: Record<PlanStatus, string> = {
  normal: "正常",
  lagging: "落后",
  severe_lagging: "严重落后",
  unplanned: "未制定",
  clearance: "清货",
};

const statusColor = (status: PlanStatus | StockStatus | OperationStatus) => ({
  normal: "green",
  lagging: "orange",
  severe_lagging: "red",
  unplanned: "default",
  clearance: "cyan",
  risk: "purple",
  new_product: "blue",
}[status] ?? "default");

const toValues = (value: ReportFacetSelectValue) => {
  if (Array.isArray(value)) return value;
  if (value) return [value];
  return [];
};

function OperationPlanPage({ page }: OperationPlanPageProps) {
  const [messageApi, contextHolder] = message.useMessage();
  const queryClient = useQueryClient();
  const [tab, setTab] = useState<TabKey>("dashboard");
  const [periodMode, setPeriodMode] = useState<PeriodMode>("月度");
  const [period, setPeriod] = useState<Dayjs>(dayjs("2026-09-01"));
  const [pageNo, setPageNo] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [selectedKeys, setSelectedKeys] = useState<Key[]>([]);
  const [columnConfigOpen, setColumnConfigOpen] = useState(false);
  const [appliedColumnKeys, setAppliedColumnKeys] = useState(defaultProductColumnKeys);
  const [sourceHint, setSourceHint] = useState("");
  const [detail, setDetail] = useState<OperationPlanProductRow | null>(null);
  const [edit, setEdit] = useState<OperationPlanProductRow | null>(null);
  const [historyItem, setHistoryItem] = useState<OperationPlanProductRow | null>(null);
  const [clearanceCandidate, setClearanceCandidate] = useState<OperationPlanProductRow | null>(null);
  const [bulkAction, setBulkAction] = useState<"adjust" | "clearance" | null>(null);
  const [importOpen, setImportOpen] = useState(false);
  const [importStep, setImportStep] = useState(0);
  const [importPeriodMode, setImportPeriodMode] = useState<PeriodMode>(periodMode);
  const [importPeriod, setImportPeriod] = useState<Dayjs>(period);
  const [conflictPolicy, setConflictPolicy] = useState<ConflictPolicy>("skip_existing");
  const [importResult, setImportResult] = useState<OperationPlanImportData | null>(null);
  const [filters, setFilters] = useState<ProductFilters>({
    owner: [],
    store: [],
    operation: [],
    planStatus: [],
    stockStatus: [],
    search: "",
    searchType: "SKU",
    batchValues: [],
  });

  const periodType = periodTypeOf(periodMode);
  const periodKey = periodKeyOf(periodMode, period);

  const summaryQuery = useQuery({
    queryKey: ["operation-plans", "summary", periodType, periodKey],
    queryFn: () => fetchOperationPlanSummary(periodType, periodKey),
  });

  const optionsQuery = useQuery({
    queryKey: ["operation-plans", "options", periodType, periodKey],
    queryFn: () => fetchOperationPlanOptions(periodType, periodKey),
  });

  const productsQuery = useQuery({
    queryKey: ["operation-plans", "products", periodType, periodKey, filters, pageNo, pageSize],
    queryFn: () => fetchOperationPlanProducts({
      periodType,
      periodKey,
      ownerRef: filters.owner[0],
      storeId: filters.store[0],
      operationStatus: filters.operation[0] as OperationStatus | undefined,
      planStatus: filters.planStatus[0] as PlanStatus | undefined,
      stockStatus: filters.stockStatus[0] as StockStatus | undefined,
      searchField: searchFieldMap[filters.searchType],
      keyword: filters.search,
      batchValues: filters.batchValues,
      page: pageNo,
      pageSize,
    }),
  });

  const historyQuery = useQuery({
    queryKey: ["operation-plans", "events", historyItem?.plan_id],
    queryFn: () => fetchOperationPlanEvents(historyItem?.plan_id ?? ""),
    enabled: Boolean(historyItem?.plan_id),
  });

  const invalidateCurrent = async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ["operation-plans", "summary"] }),
      queryClient.invalidateQueries({ queryKey: ["operation-plans", "products"] }),
      queryClient.invalidateQueries({ queryKey: ["operation-plans", "options"] }),
    ]);
  };

  const updateTargetsMutation = useMutation({
    mutationFn: (args: { planId: string; values: TargetFormValues }) => updateOperationPlanTargets(args.planId, {
      sales_target_amount: args.values.salesTarget,
      gross_profit_target_amount: args.values.profitTarget,
      reason: args.values.reason,
    }),
    onSuccess: async () => {
      await invalidateCurrent();
      setEdit(null);
      void messageApi.success("目标已更新");
    },
    onError: () => void messageApi.error("目标更新失败，请检查后端接口或权限"),
  });

  const clearMutation = useMutation({
    mutationFn: (args: { planId: string; reason?: string }) => clearOperationPlanProduct(args.planId, args.reason),
    onSuccess: async () => {
      await invalidateCurrent();
      setClearanceCandidate(null);
      void messageApi.success("已转为清货");
    },
    onError: () => void messageApi.error("转清货失败，请检查后端接口或权限"),
  });

  const importMutation = useMutation({
    mutationFn: (file: File) => importOperationPlans({
      periodType: periodTypeOf(importPeriodMode),
      periodKey: periodKeyOf(importPeriodMode, importPeriod),
      conflictPolicy,
      file,
    }),
    onSuccess: async (result) => {
      setImportResult(result);
      setImportStep(2);
      await invalidateCurrent();
      if (result.failed_count > 0) {
        void messageApi.warning(`成功处理 ${result.success_count} 行，失败 ${result.failed_count} 行，可下载失败明细补录`);
      } else {
        void messageApi.success(`已成功导入 ${result.success_count} 行`);
      }
    },
    onError: () => void messageApi.error("导入失败，请检查模板或后端接口"),
  });

  const templateMutation = useMutation({
    mutationFn: () => downloadOperationPlanTemplate(periodType, periodKey),
    onError: () => void messageApi.error("模板下载失败"),
  });

  const failedDownloadMutation = useMutation({
    mutationFn: (batchId: string) => downloadOperationPlanFailedRows(batchId),
    onError: () => void messageApi.error("失败明细下载失败"),
  });

  const summary = summaryQuery.data?.summary ?? emptySummary;
  const ownerRows = summaryQuery.data?.owners ?? [];
  const productRows = useMemo(() => productsQuery.data?.items ?? [], [productsQuery.data?.items]);
  const selectedRows = useMemo(() => productRows.filter((row) => selectedKeys.includes(row.plan_id)), [productRows, selectedKeys]);


  const quarterStartMonth = Math.floor(period.month() / 3) * 3;
  const periodStart =
    periodMode === "季度"
      ? period.month(quarterStartMonth).startOf("month")
      : period.startOf("month");
  const periodEnd =
    periodMode === "季度"
      ? period.month(quarterStartMonth + 2).endOf("month")
      : period.endOf("month");
  const periodTotalDays = periodEnd.diff(periodStart, "day") + 1;
  const periodElapsedDays = Math.max(
    0,
    Math.min(
      periodTotalDays,
      Math.round((Number(summary.period_progress_rate || 0) / 100) * periodTotalDays),
    ),
  );
  const periodProgressText = `周期 ${periodElapsedDays}/${periodTotalDays}天`;

  const updateFilter = (patch: Partial<ProductFilters>) => {
    setFilters((current) => ({ ...current, ...patch }));
    setPageNo(1);
    setSelectedKeys([]);
  };

  const clearFilters = () => {
    setFilters({ owner: [], store: [], operation: [], planStatus: [], stockStatus: [], search: "", searchType: "SKU", batchValues: [] });
    setSourceHint("");
    setSelectedKeys([]);
    setPageNo(1);
  };

  const jumpToProducts = (label: string, patch: Partial<ProductFilters>) => {
    setSourceHint(label);
    setTab("products");
    updateFilter(patch);
  };

  const onSearchCommit = ({ searchField, keyword }: CommittedSearchPayload) => {
    updateFilter({ searchType: searchField as SearchTypeLabel, search: keyword, batchValues: [] });
  };

  const onBatchSearchCommit = (values: string[], searchField: string) => {
    updateFilter({ searchType: searchField as SearchTypeLabel, search: "", batchValues: values });
    void messageApi.success(`已按 ${values.length} 个${searchField}批量搜索`);
  };

  const openImportModal = () => {
    setImportPeriodMode(periodMode);
    setImportPeriod(period);
    setConflictPolicy("skip_existing");
    setImportResult(null);
    setImportStep(0);
    setImportOpen(true);
  };

  const closeImportModal = () => {
    setImportOpen(false);
    setImportResult(null);
    setImportStep(0);
  };

  const handleBulkAdjust = async () => {
    if (selectedRows.length === 0) {
      void messageApi.warning("请先选择商品");
      return;
    }
    await Promise.all(selectedRows.map((row) => updateOperationPlanTargets(row.plan_id, {
      sales_target_amount: Math.round(row.sales_target_amount * 1.05),
      gross_profit_target_amount: Math.round(row.gross_profit_target_amount * 1.05),
      reason: "批量选择后调整目标 +5%",
    })));
    await invalidateCurrent();
    setSelectedKeys([]);
    setBulkAction(null);
    void messageApi.success(`已批量调整 ${selectedRows.length} 个商品目标`);
  };

  const handleBulkClearance = async () => {
    if (selectedRows.length === 0) {
      void messageApi.warning("请先选择商品");
      return;
    }
    await Promise.all(selectedRows.map((row) => clearOperationPlanProduct(row.plan_id, "批量选择后转为清货")));
    await invalidateCurrent();
    setSelectedKeys([]);
    setBulkAction(null);
    void messageApi.success(`已将 ${selectedRows.length} 个商品转为清货`);
  };

  const ownerColumns: ProColumns<OperationPlanOwnerRow>[] = [
    {
      title: "负责人",
      dataIndex: "owner_name",
      width: "18%",
      render: (_, row, index) => (
        <div className="owner-person">
          <span className="owner-rank-wrap"><span className={index < 3 ? `owner-medal ${index === 0 ? "gold" : index === 1 ? "silver" : "bronze"}` : "owner-rank-plain"}>{index + 1}</span></span>
          <div className="owner-person-meta">
            <button className="owner-name" onClick={() => jumpToProducts(`负责人业绩 > ${row.owner_name}`, { owner: [row.owner_ref || row.owner_name] })}>{row.owner_name}</button>
            <span className="owner-person-sub">负责 {row.product_count} 个商品</span>
          </div>
        </div>
      ),
    },
    { title: "销售业绩", width: "31%", render: (_, row) => ownerPlanCell(row.sales_actual_amount, row.sales_target_amount, row.sales_completion_rate, "sales") },
    { title: "毛利业绩", width: "31%", render: (_, row) => ownerPlanCell(row.gross_profit_actual_amount, row.gross_profit_target_amount, row.gross_profit_completion_rate, "profit") },
    {
      title: "风险商品",
      width: "20%",
      render: (_, row) => {
        const total = row.lagging_count + row.severe_lagging_count + row.stock_risk_count;
        if (!total) return <span className="risk-empty">暂无风险</span>;
        return (
          <div className="risk-summary">
            <button className="risk-summary-item lag has-risk" onClick={() => jumpToProducts(`${row.owner_name} > 落后商品`, { owner: [row.owner_ref || row.owner_name], planStatus: ["lagging"] })}><span>落后</span><b>{row.lagging_count}</b></button>
            <button className="risk-summary-item severe has-risk" onClick={() => jumpToProducts(`${row.owner_name} > 严重落后`, { owner: [row.owner_ref || row.owner_name], planStatus: ["severe_lagging"] })}><span>严重</span><b>{row.severe_lagging_count}</b></button>
            <button className="risk-summary-item stock has-risk" onClick={() => jumpToProducts(`${row.owner_name} > 库存风险`, { owner: [row.owner_ref || row.owner_name], stockStatus: ["risk"] })}><span>库存</span><b>{row.stock_risk_count}</b></button>
          </div>
        );
      },
    },
  ];

  const renderPlanCell = (
    actual: number,
    target: number,
    forecast: number,
    tone: "sales" | "profit" = "sales",
  ) => {
    const rate = target ? (actual / target) * 100 : 0;
    const safeRate = Math.max(0, Math.min(100, rate));

    return (
      <div className={`plan-cell plan-cell--${tone}`}>
        <div className="plan-values">
          <span>
            <em>当前</em>
            <b>{money(actual)}</b>
          </span>
          <span>
            <em>目标</em>
            <b>{money(target)}</b>
          </span>
        </div>
        <div className="plan-progress">
          <div className="track">
            <div className="fill" style={{ width: `${safeRate}%` }} />
          </div>
          <div className="rate">{pct(rate)}</div>
        </div>
        <div className="plan-foot">
          <span>{periodProgressText}</span>
          <Tooltip title={forecastFormulaTitle} placement="top"><span className="forecast formula-tip">预计 {money(forecast)}</span></Tooltip>
        </div>
      </div>
    );
  };

  const productColumns: Record<string, ProColumns<OperationPlanProductRow>> = {
    product: {
      key: "product",
      title: "商品",
      width: 250,
      fixed: "left",
      render: (_, row) => (
        <div className="ops-product-cell">
          <WalmartProductIdCell productId={row.item_id} />
          <div className="product-name">{row.product_name || "未命名商品"}</div>
          <div className="subtle"><CopyableTextCell text={row.sku || "-"} label="SKU" /> / <CopyableTextCell text={row.msku} label="MSKU" /> · {row.owner_name || row.owner_ref || "未分配"}</div>
        </div>
      ),
    },
    lastPerformance: { key: "lastPerformance", title: periodMode === "季度" ? "上季度表现" : "上月表现", width: 150, render: (_, row) => <div className="last-perf-cell"><div><span>销售额</span><b>{money(row.last_sales_amount)}</b></div><div><span>毛利润</span><b>{money(row.last_gross_profit_amount)}</b></div><div className="last-perf-rate">毛利率 {pct(row.last_gross_profit_rate)}</div></div> },
    salesPlan: { key: "salesPlan", title: "销售计划", width: 230, render: (_, row) => renderPlanCell(row.sales_actual_amount, row.sales_target_amount, row.sales_forecast_amount, "sales") },
    profitPlan: { key: "profitPlan", title: "毛利润计划", width: 230, render: (_, row) => renderPlanCell(row.gross_profit_actual_amount, row.gross_profit_target_amount, row.gross_profit_forecast_amount, "profit") },
    inventory: { key: "inventory", title: "库存支撑", width: 190, render: (_, row) => <div className="inventory-compact"><div className="inventory-line two"><span>WFS<b>{Number(row.wfs_available_qty)}</b></span><span>在途<b>{Number(row.inbound_qty)}</b></span></div><div className="inventory-line"><span>本期到仓</span><b>{Number(row.arriving_qty)}</b></div><Tooltip title={targetSupportFormulaTitle} placement="top"><div className="inventory-support formula-tip">目标支撑 <b>{pct(row.inventory_support_rate)}</b></div></Tooltip></div> },
    status: { key: "status", title: "状态", width: 150, render: (_, row) => <div className="status-stack"><Tag color={statusColor(row.operation_status)}>{operationLabel[row.operation_status]}</Tag><Tag color={statusColor(row.plan_status)}>计划{planStatusLabel[row.plan_status]}</Tag>{row.stock_status === "risk" && <Tag color="purple">库存风险</Tag>}{row.adjusted && <div className="status-adjust">调整 {row.event_count} 次</div>}</div> },
    actions: {
      key: "actions",
      title: "操作",
      fixed: "right",
      width: 70,
      align: "center",
      render: (_, row) => (
        <Dropdown
          trigger={["click"]}
          menu={{
            items: [
              { key: "detail", label: "查看详情" },
              { key: "edit", label: "编辑目标" },
              { key: "history", label: "查看调整记录" },
              { type: "divider" },
              { key: "clear", label: "转为清货", danger: true, disabled: row.operation_status === "clearance" },
            ],
            onClick: ({ key }) => {
              if (key === "detail") setDetail(row);
              if (key === "edit") setEdit(row);
              if (key === "history") setHistoryItem(row);
              if (key === "clear") setClearanceCandidate(row);
            },
          }}
        >
          <Button type="text" size="small" icon={<MoreOutlined />} />
        </Dropdown>
      ),
    },
  };

  const visibleProductColumns = appliedColumnKeys.flatMap((key) => productColumns[key] ? [productColumns[key]] : []);

  const renderGoalCard = (type: "sales" | "profit") => {
    const isSales = type === "sales";
    const actual = isSales ? summary.sales_actual_amount : summary.gross_profit_actual_amount;
    const target = isSales ? summary.sales_target_amount : summary.gross_profit_target_amount;
    const forecast = isSales ? summary.sales_forecast_amount : summary.gross_profit_forecast_amount;
    const rate = target ? (actual / target) * 100 : 0;
    return (
      <div className={`compact-goal-card ${type}`}>
        <div className="compact-goal-head"><span>{isSales ? "销售目标" : "毛利润目标"}</span><small>{summary.period_label}</small></div>
        <div className="compact-goal-main"><div className="compact-goal-amount">{money(actual)}<small>/ {money(target)}</small></div><div className="compact-goal-rate">{pct(rate)}</div></div>
        <div className="goal-track"><div className={`goal-fill ${type}`} style={{ width: `${Math.min(100, rate)}%` }} /></div>
        <div className="compact-goal-foot"><span>当前有效目标 <b>{money(target)}</b></span><span>预计 <b>{money(forecast)}</b></span></div>
      </div>
    );
  };

  return (
    <PageShell page={page}>
      {contextHolder}
      <ConfigProvider theme={{ token: { colorPrimary: "#1677ff", borderRadius: 7, fontSize: 12, colorBorder: "#dbe3ec" } }}>
        <main className="operation-plan-page">
          <div className="operation-plan-title-row"><div className="operation-plan-title">运营计划</div><div className="operation-plan-subtitle">商品级销售与毛利润目标管理，快速查看进度、负责人业绩与商品执行情况。</div></div>
          <div className="operation-plan-main-tabs">
            <button className={`operation-plan-tab ${tab === "dashboard" ? "active" : ""}`} onClick={() => setTab("dashboard")}>计划看板</button>
            <button className={`operation-plan-tab ${tab === "products" ? "active" : ""}`} onClick={() => setTab("products")}>商品计划</button>
            <div className="operation-plan-period"><Segmented size="small" value={periodMode} onChange={(value) => { setPeriodMode(value as PeriodMode); setPageNo(1); }} options={["月度", "季度"]} /><DatePicker size="small" picker={periodMode === "月度" ? "month" : "quarter"} value={period} onChange={(value) => value && setPeriod(value)} allowClear={false} style={{ width: 126 }} /></div>
            {tab === "products" && <div className="operation-plan-tab-actions"><Button size="small" onClick={() => void messageApi.info("批量生成计划接口下一阶段接入")}>批量生成计划</Button><Button size="small" icon={<DownloadOutlined />} loading={templateMutation.isPending} onClick={() => templateMutation.mutate()}>下载模板</Button><Button size="small" type="primary" icon={<UploadOutlined />} onClick={openImportModal}>导入计划</Button></div>}
          </div>

          {(summaryQuery.isError || productsQuery.isError) && <Alert type="error" showIcon message="运营计划接口读取失败" description="请确认后端已应用本次补丁并完成本地 Alembic 迁移。" />}

          <section className={`operation-plan-content-shell ${tab === "dashboard" ? "is-dashboard" : "is-products"}`}>
            {tab === "dashboard" ? (
              <>
                <div className="stats-grid goal-dual">{renderGoalCard("sales")}{renderGoalCard("profit")}<div className="compact-stat-card purple"><small>计划商品</small><b>{summary.product_count}</b><span>未制定 {summary.unplanned_count} 落后 {summary.lagging_count} 严重落后 {summary.severe_lagging_count}</span></div><div className="compact-stat-card orange"><small>目标调整</small><b>{summary.adjusted_product_count} 个商品</b><span>销售目标 {money(summary.sales_target_adjust_amount)} 毛利目标 {money(summary.gross_profit_target_adjust_amount)} 清货 {summary.clearance_count}</span></div></div>
                <ReportTableShell label="负责人业绩" className="owner-card">
                  <div className="card-head-inner"><div><div className="card-title">负责人业绩 <Tag color="blue">{summary.period_label}</Tag></div><div className="card-sub">本期业绩与当前风险，点击负责人或风险数可切换到商品计划筛选结果</div></div></div>
                  <ProTable<OperationPlanOwnerRow> rowKey={(row) => row.owner_ref || row.owner_name} loading={summaryQuery.isLoading} search={false} options={false} bordered={false} size="small" dataSource={ownerRows} columns={ownerColumns} pagination={false} toolBarRender={false} scroll={{ x: 980 }} />
                </ReportTableShell>
              </>
            ) : (
              <>
                <div className="operation-plan-product-tools">
                  <ReportFacetSelect mode="multiple" ariaLabel="负责人" placeholder="负责人" value={filters.owner} options={optionsQuery.data?.owners ?? []} triggerWidth={128} onChange={(value) => updateFilter({ owner: toValues(value) })} />
                  <ReportFacetSelect mode="multiple" ariaLabel="全部店铺" placeholder="全部店铺" value={filters.store} options={optionsQuery.data?.stores ?? []} triggerWidth={136} onChange={(value) => updateFilter({ store: toValues(value) })} />
                  <ReportFacetSelect mode="multiple" ariaLabel="经营状态" placeholder="经营状态" value={filters.operation} options={optionsQuery.data?.operation_statuses ?? []} triggerWidth={136} onChange={(value) => updateFilter({ operation: toValues(value) })} />
                  <ReportFacetSelect mode="multiple" ariaLabel="计划状态" placeholder="计划状态" value={filters.planStatus} options={optionsQuery.data?.plan_statuses ?? []} triggerWidth={136} onChange={(value) => updateFilter({ planStatus: toValues(value) })} />
                  <ReportFacetSelect mode="multiple" ariaLabel="库存状态" placeholder="库存状态" value={filters.stockStatus} options={optionsQuery.data?.stock_statuses ?? []} triggerWidth={136} onChange={(value) => updateFilter({ stockStatus: toValues(value) })} />
                  <CommittedSearch className="operation-plan-search" typeAriaLabel="搜索类型" typeOptions={searchFieldOptions} typeValue={filters.searchType} inputAriaLabel="搜索内容" inputPlaceholder="搜索 MSKU / SKU / 商品ID / 品名" inputValue={filters.search} batch={{ ariaLabel: "批量搜索", placeholder: "20277220088\nYC00002\nYC00002-1A", onCommit: onBatchSearchCommit, onMessage: (content) => void messageApi.warning(content) }} onCommit={onSearchCommit} />
                  <Button onClick={clearFilters}>重置</Button>
                  <Button onClick={() => setColumnConfigOpen(true)}>列配置</Button>
                </div>

                {sourceHint && <div className="source-hint"><Tag color="blue">筛选来源</Tag>{sourceHint}<Button type="link" size="small" onClick={clearFilters}>清除</Button></div>}

                <ReportTableShell label="商品计划表格" className="plan-table-wrap">
                  <ProTable<OperationPlanProductRow>
                    rowKey="plan_id"
                    loading={productsQuery.isLoading}
                    search={false}
                    options={false}
                    dataSource={productRows}
                    columns={visibleProductColumns}
                    tableAlertRender={false}
                    footer={selectedKeys.length > 0 ? () => (
                      <ReportTableSelectionBar selectedCount={selectedKeys.length} actions={[{ key: "batchAdjust", label: "批量编辑目标", onClick: () => setBulkAction("adjust") }, { key: "batchClearance", label: "批量转清货", danger: true, onClick: () => setBulkAction("clearance") }, { key: "clearSelection", label: "清空选择", onClick: () => setSelectedKeys([]) }]} />
                    ) : undefined}
                    toolBarRender={false}
                    bordered
                    size="small"
                    rowSelection={{ selectedRowKeys: selectedKeys, onChange: setSelectedKeys }}
                    scroll={{ x: 1240 }}
                    pagination={{ current: pageNo, pageSize, total: productsQuery.data?.total ?? 0, showSizeChanger: true, showTotal: (total) => `共 ${total} 个商品`, onChange: (nextPage, nextSize) => { setPageNo(nextPage); setPageSize(nextSize); } }}
                  />
                </ReportTableShell>
              </>
            )}
          </section>
        </main>

        <RuntimeColumnConfigDrawer open={columnConfigOpen} groups={productColumnGroup} fixedKeys={fixedProductColumnKeys} defaultKeys={defaultProductColumnKeys} appliedKeys={appliedColumnKeys} onApply={setAppliedColumnKeys} onClose={() => setColumnConfigOpen(false)} onSaveTemplate={() => void messageApi.info("列模板接口待接入")} />

        <Drawer open={Boolean(detail)} width={520} title={detail ? `商品详情：${detail.item_id}` : "商品详情"} onClose={() => setDetail(null)} destroyOnHidden>
          {detail && <div className="drawer-section"><div className="drawer-title">目标与库存</div><div className="detail-grid"><div className="detail-box"><span>销售目标</span><b>{money(detail.sales_target_amount)}</b></div><div className="detail-box"><span>毛利目标</span><b>{money(detail.gross_profit_target_amount)}</b></div><div className="detail-box"><span>WFS</span><b>{Number(detail.wfs_available_qty)}</b></div><div className="detail-box"><span>在途</span><b>{Number(detail.inbound_qty)}</b></div></div><Divider /><div className="drawer-title">执行状态</div><Tag color={statusColor(detail.plan_status)}>{planStatusLabel[detail.plan_status]}</Tag><p>{detail.product_name}</p></div>}
        </Drawer>

        <Modal open={Boolean(historyItem)} title={historyItem ? `调整记录：${historyItem.item_id}` : "调整记录"} onCancel={() => setHistoryItem(null)} footer={<Button onClick={() => setHistoryItem(null)}>关闭</Button>} destroyOnHidden>
          {(historyQuery.data?.items ?? []).map((item) => <div className="history-row" key={item.event_id}><Tag icon={<HistoryOutlined />}>{dayjs(item.created_at).format("YYYY-MM-DD HH:mm")}</Tag><b>{item.event_label}</b><span>{item.sales_target_amount ? money(item.sales_target_amount) : "-"} / {item.gross_profit_target_amount ? money(item.gross_profit_target_amount) : "-"}</span><p>{item.reason || "-"}</p></div>)}
        </Modal>

        <Modal open={Boolean(edit)} title={edit ? `编辑目标：${edit.item_id}` : "编辑目标"} onCancel={() => setEdit(null)} footer={null} destroyOnHidden>
          {edit && <Form<TargetFormValues> layout="vertical" initialValues={{ salesTarget: edit.sales_target_amount, profitTarget: edit.gross_profit_target_amount, reason: "手动调整目标" }} onFinish={(values) => updateTargetsMutation.mutate({ planId: edit.plan_id, values })}><Form.Item label="销售目标" name="salesTarget" rules={[{ required: true }]}><InputNumber min={0} prefix="$" style={{ width: "100%" }} /></Form.Item><Form.Item label="毛利润目标" name="profitTarget" rules={[{ required: true }]}><InputNumber min={0} prefix="$" style={{ width: "100%" }} /></Form.Item><Form.Item label="调整原因" name="reason"><Input /></Form.Item><Space><Button onClick={() => setEdit(null)}>取消</Button><Button type="primary" htmlType="submit" loading={updateTargetsMutation.isPending} icon={<EditOutlined />}>保存</Button></Space></Form>}
        </Modal>

        <Modal open={bulkAction === "adjust"} title={`批量编辑目标：${selectedRows.length} 个商品`} okText="确认调整" cancelText="取消" onOk={() => void handleBulkAdjust()} onCancel={() => setBulkAction(null)} destroyOnHidden>
          <p>将选中商品的销售目标和毛利润目标上调 5%，并写入调整记录。</p>
        </Modal>

        <Modal open={bulkAction === "clearance"} title={`批量转为清货：${selectedRows.length} 个商品`} okText="确认转清货" cancelText="取消" okButtonProps={{ danger: true }} onOk={() => void handleBulkClearance()} onCancel={() => setBulkAction(null)} destroyOnHidden>
          <p>确认后会将选中商品标记为清货中，并保留调整记录。</p>
        </Modal>

        <Modal open={Boolean(clearanceCandidate)} title={clearanceCandidate ? `转为清货：${clearanceCandidate.item_id}` : "转为清货"} okText="确认转清货" cancelText="取消" okButtonProps={{ danger: true }} confirmLoading={clearMutation.isPending} onOk={() => clearanceCandidate && clearMutation.mutate({ planId: clearanceCandidate.plan_id, reason: "单个商品确认转为清货" })} onCancel={() => setClearanceCandidate(null)} destroyOnHidden>
          {clearanceCandidate && <div className="operation-plan-bulk-preview"><p>确认后会将该商品标记为清货中，并保留一条调整记录。</p><div><b>{clearanceCandidate.item_id}</b><span>{clearanceCandidate.product_name}</span></div><div><b>{clearanceCandidate.sku}</b><span>{clearanceCandidate.owner_name} · {clearanceCandidate.store_name}</span></div></div>}
        </Modal>

        <Modal open={importOpen} title="导入计划" width={960} onCancel={closeImportModal} footer={null} destroyOnHidden className="operation-plan-import-modal">
          <Steps current={importStep} items={[{ title: "选择周期" }, { title: "上传文件" }, { title: "导入结果" }, { title: "完成" }]} className="import-steps" />

          {importStep === 0 && <div className="operation-plan-import-step operation-plan-import-step--period"><Form layout="vertical" className="operation-plan-import-form"><Form.Item label="计划类型"><Segmented value={importPeriodMode} onChange={(value) => setImportPeriodMode(value as PeriodMode)} options={["月度", "季度"]} /></Form.Item><Form.Item label={importPeriodMode === "月度" ? "计划月份" : "计划季度"}><DatePicker picker={importPeriodMode === "月度" ? "month" : "quarter"} value={importPeriod} onChange={(value) => value && setImportPeriod(value)} allowClear={false} style={{ width: "100%" }} /></Form.Item><Form.Item label="已有计划处理"><Segmented value={conflictPolicy} onChange={(value) => setConflictPolicy(value as ConflictPolicy)} options={[{ label: "跳过已有计划", value: "skip_existing" }, { label: "覆盖目标金额", value: "overwrite_existing" }]} /></Form.Item></Form><div className="operation-plan-import-actions operation-plan-import-actions--right"><Button type="primary" onClick={() => setImportStep(1)}>下一步</Button></div></div>}

          {importStep === 1 && <div className="operation-plan-import-step"><div className="operation-plan-import-upload-head"><span>模板表头：商品ID / MSKU / 销售额（$） / 毛利润（$） / 备注</span><Button size="small" loading={templateMutation.isPending} onClick={() => templateMutation.mutate()}>下载模板</Button></div><div className="operation-plan-import-guide"><div className="operation-plan-import-guide__title">表格填写要求</div><div className="operation-plan-import-guide__grid">{importTemplateGuide.map((item) => <div key={item.field} className="operation-plan-import-guide__item"><b>{item.field}</b><span>{item.rule}</span><small>示例：{item.example}</small></div>)}</div><div className="operation-plan-import-example"><span>正确示例</span><code>20277220088 | YC00002-1A | 22000 | 4200 | 本月重点商品</code></div></div><Upload.Dragger accept=".xlsx,.csv" beforeUpload={(file) => { importMutation.mutate(file); return false; }} showUploadList={false} className="operation-plan-import-dragger"><p className="ant-upload-drag-icon"><FileExcelOutlined /></p><p className="operation-plan-import-upload-title">点击或拖拽上传计划文件</p><p className="operation-plan-import-upload-desc">上传后后端会立即校验并导入成功行；失败行不会影响成功行</p></Upload.Dragger><div className="operation-plan-import-actions operation-plan-import-actions--between"><Button onClick={() => setImportStep(0)}>上一步</Button><Button loading={importMutation.isPending}>等待上传结果</Button></div></div>}

          {importStep === 2 && importResult && <div className="operation-plan-import-step operation-plan-import-step--validate"><div className="import-summary import-summary--five"><div><span>总数据</span><b>{importResult.row_count}</b></div><div><span>成功处理</span><b className="import-ok">{importResult.success_count}</b></div><div><span>已有计划</span><b>{importResult.existing_count}</b></div><div><span>错误</span><b className="import-error">{importResult.failed_count}</b></div><div><span>新建/更新</span><b>{importResult.created_plan_count}/{importResult.updated_plan_count}</b></div></div>{importResult.failed_count > 0 && <Alert className="operation-plan-import-alert" type="warning" showIcon message={`失败 ${importResult.failed_count} 行未入库；成功行已直接入库`} description={<div className="operation-plan-import-alert-detail"><p>失败数据不会影响已成功商品。下载失败明细，补完商品ID、MSKU或金额后再次导入即可。</p><Button size="small" icon={<DownloadOutlined />} loading={failedDownloadMutation.isPending} onClick={() => failedDownloadMutation.mutate(importResult.batch_id)}>下载失败明细</Button></div>} />}{importResult.failed_count === 0 && <Alert className="operation-plan-import-alert" type="success" showIcon message="本次导入全部成功" description="成功行已经写入运营计划表。" />}<ReportTableShell label="导入结果" className="operation-plan-import-table"><ProTable<OperationPlanImportRowResult> rowKey="row_number" search={false} options={false} size="small" pagination={{ pageSize: 6, size: "small" }} dataSource={importResult.rows} columns={[{ title: "行号", dataIndex: "row_number", width: 80 }, { title: "商品ID", dataIndex: "item_id", width: 130 }, { title: "MSKU", dataIndex: "msku", width: 150 }, { title: "销售额（$）", dataIndex: "sales_target_amount", width: 110, align: "right", render: (_, row) => row.sales_target_amount ? money(row.sales_target_amount) : "-" }, { title: "毛利润（$）", dataIndex: "gross_profit_target_amount", width: 110, align: "right", render: (_, row) => row.gross_profit_target_amount ? money(row.gross_profit_target_amount) : "-" }, { title: "结果", dataIndex: "import_status", width: 120, render: (_, row) => <Tag color={row.import_status === "failed" ? "red" : row.import_status === "skipped" ? "orange" : "green"}>{row.import_status}</Tag> }, { title: "错误原因 / 建议", dataIndex: "error_message", width: 420, render: (_, row) => row.error_message ? <span>{row.error_message}；{row.suggestion}</span> : row.suggestion }]} /></ReportTableShell><div className="operation-plan-import-actions operation-plan-import-actions--between"><Button onClick={() => setImportStep(1)}>继续导入</Button><Space>{importResult.failed_count > 0 && <Button icon={<DownloadOutlined />} onClick={() => failedDownloadMutation.mutate(importResult.batch_id)}>下载失败明细</Button>}<Button type="primary" icon={<CheckCircleOutlined />} onClick={() => setImportStep(3)}>完成</Button></Space></div></div>}

          {importStep === 3 && <div className="operation-plan-import-step operation-plan-import-step--confirm"><Alert type="success" showIcon message="导入流程已完成" description={`当前周期：${importPeriodMode} · ${periodLabelOf(importPeriodMode, importPeriod)}。成功行已入库，失败行可下载后补录。`} /><div className="operation-plan-import-actions operation-plan-import-actions--right"><Button type="primary" onClick={closeImportModal}>关闭</Button></div></div>}
        </Modal>
      </ConfigProvider>
    </PageShell>
  );
}


function ownerPlanCell(actual: number, target: number, rate: number, type: "sales" | "profit") {
  const safeRate = Math.max(0, Math.min(100, Number(rate || 0)));

  return (
    <div className={`owner-plan-cell owner-plan-cell--${type}`}>
      <div className="owner-plan-main">
        <span>
          <em>当前</em>
          <b>{money(actual)}</b>
        </span>
        <span>
          <em>目标</em>
          <b>{money(target)}</b>
        </span>
      </div>
      <div className="owner-mini-track" aria-label={`完成率 ${pct(rate)}`}>
        <i style={{ width: `${safeRate}%` }} />
      </div>
      <div className="owner-plan-footer">
        <span>完成率</span>
        <b>{pct(rate)}</b>
      </div>
    </div>
  );
}

export default OperationPlanPage;
