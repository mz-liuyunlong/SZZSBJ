/**
 * 待创建货件（Rocky 2026-11-04）：报表样板 PageShell + ReportTableShell，4 个页签。
 * 待创建 = 打包完成且还有箱子没建货件；提交中 / 创建失败 / 已创建未发货 一行一票。
 * 「已发货」来自 SP 发货单，服务器接入前已创建的货件都留在「已创建未发货」。页面不放帮助按钮。
 */
import { ProTable, type ProColumns } from "@ant-design/pro-components";
import { SettingOutlined } from "@ant-design/icons";
import { useQuery } from "@tanstack/react-query";
import { Alert, Button, Card, Checkbox, DatePicker, Select, Space, Table, Tabs, Tag, Typography, message } from "antd";
import type { Dayjs } from "dayjs";
import { useRef, useState } from "react";
import CommittedSearch from "@/components/report-table/CommittedSearch";
import ManagementStatCards from "@/components/report-table/ManagementStatCards";
import ReportTableShell from "@/components/report-table/ReportTableShell";
import ResetButton from "@/components/report-table/ResetButton";
import { REPORT_TABLE_PAGE_SIZE_OPTIONS } from "@/components/report-table/pagination";
import { WalmartItemLink } from "@/components/report-table/cells";
import PageShell from "@/components/page/PageShell";
import RequestLoadingOverlay from "@/components/page/RequestLoadingOverlay";
import type { NavigationPage } from "@/config/navigation";
import EmptyState from "@/shared/states/EmptyState";
import PackingWarehouseActionDialog from "../domestic-warehouse/packing/PackingWarehouseActionDialog";
import { writeWarehouseOrder } from "../domestic-warehouse/packing/packingWarehouseApi";
import type { PackingWarehouseRow, WarehouseAction, WarehouseFields } from "../domestic-warehouse/packing/packingWarehouseTypes";
import CreationDialog from "./CreationDialog";
import CreationRecords from "./CreationRecords";
import CreationTicketTable from "./CreationTicketTable";
import StoreDefaultsDrawer from "./StoreDefaultsDrawer";
import { getTicketCounts, listCreationTickets, type TicketFilters, type TicketTab } from "./creationApi";
import PendingCustomsDialog from "./PendingCustomsDialog";
import PendingIdentityDialog from "./PendingIdentityDialog";
import { pendingError, switchIdentity } from "./pendingPackingApi";
import { usePendingPacking } from "./pendingPackingQueries";
import type { IdentityFields, PendingFilters, PendingRow } from "./pendingPackingTypes";
import "./PendingPackingPage.css";

type Tab = "pending" | TicketTab;
const initialFilters = (): PendingFilters => ({ keyword: "", only_test: false, arrangement: "open" });
const initialTicketFilters = (): TicketFilters => ({ keyword: "" });
const time = (v?: string | null) => v ? new Intl.DateTimeFormat("zh-CN", { timeZone: "Asia/Taipei", dateStyle: "short", timeStyle: "short" }).format(new Date(v)) : "—";
const labels: Record<string, string> = { PACKING_NOT_COMPLETED: "尚未打包完成", IDENTITY_MISSING: "商品身份不完整", GTIN_INVALID: "缺少有效GTIN", BOXES_REQUIRED: "缺少本系统装箱" };

export default function PendingPackingPage({ page, scope = "anonymous", permissions = [] }: { page: NavigationPage; scope?: string; permissions?: string[] }) {
  const [filters, setFilters] = useState(initialFilters);
  const [pagination, setPagination] = useState({ page: 1, size: 50 });
  const [selected, setSelected] = useState<string[]>([]);
  const [dialog, setDialog] = useState<{ kind: "draft" | "identity" | "rebox" | "customs"; id?: string }>();
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState<string>();
  const [records, setRecords] = useState<string>();
  const [tab, setTab] = useState<Tab>("pending");
  const [ticketFilters, setTicketFilters] = useState(initialTicketFilters);
  const [ticketPage, setTicketPage] = useState({ page: 1, size: 50 });
  const [defaultsOpen, setDefaultsOpen] = useState(false);
  const retry = useRef<{ signature: string; key: string } | undefined>(undefined);
  const [messages, context] = message.useMessage();
  const api = usePendingPacking(filters, pagination.page, pagination.size, scope);
  const ticketTab = tab === "pending" ? undefined : tab;
  const tickets = useQuery({ queryKey: ["wfs-pending-packing", scope, "tickets", ticketTab, ticketFilters, ticketPage], queryFn: ({ signal }) => listCreationTickets(ticketTab!, ticketFilters, ticketPage.page, ticketPage.size, signal), enabled: !!ticketTab, retry: false, refetchInterval: ticketTab === "submitting" ? 30000 : false });
  const counts = useQuery({ queryKey: ["wfs-pending-packing", scope, "ticket-counts", ticketFilters], queryFn: ({ signal }) => getTicketCounts(ticketFilters, signal), retry: false });
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
  const selectedRows = rows.filter((r) => selected.includes(r.order.id));
  const openDraft = () => {
    if (!selectedRows.length) return;
    if (new Set(selectedRows.map((r) => `${r.order.source_account_ref}|${r.order.store_id}|${r.business_test}`)).size !== 1) { void messages.warning("只能合并同账号、同店铺且测试标记一致的打包单"); return; }
    setActionError(undefined); setDialog({ kind: "draft" });
  };
  const columns: ProColumns<PendingRow>[] = [
    { title: "选择", width: 56, fixed: "left", render: (_, r) => <Checkbox aria-label={`选择${r.order.pk}`} disabled={!r.available_boxes || busy || !can("action:pmc:wfs-pending-packing:create")} checked={selected.includes(r.order.id)} onChange={(e) => setSelected((old) => e.target.checked ? [...old, r.order.id] : old.filter((id) => id !== r.order.id))} /> },
    { title: "系统打包单", width: 170, fixed: "left", render: (_, r) => <span>{r.order.pk}{r.business_test && <Tag color="orange">测试</Tag>}{r.overdue && <Tag color="red">打包完成 {r.packed_days} 天未建货件</Tag>}<span className="wfs-pending__sub">{r.order.box_set?.completed_by} {time(r.order.box_set?.completed_at)}</span></span> },
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
    { title: "发货安排", width: 260, render: (_, r) => <span><Tag color={r.available_boxes ? "success" : "warning"}>{r.available_boxes ? r.occupied_boxes ? "部分已安排" : "可安排" : r.occupied_boxes ? "已安排完成" : "信息待补充"}</Tag><span className="wfs-pending__sub">总计 {r.total_boxes} 箱 · 已占用 {r.occupied_boxes} 箱 · 剩余 {r.available_boxes} 箱</span><span className="wfs-pending__sub">{r.blocked_reasons.map((x) => labels[x] ?? x).join("；")}</span><Button type="link" size="small" onClick={() => setRecords(r.order.id)}>创建记录</Button></span> },
  ];
  const loadError = api.list.error ?? api.summary.error ?? api.options.error;
  const pageLoading = api.list.isFetching || api.summary.isFetching;
  const count = (key: TicketTab) => counts.data?.data[key];
  const tabLabel = (text: string, n?: number) => n === undefined ? text : `${text} ${n}`;
  const commitTickets = (next: TicketFilters) => { setTicketFilters(next); setTicketPage((p) => ({ ...p, page: 1 })); };
  const storeSelect = (value: string | undefined, onChange: (v?: string) => void) => <Select allowClear showSearch aria-label="店铺" placeholder="全部店铺" className="wfs-create__store" value={value} options={api.options.data?.data.stores} loading={api.options.isFetching} optionFilterProp="label" onChange={onChange} />;
  const ticketError = tickets.error ? pendingError(tickets.error) : undefined;
  return <PageShell page={page}>
    {context}<div className="wfs-create">
      <Card size="small" className="wfs-create__page-card">
        <RequestLoadingOverlay spinning={tab === "pending" && pageLoading} label="正在加载待创建货件，请稍候" />
        <div className="wfs-create__title-row">
          <div>
            <h1>待创建货件</h1>
            <Typography.Text type="secondary">国内仓打包完成 → 选择发货箱数及分票 → 确认提交（程序自动检查）→ 人工书面批准 → 提交 Walmart，每 3 分钟查一次结果（任务中心「WFS 创建结果拉取」）→ 已创建未发货。</Typography.Text>
          </div>
          <Space size={8} wrap>
            <Button disabled={busy || pageLoading} onClick={() => void refresh()}>刷新</Button>
            <Button icon={<SettingOutlined />} onClick={() => setDefaultsOpen(true)}>创建默认值</Button>
          </Space>
        </div>
        <Tabs className="wfs-create__tabs" activeKey={tab} onChange={(key) => { setTab(key as Tab); setTicketPage((p) => ({ ...p, page: 1 })); }} items={[
          { key: "pending", label: tabLabel("待创建", summary?.ready) },
          { key: "submitting", label: tabLabel("提交中", count("submitting")) },
          { key: "failed", label: tabLabel("创建失败", count("failed")) },
          { key: "created", label: tabLabel("已创建未发货", count("created")) },
        ]} />
        {tab === "pending" && <>
          <Card size="small" className="wfs-create__toolbar-card">
            <div className="wfs-create__toolbar" role="search" aria-label="待创建货件筛选">
              {storeSelect(filters.store_id, (v) => commitFilters({ ...filters, store_id: v }))}
              <Select aria-label="发货安排" className="wfs-create__select" value={filters.arrangement ?? "open"} options={[
                { value: "open", label: "全部待创建" },
                { value: "ready", label: "还没安排" },
                { value: "partial", label: "部分已安排" },
              ]} onChange={(v) => commitFilters({ ...filters, arrangement: v })} />
              <DatePicker.RangePicker aria-label="打包完成日期" allowEmpty={[true, true]} onChange={(values: [Dayjs | null, Dayjs | null] | null) => {
                const [from, to] = values ?? [null, null];
                commitFilters({ ...filters, completed_from: from?.format("YYYY-MM-DD"), completed_to: to?.format("YYYY-MM-DD") });
              }} />
              <CommittedSearch key={filters.keyword} className="wfs-create__search" typeAriaLabel="待创建货件搜索类型" typeValue="all" typeOptions={[{ value: "all", label: "PK / SKU" }]} inputAriaLabel="搜索待创建货件" inputValue={filters.keyword} inputPlaceholder="PK / SKU / ItemID / GTIN" searchAriaLabel="搜索待创建货件" onCommit={({ keyword }) => commitFilters({ ...filters, keyword })} />
              <Checkbox checked={filters.only_test} onChange={(e) => commitFilters({ ...filters, only_test: e.target.checked })}>只看测试单</Checkbox>
              <ResetButton aria-label="重置待创建货件筛选" onClick={() => commitFilters(initialFilters())} />
              <span className="wfs-create__toolbar-actions">
                {can("action:pmc:wfs-pending-packing:create") && <Button type="primary" disabled={!selected.length || busy || !!loadError || api.list.isFetching} onClick={openDraft}>创建 WFS 货件</Button>}
              </span>
            </div>
          </Card>
          <ManagementStatCards ariaLabel="待创建货件统计" cards={[
            { key: "ready", title: "已打包完成 · 待创建", value: summary?.ready ?? "—", unit: "张", tone: "normal", icon: <span>单</span>, subtitle: `已完成 ${summary?.completed ?? "—"} 张 · 测试 ${summary?.test ?? "—"} · 可用 ${summary?.available_boxes ?? "—"} 箱` },
            { key: "overdue", title: `打包完成满 ${summary?.overdue_days ?? 3} 天未建货件`, value: summary?.overdue ?? "—", unit: "张", tone: "danger", icon: <span>超</span>, subtitle: "仍有箱子未安排到货件；点此只看这些单" },
            { key: "waiting", title: "已审批、还没打包完成", value: summary?.waiting ?? "—", unit: "张", tone: "warning", icon: <span>待</span>, subtitle: `没填装箱 ${summary?.no_box ?? "—"} · 已填未完成 ${summary?.filled_not_done ?? "—"}（不进下表）` },
          ]} activeKey={filters.only_overdue ? "overdue" : ""} onCardClick={(key) => commitFilters({ ...filters, only_overdue: key === "overdue" ? !filters.only_overdue : false })} />
          {loadError && <Alert className="wfs-create__error" type="error" showIcon message={pendingError(loadError)} action={<Button size="small" onClick={() => void refresh()}>重试</Button>} />}
          <div className="wfs-create__table-wrap">
            <ReportTableShell label="待创建货件表格" className="wfs-create__table-shell">
              <ProTable<PendingRow> rowKey={(r) => r.order.id} search={false} options={false} toolBarRender={false} tableAlertRender={false} size="small" bordered columns={columns} dataSource={rows} loading={false} scroll={{ x: 1760, y: "100%" }}
                expandable={{ expandedRowRender: (r) => <Table size="small" rowKey="id" pagination={false} dataSource={r.order.box_set?.lines} columns={[
                  { title: "行号", dataIndex: "line_no" }, { title: "箱数", dataIndex: "boxes" }, { title: "每箱件数", dataIndex: "units_per_box" },
                ]} /> }}
                pagination={{ current: pagination.page, pageSize: pagination.size, total: api.list.data?.data.total ?? 0, showSizeChanger: true, pageSizeOptions: REPORT_TABLE_PAGE_SIZE_OPTIONS, showTotal: (n) => `共 ${n} 张`, onChange: (next, size) => { setPagination({ page: size !== pagination.size ? 1 : next, size }); setSelected([]); } }}
                locale={{ emptyText: <EmptyState title={loadError ? "数据未加载" : "暂无数据"} description={loadError ? "数据加载失败，请重试" : "当前条件下暂无已打包完成单据"} compact /> }} />
            </ReportTableShell>
          </div>
        </>}
        {ticketTab && <>
          <Card size="small" className="wfs-create__toolbar-card">
            <div className="wfs-create__toolbar" role="search" aria-label="创建结果筛选">
              {storeSelect(ticketFilters.store_id, (v) => commitTickets({ ...ticketFilters, store_id: v }))}
              <CommittedSearch key={ticketFilters.keyword} className="wfs-create__search" typeAriaLabel="创建结果搜索类型" typeValue="all" typeOptions={[{ value: "all", label: "PK / SKU / 货件号" }]} inputAriaLabel="搜索创建结果" inputValue={ticketFilters.keyword} inputPlaceholder="PK / SKU / 货件号" searchAriaLabel="搜索创建结果" onCommit={({ keyword }) => commitTickets({ ...ticketFilters, keyword })} />
              <ResetButton aria-label="重置创建结果筛选" onClick={() => commitTickets(initialTicketFilters())} />
              <Typography.Text type="secondary" className="wfs-create__toolbar-actions">{{
                submitting: "只看不改：待人工批准的在「创建记录」里批准；提交中的每 3 分钟自动查一次，最多 10 次。",
                failed: "Walmart 给的原因原样显示；重试先查同一单号，查不到才重新提交。",
                created: "SP 发货单变成「已发货」后移出本页签（SP 发货单接入服务器后生效）。",
              }[ticketTab]}</Typography.Text>
            </div>
          </Card>
          {ticketError && <Alert className="wfs-create__error" type="error" showIcon message={ticketError} action={<Button size="small" onClick={() => void tickets.refetch()}>重试</Button>} />}
          <div className="wfs-create__table-wrap">
            <CreationTicketTable tab={ticketTab} rows={tickets.data?.data.items ?? []} total={tickets.data?.data.total ?? 0} loading={tickets.isFetching}
              page={ticketPage.page} size={ticketPage.size} error={ticketError} canRetry={can("action:pmc:wfs-pending-packing:approve")}
              onPageChange={(next, size) => setTicketPage({ page: next, size })} onOpenRecords={setRecords}
              onChanged={refresh} onError={(text) => void messages.error(text)} />
          </div>
        </>}
      </Card>
    </div>
    {dialog?.kind === "draft" && selectedRows[0] && <CreationDialog rows={selectedRows} scope={scope} canProbe={can("action:pmc:wfs-pending-packing:preview")} onCancel={() => setDialog(undefined)} onCreated={(op) => { setDialog(undefined); setRecords(op.order_id); void refresh(); }} />}
    {dialog?.kind === "identity" && dialog.id && <PendingIdentityDialog id={dialog.id} scope={scope} busy={busy} error={actionError} onCancel={() => setDialog(undefined)} onSubmit={submitIdentity} />}
    {dialog?.kind === "rebox" && dialog.id && <PackingWarehouseActionDialog id={dialog.id} kind="rebox" scope={scope} busy={busy} onCancel={() => setDialog(undefined)} onSubmit={submitWarehouse} />}
    {dialog?.kind === "customs" && dialog.id && <PendingCustomsDialog id={dialog.id} scope={scope} busy={busy} onCancel={() => setDialog(undefined)} onSubmit={(row, fields) => submitWarehouse(row, "customs", fields)} />}
    {records && <CreationRecords orderId={records} scope={scope} permissions={permissions} onClose={() => setRecords(undefined)} onRefresh={refresh} />}
    <StoreDefaultsDrawer open={defaultsOpen} scope={scope} canManage={can("action:pmc:wfs-settings:manage")} onClose={() => setDefaultsOpen(false)} />
  </PageShell>;
}
