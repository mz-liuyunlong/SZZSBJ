/** No averages, stock or outbound figures are inferred from a single page of receipts. */
import ManagementStatCards, { type ManagementStatCardItem } from "@/components/report-table/ManagementStatCards";
import type { DomesticSummary, MappingStatus } from "../domesticWarehouseTypes";

interface Props { summary?: DomesticSummary; active?: MappingStatus; onUnresolved: () => void }
export default function DomesticSummaryCards({ summary, active, onUnresolved }: Props) {
  const unavailable = (key: string, title: string, mark: string, unit: string): ManagementStatCardItem => ({
    key, title, value: "—", subtitle: "数据待接入", icon: <span className="management-stat-card__mark">{mark}</span>,
    tone: "normal", layout: "leading", unit,
  });
  const cards: ManagementStatCardItem[] = [
    { key: "receipts", title: "收货批次", value: summary?.receipt_batch_count ?? "—",
      subtitle: summary ? `实收 ${summary.received_qty.toLocaleString()} 件 · ${summary.warehouse_count} 个仓库` : "按收货单明细统计，非库存余额",
      tone: "normal", unit: "条", layout: "leading", icon: <span className="management-stat-card__mark">收</span> },
    unavailable("average", "平均在仓天数", "平", "天"),
    unavailable("todo", "待打包", "待", "张"),
    unavailable("packed", "已打包待发", "包", "张"),
    { ...unavailable("overdue", "超时未发", "超", "张"), tone: "danger" },
    unavailable("shipped", "近 7 天发出", "近", "件"),
    unavailable("cycle", "平均出仓周期", "平", "天"),
    { key: "unresolved", title: "库存批次待关联", value: summary?.unresolved_batch_count ?? "—",
      subtitle: summary ? `已关联 ${summary.matched_batch_count} 条 · 收货日期缺失 ${summary.missing_arrival_date_count} 条` : "待核对收货与库存的对应关系",
      tone: "warning", unit: "条", layout: "leading", icon: <span className="management-stat-card__mark">!</span> },
  ];
  return <ManagementStatCards ariaLabel="国内仓统计" className="domestic-board__summary" cards={cards}
    activeKey={active === "unresolved" ? "unresolved" : ""}
    onCardClick={(key) => { if (key === "unresolved") onUnresolved(); }} />;
}
