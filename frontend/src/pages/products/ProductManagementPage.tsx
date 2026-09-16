import { Card, Spin, message } from "antd";
import { useEffect, useMemo, useRef, type Key } from "react";
import PageShell from "@/components/page/PageShell";
import RuntimeColumnConfigDrawer, {
  type RuntimeColumnGroup,
} from "@/components/report-table/RuntimeColumnConfigDrawer";
import {
  REPORT_TABLE_DEFAULT_PAGE_SIZE,
  normalizeReportTablePageSize,
} from "@/components/report-table/pagination";
import type { NavigationPage } from "@/config/navigation";
import ProductDetailModal from "@/pages/products/components/ProductDetailModal";
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

  useEffect(() => {
    messageApiRef.current = messageApi;
  }, [messageApi]);

  const listQuery = useProductManagementListQuery(filters, currentPage, pageSize);
  const prefetchProductList = usePrefetchProductManagementList();
  const summaryQuery = useProductManagementSummaryQuery(filters, statisticsVisible);
  const optionsQuery = useProductManagementOptionsQuery();
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
  const owners = optionsQuery.data?.owners ?? [];
  const developers = optionsQuery.data?.developers ?? [];
  const tags = optionsQuery.data?.tags ?? [];

  useEffect(() => {
    if (total <= currentPage * pageSize) return;
    void prefetchProductList(filters, currentPage + 1, pageSize);
  }, [currentPage, filters, pageSize, prefetchProductList, total]);

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
              onDownload={() => void requestProductManagementExport(filters)
                .then(() => messageApi.info("导出任务未启用，未创建文件"))
                .catch((reason: unknown) => messageApi.error(
                  reason instanceof Error ? reason.message : "BACKEND_REQUEST_FAILED",
                ))}
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
            {listQuery.isPending && (
              <Spin className="product-management__table-loading" tip="正在加载产品数据" />
            )}
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
              onBulkExport={() => void requestProductManagementExport(filters)
                .then(() => messageApi.info("导出任务未启用，未创建文件"))
                .catch((reason: unknown) => messageApi.error(
                  reason instanceof Error ? reason.message : "BACKEND_REQUEST_FAILED",
                ))}
            />
          </div>
        </Card>

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
