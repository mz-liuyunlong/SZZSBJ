import {
  CloudDownloadOutlined,
  SettingOutlined,
  UnorderedListOutlined,
} from "@ant-design/icons";
import { Button, Input, Popover, Select, Space, Typography } from "antd";
import { useState } from "react";
import ConnectedSearch from "@/components/report-table/ConnectedSearch";
import ResetButton from "@/components/report-table/ResetButton";
import type {
  ProductManagementFilters,
  ProductPersonOption,
  ProductSourceTagOption,
} from "@/pages/products/productManagementTypes";

interface ProductManagementToolbarProps {
  filters: ProductManagementFilters;
  owners: ProductPersonOption[];
  developers: ProductPersonOption[];
  tags: ProductSourceTagOption[];
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
  owners,
  developers,
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
  const [keywordDraft, setKeywordDraft] = useState(filters.keyword);

  const applyKeywordSearch = () => {
    onChange({
      ...filters,
      keyword: keywordDraft.trim(),
      batchValues: undefined,
    });
  };

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
    setKeywordDraft("");
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

  const sourceTagOptions = tags.map((tag) => ({
    value: tag.value,
    label: (
      <span className="product-management__source-tag-option">
        <span
          aria-hidden="true"
          className="product-management__source-tag-dot"
          style={{ backgroundColor: tag.color ?? "#D0D5DD" }}
        />
        <span>{tag.label}</span>
      </span>
    ),
  }));

  return (
    <div className="product-management__toolbar" role="search" aria-label="产品管理筛选">
      <Select
        className="report-filter-select"
        classNames={{ popup: { root: "report-filter-select-dropdown" } }}
        allowClear
        showSearch
        optionFilterProp="label"
        placeholder="负责人"
        aria-label="负责人"
        value={filters.ownerUid}
        options={owners.map((option) => ({ value: option.uid, label: option.name }))}
        onChange={(ownerUid) => onChange({ ...filters, ownerUid })}
      />
      <Select
        className="report-filter-select"
        classNames={{ popup: { root: "report-filter-select-dropdown" } }}
        allowClear
        showSearch
        optionFilterProp="label"
        placeholder="开发人"
        aria-label="开发人"
        value={filters.developerUid}
        options={developers.map((option) => ({ value: option.uid, label: option.name }))}
        onChange={(developerUid) => onChange({ ...filters, developerUid })}
      />
      <Select
        className="report-filter-select"
        classNames={{ popup: { root: "report-filter-select-dropdown" } }}
        allowClear
        showSearch
        optionFilterProp="label"
        placeholder="标签"
        aria-label="标签"
        value={filters.tag}
        options={sourceTagOptions}
        onChange={(tag) => onChange({ ...filters, tag })}
      />
      <ConnectedSearch
        className="product-management__search"
        typeAriaLabel="搜索类型"
        typeOptions={[{ value: "sku", label: "SKU" }]}
        typeValue="sku"
        inputAriaLabel="搜索产品"
        inputPlaceholder="请输入 SKU"
        inputValue={keywordDraft}
        batchControl={batchControl}
        onTypeChange={() => undefined}
        onInputChange={setKeywordDraft}
        onSearch={applyKeywordSearch}
      />
      <ResetButton
        onClick={() => {
          setKeywordDraft("");
          setBatchText("");
          onReset();
        }}
      />
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
