import { Card, Spin, message } from "antd";
import { useEffect, useMemo, useRef, useState, type Key } from "react";
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
import ProductManagementSummaryCards, {
  type ProductManagementSummaryCardKey,
} from "@/pages/products/components/ProductManagementSummaryCards";
import ProductManagementTable from "@/pages/products/components/ProductManagementTable";
import ProductManagementToolbar from "@/pages/products/components/ProductManagementToolbar";
import {
  getProductManagementOptions,
  getProductManagementSku,
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
  type ProductGrade,
  type ProductTag,
} from "@/pages/products/productManagementTypes";
import "@/pages/products/ProductManagementPage.css";

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
  const messageApiRef = useRef(messageApi);
  const [filters, setFilters] = useState(createInitialFilters);
  const [statisticsVisible, setStatisticsVisible] = useState(true);
  const [summaryFilterKey, setSummaryFilterKey] = useState<ProductManagementSummaryCardKey>("total");
  const [columnConfigOpen, setColumnConfigOpen] = useState(false);
  const [appliedColumnKeys, setAppliedColumnKeys] = useState<string[]>(defaultColumnKeys);
  const [columnWidths, setColumnWidths] = useState<Record<string, number>>(defaultColumnWidths);
  const [currentPage, setCurrentPage] = useState(1);
  const [pageSize, setPageSize] = useState(REPORT_TABLE_DEFAULT_PAGE_SIZE);
  const [selectedRowKeys, setSelectedRowKeys] = useState<Key[]>([]);
  const [detailRow, setDetailRow] = useState<ProductManagementRow>();
  const [rows, setRows] = useState<ProductManagementRow[]>([]);
  const [total, setTotal] = useState(0);
  const [grades, setGrades] = useState<ProductGrade[]>([]);
  const [tags, setTags] = useState<ProductTag[]>([]);
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
        setRows(result.rows);
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
    void getProductManagementOptions()
      .then((options) => {
        setGrades(options.grades);
        setTags(options.tags);
      })
      .catch(() => undefined);
    void getProductManagementTableView()
      .then((view) => {
        setAppliedColumnKeys(view.applied_column_keys);
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
    setSummaryFilterKey("total");
    resetPageAndSelection();
  };

  const toolbarFilteredRows = useMemo(() => {
    const keyword = filters.keyword.trim().toLocaleLowerCase();
    const batchValues = filters.batchValues?.map((item) => item.toLocaleLowerCase()) ?? [];
    return rows.filter((row) => {
      const target = String(row[filters.searchType]).toLocaleLowerCase();
      return (!filters.productGrade || row.productGrade === filters.productGrade)
        && (!filters.tag || row.tags.includes(filters.tag))
        && (!keyword || target.includes(keyword))
        && (batchValues.length === 0 || (
          row.sku !== null && batchValues.includes(row.sku.toLocaleLowerCase())
        ));
    });
  }, [filters, rows]);

  const filteredRows = useMemo(() => {
    if (summaryFilterKey === "gradeA") return toolbarFilteredRows.filter((row) => row.productGrade === "A级");
    if (summaryFilterKey === "gradeB") return toolbarFilteredRows.filter((row) => row.productGrade === "B级");
    if (summaryFilterKey === "gradeC") return toolbarFilteredRows.filter((row) => row.productGrade === "C级");
    if (summaryFilterKey === "complete") return toolbarFilteredRows.filter((row) => (row.dataCompleteness ?? 0) >= 90);
    if (summaryFilterKey === "linked") return toolbarFilteredRows.filter((row) => row.linkedPlatformSkuCount > 0);
    return toolbarFilteredRows;
  }, [summaryFilterKey, toolbarFilteredRows]);

  const handleSummaryCardClick = (key: ProductManagementSummaryCardKey) => {
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
              grades={grades}
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
              rows={toolbarFilteredRows}
              activeKey={summaryFilterKey}
              onCardClick={handleSummaryCardClick}
            />
          )}

          <div className="product-management__table-wrap">
            {loading && <Spin tip="正在加载产品数据" />}
            <ProductManagementTable
              rows={filteredRows}
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
