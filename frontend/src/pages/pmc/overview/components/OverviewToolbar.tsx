/** 总看板 filter toolbar: committed search, store / owner / problem type, issue switch, reset, column config. */
import { SettingOutlined } from "@ant-design/icons";
import { Button, Space, Switch } from "antd";
import { useMemo } from "react";
import CommittedSearch from "@/components/report-table/CommittedSearch";
import ResetButton from "@/components/report-table/ResetButton";
import ReportFacetSelect from "@/shared/report-filters";
import type { ReportFilterOption } from "@/shared/report-filters";
import {
  OVERVIEW_CATEGORIES,
  type OverviewCategory,
  type OverviewFilterOptions,
  type OverviewFilters,
} from "@/pages/pmc/overview/overviewTypes";

interface OverviewToolbarProps {
  filters: OverviewFilters;
  options?: OverviewFilterOptions;
  categoryCounts?: Partial<Record<OverviewCategory, number>>;
  onChange: (next: Partial<OverviewFilters>) => void;
  onReset: () => void;
  onOpenColumnConfig: () => void;
}

const SEARCH_TYPES = [{ value: "all", label: "全部" }];

function OverviewToolbar({ filters, options, categoryCounts, onChange, onReset, onOpenColumnConfig }: OverviewToolbarProps) {
  const storeOptions = useMemo<ReportFilterOption[]>(
    () => (options?.stores ?? []).map((s) => ({ value: s.id, label: s.name })),
    [options],
  );
  const ownerOptions = useMemo<ReportFilterOption[]>(
    () => (options?.owners ?? []).map((o) => ({ value: o, label: o })),
    [options],
  );
  const categoryOptions = useMemo<ReportFilterOption[]>(
    () => OVERVIEW_CATEGORIES.map((c) => ({ value: c, label: c, count: categoryCounts?.[c] })),
    [categoryCounts],
  );

  return (
    <div className="pmc-overview__toolbar" role="search" aria-label="总看板筛选">
      <CommittedSearch
        className="pmc-overview__search"
        typeAriaLabel="搜索类型"
        typeOptions={SEARCH_TYPES}
        typeValue="all"
        inputAriaLabel="搜索 ItemID"
        inputPlaceholder="ItemID / SKU / MSKU / 品名 / 草稿号，回车搜索"
        inputValue={filters.keyword}
        onCommit={({ keyword }) => onChange({ keyword: keyword.trim() })}
      />
      <ReportFacetSelect
        ariaLabel="店铺"
        placeholder="店铺"
        unit="个"
        value={filters.storeId}
        options={storeOptions}
        onChange={(value) => onChange({ storeId: (value as string | undefined) || undefined })}
      />
      <ReportFacetSelect
        ariaLabel="负责人"
        placeholder="负责人"
        unit="人"
        value={filters.owner}
        options={ownerOptions}
        onChange={(value) => onChange({ owner: (value as string | undefined) || undefined })}
      />
      <ReportFacetSelect
        mode="multiple"
        ariaLabel="问题类型"
        placeholder="问题类型"
        unit="类"
        value={filters.cats}
        options={categoryOptions}
        onChange={(value) => onChange({ cats: ((value as string[] | undefined) ?? []) as OverviewCategory[] })}
      />
      <label className="pmc-overview__toggle">
        <Switch
          size="small"
          aria-label="只看有问题的"
          checked={filters.onlyIssue}
          onChange={(checked) => onChange({ onlyIssue: checked })}
        />
        <span>只看有问题的</span>
      </label>
      <ResetButton aria-label="重置总看板筛选" onClick={onReset} />
      <Space className="pmc-overview__toolbar-actions" size={8}>
        <Button aria-label="列配置" icon={<SettingOutlined aria-hidden="true" />} onClick={onOpenColumnConfig} />
      </Space>
    </div>
  );
}

export default OverviewToolbar;
