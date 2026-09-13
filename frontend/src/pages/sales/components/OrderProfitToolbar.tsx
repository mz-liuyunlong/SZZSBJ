/** Local no-API filters for the product-ID order-profit acceptance shell. */
import { UnorderedListOutlined } from "@ant-design/icons";
import { Button, Checkbox, DatePicker, Input, Popover, Radio, Select, Space, Typography } from "antd";
import datePickerZhCN from "antd/es/date-picker/locale/zh_CN";
import dayjs, { type Dayjs } from "dayjs";
import "dayjs/locale/zh-cn";
import updateLocale from "dayjs/plugin/updateLocale";
import { useState, type ReactNode } from "react";
import ConnectedSearch from "@/components/report-table/ConnectedSearch";
import ResetButton from "@/components/report-table/ResetButton";
import {
  dateRangeForPreset,
  type OrderProfitCurrency,
  type OrderProfitDatePreset,
  type OrderProfitPlatform,
} from "@/pages/sales/orderProfitTypes";

dayjs.extend(updateLocale);
dayjs.locale("zh-cn");
dayjs.updateLocale("zh-cn", { weekStart: 0 });

export type DatePreset = OrderProfitDatePreset;
export type SearchField = "productId" | "productName" | "sku" | "msku";

export interface OrderProfitFilters {
  platforms: OrderProfitPlatform[];
  owners: string[];
  stores: string[];
  currency: OrderProfitCurrency;
  datePreset: DatePreset;
  dateRange?: [string, string];
  searchField: SearchField;
  keyword: string;
  batchValues?: string[];
}

interface OrderProfitToolbarProps {
  filters: OrderProfitFilters;
  owners: string[];
  stores: string[];
  actions: ReactNode;
  trailingActions?: ReactNode;
  onChange: (filters: OrderProfitFilters) => void;
  onReset: () => void;
  onMessage: (content: string) => void;
}

const rangePresets = (): { label: string; value: [Dayjs, Dayjs] }[] => {
  const today = dayjs();
  return [
    { label: "今天", value: [today, today] },
    { label: "昨天", value: [today.subtract(1, "day"), today.subtract(1, "day")] },
    { label: "最近7天", value: [today.subtract(6, "day"), today] },
    { label: "最近30天", value: [today.subtract(29, "day"), today] },
    { label: "本月", value: [today.startOf("month"), today] },
    { label: "上月", value: [today.subtract(1, "month").startOf("month"), today.subtract(1, "month").endOf("month")] },
    { label: "本年", value: [today.startOf("year"), today] },
    { label: "去年", value: [today.subtract(1, "year").startOf("year"), today.subtract(1, "year").endOf("year")] },
  ];
};

const datePickerLocale = {
  ...datePickerZhCN,
  lang: {
    ...datePickerZhCN.lang,
    monthFormat: "M 月",
    shortWeekDays: ["日", "一", "二", "三", "四", "五", "六"],
  },
};

const selectedLabel = (values: string[], unit: string, fallback: string) => {
  if (values.length === 0) return fallback;
  if (values.length === 1) return values[0];
  return `已选 ${values.length} ${unit}`;
};

const checkboxOption = (selectedValues: string[], ariaLabel: string) => (
  option: { label?: ReactNode; value?: string | number },
) => {
  const value = String(option.value);
  return (
    <Checkbox
      className="order-profit__filter-checkbox"
      checked={selectedValues.includes(value)}
      aria-label={`${ariaLabel}选项：${String(option.label)}`}
      tabIndex={-1}
    >
      {option.label}
    </Checkbox>
  );
};

function OrderProfitToolbar({
  filters,
  owners,
  stores,
  actions,
  trailingActions,
  onChange,
  onReset,
  onMessage,
}: OrderProfitToolbarProps) {
  const [batchOpen, setBatchOpen] = useState(false);
  const [batchInput, setBatchInput] = useState("");

  const update = <Key extends keyof OrderProfitFilters>(key: Key, value: OrderProfitFilters[Key]) => {
    onChange({ ...filters, [key]: value });
  };
  const batchSupported = filters.searchField !== "productName";
  const submitBatchSearch = () => {
    const values = batchInput.split("\n").map((value) => value.trim()).filter(Boolean);
    if (values.length > 1000) {
      onMessage("最多支持1000行");
      return;
    }
    if (values.length === 0) {
      onMessage("请输入商品ID / SKU / MSKU");
      return;
    }
    onChange({ ...filters, keyword: "", batchValues: values });
    setBatchOpen(false);
  };

  const batchContent = (
    <div className="order-profit__batch-search" aria-label="批量搜索">
      <Typography.Text>精确搜索，一行一项，最多支持1000行</Typography.Text>
      <Input.TextArea
        aria-label="批量搜索内容"
        placeholder="请输入商品ID / SKU / MSKU，一行一个"
        value={batchInput}
        rows={7}
        onChange={(event) => setBatchInput(event.target.value)}
      />
      <Space className="order-profit__batch-actions">
        <Button onClick={() => setBatchInput("")}>清空</Button>
        <Button onClick={() => setBatchOpen(false)}>关闭</Button>
        <Button type="primary" onClick={submitBatchSearch}>搜索</Button>
      </Space>
    </div>
  );

  return (
    <div className="order-profit__toolbar" role="search" aria-label="订单利润筛选">
      <div className="order-profit__toolbar-row order-profit__toolbar-row--single">
        <Select
          mode="multiple"
          showSearch
          className="report-filter-select"
          classNames={{ popup: { root: "report-filter-select-dropdown report-filter-select-dropdown--multiple" } }}
          aria-label="平台"
          placeholder="全部平台"
          value={filters.platforms}
          maxTagCount={0}
          maxTagPlaceholder={() => selectedLabel(filters.platforms, "个平台", "全部平台")}
          options={["Walmart", "TEMU", "Amazon"].map((value) => ({ label: value, value }))}
          optionRender={checkboxOption(filters.platforms, "平台")}
          onChange={(value) => update("platforms", value as OrderProfitPlatform[])}
        />
        <Select
          mode="multiple"
          showSearch
          className="report-filter-select"
          classNames={{ popup: { root: "report-filter-select-dropdown report-filter-select-dropdown--multiple" } }}
          aria-label="负责人"
          placeholder="负责人"
          value={filters.owners}
          maxTagCount={0}
          maxTagPlaceholder={() => selectedLabel(filters.owners, "人", "负责人")}
          options={owners.map((value) => ({ label: value, value }))}
          optionRender={checkboxOption(filters.owners, "负责人")}
          onChange={(value) => update("owners", value)}
        />
        <Select
          mode="multiple"
          showSearch
          className="report-filter-select"
          classNames={{ popup: { root: "report-filter-select-dropdown report-filter-select-dropdown--multiple" } }}
          aria-label="店铺"
          placeholder="全部店铺"
          value={filters.stores}
          maxTagCount={0}
          maxTagPlaceholder={() => selectedLabel(filters.stores, "个店铺", "全部店铺")}
          options={stores.map((value) => ({ label: value, value }))}
          optionRender={checkboxOption(filters.stores, "店铺")}
          onChange={(value) => update("stores", value)}
        />
        <Radio.Group
          className="order-profit__date-presets"
          aria-label="日期快捷项"
          optionType="button"
          buttonStyle="solid"
          value={filters.datePreset === "custom" ? undefined : filters.datePreset}
          options={[
            { label: "今日", value: "today" },
            { label: "本周", value: "week" },
            { label: "本月", value: "month" },
            { label: "今年", value: "year" },
          ]}
          onChange={(event) => {
            const datePreset = event.target.value as Exclude<DatePreset, "custom">;
            onChange({ ...filters, datePreset, dateRange: dateRangeForPreset(datePreset) });
          }}
        />
        <DatePicker.RangePicker
          className="order-profit__date-range"
          aria-label="日期范围"
          locale={datePickerLocale}
          value={filters.dateRange
            ? [dayjs(filters.dateRange[0]), dayjs(filters.dateRange[1])]
            : undefined}
          presets={rangePresets()}
          format="YYYY-MM-DD"
          separator="~"
          onChange={(dates) => onChange({
            ...filters,
            datePreset: "custom",
            dateRange: dates
              ? [dates[0]?.format("YYYY-MM-DD") ?? "", dates[1]?.format("YYYY-MM-DD") ?? ""]
              : undefined,
          })}
        />
        <Select
          className="report-filter-select order-profit__currency-select"
          classNames={{ popup: { root: "report-filter-select-dropdown" } }}
          aria-label="币种"
          value={filters.currency}
          options={["USD", "CNY"].map((value) => ({ label: value, value }))}
          onChange={(value) => update("currency", value as OrderProfitCurrency)}
        />
        <ConnectedSearch
          className="order-profit__search"
          typeAriaLabel="搜索类型"
          typeOptions={[
            { label: "商品ID", value: "productId" },
            { label: "品名", value: "productName" },
            { label: "SKU", value: "sku" },
            { label: "MSKU", value: "msku" },
          ]}
          typeValue={filters.searchField}
          inputAriaLabel="搜索内容"
          inputPlaceholder="搜索商品ID / 品名 / SKU / MSKU"
          inputValue={filters.keyword}
          onTypeChange={(value) => onChange({
            ...filters,
            searchField: value as SearchField,
            batchValues: undefined,
          })}
          onInputChange={(value) => onChange({
            ...filters,
            keyword: value,
            batchValues: undefined,
          })}
          onSearch={() => onChange({ ...filters, batchValues: undefined })}
          batchControl={(
            <Popover
              trigger="click"
              placement="bottomRight"
              open={batchOpen}
              content={batchContent}
              onOpenChange={(open) => {
                if (open && !batchSupported) {
                  onMessage("批量搜索仅支持商品ID、SKU、MSKU");
                  return;
                }
                setBatchOpen(open);
              }}
            >
              <Button
                className="report-table-connected-search__batch"
                aria-label="批量搜索"
                icon={<UnorderedListOutlined aria-hidden="true" />}
              />
            </Popover>
          )}
        />
        <ResetButton onClick={onReset} />
        <div className="order-profit__toolbar-actions">{actions}</div>
        <span className="order-profit__toolbar-spacer" aria-hidden="true" />
        <div className="order-profit__toolbar-icon-actions">{trailingActions}</div>
      </div>
    </div>
  );
}

export default OrderProfitToolbar;
