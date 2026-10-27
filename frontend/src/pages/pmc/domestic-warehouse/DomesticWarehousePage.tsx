/** Inbound batch board — published API data only. */
import { Alert, Button, Card, Drawer, Input, Select, Space, Typography, message, theme } from "antd";
import { useState, type CSSProperties } from "react";
import PageShell from "@/components/page/PageShell";
import RequestLoadingOverlay from "@/components/page/RequestLoadingOverlay";
import RuntimeColumnConfigDrawer from "@/components/report-table/RuntimeColumnConfigDrawer";
import type { NavigationPage } from "@/config/navigation";
import { usePageStateCache } from "@/shared/page-state/pageStateCache";
import { writeUserPreference } from "@/shared/preferences/userPreferenceCache";
import DomesticToolbar from "./components/DomesticToolbar";
import DomesticSummaryCards from "./components/DomesticSummaryCards";
import DomesticBatchTable from "./components/DomesticBatchTable";
import DomesticBatchDetail from "./components/DomesticBatchDetail";
import PackingApprovalPanel from "./approval/PackingApprovalPanel";
import PackingWarehousePanel from "./packing/PackingWarehousePanel";
import { domesticErrorText } from "./domesticWarehouseApi";
import { useDomesticBoard, useDomesticFilterOptions } from "./domesticWarehouseQueries";
import { defaultColumnKeys, domesticColumns, initialDomesticFilters, type DomesticFilters, type BatchSort, type InventoryStatus } from "./domesticWarehouseTypes";
import { readDomesticColumns, domesticColumnPreferenceKey, domesticColumnPreferenceVersion, type DomesticColumnSettings } from "./domesticColumnPreferences";
import "./DomesticWarehousePage.css";

const columnGroups = [{ title: "入库批次字段", fields: domesticColumns.map(({ key, title }) => ({ key, title })) }];

export default function DomesticWarehousePage({ page, preferenceScope = "anonymous", view = "batches" }: { page: NavigationPage; preferenceScope?: string; view?: "batches" | "approval" | "packing" }) {
  const { token } = theme.useToken();
  const scope = `domestic-board:${preferenceScope}`;
  const activeTab = view;
  const [filters, setFilters] = usePageStateCache<DomesticFilters>(`${scope}:inbound-filters-v2`, initialDomesticFilters);
  const [pagination, setPagination] = usePageStateCache(`${scope}:inbound-pagination-v1`, { page: 1, pageSize: 50 });
  const [showStats, setShowStats] = usePageStateCache(`${scope}:stats`, true);
  const [settings, setSettings] = useState<DomesticColumnSettings>(() => readDomesticColumns(preferenceScope));
  const [columnsOpen, setColumnsOpen] = useState(false);
  const [moreOpen, setMoreOpen] = useState(false);
  const [warehouseText, setWarehouseText] = useState("");
  const [detail, setDetail] = useState<{ id: string; publication?: string | null }>();
  const [approvalFetching, setApprovalFetching] = useState(false);
  const [messageApi, messageContext] = message.useMessage();
  const batchesTabActive = activeTab === "batches";
  const approvalTabActive = activeTab === "approval";
  const filterOptionsEnabled = batchesTabActive || approvalTabActive;
  const { list, summary } = useDomesticBoard(filters, pagination.page, pagination.pageSize, preferenceScope, batchesTabActive);
  const options = useDomesticFilterOptions(filters.warehouseIds, preferenceScope, filterOptionsEnabled);
  const isTableRequesting = batchesTabActive && list.isFetching;
  const error = list.error ?? summary.error;
  const meta = list.data?.meta;
  const versionMismatch = list.data && summary.data && [...list.data.meta.publication_ids].sort().join() !== [...summary.data.meta.publication_ids].sort().join();
  const rows = list.error ? [] : list.data?.data.items ?? [];
  const total = list.error ? 0 : list.data?.data.total ?? 0;
  const stats = !versionMismatch && meta?.data_status === "ready" && !error ? summary.data?.data : undefined;
  const commitFilters = (next: DomesticFilters) => {
    if (next.ownerUids.length > 50 || next.storeIds.length > 50 || next.warehouseIds.length > 50 || (next.batchValues?.length ?? 0) > 50) { void messageApi.warning("每个多值条件最多支持 50 项"); return; }
    if ([...next.ownerUids, ...next.storeIds, ...next.warehouseIds, ...(next.batchValues ?? [])].some((v) => !v.trim() || v.length > 255)
      || next.search.length > (next.searchType === "all" ? 200 : 255)) { void messageApi.warning("输入为空或过长，请检查筛选内容"); return; }
    if (next.inboundFrom && next.inboundTo && next.inboundFrom > next.inboundTo) { void messageApi.warning("开始日期不能晚于结束日期"); return; }
    setDetail(undefined); setFilters(next); setPagination({ ...pagination, page: 1 });
  };
  const persistColumns = (next: DomesticColumnSettings) => { setSettings(next); writeUserPreference(preferenceScope, domesticColumnPreferenceKey, domesticColumnPreferenceVersion, next); };
  const retry = () => { void list.refetch(); void summary.refetch(); void options.refetch(); };
  const noPublication = meta?.data_status === "not_published";
  const emptyTitle = error ? "数据加载失败" : noPublication ? "尚无已发布入库数据" : "暂无入库批次";
  const emptyDescription = error ? "请查看错误提示并重试，不代表业务数量为零。" : noPublication
    ? "需要先完成数据库迁移、采集和发布。" : "当前筛选范围没有入库展示行，可重置条件查看。";
  return <PageShell page={page} headerActions={<Button href="/help/domestic-warehouse.html" target="_blank" rel="noopener noreferrer">？帮助</Button>}>
    {messageContext}
    <div className="domestic-board" style={{ "--ant-color-border-secondary": token.colorBorderSecondary, "--ant-border-radius-lg": `${token.borderRadiusLG}px`,
      "--ant-color-fill-quaternary": token.colorFillQuaternary, "--ant-font-size-sm": `${token.fontSizeSM}px` } as CSSProperties}>
      <Card size="small" className="domestic-board__page-card">
        <RequestLoadingOverlay
          spinning={activeTab === "approval" ? approvalFetching : isTableRequesting}
          label={activeTab === "approval" ? "正在加载打包审批，请稍候" : "正在加载入库批次，请稍候"}
        />
        <div className="domestic-board__title-row">
          <Typography.Title level={3}>{page.title}</Typography.Title>
        </div>
        {activeTab === "packing" ? <PackingWarehousePanel preferenceScope={preferenceScope} />
          : activeTab === "approval" ? <PackingApprovalPanel preferenceScope={preferenceScope}
            storeOptions={options.data?.data?.stores ?? []} optionsLoading={options.isFetching} onListFetching={setApprovalFetching} />
          : <>
          <Card size="small" className="domestic-board__toolbar-card"><DomesticToolbar filters={filters}
            filterOptions={options.data?.data} optionsLoading={options.isFetching}
            onChange={commitFilters} onReset={() => commitFilters(initialDomesticFilters())} showStats={showStats} onToggleStats={() => setShowStats(!showStats)}
            onColumns={() => setColumnsOpen(true)} onMore={() => { setWarehouseText(filters.warehouseIds.join("\n")); setMoreOpen(true); }} /></Card>
          {options.error && <Alert type="warning" showIcon message="筛选选项加载失败"
            description={domesticErrorText(options.error)} action={<Button size="small" onClick={() => void options.refetch()}>重试筛选选项</Button>} />}
          {noPublication && <Alert showIcon type="info" message="尚未发布入库数据" description="接口已接入；当前范围没有成功发布版本。" />}
          {error && <Alert type="error" showIcon message={domesticErrorText(error)} action={<Button size="small" onClick={retry}>重试</Button>} />}
          {versionMismatch && <Alert type="warning" showIcon message="列表与统计版本不同，请刷新后核对" action={<Button onClick={retry}>刷新版本</Button>} />}
          {showStats && <DomesticSummaryCards summary={stats} active={filters.inventoryStatus} onUnknown={() => commitFilters({ ...filters, inventoryStatus: filters.inventoryStatus === "unknown" ? undefined : "unknown" })} />}
          <Typography.Paragraph type="secondary" className="domestic-board__hint">一行 = 入库单 × SKU × 店铺。入库总量属于 IB×SKU，跨店铺不可直接相加；统计已去重。“—”表示未知。{stats && ` 统计日期 ${stats.as_of}。`}</Typography.Paragraph>
          <div className="domestic-board__table-wrap"><DomesticBatchTable rows={rows} total={total}
            emptyTitle={emptyTitle} emptyDescription={emptyDescription} columns={settings} pagination={pagination} sort={filters.sort}
            onPagination={(page, pageSize) => { setDetail(undefined); setPagination({ page, pageSize }); }} onSort={(sort) => commitFilters({ ...filters, sort })}
            onResize={(key, width) => persistColumns({ ...settings, widths: { ...settings.widths, [key]: width } })}
            onDetail={(id) => setDetail({ id, publication: rows.find((r) => r.id === id)?.publication_id })} /></div>
        </>}
      </Card>
      <Drawer title="更多筛选" open={moreOpen} onClose={() => setMoreOpen(false)} width={380} footer={<Space><Button onClick={() => setMoreOpen(false)}>取消</Button>
        <Button type="primary" onClick={() => { const warehouseIds = [...new Set(warehouseText.split(/[\s,，]+/).filter(Boolean))];
          if (warehouseIds.length > 50 || warehouseIds.some((id) => id.length > 64)) { void messageApi.warning("最多 50 个仓库 ID，每个不超过 64 个字符"); return; }
          commitFilters({ ...filters, warehouseIds }); setMoreOpen(false); }}>应用筛选</Button></Space>}>
        <Typography.Paragraph>仓库 ID（一行一个；留空查询权限范围内已发布仓库）</Typography.Paragraph>
        <Input.TextArea aria-label="仓库 ID" value={warehouseText} onChange={(event) => setWarehouseText(event.target.value)} rows={6} />
        <Space direction="vertical" className="domestic-board__more-options"><Typography.Text>余额数据状态</Typography.Text>
          <Select<InventoryStatus> aria-label="余额数据状态" placeholder="全部" allowClear value={filters.inventoryStatus} options={[{ value: "known", label: "余额已知（包含零）" }, { value: "unknown", label: "余额未知" }]}
            onChange={(inventoryStatus) => commitFilters({ ...filters, inventoryStatus })} /><Typography.Text>排序</Typography.Text>
          <Select<BatchSort> aria-label="排序" value={filters.sort} options={[{ value: "inbound_date_desc", label: "入库日期：新到旧" }, { value: "inbound_date_asc", label: "入库日期：旧到新" }, { value: "balance_desc", label: "批次余额：多到少" }]}
            onChange={(sort) => commitFilters({ ...filters, sort })} /></Space>
      </Drawer>
      <RuntimeColumnConfigDrawer open={columnsOpen} groups={columnGroups} fixedKeys={["arrival"]} defaultKeys={defaultColumnKeys} appliedKeys={settings.keys}
        onApply={(keys) => persistColumns({ ...settings, keys })} onClose={() => setColumnsOpen(false)} onSaveTemplate={() => void messageApi.info("列配置仅保存在当前浏览器")} />
      <DomesticBatchDetail id={detail?.id} expectedPublication={detail?.publication} scope={preferenceScope} onClose={() => setDetail(undefined)} />
    </div>
  </PageShell>;
}
