/** Committed search and facet filters; does not query approval list APIs. */
import { DatePicker, Select, Typography } from "antd";
import zhCN from "antd/es/date-picker/locale/zh_CN";
import dayjs from "dayjs";
import CommittedSearch from "@/components/report-table/CommittedSearch";
import ResetButton from "@/components/report-table/ResetButton";
import ReportFacetSelect from "@/shared/report-filters/ReportFacetSelect";
import type { PackingApprovalArrivalFilter, PackingApprovalFilters, PackingApprovalOverdueFilter } from "./packingApprovalTypes";

interface Props {
  filters: PackingApprovalFilters;
  storeOptions: { value: string; label: string }[];
  optionsLoading: boolean;
  onChange: (filters: PackingApprovalFilters) => void;
  onReset: () => void;
}

export default function PackingApprovalToolbar({ filters, storeOptions, optionsLoading, onChange, onReset }: Props) {
  return <div className="domestic-board__toolbar domestic-approval__toolbar" role="search" aria-label="打包单审批筛选">
    <ReportFacetSelect mode="multiple" className="domestic-board__facet report-filter-select" ariaLabel="店铺"
      placeholder={optionsLoading ? "店铺加载中…" : "全部店铺"} unit="个店铺"
      value={filters.storeIds} options={storeOptions} popupWidth={360}
      onChange={(value) => onChange({ ...filters, storeIds: (value as string[]) ?? [] })} />
    <Select<PackingApprovalOverdueFilter> aria-label="审批是否超时" className="domestic-board__facet" value={filters.overdue}
      options={[{ value: "all", label: "审批超时（全部）" }, { value: "overdue", label: "已超时" }, { value: "not_overdue", label: "未超时" }]}
      onChange={(overdue) => onChange({ ...filters, overdue })} />
    <Select<PackingApprovalArrivalFilter> aria-label="到货情况" className="domestic-board__facet" value={filters.arrival}
      options={[{ value: "all", label: "到货情况（全部）" }, { value: "full", label: "已全部到货" }, { value: "partial", label: "部分到货" }, { value: "none", label: "未到货" }, { value: "unknown", label: "到货明细未知" }]}
      onChange={(arrival) => onChange({ ...filters, arrival })} />
    <CommittedSearch key={filters.search} className="domestic-board__search"
      typeAriaLabel="审批搜索类型" typeValue="all" typeOptions={[{ value: "all", label: "SKU / 单号" }]}
      inputAriaLabel="搜索待审批打包单" inputValue={filters.search}
      inputPlaceholder="SKU / 入库单 / 采购单 / ItemID"
      searchAriaLabel="搜索打包单审批"
      onCommit={({ keyword }) => onChange({ ...filters, search: keyword })} />
    <label className="domestic-approval__created-range">
      <Typography.Text type="secondary">到仓日期</Typography.Text>
      <DatePicker.RangePicker aria-label="来源入库到仓日期" locale={zhCN} format="YYYY-MM-DD"
        allowEmpty={[true, true]} placeholder={["开始日期", "结束日期"]}
        value={[filters.createdFrom ? dayjs(filters.createdFrom) : null, filters.createdTo ? dayjs(filters.createdTo) : null]}
        onChange={(_, dates) => onChange({ ...filters, createdFrom: dates[0] || undefined, createdTo: dates[1] || undefined })} />
    </label>
    <ResetButton aria-label="重置打包单审批筛选" onClick={onReset} />
  </div>;
}
