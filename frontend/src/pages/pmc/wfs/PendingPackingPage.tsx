/**
 * 待创建货件（Rocky 2026-11-04 第 12–16 条 + 拆票）：一个列表，状态写在每一行上。
 * 一行 = 一个打包单 × 一个货件：还没建的箱子每个打包单一行（待创建）；已提交的每票每个货件
 * 一行，打包单号在几行里重复。状态筛选默认前 5 种，「显示已发货」打开后才有已发货的历史行。
 * 本机模拟模式（只在 APP_ENV=local）顶部有横幅和「立即拉取结果」。页面不放帮助按钮。
 */
import { SettingOutlined } from "@ant-design/icons";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Alert, Button, Card, Checkbox, DatePicker, Select, Space, Switch, Typography, message } from "antd";
import type { Dayjs } from "dayjs";
import { useRef, useState } from "react";
import CommittedSearch from "@/components/report-table/CommittedSearch";
import ManagementStatCards from "@/components/report-table/ManagementStatCards";
import ResetButton from "@/components/report-table/ResetButton";
import PageShell from "@/components/page/PageShell";
import RequestLoadingOverlay from "@/components/page/RequestLoadingOverlay";
import type { NavigationPage } from "@/config/navigation";
import PackingWarehouseActionDialog from "../domestic-warehouse/packing/PackingWarehouseActionDialog";
import { writeWarehouseOrder } from "../domestic-warehouse/packing/packingWarehouseApi";
import type { PackingWarehouseRow, WarehouseAction, WarehouseFields } from "../domestic-warehouse/packing/packingWarehouseTypes";
import CreationDialog from "./CreationDialog";
import CreationRecords from "./CreationRecords";
import CreationRowTable from "./CreationRowTable";
import StoreDefaultsDrawer from "./StoreDefaultsDrawer";
import { DEFAULT_STATUSES, ROW_STATUSES, getCreationCapabilities, listBoardRows, simulatorPull, statusText, type BoardRowFilters, type RowStatus } from "./creationApi";
import PendingCustomsDialog from "./PendingCustomsDialog";
import PendingIdentityDialog from "./PendingIdentityDialog";
import { pendingError, pendingOptions, switchIdentity } from "./pendingPackingApi";
import type { IdentityFields, PendingRow } from "./pendingPackingTypes";
import "./PendingPackingPage.css";

const initialFilters = (): BoardRowFilters => ({ keyword: "", only_test: false, statuses: [...DEFAULT_STATUSES], show_shipped: false });
const cardTone: Record<RowStatus, "normal" | "success" | "warning" | "danger"> = {
  pending: "normal", submitting: "normal", failed: "danger", created: "success", shipped: "normal",
};
const cardIcon: Record<RowStatus, string> = { pending: "待", submitting: "提", failed: "败", created: "建", shipped: "发" };
const cardHint: Record<RowStatus, string> = {
  pending: "还有可用箱子、没有提交的打包单",
  submitting: "已确认创建，在等 Walmart 结果",
  failed: "Walmart 拒绝或查询超时，可重试",
  created: "有货件号，SP 发货单还没有",
  shipped: "有领星 SP 发货单号",
};

export default function PendingPackingPage({ page, scope = "anonymous", permissions = [] }: { page: NavigationPage; scope?: string; permissions?: string[] }) {
  const client = useQueryClient();
  const [filters, setFilters] = useState(initialFilters);
  const [pagination, setPagination] = useState({ page: 1, size: 50 });
  const [selected, setSelected] = useState<string[]>([]);
  const [dialog, setDialog] = useState<{ kind: "draft" | "identity" | "rebox" | "customs"; id?: string }>();
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState<string>();
  const [records, setRecords] = useState<string>();
  const [defaultsOpen, setDefaultsOpen] = useState(false);
  const retry = useRef<{ signature: string; key: string } | undefined>(undefined);
  const [messages, context] = message.useMessage();
  const base = ["wfs-pending-packing", scope];
  const list = useQuery({ queryKey: [...base, "rows", filters, pagination], queryFn: ({ signal }) => listBoardRows(filters, pagination.page, pagination.size, signal), retry: false, refetchInterval: 30000 });
  const options = useQuery({ queryKey: [...base, "options"], queryFn: ({ signal }) => pendingOptions(signal), retry: false });
  const capabilities = useQuery({ queryKey: [...base, "capabilities"], queryFn: ({ signal }) => getCreationCapabilities(signal), retry: false });
  const simulator = capabilities.data?.data.simulator === true;
  const rows = list.data?.data.items ?? [];
  const counts = list.data?.data.counts;
  const can = (key: string) => permissions.includes("*") || permissions.includes(key);
  const canDomestic = can("page:pmc:domestic-warehouse-board:view");
  const commitFilters = (next: BoardRowFilters) => { setFilters(next); setPagination((p) => ({ ...p, page: 1 })); setSelected([]); };
  const refresh = async () => {
    setSelected([]);
    await Promise.all([client.invalidateQueries({ queryKey: base }), client.invalidateQueries({ queryKey: ["domestic-packing-warehouse"] }), client.invalidateQueries({ queryKey: ["domestic-packing-approval"] })]);
  };
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
  const selectedRows = rows.flatMap((r) => r.pending && selected.includes(r.order_id) ? [r.pending] : []);
  const openDraft = () => {
    if (!selectedRows.length) return;
    if (new Set(selectedRows.map((r) => `${r.order.source_account_ref}|${r.order.store_id}|${r.business_test}`)).size !== 1) { void messages.warning("只能合并同账号、同店铺且测试标记一致的打包单"); return; }
    setActionError(undefined); setDialog({ kind: "draft" });
  };
  const pull = async () => {
    setBusy(true);
    try { const r = await simulatorPull(); void messages.success(`已拉取结果（任务中心运行 ${r.data.run_ids.length} 次）`); await refresh(); }
    catch (e) { void messages.error(pendingError(e)); }
    finally { setBusy(false); }
  };
  const loadError = list.error ? pendingError(list.error) : undefined;
  const onlyOne = filters.statuses.length === 1 ? filters.statuses[0] : undefined;
  const activeCard = onlyOne && (onlyOne !== "shipped" || filters.show_shipped) ? onlyOne : "";
  const clickCard = (key: RowStatus) => commitFilters(activeCard === key
    ? { ...filters, statuses: [...DEFAULT_STATUSES], show_shipped: false }
    : { ...filters, statuses: [key], show_shipped: key === "shipped" ? true : filters.show_shipped });
  const statusOptions = ROW_STATUSES.filter((s) => s !== "shipped").map((s) => ({ value: s, label: statusText[s] }));
  return <PageShell page={page}>
    {context}<div className="wfs-create">
      <Card size="small" className="wfs-create__page-card">
        <RequestLoadingOverlay spinning={list.isFetching && !list.data} label="正在加载待创建货件，请稍候" />
        <div className="wfs-create__title-row">
          <div>
            <h1>待创建货件</h1>
            <Typography.Text type="secondary">国内仓打包完成 → 选择发货箱数及分票 → 确认创建（自动检查后直接提交 Walmart：先按单号查一次，再创建、回读 FC、取箱唛）→ 已创建未发货 → 领星 SP 发货单 → 已发货。</Typography.Text>
          </div>
          <Space size={8} wrap>
            <Button disabled={busy || list.isFetching} onClick={() => void refresh()}>刷新</Button>
            <Button icon={<SettingOutlined />} onClick={() => setDefaultsOpen(true)}>创建默认值</Button>
          </Space>
        </div>
        {simulator && <Alert className="wfs-create__simulator" type="warning" showIcon
          message="本机模拟通道，不连 Walmart：货件号 SIM 开头、箱唛印 SIMULATED；退货地址邮编 00000 = 拒绝，99999 = 先进提交中、下一次拉取查到，其他直接成功。"
          action={<Button size="small" type="primary" disabled={busy} onClick={() => void pull()}>立即拉取结果（本机模拟）</Button>} />}
        <Card size="small" className="wfs-create__toolbar-card">
          <div className="wfs-create__toolbar" role="search" aria-label="待创建货件筛选">
            <Select allowClear showSearch aria-label="店铺" placeholder="全部店铺" className="wfs-create__store" value={filters.store_id} options={options.data?.data.stores} loading={options.isFetching} optionFilterProp="label" onChange={(v?: string) => commitFilters({ ...filters, store_id: v })} />
            <Select mode="multiple" aria-label="状态" placeholder="全部状态" className="wfs-create__status" maxTagCount="responsive" value={filters.statuses.filter((s) => s !== "shipped")} options={statusOptions}
              onChange={(v: RowStatus[]) => commitFilters({ ...filters, statuses: v.length ? v : [...DEFAULT_STATUSES] })} />
            <span className="wfs-create__switch"><Switch size="small" aria-label="显示已发货" checked={filters.show_shipped} onChange={(on) => commitFilters({ ...filters, show_shipped: on, statuses: on ? filters.statuses : filters.statuses.filter((s) => s !== "shipped").length ? filters.statuses.filter((s) => s !== "shipped") : [...DEFAULT_STATUSES] })} />显示已发货</span>
            <DatePicker.RangePicker aria-label="打包完成日期" allowEmpty={[true, true]} onChange={(values: [Dayjs | null, Dayjs | null] | null) => {
              const [from, to] = values ?? [null, null];
              commitFilters({ ...filters, completed_from: from?.format("YYYY-MM-DD"), completed_to: to?.format("YYYY-MM-DD") });
            }} />
            <CommittedSearch key={filters.keyword} className="wfs-create__search" typeAriaLabel="待创建货件搜索类型" typeValue="all" typeOptions={[{ value: "all", label: "全部" }]} inputAriaLabel="搜索待创建货件" inputValue={filters.keyword} inputPlaceholder="PK / SKU / 单号 / 货件号 / 发货单号" searchAriaLabel="搜索待创建货件" onCommit={({ keyword }) => commitFilters({ ...filters, keyword })} />
            <Checkbox checked={filters.only_test} onChange={(e) => commitFilters({ ...filters, only_test: e.target.checked })}>只看测试单</Checkbox>
            <ResetButton aria-label="重置待创建货件筛选" onClick={() => commitFilters(initialFilters())} />
            <span className="wfs-create__toolbar-actions">
              {can("action:pmc:wfs-pending-packing:create") && <Button type="primary" disabled={!selected.length || busy || !!loadError || list.isFetching} onClick={openDraft}>创建 WFS 货件</Button>}
            </span>
          </div>
        </Card>
        <ManagementStatCards<RowStatus> ariaLabel="待创建货件统计" className="wfs-create__cards" cards={ROW_STATUSES.map((key) => ({
          key, title: statusText[key], value: counts?.[key] ?? "—", unit: "行", tone: cardTone[key], icon: <span>{cardIcon[key]}</span>,
          subtitle: key === "shipped" && !filters.show_shipped ? `${cardHint[key]}（默认隐藏）` : cardHint[key],
        }))} activeKey={activeCard as RowStatus} onCardClick={clickCard} />
        {loadError && <Alert className="wfs-create__error" type="error" showIcon message={loadError} action={<Button size="small" onClick={() => void refresh()}>重试</Button>} />}
        <div className="wfs-create__table-wrap">
          <CreationRowTable rows={rows} total={list.data?.data.total ?? 0} loading={list.isFetching && !!list.data}
            page={pagination.page} size={pagination.size} error={loadError} selected={selected} onSelect={setSelected}
            actions={{ can, canDomestic, onIdentity: (r) => open("identity", r), onRebox: (r) => open("rebox", r), onCustoms: (r) => open("customs", r) }}
            onPageChange={(next, size) => { setPagination({ page: next, size }); setSelected([]); }} onOpenRecords={setRecords}
            onChanged={refresh} onError={(text) => void messages.error(text)} onDone={(text) => void messages.success(text)} />
        </div>
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
