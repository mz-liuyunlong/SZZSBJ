/**
 * PMC 总看板 (PRP pmc-overview, read-only).
 *
 * Composition-only page in the high-density report pattern (PageShell + ReportTableShell,
 * same as 采购看板): toolbar card → 12 stat cards (click = quick filter) → ItemID main table
 * (server-side filter / whitelist sort / paging, runtime column config). Warehouse and rules
 * tabs, the detail drawer and the 口径 drawer are local components. All numbers come from
 * `/api/pmc/overview/*`; 5173 source = one 8088 data-day snapshot, never sample data.
 */
import { DownloadOutlined, InfoCircleOutlined } from "@ant-design/icons";
import { Alert, Button, Card, Dropdown, Space, Tabs, Tag, Typography, message } from "antd";
import { useMemo, useState } from "react";
import PageShell from "@/components/page/PageShell";
import RequestLoadingOverlay from "@/components/page/RequestLoadingOverlay";
import RuntimeColumnConfigDrawer from "@/components/report-table/RuntimeColumnConfigDrawer";
import type { NavigationPage } from "@/config/navigation";
import OverviewFootnote from "@/pages/pmc/overview/components/OverviewFootnote";
import OverviewItemDrawer from "@/pages/pmc/overview/components/OverviewItemDrawer";
import OverviewRulesTab from "@/pages/pmc/overview/components/OverviewRulesTab";
import OverviewSummaryCards, { type CardKey } from "@/pages/pmc/overview/components/OverviewSummaryCards";
import OverviewTable from "@/pages/pmc/overview/components/OverviewTable";
import OverviewToolbar from "@/pages/pmc/overview/components/OverviewToolbar";
import OverviewWarehouseTab from "@/pages/pmc/overview/components/OverviewWarehouseTab";
import { getOverviewExport, overviewErrorText } from "@/pages/pmc/overview/overviewApi";
import {
  fixedOverviewColumnKeys,
  overviewColumnFields,
  overviewColumnGroups,
  overviewDefaultColumnKeys,
  overviewDefaultColumnWidths,
} from "@/pages/pmc/overview/overviewColumns";
import { fmt } from "@/pages/pmc/overview/overviewDisplay";
import {
  useOverviewItemQuery,
  useOverviewItemsQuery,
  useOverviewOptionsQuery,
  useOverviewSummaryQuery,
} from "@/pages/pmc/overview/overviewQueries";
import {
  createInitialOverviewFilters,
  OVERVIEW_PAGE_SIZES,
  type OverviewFilters,
  type OverviewSort,
} from "@/pages/pmc/overview/overviewTypes";
import { downloadOverviewWorkbook } from "@/pages/pmc/overview/overviewWorkbook";
import { usePageStateCache } from "@/shared/page-state/pageStateCache";
import { readUserPreference, writeUserPreference } from "@/shared/preferences/userPreferenceCache";
import "@/pages/pmc/overview/OverviewPage.css";

const COLUMN_PREFERENCE_KEY = "pmc-overview:columns";
const COLUMN_PREFERENCE_VERSION = 1;
const DEFAULT_SORT: OverviewSort = { order: "desc" };

interface ColumnPreference {
  appliedColumnKeys: string[];
  columnWidths: Record<string, number>;
}

const normalizeColumnKeys = (keys: string[]) => {
  const allowed = new Set(overviewColumnFields.map((f) => f.key));
  const merged = keys.filter((key) => allowed.has(key));
  for (const key of [...fixedOverviewColumnKeys].reverse()) if (!merged.includes(key)) merged.unshift(key);
  return merged;
};

interface OverviewPageProps {
  page: NavigationPage;
  preferenceScope?: string;
}

function OverviewPage({ page, preferenceScope = "anonymous" }: OverviewPageProps) {
  const [messageApi, holder] = message.useMessage();
  const stateKey = `pmc-overview:${preferenceScope}`;
  const [filters, setFilters] = usePageStateCache(`${stateKey}:filters`, createInitialOverviewFilters);
  const [currentPage, setCurrentPage] = usePageStateCache(`${stateKey}:page`, 1);
  const [storedPageSize, setPageSize] = usePageStateCache<number>(`${stateKey}:pageSize`, 50);
  const [sort, setSort] = usePageStateCache<OverviewSort>(`${stateKey}:sort`, DEFAULT_SORT);
  const [tab, setTab] = usePageStateCache(`${stateKey}:tab`, "main");
  const [columnConfigOpen, setColumnConfigOpen] = useState(false);
  const [footnoteOpen, setFootnoteOpen] = useState(false);
  const [openId, setOpenId] = useState<string>();
  const [exporting, setExporting] = useState(false);
  // A size cached before this release may no longer be offered; fall back to 50.
  const pageSize = (OVERVIEW_PAGE_SIZES as readonly number[]).includes(storedPageSize) ? storedPageSize : 50;

  const initialColumns = useMemo(() => {
    const stored = readUserPreference<ColumnPreference>(preferenceScope, COLUMN_PREFERENCE_KEY, COLUMN_PREFERENCE_VERSION);
    return {
      appliedColumnKeys: normalizeColumnKeys(stored?.appliedColumnKeys ?? overviewDefaultColumnKeys),
      columnWidths: { ...overviewDefaultColumnWidths, ...stored?.columnWidths },
    } satisfies ColumnPreference;
  }, [preferenceScope]);
  const [columns, setColumns] = usePageStateCache<ColumnPreference>(`${stateKey}:columns:v1`, initialColumns);
  const persistColumns = (next: ColumnPreference) => {
    setColumns(next);
    writeUserPreference(preferenceScope, COLUMN_PREFERENCE_KEY, COLUMN_PREFERENCE_VERSION, next);
  };

  const summaryQuery = useOverviewSummaryQuery();
  const itemsQuery = useOverviewItemsQuery(filters, currentPage, pageSize, sort);
  const optionsQuery = useOverviewOptionsQuery();
  const detailQuery = useOverviewItemQuery(openId);

  const summary = summaryQuery.data;
  const params = summary?.params ?? {};
  const total = itemsQuery.data?.total ?? 0;
  const pageError = summaryQuery.error ?? itemsQuery.error;
  const notReady = (pageError as { status?: number } | null)?.status === 503;

  const commit = (next: Partial<OverviewFilters>) => {
    setFilters({ ...filters, ...next });
    setCurrentPage(1);
  };
  const toggleCard = (key: CardKey) => {
    if (key === "all") commit({ cats: [], onlyIssue: false });
    else commit({ cats: filters.cats.includes(key) ? filters.cats.filter((c) => c !== key) : [key], onlyIssue: true });
  };
  const reset = () => {
    setSort(DEFAULT_SORT);
    commit(createInitialOverviewFilters());
  };

  const download = async (all: boolean) => {
    setExporting(true);
    const hide = messageApi.loading("正在生成 Excel…", 0);
    try {
      const data = await getOverviewExport(all ? undefined : filters);
      downloadOverviewWorkbook(data, all);
      void messageApi.success(`已下载（${fmt(data.items.length)} 个 ItemID）`);
    } catch (reason) {
      void messageApi.error(overviewErrorText(reason));
    } finally {
      hide();
      setExporting(false);
    }
  };

  const filtered = Boolean(filters.keyword || filters.storeId || filters.owner || filters.cats.length);
  const emptyText = pageError
    ? overviewErrorText(pageError)
    : filtered ? "当前筛选条件下没有 ItemID，可点「重置」查看全部。" : "当前数据日没有需要关注的 ItemID。";

  return (
    <PageShell
      page={page}
      headerActions={(
        <Button icon={<InfoCircleOutlined />} onClick={() => setFootnoteOpen(true)}>口径说明</Button>
      )}
    >
      {holder}
      <div className="pmc-overview">
        <Card size="small" className="pmc-overview__page-card">
          <RequestLoadingOverlay spinning={summaryQuery.isPending && !pageError} label="正在加载总看板，请稍候" />
          <div className="pmc-overview__title-row">
            <div>
              <h1>PMC 总看板</h1>
              <Typography.Text type="secondary">按 ItemID 汇总采购、国内仓、在途、WFS 和销量，提示断货、过剩、供应链 / 执行异常；本页只读。</Typography.Text>
            </div>
            <Space size={8} wrap>
              {summary && <Tag bordered={false}>数据日 {summary.data_date}</Tag>}
              {summary && <Tag color="gold" bordered={false}>8088 数据日快照（过渡，每周刷新）</Tag>}
              <Dropdown
                disabled={!summary || exporting}
                menu={{
                  items: [
                    { key: "all", label: `下载全部（${fmt(summary?.kpi.items)} 个 ItemID）` },
                    { key: "filtered", label: `下载当前筛选（${fmt(total)} 个 ItemID）` },
                  ],
                  onClick: ({ key }) => void download(key === "all"),
                }}
              >
                <Button type="primary" icon={<DownloadOutlined />} loading={exporting}>下载 Excel</Button>
              </Dropdown>
            </Space>
          </div>

          <Tabs
            className="pmc-overview__tabs"
            activeKey={tab}
            onChange={setTab}
            items={[
              { key: "main", label: "ItemID 主表" },
              { key: "wh", label: "仓库分布" },
              { key: "rules", label: "规则设置" },
            ]}
          />

          {tab === "main" && (
            <>
              <Card size="small" className="pmc-overview__toolbar-card">
                <OverviewToolbar
                  filters={filters}
                  options={optionsQuery.data}
                  categoryCounts={itemsQuery.data?.categoryCounts}
                  onChange={commit}
                  onReset={reset}
                  onOpenColumnConfig={() => setColumnConfigOpen(true)}
                />
              </Card>
              <OverviewSummaryCards kpi={summary?.kpi} params={params} filters={filters} onCardClick={toggleCard} />
              {pageError && (
                <Alert
                  className="pmc-overview__error"
                  type={notReady ? "warning" : "error"}
                  showIcon
                  message={overviewErrorText(pageError)}
                  action={<Button size="small" onClick={() => { void summaryQuery.refetch(); void itemsQuery.refetch(); }}>重试</Button>}
                />
              )}
              <div className="pmc-overview__table-wrap">
                <OverviewTable
                  rows={itemsQuery.data?.rows ?? []}
                  total={total}
                  loading={itemsQuery.isFetching}
                  salesMinDays={params.salesMinDays ?? 14}
                  appliedColumnKeys={columns.appliedColumnKeys}
                  columnWidths={columns.columnWidths}
                  sort={sort}
                  currentPage={currentPage}
                  pageSize={pageSize}
                  emptyTitle={pageError ? "数据未加载" : "暂无 ItemID"}
                  emptyText={emptyText}
                  onColumnWidthChange={(key, width) => persistColumns({ ...columns, columnWidths: { ...columns.columnWidths, [key]: width } })}
                  onSortChange={(next) => { setSort(next); setCurrentPage(1); }}
                  onPageChange={(nextPage, nextSize) => { setPageSize(nextSize); setCurrentPage(nextPage); }}
                  onOpenDetail={(row) => setOpenId(row.item_id)}
                />
              </div>
            </>
          )}
          {tab === "wh" && <div className="pmc-overview__tab-scroll"><OverviewWarehouseTab /></div>}
          {tab === "rules" && <div className="pmc-overview__tab-scroll"><OverviewRulesTab /></div>}
        </Card>

        <RuntimeColumnConfigDrawer
          open={columnConfigOpen}
          groups={overviewColumnGroups}
          fixedKeys={fixedOverviewColumnKeys}
          defaultKeys={overviewDefaultColumnKeys}
          appliedKeys={columns.appliedColumnKeys}
          onApply={(keys) => persistColumns({ ...columns, appliedColumnKeys: normalizeColumnKeys(keys) })}
          onClose={() => setColumnConfigOpen(false)}
          onSaveTemplate={() => void messageApi.info("列模板暂未开放；当前列配置仅保存在本浏览器")}
        />
        <OverviewFootnote open={footnoteOpen} summary={summary} onClose={() => setFootnoteOpen(false)} />
        {openId && detailQuery.data && summary && (
          <OverviewItemDrawer item={detailQuery.data} today={summary.data_date} params={params} onClose={() => setOpenId(undefined)} />
        )}
        {openId && detailQuery.error && (
          <Alert type="error" showIcon closable onClose={() => setOpenId(undefined)} message={overviewErrorText(detailQuery.error)} />
        )}
      </div>
    </PageShell>
  );
}

export default OverviewPage;
