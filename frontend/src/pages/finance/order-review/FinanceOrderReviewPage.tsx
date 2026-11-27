/**
 * 财务 · 订单审核（结算利润 V3 PR-OR，PRP §7A）：
 * - 粒度：期（= 回款对账的期）× 店铺 × 订单行；只显示已出账单的期，2026-10-01 起。
 * - 审产品成本三项：采购价、头程、尾程（WFS 订单尾程 = 结算单配送费，只展示不入货本）。
 * - 待审原因 8 种；录成本按 MSKU × 发货单（或出库单）；初审 → 终审，退回要原因，同一人不能既初审又终审。
 * 全部读写 /api/finance/order-review，没有本地预览数据。
 */
import { ReloadOutlined, SearchOutlined, SettingOutlined } from "@ant-design/icons";
import type { ProColumns } from "@ant-design/pro-components";
import { Alert, Button, Dropdown, Input, Modal, Space, Tag, Tooltip, Typography, message } from "antd";
import { useQuery } from "@tanstack/react-query";
import { useMemo, useState, type ReactNode } from "react";
import { MoneyCell } from "@/components/report-table/cells";
import ResetButton from "@/components/report-table/ResetButton";
import RuntimeColumnConfigDrawer from "@/components/report-table/RuntimeColumnConfigDrawer";
import PageShell from "@/components/page/PageShell";
import type { NavigationPage } from "@/config/navigation";
import { fetchCurrentUser } from "@/pages/auth/authApi";
import FinanceBoardFrame from "@/pages/finance/FinanceBoardFrame";
import { hasPermission } from "@/shared/permissions/mockAccess";
import BoardTable from "@/pages/finance/payout-recon/BoardTable";
import HelpButton, { type HelpSection } from "@/pages/finance/payout-recon/HelpButton";
import ReportFacetSelect from "@/shared/report-filters";
import CostEntryDrawer from "./CostEntryDrawer";
import ExactSearchModal from "./ExactSearchModal";
import {
  BATCH_CONFIRM_THRESHOLD, CHANGED_AFTER_REVIEW, DEFAULT_FILTERS, KIND_TEXT, LOOKUP_LABEL, PERMISSIONS, REASON_TEXT, SOURCE_KIND_TEXT, STATUS_TEXT, errorText, n, postRecalc, postReview,
  useLines, useOrderReviewRefresh, usePeriods, useTransactionTypes,
  type ApiLine, type ApiMoney, type ApiPeriod, type LineFilters, type LineKind, type LookupKind, type Reason, type ReviewStatus,
} from "./orderReviewApi";
import { OR_COLUMN_GROUPS, OR_DEFAULT_KEYS, OR_FIXED_KEYS, readOrderReviewColumns, writeOrderReviewColumns } from "./orderReviewColumns";
import "@/pages/finance/payout-recon/payout-recon.css";

const HELP: HelpSection[] = [
  { title: "这页做什么", body: "按期（= 回款对账的期，一期一个账单日）审每一笔订单行的产品成本：采购价、头程、尾程。收入、佣金、WFS 配送费等从沃尔玛账单带出来只展示，不审。只显示已出账单的期，2026-10-01 起。" },
  { title: "货本怎么来", body: "订单行按订单号 + GTIN 查领星成本计价流水，定位到发货单；发货单明细里的采购价、出库头程、头程费用、税就是货本（单位成本 = 四项之和）。WFS 订单的尾程 = 结算单配送费，只展示、不计入货本；自发货订单的尾程 = 销售出库单物流费用，计入货本。" },
  { title: "自动通过", body: "发货单来源、物流商不是 WFS 承运（按设置里的 WFS 承运商清单）、发货单明细四项齐全且之和等于单位成本、币种人民币、商品有负责人 → 自动通过，不用人审。" },
  { title: "待审原因", body: "WFS 承运货件（确认头程）、自发货（录采购价 / 头程 / 尾程）、固定值、最近签收成本、没有成本来源、发货单明细不完整、商品无负责人、同期卖出又取消。一行可以有多个原因。" },
  { title: "录成本", body: "点行上的「录成本」：范围 = MSKU × 发货单；自发货订单和流水没覆盖的差额是 MSKU × 平台订单号（一单拆多张出库单也只录一次）。一次录入覆盖范围内所有订单行（含跨期）。自发货尾程按出库单里本 MSKU 的分摊运费预填，找不到就留空待手填。「确认」= 接受领星发货单的值；「修正」= 改值，原因必填，系统不回写领星，请同时去领星改。录入后不自动通过，进待审 → 初审 → 终审；撤销录入退回待审。批量审核 20 行以上要二次确认。" },
  { title: "审核", body: "初审、终审分开授权；同一人不能既初审又终审；退回要写原因；终审通过后要先撤销终审才能改。自动通过的行不用审。" },
  { title: "重算", body: "账单、发货单、出库单同步后会自动重算受影响的期；也可以点「重算」。内容没变不写新版本；已初审 / 终审的行计算值变了不自动改状态，版本号 +1 并红字提示「审核后数据有变」，请撤销后重审。已结账的月不重算。" },
];

const EMPTY = "—";
const usd = (v: ApiMoney | null) => <MoneyCell value={n(v)} />;
const cny = (v: ApiMoney | null) => <MoneyCell value={n(v)} currency="¥" />;
const period = (p: ApiPeriod) => `${p.report_date}${p.period_start_date ? `（${p.period_start_date.slice(5)}–${p.period_end_date?.slice(5) ?? ""}）` : ""}`;

function statusTag(line: ApiLine): ReactNode {
  const meta = STATUS_TEXT[line.review_status];
  const title = [
    line.first_reviewed_at ? `初审 ${line.first_reviewed_at.slice(0, 16).replace("T", " ")}` : null,
    line.final_reviewed_at ? `终审 ${line.final_reviewed_at.slice(0, 16).replace("T", " ")}` : null,
  ].filter(Boolean).join(" · ");
  return <Tooltip title={title || undefined}><Tag color={meta.color} bordered={false}>{meta.text}</Tag></Tooltip>;
}

function sourceCell(line: ApiLine): ReactNode {
  if (!line.cost_sources.length) return EMPTY;
  const parts = line.cost_sources.map((s) => {
    const ref = s.scope_ref?.split(":", 2)[1];
    return `${SOURCE_KIND_TEXT[s.kind] ?? s.kind}${ref ? ` ${ref}` : ""}${s.quantity ? ` ×${Number(s.quantity)}` : ""}`;
  });
  return <Tooltip title={parts.join("；")}><span>{parts.join("；")}</span></Tooltip>;
}

function Workbench({ periods }: { periods: ApiPeriod[] }) {
  const refresh = useOrderReviewRefresh();
  const [messageApi, holder] = message.useMessage();
  const [modal, modalHolder] = Modal.useModal();
  const me = useQuery({ queryKey: ["auth", "current-user"], queryFn: fetchCurrentUser, staleTime: 5 * 60 * 1000 });
  const can = useMemo(() => ({
    costEntry: hasPermission(me.data?.permissions, PERMISSIONS.costEntry),
    review1: hasPermission(me.data?.permissions, PERMISSIONS.review1),
    review2: hasPermission(me.data?.permissions, PERMISSIONS.review2),
    recalc: hasPermission(me.data?.permissions, PERMISSIONS.recalc),
  }), [me.data?.permissions]);
  const latest = periods[0]?.period_key;
  const [filters, setFilters] = useState<LineFilters>({ ...DEFAULT_FILTERS, periodKeys: latest ? [latest] : [] });
  const lines = useLines(filters);
  const types = useTransactionTypes();
  const [columnKeys, setColumnKeys] = useState<string[]>(readOrderReviewColumns);
  const [columnOpen, setColumnOpen] = useState(false);
  const [selected, setSelected] = useState<string[]>([]);
  const [entryLine, setEntryLine] = useState<ApiLine>();
  const [lookupKind, setLookupKind] = useState<LookupKind>();
  const [rejectOpen, setRejectOpen] = useState<"first" | "final">();
  const [rejectReason, setRejectReason] = useState("");
  const [busy, setBusy] = useState(false);

  const set = (patch: Partial<LineFilters>) => { setFilters((f) => ({ ...f, ...patch, page: 1 })); setSelected([]); };
  const rows = lines.data?.items ?? [];
  const selectedRows = rows.filter((r) => selected.includes(r.review_id));
  const stores = useMemo(() => Array.from(new Map(periods.map((p) => [p.store_id, p.store_name ?? p.store_id]))), [periods]);
  const periodOptions = useMemo(() => Array.from(new Map(periods.map((p) => [p.period_key, p])).values()), [periods]);
  const totals = useMemo(() => periods.filter((p) => !filters.periodKeys.length || filters.periodKeys.includes(p.period_key)).reduce((acc, p) => ({
    pending: acc.pending + p.pending_count, auto: acc.auto + p.auto_count, first: acc.first + p.first_passed_count, final: acc.final + p.final_passed_count, rejected: acc.rejected + p.rejected_count,
  }), { pending: 0, auto: 0, first: 0, final: 0, rejected: 0 }), [periods, filters.periodKeys]);

  const act = async (work: () => Promise<unknown>, done: (result: unknown) => string) => {
    setBusy(true);
    try {
      const result = await work();
      void messageApi.success(done(result));
      setSelected([]);
      await refresh();
    } catch (error) {
      void messageApi.error(errorText(error));
    } finally {
      setBusy(false);
    }
  };
  const reviewNow = (stage: "first" | "final", decision: "pass" | "reject" | "revert", comment: string | undefined, confirmed: boolean) =>
    act(() => postReview(selectedRows.map((r) => r.review_id), stage, decision, comment, confirmed), (result) => {
      const r = result as { succeeded: number; failed: number; items: { message: string | null }[] };
      const firstError = r.items.find((i) => i.message)?.message;
      return `${stage === "first" ? "初审" : "终审"}${decision === "pass" ? "通过" : decision === "reject" ? "退回" : "撤销"} ${r.succeeded} 行${r.failed ? `，${r.failed} 行未成功${firstError ? `（${firstError}）` : ""}` : ""}`;
    });
  /** PRP §5：≥ 20 行先二次确认，再带 confirm_token 提交 */
  const review = (stage: "first" | "final", decision: "pass" | "reject" | "revert", comment?: string) => {
    const count = selectedRows.length;
    if (count < BATCH_CONFIRM_THRESHOLD) return reviewNow(stage, decision, comment, false);
    modal.confirm({
      title: `批量${stage === "first" ? "初审" : "终审"}${decision === "pass" ? "通过" : decision === "reject" ? "退回" : "撤销"} ${count} 行`,
      content: `一次操作 ${count} 行（≥ ${BATCH_CONFIRM_THRESHOLD} 行），确认后提交。`,
      okText: "确认提交",
      onOk: () => reviewNow(stage, decision, comment, true),
    });
    return Promise.resolve();
  };
  const recalc = () => act(() => postRecalc(filters.storeIds, filters.periodKeys), (result) => {
    const r = result as { periods_total: number; items: { status: string }[] };
    const skipped = r.items.filter((i) => i.status === "skipped_closed").length;
    return `已重算 ${r.periods_total} 期${skipped ? `（${skipped} 期已结账跳过）` : ""}`;
  });

  const all: Record<string, ProColumns<ApiLine>> = {
    order: { key: "order", title: "订单号 / 行", width: 170, fixed: "left", render: (_, r) => <span>{r.platform_order_no} <Typography.Text type="secondary">/ {r.order_line_no}</Typography.Text></span> },
    store: { key: "store", title: "店铺", width: 90, render: (_, r) => stores.find(([id]) => id === r.store_id)?.[1] ?? r.store_id },
    period: { key: "period", title: "期", width: 100, render: (_, r) => r.period_key },
    item: { key: "item", title: "ItemID", width: 120, render: (_, r) => r.item_id ?? EMPTY },
    sku: { key: "sku", title: "SKU", width: 110, render: (_, r) => r.sku ?? EMPTY },
    msku: { key: "msku", title: "MSKU", width: 130, render: (_, r) => r.msku ?? EMPTY },
    gtin: { key: "gtin", title: "GTIN", width: 130, render: (_, r) => r.gtin ?? EMPTY },
    owner: { key: "owner", title: "负责人", width: 90, render: (_, r) => r.owner_id ?? EMPTY },
    kind: { key: "kind", title: "类型", width: 70, render: (_, r) => KIND_TEXT[r.line_kind] },
    fulfillment: { key: "fulfillment", title: "履约", width: 70, render: (_, r) => (r.fulfillment_type === "wfs" ? "WFS" : "自发货") },
    qty: { key: "qty", title: "件数", width: 60, align: "right", render: (_, r) => Number(r.quantity) },
    posted: { key: "posted", title: "结算时间", width: 100, render: (_, r) => r.posted_date ?? EMPTY },
    types: { key: "types", title: "交易类型", width: 220, render: (_, r) => r.transaction_types.map((t) => types.data?.find((x) => x.code === t)?.name_zh ?? t).join("；") },
    sales: { key: "sales", title: "销售", width: 90, align: "right", render: (_, r) => usd(r.sales) },
    refund: { key: "refund", title: "退款", width: 90, align: "right", render: (_, r) => usd(r.refund) },
    promotion: { key: "promotion", title: "促销折扣", width: 90, align: "right", render: (_, r) => usd(r.promotion) },
    commission: { key: "commission", title: "佣金", width: 90, align: "right", render: (_, r) => usd(r.commission) },
    returnFee: { key: "returnFee", title: "退货处理费", width: 90, align: "right", render: (_, r) => usd(r.return_fee) },
    tax: { key: "tax", title: "税费代收代缴", width: 100, align: "right", render: (_, r) => usd(r.tax_withheld) },
    wfsFee: { key: "wfsFee", title: "WFS 配送费", width: 100, align: "right", render: (_, r) => <Tooltip title="WFS 订单尾程：只展示，不计入货本"><span>{usd(r.wfs_fulfillment_fee)}</span></Tooltip> },
    mcfFee: { key: "mcfFee", title: "MCF 费", width: 90, align: "right", render: (_, r) => usd(r.mcf_fee) },
    settlement: { key: "settlement", title: "结算净额", width: 100, align: "right", render: (_, r) => usd(r.settlement_amount) },
    purchase: { key: "purchase", title: "采购价 ¥", width: 90, align: "right", render: (_, r) => (r.purchase ? cny(r.purchase) : EMPTY) },
    head: { key: "head", title: "头程 ¥", width: 90, align: "right", render: (_, r) => (r.head ? cny(r.head) : EMPTY) },
    lastLeg: { key: "lastLeg", title: "尾程 ¥", width: 90, align: "right", render: (_, r) => (r.fulfillment_type === "wfs" ? <Tooltip title="WFS 订单尾程见「WFS 配送费」列"><span>{EMPTY}</span></Tooltip> : r.last_leg ? cny(r.last_leg) : EMPTY) },
    source: { key: "source", title: "成本来源", width: 200, render: (_, r) => sourceCell(r) },
    costTotal: { key: "costTotal", title: "货本合计 ¥", width: 100, align: "right", render: (_, r) => (r.cost_total ? <Typography.Text strong>{cny(r.cost_total)}</Typography.Text> : EMPTY) },
    costUsd: { key: "costUsd", title: "货本 $", width: 90, align: "right", render: (_, r) => (r.fx_status === "missing" ? <Tag color="gold" bordered={false}>汇率缺失</Tag> : r.cost_total_usd ? usd(r.cost_total_usd) : EMPTY) },
    fx: { key: "fx", title: "汇率", width: 80, render: (_, r) => r.fx_rate ?? EMPTY },
    profit: { key: "profit", title: "利润 $", width: 90, align: "right", render: (_, r) => (r.profit_usd ? <MoneyCell value={n(r.profit_usd)} tone="profit" /> : EMPTY) },
    reasons: { key: "reasons", title: "待审原因", width: 220, render: (_, r) => (
      <>
        {r.review_reasons.includes(CHANGED_AFTER_REVIEW) && <Tooltip title="审核后计算值有变，请撤销后重审"><Tag color="red" bordered={false}>审核后数据有变</Tag></Tooltip>}
        {r.reasons.length ? r.reasons.map((x) => <Tag key={x} color="orange" bordered={false}>{REASON_TEXT[x] ?? x}</Tag>) : r.auto_passed ? <Tag color="green" bordered={false}>自动通过</Tag> : r.review_reasons.length ? null : EMPTY}
      </>
    ) },
    version: { key: "version", title: "版本", width: 70, render: (_, r) => `${r.version} / 算 ${r.calc_version}` },
    status: { key: "status", title: "状态", width: 150, fixed: "right", render: (_, r) => (
      <Space size={4}>
        {statusTag(r)}
        {can.costEntry && r.line_kind !== "refund" && r.review_status !== "final_passed" && <Button size="small" type="link" onClick={(e) => { e.stopPropagation(); setEntryLine(r); }}>录成本</Button>}
      </Space>
    ) },
  };
  const shown = columnKeys.flatMap((key) => (all[key] ? [all[key]] : []));
  const sortable = ["posted_date", "platform_order_no", "item_id", "msku", "sales_usd", "settlement_amount_usd", "cost_total_cny", "quantity", "review_status"];

  // PRP §7A：无 action 权限的按钮不显示（后端仍按权限 403）
  const batch = [
    ...(can.review1 ? [
      { key: "first_pass", label: "批量初审通过", onClick: () => void review("first", "pass") },
      { key: "first_reject", label: "退回（初审）", danger: true, onClick: () => setRejectOpen("first") },
      { key: "first_revert", label: "撤销初审", onClick: () => void review("first", "revert") },
    ] : []),
    ...(can.review2 ? [
      { key: "final_pass", label: "批量终审通过", onClick: () => void review("final", "pass") },
      { key: "final_reject", label: "退回（终审）", danger: true, onClick: () => setRejectOpen("final") },
      { key: "final_revert", label: "撤销终审", onClick: () => void review("final", "revert") },
    ] : []),
  ];
  const missingTranslation = (types.data ?? []).filter((t) => !t.translated);

  return (
    <>
      {holder}
      {modalHolder}
      {missingTranslation.length > 0 && <Alert type="warning" showIcon style={{ marginBottom: 12 }} message={`有 ${missingTranslation.length} 种交易类型还没有中文名（${missingTranslation.map((t) => t.name_en).join("、")}），请通知代码维护补翻译`} />}
      {lines.error && <Alert type="error" showIcon style={{ marginBottom: 12 }} message={errorText(lines.error)} />}
      <FinanceBoardFrame
        title="订单审核"
        preview={false}
        subtitle={`待审 ${totals.pending} · 自动通过 ${totals.auto} · 初审通过 ${totals.first} · 终审通过 ${totals.final} · 退回 ${totals.rejected}`}
        toolbar={<>
          <ReportFacetSelect mode="multiple" ariaLabel="期" placeholder="全部期" unit="期" value={filters.periodKeys} showSearch={false}
            options={periodOptions.map((p) => ({ value: p.period_key, label: p.period_key === latest ? `${period(p)}（最新）` : period(p) }))}
            onChange={(v) => set({ periodKeys: (v as string[] | undefined) ?? [] })} />
          <ReportFacetSelect mode="multiple" ariaLabel="店铺" placeholder="店铺" unit="家" value={filters.storeIds}
            options={stores.map(([value, label]) => ({ value, label }))} onChange={(v) => set({ storeIds: (v as string[] | undefined) ?? [] })} />
          <ReportFacetSelect mode="multiple" ariaLabel="状态" placeholder="状态" unit="项" value={filters.statuses}
            options={(Object.keys(STATUS_TEXT) as ReviewStatus[]).map((value) => ({ value, label: STATUS_TEXT[value].text }))} onChange={(v) => set({ statuses: (v as ReviewStatus[] | undefined) ?? [] })} />
          <ReportFacetSelect mode="multiple" ariaLabel="原因" placeholder="待审原因" unit="项" value={filters.reasons}
            options={[...(Object.keys(REASON_TEXT) as Reason[]).map((value) => ({ value: value as string, label: REASON_TEXT[value] })), { value: CHANGED_AFTER_REVIEW, label: "审核后数据有变" }]} onChange={(v) => set({ reasons: (v as Reason[] | undefined) ?? [] })} />
          <ReportFacetSelect mode="multiple" ariaLabel="类型" placeholder="销售 / 退款 / MCF" unit="项" value={filters.lineKinds} showSearch={false}
            options={(Object.keys(KIND_TEXT) as LineKind[]).map((value) => ({ value, label: KIND_TEXT[value] }))} onChange={(v) => set({ lineKinds: (v as LineKind[] | undefined) ?? [] })} />
          <ReportFacetSelect mode="multiple" ariaLabel="交易类型" placeholder="交易类型" unit="种" value={filters.transactionTypes}
            options={(types.data ?? []).map((t) => ({ value: t.code, label: `${t.name_zh ?? "（未翻译）"}（${t.name_en}）` }))} onChange={(v) => set({ transactionTypes: (v as string[] | undefined) ?? [] })} />
          {(["item_id", "sku", "msku"] as LookupKind[]).map((kind) => {
            const key = kind === "item_id" ? "itemIds" : kind === "sku" ? "skus" : "mskus";
            const count = filters[key].length;
            return <Button key={kind} icon={<SearchOutlined aria-hidden="true" />} onClick={() => setLookupKind(kind)}>{LOOKUP_LABEL[kind]}{count ? `（${count}）` : ""}</Button>;
          })}
          <Input.Search allowClear placeholder="订单号 / ItemID / MSKU / GTIN" style={{ width: 220 }} onSearch={(v) => set({ keyword: v })} />
          <ResetButton onClick={() => { setFilters({ ...DEFAULT_FILTERS, periodKeys: latest ? [latest] : [] }); setSelected([]); }} />
          <Space className="finance-board__toolbar-actions" size={8}>
            {can.recalc && <Tooltip title="按当前选的期 / 店铺重算（已结账的月跳过）"><Button icon={<ReloadOutlined aria-hidden="true" />} loading={busy} onClick={() => void recalc()}>重算</Button></Tooltip>}
            {batch.length > 0 && <Dropdown menu={{ items: batch }} disabled={!selectedRows.length}><Button loading={busy}>批量审核（{selectedRows.length}）</Button></Dropdown>}
            <Button aria-label="列配置" icon={<SettingOutlined aria-hidden="true" />} onClick={() => setColumnOpen(true)} />
          </Space>
        </>}
      >
        <BoardTable<ApiLine>
          label="订单审核" resizeKey="finance-order-review:lines" rowKey="review_id" rows={rows} columns={shown}
          emptyTitle="该期没有结算数据" emptyText="先同步沃尔玛账单并重算；账单同步状态见回款对账页"
          rowSelection={{ selectedRowKeys: selected, onChange: (keys) => setSelected(keys as string[]) }}
          serverPage={{ current: filters.page, pageSize: filters.pageSize, total: lines.data?.total ?? 0, onChange: (p, size) => setFilters((f) => ({ ...f, page: p, pageSize: size })) }}
        />
        <Space size={8} style={{ marginTop: 8 }}>
          <Typography.Text type="secondary">排序：</Typography.Text>
          {sortable.map((key) => (
            <a key={key} onClick={() => set({ sortBy: key, sortOrder: filters.sortBy === key && filters.sortOrder === "desc" ? "asc" : "desc" })}>
              {key}{filters.sortBy === key ? (filters.sortOrder === "desc" ? " ↓" : " ↑") : ""}
            </a>
          ))}
        </Space>
      </FinanceBoardFrame>
      <RuntimeColumnConfigDrawer open={columnOpen} groups={OR_COLUMN_GROUPS} fixedKeys={OR_FIXED_KEYS} defaultKeys={OR_DEFAULT_KEYS} appliedKeys={columnKeys}
        onApply={(keys) => { setColumnKeys(keys); writeOrderReviewColumns(keys); }} onClose={() => setColumnOpen(false)} onSaveTemplate={() => void messageApi.info("列配置只记在本浏览器")} />
      <CostEntryDrawer key={entryLine?.review_id ?? "none"} line={entryLine} onClose={() => setEntryLine(undefined)} onDone={() => void refresh()} />
      {lookupKind && (
        <ExactSearchModal kind={lookupKind} open value={lookupKind === "item_id" ? filters.itemIds : lookupKind === "sku" ? filters.skus : filters.mskus}
          onClose={() => setLookupKind(undefined)}
          onApply={(values) => set(lookupKind === "item_id" ? { itemIds: values } : lookupKind === "sku" ? { skus: values } : { mskus: values })} />
      )}
      <Modal open={!!rejectOpen} title={`退回（${rejectOpen === "first" ? "初审" : "终审"}）· ${selectedRows.length} 行`} okText="退回" okButtonProps={{ danger: true, disabled: !rejectReason.trim() }}
        onOk={() => { const stage = rejectOpen; setRejectOpen(undefined); if (stage) void review(stage, "reject", rejectReason.trim()); setRejectReason(""); }}
        onCancel={() => { setRejectOpen(undefined); setRejectReason(""); }}>
        <Input.TextArea rows={3} placeholder="退回原因（必填，写到每一行）" value={rejectReason} onChange={(e) => setRejectReason(e.target.value)} maxLength={2000} />
      </Modal>
    </>
  );
}

function FinanceOrderReviewPage({ page }: { page: NavigationPage }) {
  const periods = usePeriods();
  return (
    <PageShell page={page} headerActions={<HelpButton title="订单审核" sections={HELP} />}>
      {periods.data ? <Workbench periods={periods.data} /> : (
        <FinanceBoardFrame title="订单审核" preview={false} loading={periods.isPending && !periods.error} subtitle="">
          <Alert type={periods.error ? "error" : "info"} showIcon message={periods.error ? errorText(periods.error) : "正在读取期列表"} />
        </FinanceBoardFrame>
      )}
    </PageShell>
  );
}

export default FinanceOrderReviewPage;
