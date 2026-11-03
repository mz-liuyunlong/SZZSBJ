/**
 * Excel for the overview board, ported from 8088 `buildWorkbook` (5 sheets).
 *
 * The Walmart column group of 8088 is not included: its data comes from Walmart reports that
 * 5173 does not read yet (red line: Walmart calls need Rocky's written approval).
 */
import * as XLSX from "xlsx";
import { domAvailable, KIND } from "@/pages/pmc/overview/overviewDisplay";
import type { OverviewExportData } from "@/pages/pmc/overview/overviewTypes";

type Cell = string | number | null;

const sheet = (title: string, note: string, heads: string[], data: Cell[][]) => {
  const ws = XLSX.utils.aoa_to_sheet([[title], [note], [], heads, ...data]);
  ws["!cols"] = heads.map((h) => ({ wch: Math.min(40, Math.max(10, String(h).length * 2)) }));
  return ws;
};

const STORE_HEADS = ["店铺", "SKU 行数", "① 采购待到货", "待下单（未计入）", "② 国内仓可用", "② 国内仓锁定", "③ 海外仓", "④ 已建货件未发货", "⑤ 未可售合计", "其中已过可售日未上架", "⑥ 已到·收货中", "⑦ Walmart available", "Walmart onhand", "领星 WFS 可售"];
const STORE_KEYS = ["skus", "po_outstanding", "po_to_order", "domestic_valid", "domestic_lock", "overseas_valid", "created_not_shipped", "transit_total", "transit_已过预计可售日未上架", "receiving", "wm_available", "wm_onhand", "wfs_available"];

const ITEM_HEADS = ["ItemID", "SKU", "MSKU", "品名", "店铺", "负责人", "主要问题", "全部提示", "采购未到国内仓", "国内仓可用", "国内仓锁定", "已发货未可售", "已到·收货中", "WFS 可售", "全链路有效供应（互斥）", "日销", "有库存天数（近 90 天内最多取 30）", "断货天数", "现有可售能卖到", "下一批预计可售", "预计断货天数", "库存覆盖天数", "过剩判断", "补货状态", "草稿号", "系统建议量", "扣海外仓", "国内采购量（箱规取整）", "海外仓同 SKU 件数（不计入）", "国内仓超 7 天件数", "国内仓最长在仓天数", "默认箱规"];

const num = (value: unknown) => (typeof value === "number" ? value : Number(value) || 0);

export function buildOverviewWorkbook(data: OverviewExportData, scopeLabel: string) {
  const day = data.data_date;
  const p = data.params;
  const salesMinDays = p.salesMinDays ?? 14;
  const wb = XLSX.utils.book_new();

  const storeRows: Cell[][] = data.store_summary.map((s) => [String(s.store ?? ""), ...STORE_KEYS.map((k) => num(s[k]))]);
  storeRows.push(["合计", ...STORE_KEYS.map((k) => data.store_summary.reduce((acc, s) => acc + num(s[k]), 0))]);
  XLSX.utils.book_append_sheet(wb, sheet(`PMC 总看板 · 汇总 · 数据日 ${day}`, "口径同运营数据表：各段为同一时点快照，段与段可能重叠（例如已建货件未发货的实物仍在国内仓锁定里），不要跨段相加。", STORE_HEADS, storeRows), "汇总");

  const itemRows: Cell[][] = data.items.map((r) => [
    r.item_id, r.sku, r.msku, r.name, r.stores.map((s) => s.name).join(" | "), r.owner, r.main,
    r.issues.map((i) => `${i.label}：${i.detail}`).join("；"),
    r.seg.po ?? 0, domAvailable(r), r.dom_lock, r.seg.shipped ?? 0, r.seg.receiving ?? 0, r.wm_available, r.supply,
    r.daily, r.n30, r.oos_days === null ? "90+" : r.oos_days, r.sellout ?? "", r.next_date ?? "",
    r.gap_days === null ? (r.sellout ? "无来货" : "") : r.gap_days,
    r.cover ?? "",
    r.over ?? (r.no_stock_90 ? "近 90 天无库存" : r.stale ? "滞销" : r.n30 < salesMinDays ? `有货 ${r.n30} 天不判` : ""),
    r.draft_text, r.draft_id, r.suggest, r.overseas_alloc, r.is_draft ? (r.boxed ?? r.purchase) : "",
    r.overseas_total, r.dom_over_qty, r.dom_max ?? "", r.box || "",
  ]);
  XLSX.utils.book_append_sheet(wb, sheet(`ItemID 总看板明细（${scopeLabel}）· 数据日 ${day}`, "一个 ItemID 一行，多店铺合并。各段为互斥口径（每件货只属一个状态），全链路有效供应 = 各段之和；不含海外仓。", ITEM_HEADS, itemRows), "ItemID总看板明细");

  XLSX.utils.book_append_sheet(wb, sheet(`店铺 × SKU 明细 · 数据日 ${day}`, "口径 = 运营数据表（agg_pmc_ops v4）：分段可重叠，不要跨段相加；库存 / 采购按 ItemID 分摊。", data.ops_heads, data.ops_rows), "店铺×SKU明细");

  const whHeads = ["仓库", "分类", "可用", "锁定", "在库合计", "调拨在途", "有库存 SKU 数", "在仓天数（加权平均）", "在仓天数（最长）"];
  const whRows: Cell[][] = data.warehouses.map((w) => [w.name, w.warehouse_class, w.valid, w.lock, w.total, w.onway, w.skus, w.age_avg ?? "", w.age_max ?? ""]);
  XLSX.utils.book_append_sheet(wb, sheet(`仓库分布 · 数据日 ${day}`, "来源：领星仓库库存明细（全量）。在仓天数 = 数据日 − 批次入库日，按件数加权。", whHeads, whRows), "仓库分布");

  const doc: Cell[][] = [
    ["PMC 总看板 · 口径与说明"], [],
    ["数据日", day],
    ["数据来源", data.source_note],
    ["主表粒度", "一个 ItemID 一行；同一 ItemID 多店铺在售时合并销量 / 库存 / 供应"],
    ["全链路有效供应", "WFS 可售 + 已到·收货中 + 已发货未可售 + 国内仓（可用 + 锁定）+ 采购单待到货 / 待下单 + 采购计划待采购 / 待审批；互斥，不含海外仓"],
    ["提前期", `审批到下单 ${p.approve} + 采购交期（近 5 单实际 → 领星产品 → 兜底 ${p.leadFallback}）+ 打包发货 ${p.pack} + 运输 ${p.transport} + 上架 ${p.shelf}`],
    ["已断货", "日销 > 0 且 WFS 可售 = 0"],
    ["断货风险", "有断货窗口（断 N 天后才有来货），或无来货且提前期内就卖完"],
    ["库存覆盖天数", "全链路有效供应 ÷ 日销（不含海外仓）"],
    ["库存过剩", `> ${p.over1} 天且 ≤ ${p.over2} 天`],
    ["严重过剩", `> ${p.over2} 天`],
    ["滞销", `有库存天数 ≥ ${salesMinDays} 天、销量 0、仍有库存`],
    ["供应链异常", "已过预计可售日未上架 / 超期无物流轨迹（海外仓发出的货件不套）/ 被查验 / 采购已下单未到货超期 / 缺默认箱规"],
    ["执行异常", `采购计划待审批 > ${p.s1Days} 天 / 待采购、待下单 > ${p.s2Days} 天 / 国内仓到仓 > ${p.domesticDays} 天（合计 < ${p.domesticMinQty} 件不计）`],
    ["海外仓", "不计入全流程库存，单独按 SKU 统计、不分摊；需要补货且同 SKU 海外仓有货 → 先补海外仓（断货最早的先用）"],
    ["主要问题优先级", "已断货 > 断货风险 > 供应链异常 > 执行异常 > 严重过剩 > 库存过剩 > 滞销"],
    ["当前参数", Object.entries(p).map(([k, v]) => `${k}=${v}`).join("，")],
    ["未归属", `归不到 ItemID 的${Object.values(KIND).slice(1).join(" / ")}件数单独列出，不计入任何 ItemID`],
    ["Walmart 数据列", "5173 暂不显示（需 Walmart 报表接入，按红线另行审批）"],
  ];
  const ws = XLSX.utils.aoa_to_sheet(doc);
  ws["!cols"] = [{ wch: 18 }, { wch: 120 }];
  XLSX.utils.book_append_sheet(wb, ws, "说明");
  return wb;
}

export function overviewWorkbookFilename(day: string, all: boolean) {
  return `PMC总看板_${day.replace(/-/g, "")}_${all ? "全部" : "筛选"}.xlsx`;
}

export function downloadOverviewWorkbook(data: OverviewExportData, all: boolean) {
  const wb = buildOverviewWorkbook(data, all ? "全部" : "当前筛选");
  XLSX.writeFile(wb, overviewWorkbookFilename(data.data_date, all));
}
