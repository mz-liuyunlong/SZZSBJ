import {
  CloudDownloadOutlined,
  SettingOutlined,
} from "@ant-design/icons";
import { Button, Space, Typography } from "antd";
import { useMemo } from "react";
import CommittedSearch from "@/components/report-table/CommittedSearch";
import ResetButton from "@/components/report-table/ResetButton";
import ReportFacetSelect from "@/shared/report-filters";
import type { ReportFilterOption } from "@/shared/report-filters";
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

const normalizeSelected = (values?: string[], legacyValue?: string) => (
  values && values.length > 0 ? values : legacyValue ? [legacyValue] : []
);

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
  const ownerOptions = useMemo<ReportFilterOption[]>(
    () => owners.map((option) => ({
      value: option.uid,
      label: option.name,
      count: option.count ?? 0,
    })),
    [owners],
  );

  const developerOptions = useMemo<ReportFilterOption[]>(
    () => developers.map((option) => ({
      value: option.uid,
      label: option.name,
      count: option.count ?? 0,
    })),
    [developers],
  );

  const sourceTagOptions = useMemo<ReportFilterOption[]>(
    () => tags.map((tag) => ({
      value: tag.value,
      label: tag.label,
      count: tag.count ?? 0,
      color: tag.color,
    })),
    [tags],
  );

  const sourceTagLabel = (option: ReportFilterOption) => (
    <span className="product-management__source-tag-option">
      <span
        aria-hidden="true"
        className="product-management__source-tag-dot"
        style={{ backgroundColor: option.color ?? "#D0D5DD" }}
      />
      <span>{option.label}</span>
      {option.count !== undefined && (
        <Typography.Text type="secondary">（{option.count}）</Typography.Text>
      )}
    </span>
  );

  return (
    <div className="product-management__toolbar" role="search" aria-label="产品管理筛选">
      <ReportFacetSelect
        mode="multiple"
        ariaLabel="负责人"
        placeholder="负责人"
        unit="人"
        value={normalizeSelected(filters.ownerUids, filters.ownerUid)}
        options={ownerOptions}
        onChange={(value) => onChange({
          ...filters,
          ownerUids: value as string[],
          ownerUid: undefined,
        })}
      />
      <ReportFacetSelect
        mode="multiple"
        ariaLabel="开发人"
        placeholder="开发人"
        unit="人"
        value={normalizeSelected(filters.developerUids, filters.developerUid)}
        options={developerOptions}
        onChange={(value) => onChange({
          ...filters,
          developerUids: value as string[],
          developerUid: undefined,
        })}
      />
      <ReportFacetSelect
        mode="multiple"
        ariaLabel="标签"
        placeholder="标签"
        unit="个标签"
        value={normalizeSelected(filters.tags, filters.tag)}
        options={sourceTagOptions}
        renderOptionLabel={sourceTagLabel}
        onChange={(value) => onChange({
          ...filters,
          tags: value as string[],
          tag: undefined,
        })}
      />
      <CommittedSearch
        className="product-management__search"
        typeAriaLabel="搜索类型"
        typeOptions={[{ value: "sku", label: "SKU" }]}
        typeValue="sku"
        inputAriaLabel="搜索产品"
        inputPlaceholder="请输入 SKU"
        inputValue={filters.keyword}
        batch={{
          ariaLabel: "批量搜索 SKU",
          placeholder: "请输入 SKU，一行一个",
          onMessage,
          onCommit: (values) => onBatchSearch(values),
        }}
        onCommit={({ keyword }) => onChange({
          ...filters,
          keyword,
          batchValues: undefined,
        })}
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
