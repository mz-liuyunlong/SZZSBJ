/** Read-only domestic receipt board; business operations and unsupported indicators stay unavailable. */
import { Alert, Button, Card, Drawer, Input, Select, Space, Tabs, Tooltip, Typography, message, theme } from "antd";
import { useState, type CSSProperties } from "react";
import PageShell from "@/components/page/PageShell";
import RuntimeColumnConfigDrawer from "@/components/report-table/RuntimeColumnConfigDrawer";
import type { NavigationPage } from "@/config/navigation";
import { formatDateTime } from "@/shared/formatters";
import { usePageStateCache } from "@/shared/page-state/pageStateCache";
import { readUserPreference, writeUserPreference } from "@/shared/preferences/userPreferenceCache";
import DomesticToolbar from "./components/DomesticToolbar";
import DomesticSummaryCards from "./components/DomesticSummaryCards";
import DomesticBatchTable from "./components/DomesticBatchTable";
import DomesticBatchDetail from "./components/DomesticBatchDetail";
import PackingWarehousePanel from "./packing/PackingWarehousePanel";
import { domesticErrorText } from "./domesticWarehouseApi";
import { useDomesticBoard, useDomesticFilterOptions } from "./domesticWarehouseQueries";
import { defaultColumnKeys, defaultColumnWidths, domesticColumns, initialDomesticFilters, type DomesticFilters, type BatchSort, type MappingStatus } from "./domesticWarehouseTypes";
import "./DomesticWarehousePage.css";

interface ColumnSettings { keys: string[]; widths: Record<string, number> }
const preferenceKey = "pmc-domestic-board:columns";
const columnGroups = [{ title: "批次字段", fields: domesticColumns.map(({ key, title }) => ({ key, title })) }];

export default function DomesticWarehousePage({ page, preferenceScope = "anonymous" }: { page: NavigationPage; preferenceScope?: string }) {
  const { token } = theme.useToken();
  const scope = `domestic-board:${preferenceScope}`;
  const [activeTab, setActiveTab] = usePageStateCache<"batches" | "packing">(`${scope}:tab`, "batches");
  const [filters, setFilters] = usePageStateCache<DomesticFilters>(`${scope}:filters`, initialDomesticFilters);
  const [pagination, setPagination] = usePageStateCache(`${scope}:pagination`, { page: 1, pageSize: 50 });
  const [showStats, setShowStats] = usePageStateCache(`${scope}:stats`, true);
  const [settings, setSettings] = useState<ColumnSettings>(() => {
    const stored = readUserPreference<ColumnSettings>(preferenceScope, preferenceKey, 1);
    const allowed = new Set(defaultColumnKeys);
    return { keys: ["arrival", ...(stored?.keys ?? defaultColumnKeys).filter((key) => key !== "arrival" && allowed.has(key))],
      widths: { ...defaultColumnWidths, ...stored?.widths } };
  });
  const [columnsOpen, setColumnsOpen] = useState(false);
  const [moreOpen, setMoreOpen] = useState(false);
  const [warehouseText, setWarehouseText] = useState("");
  const [detailId, setDetailId] = useState<string>();
  const [messageApi, messageContext] = message.useMessage();
  const { list, summary } = useDomesticBoard(filters, pagination.page, pagination.pageSize, preferenceScope, activeTab === "batches");
  const options = useDomesticFilterOptions(preferenceScope, activeTab === "batches");
  const error = list.error ?? summary.error;
  const meta = list.data?.meta ?? summary.data?.meta;
  const commitFilters = (next: DomesticFilters) => {
    if (next.storeIds.length > 50 || (next.ownerUids?.length ?? 0) > 50) {
      void messageApi.warning("店铺和负责人分别最多支持 50 项"); return;
    }
    if (next.search.trim().length > 200) {
      void messageApi.warning("搜索内容最多支持 200 个字符"); return;
    }
    setFilters(next); setPagination({ ...pagination, page: 1 });
  };
  const persistColumns = (next: ColumnSettings) => {
    setSettings(next); writeUserPreference(preferenceScope, preferenceKey, 1, next);
  };
  const retry = () => { void list.refetch(); void summary.refetch(); };
  return <PageShell page={page} headerActions={<Button href="/help/domestic-warehouse.html" target="_blank" rel="noopener noreferrer">？帮助</Button>}>
    {messageContext}
    <div className="domestic-board" style={{
      "--ant-color-border-secondary": token.colorBorderSecondary,
      "--ant-border-radius-lg": `${token.borderRadiusLG}px`,
      "--ant-color-fill-quaternary": token.colorFillQuaternary,
      "--ant-font-size-sm": `${token.fontSizeSM}px`,
    } as CSSProperties}>
      <Card size="small" className="domestic-board__page-card">
        <div className="domestic-board__title-row">
          <div><Typography.Title level={3}>国内仓看板</Typography.Title>
            <Typography.Text type="secondary">{activeTab === "batches"
              ? "按收货批次追踪到仓与库存关联；到仓日期以收货单实际收货日期为准。"
              : "打包单（仓库）页面结构；业务查询、装箱和标签服务待接入。"}</Typography.Text></div>
          <Typography.Text type="secondary" className="domestic-board__freshness">
            {activeTab === "packing" ? "打包单数据尚未接入" : meta?.freshness_at ? `数据更新 ${formatDateTime(meta.freshness_at)}` : "暂无同步时间"}
            {activeTab === "batches" && summary.data && <><br />统计日期 {summary.data.data.as_of}</>}
          </Typography.Text>
        </div>
        <Tabs activeKey={activeTab} onChange={(key) => { if (key === "batches" || key === "packing") setActiveTab(key); }} className="domestic-board__tabs" items={[
          { key: "batches", label: "批次看板" },
          { key: "packing", label: "打包单（仓库）" },
          ...[{ key: "approval", label: "打包单审批" }, { key: "reconciliation", label: "双轨对账" }]
            .map((tab) => ({ key: tab.key, disabled: true, label: <Tooltip title="后续阶段开放">{tab.label}</Tooltip> })),
        ]} />
        {activeTab === "packing" ? <PackingWarehousePanel preferenceScope={preferenceScope} /> : <>
        <Card size="small" className="domestic-board__toolbar-card">
          <DomesticToolbar filters={filters} options={options.data?.data ?? { stores: [], owners: [] }}
            optionsLoading={options.isFetching} onChange={commitFilters}
            onReset={() => commitFilters(initialDomesticFilters())} showStats={showStats} onToggleStats={() => setShowStats(!showStats)}
            onColumns={() => setColumnsOpen(true)} onMore={() => { setWarehouseText(filters.warehouseIds.join("\n")); setMoreOpen(true); }} />
        </Card>
        {options.error && <Alert showIcon type="warning" message="店铺与负责人选项加载失败"
          description="请检查当前账号的国内仓权限或稍后重试；已选条件不会被静默清除。"
          action={<Button onClick={() => { void options.refetch(); }}>重试选项</Button>} />}
        {filters.businessStatus && <Alert showIcon type="info" message="业务状态筛选尚未接入"
          description="已选择状态，但当前后端尚不支持在库、打包或出库状态查询。已暂停查询，清除状态后可继续使用其他条件。"
          action={<Button onClick={() => commitFilters({ ...filters, businessStatus: undefined })}>清除状态</Button>} />}
        {showStats && <DomesticSummaryCards summary={filters.businessStatus ? undefined : summary.data?.data} active={filters.mappingStatus}
          onUnresolved={() => commitFilters({ ...filters, mappingStatus: filters.mappingStatus === "unresolved" ? undefined : "unresolved" })} />}
        {error && <Alert type="warning" showIcon message={domesticErrorText(error)}
          action={<Button size="small" onClick={retry}>重试</Button>} />}
        <Typography.Paragraph type="secondary" className="domestic-board__hint">
          当前一行对应一条收货明细；产品、ItemID、负责人、装箱及出库指标待接入。“—”表示未知，不代表 0。
        </Typography.Paragraph>
        <div className="domestic-board__table-wrap">
          <DomesticBatchTable rows={filters.businessStatus ? [] : list.data?.data.items ?? []} total={filters.businessStatus ? 0 : list.data?.data.total ?? 0}
            loading={list.isFetching} columns={settings} pagination={pagination} sort={filters.sort}
            onPagination={(page, pageSize) => setPagination({ page, pageSize })}
            onSort={(sort) => commitFilters({ ...filters, sort })}
            onResize={(key, width) => persistColumns({ ...settings, widths: { ...settings.widths, [key]: width } })}
            onDetail={setDetailId} />
        </div>
        </>}
      </Card>
      <Drawer title="更多筛选" open={moreOpen} onClose={() => setMoreOpen(false)} width={380}
        footer={<Space><Button onClick={() => setMoreOpen(false)}>取消</Button><Button type="primary" onClick={() => {
          const warehouseIds = [...new Set(warehouseText.split(/[\s,，]+/).filter(Boolean))];
          if (warehouseIds.length > 50 || warehouseIds.some((id) => id.length > 64)) {
            void messageApi.warning("最多支持 50 个仓库 ID，每个不超过 64 个字符"); return;
          }
          commitFilters({ ...filters, warehouseIds }); setMoreOpen(false);
        }}>应用筛选</Button></Space>}>
        <Typography.Paragraph>仓库 ID（一行一个，最多 50 个；不填则查询权限范围内全部国内仓）</Typography.Paragraph>
        <Input.TextArea aria-label="仓库 ID" value={warehouseText} onChange={(event) => setWarehouseText(event.target.value)} rows={8} />
        <Space direction="vertical" className="domestic-board__more-options">
          <Typography.Text>库存关联状态</Typography.Text>
          <Select<MappingStatus> aria-label="库存关联状态" placeholder="全部关联状态" allowClear value={filters.mappingStatus}
            options={[{ value: "matched", label: "库存已关联" }, { value: "unresolved", label: "库存待关联" }]}
            onChange={(mappingStatus) => commitFilters({ ...filters, mappingStatus })} />
          <Typography.Text>排序</Typography.Text>
          <Select<BatchSort> aria-label="排序" value={filters.sort}
            options={[{ value: "received_date_desc", label: "到仓日期：新到旧" },
              { value: "received_date_asc", label: "到仓日期：旧到新" }, { value: "qty_desc", label: "实收数量：多到少" }]}
            onChange={(sort) => commitFilters({ ...filters, sort })} />
        </Space>
      </Drawer>
      <RuntimeColumnConfigDrawer open={columnsOpen} groups={columnGroups} fixedKeys={["arrival"]}
        defaultKeys={defaultColumnKeys} appliedKeys={settings.keys}
        onApply={(keys) => persistColumns({ ...settings, keys })} onClose={() => setColumnsOpen(false)}
        onSaveTemplate={() => void messageApi.info("列配置已保存在当前浏览器，暂不支持服务端模板")} />
      <DomesticBatchDetail id={detailId} scope={preferenceScope} onClose={() => setDetailId(undefined)} />

    </div>
  </PageShell>;
}
