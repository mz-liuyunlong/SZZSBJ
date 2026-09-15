import { Card, Spin, message } from "antd";
import { useEffect, useRef, useState, type Key } from "react";
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
import {
  getProductManagementSku,
  getProductManagementSummary,
  getProductManagementTableView,
  listProductManagementSkus,
  requestProductManagementExport,
  saveProductManagementTableView,
} from "@/pages/products/productManagementApi";
import {
  fixedProductColumnKeys,
  productColumnFields,
  type ProductManagementFilters,
  type ProductManagementRow,
  type ProductManagementSummary,
  type ProductSourceTagOption,
} from "@/pages/products/productManagementTypes";
import "@/pages/products/ProductManagementPage.css";
import { applyProductBasicCompleteness } from "@/pages/products/productBasicCompleteness";

const createInitialFilters = (): ProductManagementFilters => ({
  searchType: "sku",
  keyword: "",
});

const hiddenProductColumnKeys = new Set<string>(["category", "linkedPlatformSkuCount", "wfsDeliveryFee", "wfsFulfillmentFee", "wfsShippingFee", "wfsFee", "tags", "internalTags", "internalTag", "suggestedPrice", "minimumPrice", "productGrade", "updatedAt", "dataCompleteness"]);
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
    if (!mergedKeys.includes(key)) {
      mergedKeys.push(key);
    }
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

interface ProductManagementPageProps {
  page: NavigationPage;
}

const emptySummary: ProductManagementSummary = {
  syncedDetailCount: 0,
  dataCompletenessRate: 0,
  withImageCount: 0,
  withSourceTagCount: 0,
  incompleteCount: 0,
  missingPurchaseCostCount: 0,
  missingGrossWeightCount: 0,
  missingPackageDimensionsCount: 0,
  missingDimensionImageCount: 0,
  invalidPricingRuleCount: 0,
  pricingOkCount: 0,
};

const sourceTagOptionsFromRows = (
  nextRows: ProductManagementRow[],
): ProductSourceTagOption[] => {
  const options = new Map<string, string | null>();

  for (const row of nextRows) {
    for (const label of row.sourceTags) {
      if (!options.has(label)) {
        options.set(label, row.sourceTagColors?.[label] ?? null);
      }
    }
  }

  return Array.from(options, ([label, color]) => ({ label, color }));
};



function ProductManagementPage({ page }: ProductManagementPageProps) {
  const [messageApi, messageContextHolder] = message.useMessage();
  const messageApiRef = useRef(messageApi);
  const [filters, setFilters] = useState(createInitialFilters);
  const [statisticsVisible, setStatisticsVisible] = useState(false);
  const [columnConfigOpen, setColumnConfigOpen] = useState(false);
  const [appliedColumnKeys, setAppliedColumnKeys] = useState<string[]>(() => normalizeProductColumnKeys(defaultColumnKeys));
  const [columnWidths, setColumnWidths] = useState<Record<string, number>>(defaultColumnWidths);
  const [currentPage, setCurrentPage] = useState(1);
  const [pageSize, setPageSize] = useState(REPORT_TABLE_DEFAULT_PAGE_SIZE);
  const [selectedRowKeys, setSelectedRowKeys] = useState<Key[]>([]);
  const [detailRow, setDetailRow] = useState<ProductManagementRow>();
  const [rows, setRows] = useState<ProductManagementRow[]>([]);
  const [total, setTotal] = useState(0);
  const [, setSummary] = useState<ProductManagementSummary>(emptySummary);
  const ownerOptions: string[] = [];
  const developerOptions: string[] = [];
  const [tags, setTags] = useState<ProductSourceTagOption[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    messageApiRef.current = messageApi;
  }, [messageApi]);

  useEffect(() => {
    let active = true;
    void Promise.resolve()
      .then(() => {
        if (active) {
          setLoading(true);
        }
        return listProductManagementSkus(filters, currentPage, pageSize);
      })
      .then((result) => {
        if (!active) return;
        const rowsWithDynamicCompleteness = applyProductBasicCompleteness(result.rows);
      setRows(rowsWithDynamicCompleteness);
        setTags(sourceTagOptionsFromRows(rowsWithDynamicCompleteness));
        setTotal(result.total);
      })
      .catch((reason: unknown) => {
        if (!active) return;
        setRows([]);
        setTotal(0);
        void messageApiRef.current.error(
          reason instanceof Error ? reason.message : "BACKEND_REQUEST_FAILED",
        );
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => { active = false; };
  }, [currentPage, filters, pageSize]);

  useEffect(() => {
    if (!statisticsVisible) return;
    let active = true;
    void getProductManagementSummary(filters)
      .then((result) => {
        if (active) setSummary(result);
      })
      .catch((reason: unknown) => {
        if (!active) return;
        void messageApiRef.current.error(
          reason instanceof Error ? reason.message : "BACKEND_REQUEST_FAILED",
        );
      });
    return () => { active = false; };
  }, [filters, statisticsVisible]);

  useEffect(() => {
    void getProductManagementTableView()
      .then((view) => {
        setAppliedColumnKeys(normalizeProductColumnKeys(view.applied_column_keys));
        setColumnWidths((current) => ({ ...current, ...view.column_widths }));
      })
      .catch(() => undefined);
  }, []);

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

  return (
    <PageShell page={page}>
      {messageContextHolder}
      <div className="product-management">
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
              owners={ownerOptions}
              developers={developerOptions}
              tags={tags}
              statisticsVisible={statisticsVisible}
              onChange={updateFilters}
              onReset={resetFilters}
              onBatchSearch={(values) => updateFilters({ ...filters, batchValues: values })}
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
            rows={rows}
              total={total}
            />
          )}

          <div className="product-management__table-wrap">
            {loading && <Spin className="product-management__table-loading" tip="正在加载产品数据" />}
            <ProductManagementTable
              rows={rows}
              total={total}
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
              onOpenDetail={(row) => {
                setDetailRow(row);
                void getProductManagementSku(row)
                  .then(setDetailRow)
                  .catch((reason: unknown) => messageApi.error(
                    reason instanceof Error ? reason.message : "BACKEND_REQUEST_FAILED",
                  ));
              }}
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
          onApply={setAppliedColumnKeys}
          onClose={() => setColumnConfigOpen(false)}
          onSaveTemplate={() => void saveProductManagementTableView(
            appliedColumnKeys,
            columnWidths,
          ).then(() => messageApi.success("列配置已保存"))
            .catch((reason: unknown) => messageApi.error(
              reason instanceof Error ? reason.message : "BACKEND_REQUEST_FAILED",
            ))}
        />
        <ProductDetailModal row={detailRow} onClose={() => setDetailRow(undefined)} />
      </div>
    </PageShell>
  );
}

export default ProductManagementPage;
