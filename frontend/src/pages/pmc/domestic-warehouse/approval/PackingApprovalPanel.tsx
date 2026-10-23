/** Local API composition; source selection and approvals remain server-owned. */
import { Alert, Button, Card, Space, Tooltip, Typography, message } from "antd";
import { useEffect, useRef, useState } from "react";
import { usePageStateCache } from "@/shared/page-state/pageStateCache";
import PackingApprovalHistory from "./PackingApprovalHistory";
import ManualPackingModal from "./ManualPackingModal";
import PackingApprovalTable from "./PackingApprovalTable";
import PackingApprovalToolbar from "./PackingApprovalToolbar";
import PackingDecisionModal, { type DecisionValues } from "./PackingDecisionModal";
import { approvalErrorText, type ApprovalCandidate, type DecisionKind, type DecisionPayload } from "./packingApprovalApi";
import { usePackingApproval } from "./packingApprovalQueries";
import { initialPackingApprovalFilters, type PackingApprovalFilters } from "./packingApprovalTypes";
import "./PackingApprovalPanel.css";
interface Props { preferenceScope: string; storeOptions: { value: string; label: string }[]; optionsLoading: boolean; onListFetching?: (fetching: boolean) => void }
export default function PackingApprovalPanel({ preferenceScope, onListFetching }: Props) {
  const scope = `domestic-approval:${preferenceScope}`;
  const [filters, setFilters] = usePageStateCache<PackingApprovalFilters>(`${scope}:filters`, initialPackingApprovalFilters);
  const [pagination, setPagination] = usePageStateCache(`${scope}:pagination`, { page: 1, pageSize: 50 });
  const [widths, setWidths] = usePageStateCache<Record<string, number>>(`${scope}:widths`, {});
  const [manualOpen, setManualOpen] = useState(false);
  const [historyOpen, setHistoryOpen] = useState(false); const [historyPage, setHistoryPage] = useState(1);
  const [selected, setSelected] = useState<{ row: ApprovalCandidate; kind: DecisionKind }>();
  const retryRequest = useRef<{ signature: string; key: string } | undefined>(undefined);
  const [messages, context] = message.useMessage();
  const api = usePackingApproval(filters, pagination.page, pagination.pageSize, preferenceScope, historyOpen, historyPage);
  useEffect(() => {
    onListFetching?.(api.list.isFetching);
    return () => onListFetching?.(false);
  }, [api.list.isFetching, onListFetching]);
  const perms = api.user.data?.permissions ?? [];
  const permission = (kind: DecisionKind) => perms.includes("*") || perms.includes(`action:pmc:domestic-warehouse-board:packing-${kind}`);
  const commitFilters = (next: PackingApprovalFilters) => {
    if (next.storeIds.length > 50) return;
    if (next.createdFrom && next.createdTo && next.createdFrom > next.createdTo) { void messages.warning("开始日期不能晚于结束日期"); return; }
    setFilters(next); setPagination({ ...pagination, page: 1 }); setHistoryPage(1);
  };
  const decide = async (values: DecisionValues) => {
    if (!selected) return;
    const { row, kind } = selected;
    const payload = { source_account_ref: row.source_account_ref, warehouse_id: row.warehouse_id, candidate_version: row.candidate_version,
      ...(kind === "approve" ? { qty: values.qty, customs: values.customs, rwh: values.rwh || undefined } : { note: values.note?.trim() }) };
    if (kind === "approve" && values.target) {
      const [target_store_id, target_item_id, listing_version] = JSON.parse(values.target) as string[];
      Object.assign(payload, { target_store_id, target_item_id, listing_version, edit_reason: values.edit_reason?.trim() || undefined });
    }
    const signature = JSON.stringify({ id: row.id, kind, ...payload });
    if (retryRequest.current?.signature !== signature) retryRequest.current = { signature, key: crypto.randomUUID() };
    const body: DecisionPayload = { ...payload, idempotency_key: retryRequest.current.key };
    try {
      const result = await api.decision.mutateAsync({ id: row.id, kind, body });
      void messages.success(kind === "approve" ? `已生成本地打包单 ${result.data.pk}` : "已记录驳回原因");
      setSelected(undefined); retryRequest.current = undefined;
    } catch (error) { void messages.error(approvalErrorText(error)); await api.refresh(); }
  };
  const error = api.list.error ?? api.summary.error ?? api.options.error;
  const stats = api.summary.error ? undefined : api.summary.data?.data;
  return <section className="domestic-approval" aria-label="打包单审批内容">{context}
    <Card size="small" className="domestic-board__toolbar-card"><PackingApprovalToolbar filters={filters} storeOptions={api.options.data?.data.stores ?? []} optionsLoading={api.options.isFetching}
      onChange={commitFilters} onReset={() => commitFilters(initialPackingApprovalFilters())} /></Card>
    {error && <Alert type="error" showIcon message={approvalErrorText(error)} action={<Button onClick={() => void api.refresh()}>重试</Button>} />}
    {api.user.error && <Alert type="warning" message="审批权限加载失败，请刷新登录状态；暂不开放审批操作" />}
    <div className="domestic-approval__summary-row"><Typography.Text>待审批打包单（待审 {stats?.pending ?? "—"}，超时 {stats?.overdue ?? "—"}，待补资料 {stats?.blocked ?? "—"}；已审 {stats ? stats.approved + stats.rejected : "—"}）</Typography.Text>
      <Space><Button onClick={() => setHistoryOpen(true)}>审批记录</Button><Button onClick={() => void api.refresh()}>刷新</Button><Tooltip title="先选入库单×SKU，再填写目标商品与数量"><Button disabled={!(perms.includes("*") || perms.includes("action:pmc:domestic-warehouse-board:packing-manual-create"))} onClick={() => setManualOpen(true)}>手工添加打包单</Button></Tooltip></Space></div>
    <div className="domestic-board__table-wrap"><PackingApprovalTable rows={api.list.error ? [] : api.list.data?.data.items ?? []} total={api.list.error ? 0 : api.list.data?.data.total ?? 0}
      canApprove={permission("approve")} canReject={permission("reject")} busy={api.decision.isPending}
      onDecision={(row, kind) => { retryRequest.current = undefined; setSelected({ row, kind }); }} pagination={pagination} widths={widths} sort={filters.sort}
      onPagination={(page, pageSize) => setPagination({ page, pageSize })} onResize={(key, width) => setWidths({ ...widths, [key]: width })} onSort={(sort) => commitFilters({ ...filters, sort })} /></div>
    {manualOpen && <ManualPackingModal open={manualOpen} scope={preferenceScope} onCancel={() => setManualOpen(false)} onSubmitted={() => { setManualOpen(false); void messages.success("已提交待审批，通过后才生成PK"); void api.refresh(); }} />}
    <PackingDecisionModal scope={preferenceScope} row={selected?.row ?? null} kind={selected?.kind ?? "approve"} busy={api.decision.isPending} onCancel={() => setSelected(undefined)} onSubmit={decide} />
    <PackingApprovalHistory open={historyOpen} onClose={() => setHistoryOpen(false)} scope={preferenceScope} rows={api.history.data?.data.items ?? []} total={api.history.data?.data.total ?? 0} page={historyPage} onPage={setHistoryPage} loading={api.history.isFetching} error={api.history.error} retry={() => void api.history.refetch()} />
  </section>;
}
