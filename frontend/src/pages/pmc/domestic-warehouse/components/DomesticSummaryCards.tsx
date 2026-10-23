import ManagementStatCards, { type ManagementStatCardItem } from "@/components/report-table/ManagementStatCards";
import type { DomesticSummary, InventoryStatus } from "../domesticWarehouseTypes";

export default function DomesticSummaryCards({ summary, active, onUnknown }: { summary?: DomesticSummary; active?: InventoryStatus; onUnknown: () => void }) {
  const values = [
    ["orders", "入库单数", summary?.inbound_order_count, "按账号、仓库和入库单去重", "单"],
    ["rows", "展示行数", summary?.board_row_count, "入库单 × SKU × 店铺", "行"],
    ["sku", "SKU 数", summary?.sku_count, "当前筛选范围去重", "个"],
    ["quantity", "已知入库总量", summary?.total_inbound_qty, "IB×SKU 去重，非店铺分摊量", "件"],
    ["balance", "已知批次余额", summary?.balance_qty, "仅累加已知值，零不等于已发货", "件"],
    ["unknown", "余额未知行", summary?.unknown_inventory_row_count, "点击筛选 / 再次点击取消", "行"],
    ["unknownQty", "入库量未知", summary?.unknown_inbound_qty_count, "缺少完整入库数量证据的 IB×SKU", "组"],
    ["dates", "到仓日期未知", summary?.missing_arrival_date_count, "缺少日期或源时区尚未核实", "行"],
  ] as const;
  const cards: ManagementStatCardItem[] = values.map(([key, title, value, subtitle, unit]) => ({
    key, title, value: value ?? "—", subtitle, unit, tone: key === "unknown" ? "warning" : "normal",
    layout: "leading", icon: <span className="management-stat-card__mark">{title[0]}</span>,
  }));
  return <ManagementStatCards ariaLabel="国内仓统计" className="domestic-board__summary" cards={cards}
    activeKey={active === "unknown" ? "unknown" : ""} onCardClick={(key) => { if (key === "unknown") onUnknown(); }} />;
}
