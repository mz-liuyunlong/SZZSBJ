import {
  CloudDownloadOutlined,
  SettingOutlined,
  UnorderedListOutlined,
} from "@ant-design/icons";
import { Button, Popover, Select, Space, Typography, Input } from "antd";
import { useState } from "react";
import ConnectedSearch from "@/components/report-table/ConnectedSearch";
import ResetButton from "@/components/report-table/ResetButton";
import type {
  ProductGrade,
  ProductManagementFilters,
  ProductTag,
} from "@/pages/products/productManagementTypes";

interface ProductManagementToolbarProps {
  filters: ProductManagementFilters;
  grades: ProductGrade[];
  tags: ProductTag[];
  statisticsVisible: boolean;
  onChange: (filters: ProductManagementFilters) => void;
  onReset: () => void;
  onBatchSearch: (values: string[]) => void;
  onMessage: (content: string) => void;
  onToggleStatistics: () => void;
  onOpenColumnConfig: () => void;
  onDownload: () => void;
}

function ProductManagementToolbar({
  filters,
  grades,
  tags,
  statisticsVisible,
  onChange,
  onReset,
  onBatchSearch,
  onMessage,
  onToggleStatistics,
  onOpenColumnConfig,
  onDownload,
}: ProductManagementToolbarProps) {
  const [batchOpen, setBatchOpen] = useState(false);
  const [batchText, setBatchText] = useState("");

  const applyBatchSearch = () => {
    const values = batchText
      .split(/\r?\n/)
      .map((line) => line.trim())
      .filter(Boolean);
    if (values.length === 0) {
      onMessage("请输入 SKU");
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
        <div className="product-management__batch-popover">
          <Typography.Text strong>精确搜索，一行一项，最多支持1000行</Typography.Text>
          <Input.TextArea
            value={batchText}
            placeholder="请输入 SKU，一行一个"
            rows={8}
            onChange={(event) => setBatchText(event.target.value)}
          />
          <div className="product-management__batch-actions">
            <Button onClick={() => setBatchText("")}>清空</Button>
            <Button onClick={() => setBatchOpen(false)}>关闭</Button>
            <Button type="primary" onClick={applyBatchSearch}>搜索</Button>
          </div>
        </div>
      )}
    >
      <Button
        className="report-table-connected-search__filter"
        aria-label="批量搜索 SKU"
        icon={<UnorderedListOutlined aria-hidden="true" />}
      />
    </Popover>
  );

  return (
    <div className="product-management__toolbar" role="search" aria-label="产品管理筛选">
      <Select
        className="report-filter-select"
        classNames={{ popup: { root: "report-filter-select-dropdown" } }}
        allowClear
        placeholder="产品等级"
        aria-label="产品等级"
        value={filters.productGrade}
        options={grades.map((value) => ({ value, label: value }))}
        onChange={(value) => onChange({ ...filters, productGrade: value })}
      />
      <Select
        className="report-filter-select"
        classNames={{ popup: { root: "report-filter-select-dropdown" } }}
        allowClear
        placeholder="标签"
        aria-label="标签"
        value={filters.tag}
        options={tags.map((value) => ({ value, label: value }))}
        onChange={(value) => onChange({ ...filters, tag: value })}
      />
      <ConnectedSearch
        className="product-management__search"
        typeAriaLabel="搜索类型"
        typeOptions={[
          { value: "sku", label: "SKU" },
          { value: "productName", label: "产品名称" },
          { value: "category", label: "类目" },
        ]}
        typeValue={filters.searchType}
        inputAriaLabel="搜索产品"
        inputPlaceholder="请输入搜索内容"
        inputValue={filters.keyword}
        batchControl={batchControl}
        onTypeChange={(searchType) => onChange({
          ...filters,
          searchType: searchType as ProductManagementFilters["searchType"],
        })}
        onInputChange={(keyword) => onChange({ ...filters, keyword })}
        onSearch={() => onMessage("已应用搜索条件")}
      />
      <ResetButton onClick={onReset} />
      <Button onClick={onToggleStatistics}>
        {statisticsVisible ? "隐藏统计" : "显示统计"}
      </Button>
      <Space className="product-management__toolbar-actions" size={8}>
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

export default ProductManagementToolbar;
