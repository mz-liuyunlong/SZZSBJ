/** Listing-management page backed by DATA-PAGES MART API. */

import { useCallback, useEffect, useMemo, useRef, useState, type Key } from "react";
import { Card, Modal, Select, message } from "antd";

import PageShell from "@/components/page/PageShell";
import RequestLoadingOverlay from "@/components/page/RequestLoadingOverlay";
import CustomTagManagerModal, { type CustomProductTag } from "@/components/product-tags/CustomTagManagerModal";
import RuntimeColumnConfigDrawer, {
  type RuntimeColumnGroup,
} from "@/components/report-table/RuntimeColumnConfigDrawer";
import {
  REPORT_TABLE_DEFAULT_PAGE_SIZE,
  normalizeReportTablePageSize,
} from "@/components/report-table/pagination";
import { useElementScrollRestoration } from "@/shared/page-state/useElementScrollRestoration";
import { usePageStateCache } from "@/shared/page-state/pageStateCache";
import ListingAnalysisModal, { type ListingAnalysisSource } from "@/shared/listing-analysis";
import type { NavigationPage } from "@/config/navigation";

import ListingManagementSummaryCards, {
  type ListingManagementSummaryCardKey,
} from "@/pages/products/components/ListingManagementSummaryCards";
import ListingManagementTable from "@/pages/products/components/ListingManagementTable";
import ListingManagementToolbar, {
  type ListingManagementFilters,
} from "@/pages/products/components/ListingManagementToolbar";
import {
  batchSetListingTags,
  createListingTag,
  deleteListingTag,
  fetchListingManagementFilterOptions,
  fetchListingManagementRows,
  fetchListingManagementSummary,
  fetchListingTags,
  type ListingManagementFilterOptions,
  type ListingManagementSummary,
  updateListingTag,
} from "@/pages/products/listingManagementApi";
import {
  fixedListingColumnKeys,
  listingColumnFields,
  type ListingManagementRow,
} from "@/pages/products/listingManagementData";

import "@/pages/products/ListingManagementPage.css";

const TEMPLATE_PENDING = "列模板接口待接入";
const EXPORT_PENDING = "导出接口待接入";


const DEFAULT_LISTING_CUSTOM_TAGS: CustomProductTag[] = [
  { id: 1, name: "重点产品", color: "#E5484D", usage: 128 },
  { id: 2, name: "主推", color: "#1677FF", usage: 86 },
  { id: 3, name: "新品", color: "#7C5CFF", usage: 46 },
  { id: 4, name: "高利润", color: "#16A36A", usage: 31 },
  { id: 5, name: "清库存", color: "#D99000", usage: 12 },
  { id: 6, name: "待优化", color: "#667085", usage: 8 },
];


const createInitialFilters = (): ListingManagementFilters => ({
  stores: [],
  owners: [],
  productTypes: [],
  productStatuses: [],
  tagValues: [],
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
  tags: [],
};

const DEFAULT_LISTING_SUMMARY_FILTER_KEY: ListingManagementSummaryCardKey = "online";



const defaultColumnKeys = listingColumnFields.map((field) => field.key);
const defaultColumnWidths: Record<string, number> = {
  image: 72,
  productIdName: 240,
  skuMsku: 190,
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
  const [managedTags, setManagedTags] = useState<CustomProductTag[]>(DEFAULT_LISTING_CUSTOM_TAGS);
  const [batchTagOpen, setBatchTagOpen] = useState(false);
  const [batchTagValues, setBatchTagValues] = useState<string[]>([]);
  const [listingRefreshToken, setListingRefreshToken] = useState(0);
  const [tagManagerOpen, setTagManagerOpen] = useState(false);
  const [isTagManagerLoading, setIsTagManagerLoading] = useState(false);
  const pageStateKey = "listing-management";
  const listingManagementPageRootRef = useRef<HTMLDivElement | null>(null);

  const [filters, setFilters] = usePageStateCache<ListingManagementFilters>(`${pageStateKey}:filters`, createInitialFilters);
  const [statisticsVisible, setStatisticsVisible] = usePageStateCache(`${pageStateKey}:statisticsVisible`, true);
  const [summaryFilterKey, setSummaryFilterKey] = usePageStateCache<ListingManagementSummaryCardKey>(
    `${pageStateKey}:summaryFilterKey:v3`,
    DEFAULT_LISTING_SUMMARY_FILTER_KEY,
  );
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
  const [analysisSource, setAnalysisSource] = useState<ListingAnalysisSource | null>(null);
  const [isTableRequesting, setIsTableRequesting] = useState(false);

  useElementScrollRestoration(`${pageStateKey}:tableScroll`, listingManagementPageRootRef, ".ant-table-body");

  const reloadListingTags = useCallback(async (options: { showError?: boolean } = {}) => {
    setIsTagManagerLoading(true);

    try {
      const tags = await fetchListingTags();
      setManagedTags(tags);
    } catch {
      setManagedTags([]);
      if (options.showError) {
        void messageApi.warning("标签加载失败，暂时不影响 Listing 页面");
      }
    } finally {
      setIsTagManagerLoading(false);
    }
  }, [messageApi]);

  const handleCreateListingTag = useCallback(
    (payload: Parameters<typeof createListingTag>[0]) => createListingTag(payload),
    [],
  );

  const handleUpdateListingTag = useCallback(
    (tagId: string, payload: Parameters<typeof updateListingTag>[1]) => updateListingTag(tagId, payload),
    [],
  );

  const handleDeleteListingTag = useCallback(
    (tagId: string) => deleteListingTag(tagId),
    [],
  );

  useEffect(() => {
    const timer = window.setTimeout(() => {
      void reloadListingTags({ showError: false });
    }, 0);

    return () => window.clearTimeout(timer);
  }, [reloadListingTags]);

  useEffect(() => {
    if (!tagManagerOpen) return undefined;

    const timer = window.setTimeout(() => {
      void reloadListingTags({ showError: true });
    }, 0);

    return () => window.clearTimeout(timer);
  }, [reloadListingTags, tagManagerOpen]);

  const tagOptions = useMemo(() => {
    const optionMap = new Map<string, { value: string; label: string; count: number }>();

    for (const option of filterOptions.tags ?? []) {
      optionMap.set(String(option.value), {
        value: String(option.value),
        label: String(option.label ?? option.value),
        count: Number(option.count ?? 0),
      });
    }

    for (const tag of managedTags) {
      optionMap.set(tag.name, {
        value: tag.name,
        label: tag.name,
        count: tag.usage,
      });
    }

    return Array.from(optionMap.values());
  }, [filterOptions.tags, managedTags]);

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
      tagValues: filters.tagValues ?? [],
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
      summaryFilter: summaryFilterKey || DEFAULT_LISTING_SUMMARY_FILTER_KEY,
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
  }, [currentPage, listingRefreshToken, normalizedFilters, pageSize, summaryFilterKey]);

  const resetPageAndSelection = () => {
    setCurrentPage(1);
    setSelectedRowKeys([]);
  };

  const updateFilters = (nextFilters: ListingManagementFilters) => {
    setFilters(nextFilters);
    setSummaryFilterKey(DEFAULT_LISTING_SUMMARY_FILTER_KEY);
    resetPageAndSelection();
  };

  const handleSummaryCardClick = (key: ListingManagementSummaryCardKey) => {
    setSummaryFilterKey(key);
    resetPageAndSelection();
  };

  const resetFilters = () => {
    setFilters(createInitialFilters());
    setSummaryFilterKey(DEFAULT_LISTING_SUMMARY_FILTER_KEY);
    resetPageAndSelection();
  };

  const openListingAnalysis = (row: ListingManagementRow) => {
    setAnalysisSource({
      title: row.title || row.productName,
      sku: row.sku,
      msku: row.msku,
      productId: row.productId,
      date: row.listedAt || row.checkedAt,
      platform: "Walmart US",
      status: row.listingStatus || row.productStatus,
      store: row.store,
      listPrice: row.listPrice,
      salePrice: row.salePrice,
      rating: row.rating,
      reviewCount: row.reviewCount,
      wfsAvailableInventory: row.wfsAvailableInventory,
    });
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
              tags={tagOptions}
              statisticsVisible={statisticsVisible}
              onChange={updateFilters}
              onReset={resetFilters}
              onBatchSearch={(values) => updateFilters({ ...filters, batchValues: values })}
              onMessage={(content) => void messageApi.info(content)}
              onToggleStatistics={() => setStatisticsVisible((visible) => !visible)}
              onOpenTagManager={() => setTagManagerOpen(true)}
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
              onOpenDetail={openListingAnalysis}
              onBatchSetTags={() => {
                if (selectedRowKeys.length === 0) {
                  void messageApi.warning("请先选择商品");
                  return;
                }
                setBatchTagValues([]);
                setBatchTagOpen(true);
              }}
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
        <ListingAnalysisModal
          open={analysisSource !== null}
          source={analysisSource ?? undefined}
          onClose={() => setAnalysisSource(null)}
        />
      </div>
        <Modal
          title="批量设置标签"
          open={batchTagOpen}
          okText="保存"
          cancelText="取消"
          destroyOnHidden
          okButtonProps={{
            disabled: selectedRowKeys.length === 0 || batchTagValues.length === 0,
          }}
          onCancel={() => {
            setBatchTagOpen(false);
            setBatchTagValues([]);
          }}
          onOk={() => {
            if (selectedRowKeys.length === 0) {
              void messageApi.warning("请先选择商品");
              return;
            }
            if (batchTagValues.length === 0) {
              void messageApi.warning("请选择标签");
              return;
            }

            void batchSetListingTags({
              listingIds: selectedRowKeys.map(String),
              tagValues: batchTagValues,
              mode: "append",
            })
              .then(() => {
                void messageApi.success(`已给 ${selectedRowKeys.length} 个商品添加标签`);
                setBatchTagOpen(false);
                setBatchTagValues([]);
                setSelectedRowKeys([]);
                setListingRefreshToken((current) => current + 1);
                void reloadListingTags({ showError: false });
              })
              .catch(() => {
                void messageApi.error("批量设置标签失败，请确认后端接口已接入");
              });
          }}
        >
          <p className="listing-management__batch-tag-tip">
            已选择 <strong>{selectedRowKeys.length}</strong> 个商品，保存后会追加标签，不会清除原有标签。
          </p>
          <Select
            mode="multiple"
            allowClear
            showSearch
            optionFilterProp="label"
            placeholder="选择要添加的标签"
            value={batchTagValues}
            options={tagOptions}
            style={{ width: "100%" }}
            onChange={setBatchTagValues}
          />
        </Modal>
        <CustomTagManagerModal
          open={tagManagerOpen}
          initialTags={managedTags}
          loading={isTagManagerLoading}
          onCreateTag={handleCreateListingTag}
          onUpdateTag={handleUpdateListingTag}
          onDeleteTag={handleDeleteListingTag}
          onTagsChange={setManagedTags}
          onClose={() => setTagManagerOpen(false)}
        />
    </PageShell>
  );
}

export default ListingManagementPage;
