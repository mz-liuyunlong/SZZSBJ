import { useEffect, useRef, useState } from "react";
import { createNewProductAccountGuard } from "./newProductAccountGuard";
import { Alert, Button, Card, DatePicker, Descriptions, Form, Input, InputNumber, Modal, Select, Space, Tabs, Typography, message } from "antd";
import { ProTable, type ProColumns } from "@ant-design/pro-components";
import dayjs from "dayjs";
import NewProductMetricsPanel from "./NewProductMetricsPanel";
import ReportTableShell from "@/components/report-table/ReportTableShell";
import { StatusTagCell } from "@/components/report-table/cells";
import {
  decideNewProductPurchase,
  getNewProductWorkflows,
  getNewProductListingCandidates,
  getNewProductAccounts,
  getIndependentNewProductPlans,
  getIndependentNewProductPlan,
  getNewProductMetrics,
  getNewProductReconciliation,
  getNewProductDashboard,
  getNewProductScoreCorrections,
  getNewProductRules,
  getNewProductRulesHistory,
  requestNewProductScoreCorrection,
  decideNewProductScoreCorrection,
  updateNewProductDraftRules,
  requestNewProductPurchase,
  reviewNewProductLaunch,
  saveMarketScore,
  verifyNewProductDates,
  type NewProductWorkflowList,
  type NewProductListingCandidate,
  type NewProductListingCandidates,
  type NewProductWorkflowRecord,
  type NewProductPurchasePlan,
  type NewProductPurchasePlanList,
  type NewProductPurchasePlanDetail,
  type NewProductMetrics,
  type NewProductReconciliation,
  type NewProductDashboard,
  type NewProductScoreCorrection,
  type NewProductCorrectionList,
  type NewProductDraftRules,
  type NewProductRulesHistory,
  type NewProductRealMode,
} from "./newProductApi";

type Action = "market" | "request" | "decision" | "review" | "dates" | "correction" | "correction-decision";
type PanelTab = "listing" | "overview" | "records" | "plans" | "corrections" | "rules";
type Draft = {
  score?: number;
  quantity?: number;
  reason: string;
  decision?: "approved_draft" | "rejected";
  correctionDecision?: "approved" | "rejected";
  dimension?: "order" | "ads" | "trust";
  result?: "observe" | "optimize";
  nextReview?: string;
  arrivalDate?: string;
  sellableDate?: string;
};

export default function NewProductLivePanel({ mode, canScore, canRequest, canApprove, canReview, canConfigure }: {
  mode: NewProductRealMode;
  canScore: boolean; canRequest: boolean; canApprove: boolean; canReview: boolean;
  canConfigure: boolean;
}) {
  const [account, setAccount] = useState("");
  const [panelTab, setPanelTab] = useState<PanelTab>(mode === "performance" ? "listing" : "overview");
  const [dashboard, setDashboard] = useState<NewProductDashboard | null>(null);
  const [corrections, setCorrections] = useState<NewProductCorrectionList | null>(null);
  const [correctionRecord, setCorrectionRecord] = useState<NewProductScoreCorrection | null>(null);
  const [rules, setRules] = useState<NewProductDraftRules | null>(null);
  const [ruleHistory, setRuleHistory] = useState<NewProductRulesHistory | null>(null);
  const [ruleReason, setRuleReason] = useState("");
  const [ruleSaving, setRuleSaving] = useState(false);
  const [accounts, setAccounts] = useState<string[]>([]);
  const [accountsError, setAccountsError] = useState<string | null>(null);
  const [data, setData] = useState<NewProductWorkflowList | null>(null);
  const [listingData, setListingData] = useState<NewProductListingCandidates | null>(null);
  const [listingPage, setListingPage] = useState(1);
  const [listingBusy, setListingBusy] = useState(false);
  const [planData, setPlanData] = useState<NewProductPurchasePlanList | null>(null);
  const [planDetail, setPlanDetail] = useState<NewProductPurchasePlanDetail | null>(null);
  const [planPage, setPlanPage] = useState(1);
  const [correctionPage, setCorrectionPage] = useState(1);
  const [skuSearchInput, setSkuSearchInput] = useState("");
  const [skuSearch, setSkuSearch] = useState("");
  const planGuard = useRef(createNewProductAccountGuard());
  const listingGuard = useRef(createNewProductAccountGuard());
  const boardGuard = useRef(createNewProductAccountGuard());
  const correctionGuard = useRef(createNewProductAccountGuard());
  const [page, setPage] = useState(1);
  const [busy, setBusy] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const requestGuard = useRef(createNewProductAccountGuard());
  const [metricData, setMetricData] = useState<NewProductMetrics | null>(null);
  const [reconciliation, setReconciliation] = useState<NewProductReconciliation | null>(null);
  const [reconcileBusy, setReconcileBusy] = useState(false);
  const reconciliationGuard = useRef(createNewProductAccountGuard());
  const [record, setRecord] = useState<NewProductWorkflowRecord | null>(null);
  const [action, setAction] = useState<Action>("market");
  const [draft, setDraft] = useState<Draft>({ reason: "" });
  const [api, context] = message.useMessage();

  useEffect(() => {
    let cancelled = false;
    void getNewProductAccounts()
      .then(items => {
        if (cancelled) return;
        setAccounts(items);
        if (items.length === 1) {
          requestGuard.current.selectAccount(items[0]);
          reconciliationGuard.current.selectAccount(items[0]);
          planGuard.current.selectAccount(items[0]);
          listingGuard.current.selectAccount(items[0]);
          boardGuard.current.selectAccount(items[0]);
          correctionGuard.current.selectAccount(items[0]);
          setAccount(items[0]);
        }
      })
      .catch(error => {
        if (!cancelled) setAccountsError(error instanceof Error ? error.message : "账户列表读取失败");
      });
    return () => {
      cancelled = true;
      requestGuard.current.invalidate();
      reconciliationGuard.current.invalidate();
      planGuard.current.invalidate();
      listingGuard.current.invalidate();
      boardGuard.current.invalidate();
      correctionGuard.current.invalidate();
    };
  }, []);

  async function load(next = page, query = skuSearch) {
    const ticket = requestGuard.current.begin(account.trim());
    setBusy(true);
    try {
      const result = await getNewProductWorkflows(ticket.account, next, {
        status: mode === "tracking" ? "approved_draft" : undefined,
        sku: query,
      });
      if (!requestGuard.current.isCurrent(ticket)) return;
      if (result.items.some(row => row.source_account_ref !== ticket.account)) {
        throw new Error("后端返回跨账户记录，已拒绝展示");
      }
      setData(result);
      setPage(next);
      void loadPlans(1);
      void loadDashboard();
      void loadCorrections();
    } catch (error) {
      if (requestGuard.current.isCurrent(ticket)) {
        api.error(error instanceof Error ? error.message : "读取真实数据失败");
      }
    } finally {
      if (requestGuard.current.isCurrent(ticket)) setBusy(false);
    }
  }

  async function loadListingCandidates(next = listingPage, query = skuSearch) {
    if (!account.trim()) return;
    const ticket = listingGuard.current.begin(account.trim());
    setListingBusy(true);
    try {
      const result = await getNewProductListingCandidates(ticket.account, next, { sku: query });
      if (!listingGuard.current.isCurrent(ticket)) return;
      if (
        result.source_account_ref !== ticket.account ||
        result.selection_mode !== "all_listings_pending_new_product_tag" ||
        result.items.some(item => item.source_account_ref !== ticket.account)
      ) {
        throw new Error("Listing 候选数据来源或账户不一致");
      }
      setListingData(result);
      setListingPage(next);
    } catch (error) {
      if (listingGuard.current.isCurrent(ticket)) {
        api.error(error instanceof Error ? error.message : "读取 Listing 候选商品失败");
      }
    } finally {
      if (listingGuard.current.isCurrent(ticket)) setListingBusy(false);
    }
  }

  async function loadPlans(next = planPage) {
    const ticket = planGuard.current.begin(account.trim());
    try {
      const result = await getIndependentNewProductPlans(ticket.account, next);
      if (!planGuard.current.isCurrent(ticket)) return;
      if (result.items.some(plan => plan.source_account_ref !== ticket.account)) {
        throw new Error("采购计划账户不一致，已拒绝展示");
      }
      setPlanData(result);
      setPlanPage(next);
    } catch (error) {
      if (planGuard.current.isCurrent(ticket)) {
        api.error(error instanceof Error ? error.message : "独立新品计划读取失败");
      }
    }
  }

  async function inspectPlan(row: NewProductPurchasePlan) {
    if (row.source_account_ref !== account.trim()) {
      api.error("当前独立计划账户不一致");
      return;
    }
    const ticket = planGuard.current.begin(row.source_account_ref);
    try {
      const result = await getIndependentNewProductPlan(row.id);
      if (!planGuard.current.isCurrent(ticket)) return;
      if (result.source_account_ref !== ticket.account) {
        throw new Error("跨账户独立计划详情已拒绝展示");
      }
      setPlanDetail(result);
    } catch (error) {
      if (planGuard.current.isCurrent(ticket)) {
        api.error(error instanceof Error ? error.message : "独立计划详情读取失败");
      }
    }
  }

  async function loadDashboard() {
    if (!account.trim()) return;
    const ticket = boardGuard.current.begin(account.trim());
    try {
      const next = await getNewProductDashboard(ticket.account);
      if (!boardGuard.current.isCurrent(ticket)) return;
      if (next.account !== ticket.account) throw new Error("正式看板账户校验失败");
      setDashboard(next);
    } catch (error) {
      if (boardGuard.current.isCurrent(ticket)) {
        api.error(error instanceof Error ? error.message : "真实看板读取失败");
      }
    }
  }

  async function loadCorrections(nextPage = 1) {
    if (!account.trim()) return;
    const ticket = correctionGuard.current.begin(account.trim());
    try {
      const result = await getNewProductScoreCorrections(ticket.account, nextPage);
      if (!correctionGuard.current.isCurrent(ticket)) return;
      if (result.items.some(item => item.source_account_ref !== ticket.account)) {
        throw new Error("评分修正账户范围不一致");
      }
      setCorrections(result);
      setCorrectionPage(nextPage);
    } catch (error) {
      if (correctionGuard.current.isCurrent(ticket)) {
        api.error(error instanceof Error ? error.message : "修正记录读取失败");
      }
    }
  }

  async function loadRuleHistory() {
    try {
      const [current, history] = await Promise.all([
        getNewProductRules(),
        getNewProductRulesHistory(),
      ]);
      setRules({
        ...current,
        rule_json: current.rule_json ?? {
          weights: { market: 15, order: 30, ads: 20, profit: 25, trust: 10 },
          success_days: 60, min_sales: 200, min_margin: 0, max_acos: 35,
        },
      });
      setRuleHistory(history);
    } catch (error) {
      api.error(error instanceof Error ? error.message : "草稿规则历史读取失败");
    }
  }

  async function saveDraftRules() {
    if (!canConfigure || !rules?.rule_json || ruleReason.trim().length < 5) {
      api.warning("需要配置权限、草稿规则和至少5字的变更说明");
      return;
    }
    if (Object.values(rules.rule_json.weights).reduce((sum, weight) => sum + weight, 0) !== 100) {
      api.warning("五维权重之和必须为100%");
      return;
    }
    setRuleSaving(true);
    try {
      await updateNewProductDraftRules({
        ...rules.rule_json, expected_version: rules.version, reason: ruleReason,
      });
      await loadRuleHistory();
      setRuleReason("");
      api.success("草稿规则版本已记录，未自动成为正式评分依据");
    } catch (error) {
      api.error(error instanceof Error ? error.message : "规则版本提交失败");
    } finally {
      setRuleSaving(false);
    }
  }

  async function inspectMetrics(row: NewProductWorkflowRecord) {
    if (row.source_account_ref !== account.trim()) {
      api.error("当前数据账户不一致，已拒绝读取");
      return;
    }
    const ticket = requestGuard.current.begin(row.source_account_ref);
    setBusy(true);
    try {
      const result = await getNewProductMetrics(row.sku_identity_id);
      if (!requestGuard.current.isCurrent(ticket)) return;
      if (result.account !== ticket.account) {
        throw new Error("经营指标账户与当前选择不一致，已拒绝展示");
      }
      setMetricData(result);
    } catch (error) {
      if (requestGuard.current.isCurrent(ticket)) {
        api.error(error instanceof Error ? error.message : "经营数据读取失败");
      }
    } finally {
      if (requestGuard.current.isCurrent(ticket)) setBusy(false);
    }
  }

  async function inspectReconciliation(row: NewProductWorkflowRecord) {
    if (row.source_account_ref !== account.trim()) {
      api.error("对账账户与当前选择不一致");
      return;
    }
    const ticket = reconciliationGuard.current.begin(row.source_account_ref);
    setReconcileBusy(true);
    try {
      const report = await getNewProductReconciliation(row.sku_identity_id, 30);
      if (!reconciliationGuard.current.isCurrent(ticket)) return;
      if (report.account !== ticket.account || report.sku !== row.sku) {
        throw new Error("对账记录与当前账户或SKU不一致，已拒绝展示");
      }
      setReconciliation(report);
    } catch (error) {
      if (reconciliationGuard.current.isCurrent(ticket)) {
        api.error(error instanceof Error ? error.message : "来源对账查询失败");
      }
    } finally {
      if (reconciliationGuard.current.isCurrent(ticket)) setReconcileBusy(false);
    }
  }

  function open(row: NewProductWorkflowRecord, nextAction: Action) {
    setRecord(row);
    setCorrectionRecord(null);
    setAction(nextAction);
    setDraft({ reason: "" });
  }

  function openCorrectionDecision(item: NewProductScoreCorrection) {
    setRecord(null);
    setCorrectionRecord(item);
    setAction("correction-decision");
    setDraft({ reason: "" });
  }

  async function submit() {
    if (!record && !correctionRecord) return;
    if (draft.reason.trim().length < 5) {
      api.warning("原因至少填写5个字");
      return;
    }
    const version = record?.row_version ?? 0;
    const id = record?.sku_identity_id ?? "";
    setBusy(true);
    setSubmitting(true);
    try {
      if (action === "correction-decision") {
        if (!canApprove || !correctionRecord || !draft.correctionDecision) {
          throw new Error("没有修正审核权限或决定为空");
        }
        await decideNewProductScoreCorrection(
          correctionRecord.id, draft.correctionDecision, draft.reason,
        );
      } else if (action === "correction") {
        if (!canScore || !draft.dimension || draft.score == null) {
          throw new Error("没有修正申请权限或维度和分数为空");
        }
        await requestNewProductScoreCorrection(
          id, version, draft.dimension, draft.score, draft.reason,
        );
      } else if (action === "market") {
        if (!canScore || draft.score == null) throw new Error("没有评分权限或评分为空");
        await saveMarketScore(id, version, draft.score, draft.reason);
      } else if (action === "request") {
        if (!canRequest || !draft.quantity) throw new Error("没有申请权限或数量为空");
        await requestNewProductPurchase(id, version, draft.quantity, draft.reason);
      } else if (action === "decision") {
        if (!canApprove || !draft.decision) throw new Error("没有审批权限或决定为空");
        await decideNewProductPurchase(id, version, draft.decision, draft.reason);
      } else if (action === "dates") {
        if (!canReview || !draft.arrivalDate || !draft.sellableDate) {
          throw new Error("没有日期确认权限或到货、可售日期不完整");
        }
        await verifyNewProductDates(id, version, draft.arrivalDate, draft.sellableDate, draft.reason);
      } else {
        if (!canReview || !draft.result) throw new Error("没有复盘权限或结果为空");
        await reviewNewProductLaunch(id, version, draft.result, draft.reason, draft.nextReview);
      }
      setRecord(null);
      setCorrectionRecord(null);
      api.success(action === "decision" && draft.decision === "approved_draft"
        ? "审批已记录，独立新品计划已创建（未执行采购）"
        : "已记录到新品工作流");
      await load(page);
    } catch (error) {
      api.error(error instanceof Error ? error.message : "提交失败");
    } finally {
      setBusy(false);
      setSubmitting(false);
    }
  }

  const statusLabels: Record<string, string> = {
    pending_market: "待市场评分", scored: "已评分",
    pending_purchase: "待采购审批", approved_draft: "独立计划已批准",
    rejected: "已驳回",
  };
  const trackingLabels: Record<string, string> = {
    not_in_pool: "未进入打品池", awaiting_sellable: "待确认可售",
    observing: "观察中", optimize: "需要优化", due_review: "待复盘",
  };
  const groupBoard = mode === "performance" ? "purchase_status" : "tracking_status";
  const groupNames = dashboard?.groups[groupBoard] ?? [];
  // Server filters before LIMIT/OFFSET, so tracking cannot hide approved SKUs
  // beyond the first page of unrelated new products.
  const visibleRows = data?.items ?? [];

  const listingColumns: ProColumns<NewProductListingCandidate>[] = [
    { title: "店铺", dataIndex: "store_name", width: 125,
      render: (_, row) => row.store_name || row.store_id },
    { title: "Item ID", dataIndex: "item_id", width: 140 },
    { title: "SKU", dataIndex: "local_sku", width: 150, render: value => value ?? "—" },
    { title: "MSKU", dataIndex: "msku", width: 150, render: value => value ?? "—" },
    { title: "商品名称", dataIndex: "title", ellipsis: true,
      render: (_, row) => row.title || row.local_name || "—" },
    { title: "类目", dataIndex: "category", width: 150, ellipsis: true },
    { title: "Listing 状态", dataIndex: "listing_status", width: 125,
      render: value => value ?? "—" },
    { title: "生命周期", dataIndex: "lifecycle_status", width: 125,
      render: value => value ?? "—" },
    { title: "7天销量", dataIndex: "sales_7d", width: 90 },
    { title: "14天销量", dataIndex: "sales_14d", width: 90 },
    { title: "30天销量", dataIndex: "sales_30d", width: 90 },
    { title: "可售库存", dataIndex: "available_quantity", width: 100,
      render: value => value ?? "—" },
    { title: "WFS 可售", dataIndex: "wfs_available_quantity", width: 100,
      render: value => value ?? "—" },
    { title: "上架时间", dataIndex: "listing_start_at_utc", width: 180,
      render: value => value ?? "—" },
    { title: "数据更新时间", dataIndex: "calculated_at", width: 190 },
  ];

  const columns: ProColumns<NewProductWorkflowRecord>[] = [
    { title: "SKU", dataIndex: "sku", width: 150 },
    { title: "商品名称", dataIndex: "product_name", ellipsis: true },
    { title: "类目", dataIndex: "category", width: 125 },
    { title: "开发人员", dataIndex: "developer", width: 125 },
    { title: "运营人员", dataIndex: "operator", width: 125 },
    { title: "数据更新时间", dataIndex: "product_observed_at", width: 185 },
    { title: "已确认到货日", dataIndex: "arrival_date", width: 130, render: v => v ?? "—" },
    { title: "已确认可售日", dataIndex: "sellable_date", width: 130, render: v => v ?? "—" },
    { title: "账户", dataIndex: "source_account_ref", width: 130 },
    { title: "市场评分", dataIndex: "market_score", width: 95, render: v => v ?? "待评分" },
    { title: "打品阶段", width: 125, key: "tracking-stage",
      render: (_, row) => trackingLabels[row.tracking_status ?? "not_in_pool"] ?? "—" },
    { title: "复盘结果", dataIndex: "review_result", width: 115,
      render: v => v === "optimize" ? "需要优化" : v === "observe" ? "继续观察" : "—" },
    { title: "申请采购量", dataIndex: "purchase_request_qty", width: 110, render: v => v ?? "—" },
    { title: "独立计划编号", dataIndex: "plan_number", width: 300,
      render: v => v ?? "—" },
    { title: "业务状态", dataIndex: "status", width: 130, render: v => <StatusTagCell label={({
      pending_market: "待市场评分", scored: "已评分", pending_purchase: "待审核",
      approved_draft: "草稿已批准", rejected: "已驳回",
    } as Record<string, string>)[String(v ?? "pending_market")] ?? String(v ?? "待市场评分")} color={v === "approved_draft" ? "success" : v === "rejected" ? "error" : "processing"}/> },
    { title: "操作", key: "actions", width: 345, render: (_, row) => {
      const state = row.status ?? "pending_market";
      return <Space wrap size={0}><Button type="link" onClick={() => void inspectMetrics(row)}>经营指标</Button>
        <Button type="link" loading={reconcileBusy}
          onClick={() => void inspectReconciliation(row)}>来源对账</Button>
        {canScore && state === "pending_market" && <Button type="link" onClick={() => open(row, "market")}>市场评分</Button>}
        {canScore && (state === "scored" || state === "pending_purchase" || state === "rejected")
          && <Button type="link" onClick={() => open(row, "correction")}>评分修正</Button>}
        {canRequest && (state === "scored" || state === "rejected") && <Button type="link" onClick={() => open(row, "request")}>采购申请</Button>}
        {canApprove && state === "pending_purchase" && <Button type="link" onClick={() => open(row, "decision")}>草稿审批</Button>}
        {canReview && state === "approved_draft" && <Button type="link" onClick={() => open(row, "dates")}>确认到货/可售日</Button>}
        {canReview && state === "approved_draft" && <Button type="link" onClick={() => open(row, "review")}>复盘</Button>}
      </Space>;
    } },
  ];

  const planColumns: ProColumns<NewProductPurchasePlan>[] = [
    { title: "独立计划编号", dataIndex: "plan_number", width: 330 },
    { title: "SKU", dataIndex: "sku", width: 160 },
    { title: "审批数量", dataIndex: "quantity", width: 100 },
    { title: "审核人", dataIndex: "approved_by", width: 130 },
    { title: "审核意见", dataIndex: "approval_note", ellipsis: true },
    { title: "创建时间", dataIndex: "created_at", width: 180 },
    { title: "执行状态", key: "execution_status", width: 120,
      render: () => <StatusTagCell label="未执行采购" color="warning" /> },
    { title: "操作", key: "action", width: 100,
      render: (_, row) => <Button type="link" onClick={() => void inspectPlan(row)}>详情</Button> },
  ];

  const correctionColumns: ProColumns<NewProductScoreCorrection>[] = [
    { title: "SKU 身份", dataIndex: "sku_identity_id", width: 280 },
    { title: "维度", dataIndex: "dimension", width: 90,
      render: v => ({
        order: "出单速度", ads: "广告有效性", profit: "利润空间",
        trust: "数据可信度",
      } as Record<string, string>)[String(v)] ?? String(v) },
    { title: "原始分", dataIndex: "from_score", width: 95 },
    { title: "申请分", dataIndex: "requested_score", width: 95 },
    { title: "原因", dataIndex: "reason", ellipsis: true },
    { title: "状态", dataIndex: "status", width: 110,
      render: v => v === "approved" ? "已批准（仅预估）"
        : v === "rejected" ? "已驳回" : "待审核" },
    { title: "操作", key: "action", width: 105,
      render: (_, item) => item.status === "pending" && canApprove
        ? <Button type="link" onClick={() => openCorrectionDecision(item)}>审核</Button>
        : "—" },
  ];

  return <Card title={mode === "performance" ? "真实新品表现" : "真实打品跟踪"} size="small">
    {context}
    <Typography.Paragraph type="secondary">此入口读取真实 SKU 和独立新品记录。人工批准后原子化生成独立计划；计划不会执行采购，也不写入 PMC。</Typography.Paragraph>
    {accountsError && <Alert type="error" showIcon message={accountsError} />}
    <Space wrap style={{ marginBottom: 16 }}>
      <Select style={{ width: 250 }} placeholder="选择有权限的数据账户"
        disabled={submitting} value={account || undefined}
        showSearch optionFilterProp="label" options={accounts.map(value => ({ label: value, value }))}
        onChange={value => {
          requestGuard.current.selectAccount(value);
          reconciliationGuard.current.selectAccount(value);
          planGuard.current.selectAccount(value);
          listingGuard.current.selectAccount(value);
          boardGuard.current.selectAccount(value);
          correctionGuard.current.selectAccount(value);
          setAccount(value);
          setDashboard(null);
          setCorrections(null);
          setCorrectionRecord(null);
          setRules(null);
          setRuleHistory(null);
          setData(null);
          setListingData(null);
          setListingPage(1);
          setListingBusy(false);
          setPlanData(null);
          setPlanDetail(null);
          setPlanPage(1);
          setCorrectionPage(1);
          setSkuSearchInput("");
          setSkuSearch("");
          setMetricData(null);
          setReconciliation(null);
          setRecord(null);
          setPage(1);
          setBusy(false);
        }} />
      <Input.Search
        style={{ width: 255 }}
        placeholder="搜索 SKU（真实数据）"
        value={skuSearchInput}
        allowClear
        disabled={!account.trim() || submitting}
        onChange={event => setSkuSearchInput(event.target.value)}
        onSearch={value => {
          const query = value.trim();
          setSkuSearch(query);
          void load(1, query);
          if (mode === "performance") void loadListingCandidates(1, query);
        }}
      />
      <Button type="primary" loading={busy} disabled={!account.trim()}
        onClick={() => {
          void load(1);
          if (mode === "performance") void loadListingCandidates(1);
        }}>刷新真实数据</Button>
    </Space>
    <Tabs activeKey={panelTab} onChange={next => {
      setPanelTab(next as PanelTab);
      if (next === "rules") void loadRuleHistory();
      if (next === "listing" && !listingData && account.trim()) void loadListingCandidates(1);
    }} items={[
      ...(mode === "performance" ? [{ key: "listing", label: "Listing 商品（全量测试）" }] : []),
      { key: "overview", label: mode === "performance" ? "真实新品看板" : "真实打品看板" },
      { key: "records", label: "真实 SKU 明细" },
      { key: "plans", label: "独立新品计划" },
      { key: "corrections", label: "评分修正审核" },
      { key: "rules", label: "草稿规则与历史" },
    ]} />
    {panelTab === "listing" && mode === "performance" && <>
      <Alert type="info" showIcon style={{ marginBottom: 12 }}
        message="Listing 全量测试：暂不按新品标签筛选，此列表包含非新品商品。"
        description="按账户、店铺、Item ID 读取 Listing 管理的实际商品；只读、不写回、不删除，不自动建立新品采购或打品审批。" />
      <ReportTableShell label="Listing 商品测试候选">
        <ProTable<NewProductListingCandidate> rowKey="id"
          dataSource={listingData?.items ?? []} columns={listingColumns}
          loading={listingBusy} options={false} search={false}
          tableAlertRender={false} scroll={{ x: 1800 }}
          pagination={{ current: listingPage, pageSize: 50,
            total: listingData?.total ?? 0, showSizeChanger: false,
            onChange: next => void loadListingCandidates(next) }} />
      </ReportTableShell>
    </>}
    {panelTab === "overview" && <>
      <Space wrap style={{ marginBottom: 12 }}>
        <Card size="small"><Typography.Text type="secondary">实际 SKU 数量</Typography.Text>
          <Typography.Title level={4}>{dashboard?.total ?? "—"}</Typography.Title></Card>
        <Card size="small"><Typography.Text type="secondary">正式评级 / 成功率</Typography.Text>
          <Typography.Title level={5}>尚未批准</Typography.Title></Card>
        <Card size="small"><Typography.Text type="secondary">账户</Typography.Text>
          <Typography.Text>{dashboard?.account ?? "尚未加载"}</Typography.Text></Card>
      </Space>
      <Alert type="info" showIcon style={{ marginBottom: 12 }}
        message="此看板只展示数据库真实分类与状态数量；尚无已批准评分阈值，不生成虚假的正式等级或打品成功率。" />
      <ReportTableShell label="真实业务状态分布">
        <ProTable rowKey="name" search={false} options={false} pagination={false}
          dataSource={groupNames} columns={[
            { title: "业务阶段", dataIndex: "name",
              render: (_, item) => groupBoard === "purchase_status"
                ? (statusLabels[item.name] ?? item.name)
                : (trackingLabels[item.name] ?? item.name) },
            { title: "SKU 数", dataIndex: "count" },
          ]} />
      </ReportTableShell>
      <ReportTableShell label="真实类目 / 负责人分布">
        <ProTable rowKey="id" search={false} options={false} pagination={false}
          dataSource={(["category", "developer", "operator"] as const).flatMap(kind =>
            (dashboard?.groups[kind] ?? []).map(row => ({
              id: kind + ":" + row.name, kind, ...row,
            })),
          )}
          columns={[
            { title: "分组", dataIndex: "kind",
              render: value => ({ category: "类目", developer: "开发人员", operator: "运营人员" } as Record<string,string>)[String(value)] },
            { title: "名称", dataIndex: "name" },
            { title: "SKU 数", dataIndex: "count" },
          ]} />
      </ReportTableShell>
    </>}
    {panelTab === "records" && <ReportTableShell label="真实新品工作流列表">
      <ProTable<NewProductWorkflowRecord> rowKey="sku_identity_id" dataSource={visibleRows} columns={columns} loading={busy}
        options={false} search={false} tableAlertRender={false} scroll={{ x: 1450 }} pagination={{ current: page, pageSize: 50, total: data?.total ?? 0,
          onChange: next => void load(next), showSizeChanger: false }} />
    </ReportTableShell>}
    {panelTab === "plans" && <ReportTableShell label="独立新品计划（已批准，尚未执行采购）">
      <ProTable<NewProductPurchasePlan> rowKey="id" dataSource={planData?.items ?? []}
        columns={planColumns} options={false} search={false} tableAlertRender={false}
        scroll={{ x: 1200 }} pagination={{ current: planPage, pageSize: 50,
          total: planData?.total ?? 0, showSizeChanger: false,
          onChange: next => void loadPlans(next) }} />
    </ReportTableShell>}
    {panelTab === "corrections" && <ReportTableShell label="评分修正申请和审核（仅预估）">
      <ProTable<NewProductScoreCorrection> rowKey="id"
        dataSource={corrections?.items ?? []} columns={correctionColumns}
        options={false} search={false} pagination={{
          current: correctionPage, pageSize: 50,
          total: corrections?.total ?? 0, showSizeChanger: false,
          onChange: next => void loadCorrections(next),
        }}
        scroll={{ x: 1100 }} />
    </ReportTableShell>}
    {panelTab === "rules" && <>
      <Alert type="warning" showIcon style={{ marginBottom: 12 }}
        message="规则版本仍为草稿，不会自动发布正式 S/A/B/C/D 等级或代替经营数据口径验收。" />
      <Descriptions size="small" column={2} items={[
        { key: "bands", label: "已确认等级采购区间", span: 2,
          children: rules?.confirmed_purchase_bands
            ? Object.entries(rules.confirmed_purchase_bands).map(
              ([grade, range]) => `${grade}级 ${range[0]}–${range[1]}`,
            ).join("、")
            : "S 400–600、A 300–500、B 200–400、C 150–250、D/Pass 不采购" },
        { key: "formal", label: "正式评分启用状态", span: 2,
          children: rules?.formal_policy?.status === "blocked"
            ? "待批准（禁止自动评级和正式采购建议）"
            : "未取得完整批准证据" },
        { key: "version", label: "当前草稿版本", children: rules ? "V" + rules.version : "未加载" },
        { key: "author", label: "最近修改人", children: rules?.actor ?? "—" },
        { key: "reason", label: "修改依据", children: rules?.reason ?? "—" },
        { key: "history", label: "历史版本数", children: ruleHistory?.total ?? "—" },
      ]} />
      <ReportTableShell label="已保存的规则历史">
        <ProTable rowKey="version" dataSource={ruleHistory?.items ?? []}
          options={false} search={false} pagination={false}
          columns={[
            { title: "版本", dataIndex: "version", width: 80 },
            { title: "修改人", dataIndex: "actor", width: 120 },
            { title: "变更说明", dataIndex: "reason" },
            { title: "创建时间", dataIndex: "created_at", width: 190 },
          ]} />
      </ReportTableShell>
      {canConfigure && rules?.rule_json && <>
        <Typography.Title level={5} style={{ marginTop: 12 }}>
          草稿规则编辑（不会自动发布正式评级）
        </Typography.Title>
        <Space wrap style={{ marginBottom: 12 }}>
          {(["market", "order", "ads", "profit", "trust"] as const).map(key => (
            <div key={key} style={{ width: 126 }}>
              <Typography.Text type="secondary">{({
                market: "市场", order: "出单", ads: "广告",
                profit: "利润", trust: "可信度",
              } as const)[key]}权重</Typography.Text>
              <InputNumber min={0} max={100} precision={0} style={{ width: "100%" }}
                value={rules.rule_json!.weights[key]}
                onChange={v => setRules(current => current?.rule_json
                  ? { ...current, rule_json: {
                    ...current.rule_json, weights: {
                      ...current.rule_json.weights, [key]: v ?? 0,
                    },
                  } } : current)} />
            </div>
          ))}
          <div style={{ width: 126 }}>
            <Typography.Text type="secondary">观察期</Typography.Text>
            <Select style={{ width: "100%" }} value={rules.rule_json.success_days}
              options={[30, 60, 90].map(v => ({ value: v, label: v + "天" }))}
              onChange={v => setRules(current => current?.rule_json
                ? { ...current, rule_json: {
                  ...current.rule_json, success_days: v as 30 | 60 | 90,
                } } : current)} />
          </div>
          {(["min_sales", "min_margin", "max_acos"] as const).map(key => (
            <div key={key} style={{ width: 130 }}>
              <Typography.Text type="secondary">{({
                min_sales: "最低销量", min_margin: "最低利润率",
                max_acos: "最高ACOS",
              } as const)[key]}</Typography.Text>
              <InputNumber style={{ width: "100%" }} precision={key === "min_sales" ? 0 : 2}
                min={key === "min_margin" ? -100 : key === "min_sales" ? 1 : 0}
                max={key === "min_sales" ? undefined : 100}
                value={rules.rule_json![key]}
                onChange={v => setRules(current => current?.rule_json
                  ? { ...current, rule_json: { ...current.rule_json, [key]: v ?? 0 } }
                  : current)} />
            </div>
          ))}
        </Space>
        <Input.TextArea rows={2} value={ruleReason} onChange={e => setRuleReason(e.target.value)}
          placeholder="草稿规则变更说明（至少5字）" style={{ marginTop: 12 }} />
        <Button type="primary" loading={ruleSaving} onClick={() => void saveDraftRules()}>
          保存当前草稿规则新版本（不发布正式评分）
        </Button>
      </>}
    </>}
    <Modal title="独立新品计划详情（未执行采购）" open={planDetail !== null}
      onCancel={() => setPlanDetail(null)} footer={null} width={710}>
      {planDetail && <>
        <Descriptions column={2} size="small" bordered items={[
          { key: "number", label: "计划编号", span: 2, children: planDetail.plan_number },
          { key: "qty", label: "审批数量", children: planDetail.quantity },
          { key: "account", label: "所属账户", children: planDetail.source_account_ref },
          { key: "actor", label: "审核人", children: planDetail.approved_by },
          { key: "version", label: "批准时规则版本", children: planDetail.rule_version },
          { key: "note", label: "审核意见", span: 2, children: planDetail.approval_note },
          { key: "reason", label: "采购申请依据", span: 2,
            children: planDetail.snapshot_json.purchase_reason },
          { key: "snapshot", label: "评分证据", children: "正式评分尚未认证" },
          { key: "execution", label: "执行状态", children: "未执行采购（非 PMC 采购单）" },
        ]} />
      </>}
    </Modal>
    <Modal title="真实数据来源对账（只读）" open={reconciliation !== null}
      footer={null} width={840} onCancel={() => setReconciliation(null)}>
      {reconciliation && <>
        <Alert type={reconciliation.status === "blocked" ? "warning" : "info"} showIcon
          message={reconciliation.status === "blocked"
            ? "实际来源存在未解决问题，禁止用于正式评分与采购决策"
            : "派生表初步一致；未证明上游发布完整性，不能视为生产实数验收"}
          style={{ marginBottom: 12 }} />
        <Descriptions size="small" column={2} bordered items={[
          { key: "account", label: "来源账户", children: reconciliation.account },
          { key: "sku", label: "SKU", children: reconciliation.sku },
          { key: "days", label: "业务日窗口", children:
            `${reconciliation.window.from} 至 ${reconciliation.window.to_exclusive}（不含）` },
          { key: "listing", label: "Listing / 店铺 / Item", children:
            `${reconciliation.mapping.listing_rows} / ${reconciliation.mapping.stores} / ${reconciliation.mapping.item_ids}` },
          { key: "salesDays", label: "销售日覆盖", children:
            `${reconciliation.sales.mart_days} / ${reconciliation.window.days}` },
          { key: "zeroDays", label: "已记录零销量天数", children:
            reconciliation.sales.recorded_zero_days },
          { key: "adDays", label: "广告事实日覆盖", children:
            `${reconciliation.ads.observed_days} / ${reconciliation.window.days}` },
          { key: "adMap", label: "广告映射匹配 / 未匹配", children:
            `${reconciliation.ads.matched_rows} / ${reconciliation.ads.unmatched_rows}` },
          { key: "currency", label: "广告费用 / 归因销售币种", children:
            `${reconciliation.ads.spend_currency ?? "未知"} / ${reconciliation.ads.attributed_currency ?? "未知"}` },
          { key: "finance", label: "财务可见性", children:
            reconciliation.finance.visibility === "authorized" ? "已授权" : "受限" },
          { key: "diff", label: "销售额汇总差异", children:
            reconciliation.finance.visibility === "authorized"
              ? (reconciliation.finance.sales_difference ?? "无法核对") : "权限不足" },
          { key: "roas", label: "广告 ROAS（非 ROI）", children:
            reconciliation.finance.visibility === "authorized"
              ? (reconciliation.finance.roas ?? "未知") : "权限不足" },
          { key: "readiness", label: "上架30天提醒", children:
            reconciliation.market_review_readiness.status === "ready_for_market_review"
              ? "已满30天" : "待达到或核验上架30天" },
          { key: "formal", label: "正式评分等级", children: "等待规则与实际对账批准" },
        ]} />
        <Typography.Paragraph strong style={{ marginTop: 12 }}>
          数据核对问题（{reconciliation.issues.length}项）
        </Typography.Paragraph>
        {reconciliation.issues.length
          ? <Space size={[4, 4]} wrap>{reconciliation.issues.map(code =>
            <Typography.Text code key={code}>{code}</Typography.Text>)}</Space>
          : <Typography.Text>未发现派生数据异常，但上游零销量日发布完整性仍未认证。</Typography.Text>}
        <Alert type="warning" showIcon style={{ marginTop: 12 }}
          message="没有来源同步任务的日期覆盖证明时，缺失记录不能解释为销量零；本查询不修改数据库。" />
      </>}
    </Modal>
    <Modal title="真实经营数据及评分依据" open={metricData !== null} footer={null}
      onCancel={() => setMetricData(null)} width={1120}>
      {metricData && <NewProductMetricsPanel metrics={metricData} />}
    </Modal>
    <Modal title={action === "correction" ? "申请修正预估评分"
      : action === "correction-decision" ? "审核评分修正"
      : action === "market" ? "市场评分" : action === "request" ? "申请采购" :
      action === "decision" ? "审批采购草稿" : action === "dates" ? "确认打品观察起点" : "打品复盘"} open={!!record || !!correctionRecord} confirmLoading={busy}
      onCancel={() => { setRecord(null); setCorrectionRecord(null); }}
      onOk={() => void submit()} okText="保存">
      <Form layout="vertical">
        <Typography.Paragraph>{record?.sku} · {record?.product_name}</Typography.Paragraph>
        {action === "correction" && <>
          <Form.Item label="需要修正的预估维度" required>
            <Select value={draft.dimension}
              onChange={value => setDraft(s => ({ ...s, dimension: value }))}
              options={[
                { value: "order", label: "出单速度" },
                { value: "ads", label: "广告有效性" },
                { value: "trust", label: "数据可信度" },
              ]} />
          </Form.Item>
          <Form.Item label="调整后分数（仅预估，0–10）" required>
            <InputNumber min={0} max={10} precision={2} value={draft.score}
              onChange={value => setDraft(s => ({ ...s, score: value ?? undefined }))}
              style={{ width: "100%" }} />
          </Form.Item>
        </>}
        {action === "correction-decision" && <>
          <Typography.Paragraph>
            维度：{correctionRecord?.dimension} · 原始分 {correctionRecord?.from_score}
            · 申请分 {correctionRecord?.requested_score}
          </Typography.Paragraph>
          <Form.Item label="审核决定" required>
            <Select value={draft.correctionDecision}
              onChange={value => setDraft(s => ({ ...s, correctionDecision: value }))}
              options={[{ label: "批准预估修正", value: "approved" },
                { label: "驳回", value: "rejected" }]} />
          </Form.Item>
        </>}
        {action === "market" && <Form.Item label="市场评分（0–10）" required>
          <InputNumber min={0} max={10} precision={0} value={draft.score}
            onChange={value => setDraft(s => ({ ...s, score: value ?? undefined }))} style={{ width: "100%" }} />
        </Form.Item>}
        {action === "request" && <Form.Item label="申请采购量" required>
          <InputNumber min={1} precision={0} value={draft.quantity}
            onChange={value => setDraft(s => ({ ...s, quantity: value ?? undefined }))} style={{ width: "100%" }} />
        </Form.Item>}
        {action === "decision" && <Form.Item label="审批决定" required>
          <Select value={draft.decision} onChange={value => setDraft(s => ({ ...s, decision: value }))}
            options={[{ label: "批准并生成独立新品计划（不执行采购）", value: "approved_draft" },
              { label: "驳回", value: "rejected" }]} />
        </Form.Item>}
        {action === "dates" && <>
          <Form.Item label="实际到货日" required>
            <DatePicker style={{ width: "100%" }} value={draft.arrivalDate ? dayjs(draft.arrivalDate) : null}
              onChange={value => setDraft(s => ({ ...s, arrivalDate: value?.format("YYYY-MM-DD") }))} />
          </Form.Item>
          <Form.Item label="实际可售日" required>
            <DatePicker style={{ width: "100%" }} value={draft.sellableDate ? dayjs(draft.sellableDate) : null}
              onChange={value => setDraft(s => ({ ...s, sellableDate: value?.format("YYYY-MM-DD") }))} />
          </Form.Item>
          <Alert type="info" showIcon message="必须在理由中填写可核对的到货和可售来源；以两日期中较晚者作为观察期起点。" />
        </>}
        {action === "review" && <>
          <Form.Item label="复盘状态" required>
            <Select value={draft.result} onChange={value => setDraft(s => ({ ...s, result: value }))}
              options={[{ label: "继续观察", value: "observe" }, { label: "需要优化", value: "optimize" }]} />
          </Form.Item>
          {draft.result === "optimize" && <Form.Item label="下次复核日期（YYYY-MM-DD）" required>
            <DatePicker style={{ width: "100%" }} value={draft.nextReview ? dayjs(draft.nextReview) : null}
              onChange={value => setDraft(s => ({ ...s, nextReview: value?.format("YYYY-MM-DD") }))} />
          </Form.Item>}
        </>}
        <Form.Item label="理由（至少5字）" required>
          <Input.TextArea rows={3} value={draft.reason}
            onChange={event => setDraft(s => ({ ...s, reason: event.target.value }))} />
        </Form.Item>
      </Form>
      <Alert type="info" showIcon message="审批通过仅在新品模块生成独立计划，不会执行采购、不接 PMC；正式评分分档仍待批准。" />
    </Modal>
  </Card>;
}
