import { Card, message } from "antd";
import { useEffect, useMemo, useRef, useState, type Key } from "react";
import PageShell from "@/components/page/PageShell";
import RequestLoadingOverlay from "@/components/page/RequestLoadingOverlay";
import RuntimeColumnConfigDrawer, {
  type RuntimeColumnGroup,
} from "@/components/report-table/RuntimeColumnConfigDrawer";
import {
  REPORT_TABLE_DEFAULT_PAGE_SIZE,
  normalizeReportTablePageSize,
} from "@/components/report-table/pagination";
import type { NavigationPage } from "@/config/navigation";
import ProductDetailModal from "@/pages/products/components/ProductDetailModal";
import ListExportModal, {
  type ListExportColumnGroup,
} from "@/pages/products/components/ListExportModal";
import ProductManagementSummaryCards from "@/pages/products/components/ProductManagementSummaryCards";
import ProductManagementTable from "@/pages/products/components/ProductManagementTable";
import ProductManagementToolbar from "@/pages/products/components/ProductManagementToolbar";
import { requestProductManagementExport } from "@/pages/products/productManagementApi";
import {
  useProductManagementDetailQuery,
  useProductManagementListQuery,
  useProductManagementOptionsQuery,
  usePrefetchProductManagementList,
  useProductManagementSummaryQuery,
  useProductManagementTableViewQuery,
  useSaveProductManagementTableViewMutation,
} from "@/pages/products/productManagementQueries";
import {
  fixedProductColumnKeys,
  productColumnFields,
  type ProductManagementFilters,
  type ProductManagementSummary,
} from "@/pages/products/productManagementTypes";
import {
  readUserPreference,
  removeUserPreference,
  writeUserPreference,
} from "@/shared/preferences/userPreferenceCache";
import { usePageStateCache } from "@/shared/page-state/pageStateCache";
import { useDebouncedValue } from "@/shared/hooks/useDebouncedValue";
import { useElementScrollRestoration } from "@/shared/page-state/useElementScrollRestoration";
import { applyProductBasicCompleteness } from "@/pages/products/productBasicCompleteness";
import "@/pages/products/ProductManagementPage.css";

const TABLE_VIEW_PREFERENCE_KEY = "product-management:table-view";
const TABLE_VIEW_SCHEMA_VERSION = 1;

interface ProductTablePreference {
  appliedColumnKeys: string[];
  columnWidths: Record<string, number>;
}

const createInitialFilters = (): ProductManagementFilters => ({
  searchType: "sku",
  keyword: "",
});

const hiddenProductColumnKeys = new Set<string>([
  "category",
  "linkedPlatformSkuCount",
  "wfsDeliveryFee",
  "wfsFulfillmentFee",
  "wfsShippingFee",
  "wfsFee",
  "tags",
  "internalTags",
  "internalTag",
  "suggestedPrice",
  "minimumPrice",
  "productGrade",
  "updatedAt",
  "dataCompleteness",
]);
const configurableProductColumnFields = productColumnFields.filter(
  (field) => !hiddenProductColumnKeys.has(field.key),
);
const defaultColumnKeys = configurableProductColumnFields.map((field) => field.key);

const normalizeProductColumnKeys = (keys: string[]) => {
  const allowedKeys = new Set<string>(configurableProductColumnFields.map((field) => field.key));
  const normalizedKeys = keys.filter(
    (key) => allowedKeys.has(key) && !hiddenProductColumnKeys.has(key),
  );
  const mergedKeys = [...normalizedKeys];
  for (const key of defaultColumnKeys) {
    if (!mergedKeys.includes(key)) mergedKeys.push(key);
  }
  return mergedKeys;
};

const defaultColumnWidths: Record<string, number> = {
  image: 72,
  sku: 170,
  productName: 240,
  ownerName: 120,
  developerName: 120,
  tags: 132,
  sourceTags: 132,
  productGrade: 116,
  wfsFee: 118,
  suggestedPrice: 128,
  minimumPrice: 128,
  clearancePrice: 128,
  category: 128,
  purchasePrice: 128,
  firstLegFreight: 128,
  wfsDeliveryFee: 128,
  purchaseLeadTime: 128,
  storageFee: 118,
  linkedPlatformSkuCount: 132,
  dataCompleteness: 132,
  updatedAt: 168,
  actions: 112,
};
const columnGroups: RuntimeColumnGroup[] = [
  { title: "默认主表字段", fields: [...configurableProductColumnFields.slice(0, 8)] },
  { title: "可选基本信息字段", fields: [...configurableProductColumnFields.slice(8)] },
];

const productExportColumnGroups: ListExportColumnGroup[] = [
  {
    title: "基础信息",
    fields: [
      { key: "sku", label: "SKU" },
      { key: "product_name", label: "品名" },
      { key: "category", label: "类目" },
      { key: "product_grade", label: "产品等级" },
      { key: "owner", label: "负责人" },
      { key: "developer", label: "开发" },
      { key: "tags", label: "标签" },
      { key: "source_tags", label: "来源标签" },
    ],
  },
  {
    title: "资料状态",
    fields: [
      { key: "image_count", label: "图片数" },
      { key: "listing_count", label: "Listing数" },
      { key: "completeness_status", label: "资料完整状态" },
      { key: "missing_codes", label: "缺失项" },
      { key: "observed_at", label: "最近观测时间" },
      { key: "calculated_at", label: "计算时间" },
    ],
  },
  {
    title: "计价状态",
    fields: [
      { key: "calculation_status", label: "计价状态" },
      { key: "wfs_status", label: "WFS状态" },
      { key: "storage_status", label: "仓储状态" },
      { key: "first_leg_status", label: "头程状态" },
    ],
  },
  {
    title: "成本价格",
    fields: [
      { key: "purchase_cost_cny", label: "采购价(CNY)" },
      { key: "first_leg_fee_cny", label: "头程费(CNY)" },
      { key: "wfs_fulfillment_fee", label: "WFS配送费" },
      { key: "storage_fee_usd", label: "仓储费(USD)" },
      { key: "suggested_price_usd", label: "建议售价(USD)" },
      { key: "minimum_price_usd", label: "最低售价(USD)" },
      { key: "clearance_price_usd", label: "清仓价(USD)" },
    ],
  },
];

const productDefaultExportColumnKeys = productExportColumnGroups.flatMap((group) =>
  group.fields.map((field) => field.key),
);

const emptySummary: ProductManagementSummary = {
  total: 0,
  syncedDetailCount: 0,
  dataCompletenessRate: 0,
  withImageCount: 0,
  withSourceTagCount: 0,
  incompleteCount: 0,
  missingPurchaseCostCount: 0,
  missingPurchaseDeliveryCount: 0,
  missingGrossWeightCount: 0,
  missingPackageDimensionsCount: 0,
  missingImageCount: 0,
  missingDimensionImageCount: 0,
  invalidPricingRuleCount: 0,
  pricingOkCount: 0,
};

interface ProductManagementPageProps {
  page: NavigationPage;
  preferenceScope?: string;
}

function ProductManagementPage({
  page,
  preferenceScope = "anonymous",
}: ProductManagementPageProps) {
  const [messageApi, messageContextHolder] = message.useMessage();
  const messageApiRef = useRef(messageApi);
  const pageStateKey = `product-management:${preferenceScope}`;
  const productPageRootRef = useRef<HTMLDivElement | null>(null);
  const initialPreference = useMemo(
    () => readUserPreference<ProductTablePreference>(
      preferenceScope,
      TABLE_VIEW_PREFERENCE_KEY,
      TABLE_VIEW_SCHEMA_VERSION,
    ),
    [preferenceScope],
  );
  const [filters, setFilters] = usePageStateCache(`${pageStateKey}:filters`, createInitialFilters);
  const [statisticsVisible, setStatisticsVisible] = usePageStateCache(`${pageStateKey}:statisticsVisible`, false);
  const [columnConfigOpen, setColumnConfigOpen] = usePageStateCache(`${pageStateKey}:columnConfigOpen`, false);
  const [columnPreferenceOverride, setColumnPreferenceOverride] = usePageStateCache<{
    scope: string;
    value: ProductTablePreference;
  } | undefined>(`${pageStateKey}:columnPreferenceOverride`, undefined);
  const [currentPage, setCurrentPage] = usePageStateCache(`${pageStateKey}:currentPage`, 1);
  const [pageSize, setPageSize] = usePageStateCache(`${pageStateKey}:pageSize`, REPORT_TABLE_DEFAULT_PAGE_SIZE);
  const [selectedRowKeys, setSelectedRowKeys] = usePageStateCache<Key[]>(`${pageStateKey}:selectedRowKeys`, []);
  const [detailRowId, setDetailRowId] = usePageStateCache<string | undefined>(`${pageStateKey}:detailRowId`, undefined);
  const [exportModalOpen, setExportModalOpen] = useState(false);
  const [isExporting, setIsExporting] = useState(false);

  useEffect(() => {
    messageApiRef.current = messageApi;
  }, [messageApi]);

  const debouncedFilters = useDebouncedValue(filters, 350);
  const isFilterDebouncing = debouncedFilters !== filters;
  const listQuery = useProductManagementListQuery(debouncedFilters, currentPage, pageSize);
  const prefetchProductList = usePrefetchProductManagementList();
  const summaryQuery = useProductManagementSummaryQuery(debouncedFilters, statisticsVisible);
  const optionsQuery = useProductManagementOptionsQuery(debouncedFilters);
  useElementScrollRestoration(`${pageStateKey}:tableScroll`, productPageRootRef, ".ant-table-body");
  const tableViewQuery = useProductManagementTableViewQuery();
  const saveTableView = useSaveProductManagementTableViewMutation();
  const serverColumnPreference = useMemo<ProductTablePreference>(() => {
    if (tableViewQuery.data) {
      return {
        appliedColumnKeys: normalizeProductColumnKeys(tableViewQuery.data.applied_column_keys),
        columnWidths: { ...defaultColumnWidths, ...tableViewQuery.data.column_widths },
      };
    }
    return {
      appliedColumnKeys: normalizeProductColumnKeys(
        initialPreference?.appliedColumnKeys ?? defaultColumnKeys,
      ),
      columnWidths: { ...defaultColumnWidths, ...initialPreference?.columnWidths },
    };
  }, [initialPreference, tableViewQuery.data]);
  const activeColumnPreference = columnPreferenceOverride?.scope === preferenceScope
    ? columnPreferenceOverride.value
    : serverColumnPreference;
  const appliedColumnKeys = activeColumnPreference.appliedColumnKeys;
  const columnWidths = activeColumnPreference.columnWidths;

  const rows = useMemo(
    () => applyProductBasicCompleteness(listQuery.data?.rows ?? []),
    [listQuery.data?.rows],
  );
  const total = listQuery.data?.total ?? 0;
  const detailBaseRow = rows.find((row) => row.id === detailRowId);
  const detailQuery = useProductManagementDetailQuery(detailBaseRow);
  const detailRow = detailQuery.data ?? detailBaseRow;
  const summary = summaryQuery.data ?? { ...emptySummary, total };
  const isTableRequesting = isFilterDebouncing
    || listQuery.isFetching
    || optionsQuery.isFetching
    || (statisticsVisible && summaryQuery.isFetching)
    || saveTableView.isPending;
  const owners = optionsQuery.data?.owners ?? [];
  const developers = optionsQuery.data?.developers ?? [];
  const tags = optionsQuery.data?.tags ?? [];

  useEffect(() => {
    if (total <= currentPage * pageSize) return;
    void prefetchProductList(debouncedFilters, currentPage + 1, pageSize);
  }, [currentPage, debouncedFilters, pageSize, prefetchProductList, total]);

  useEffect(() => {
    if (!tableViewQuery.data) return;
    writeUserPreference<ProductTablePreference>(
      preferenceScope,
      TABLE_VIEW_PREFERENCE_KEY,
      tableViewQuery.data.schema_version,
      serverColumnPreference,
    );
  }, [preferenceScope, serverColumnPreference, tableViewQuery.data]);

  const shownErrorsRef = useRef(new Set<string>());
  useEffect(() => {
    const candidates: unknown[] = [
      listQuery.error,
      optionsQuery.error,
      statisticsVisible ? summaryQuery.error : null,
      detailRowId ? detailQuery.error : null,
    ];
    for (const reason of candidates) {
      if (!reason) continue;
      const text = reason instanceof Error ? reason.message : "BACKEND_REQUEST_FAILED";
      if (shownErrorsRef.current.has(text)) continue;
      shownErrorsRef.current.add(text);
      void messageApiRef.current.error(text);
    }
  }, [
    detailQuery.error,
    detailRowId,
    listQuery.error,
    optionsQuery.error,
    statisticsVisible,
    summaryQuery.error,
  ]);

  const resetPageAndSelection = () => {
    setCurrentPage(1);
    setSelectedRowKeys([]);
  };

  const updateFilters = (nextFilters: ProductManagementFilters) => {
    setFilters(nextFilters);
    resetPageAndSelection();
  };

  const resetFilters = () => {
    setFilters(createInitialFilters());
    resetPageAndSelection();
  };

  const openExportModal = () => {
    setExportModalOpen(true);
  };

  const closeExportModal = () => {
    if (isExporting) return;
    setExportModalOpen(false);
  };

  const handleExport = async (columnKeys: string[]) => {
    if (isExporting) return;
    setIsExporting(true);

    try {
      await requestProductManagementExport(filters, columnKeys);
      setExportModalOpen(false);
      void messageApi.success("产品管理导出已开始下载");
    } catch (reason: unknown) {
      void messageApi.error(
        reason instanceof Error ? reason.message : "PRODUCT_MANAGEMENT_EXPORT_FAILED",
      );
    } finally {
      setIsExporting(false);
    }
  };

  const persistColumns = (nextKeys: string[]) => {
    const normalizedKeys = normalizeProductColumnKeys(nextKeys);
    const previousPreference: ProductTablePreference = {
      appliedColumnKeys,
      columnWidths,
    };
    const nextPreference: ProductTablePreference = {
      appliedColumnKeys: normalizedKeys,
      columnWidths,
    };
    setColumnPreferenceOverride({ scope: preferenceScope, value: nextPreference });
    writeUserPreference<ProductTablePreference>(
      preferenceScope,
      TABLE_VIEW_PREFERENCE_KEY,
      TABLE_VIEW_SCHEMA_VERSION,
      nextPreference,
    );
    saveTableView.mutate(
      { appliedColumnKeys: normalizedKeys, columnWidths },
      {
        onSuccess: (view) => {
          const savedPreference: ProductTablePreference = {
            appliedColumnKeys: normalizeProductColumnKeys(view.applied_column_keys),
            columnWidths: { ...defaultColumnWidths, ...view.column_widths },
          };
          setColumnPreferenceOverride({ scope: preferenceScope, value: savedPreference });
          writeUserPreference<ProductTablePreference>(
            preferenceScope,
            TABLE_VIEW_PREFERENCE_KEY,
            view.schema_version,
            savedPreference,
          );
          void messageApi.success("列配置已保存");
        },
        onError: (reason) => {
          setColumnPreferenceOverride({ scope: preferenceScope, value: previousPreference });
          removeUserPreference(preferenceScope, TABLE_VIEW_PREFERENCE_KEY);
          void messageApi.error(reason instanceof Error ? reason.message : "BACKEND_REQUEST_FAILED");
        },
      },
    );
  };

  return (
    <PageShell page={page}>
      {messageContextHolder}
      <div ref={productPageRootRef} className="product-management">
          <Card size="small" className="product-management__page-card">
          <RequestLoadingOverlay spinning={isTableRequesting} label="正在加载产品数据，请稍候" />
          <div className="product-management__title-row">
            <div>
              <h1>产品管理</h1>
              <p>SKU 维度产品基础数据源，维护资料、成本、WFS费用与价格字段。</p>
            </div>
          </div>

          <Card size="small" className="product-management__toolbar-card">
            <ProductManagementToolbar
              filters={filters}
              owners={owners}
              developers={developers}
              tags={tags}
              statisticsVisible={statisticsVisible}
              onChange={updateFilters}
              onReset={resetFilters}
              onBatchSearch={(values) => updateFilters({
                ...filters,
                keyword: "",
                batchValues: values,
              })}
              onMessage={(content) => void messageApi.info(content)}
              onToggleStatistics={() => setStatisticsVisible((visible) => !visible)}
              onOpenColumnConfig={() => setColumnConfigOpen(true)}
              onDownload={openExportModal}
            />
          </Card>

          {statisticsVisible && (
            <ProductManagementSummaryCards
              summary={summary}
              activeIssue={filters.issueCode}
              onIssueChange={(issueCode) => updateFilters({ ...filters, issueCode })}
            />
          )}

          <div className="product-management__table-wrap">
            <ProductManagementTable
              rows={rows}
              total={total}
              appliedColumnKeys={appliedColumnKeys}
              columnWidths={columnWidths}
              currentPage={currentPage}
              pageSize={pageSize}
              selectedRowKeys={selectedRowKeys}
              onColumnWidthChange={(key, width) => setColumnPreferenceOverride({
                scope: preferenceScope,
                value: {
                  appliedColumnKeys,
                  columnWidths: { ...columnWidths, [key]: width },
                },
              })}
              onCurrentPageChange={setCurrentPage}
              onPageSizeChange={(nextPageSize) => {
                setPageSize(normalizeReportTablePageSize(nextPageSize));
                resetPageAndSelection();
              }}
              onSelectionChange={setSelectedRowKeys}
              onOpenDetail={(row) => setDetailRowId(row.id)}
              onBulkExport={openExportModal}
            />
          </div>
          </Card>

        <ListExportModal
          open={exportModalOpen}
          title="导出数据"
          subtitle="配置导出字段"
          columnGroups={productExportColumnGroups}
          defaultSelectedColumnKeys={productDefaultExportColumnKeys}
          exporting={isExporting}
          onClose={closeExportModal}
          onExport={handleExport}
        />

        <RuntimeColumnConfigDrawer
          open={columnConfigOpen}
          groups={columnGroups}
          fixedKeys={fixedProductColumnKeys}
          defaultKeys={defaultColumnKeys}
          appliedKeys={appliedColumnKeys}
          onApply={persistColumns}
          onClose={() => setColumnConfigOpen(false)}
          onSaveTemplate={() => void messageApi.info("模板功能暂未开放；当前列配置请使用“保存并应用”")}
        />
        <ProductDetailModal row={detailRow} onClose={() => setDetailRowId(undefined)} />
      </div>
    </PageShell>
  );
}

export default ProductManagementPage;
