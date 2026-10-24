/** Uses the existing committed-search and reset controls; does not submit business requests. */
import { DatePicker, Select, Typography } from "antd";
import zhCN from "antd/es/date-picker/locale/zh_CN";
import dayjs from "dayjs";
import CommittedSearch from "@/components/report-table/CommittedSearch";
import ResetButton from "@/components/report-table/ResetButton";
import type { PackingWarehouseFilters, PackingWarehouseStatus } from "./packingWarehouseTypes";

interface Props {
  filters: PackingWarehouseFilters;
  onChange: (filters: PackingWarehouseFilters) => void;
  onReset: () => void;
  storeOptions: { value: string; label: string }[];
  optionsLoading: boolean;
}

export default function PackingWarehouseToolbar({ filters, onChange, onReset, storeOptions, optionsLoading }: Props) {
  return <div className="domestic-board__toolbar domestic-packing__toolbar" role="search" aria-label="仓库打包单筛选">
    <Select aria-label="打包单店铺" placeholder="全部店铺" allowClear showSearch optionFilterProp="label" className="domestic-board__facet" value={filters.storeId} options={storeOptions} loading={optionsLoading} onChange={(storeId) => onChange({ ...filters, storeId })} />
    <Select<PackingWarehouseStatus> aria-label="打包状态" className="domestic-board__facet" value={filters.status}
      options={[{ value: "todo", label: "待打包" }, { value: "packed", label: "已打包待发" }, { value: "all", label: "全部状态" }]}
      onChange={(status) => onChange({ ...filters, status })} />
    <CommittedSearch key={filters.search} className="domestic-board__search"
      typeAriaLabel="打包单搜索类型" typeValue="all" typeOptions={[{ value: "all", label: "SKU / 单号" }]}
      inputAriaLabel="搜索仓库打包单" inputValue={filters.search}
      inputPlaceholder="SKU / 入库单 / 采购单 / 打包单 / ItemID"
      searchAriaLabel="搜索打包单"
      onCommit={({ keyword }) => onChange({ ...filters, search: keyword })} />
    <label className="domestic-packing__approved-range">
      <Typography.Text type="secondary">审批日期</Typography.Text>
      <DatePicker.RangePicker aria-label="打包单审批日期" locale={zhCN} format="YYYY-MM-DD"
        allowEmpty={[true, true]} placeholder={["审批开始日期", "审批结束日期"]}
        value={[filters.approvedFrom ? dayjs(filters.approvedFrom) : null, filters.approvedTo ? dayjs(filters.approvedTo) : null]}
        onChange={(_, dates) => onChange({ ...filters, approvedFrom: dates[0] || undefined, approvedTo: dates[1] || undefined })} />
    </label>
    <ResetButton aria-label="重置打包单筛选" onClick={onReset} />
  </div>;
}
