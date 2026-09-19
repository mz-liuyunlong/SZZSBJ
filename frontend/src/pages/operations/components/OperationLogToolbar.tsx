import {
  CloudDownloadOutlined,
  SettingOutlined,
  UnorderedListOutlined,
} from "@ant-design/icons";
import { Button, Checkbox, DatePicker, Select, Space, Tooltip } from "antd";
import dayjs, { type Dayjs } from "dayjs";
import type { ReactNode } from "react";
import ConnectedSearch from "@/components/report-table/ConnectedSearch";
import { disableFutureDate } from "@/shared/date/disableFutureDate";
import {
  type OperationLogDatePreset,
  type OperationLogFilters,
  type OperationLogSearchField,
  type OperationLogSystemFilter,
  type OperationLogWorkType,
} from "@/pages/operations/operationLogTypes";

interface OperationLogToolbarProps {
  filters: OperationLogFilters;
  owners: string[];
  stores: string[];
  workTypes: OperationLogWorkType[];
  trailingActions?: ReactNode;
  onChange: (filters: OperationLogFilters) => void;
  onReset: () => void;
  onOpenBatchSearch: () => void;
  onOpenColumnConfig: () => void;
  onDownload: () => void;
}

const referenceDate = dayjs("2026-09-13");

const rangePickerPresets: { label: string; value: [Dayjs, Dayjs] }[] = [
  { label: "今天", value: [referenceDate, referenceDate] },
  { label: "昨天", value: [referenceDate.subtract(1, "day"), referenceDate.subtract(1, "day")] },
  { label: "最近7天", value: [referenceDate.subtract(6, "day"), referenceDate] },
  { label: "最近30天", value: [referenceDate.subtract(29, "day"), referenceDate] },
  { label: "本月", value: [referenceDate.startOf("month"), referenceDate.endOf("month")] },
  {
    label: "上月",
    value: [
      referenceDate.subtract(1, "month").startOf("month"),
      referenceDate.subtract(1, "month").endOf("month"),
    ],
  },
  { label: "本年", value: [referenceDate.startOf("year"), referenceDate.endOf("year")] },
  {
    label: "去年",
    value: [
      referenceDate.subtract(1, "year").startOf("year"),
      referenceDate.subtract(1, "year").endOf("year"),
    ],
  },
];

const systemOptions: { label: string; value: OperationLogSystemFilter }[] = [
  { label: "系统日志：全部", value: "all" },
  { label: "有系统记录", value: "has" },
  { label: "缺系统记录", value: "missing" },
];

const searchOptions: { label: string; value: OperationLogSearchField }[] = [
  { label: "商品ID", value: "productId" },
  { label: "SKU", value: "sku" },
  { label: "商品名", value: "productName" },
  { label: "店铺", value: "store" },
  { label: "运营", value: "owner" },
  { label: "日期", value: "date" },
];

function optionRender(label: string, prefix: string) {
  return (
    <Space>
      <Checkbox aria-label={`${prefix}选项：${label}`} tabIndex={-1} />
      {label}
    </Space>
  );
}

function OperationLogToolbar({
  filters,
  owners,
  stores,
  workTypes,
  trailingActions,
  onChange,
  onReset,
  onOpenBatchSearch,
  onOpenColumnConfig,
  onDownload,
}: OperationLogToolbarProps) {
  return (
    <div className="operation-log__toolbar" role="search" aria-label="运营日志筛选">
      <DatePicker.RangePicker
        aria-label="日期范围"
        className="operation-log__date-range"
        allowClear={false}
        format="YYYY-MM-DD"
          disabledDate={disableFutureDate}
        presets={rangePickerPresets}
        value={[dayjs(filters.dateRange[0]), dayjs(filters.dateRange[1])]}
        onChange={(dates) => {
          if (!dates?.[0] || !dates?.[1]) return;
          onChange({
            ...filters,
            datePreset: "custom" as OperationLogDatePreset,
            dateRange: [
              dates[0].format("YYYY-MM-DD"),
              dates[1].format("YYYY-MM-DD"),
            ],
          });
        }}
      />

      <Select
        aria-label="运营"
        className="operation-log__filter-select"
        mode="multiple"
        allowClear
        maxTagCount="responsive"
        placeholder="运营：全部"
        value={filters.owners}
        options={owners.map((owner) => ({ label: owner, value: owner }))}
        optionRender={(option) => optionRender(String(option.label), "运营")}
        onChange={(nextOwners) => onChange({ ...filters, owners: nextOwners })}
      />

      <Select
        aria-label="店铺"
        className="operation-log__filter-select"
        mode="multiple"
        allowClear
        maxTagCount="responsive"
        placeholder="店铺：全部"
        value={filters.stores}
        options={stores.map((store) => ({ label: store, value: store }))}
        optionRender={(option) => optionRender(String(option.label), "店铺")}
        onChange={(nextStores) => onChange({ ...filters, stores: nextStores })}
      />

      <Select
        aria-label="工作类型"
        className="operation-log__filter-select"
        mode="multiple"
        allowClear
        maxTagCount="responsive"
        placeholder="工作类型：全部"
        value={filters.workTypes}
        options={workTypes.map((workType) => ({ label: workType, value: workType }))}
        optionRender={(option) => optionRender(String(option.label), "工作类型")}
        onChange={(nextWorkTypes) => onChange({ ...filters, workTypes: nextWorkTypes })}
      />

      <Select
        aria-label="系统日志"
        className="operation-log__filter-select"
        value={filters.systemLog}
        options={systemOptions}
        onChange={(systemLog) => onChange({ ...filters, systemLog })}
      />

      <ConnectedSearch
        className="operation-log__search"
        typeAriaLabel="搜索类型"
        typeOptions={searchOptions}
        typeValue={filters.searchField}
        inputAriaLabel="搜索运营日志"
        inputPlaceholder="请输入搜索内容"
        inputValue={filters.keyword}
        batchControl={(
          <Button
            className="report-table-connected-search__filter"
            aria-label="批量搜索"
            icon={<UnorderedListOutlined aria-hidden="true" />}
            onClick={onOpenBatchSearch}
          />
        )}
        onTypeChange={(searchField) => onChange({
          ...filters,
          searchField: searchField as OperationLogSearchField,
        })}
        onInputChange={(keyword) => onChange({ ...filters, keyword })}
        onSearch={() => onChange(filters)}
      />

      <Button className="report-table-reset-button" onClick={onReset}>
        重置
      </Button>

      <span className="operation-log__toolbar-spacer" aria-hidden="true" />

      <span className="operation-log__toolbar-icon-actions">
        {trailingActions}
        <Tooltip title="列配置">
          <Button
            aria-label="列配置"
            className="operation-log__toolbar-icon-button"
            icon={<SettingOutlined aria-hidden="true" />}
            onClick={onOpenColumnConfig}
          />
        </Tooltip>
        <Tooltip title="下载">
          <Button
            aria-label="下载"
            className="operation-log__toolbar-icon-button"
            icon={<CloudDownloadOutlined aria-hidden="true" />}
            onClick={onDownload}
          />
        </Tooltip>
      </span>
    </div>
  );
}

export default OperationLogToolbar;
