/** Purchase-board filter toolbar: owner / status / connected batch search / order-date range / more. */
import { FilterOutlined, SettingOutlined } from "@ant-design/icons";
import { Badge, Button, DatePicker, Select, Space, Switch } from "antd";
import datePickerZhCN from "antd/es/date-picker/locale/zh_CN";
import dayjs from "dayjs";
import { useMemo } from "react";
import CommittedSearch from "@/components/report-table/CommittedSearch";
import ResetButton from "@/components/report-table/ResetButton";
import ReportFacetSelect from "@/shared/report-filters";
import type { ReportFilterOption } from "@/shared/report-filters";
import type { PurchaseBoardOwnerOption } from "@/pages/pmc/purchase-board/purchaseBoardApi";
import {
  purchaseBoardSearchTypeOptions,
  purchaseBoardSortOptions,
  purchaseBoardStatusOptions,
  type PurchaseBoardFilters,
  type PurchaseBoardSearchType,
  type PurchaseBoardSort,
  type PurchaseBoardStatusFilter,
} from "@/pages/pmc/purchase-board/purchaseBoardTypes";

interface PurchaseBoardToolbarProps {
  filters: PurchaseBoardFilters;
  owners: PurchaseBoardOwnerOption[];
  ownersLoading: boolean;
  moreFilterCount: number;
  onChange: (filters: PurchaseBoardFilters) => void;
  onBatchSearch: (values: string[], searchType: PurchaseBoardSearchType) => void;
  onReset: () => void;
  onMessage: (content: string) => void;
  onOpenMoreFilters: () => void;
  onOpenColumnConfig: () => void;
}

const isSearchType = (value: string): value is PurchaseBoardSearchType => (
  purchaseBoardSearchTypeOptions.some((option) => option.value === value)
);

function PurchaseBoardToolbar({
  filters,
  owners,
  ownersLoading,
  moreFilterCount,
  onChange,
  onBatchSearch,
  onReset,
  onMessage,
  onOpenMoreFilters,
  onOpenColumnConfig,
}: PurchaseBoardToolbarProps) {
  const ownerOptions = useMemo<ReportFilterOption[]>(
    () => owners.map((owner) => ({ value: owner.uid, label: owner.name, count: owner.count })),
    [owners],
  );
  const statusOptions = useMemo<ReportFilterOption[]>(
    () => purchaseBoardStatusOptions.map((option) => ({ value: option.value, label: option.label })),
    [],
  );

  return (
    <div className="purchase-board__toolbar" role="search" aria-label="采购看板筛选">
      <ReportFacetSelect
        mode="multiple"
        ariaLabel="负责人"
        placeholder={ownersLoading ? "负责人加载中" : "负责人"}
        unit="人"
        value={filters.ownerUids}
        options={ownerOptions}
        onChange={(value) => onChange({ ...filters, ownerUids: (value as string[] | undefined) ?? [] })}
      />
      <ReportFacetSelect
        mode="multiple"
        ariaLabel="状态"
        placeholder="状态"
        unit="项"
        value={filters.statuses}
        options={statusOptions}
        onChange={(value) => onChange({
          ...filters,
          statuses: ((value as string[] | undefined) ?? []) as PurchaseBoardStatusFilter[],
        })}
      />
      <CommittedSearch
        className="purchase-board__search"
        typeAriaLabel="搜索类型"
        typeOptions={purchaseBoardSearchTypeOptions}
        typeValue={filters.searchType}
        inputAriaLabel="搜索采购单"
        inputPlaceholder="输入后回车，支持逗号或空格分隔多个值"
        inputValue={filters.keyword}
        batch={{
          ariaLabel: "批量搜索",
          placeholder: "一行一个值，最多 200 个",
          onMessage,
          onCommit: (values, searchField) => {
            if (values.length > 200) {
              onMessage("批量搜索最多支持 200 个值，请分批查询");
              return;
            }
            onBatchSearch(values, isSearchType(searchField) ? searchField : "sku");
          },
        }}
        onCommit={({ searchField, keyword }) => onChange({
          ...filters,
          searchType: isSearchType(searchField) ? searchField : "sku",
          keyword,
          batchValues: undefined,
        })}
      />
      <DatePicker.RangePicker
        className="purchase-board__date-range"
        aria-label="下单日期"
        locale={datePickerZhCN}
        placeholder={["下单开始", "下单结束"]}
        allowEmpty={[true, true]}
        format="YYYY-MM-DD"
        separator="~"
        value={[
          filters.orderDateFrom ? dayjs(filters.orderDateFrom) : null,
          filters.orderDateTo ? dayjs(filters.orderDateTo) : null,
        ]}
        onChange={(dates) => onChange({
          ...filters,
          orderDateFrom: dates?.[0] ? dates[0].format("YYYY-MM-DD") : undefined,
          orderDateTo: dates?.[1] ? dates[1].format("YYYY-MM-DD") : undefined,
        })}
      />
      <Badge count={moreFilterCount} size="small" offset={[-2, 2]}>
        <Button
          aria-label="更多筛选"
          icon={<FilterOutlined aria-hidden="true" />}
          onClick={onOpenMoreFilters}
        >
          更多筛选
        </Button>
      </Badge>
      <label className="purchase-board__followup-toggle">
        <Switch
          size="small"
          aria-label="今日待跟进"
          checked={filters.todayFollowup}
          onChange={(checked) => onChange({ ...filters, todayFollowup: checked })}
        />
        <span>今日待跟进</span>
      </label>
      <ResetButton onClick={onReset} />
      <Space className="purchase-board__toolbar-actions" size={8}>
        <Select<PurchaseBoardSort>
          aria-label="排序"
          className="purchase-board__sort"
          value={filters.sort}
          options={purchaseBoardSortOptions}
          onChange={(sort) => onChange({ ...filters, sort })}
        />
        <Button
          aria-label="列配置"
          icon={<SettingOutlined aria-hidden="true" />}
          onClick={onOpenColumnConfig}
        />
      </Space>
    </div>
  );
}

export default PurchaseBoardToolbar;
