import { SearchOutlined } from "@ant-design/icons";
import { Button, Checkbox, DatePicker, Input, Select, Space } from "antd";
import dayjs, { type Dayjs } from "dayjs";
import type { ReactNode } from "react";
import {
  type WfsFeeAlertCaseStatus,
  type WfsFeeAlertFilters,
  type WfsFeeAlertSearchField,
} from "@/pages/warehouse/wfsFeeAlertTypes";

interface WfsFeeAlertToolbarProps {
  filters: WfsFeeAlertFilters;
  stores: string[];
  owners: string[];
  reasons: string[];
  actions: ReactNode;
  trailingActions: ReactNode;
  onChange: (filters: WfsFeeAlertFilters) => void;
  onReset: () => void;
  onBatchOpenCase: () => void;
  onBatchFollow: () => void;
}


const statusOptions: { label: WfsFeeAlertCaseStatus; value: WfsFeeAlertCaseStatus }[] = [
  { label: "未开Case", value: "未开Case" },
  { label: "已开Case", value: "已开Case" },
  { label: "跟进中", value: "跟进中" },
  { label: "已追回", value: "已追回" },
  { label: "驳回", value: "驳回" },
  { label: "已关闭", value: "已关闭" },
];


const referenceDate = dayjs("2026-09-13");

const rangePickerPresets: { label: string; value: [Dayjs, Dayjs] }[] = [
  { label: "今天", value: [referenceDate, referenceDate] },
  { label: "昨天", value: [referenceDate.subtract(1, "day"), referenceDate.subtract(1, "day")] },
  { label: "最近7天", value: [referenceDate.subtract(6, "day"), referenceDate] },
  { label: "最近30天", value: [referenceDate.subtract(29, "day"), referenceDate] },
  { label: "本月", value: [referenceDate.startOf("month"), referenceDate.endOf("month")] },
  { label: "上月", value: [
    referenceDate.subtract(1, "month").startOf("month"),
    referenceDate.subtract(1, "month").endOf("month"),
  ] },
  { label: "本年", value: [referenceDate.startOf("year"), referenceDate.endOf("year")] },
  { label: "去年", value: [
    referenceDate.subtract(1, "year").startOf("year"),
    referenceDate.subtract(1, "year").endOf("year"),
  ] },
];

const searchOptions: { label: string; value: WfsFeeAlertSearchField }[] = [
  { label: "SKU", value: "sku" },
  { label: "MSKU", value: "msku" },
  { label: "商品ID", value: "productId" },
  { label: "品名", value: "productName" },
];

function optionRender(label: string, prefix: string) {
  return (
    <Space>
      <Checkbox aria-label={`${prefix}选项：${label}`} tabIndex={-1} />
      {label}
    </Space>
  );
}

function WfsFeeAlertToolbar({
  filters,
  stores,
  owners,
  reasons,
  actions,
  trailingActions,
  onChange,
  onReset,
  onBatchOpenCase,
  onBatchFollow,
}: WfsFeeAlertToolbarProps) {

  return (
    <div className="wfs-fee-alert__toolbar" role="search" aria-label="WFS费用异常筛选">
      <DatePicker.RangePicker
        aria-label="日期范围"
        className="wfs-fee-alert__date-range"
        allowClear={false}
        format="YYYY-MM-DD"
        presets={rangePickerPresets}
        value={[dayjs(filters.dateRange[0]), dayjs(filters.dateRange[1])]}
        onChange={(dates) => {
          if (!dates?.[0] || !dates?.[1]) return;
          onChange({
            ...filters,
            datePreset: "custom",
            dateRange: [
              dates[0].format("YYYY-MM-DD"),
              dates[1].format("YYYY-MM-DD"),
            ],
          });
        }}
      />
      <Select
        aria-label="币种"
        className="wfs-fee-alert__currency-select"
        value={filters.currency}
        options={[{ label: "USD", value: "USD" }, { label: "CNY", value: "CNY" }]}
        onChange={(currency) => onChange({ ...filters, currency })}
      />
      <Select
        aria-label="店铺"
        className="wfs-fee-alert__filter-select"
        mode="multiple"
        allowClear
        maxTagCount="responsive"
        placeholder="全部店铺"
        value={filters.stores}
        options={stores.map((store) => ({ label: store, value: store }))}
        optionRender={(option) => optionRender(String(option.label), "店铺")}
        onChange={(nextStores) => onChange({ ...filters, stores: nextStores })}
      />
      <Select
        aria-label="负责人"
        className="wfs-fee-alert__filter-select"
        mode="multiple"
        allowClear
        maxTagCount="responsive"
        placeholder="负责人"
        value={filters.owners}
        options={owners.map((owner) => ({ label: owner, value: owner }))}
        optionRender={(option) => optionRender(String(option.label), "负责人")}
        onChange={(nextOwners) => onChange({ ...filters, owners: nextOwners })}
      />
      <Select
        aria-label="Case状态"
        className="wfs-fee-alert__filter-select"
        mode="multiple"
        allowClear
        maxTagCount="responsive"
        placeholder="Case状态"
        value={filters.statuses}
        options={statusOptions}
        optionRender={(option) => optionRender(String(option.label), "Case状态")}
        onChange={(statuses) => onChange({ ...filters, statuses })}
      />
      <Select
        aria-label="异常原因"
        className="wfs-fee-alert__filter-select"
        mode="multiple"
        allowClear
        maxTagCount="responsive"
        placeholder="异常原因"
        value={filters.reasons}
        options={reasons.map((reason) => ({ label: reason, value: reason }))}
        optionRender={(option) => optionRender(String(option.label), "异常原因")}
        onChange={(nextReasons) => onChange({ ...filters, reasons: nextReasons })}
      />
      <div className="wfs-fee-alert__connected-search">
        <Select
          aria-label="搜索类型"
          value={filters.searchField}
          options={searchOptions}
          onChange={(searchField) => onChange({ ...filters, searchField })}
        />
        <Input
          aria-label="搜索内容"
          value={filters.keyword}
          placeholder="搜索 SKU / MSKU / 商品ID / 品名"
          onChange={(event) => onChange({ ...filters, keyword: event.target.value })}
          onPressEnter={() => onChange(filters)}
        />
        <Button aria-label="搜索" icon={<SearchOutlined aria-hidden="true" />} onClick={() => onChange(filters)} />
      </div>
      <Button className="report-table-reset-button" onClick={onReset}>重置</Button>
      {actions}
      <Button onClick={onBatchOpenCase}>批量开Case</Button>
      <Button onClick={onBatchFollow}>批量跟进</Button>
      <span className="wfs-fee-alert__toolbar-spacer" aria-hidden="true" />
      <span className="wfs-fee-alert__toolbar-icon-actions">
        {trailingActions}
      </span>
    </div>
  );
}

export default WfsFeeAlertToolbar;
