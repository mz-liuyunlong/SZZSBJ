/** Listing Management No-API page shell using local acceptance data only. */
import {
  CloudDownloadOutlined,
  SettingOutlined,
} from "@ant-design/icons";
import { Button, Card, Checkbox, Select, message } from "antd";
import { useMemo, useState, type Key } from "react";
import PageShell from "@/components/page/PageShell";
import ConnectedSearch from "@/components/report-table/ConnectedSearch";
import {
  REPORT_TABLE_DEFAULT_PAGE_SIZE,
  normalizeReportTablePageSize,
} from "@/components/report-table/pagination";
import ResetButton from "@/components/report-table/ResetButton";
import RuntimeColumnConfigDrawer, {
  type RuntimeColumnGroup,
} from "@/components/report-table/RuntimeColumnConfigDrawer";
import type { NavigationPage } from "@/config/navigation";
import ListingManagementTable from "@/pages/products/components/ListingManagementTable";
import {
  fixedListingColumnKeys,
  listingColumnFields,
  listingManagementMockData,
  listingOwners,
  listingProductTypes,
  listingStores,
} from "@/pages/products/listingManagementData";
import "@/pages/products/ListingManagementPage.css";

const NO_API_PENDING = "Listing 数据接口待接入";
const TEMPLATE_PENDING = "列模板接口待接入";
const defaultColumnKeys = listingColumnFields.map((field) => field.key);
const columnGroups: RuntimeColumnGroup[] = [{ title: "Listing 管理字段", fields: [...listingColumnFields] }];
const defaultWidths = Object.fromEntries(listingColumnFields.map((field) => [field.key, field.key === "image" ? 72 : 112]));

interface ListingManagementPageProps {
  page: NavigationPage;
}

function ListingManagementPage({ page }: ListingManagementPageProps) {
  const [messageApi, messageContextHolder] = message.useMessage();
  const [stores, setStores] = useState<string[]>([]);
  const [owner, setOwner] = useState<string>();
  const [productType, setProductType] = useState<string>();
  const [productStatus, setProductStatus] = useState<string>();
  const [searchType, setSearchType] = useState("sku");
  const [keyword, setKeyword] = useState("");
  const [columnConfigOpen, setColumnConfigOpen] = useState(false);
  const [appliedColumnKeys, setAppliedColumnKeys] = useState<string[]>(defaultColumnKeys);
  const [columnWidths, setColumnWidths] = useState(defaultWidths);
  const [currentPage, setCurrentPage] = useState(1);
  const [pageSize, setPageSize] = useState(REPORT_TABLE_DEFAULT_PAGE_SIZE);
  const [selectedRowKeys, setSelectedRowKeys] = useState<Key[]>([]);

  const resetPageAndSelection = () => {
    setCurrentPage(1);
    setSelectedRowKeys([]);
  };
  const updateFilter = (update: () => void) => {
    update();
    resetPageAndSelection();
  };
  const rows = useMemo(() => {
    const query = keyword.trim().toLocaleLowerCase();
    return listingManagementMockData.filter((row) => (
      (stores.length === 0 || stores.includes(row.store))
      && (!owner || row.owner === owner)
      && (!productType || row.productType === productType)
      && (!productStatus || row.productStatus === productStatus)
      && (!query || String(row[searchType as "sku" | "msku" | "productId" | "productName"])
        .toLocaleLowerCase().includes(query))
    ));
  }, [keyword, owner, productStatus, productType, searchType, stores]);

  const resetFilters = () => {
    setStores([]);
    setOwner(undefined);
    setProductType(undefined);
    setProductStatus(undefined);
    setSearchType("sku");
    setKeyword("");
    resetPageAndSelection();
  };
  const copyText = async (text: string) => {
    try {
      if (!navigator.clipboard) throw new Error("Clipboard API unavailable");
      await navigator.clipboard.writeText(text);
      void messageApi.success("已复制");
    } catch {
      void messageApi.error("复制失败，请手动复制");
    }
  };

  return (
    <PageShell page={page}>
      {messageContextHolder}
      <div className="listing-management">
        <Card size="small" className="listing-management__toolbar-card">
          <div className="listing-management__toolbar" role="search" aria-label="Listing 管理筛选">
            <Select
              className="report-filter-select"
              classNames={{ popup: { root: "report-filter-select-dropdown" } }}
              allowClear
              aria-label="产品类型"
              placeholder="产品类型"
              value={productType}
              options={listingProductTypes.map((value) => ({ value, label: value }))}
              onChange={(value) => updateFilter(() => setProductType(value))}
            />
            <Select
              className="report-filter-select"
              classNames={{ popup: { root: "report-filter-select-dropdown" } }}
              allowClear
              aria-label="负责人"
              placeholder="负责人"
              value={owner}
              options={listingOwners.map((value) => ({ value, label: value }))}
              onChange={(value) => updateFilter(() => setOwner(value))}
            />
            <Select
              className="report-filter-select"
              classNames={{ popup: { root: "report-filter-select-dropdown" } }}
              allowClear
              aria-label="产品状态"
              placeholder="产品状态"
              value={productStatus}
              options={["启用", "停用"].map((value) => ({ value, label: value }))}
              onChange={(value) => updateFilter(() => setProductStatus(value))}
            />
            <Select
              className="report-filter-select"
              classNames={{ popup: { root: "report-filter-select-dropdown report-filter-select-dropdown--multiple" } }}
              mode="multiple"
              maxTagCount="responsive"
              allowClear
              aria-label="店铺"
              placeholder="全部店铺"
              value={stores}
              options={listingStores.map((value) => ({ value, label: value }))}
              optionRender={(option) => (
                <Checkbox checked={stores.includes(String(option.value))}>{option.label}</Checkbox>
              )}
              onChange={(value) => updateFilter(() => setStores(value))}
            />
            <ConnectedSearch
              className="listing-management__search"
              typeAriaLabel="搜索类型"
              typeOptions={[
                { value: "sku", label: "SKU" },
                { value: "msku", label: "MSKU" },
                { value: "productId", label: "商品ID" },
                { value: "productName", label: "品名" },
              ]}
              typeValue={searchType}
              inputAriaLabel="搜索 Listing"
              inputPlaceholder="搜索商品"
              inputValue={keyword}
              filterAction={{
                ariaLabel: "批量搜索",
                tooltip: "批量搜索待接入",
                onClick: () => void messageApi.info(NO_API_PENDING),
              }}
              onTypeChange={(value) => updateFilter(() => setSearchType(value))}
              onInputChange={(value) => updateFilter(() => setKeyword(value))}
              onSearch={() => undefined}
            />
            <ResetButton onClick={resetFilters} />
            <div className="listing-management__toolbar-spacer" />
            <Button
              icon={<CloudDownloadOutlined aria-hidden="true" />}
              onClick={() => void messageApi.info(NO_API_PENDING)}
            >
              下载
            </Button>
            <Button
              icon={<SettingOutlined aria-hidden="true" />}
              onClick={() => setColumnConfigOpen(true)}
            >
              列配置
            </Button>
          </div>
        </Card>

        <ListingManagementTable
          rows={rows}
          appliedColumnKeys={appliedColumnKeys}
          columnWidths={columnWidths}
          currentPage={currentPage}
          pageSize={pageSize}
          selectedRowKeys={selectedRowKeys}
          onColumnWidthChange={(key, width) => setColumnWidths((current) => ({ ...current, [key]: width }))}
          onCurrentPageChange={setCurrentPage}
          onPageSizeChange={(nextPageSize) => {
            setPageSize(normalizeReportTablePageSize(nextPageSize));
            resetPageAndSelection();
          }}
          onSelectionChange={setSelectedRowKeys}
          onBulkMark={() => void messageApi.info(NO_API_PENDING)}
          onCopy={(text) => void copyText(text)}
        />
      </div>

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
    </PageShell>
  );
}

export default ListingManagementPage;
