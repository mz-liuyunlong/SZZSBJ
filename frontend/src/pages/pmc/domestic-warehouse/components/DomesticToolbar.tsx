/** Screenshot-aligned filters reuse committed search; unsupported business conditions never look applied. */
import { DownloadOutlined, FilterOutlined, SettingOutlined } from "@ant-design/icons";
import { Badge, Button, DatePicker, Select, Space, Tooltip, message } from "antd";
import zhCN from "antd/es/date-picker/locale/zh_CN";
import dayjs from "dayjs";
import CommittedSearch from "@/components/report-table/CommittedSearch";
import ResetButton from "@/components/report-table/ResetButton";
import ReportFacetSelect from "@/shared/report-filters";
import {
  domesticBusinessStatusOptions, domesticSearchOptions,
  type DomesticBusinessStatus, type DomesticFilters, type DomesticSearchType, type DomesticFilterOptions,
} from "../domesticWarehouseTypes";

interface Props {
  options: DomesticFilterOptions; optionsLoading: boolean;
  filters: DomesticFilters; onChange: (next: DomesticFilters) => void; onReset: () => void;
  onMore: () => void; onColumns: () => void; showStats: boolean; onToggleStats: () => void;
}
const placeholders: Partial<Record<DomesticSearchType, string>> = {
  sku: "请输入 SKU", inbound: "请输入入库单号", purchase: "请输入采购单号",
  receipt: "请输入收货单号", all: "请输入 SKU 或单号",
};
export default function DomesticToolbar({ filters, options, optionsLoading, onChange, onReset, onMore, onColumns, showStats, onToggleStats }: Props) {
  const [messageApi, context] = message.useMessage();
  const searchType = filters.searchType ?? "sku";
  return (
    <div className="domestic-board__toolbar domestic-board__toolbar--batch" role="search" aria-label="国内仓看板筛选">
      {context}
      <div className="domestic-board__filter-row">
        <ReportFacetSelect mode="multiple" ariaLabel="店铺" placeholder={optionsLoading ? "店铺加载中" : "店铺"}
          triggerWidth={150} unit="个店铺" value={filters.storeIds} options={options.stores}
          onChange={(value) => onChange({ ...filters, storeIds: (value as string[] | undefined) ?? [] })} />
        <ReportFacetSelect mode="multiple" ariaLabel="负责人" placeholder={optionsLoading ? "负责人加载中" : "负责人"}
          triggerWidth={150} unit="人" value={filters.ownerUids ?? []} options={options.owners}
          onChange={(value) => onChange({ ...filters, ownerUids: (value as string[] | undefined) ?? [] })} />
        <Select<DomesticBusinessStatus> aria-label="状态" placeholder="状态" allowClear
          className="domestic-board__facet" value={filters.businessStatus}
          popupMatchSelectWidth={230}
          options={domesticBusinessStatusOptions}
          onChange={(businessStatus) => onChange({ ...filters, businessStatus })} />
        <CommittedSearch key={`${searchType}:${filters.search}:${filters.batchValues?.join("|") ?? ""}`}
          className="domestic-board__search" typeAriaLabel="搜索类型"
          typeValue={searchType} typeOptions={domesticSearchOptions} inputAriaLabel="搜索国内仓批次"
          inputPlaceholder={filters.batchValues?.length ? `已提交 ${filters.batchValues.length} 项批量搜索` : placeholders[searchType] ?? "请输入搜索内容"}
          inputValue={filters.search} searchButtonText="搜索" batchPlacement="before-search"
          batch={{
            ariaLabel: "批量搜索国内仓批次", placeholder: "一行一个，最多 50 项",
            isSupported: (field) => ["sku", "purchase", "receipt"].includes(field),
            unsupportedMessage: "当前类型暂不支持批量查询；可选 SKU、采购单号或收货单号",
            onMessage: (content) => { void messageApi.info(content); },
            onCommit: (values, field) => {
              const batchValues = [...new Set(values)];
              if (batchValues.length > 50) { void messageApi.warning("批量搜索最多支持 50 项"); return; }
              onChange({ ...filters, searchType: field as DomesticSearchType, search: "", batchValues });
            },
          }}
          onCommit={({ searchField, keyword }) => onChange({
            ...filters, searchType: searchField as DomesticSearchType, search: keyword, batchValues: undefined,
          })} />
        <DatePicker.RangePicker aria-label="到仓日期（收货单日期）" locale={zhCN}
          className="domestic-board__date-range" placeholder={["年/月/日", "年/月/日"]}
          allowEmpty={[true, true]} format="YYYY-MM-DD" separator="—"
          value={[filters.receivedFrom ? dayjs(filters.receivedFrom) : null, filters.receivedTo ? dayjs(filters.receivedTo) : null]}
          onChange={(_, dates) => onChange({ ...filters, receivedFrom: dates[0] || undefined, receivedTo: dates[1] || undefined })} />
        <Badge count={filters.warehouseIds.length + (filters.mappingStatus ? 1 : 0)}>
          <Button icon={<FilterOutlined aria-hidden="true" />} onClick={onMore}>更多筛选</Button>
        </Badge>
      </div>
      <div className="domestic-board__filter-actions">
        <ResetButton onClick={onReset} />
        <Button onClick={onToggleStats}>{showStats ? "隐藏统计" : "显示统计"}</Button>
        <Space className="domestic-board__toolbar-actions">
          <Button aria-label="列配置" icon={<SettingOutlined aria-hidden="true" />} onClick={onColumns} />
          <Tooltip title="导出服务与导出权限尚未接入">
            <span><Button aria-label="导出国内仓批次" icon={<DownloadOutlined aria-hidden="true" />} disabled /></span>
          </Tooltip>
        </Space>
      </div>
    </div>
  );
}
