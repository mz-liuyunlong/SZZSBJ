/** 总看板 stat cards (ManagementStatCards; active card = quick filter). Counts are whole-board KPIs. */
import ManagementStatCards, { type ManagementStatCardItem } from "@/components/report-table/ManagementStatCards";
import { fmt } from "@/pages/pmc/overview/overviewDisplay";
import type { OverviewCategory, OverviewFilters, OverviewKpi } from "@/pages/pmc/overview/overviewTypes";

export type CardKey = "all" | OverviewCategory;

const mark = (text: string) => <span className="management-stat-card__mark">{text}</span>;

function buildCards(k: OverviewKpi | undefined, p: Record<string, number>): ManagementStatCardItem<CardKey>[] {
  const v = (pick: (x: OverviewKpi) => number) => (k ? pick(k) : "—");
  const card = (
    key: CardKey, title: string, value: number | string, subtitle: string, icon: string,
    tone: ManagementStatCardItem["tone"],
  ): ManagementStatCardItem<CardKey> => ({ key, title, value, subtitle, tone, icon: mark(icon), layout: "leading" });
  return [
    card("all", "ItemID 总数", v((x) => x.items), k ? `正常 ${fmt(k.normal)} · 草稿 ${fmt(k.drafts)}${k.listing_bad ? ` · Listing 异常 ${fmt(k.listing_bad)}` : ""}` : "", "品", "normal"),
    card("已断货", "已断货", v((x) => x.oos), `日销 > 0 且 WFS 可售 < ${p.instockMin ?? 5}`, "断", "danger"),
    card("断货风险", "断货风险", v((x) => x.risk), "卖完前下一批到不了", "!", "danger"),
    card("供应链异常", "供应链异常", v((x) => x.supply_chain), "超期未上架 / 查验 / 采购超期 / 缺箱规", "链", "warning"),
    card("执行异常", "执行异常", v((x) => x.execution), `国内仓 > ${p.domesticDays ?? 7} 天 / 审批·下单超时`, "执", "warning"),
    card("海外仓可补", "海外仓可补", v((x) => x.overseas), "先补海外仓，再看差额", "海", "normal"),
    card("库存过剩", "库存过剩", v((x) => x.over1), `覆盖 ${p.over1 ?? 120}–${p.over2 ?? 150} 天`, "剩", "normal"),
    card("严重过剩", "严重过剩", v((x) => x.over2), `覆盖 > ${p.over2 ?? 150} 天`, "重", "warning"),
    card("滞销", "滞销", v((x) => x.stale), `有货 ≥ ${p.salesMinDays ?? 14} 天销量 0`, "滞", "normal"),
    card("近 90 天无库存", "近 90 天无库存", v((x) => x.no_stock_90), k ? `有库存不足 30 天 ${fmt(k.low_days)}` : "", "无", "normal"),
    card("超期未上架", "超期未上架", v((x) => x.overdue), "已过预计可售日", "期", "warning"),
    card("缺默认箱规", "缺默认箱规", v((x) => x.box_missing), "已发过货仍无箱规", "箱", "warning"),
  ];
}

const activeCardOf = (f: OverviewFilters): CardKey | "" => {
  if (!f.cats.length && !f.onlyIssue) return "all";
  return f.cats.length === 1 ? f.cats[0] : "";
};


interface OverviewSummaryCardsProps {
  kpi?: OverviewKpi;
  params: Record<string, number>;
  filters: OverviewFilters;
  onCardClick: (key: CardKey) => void;
}

function OverviewSummaryCards({ kpi, params, filters, onCardClick }: OverviewSummaryCardsProps) {
  return (
    <ManagementStatCards<CardKey | "">
      ariaLabel="总看板统计"
      className="pmc-overview__cards"
      cards={buildCards(kpi, params)}
      activeKey={activeCardOf(filters)}
      onCardClick={(key) => key && onCardClick(key)}
    />
  );
}

export default OverviewSummaryCards;
