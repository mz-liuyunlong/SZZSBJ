/**
 * PMC 采购看板 (Gate 4a, read-only).
 *
 * Composition-only page: filters / paging state live here, data comes from
 * `purchaseBoardQueries`, and every visual block is a local component. The page reads the
 * approved `/api/pmc/purchase/*` contract only; no export, no push, no manual override yet
 * (the 交期修正 Modal is Gate 4b and needs `pmc:purchase:override`).
 */
import { Alert, Button, Card, Typography, message } from "antd";
import dayjs from "dayjs";
import { useEffect, useMemo, useRef } from "react";
import PageShell from "@/components/page/PageShell";
import RequestLoadingOverlay from "@/components/page/RequestLoadingOverlay";
import RuntimeColumnConfigDrawer, {
  type RuntimeColumnGroup,
} from "@/components/report-table/RuntimeColumnConfigDrawer";
import type { NavigationPage } from "@/config/navigation";
import PendingPlansDrawer from "@/pages/pmc/purchase-board/components/PendingPlansDrawer";
import PurchaseBoardMoreFiltersDrawer from "@/pages/pmc/purchase-board/components/PurchaseBoardMoreFiltersDrawer";
import PurchaseBoardSummaryCards, {
  type PurchaseBoardCardKey,
} from "@/pages/pmc/purchase-board/components/PurchaseBoardSummaryCards";
import PurchaseBoardTable from "@/pages/pmc/purchase-board/components/PurchaseBoardTable";
import PurchaseBoardToolbar from "@/pages/pmc/purchase-board/components/PurchaseBoardToolbar";
import PurchaseOrderDetailModal from "@/pages/pmc/purchase-board/components/PurchaseOrderDetailModal";
import { purchaseBoardErrorText } from "@/pages/pmc/purchase-board/purchaseBoardDisplay";
import {
  usePendingPurchasePlansQuery,
  usePurchaseBoardListQuery,
  usePurchaseBoardOwnerOptionsQuery,
  usePurchaseBoardSummaryQuery,
  usePurchaseOrderDetailQuery,
} from "@/pages/pmc/purchase-board/purchaseBoardQueries";
import {
  PURCHASE_BOARD_MAX_PAGE_SIZE,
  countMoreFilters,
  createInitialPurchaseBoardFilters,
  fixedPurchaseBoardColumnKeys,
  purchaseBoardColumnFields,
  purchaseBoardDefaultColumnWidths,
  type PurchaseBoardFilters,
  type PurchaseBoardMoreFilters,
} from "@/pages/pmc/purchase-board/purchaseBoardTypes";
import { formatDateTime } from "@/shared/formatters";
import { usePageStateCache } from "@/shared/page-state/pageStateCache";
import { readUserPreference, writeUserPreference } from "@/shared/preferences/userPreferenceCache";
import "@/pages/pmc/purchase-board/PurchaseBoardPage.css";

const COLUMN_PREFERENCE_KEY = "pmc-purchase-board:columns";
const COLUMN_PREFERENCE_VERSION = 1;
const DEFAULT_PAGE_SIZE = 50;

interface ColumnPreference {
  appliedColumnKeys: string[];
  columnWidths: Record<string, number>;
}

const defaultColumnKeys = purchaseBoardColumnFields.map((field) => field.key);
const columnGroups: RuntimeColumnGroup[] = [
  { title: "主表字段", fields: purchaseBoardColumnFields.slice(0, 9) },
  { title: "日期 / 交期 / 金额", fields: purchaseBoardColumnFields.slice(9) },
];

const normalizeColumnKeys = (keys: string[]) => {
  const allowed = new Set(defaultColumnKeys);
  const merged = keys.filter((key) => allowed.has(key));
  for (const key of fixedPurchaseBoardColumnKeys) if (!merged.includes(key)) merged.unshift(key);
  return merged;
};

/** Card → filter mapping (display convenience only; the backend owns the definitions). */
const filtersForCard = (
  key: PurchaseBoardCardKey,
  current: PurchaseBoardFilters,
): PurchaseBoardFilters => {
  const base = { ...createInitialPurchaseBoardFilters(), ownerUids: current.ownerUids };
  switch (key) {
    case "awaiting_arrival":
      return { ...base, statuses: ["s3", "s4"] };
    case "arrival_overdue":
      return { ...base, statuses: ["overdue"], sort: "overdue_days_desc" };
    case "purchase_overdue":
      return { ...base, statuses: ["s2"], sort: "overdue_days_desc" };
    case "month_amount":
      return {
        ...base,
        orderDateFrom: dayjs().startOf("month").format("YYYY-MM-DD"),
        orderDateTo: dayjs().format("YYYY-MM-DD"),
      };
    case "itemid_pending":
      return { ...base, itemIdSources: ["pending_packing_slip", "unresolved"] };
    case "average_cycle":
    case "unstable_sku":
    default:
      return base;
  }
};

interface PurchaseBoardPageProps {
  page: NavigationPage;
  preferenceScope?: string;
}

function PurchaseBoardPage({ page, preferenceScope = "anonymous" }: PurchaseBoardPageProps) {
  const [messageApi, messageContextHolder] = message.useMessage();
  const stateKey = `pmc-purchase-board:${preferenceScope}`;
  const rootRef = useRef<HTMLDivElement | null>(null);

  const [filters, setFilters] = usePageStateCache(`${stateKey}:filters`, createInitialPurchaseBoardFilters);
  const [activeCard, setActiveCard] = usePageStateCache<PurchaseBoardCardKey | undefined>(`${stateKey}:activeCard`, undefined);
  const [currentPage, setCurrentPage] = usePageStateCache(`${stateKey}:page`, 1);
  const [pageSize, setPageSize] = usePageStateCache(`${stateKey}:pageSize`, DEFAULT_PAGE_SIZE);
  const [detailOrderSn, setDetailOrderSn] = usePageStateCache<string | undefined>(`${stateKey}:detail`, undefined);
  const [moreFiltersOpen, setMoreFiltersOpen] = usePageStateCache(`${stateKey}:moreFilters`, false);
  const [columnConfigOpen, setColumnConfigOpen] = usePageStateCache(`${stateKey}:columnConfig`, false);
  const [pendingOpen, setPendingOpen] = usePageStateCache(`${stateKey}:pendingOpen`, false);
  const [pendingPage, setPendingPage] = usePageStateCache(`${stateKey}:pendingPage`, 1);
  const [pendingPageSize, setPendingPageSize] = usePageStateCache(`${stateKey}:pendingPageSize`, DEFAULT_PAGE_SIZE);
  const [pendingOverdueOnly, setPendingOverdueOnly] = usePageStateCache(`${stateKey}:pendingOverdueOnly`, false);

  const initialColumns = useMemo(() => {
    const stored = readUserPreference<ColumnPreference>(preferenceScope, COLUMN_PREFERENCE_KEY, COLUMN_PREFERENCE_VERSION);
    return {
      appliedColumnKeys: normalizeColumnKeys(stored?.appliedColumnKeys ?? defaultColumnKeys),
      columnWidths: { ...purchaseBoardDefaultColumnWidths, ...stored?.columnWidths },
    } satisfies ColumnPreference;
  }, [preferenceScope]);
  const [columnPreference, setColumnPreference] = usePageStateCache<ColumnPreference>(`${stateKey}:columns`, initialColumns);

  const listQuery = usePurchaseBoardListQuery(filters, currentPage, pageSize);
  const summaryQuery = usePurchaseBoardSummaryQuery(filters);
  const ownersQuery = usePurchaseBoardOwnerOptionsQuery();
  const detailQuery = usePurchaseOrderDetailQuery(detailOrderSn);
  const pendingQuery = usePendingPurchasePlansQuery(
    { page: pendingPage, pageSize: pendingPageSize, overdueOnly: pendingOverdueOnly },
    pendingOpen,
  );

  const rows = listQuery.data?.rows ?? [];
  const total = listQuery.data?.total ?? 0;
  const meta = listQuery.data?.meta ?? summaryQuery.data?.meta;
  const isRequesting = listQuery.isFetching || summaryQuery.isFetching;

  const shownErrorsRef = useRef(new Set<string>());
  useEffect(() => {
    for (const reason of [summaryQuery.error, ownersQuery.error]) {
      if (!reason) continue;
      const text = purchaseBoardErrorText(reason);
      if (shownErrorsRef.current.has(text)) continue;
      shownErrorsRef.current.add(text);
      void messageApi.error(text);
    }
  }, [messageApi, ownersQuery.error, summaryQuery.error]);

  const commitFilters = (next: PurchaseBoardFilters, card?: PurchaseBoardCardKey) => {
    setFilters(next);
    setActiveCard(card);
    setCurrentPage(1);
  };

  const resetFilters = () => commitFilters(createInitialPurchaseBoardFilters());

  const persistColumns = (next: ColumnPreference) => {
    setColumnPreference(next);
    writeUserPreference(preferenceScope, COLUMN_PREFERENCE_KEY, COLUMN_PREFERENCE_VERSION, next);
  };

  const moreFilters: PurchaseBoardMoreFilters = {
    itemIdSources: filters.itemIdSources,
    qtyMin: filters.qtyMin,
    qtyMax: filters.qtyMax,
    priceMin: filters.priceMin,
    priceMax: filters.priceMax,
    wfsNotReady: filters.wfsNotReady,
  };

  const listErrorText = listQuery.error ? purchaseBoardErrorText(listQuery.error) : undefined;
  const emptyText = listErrorText
    ?? (filters.keyword || filters.batchValues?.length
      ? "当前搜索条件下没有匹配的采购单明细。"
      : "当前筛选下没有采购单明细；若刚接入，请等待 DWS 刷新完成。");

  return (
    <PageShell
      page={page}
      headerActions={(
        <Button onClick={() => setPendingOpen(true)}>待采购计划</Button>
      )}
    >
      {messageContextHolder}
      <div ref={rootRef} className="purchase-board">
        <Card size="small" className="purchase-board__page-card">
          <RequestLoadingOverlay spinning={isRequesting && !listQuery.data} label="正在加载采购看板，请稍候" />
          <div className="purchase-board__title-row">
            <div>
              <h1>采购看板</h1>
              <p>
                采购单明细 × 计划的进度、逾期、ItemID 归属与交期看板；只读 DWS，不含未转单的采购计划。
                {meta?.freshnessAt && (
                  <Typography.Text type="secondary" className="purchase-board__freshness">
                    数据更新 {formatDateTime(meta.freshnessAt)}
                    {meta.ruleVersion !== null && meta.ruleVersion !== undefined ? ` · 规则版本 v${meta.ruleVersion}` : ""}
                  </Typography.Text>
                )}
              </p>
            </div>
          </div>

          <Card size="small" className="purchase-board__toolbar-card">
            <PurchaseBoardToolbar
              filters={filters}
              owners={ownersQuery.data ?? []}
              ownersLoading={ownersQuery.isPending}
              moreFilterCount={countMoreFilters(moreFilters)}
              onChange={(next) => commitFilters(next)}
              onBatchSearch={(values, searchType) => commitFilters({
                ...filters,
                searchType,
                keyword: "",
                batchValues: values,
              })}
              onReset={resetFilters}
              onMessage={(content) => void messageApi.info(content)}
              onOpenMoreFilters={() => setMoreFiltersOpen(true)}
              onOpenColumnConfig={() => setColumnConfigOpen(true)}
            />
          </Card>

          <PurchaseBoardSummaryCards
            summary={summaryQuery.data}
            activeKey={activeCard}
            onCardClick={(key) => {
              if (activeCard === key) {
                resetFilters();
                return;
              }
              commitFilters(filtersForCard(key, filters), key);
            }}
          />

          {listErrorText && (
            <Alert
              className="purchase-board__error"
              type={listQuery.error && (listQuery.error as { status?: number }).status === 403 ? "warning" : "error"}
              showIcon
              message={listErrorText}
            />
          )}

          <div className="purchase-board__table-wrap">
            <PurchaseBoardTable
              rows={rows}
              total={total}
              appliedColumnKeys={columnPreference.appliedColumnKeys}
              columnWidths={columnPreference.columnWidths}
              currentPage={currentPage}
              pageSize={pageSize}
              emptyText={emptyText}
              onColumnWidthChange={(key, width) => persistColumns({
                ...columnPreference,
                columnWidths: { ...columnPreference.columnWidths, [key]: width },
              })}
              onCurrentPageChange={setCurrentPage}
              onPageSizeChange={(next) => {
                setPageSize(Math.min(next, PURCHASE_BOARD_MAX_PAGE_SIZE));
                setCurrentPage(1);
              }}
              onOpenDetail={(row) => setDetailOrderSn(row.purchaseOrderSn)}
            />
          </div>
        </Card>

        <PurchaseBoardMoreFiltersDrawer
          open={moreFiltersOpen}
          value={moreFilters}
          onApply={(value) => {
            commitFilters({ ...filters, ...value });
            setMoreFiltersOpen(false);
          }}
          onClose={() => setMoreFiltersOpen(false)}
        />
        <RuntimeColumnConfigDrawer
          open={columnConfigOpen}
          groups={columnGroups}
          fixedKeys={fixedPurchaseBoardColumnKeys}
          defaultKeys={defaultColumnKeys}
          appliedKeys={columnPreference.appliedColumnKeys}
          onApply={(keys) => persistColumns({ ...columnPreference, appliedColumnKeys: normalizeColumnKeys(keys) })}
          onClose={() => setColumnConfigOpen(false)}
          onSaveTemplate={() => void messageApi.info("列模板暂未开放；当前列配置仅保存在本浏览器")}
        />
        <PurchaseOrderDetailModal
          orderSn={detailOrderSn}
          detail={detailQuery.data}
          loading={detailQuery.isFetching}
          errorText={detailQuery.error ? purchaseBoardErrorText(detailQuery.error) : undefined}
          onClose={() => setDetailOrderSn(undefined)}
        />
        <PendingPlansDrawer
          open={pendingOpen}
          data={pendingQuery.data}
          loading={pendingQuery.isFetching}
          errorText={pendingQuery.error ? purchaseBoardErrorText(pendingQuery.error) : undefined}
          page={pendingPage}
          pageSize={pendingPageSize}
          overdueOnly={pendingOverdueOnly}
          onPageChange={(nextPage, nextPageSize) => {
            setPendingPage(nextPageSize !== pendingPageSize ? 1 : nextPage);
            setPendingPageSize(Math.min(nextPageSize, PURCHASE_BOARD_MAX_PAGE_SIZE));
          }}
          onOverdueOnlyChange={(checked) => {
            setPendingOverdueOnly(checked);
            setPendingPage(1);
          }}
          onClose={() => setPendingOpen(false)}
        />
      </div>
    </PageShell>
  );
}

export default PurchaseBoardPage;
