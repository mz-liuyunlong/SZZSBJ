/** Structure-only warehouse tab: caches UI settings without storing orders or simulating writes. */
import { Alert, Card } from "antd";
import { usePageStateCache } from "@/shared/page-state/pageStateCache";
import PackingWarehouseTable from "./PackingWarehouseTable";
import PackingWarehouseToolbar from "./PackingWarehouseToolbar";
import { initialPackingWarehouseFilters, type PackingWarehouseFilters } from "./packingWarehouseTypes";
import "./PackingWarehousePanel.css";

export default function PackingWarehousePanel({ preferenceScope }: { preferenceScope: string }) {
  const scope = `domestic-packing:${preferenceScope}`;
  const [filters, setFilters] = usePageStateCache<PackingWarehouseFilters>(`${scope}:filters`, initialPackingWarehouseFilters);
  const [pagination, setPagination] = usePageStateCache(`${scope}:pagination`, { page: 1, pageSize: 50 });
  const [widths, setWidths] = usePageStateCache<Record<string, number>>(`${scope}:widths`, {});
  const commitFilters = (next: PackingWarehouseFilters) => { setFilters(next); setPagination({ ...pagination, page: 1 }); };
  return <section className="domestic-packing" aria-label="打包单（仓库）内容">
    <Card size="small" className="domestic-board__toolbar-card">
      <PackingWarehouseToolbar filters={filters} onChange={commitFilters}
        onReset={() => commitFilters(initialPackingWarehouseFilters())} />
    </Card>
    <Alert className="domestic-packing__notice" type="info" showIcon
      message="打包单服务待接入"
      description="当前仅提供页面结构，筛选和分页仅保留界面设置。暂无真实单据，不支持装箱保存、完成确认或标签 PDF。到仓日期将使用收货单实际收货日期。" />
    <div className="domestic-board__table-wrap">
      <PackingWarehouseTable pagination={pagination} widths={widths} sort={filters.sort}
        onPagination={(page, pageSize) => setPagination({ page, pageSize })}
        onResize={(key, width) => setWidths({ ...widths, [key]: width })}
        onSort={(sort) => commitFilters({ ...filters, sort })} />
    </div>
  </section>;
}
