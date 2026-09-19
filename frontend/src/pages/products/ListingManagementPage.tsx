/** Listing-management page backed by DATA-PAGES MART API. */
import { Card, message } from "antd";
import { useEffect, useMemo, useRef, useState, type Key } from "react";
import PageShell from "@/components/page/PageShell";
import RequestLoadingOverlay from "@/components/page/RequestLoadingOverlay";
import { usePageStateCache } from "@/shared/page-state/pageStateCache";
import { useElementScrollRestoration } from "@/shared/page-state/useElementScrollRestoration";
import RuntimeColumnConfigDrawer, {
  type RuntimeColumnGroup,
} from "@/components/report-table/RuntimeColumnConfigDrawer";
import {
  REPORT_TABLE_DEFAULT_PAGE_SIZE,
  normalizeReportTablePageSize,
} from "@/components/report-table/pagination";
import type { NavigationPage } from "@/config/navigation";
import ListingDetailModal from "@/pages/products/components/ListingDetailModal";
import ListingManagementSummaryCards, {
  type ListingManagementSummaryCardKey,
} from "@/pages/products/components/ListingManagementSummaryCards";
import ListingManagementTable from "@/pages/products/components/ListingManagementTable";
import ListingManagementToolbar, {
  type ListingManagementFilters,
} from "@/pages/products/components/ListingManagementToolbar";
import {
  fetchListingManagementFilterOptions,
  fetchListingManagementRows,
  fetchListingManagementSummary,
  type ListingManagementFilterOptions,
  type ListingManagementSummary,
} from "@/pages/products/listingManagementApi";
import {
  fixedListingColumnKeys,
  listingColumnFields,
  type ListingManagementRow,
} from "@/pages/products/listingManagementData";
import "@/pages/products/ListingManagementPage.css";

const TEMPLATE_PENDING = "列模板接口待接入";
const EXPORT_PENDING = "导出接口待接入";

const createInitialFilters = (): ListingManagementFilters => ({
  stores: [],
  owners: [],
  productTypes: [],
  productStatuses: [],
  searchType: "sku",
  keyword: "",
});

const emptySummary: ListingManagementSummary = {
  total: 0,
  online: 0,
  buyboxException: 0,
  ratingWarning: 0,
  resoldWarning: 0,
  strikePriceException: 0,
};

const emptyFilterOptions: ListingManagementFilterOptions = {
  stores: [],
  owners: [],
  productTypes: [],
};

const defaultColumnKeys = listingColumnFields.map((field) => field.key);
const defaultColumnWidths: Record<string, number> = {
  image: 72,
  msku: 130,
  productId: 150,
  store: 120,
  owner: 110,
  sku: 130,
  productName: 190,
  title: 260,
  productType: 130,
  listPrice: 110,
  salePrice: 110,
  productStatus: 120,
  lifecycle: 120,
  listedAt: 140,
  category: 120,
  wfsAvailableInventory: 140,
  inboundInventory: 130,
  sales90Days: 130,
  adSpend30Days: 140,
  disabledReason: 130,
  listingStatus: 130,
  buyBoxStatus: 130,
  walmartSeller: 140,
  resold: 120,
  checkedAt: 160,
  rating: 100,
  reviewCount: 110,
  brand: 130,
  tags: 130,
  gtin: 160,
  productGrade: 120,
  actions: 112,
};

const columnGroups: RuntimeColumnGroup[] = [
  { title: "Listing 管理字段", fields: [...listingColumnFields] },
];

interface ListingManagementPageProps {
  page: NavigationPage;
}

function ListingManagementPage({ page }: ListingManagementPageProps) {
  const [messageApi, messageContextHolder] = message.useMessage();
  const pageStateKey = "listing-management";
  const listingManagementPageRootRef = useRef<HTMLDivElement | null>(null);

  const [filters, setFilters] = usePageStateCache<ListingManagementFilters>(`${pageStateKey}:filters`, createInitialFilters);
  const [statisticsVisible, setStatisticsVisible] = usePageStateCache(`${pageStateKey}:statisticsVisible`, true);
  const [summaryFilterKey, setSummaryFilterKey] = usePageStateCache<ListingManagementSummaryCardKey>(`${pageStateKey}:summaryFilterKey`, "total");
  const [columnConfigOpen, setColumnConfigOpen] = usePageStateCache(`${pageStateKey}:columnConfigOpen`, false);
  const [appliedColumnKeys, setAppliedColumnKeys] = usePageStateCache<string[]>(`${pageStateKey}:appliedColumnKeys`, defaultColumnKeys);
  const [columnWidths, setColumnWidths] = usePageStateCache<Record<string, number>>(`${pageStateKey}:columnWidths`, defaultColumnWidths);
  const [currentPage, setCurrentPage] = usePageStateCache(`${pageStateKey}:currentPage`, 1);
  const [pageSize, setPageSize] = usePageStateCache(`${pageStateKey}:pageSize`, REPORT_TABLE_DEFAULT_PAGE_SIZE);
  const [selectedRowKeys, setSelectedRowKeys] = usePageStateCache<Key[]>(`${pageStateKey}:selectedRowKeys`, []);

  const [rows, setRows] = useState<ListingManagementRow[]>([]);
  const [totalRows, setTotalRows] = useState(0);
  const [summary, setSummary] = useState<ListingManagementSummary>(emptySummary);
  const [filterOptions, setFilterOptions] = useState<ListingManagementFilterOptions>(emptyFilterOptions);
  const [detailRow, setDetailRow] = useState<ListingManagementRow>();
  const [isTableRequesting, setIsTableRequesting] = useState(false);

  useElementScrollRestoration(`${pageStateKey}:tableScroll`, listingManagementPageRootRef, ".ant-table-body");

  const normalizedFilters = useMemo(() => {
    const owners = filters.owners && filters.owners.length > 0
      ? filters.owners
      : filters.owner ? [filters.owner] : [];
    const productTypes = filters.productTypes && filters.productTypes.length > 0
      ? filters.productTypes
      : filters.productType ? [filters.productType] : [];
    const productStatuses = filters.productStatuses && filters.productStatuses.length > 0
      ? filters.productStatuses
      : filters.productStatus ? [filters.productStatus] : [];

    return {
      stores: filters.stores ?? [],
      owners,
      productTypes,
      productStatuses,
      searchType: filters.searchType,
      keyword: filters.keyword,
      batchValues: filters.batchValues,
    };
  }, [filters]);

  useEffect(() => {
    let active = true;

    void fetchListingManagementFilterOptions()
      .then((options) => {
        if (!active) return;
        setFilterOptions(options);
      })
      .catch(() => {
        if (!active) return;
        setFilterOptions(emptyFilterOptions);
      });

    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    let active = true;

    void fetchListingManagementSummary(normalizedFilters)
      .then((nextSummary) => {
        if (!active) return;
        setSummary(nextSummary);
      })
      .catch(() => {
        if (!active) return;
        setSummary(emptySummary);
      });

    return () => {
      active = false;
    };
  }, [normalizedFilters]);

  useEffect(() => {
    let active = true;

    queueMicrotask(() => {
      if (active) setIsTableRequesting(true);
    });

    void fetchListingManagementRows({
      ...normalizedFilters,
      summaryFilter: summaryFilterKey,
      page: currentPage,
      pageSize,
    })
      .then(({ rows: nextRows, meta }) => {
        if (!active) return;
        setRows(nextRows);
        setTotalRows(meta.total);
      })
      .catch(() => {
        if (!active) return;
        setRows([]);
        setTotalRows(0);
      })
      .finally(() => {
        if (active) setIsTableRequesting(false);
      });

    return () => {
      active = false;
    };
  }, [currentPage, normalizedFilters, pageSize, summaryFilterKey]);

  const resetPageAndSelection = () => {
    setCurrentPage(1);
    setSelectedRowKeys([]);
  };

  const updateFilters = (nextFilters: ListingManagementFilters) => {
    setFilters(nextFilters);
    setSummaryFilterKey("total");
    resetPageAndSelection();
  };

  const handleSummaryCardClick = (key: ListingManagementSummaryCardKey) => {
    setSummaryFilterKey(key);
    resetPageAndSelection();
  };

  const resetFilters = () => {
    setFilters(createInitialFilters());
    setSummaryFilterKey("total");
    resetPageAndSelection();
  };

  return (
    <PageShell page={page}>
      {messageContextHolder}
      <div ref={listingManagementPageRootRef} className="listing-management">
        <Card size="small" className="listing-management__page-card">
          <RequestLoadingOverlay spinning={isTableRequesting} label="正在加载Listing数据，请稍候" />
          <div className="listing-management__title-row">
            <div>
              <h1>Listing管理</h1>
              <p>覆盖店铺、负责人、状态、价格、库存、购物车、跟卖与检查信息。</p>
            </div>
          </div>

          <Card size="small" className="listing-management__toolbar-card">
            <ListingManagementToolbar
              filters={filters}
              stores={filterOptions.stores}
              owners={filterOptions.owners}
              productTypes={filterOptions.productTypes}
              statisticsVisible={statisticsVisible}
              onChange={updateFilters}
              onReset={resetFilters}
              onBatchSearch={(values) => updateFilters({ ...filters, batchValues: values })}
              onMessage={(content) => void messageApi.info(content)}
              onToggleStatistics={() => setStatisticsVisible((visible) => !visible)}
              onOpenColumnConfig={() => setColumnConfigOpen(true)}
              onDownload={() => void messageApi.info(EXPORT_PENDING)}
            />
          </Card>

          {statisticsVisible && (
            <ListingManagementSummaryCards
              summary={summary}
              activeKey={summaryFilterKey}
              onCardClick={handleSummaryCardClick}
            />
          )}

          <div className="listing-management__table-wrap">
            <ListingManagementTable
              rows={rows}
              total={totalRows}
              appliedColumnKeys={appliedColumnKeys}
              columnWidths={columnWidths}
              currentPage={currentPage}
              pageSize={pageSize}
              selectedRowKeys={selectedRowKeys}
              onColumnWidthChange={(key, width) => setColumnWidths((current) => ({
                ...current,
                [key]: width,
              }))}
              onCurrentPageChange={setCurrentPage}
              onPageSizeChange={(nextPageSize) => {
                setPageSize(normalizeReportTablePageSize(nextPageSize));
                resetPageAndSelection();
              }}
              onSelectionChange={setSelectedRowKeys}
              onOpenDetail={setDetailRow}
              onBulkExport={() => void messageApi.info(EXPORT_PENDING)}
            />
          </div>
        </Card>

        <RuntimeColumnConfigDrawer
          open={columnConfigOpen}
          groups={columnGroups}
          fixedKeys={fixedListingColumnKeys}
          defaultKeys={defaultColumnKeys}
          appliedKeys={appliedColumnKeys}
          onApply={setAppliedColumnKeys}
          onClose={() => setColumnConfigOpen(false)}
          onSaveTemplate={() => void messageApi.info(TEMPLATE_PENDING)}
        />
        <ListingDetailModal row={detailRow} onClose={() => setDetailRow(undefined)} />
      </div>
    </PageShell>
  );
}

export default ListingManagementPage;
