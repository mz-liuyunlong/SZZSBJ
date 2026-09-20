import {
  CloudDownloadOutlined,
  SettingOutlined,
  UnorderedListOutlined,
} from "@ant-design/icons";
import { Button, Popover, Space, Typography, Input } from "antd";
import { useState } from "react";
import ConnectedSearch from "@/components/report-table/ConnectedSearch";
import ResetButton from "@/components/report-table/ResetButton";
import ReportFacetSelect from "@/shared/report-filters";
import type { ReportFilterOption } from "@/shared/report-filters";

export interface ListingManagementFilters {
  stores: string[];
  owners?: string[];
  productTypes?: string[];
  productStatuses?: string[];
  tagValues?: string[];

  /** Legacy cached single-value filters. Kept only to migrate older page-state cache safely. */
  owner?: string;
  productType?: string;
  productStatus?: string;

  searchType: "sku" | "msku" | "productId" | "productName";
  keyword: string;
  batchValues?: string[];
}

interface ListingManagementToolbarProps {
  filters: ListingManagementFilters;
  stores: ReportFilterOption[];
  owners: ReportFilterOption[];
  productTypes: ReportFilterOption[];
  tags: ReportFilterOption[];
  statisticsVisible: boolean;
  onChange: (filters: ListingManagementFilters) => void;
  onReset: () => void;
  onBatchSearch: (values: string[]) => void;
  onMessage: (content: string) => void;
  onToggleStatistics: () => void;
  onOpenTagManager?: () => void;
  onOpenColumnConfig: () => void;
  onDownload: () => void;
}

const normalizeSelected = (values?: string[], legacyValue?: string) => (
  values && values.length > 0 ? values : legacyValue ? [legacyValue] : []
);

const listingStatusOptions: ReportFilterOption[] = [
  "启用",
  "停用",
  "在线",
  "离线",
  "拥有",
  "未拥有",
].map((value) => ({ value, label: value }));

function ListingManagementToolbar({
  filters,
  stores,
  owners,
  productTypes,
  tags,
  statisticsVisible,
  onChange,
  onReset,
  onMessage,
  onToggleStatistics,
  onOpenTagManager,
  onOpenColumnConfig,
  onDownload,
}: ListingManagementToolbarProps) {
  const [batchOpen, setBatchOpen] = useState(false);
  const [batchText, setBatchText] = useState("");
  const [searchTypeDraft, setSearchTypeDraft] = useState<ListingManagementFilters["searchType"]>(filters.searchType);
  const [keywordDraft, setKeywordDraft] = useState(filters.keyword);

  const applyBatchSearch = () => {
    const values = batchText
      .split(/\r?\n/)
      .map((line) => line.trim())
      .filter(Boolean);

    if (values.length === 0) {
      onMessage("请输入 SKU / MSKU / 商品ID");
      return;
    }
    if (values.length > 1000) {
      onMessage("最多支持 1000 行");
      return;
    }

    onChange({
      ...filters,
      searchType: searchTypeDraft,
      keyword: "",
      batchValues: values,
    });
    setBatchOpen(false);
  };

  const batchControl = (
    <Popover
      trigger="click"
      open={batchOpen}
      placement="bottomRight"
      onOpenChange={setBatchOpen}
      content={(
        <div className="listing-management__batch-popover">
          <Typography.Text strong>精确搜索，一行一项，最多支持1000行</Typography.Text>
          <Input.TextArea
            value={batchText}
            placeholder="请输入 SKU / MSKU / 商品ID，一行一个"
            rows={8}
            onChange={(event) => setBatchText(event.target.value)}
          />
          <div className="listing-management__batch-actions">
            <Button onClick={() => setBatchText("")}>清空</Button>
            <Button onClick={() => setBatchOpen(false)}>关闭</Button>
            <Button type="primary" onClick={applyBatchSearch}>搜索</Button>
          </div>
        </div>
      )}
    >
      <Button
        className="report-table-connected-search__filter"
        aria-label="批量搜索 Listing"
        icon={<UnorderedListOutlined aria-hidden="true" />}
      />
    </Popover>
  );

  return (
    <div className="listing-management__toolbar" role="search" aria-label="Listing 管理筛选">
      <ReportFacetSelect
        mode="multiple"
        ariaLabel="产品类型"
        placeholder="产品类型"
        unit="个类型"
        value={normalizeSelected(filters.productTypes, filters.productType)}
        options={productTypes}
        onChange={(value) => onChange({
          ...filters,
          productTypes: value as string[],
          productType: undefined,
        })}
      />
      <ReportFacetSelect
        mode="multiple"
        ariaLabel="负责人"
        placeholder="负责人"
        unit="人"
        value={normalizeSelected(filters.owners, filters.owner)}
        options={owners}
        onChange={(value) => onChange({
          ...filters,
          owners: value as string[],
          owner: undefined,
        })}
      />
      <ReportFacetSelect
        mode="multiple"
        ariaLabel="产品状态"
        placeholder="产品状态"
        unit="个状态"
        value={normalizeSelected(filters.productStatuses, filters.productStatus)}
        options={listingStatusOptions}
        onChange={(value) => onChange({
          ...filters,
          productStatuses: value as string[],
          productStatus: undefined,
        })}
      />
      <ReportFacetSelect
        mode="multiple"
        ariaLabel="标签"
        placeholder="标签"
        unit="个标签"
        value={filters.tagValues ?? []}
        options={tags}
        popupWidth={320}
        onChange={(value) => onChange({
          ...filters,
          tagValues: value as string[],
        })}
      />
      <ReportFacetSelect
        mode="multiple"
        ariaLabel="店铺"
        placeholder="全部店铺"
        unit="个店铺"
        value={filters.stores}
        options={stores}
        popupWidth={360}
        onChange={(value) => onChange({ ...filters, stores: value as string[] })}
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
        typeValue={searchTypeDraft}
        inputAriaLabel="搜索商品"
        inputPlaceholder="搜索商品"
        inputValue={keywordDraft}
        batchControl={batchControl}
        onTypeChange={(searchType) => setSearchTypeDraft(searchType as ListingManagementFilters["searchType"])}
        onInputChange={setKeywordDraft}
        onSearch={() => {
          onChange({
            ...filters,
            searchType: searchTypeDraft,
            keyword: keywordDraft.trim(),
            batchValues: undefined,
          });
          onMessage("已应用搜索条件");
        }}
      />
      <ResetButton
        onClick={() => {
          setSearchTypeDraft("sku");
          setKeywordDraft("");
          setBatchText("");
          onReset();
        }}
      />
      {onOpenTagManager ? (
        <Button
          className="listing-management__tag-manager-button"
          onClick={onOpenTagManager}
        >
          标签管理
        </Button>
      ) : null}
      <Button onClick={onToggleStatistics}>
        {statisticsVisible ? "隐藏统计" : "显示统计"}
      </Button>
      <Space className="listing-management__toolbar-actions" size={8}>
        <Button
          aria-label="列配置"
          icon={<SettingOutlined aria-hidden="true" />}
          onClick={onOpenColumnConfig}
        />
        <Button
          aria-label="下载"
          icon={<CloudDownloadOutlined aria-hidden="true" />}
          onClick={onDownload}
        />
      </Space>
    </div>
  );
}

export default ListingManagementToolbar;
