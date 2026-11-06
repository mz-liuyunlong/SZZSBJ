/** Local API composition; source selection and approvals remain server-owned. */
import { Alert, Button, Card, Modal, Space, Typography, message } from "antd";
import { useEffect, useRef, useState } from "react";
import { usePageStateCache } from "@/shared/page-state/pageStateCache";
import PackingApprovalHistory from "./PackingApprovalHistory";
import ManualPackingModal from "./ManualPackingModal";
import PackingApprovalTable from "./PackingApprovalTable";
import PackingApprovalToolbar from "./PackingApprovalToolbar";
import PackingApproveConfirmModal from "./PackingApproveConfirmModal";
import PackingDecisionModal, { type DecisionValues } from "./PackingDecisionModal";
import { approvalBlockedText, approvalErrorText, decidePacking, savePendingEdit, type ApprovalCandidate, type DecisionKind, type DecisionPayload, type PackingOrder } from "./packingApprovalApi";
import { usePackingApproval } from "./packingApprovalQueries";
import { initialPackingApprovalFilters, type PackingApprovalFilters } from "./packingApprovalTypes";
import "./PackingApprovalPanel.css";
interface BatchResult { approved: { row: ApprovalCandidate; pks: string[] }[]; skipped: { row: ApprovalCandidate; reason: string }[]; failed: { row: ApprovalCandidate; reason: string }[] }
const rowLabel = (row: ApprovalCandidate) => `${row.inbound_order_sn} / ${row.sku}`;
const createdPks = (order: PackingOrder) => (order.split_pks?.length ? order.split_pks : order.pk ? [order.pk] : []);
const approveBody = (row: ApprovalCandidate, qty: number, customs: "default" | "declare" | "skip", identity: { operatorName?: string; passcode?: string }, key: string): DecisionPayload => ({
  source_account_ref: row.source_account_ref, warehouse_id: row.warehouse_id, candidate_version: row.candidate_version, qty, customs,
  rwh: row.warehouse_name?.trim() || row.manual_rwh?.trim() || undefined, idempotency_key: key,
  ...(identity.operatorName ? { operator_name: identity.operatorName } : {}), ...(identity.passcode ? { passcode: identity.passcode } : {}),
});
interface Props { preferenceScope: string; storeOptions: { value: string; label: string }[]; optionsLoading: boolean; onListFetching?: (fetching: boolean) => void }
export default function PackingApprovalPanel({ preferenceScope, onListFetching }: Props) {
  const scope = `domestic-approval:${preferenceScope}`;
  const [filters, setFilters] = usePageStateCache<PackingApprovalFilters>(`${scope}:filters`, initialPackingApprovalFilters);
  const [pagination, setPagination] = usePageStateCache(`${scope}:pagination`, { page: 1, pageSize: 50 });
  const [widths, setWidths] = usePageStateCache<Record<string, number>>(`${scope}:widths`, {});
  const [manualOpen, setManualOpen] = useState(false);
  const [historyOpen, setHistoryOpen] = useState(false); const [historyPage, setHistoryPage] = useState(1);
  const [selected, setSelected] = useState<{ row: ApprovalCandidate; kind: DecisionKind }>();
  const [confirmRow, setConfirmRow] = useState<ApprovalCandidate>();
  const [savingDraft, setSavingDraft] = useState(false);
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [batchOpen, setBatchOpen] = useState(false);
  const [batchProgress, setBatchProgress] = useState<string>();
  const [batchResult, setBatchResult] = useState<BatchResult>();
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
    setFilters(next); setPagination({ ...pagination, page: 1 }); setHistoryPage(1); setSelectedIds([]);
  };
  const submitDecision = async (row: ApprovalCandidate, kind: DecisionKind, values: DecisionValues) => {
    const payload = { source_account_ref: row.source_account_ref, warehouse_id: row.warehouse_id, candidate_version: row.candidate_version,
      ...(kind === "approve" ? { qty: values.qty, customs: values.customs, rwh: values.rwh?.trim() || row.warehouse_name?.trim() || row.manual_rwh?.trim() || undefined } : { note: values.note?.trim() }) };
    const signature = JSON.stringify({ id: row.id, kind, ...payload });
    if (retryRequest.current?.signature !== signature) retryRequest.current = { signature, key: crypto.randomUUID() };
    const body: DecisionPayload = { ...payload, idempotency_key: retryRequest.current.key, ...(values.operatorName ? { operator_name: values.operatorName } : {}), ...(values.passcode ? { passcode: values.passcode } : {}) };
    try {
      const result = await api.decision.mutateAsync({ id: row.id, kind, body });
      const pks = createdPks(result.data);
      void messages.success(kind !== "approve" ? "已记录驳回原因" : pks.length > 1 ? `已生成 ${pks.length} 张打包单：${pks.join("、")}` : `已生成本地打包单 ${result.data.pk}`);
      setSelected(undefined); setConfirmRow(undefined); retryRequest.current = undefined;
    } catch (error) { void messages.error(approvalErrorText(error)); await api.refresh(); }
  };
  const saveModify = async (row: ApprovalCandidate, values: DecisionValues) => {
    const reason = values.edit_reason?.trim() ?? "";
    if (!values.lines?.length || reason.length < 2) return;
    setSavingDraft(true);
    try {
      await savePendingEdit(row.id, {
        source_account_ref: row.source_account_ref,
        warehouse_id: row.warehouse_id,
        candidate_version: row.candidate_version,
        lines: values.lines.map((line) => ({ target_store_id: line.hit.store_id, target_item_id: line.hit.item_id, listing_version: line.hit.listing_version, qty: line.qty })),
        customs: values.customs,
        edit_reason: reason,
      });
      await api.refresh();
      void messages.success("已保存修改（未审批）");
      setSelected(undefined);
    } catch (error) {
      void messages.error(approvalErrorText(error));
      await api.refresh();
    } finally {
      setSavingDraft(false);
    }
  };
  const decide = async (values: DecisionValues) => {
    if (!selected) return;
    if (selected.kind === "approve") await saveModify(selected.row, values);
    else await submitDecision(selected.row, selected.kind, values);
  };
  const confirmApprove = async (values: { operatorName: string; passcode: string }) => {
    if (!confirmRow) return;
    const qty = confirmRow.default_quantity ?? confirmRow.available_quantity;
    if (!qty || qty < 1) { void messages.warning("请先在修改里填写备货数量"); return; }
    await submitDecision(confirmRow, "approve", { qty, customs: confirmRow.manual_customs ?? "default", rwh: confirmRow.warehouse_name?.trim() || confirmRow.manual_rwh?.trim() || undefined, operatorName: values.operatorName, passcode: values.passcode });
  };
  const listRowsAll = api.list.error ? [] : api.list.data?.data.items ?? [];
  const selectedRows = listRowsAll.filter((row) => selectedIds.includes(row.id));
  const runBatch = async (identity: { operatorName: string; passcode: string }) => {
    const rows = selectedRows;
    const result: BatchResult = { approved: [], skipped: [], failed: [] };
    for (const [index, row] of rows.entries()) {
      setBatchProgress(`审批中 ${index + 1}/${rows.length}`);
      const qty = row.default_quantity ?? row.available_quantity;
      if (!row.can_approve) { result.skipped.push({ row, reason: `待补资料：${approvalBlockedText(row.blocked_reasons)}` }); continue; }
      if (!qty || qty < 1) { result.skipped.push({ row, reason: "未填写备货数量" }); continue; }
      try {
        const order = await decidePacking(row.id, "approve", approveBody(row, qty, row.manual_customs ?? "default", identity, crypto.randomUUID()));
        result.approved.push({ row, pks: createdPks(order.data) });
      } catch (failure) {
        result.failed.push({ row, reason: approvalErrorText(failure) });
      }
    }
    setBatchProgress(undefined); setBatchOpen(false); setSelectedIds([]); setBatchResult(result);
    await api.refresh();
  };
  const error = api.list.error ?? api.summary.error ?? api.options.error;
  const stats = api.summary.error ? undefined : api.summary.data?.data;
  const listRows = listRowsAll;
  return <section className="domestic-approval" aria-label="打包单审批内容">{context}
    <Card size="small" className="domestic-board__toolbar-card"><PackingApprovalToolbar filters={filters} storeOptions={api.options.data?.data.stores ?? []} optionsLoading={api.options.isFetching}
      onChange={commitFilters} onReset={() => commitFilters(initialPackingApprovalFilters())} /></Card>
    {error && <Alert type="error" showIcon message={approvalErrorText(error)} action={<Button onClick={() => void api.refresh()}>重试</Button>} />}
    {api.user.error && <Alert type="warning" message="审批权限加载失败，请刷新登录状态；暂不开放审批操作" />}
    <div className="domestic-approval__summary-row"><Typography.Text>待审批打包单（待审 {stats?.pending ?? "—"}，超时 {stats?.overdue ?? "—"}，待补资料 {stats?.blocked ?? "—"}；已审 {stats ? stats.approved + stats.rejected : "—"}）</Typography.Text>
      <Space><Button type="primary" disabled={!permission("approve") || !selectedIds.length || !!batchProgress} onClick={() => setBatchOpen(true)}>{batchProgress ?? `批量审批（${selectedIds.length}）`}</Button><Button onClick={() => setHistoryOpen(true)}>审批记录</Button><Button onClick={() => void api.refresh()}>刷新</Button><Button disabled={!(perms.includes("*") || perms.includes("action:pmc:domestic-warehouse-board:packing-manual-create"))} onClick={() => setManualOpen(true)}>手工添加打包单</Button></Space></div>
    <div className="domestic-board__table-wrap"><PackingApprovalTable rows={listRows} total={api.list.error ? 0 : api.list.data?.data.total ?? 0}
      canApprove={permission("approve")} canReject={permission("reject")} busy={api.decision.isPending || savingDraft || !!batchProgress}
      selectedIds={selectedIds} onSelect={setSelectedIds}
      onDecision={(row, kind) => { retryRequest.current = undefined; setConfirmRow(undefined); setSelected({ row, kind }); }}
      onApprove={(row) => { retryRequest.current = undefined; setSelected(undefined); setConfirmRow(row); }} pagination={pagination} widths={widths} sort={filters.sort}
      onPagination={(page, pageSize) => { setSelectedIds([]); setPagination({ page, pageSize }); }} onResize={(key, width) => setWidths({ ...widths, [key]: width })} onSort={(sort) => commitFilters({ ...filters, sort })} /></div>
    <ManualPackingModal open={manualOpen} scope={preferenceScope} onCancel={() => setManualOpen(false)} onSubmitted={() => { setManualOpen(false); void messages.success("已提交待审批，通过后才生成PK"); void api.refresh(); }} />
    <PackingDecisionModal scope={preferenceScope} row={selected?.row ?? null} kind={selected?.kind ?? "approve"} busy={api.decision.isPending || savingDraft} onCancel={() => setSelected(undefined)} onSubmit={decide} />
    <PackingApproveConfirmModal row={confirmRow ?? null} busy={api.decision.isPending} onCancel={() => setConfirmRow(undefined)} onSubmit={confirmApprove} />
    <PackingApproveConfirmModal row={null} rows={batchOpen ? selectedRows : []} progress={batchProgress} busy={!!batchProgress} onCancel={() => setBatchOpen(false)} onSubmit={runBatch} />
    <Modal title="批量审批结果" open={!!batchResult} onCancel={() => setBatchResult(undefined)} footer={<Button onClick={() => setBatchResult(undefined)}>关闭</Button>} destroyOnHidden>
      {batchResult && <>
        <Typography.Paragraph>成功 {batchResult.approved.length} 张{batchResult.approved.length ? `：${batchResult.approved.flatMap((item) => item.pks).join("、")}` : ""}</Typography.Paragraph>
        {batchResult.skipped.length > 0 && <Typography.Paragraph>跳过 {batchResult.skipped.length} 张：{batchResult.skipped.map((item) => `${rowLabel(item.row)}（${item.reason}）`).join("；")}</Typography.Paragraph>}
        {batchResult.failed.length > 0 && <Typography.Paragraph type="danger">失败 {batchResult.failed.length} 张：{batchResult.failed.map((item) => `${rowLabel(item.row)}（${item.reason}）`).join("；")}</Typography.Paragraph>}
      </>}
    </Modal>
    <PackingApprovalHistory open={historyOpen} onClose={() => setHistoryOpen(false)} scope={preferenceScope} rows={api.history.data?.data.items ?? []} total={api.history.data?.data.total ?? 0} page={historyPage} onPage={setHistoryPage} loading={api.history.isFetching} error={api.history.error} retry={() => void api.history.refetch()} />
  </section>;
}
