import {
  CloudDownloadOutlined,
  SettingOutlined,
  UnorderedListOutlined,
} from "@ant-design/icons";
import { Button, Popover, Select, Space, Typography, Input } from "antd";
import { useState } from "react";
import ConnectedSearch from "@/components/report-table/ConnectedSearch";
import ResetButton from "@/components/report-table/ResetButton";

export interface ListingManagementFilters {
  stores: string[];
  owner?: string;
  productType?: string;
  productStatus?: string;
  searchType: "sku" | "msku" | "productId" | "productName";
  keyword: string;
  batchValues?: string[];
}

interface ListingManagementToolbarProps {
  filters: ListingManagementFilters;
  stores: string[];
  owners: string[];
  productTypes: string[];
  statisticsVisible: boolean;
  onChange: (filters: ListingManagementFilters) => void;
  onReset: () => void;
  onBatchSearch: (values: string[]) => void;
  onMessage: (content: string) => void;
  onToggleStatistics: () => void;
  onOpenColumnConfig: () => void;
  onDownload: () => void;
}

function ListingManagementToolbar({
  filters,
  stores,
  owners,
  productTypes,
  statisticsVisible,
  onChange,
  onReset,
  onBatchSearch,
  onMessage,
  onToggleStatistics,
  onOpenColumnConfig,
  onDownload,
}: ListingManagementToolbarProps) {
  const [batchOpen, setBatchOpen] = useState(false);
  const [batchText, setBatchText] = useState("");

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
    onBatchSearch(values);
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
      <Select
        className="report-filter-select"
        classNames={{ popup: { root: "report-filter-select-dropdown" } }}
        allowClear
        placeholder="产品类型"
        aria-label="产品类型"
        value={filters.productType}
        options={productTypes.map((value) => ({ value, label: value }))}
        onChange={(value) => onChange({ ...filters, productType: value })}
      />
      <Select
        className="report-filter-select"
        classNames={{ popup: { root: "report-filter-select-dropdown" } }}
        allowClear
        placeholder="负责人"
        aria-label="负责人"
        value={filters.owner}
        options={owners.map((value) => ({ value, label: value }))}
        onChange={(value) => onChange({ ...filters, owner: value })}
      />
      <Select
        className="report-filter-select"
        classNames={{ popup: { root: "report-filter-select-dropdown" } }}
        allowClear
        placeholder="产品状态"
        aria-label="产品状态"
        value={filters.productStatus}
        options={["启用", "停用", "在线", "离线", "拥有", "未拥有"].map((value) => ({ value, label: value }))}
        onChange={(value) => onChange({ ...filters, productStatus: value })}
      />
      <Select
        className="listing-management__store-select"
        classNames={{ popup: { root: "report-filter-select-dropdown" } }}
        mode="multiple"
        allowClear
        maxTagCount="responsive"
        placeholder="全部店铺"
        aria-label="店铺"
        value={filters.stores}
        options={stores.map((value) => ({ value, label: value }))}
        onChange={(value) => onChange({ ...filters, stores: value })}
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
        typeValue={filters.searchType}
        inputAriaLabel="搜索商品"
        inputPlaceholder="搜索商品"
        inputValue={filters.keyword}
        batchControl={batchControl}
        onTypeChange={(searchType) => onChange({
          ...filters,
          searchType: searchType as ListingManagementFilters["searchType"],
        })}
        onInputChange={(keyword) => onChange({ ...filters, keyword })}
        onSearch={() => onMessage("已应用搜索条件")}
      />
      <ResetButton onClick={onReset} />
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
