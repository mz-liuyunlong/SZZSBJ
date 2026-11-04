/** Labels and formatters shared by the overview page and its Excel (display only, no business math). */
import type { OverviewItemRow } from "@/pages/pmc/overview/overviewTypes";

export const CAT_COLOR: Record<string, string> = {
  "Listing 异常": "magenta",
  已断货: "red",
  断货风险: "red",
  供应链异常: "volcano",
  执行异常: "orange",
  严重过剩: "purple",
  库存过剩: "gold",
  滞销: "default",
  "近 90 天无库存": "default",
  海外仓可补: "blue",
  超期未上架: "volcano",
  缺默认箱规: "volcano",
};

export const KIND: Record<string, string> = {
  wfs: "WFS 可售",
  receiving: "已到·收货中",
  shipped: "已发货未可售",
  domestic: "国内仓",
  po: "采购单待到货",
  po_pending: "采购单待下单",
  plan: "采购计划",
};

/** Rule parameter labels, in 8088 「规则设置」 order (group rows have one element). */
export const PARAM_DOC: readonly (readonly [string] | readonly [string, string, string])[] = [
  ["补货公式（与采购计划草稿共用）"],
  ["minQty", "最低草稿量（件）", "国内采购量低于该值不出采购计划草稿"],
  ["approve", "审批到下单（天）", "提前期第 1 段"],
  ["pack", "打包发货（天）", "提前期第 3 段"],
  ["transport", "运输（天）", "提前期第 4 段，统一 LAX2T 美西"],
  ["shelf", "上架缓冲（天）", "提前期第 5 段：签收到首次上架；也是货件预计可售日 = 到仓 + 缓冲"],
  ["cycle", "补货周期（天）", "公式里的补货周期"],
  ["safety", "安全天数（天）", "默认 0 = 保守补货"],
  ["leadFallback", "采购交期兜底（天）", "采购单无 2 个有效样本且领星产品也没填时用"],
  ["总看板判断"],
  ["minSupplyIssue", "库存问题最低件数（件）", "全链路有效供应低于该值的 ItemID 不提示库存类问题（过剩 / 滞销 / 超期未上架 / 查验 / 无轨迹 / 国内仓超期 / 无库存）；断货、采购单据超时、缺箱规仍提示"],
  ["over1", "库存过剩（天）", "覆盖天数 > 该值为库存过剩"],
  ["over2", "严重过剩（天）", "覆盖天数 > 该值为严重过剩"],
  ["salesMinDays", "过剩 / 滞销判断最少有库存天数", "有库存天数低于该值只标天数，不判过剩 / 滞销"],
  ["capDays", "单次封顶：有货日不足（天）", "有货日不足该天数的 ItemID 单次补货封顶（Rocky 2026-09-28）"],
  ["capQty", "单次封顶量（件）", "有货日不足上面天数时建议量最多这么多，不允许单次超出"],
  ["instockMin", "有货日最低库存（件）", "当天期初 WFS 可售低于该值不算有货日（销量也不计）；WFS 可售低于该值视同断货（Rocky 2026-09-30）"],
  ["domesticDays", "国内仓在仓超期（天）", "惠州批次到仓超过该天数为执行异常（可用 + 锁定都算）"],
  ["domesticMinQty", "国内仓超期最低件数（件）", "超期件数合计低于该值不计（尾数等下一批）"],
  ["s1Days", "采购计划待审批超时（天）", "采购看板 S1"],
  ["s2Days", "待采购 / 待下单超时（天）", "采购看板 S2"],
  ["s3Fallback", "已下单未到货兜底交期（天）", "采购看板 S3：无近 5 单实际交期样本时用"],
];

const intFormatter = new Intl.NumberFormat("zh-CN", { maximumFractionDigits: 0 });

export const fmt = (value: number | null | undefined) => (
  value === null || value === undefined ? "—" : intFormatter.format(Math.round(value))
);

export const fmt1 = (value: number | null | undefined) => (
  value === null || value === undefined ? "—" : value.toFixed(1)
);

export const domAvailable = (r: Pick<OverviewItemRow, "seg" | "dom_lock">) => (r.seg.domestic ?? 0) - r.dom_lock;

export const poOutstanding = (r: Pick<OverviewItemRow, "seg">) => (
  (r.seg.po ?? 0) + (r.seg.po_pending ?? 0) + (r.seg.plan ?? 0)
);

export const addDays = (iso: string, days: number) => {
  const d = new Date(`${iso}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() + days);
  return d.toISOString().slice(0, 10);
};

/** 覆盖天数 cell text when there is no number (8088 TabMain / ItemDrawer). */
export const coverFallback = (r: OverviewItemRow, salesMinDays: number) => (
  r.no_stock_90 ? "无库存" : r.n30 < salesMinDays ? `有货 ${r.n30} 天` : r.stale ? "滞销" : "—"
);
