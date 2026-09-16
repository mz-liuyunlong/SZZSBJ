/** Listing-management page backed by DATA-PAGES MART API with temporary local fallback. */
import { Card, message } from "antd";
import { useEffect, useMemo, useState, type Key } from "react";
import PageShell from "@/components/page/PageShell";
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
import { fetchListingManagementRows } from "@/pages/products/listingManagementApi";
import {
  fixedListingColumnKeys,
  listingColumnFields,
  listingManagementMockData,
  listingOwners,
  listingProductTypes,
  listingStores,
  type ListingManagementRow,
} from "@/pages/products/listingManagementData";
import "@/pages/products/ListingManagementPage.css";

const TEMPLATE_PENDING = "列模板接口待接入";
const EXPORT_PENDING = "导出接口待接入";

const createInitialFilters = (): ListingManagementFilters => ({
  stores: [],
  searchType: "sku",
  keyword: "",
});

const uniqueValues = (values: string[]) => [...new Set(values.filter(Boolean))];

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
  const [filters, setFilters] = useState(createInitialFilters);
  const [sourceRows, setSourceRows] = useState<ListingManagementRow[]>(listingManagementMockData);
  const [statisticsVisible, setStatisticsVisible] = useState(true);
  const [summaryFilterKey, setSummaryFilterKey] = useState<ListingManagementSummaryCardKey>("total");
  const [columnConfigOpen, setColumnConfigOpen] = useState(false);
  const [appliedColumnKeys, setAppliedColumnKeys] = useState<string[]>(defaultColumnKeys);
  const [columnWidths, setColumnWidths] = useState<Record<string, number>>(defaultColumnWidths);
  const [currentPage, setCurrentPage] = useState(1);
  const [pageSize, setPageSize] = useState(REPORT_TABLE_DEFAULT_PAGE_SIZE);
  const [selectedRowKeys, setSelectedRowKeys] = useState<Key[]>([]);
  const [detailRow, setDetailRow] = useState<ListingManagementRow>();

  useEffect(() => {
    let active = true;
    void fetchListingManagementRows({ pageSize: 500 })
      .then(({ rows }) => {
        if (active) setSourceRows(rows);
      })
      .catch(() => {
        // Keep the local fallback visible until the backend has synced MART data.
      });
    return () => {
      active = false;
    };
  }, []);

  const storeOptions = useMemo(() => uniqueValues([
    ...listingStores,
    ...sourceRows.map((row) => row.store),
  ]), [sourceRows]);
  const ownerOptions = useMemo(() => uniqueValues([
    ...listingOwners,
    ...sourceRows.map((row) => row.owner),
  ]), [sourceRows]);
  const productTypeOptions = useMemo(() => uniqueValues([
    ...listingProductTypes,
    ...sourceRows.map((row) => row.productType),
  ]), [sourceRows]);

  const resetPageAndSelection = () => {
    setCurrentPage(1);
    setSelectedRowKeys([]);
  };

  const updateFilters = (nextFilters: ListingManagementFilters) => {
    setFilters(nextFilters);
    setSummaryFilterKey("total");
    resetPageAndSelection();
  };

  const toolbarFilteredRows = useMemo(() => {
    const keyword = filters.keyword.trim().toLocaleLowerCase();
    const batchValues = filters.batchValues?.map((item) => item.toLocaleLowerCase()) ?? [];

    return sourceRows.filter((row) => {
      const target = String(row[filters.searchType]).toLocaleLowerCase();
      const statusMatched = !filters.productStatus
        || row.productStatus === filters.productStatus
        || row.listingStatus === filters.productStatus
        || row.buyBoxStatus === filters.productStatus;
      return (filters.stores.length === 0 || filters.stores.includes(row.store))
        && (!filters.owner || row.owner === filters.owner)
        && (!filters.productType || row.productType === filters.productType)
        && statusMatched
        && (!keyword || target.includes(keyword))
        && (batchValues.length === 0
          || batchValues.includes(row.sku.toLocaleLowerCase())
          || batchValues.includes(row.msku.toLocaleLowerCase())
          || batchValues.includes(row.productId.toLocaleLowerCase()));
    });
  }, [filters, sourceRows]);

  const filteredRows = useMemo(() => {
    if (summaryFilterKey === "online") return toolbarFilteredRows.filter((row) => row.listingStatus === "在线");
    if (summaryFilterKey === "offline") return toolbarFilteredRows.filter((row) => row.listingStatus === "离线");
    if (summaryFilterKey === "buybox") return toolbarFilteredRows.filter((row) => row.buyBoxStatus === "未拥有");
    if (summaryFilterKey === "resold") return toolbarFilteredRows.filter((row) => row.resold === "是");
    if (summaryFilterKey === "disabled") return toolbarFilteredRows.filter((row) => row.productStatus === "停用");
    return toolbarFilteredRows;
  }, [summaryFilterKey, toolbarFilteredRows]);

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
      <div className="listing-management">
        <Card size="small" className="listing-management__page-card">
          <div className="listing-management__title-row">
            <div>
              <h1>Listing管理</h1>
              <p>覆盖店铺、负责人、状态、价格、库存、购物车、跟卖与检查信息。</p>
            </div>
          </div>

          <Card size="small" className="listing-management__toolbar-card">
            <ListingManagementToolbar
              filters={filters}
              stores={storeOptions}
              owners={ownerOptions}
              productTypes={productTypeOptions}
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
              rows={toolbarFilteredRows}
              activeKey={summaryFilterKey}
              onCardClick={handleSummaryCardClick}
            />
          )}

          <div className="listing-management__table-wrap">
            <ListingManagementTable
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
