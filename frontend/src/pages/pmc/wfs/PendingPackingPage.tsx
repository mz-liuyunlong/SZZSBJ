/** Real domestic packing facts and local draft submission; no external execution. */
import { ProTable, type ProColumns } from "@ant-design/pro-components";
import { Alert, Button, Checkbox, Empty, Modal, Select, Space, Table, Tag, Typography, message } from "antd";
import { useEffect, useRef, useState } from "react";
import CommittedSearch from "@/components/report-table/CommittedSearch";
import ManagementStatCards from "@/components/report-table/ManagementStatCards";
import ResetButton from "@/components/report-table/ResetButton";
import { WalmartItemLink } from "@/components/report-table/cells";
import PageShell from "@/components/page/PageShell";
import RequestLoadingOverlay from "@/components/page/RequestLoadingOverlay";
import type { NavigationPage } from "@/config/navigation";
import PackingWarehouseActionDialog from "../domestic-warehouse/packing/PackingWarehouseActionDialog";
import { writeWarehouseOrder } from "../domestic-warehouse/packing/packingWarehouseApi";
import type { PackingWarehouseRow, WarehouseAction, WarehouseFields } from "../domestic-warehouse/packing/packingWarehouseTypes";
import PendingDraftDialog from "./PendingDraftDialog";
import PendingIdentityDialog from "./PendingIdentityDialog";
import { pendingError, submitDrafts, switchIdentity } from "./pendingPackingApi";
import { usePendingPacking } from "./pendingPackingQueries";
import type { DraftRead, IdentityFields, PendingFilters, PendingRow, ReturnAddress } from "./pendingPackingTypes";
import "./PendingPackingPage.css";

const initialFilters = (): PendingFilters => ({ keyword: "", only_test: false });
const time = (v?: string | null) => v ? new Intl.DateTimeFormat("zh-CN", { timeZone: "Asia/Taipei", dateStyle: "short", timeStyle: "short" }).format(new Date(v)) : "—";
const labels: Record<string, string> = { PACKING_NOT_COMPLETED: "尚未打包完成", IDENTITY_MISSING: "商品身份不完整", GTIN_INVALID: "缺少有效GTIN", BOXES_REQUIRED: "缺少本系统装箱" };

export default function PendingPackingPage({ page, scope = "anonymous", permissions = [] }: { page: NavigationPage; scope?: string; permissions?: string[] }) {
  const [filters, setFilters] = useState(initialFilters);
  const [pagination, setPagination] = useState({ page: 1, size: 20 });
  const [selected, setSelected] = useState<string[]>([]);
  const [dialog, setDialog] = useState<{ kind: "draft" | "identity" | "rebox" | "customs"; id?: string }>();
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState<string>();
  const [result, setResult] = useState<DraftRead[]>();
  const retry = useRef<{ signature: string; key: string } | undefined>(undefined);
  const [messages, context] = message.useMessage();
  const bodyRef = useRef<HTMLDivElement>(null);
  const [scrollY, setScrollY] = useState(360);
  const api = usePendingPacking(filters, pagination.page, pagination.size, scope);
  const rows = api.list.data?.data.items ?? [];
  const summary = api.summary.data?.data;
  const can = (key: string) => permissions.includes("*") || permissions.includes(key);
  const canDomestic = can("page:pmc:domestic-warehouse-board:view");
  const commitFilters = (next: PendingFilters) => { setFilters(next); setPagination((p) => ({ ...p, page: 1 })); setSelected([]); };
  const refresh = async () => { setSelected([]); await api.refresh(); };
  const keyFor = (value: unknown) => {
    const signature = JSON.stringify(value);
    if (retry.current?.signature !== signature) retry.current = { signature, key: crypto.randomUUID() };
    return retry.current.key;
  };
  useEffect(() => {
    const node = bodyRef.current;
    if (!node) return;
    const measure = () => setScrollY(Math.max(220, node.clientHeight - 96));
    measure(); const observer = new ResizeObserver(measure); observer.observe(node);
    return () => observer.disconnect();
  }, []);
  const open = (kind: "identity" | "rebox" | "customs", row: PendingRow) => { setActionError(undefined); retry.current = undefined; setDialog({ kind, id: row.order.id }); };
  const perform = async (operation: () => Promise<void>) => {
    setBusy(true); setActionError(undefined);
    try { await operation(); setDialog(undefined); retry.current = undefined; await refresh(); }
    catch (e) { const text = pendingError(e); setActionError(text); void messages.error(text); throw e; }
    finally { setBusy(false); }
  };
  const submitWarehouse = (row: PackingWarehouseRow, action: WarehouseAction, fields: WarehouseFields) => perform(async () => {
    const body = { source_account_ref: row.source_account_ref, expected_version: row.version, ...fields };
    const response = await writeWarehouseOrder(row.id, action, { ...body, idempotency_key: keyFor({ id: row.id, action, body }) });
    void messages[response.data.command_outcome === "blocked" ? "warning" : "success"](response.data.command_outcome === "blocked" ? "已记录缺口提议，实际装箱未改变" : "已保存");
  });
  const submitIdentity = (row: PendingRow, fields: IdentityFields) => perform(async () => {
    await switchIdentity(row, fields, keyFor({ id: row.order.id, version: row.order.version, fields }));
    void messages.success("已生成新 PK，原单及装箱历史保留");
  });
  const selectedRows = rows.filter((r) => r.order.box_set?.lines.some((l) => selected.includes(l.id)));
  const openDraft = () => {
    if (!selectedRows.length) return;
    if (new Set(selectedRows.map((r) => `${r.order.source_account_ref}|${r.order.store_id}|${r.business_test}`)).size !== 1) { void messages.warning("一次只能选择同账号、同店铺且测试标记一致的装箱"); return; }
    setActionError(undefined); retry.current = undefined; setDialog({ kind: "draft" });
  };
  const saveDraft = (address: ReturnAddress, its: boolean) => perform(async () => {
    const body = { source_account_ref: selectedRows[0].order.source_account_ref, its, return_address: address, selections: selectedRows.map((r) => ({ order_id: r.order.id, expected_version: r.order.version, expected_box_version: r.order.box_set!.version, box_line_ids: r.order.box_set!.lines.filter((l) => selected.includes(l.id)).map((l) => l.id) })) };
    const response = await submitDrafts({ ...body, idempotency_key: keyFor(body) }); setResult(response.data.drafts);
  });
  const toggle = (ids: string[], checked: boolean) => setSelected((old) => checked ? [...new Set([...old, ...ids])] : old.filter((id) => !ids.includes(id)));
  const columns: ProColumns<PendingRow>[] = [
    { title: "选择", width: 56, fixed: "left", render: (_, r) => <Checkbox aria-label={`选择${r.order.pk}`} disabled={!r.available_line_ids.length || busy || !can("action:pmc:wfs-pending-packing:draft-submit")} checked={!!r.available_line_ids.length && r.available_line_ids.every((id) => selected.includes(id))} indeterminate={r.available_line_ids.some((id) => selected.includes(id)) && !r.available_line_ids.every((id) => selected.includes(id))} onChange={(e) => toggle(r.available_line_ids, e.target.checked)} /> },
    { title: "系统打包单", width: 170, fixed: "left", render: (_, r) => <span>{r.order.pk}{r.business_test && <Tag color="orange">测试</Tag>}<span className="wfs-pending__sub">{r.order.box_set?.completed_by} {time(r.order.box_set?.completed_at)}</span></span> },
    { title: "店铺", width: 230, render: (_, r) => <span>{r.order.store_name ?? r.order.store_id ?? "—"}{can("action:pmc:wfs-pending-packing:identity-switch") && <Button type="link" size="small" disabled={!r.can_edit || busy} onClick={() => open("identity", r)}>换店铺 / 换链接</Button>}</span> },
    { title: "SKU · 品名", width: 180, render: (_, r) => <span>{r.order.sku}<span className="wfs-pending__sub">{r.order.product_name ?? "—"}</span></span> },
    { title: "Item ID / GTIN", width: 170, render: (_, r) => <span><WalmartItemLink itemId={r.order.item_id} /><span className="wfs-pending__sub">{r.order.gtin ?? "缺GTIN"}</span></span> },
    { title: "审批 / 实装数量", width: 130, align: "right", render: (_, r) => `${r.order.approved_quantity} / ${r.order.box_set?.total_qty ?? "—"}` },
    { title: "是否报关", width: 130, render: (_, r) => <span><Tag color={r.order.customs_value ? "red" : "default"}>{r.order.customs_value ? "报关" : "不报关"}</Tag>{canDomestic && can("action:pmc:domestic-warehouse-board:packing-customs") && <Button type="link" size="small" disabled={!r.can_edit || busy} onClick={() => open("customs", r)}>修改</Button>}</span> },
    { title: "单品包装 / 毛重", width: 170, render: (_, r) => {
      const measured = r.order.box_set?.package_snapshot?.values;
      const pack = measured ?? r.order.product_requirement?.package;
      return pack ? <span>{pack.length_cm}×{pack.width_cm}×{pack.height_cm} cm<span className="wfs-pending__sub">{pack.gross_weight_g} g · {measured ? "本单快照" : "产品资料"}</span></span> : "—";
    } },
    { title: "实际装箱（本系统）", width: 300, render: (_, r) => <span>{r.order.box_set?.lines.reduce((n, l) => n + l.boxes, 0)} 箱 · {r.order.box_set?.total_qty} 件{canDomestic && can("action:pmc:domestic-warehouse-board:packing-rebox") && <Button size="small" disabled={!r.can_edit || busy} onClick={() => open("rebox", r)}>改装箱</Button>}<span className="wfs-pending__sub">{r.order.box_set?.lines.map((l) => `${l.boxes}箱×${l.units_per_box}件`).join("；")}</span><span className="wfs-pending__sub">{r.order.box_set?.variance_reason}</span></span> },
    { title: "可建货件", width: 220, render: (_, r) => <span><Tag color={r.available_line_ids.length ? "success" : "warning"}>{r.available_line_ids.length ? "可勾选" : r.occupied_line_ids.length ? "已占用" : "不能建"}</Tag><span className="wfs-pending__sub">{r.blocked_reasons.map((x) => labels[x] ?? x).join("；")}{r.occupied_line_ids.length ? ` ${r.occupied_line_ids.length} 行装箱已进入草稿` : ""}</span></span> },
  ];
  const loadError = api.list.error ?? api.summary.error ?? api.options.error;
  const pageLoading = api.list.isFetching || api.summary.isFetching;
  return <PageShell page={page}>
    {context}<div className="wfs-pending">
      <RequestLoadingOverlay spinning={pageLoading} label="正在加载待发货打包单，请稍候" />
      <Typography.Paragraph className="wfs-pending__flow">国内仓系统审批 → 本系统装箱 → 打包完成 → 本页选择剩余装箱 → 保存待审批货件草稿。装箱只认本系统。</Typography.Paragraph>
      {loadError && <Alert type="error" showIcon message={pendingError(loadError)} action={<Button onClick={() => void refresh()}>重试</Button>} />}
      <ManagementStatCards ariaLabel="待发货打包单统计" cards={[
        { key: "ready", title: "已打包完成 · 可建货件", value: summary?.ready ?? "—", unit: "张", tone: "normal", icon: <span>单</span>, subtitle: `已完成 ${summary?.completed ?? "—"} 张 · 测试 ${summary?.test ?? "—"} · 可用 ${summary?.available_boxes ?? "—"} 箱` },
        { key: "waiting", title: "已审批、还没打包完成", value: summary?.waiting ?? "—", unit: "张", tone: "warning", icon: <span>待</span>, subtitle: `没填装箱 ${summary?.no_box ?? "—"} · 已填未完成 ${summary?.filled_not_done ?? "—"}（不进下表）` },
      ]} activeKey="" onCardClick={() => undefined} />
      <div className="wfs-pending__toolbar" role="search" aria-label="待发货打包单筛选">
        <Select allowClear showSearch aria-label="店铺" placeholder="全部店铺" style={{ width: 280 }} value={filters.store_id} options={api.options.data?.data.stores} loading={api.options.isFetching} optionFilterProp="label" onChange={(v) => commitFilters({ ...filters, store_id: v })} />
        <CommittedSearch key={filters.keyword} className="wfs-pending__search" typeAriaLabel="待发货打包单搜索类型" typeValue="all" typeOptions={[{ value: "all", label: "PK / SKU" }]} inputAriaLabel="搜索待发货打包单" inputValue={filters.keyword} inputPlaceholder="PK / SKU / ItemID / GTIN" searchAriaLabel="搜索待发货打包单" onCommit={({ keyword }) => commitFilters({ ...filters, keyword })} />
        <ResetButton aria-label="重置待发货打包单筛选" onClick={() => commitFilters(initialFilters())} />
      </div>
      <section className="wfs-pending__table" aria-label="待发货打包单表格"><div className="wfs-pending__head"><b>待发货打包单（来源：本系统已打包完成）</b><Space wrap>
        <Checkbox checked={filters.only_test} onChange={(e) => commitFilters({ ...filters, only_test: e.target.checked })}>只看测试单</Checkbox>
        <Button size="small" disabled={busy || pageLoading} onClick={() => void refresh()}>刷新</Button>
        {can("action:pmc:wfs-pending-packing:draft-submit") && <Button size="small" type="primary" disabled={!selected.length || busy || !!loadError || api.list.isFetching} onClick={openDraft}>生成货件草稿{selected.length ? `（${selected.length} 行装箱）` : ""}</Button>}
      </Space></div><div className="wfs-pending__body" ref={bodyRef}>
        <ProTable<PendingRow> rowKey={(r) => r.order.id} search={false} options={false} toolBarRender={false} tableAlertRender={false} size="small" bordered columns={columns} dataSource={rows} loading={false} scroll={{ x: 1760, y: scrollY }}
          expandable={{ expandedRowRender: (r) => <Table size="small" rowKey="id" pagination={false} dataSource={r.order.box_set?.lines} columns={[
            { title: "选择装箱行", render: (_, l) => <Checkbox aria-label={`选择装箱行${l.line_no}`} disabled={!r.available_line_ids.includes(l.id) || busy || !can("action:pmc:wfs-pending-packing:draft-submit")} checked={selected.includes(l.id)} onChange={(e) => toggle([l.id], e.target.checked)} /> },
            { title: "行号", dataIndex: "line_no" }, { title: "箱数", dataIndex: "boxes" }, { title: "每箱件数", dataIndex: "units_per_box" }, { title: "占用", render: (_, l) => r.occupied_line_ids.includes(l.id) ? "已进入待审批草稿" : "未占用" },
          ]} /> }} pagination={{ current: pagination.page, pageSize: pagination.size, total: api.list.data?.data.total ?? 0, showSizeChanger: true, showTotal: (n) => `共 ${n} 张`, onChange: (page, size) => { setPagination({ page, size }); setSelected([]); } }} locale={{ emptyText: <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={loadError ? "数据加载失败，请重试" : "当前条件下暂无已打包完成单据"} /> }} />
      </div><div className="wfs-pending__foot">展开可单独选择主箱、尾箱。有效占用后禁止修改该 PK。测试记录不计正式供货、在途和异常；本页不会写入领星或 Walmart。</div></section>
    </div>
    {dialog?.kind === "draft" && <PendingDraftDialog rows={selectedRows} selected={selected} busy={busy} error={actionError} onCancel={() => setDialog(undefined)} onSubmit={saveDraft} />}
    {dialog?.kind === "identity" && dialog.id && <PendingIdentityDialog id={dialog.id} scope={scope} busy={busy} error={actionError} onCancel={() => setDialog(undefined)} onSubmit={submitIdentity} />}
    {(dialog?.kind === "rebox" || dialog?.kind === "customs") && dialog.id && <PackingWarehouseActionDialog id={dialog.id} kind={dialog.kind} scope={scope} busy={busy} onCancel={() => setDialog(undefined)} onSubmit={submitWarehouse} />}
    <Modal title="货件草稿已保存" open={!!result} onCancel={() => setResult(undefined)} footer={<Button type="primary" onClick={() => setResult(undefined)}>知道了</Button>}><Alert type="success" message="草稿已持久化，当前为待审批" description="审批、写入 Walmart、箱唛和撤销属于下一阶段。" />{result?.map((r) => <p key={r.id}>{r.number} · 待审批 {r.business_test && <Tag>测试</Tag>}</p>)}</Modal>
  </PageShell>;
}
