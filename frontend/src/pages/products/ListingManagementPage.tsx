/** Listing-management No-API page shell rebuilt from the approved HTML prototype. */
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
import ListingDetailModal from "@/pages/products/components/ListingDetailModal";
import ListingManagementSummaryCards from "@/pages/products/components/ListingManagementSummaryCards";
import ListingManagementTable from "@/pages/products/components/ListingManagementTable";
import ListingManagementToolbar, {
  type ListingManagementFilters,
} from "@/pages/products/components/ListingManagementToolbar";
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
  const [statisticsVisible, setStatisticsVisible] = useState(true);
  const [columnConfigOpen, setColumnConfigOpen] = useState(false);
  const [appliedColumnKeys, setAppliedColumnKeys] = useState<string[]>(defaultColumnKeys);
  const [columnWidths, setColumnWidths] = useState<Record<string, number>>(defaultColumnWidths);
  const [currentPage, setCurrentPage] = useState(1);
  const [pageSize, setPageSize] = useState(REPORT_TABLE_DEFAULT_PAGE_SIZE);
  const [selectedRowKeys, setSelectedRowKeys] = useState<Key[]>([]);
  const [detailRow, setDetailRow] = useState<ListingManagementRow>();

  const resetPageAndSelection = () => {
    setCurrentPage(1);
    setSelectedRowKeys([]);
  };

  const updateFilters = (nextFilters: ListingManagementFilters) => {
    setFilters(nextFilters);
    resetPageAndSelection();
  };

  const filteredRows = useMemo(() => {
    const keyword = filters.keyword.trim().toLocaleLowerCase();
    const batchValues = filters.batchValues?.map((item) => item.toLocaleLowerCase()) ?? [];

    return listingManagementMockData.filter((row) => {
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
  }, [filters]);

  const resetFilters = () => {
    setFilters(createInitialFilters());
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
              stores={listingStores}
              owners={listingOwners}
              productTypes={listingProductTypes}
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

          {statisticsVisible && <ListingManagementSummaryCards rows={filteredRows} />}

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
