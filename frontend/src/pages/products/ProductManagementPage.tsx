/** Product-management No-API page shell rebuilt from the approved HTML prototype. */
import { Card, message } from "antd";
import { useMemo, useState, type Key } from "react";
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
  productGrades,
  productManagementMockData,
  productTags,
} from "@/pages/products/productManagementMockData";
import {
  fixedProductColumnKeys,
  productColumnFields,
  type ProductManagementFilters,
  type ProductManagementRow,
} from "@/pages/products/productManagementTypes";
import "@/pages/products/ProductManagementPage.css";

const TEMPLATE_PENDING = "列模板接口待接入";
const EXPORT_PENDING = "导出接口待接入";

const createInitialFilters = (): ProductManagementFilters => ({
  searchType: "sku",
  keyword: "",
});

const defaultColumnKeys = productColumnFields
  .map((field) => field.key)
  .filter((key) => [
    "image",
    "sku",
    "productName",
    "tags",
    "productGrade",
    "wfsFee",
    "suggestedPrice",
    "minimumPrice",
    "clearancePrice",
  ].includes(key));
const defaultColumnWidths: Record<string, number> = {
  image: 72,
  sku: 170,
  productName: 240,
  tags: 132,
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
  { title: "默认主表字段", fields: [...productColumnFields.slice(0, 9)] },
  { title: "可选基本信息字段", fields: [...productColumnFields.slice(9)] },
];

interface ProductManagementPageProps {
  page: NavigationPage;
}

function ProductManagementPage({ page }: ProductManagementPageProps) {
  const [messageApi, messageContextHolder] = message.useMessage();
  const [filters, setFilters] = useState(createInitialFilters);
  const [statisticsVisible, setStatisticsVisible] = useState(true);
  const [columnConfigOpen, setColumnConfigOpen] = useState(false);
  const [appliedColumnKeys, setAppliedColumnKeys] = useState<string[]>(defaultColumnKeys);
  const [columnWidths, setColumnWidths] = useState<Record<string, number>>(defaultColumnWidths);
  const [currentPage, setCurrentPage] = useState(1);
  const [pageSize, setPageSize] = useState(REPORT_TABLE_DEFAULT_PAGE_SIZE);
  const [selectedRowKeys, setSelectedRowKeys] = useState<Key[]>([]);
  const [detailRow, setDetailRow] = useState<ProductManagementRow>();

  const resetPageAndSelection = () => {
    setCurrentPage(1);
    setSelectedRowKeys([]);
  };

  const updateFilters = (nextFilters: ProductManagementFilters) => {
    setFilters(nextFilters);
    resetPageAndSelection();
  };

  const filteredRows = useMemo(() => {
    const keyword = filters.keyword.trim().toLocaleLowerCase();
    const batchValues = filters.batchValues?.map((item) => item.toLocaleLowerCase()) ?? [];
    return productManagementMockData.filter((row) => {
      const target = String(row[filters.searchType]).toLocaleLowerCase();
      return (!filters.productGrade || row.productGrade === filters.productGrade)
        && (!filters.tag || row.tags.includes(filters.tag))
        && (!keyword || target.includes(keyword))
        && (batchValues.length === 0 || batchValues.includes(row.sku.toLocaleLowerCase()));
    });
  }, [filters]);

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
              grades={productGrades}
              tags={productTags}
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

          {statisticsVisible && <ProductManagementSummaryCards rows={filteredRows} />}

          <div className="product-management__table-wrap">
            <ProductManagementTable
              rows={filteredRows}
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
          fixedKeys={fixedProductColumnKeys}
          defaultKeys={defaultColumnKeys}
          appliedKeys={appliedColumnKeys}
          onApply={setAppliedColumnKeys}
          onClose={() => setColumnConfigOpen(false)}
          onSaveTemplate={() => void messageApi.info(TEMPLATE_PENDING)}
        />
        <ProductDetailModal row={detailRow} onClose={() => setDetailRow(undefined)} />
      </div>
    </PageShell>
  );
}

export default ProductManagementPage;
