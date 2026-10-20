/** Filters send only fields supported by the inbound contract. */
import { FilterOutlined, SettingOutlined } from "@ant-design/icons";
import { Badge, Button, DatePicker, Select, Space, Tooltip, message } from "antd";
import zhCN from "antd/es/date-picker/locale/zh_CN";
import dayjs from "dayjs";
import CommittedSearch from "@/components/report-table/CommittedSearch";
import ResetButton from "@/components/report-table/ResetButton";
import ReportFacetSelect from "@/shared/report-filters/ReportFacetSelect";
import { domesticSearchOptions, type DomesticFilterOptions, type DomesticFilters, type DomesticSearchType } from "../domesticWarehouseTypes";

interface Props {
  filterOptions?: DomesticFilterOptions;
  optionsLoading: boolean;
  filters: DomesticFilters; onChange: (next: DomesticFilters) => void; onReset: () => void;
  onMore: () => void; onColumns: () => void; showStats: boolean; onToggleStats: () => void;
}
export default function DomesticToolbar({ filters, filterOptions, optionsLoading, onChange, onReset, onMore, onColumns, showStats, onToggleStats }: Props) {
  const [messageApi, context] = message.useMessage();
  return <div className="domestic-board__toolbar domestic-board__toolbar--batch" role="search" aria-label="国内仓看板筛选">
    {context}
    <div className="domestic-board__filter-row">
      <ReportFacetSelect
        mode="multiple"
        className="domestic-board__facet report-filter-select"
        ariaLabel="店铺"
        placeholder={optionsLoading ? "店铺加载中…" : "全部店铺"}
        unit="个店铺"
        value={filters.storeIds}
        options={filterOptions?.stores ?? []}
        popupWidth={360}
        onChange={(value) => onChange({ ...filters, storeIds: (value as string[]) ?? [] })}
      />
      <ReportFacetSelect mode="multiple" ariaLabel="负责人" className="domestic-board__facet report-filter-select"
        placeholder={optionsLoading ? "负责人加载中…" : "全部负责人"} unit="位负责人"
        value={filters.ownerUids} options={filterOptions?.owners ?? []} popupWidth={360}
        onChange={(value) => onChange({ ...filters, ownerUids: (value as string[]) ?? [] })} />
      <Tooltip title="业务状态需要打包与出库关联数据；当前六种状态尚未接入">
        <Select aria-label="业务状态" placeholder="状态（待接入）" className="domestic-board__facet"
          popupMatchSelectWidth={false} options={(filterOptions?.statuses ?? []).map((option) => ({ ...option, title: option.reason }))} />
      </Tooltip>
      <CommittedSearch key={`${filters.searchType}:${filters.search}:${filters.batchValues?.join("|") ?? ""}`}
        className="domestic-board__search" typeAriaLabel="搜索类型" typeValue={filters.searchType}
        typeOptions={domesticSearchOptions} inputAriaLabel="搜索国内仓批次"
        inputPlaceholder={filters.batchValues?.length ? `已提交 ${filters.batchValues.length} 项` : "输入 SKU 或单号"}
        inputValue={filters.search} searchButtonText="搜索" batchPlacement="before-search"
        batch={{ ariaLabel: "批量搜索国内仓批次", placeholder: "一行一个，最多 50 项",
          isSupported: (field) => ["sku", "purchase", "inbound"].includes(field),
          unsupportedMessage: "批量搜索支持 SKU、采购单号和入库单号",
          onMessage: (text) => { void messageApi.info(text); },
          onCommit: (values, field) => onChange({ ...filters, searchType: field as DomesticSearchType, search: "", batchValues: [...new Set(values)] }),
        }} onCommit={({ searchField, keyword }) => onChange({ ...filters, searchType: searchField as DomesticSearchType, search: keyword, batchValues: undefined })} />
      <DatePicker.RangePicker aria-label="到仓日期（入库日期）" locale={zhCN} className="domestic-board__date-range"
        placeholder={["入库开始日期", "入库结束日期"]} allowEmpty={[true, true]} format="YYYY-MM-DD"
        value={[filters.inboundFrom ? dayjs(filters.inboundFrom) : null, filters.inboundTo ? dayjs(filters.inboundTo) : null]}
        onChange={(_, dates) => onChange({ ...filters, inboundFrom: dates[0] || undefined, inboundTo: dates[1] || undefined })} />
      <Badge count={filters.warehouseIds.length + (filters.inventoryStatus ? 1 : 0)}><Button icon={<FilterOutlined />} onClick={onMore}>更多筛选</Button></Badge>
    </div>
    <div className="domestic-board__filter-actions">
      <ResetButton onClick={onReset} /><Button onClick={onToggleStats}>{showStats ? "隐藏统计" : "显示统计"}</Button>
      <Space className="domestic-board__toolbar-actions"><Button aria-label="列配置" icon={<SettingOutlined />} onClick={onColumns} /></Space>
    </div>
  </div>;
}
