/** Warehouse tab orchestrates local APIs; business rules stay on the server. */
import { Alert, Button, Card, Space, Typography, message } from "antd";
import { useRef, useState } from "react";
import { usePageStateCache } from "@/shared/page-state/pageStateCache";
import PackingWarehouseTable, { type WarehouseDialogKind } from "./PackingWarehouseTable";
import PackingWarehouseToolbar from "./PackingWarehouseToolbar";
import PackingWarehouseActionDialog from "./PackingWarehouseActionDialog";
import PackingWarehouseDetails from "./PackingWarehouseDetails";
import { usePackingWarehouse } from "./packingWarehouseQueries";
import { warehouseError, warehouseSyncLabel } from "./packingWarehouseApi";
import { initialPackingWarehouseFilters, type PackingWarehouseFilters, type PackingWarehouseRow, type WarehouseAction, type WarehouseFields } from "./packingWarehouseTypes";
import "./PackingWarehousePanel.css";
const permissions = { boxes: "packing-boxes-save", done: "packing-done", customs: "packing-customs", notes: "packing-note", unpacked: "packing-unpacked-dispose", rebox: "packing-rebox", "supplemental-inbound": "packing-supplement-ib", "supplemental-sync": "packing-supplement-sync" };
export default function PackingWarehousePanel({ preferenceScope }: { preferenceScope: string }) {
  const scope = `domestic-packing:${preferenceScope}`;
  const [filters, setFilters] = usePageStateCache<PackingWarehouseFilters>(`${scope}:filters`, initialPackingWarehouseFilters);
  const [pagination, setPagination] = usePageStateCache(`${scope}:pagination`, { page: 1, pageSize: 50 });
  const [widths, setWidths] = usePageStateCache<Record<string, number>>(`${scope}:widths`, {});
  const [selected, setSelected] = useState<{ id: string; kind: WarehouseDialogKind }>();
  const [customsDraft, setCustomsDraft] = useState<Record<string, boolean | null>>({});
  const retry = useRef<{ signature: string; key: string } | undefined>(undefined);
  const [messages, context] = message.useMessage();
  const api = usePackingWarehouse(filters, pagination.page, pagination.pageSize, preferenceScope);
  const grants = api.user.data?.permissions ?? [];
  const can = (kind: WarehouseDialogKind | "customs") => {
    if (kind === "detail") return true;
    return grants.includes("*") || grants.includes(`action:pmc:domestic-warehouse-board:${permissions[kind]}`);
  };
  const commitFilters = (next: PackingWarehouseFilters) => {
    if (next.approvedFrom && next.approvedTo && next.approvedFrom > next.approvedTo) { void messages.warning("开始日期不能晚于结束日期"); return; }
    setFilters(next); setPagination({ ...pagination, page: 1 });
  };
  const submit = async (row: PackingWarehouseRow, action: WarehouseAction, fields: WarehouseFields) => {
    const command = { source_account_ref: row.source_account_ref, expected_version: row.version, ...fields };
    const signature = JSON.stringify({ id: row.id, action, command });
    if (retry.current?.signature !== signature) retry.current = { signature, key: crypto.randomUUID() };
    try { const response = await api.write.mutateAsync({ id: row.id, action, body: { ...command, idempotency_key: retry.current.key } }); setSelected(undefined); const result = response.data;
      if (action === "supplemental-sync") void messages[result.command_outcome === "ready" ? "success" : "warning"](warehouseSyncLabel(result.variance_case?.last_sync_code));
      else if (result.command_outcome === "blocked") void messages.warning("已记录超发待补入库，尚未放行；实际完成状态未改变");
      else void messages.success(action === "done" ? "打包完成，已进入已打包待发" : "已保存"); }
    catch (error) { void messages.error(warehouseError(error)); }
  };
  const changeCustoms = async (row: PackingWarehouseRow, value: boolean | null) => {
    setCustomsDraft((current) => ({ ...current, [row.id]: value }));
    await submit(row, "customs", { value });
    setCustomsDraft((current) => { const next = { ...current }; delete next[row.id]; return next; });
  };
  const error = api.list.error ?? api.summary.error;
  const stats = api.summary.data?.data;
  return <section className="domestic-packing" aria-label="打包单（仓库）内容">{context}
    <Card size="small" className="domestic-board__toolbar-card"><PackingWarehouseToolbar filters={filters} onChange={commitFilters} onReset={() => commitFilters(initialPackingWarehouseFilters())} storeOptions={api.options.data?.data.stores ?? []} optionsLoading={api.options.isFetching} /></Card>
    {error && <Alert type="error" showIcon message={warehouseError(error)} action={<Button onClick={() => void api.refresh()}>重试</Button>} />}
    {api.options.error && <Alert type="warning" message="店铺选项加载失败" action={<Button onClick={() => void api.options.refetch()}>重试店铺选项</Button>} />}
    {api.user.error && <Alert type="warning" message="操作权限加载失败，暂不开放写入，请刷新登录状态" />}
    <Space className="domestic-packing__summary"><Button onClick={() => commitFilters({ ...filters, status: "todo", exception: undefined })}>待打包 {stats?.todo ?? "—"}</Button><Button onClick={() => commitFilters({ ...filters, status: "packed", exception: undefined })}>已打包待发 {stats?.packed ?? "—"}</Button><Button onClick={() => commitFilters({ ...filters, status: "all", exception: "overpack" })}>超发待补入库 {stats?.overpack_blocked ?? "—"} 张</Button><Typography.Text type="secondary">仅展示已审批 PK</Typography.Text><Button onClick={() => void api.refresh()}>刷新仓库列表</Button></Space>
    <div className="domestic-board__table-wrap"><PackingWarehouseTable rows={api.list.error ? [] : api.list.data?.data.items ?? []} total={api.list.error ? 0 : api.list.data?.data.total ?? 0} loading={api.list.isFetching} busy={api.write.isPending} customsDraft={customsDraft} can={can} onAction={(row, kind) => { retry.current = undefined; setSelected({ id: row.id, kind }); }} onCustomsChange={(row, value) => { retry.current = undefined; void changeCustoms(row, value); }} pagination={pagination} widths={widths} sort={filters.sort}
      onPagination={(page, pageSize) => setPagination({ page, pageSize })} onResize={(key, width) => setWidths({ ...widths, [key]: width })} onSort={(sort) => commitFilters({ ...filters, sort })} /></div>
    {selected && (selected.kind === "detail" ? <PackingWarehouseDetails key={selected.id} id={selected.id} scope={preferenceScope} onClose={() => setSelected(undefined)} /> : <PackingWarehouseActionDialog id={selected.id} kind={selected.kind} scope={preferenceScope} busy={api.write.isPending} onCancel={() => setSelected(undefined)} onSubmit={submit} />)}
  </section>;
}
