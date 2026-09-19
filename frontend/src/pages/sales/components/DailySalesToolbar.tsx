/** Server-backed facet filters for the daily-sales acceptance shell. */
import { DatePicker, Radio, Select } from "antd";
import datePickerZhCN from "antd/es/date-picker/locale/zh_CN";
import dayjs, { type Dayjs } from "dayjs";
import "dayjs/locale/zh-cn";
import updateLocale from "dayjs/plugin/updateLocale";
import type { ReactNode } from "react";
import CommittedSearch from "@/components/report-table/CommittedSearch";
import ResetButton from "@/components/report-table/ResetButton";
import ReportFacetSelect from "@/shared/report-filters";
import type { ReportFilterOption } from "@/shared/report-filters";
import { disableFutureDate } from "@/shared/date/disableFutureDate";
import {
  dateRangeForPreset,
  type DailySalesCurrency,
  type DailySalesDatePreset,
  type DailySalesPlatform,
} from "@/pages/sales/dailySalesTypes";

dayjs.extend(updateLocale);
dayjs.locale("zh-cn");
dayjs.updateLocale("zh-cn", { weekStart: 0 });

export type DatePreset = DailySalesDatePreset;
export type SearchField = "msku" | "sku" | "productId" | "productName";

export interface DailySalesFilters {
  platforms: DailySalesPlatform[];
  owners: string[];
  stores: string[];
  currency: DailySalesCurrency;
  datePreset: DatePreset;
  dateRange?: [string, string];
  searchField: SearchField;
  keyword: string;
  batchValues?: string[];
}

interface DailySalesToolbarProps {
  filters: DailySalesFilters;
  platformOptions?: ReportFilterOption[];
  owners: ReportFilterOption[];
  stores: ReportFilterOption[];
  actions: ReactNode;
  trailingActions?: ReactNode;
  onChange: (filters: DailySalesFilters) => void;
  onReset: () => void;
  onMessage: (content: string) => void;
}

const defaultPlatformOptions: ReportFilterOption[] = [
  { value: "Walmart", label: "Walmart" },
  { value: "Amazon", label: "Amazon" },
  { value: "TEMU", label: "TEMU" },
];

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

const actualTodayRange = (): [string, string] => {
  const today = dayjs().format("YYYY-MM-DD");
  return [today, today];
};

const shortcutDateRange = (datePreset: Exclude<DatePreset, "custom">): [string, string] => (
  datePreset === "today" ? actualTodayRange() : dateRangeForPreset(datePreset)
);

const shortcutDatePresetValue = (datePreset: DatePreset) => (
  datePreset === "custom" ? undefined : datePreset
);

function DailySalesToolbar({
  filters,
  platformOptions = defaultPlatformOptions,
  owners,
  stores,
  actions,
  trailingActions,
  onChange,
  onReset,
  onMessage,
}: DailySalesToolbarProps) {
  const update = <Key extends keyof DailySalesFilters>(key: Key, value: DailySalesFilters[Key]) => {
    onChange({ ...filters, [key]: value });
  };

  return (
    <div className="daily-sales__toolbar" role="search" aria-label="每日销售筛选">
      <div className="daily-sales__toolbar-row daily-sales__toolbar-row--single">
        <ReportFacetSelect
          mode="multiple"
          ariaLabel="平台"
          placeholder="全部平台"
          unit="个平台"
          value={filters.platforms}
          options={platformOptions}
          optionCheckboxClassName="daily-sales__filter-checkbox"
          onChange={(value) => update("platforms", value as DailySalesPlatform[])}
        />
        <ReportFacetSelect
          mode="multiple"
          ariaLabel="负责人"
          placeholder="负责人"
          unit="人"
          value={filters.owners}
          options={owners}
          optionCheckboxClassName="daily-sales__filter-checkbox"
          onChange={(value) => update("owners", value as string[])}
        />
        <ReportFacetSelect
          mode="multiple"
          ariaLabel="店铺"
          placeholder="全部店铺"
          unit="个店铺"
          value={filters.stores}
          options={stores}
          popupWidth={360}
          optionCheckboxClassName="daily-sales__filter-checkbox"
          onChange={(value) => update("stores", value as string[])}
        />
        <Radio.Group
          key={`date-preset-${filters.datePreset}`}
          className="daily-sales__date-presets"
          aria-label="日期快捷项"
          optionType="button"
          buttonStyle="solid"
          value={shortcutDatePresetValue(filters.datePreset)}
          options={[
            { label: "今日", value: "today" },
            { label: "本周", value: "week" },
            { label: "本月", value: "month" },
            { label: "今年", value: "year" },
          ]}
          onChange={(event) => {
            const datePreset = event.target.value as Exclude<DatePreset, "custom">;
            onChange({ ...filters, datePreset, dateRange: shortcutDateRange(datePreset) });
          }}
        />
        <DatePicker.RangePicker
          className="daily-sales__date-range"
          aria-label="日期范围"
          locale={datePickerLocale}
          value={filters.dateRange
            ? [dayjs(filters.dateRange[0]), dayjs(filters.dateRange[1])]
            : undefined}
          presets={rangePresets()}
          format="YYYY-MM-DD"
          disabledDate={disableFutureDate}
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
          className="report-filter-select daily-sales__currency-select"
          classNames={{ popup: { root: "report-filter-select-dropdown" } }}
          aria-label="币种"
          value={filters.currency}
          options={["USD", "CNY"].map((value) => ({ label: value, value }))}
          onChange={(value) => update("currency", value as DailySalesCurrency)}
        />
        <CommittedSearch
          className="daily-sales__search"
          typeAriaLabel="搜索类型"
          typeOptions={[
            { label: "MSKU", value: "msku" },
            { label: "SKU", value: "sku" },
            { label: "商品ID", value: "productId" },
            { label: "品名", value: "productName" },
          ]}
          typeValue={filters.searchField}
          inputAriaLabel="搜索内容"
          inputPlaceholder="搜索 MSKU / SKU / 商品ID / 品名"
          inputValue={filters.keyword}
          batch={{
            ariaLabel: "批量搜索",
            placeholder: "请输入 MSKU / SKU / 商品ID，一行一个",
            unsupportedMessage: "批量搜索仅支持 MSKU、SKU、商品ID",
            isSupported: (searchField) => searchField !== "productName",
            onMessage,
            onCommit: (values, searchField) => onChange({
              ...filters,
              searchField: searchField as SearchField,
              keyword: "",
              batchValues: values,
            }),
          }}
          onCommit={({ searchField, keyword }) => onChange({
            ...filters,
            searchField: searchField as SearchField,
            keyword,
            batchValues: undefined,
          })}
        />
        <ResetButton onClick={onReset} />
        <div className="daily-sales__toolbar-actions">{actions}</div>
        <span className="daily-sales__toolbar-spacer" aria-hidden="true" />
        <div className="daily-sales__toolbar-icon-actions">{trailingActions}</div>
      </div>
    </div>
  );
}

export default DailySalesToolbar;
