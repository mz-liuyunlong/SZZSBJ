/**
 * AiFinanceItemCashProfitV2.tsx — AI财务 · 单品现金利润 v2（按「店铺 + ITEMID」）批13 第一批
 * 接口：GET /api/finance/item-cash-profit-v2（新接口，旧接口与旧页面一行不改）
 * UI_STANDARDS：§1 工具条(图标序 KPI→刷新→帮助→下载) §5 列宽拖动 §7 表头ⓘ
 *   §8 表头吸顶+总计吸底+翻页 §9 独立 hash 路由 #/finance/item-cash-profit-v2
 *
 * 与 v1 的差异只有聚合键：v1 = 店铺+本地SKU；v2 = 店铺+ITEMID。
 *   ITEMID 升为主键列（紧跟店铺），SKU 与 MSKU 降为展示列、支持多值。
 *   记账口径（切点/期初FIFO/一刀切/虚拟SKU豁免/汇率取上月我的汇率）与 v1 完全一致，未改算法。
 *
 * scope：clean（默认）只出「1店1item」可直归 item，采购份额恒 100%、零分摊争议；
 *        被排除的 item 汇总在 excluded 桶，总量不失真。all = 全部 item（第二批接分摊逻辑后再用）。
 * family：yc200 = 本地SKU 为 YC00200 及之后（需求方口径：基本都是新品）；all = 不限。
 */
import { useEffect, useMemo, useRef, useState } from "react";
import { lxTB, IconRefresh, IconHelp, IconDownload, IconColumns } from "./LxToolbar";
import { ItemIdLink } from "./ItemIdLink";

interface Cell { c: number; u: number }
interface Row {
  store_id: string; store_name: string; item_id: string;
  skus: string[]; mskus: string[];
  sale: Cell; refund: Cell; comp: Cell; wfs_fee: Cell; other_item: Cell;
  ads: Cell; storage: Cell; inbound: Cell; purchase: Cell; firstmile: Cell; opening_cost: Cell;
  sold_qty: number; opening_used_qty: number;
  revenue: Cell; expense: Cell; profit: Cell; is_clean: boolean;
}
interface StoreRow { store_id: string; store_name: string; sem: Cell; review: Cell; comp: Cell; other: Cell; ads_unmapped: Cell; purchase_unmapped: Cell; unmapped_cnt: number }
interface Sentinel { name: string; expect: number; actual: number; diff: number; ok: boolean; note: string }
interface Resp {
  from: string; to: string; cutoff: string; scope: string; family: string;
  kpi: { opening_value: number; pool_remain_qty: number; pool_remain_value: number; huizhou_value: number; huizhou_qty: number; profit_cny: number; profit_usd: number; row_cnt: number; clean_cnt: number };
  rows: Row[]; store_rows: StoreRow[];
  excluded: { rows: number; revenue: Cell; expense: Cell; profit: Cell };
  sentinels: Sentinel[]; fx_missing: string[]; excluded_note: string; error?: string;
}
interface StoreOpt { store_id: string; store_name: string }

const C = { blue: "#1a73e8", txt2: "#5f6368", txt3: "#9aa0a6", line: "#dadce0", neg: "#d93025", green: "#188038", amber: "#b06f00" };
const card: React.CSSProperties = { background: "#fff", border: "1px solid #e5e7eb", borderRadius: "10px" };
const PAGE_SIZE_OPTIONS = [50, 100, 200];
const MAX_PINNED_COLUMNS = 7;                       // 领星同款上限（context TASK_CHANGE_LOG:1252/1514）
const DEFAULT_PINNED = ["store_name", "item_id"];   // 默认固定列（context TASK_CHANGE_LOG:1274 各页默认固定列）
const pageBtn = (active: boolean, disabled: boolean): React.CSSProperties => ({ padding: "5px 12px", borderRadius: "5px", border: "1px solid #e5e7eb", cursor: disabled ? "not-allowed" : "pointer", background: active ? "#6366f1" : "#fff", color: active ? "#fff" : "#374151", fontWeight: active ? 700 : 400, fontSize: "13px", opacity: disabled ? 0.5 : 1 });

const COLS: { key: string; label: string; w: number; align: "left" | "right"; hideable?: boolean; tip?: string }[] = [
  { key: "store_name", label: "店铺", w: 150, align: "left", tip: "沃尔玛店铺（领星 store_id 已做数字精度就近修复后归一）。本页唯一键为「店铺+ITEMID」，同一 ITEMID 可跨店" },
  { key: "item_id", label: "ITEM_ID", w: 124, align: "left", tip: "沃尔玛 ItemID —— 本页主维度。注意：同一 ITEMID 可跨多个店铺（同一 listing 多店共用），故唯一键为「店铺+ITEMID」，不可单用 ITEMID 反查店铺" },
  { key: "sku", label: "SKU", w: 110, align: "left", tip: "该 (店铺,ITEMID) 对应的本地SKU；一个 ITEMID 可能对应多个本地SKU（如 YC00019 与 YC00019-2），多值时逗号展示" },
  { key: "msku", label: "MSKU", w: 130, align: "left", tip: "该 (店铺,ITEMID) 下的平台变体 MSKU，最多展示12个" },
  { key: "sold_qty", label: "销量", w: 74, align: "right", tip: "区间内结算销量（领星结算月度经 (店,msku)→ITEMID 归位，store_id 已修复精度损坏）" },
  { key: "sale", label: "销售额", w: 100, align: "right", tip: "回款对账单 sale 类目净额，按账期止日归月；直接取 recon.item_id（无需 msku→sku 映射）" },
  { key: "refund", label: "退款", w: 90, align: "right", tip: "refund_keepit / return / seller_initiated 合计（负）" },
  { key: "comp", label: "赔付返还", w: 92, align: "right", tip: "丢失/找回/仓损/WFS费用退款/广告返还/NSS折扣/库存转移 净额±（账单多为店铺级无品，见下方店铺级表）" },
  { key: "revenue", label: "收入合计", w: 100, align: "right", tip: "销售额+退款+赔付返还" },
  { key: "wfs_fee", label: "WFS配送费", w: 96, align: "right", tip: "wfs_fulfillment（账单负号原样）" },
  { key: "ads", label: "广告费", w: 90, align: "right", tip: "SP/SB/SV 商品级实付合计（fact_ads_product_daily.item_id）；SEM 在店铺级行" },
  { key: "storage", label: "仓储费", w: 88, align: "right", tip: "仓储报告导入，item_id 100% 填充，账期起日归月" },
  { key: "inbound", label: "入库运输", w: 90, align: "right", tip: "货件级运费按已发货数分摊，item_id 100% 填充" },
  { key: "purchase", label: "采购现金", w: 96, align: "right", tip: "切点(2026-05-01)后采购单下单日全额；采购为SKU级，按「sid直归/发货单回退/未归属单列」三路归属，店内多item时按实际发货量份额拆" },
  { key: "firstmile", label: "头程现金", w: 96, align: "right", tip: "切点后发货单实付头程按品分摊（matched·非预估·单据非作废）" },
  { key: "opening_cost", label: "期初消耗", w: 96, align: "right", tip: "期初池(05-01 WFS快照)按月FIFO×财务一刀价；YC00200+ 新品 100% 不在期初池，本列应为 0" },
  { key: "other_item", label: "其他按品", w: 92, align: "right", tip: "退货处理/弃置及未单列按品类目净额±（佣金已含在回款销售净额，不重复计）" },
  { key: "expense", label: "支出合计", w: 100, align: "right", tip: "WFS配送+广告+仓储+入库运输+采购+头程+期初消耗+其他按品（取扣费口径）" },
  { key: "profit", label: "现金利润", w: 104, align: "right", tip: "收入合计−支出合计" },
  { key: "opening_used_qty", label: "耗池量", w: 74, align: "right", tip: "本区间从期初池消耗的数量" },
];

export default function AiFinanceItemCashProfitV2({ onNavigate }: { onNavigate?: (key: string) => void }) {
  const [data, setData] = useState<Resp | null>(null);
  const [loading, setLoading] = useState(false);
  const [msg, setMsg] = useState("");
  const [from, setFrom] = useState("2026-05");
  const [to, setTo] = useState(() => new Date().toISOString().slice(0, 7));
  const [storeId, setStoreId] = useState("");
  const [stores, setStores] = useState<StoreOpt[]>([]);
  const [cur, setCur] = useState<"CNY" | "USD">("CNY");
  const [scope, setScope] = useState<"clean" | "all">("clean");
  const [family, setFamily] = useState<"yc200" | "all">("yc200");
  const [pageSize, setPageSize] = useState(50);
  const [page, setPage] = useState(1);
  const [colWidths, setColWidths] = useState<Record<string, number>>({});
  const [kpiHidden, setKpiHidden] = useState(false);
  const [visibleCols, setVisibleCols] = useState<string[]>(COLS.map((c) => c.key));
  const [pinnedCols, setPinnedCols] = useState<string[]>(DEFAULT_PINNED);
  const [showColCfg, setShowColCfg] = useState(false);
  const [cfgSelected, setCfgSelected] = useState<string[]>(COLS.map((c) => c.key)); // 弹窗草稿态，点「应用」才生效
  const [cfgPins, setCfgPins] = useState<string[]>(DEFAULT_PINNED);
  const dragColIdxRef = useRef<number | null>(null);
  // 点单元格 → 行列淡色高亮，再点取消（context TASK_CHANGE_LOG:1075；交互控件内点击不触发）
  const [hlCell, setHlCell] = useState<{ row: number; col: number } | null>(null);
  const resizeRef = useRef<{ col: string; startX: number; startW: number } | null>(null);

  useEffect(() => {
    // 与 AiFinanceCredits.tsx 逐字一致：同 id 同内容，消除"同 id 不同内容、谁先挂载谁生效"的冲突
    if (typeof document !== "undefined" && !document.getElementById("lx-colresize-css")) {
      const st = document.createElement("style");
      st.id = "lx-colresize-css";
      st.textContent =
        ".lx-colresize{position:absolute;top:0;right:-4px;width:9px;height:100%;cursor:col-resize;user-select:none;z-index:3;display:flex;align-items:center;justify-content:center}" +
        ".lx-colresize::after{content:'';width:2px;height:56%;background:#dadce0;border-radius:1px;transition:background .12s,height .12s,width .12s}" +
        ".lx-colresize:hover::after{background:#1a73e8;width:3px;height:100%}";
      document.head.appendChild(st);
    }
    if (typeof document !== "undefined" && !document.getElementById("lxfin-tip-css")) {
      const st = document.createElement("style");
      st.id = "lxfin-tip-css";
      st.textContent =
        ".lxfin-info{position:relative;display:inline-flex;align-items:center;justify-content:center;width:13px;height:13px;margin-left:3px;border:1px solid #9aa0a6;border-radius:50%;font-size:9px;color:#9aa0a6;cursor:help;font-style:normal;vertical-align:1px}" +
        ".lxfin-info .lxfin-tip{display:none;position:absolute;top:20px;left:50%;transform:translateX(-50%);background:#202124;color:#fff;font-size:11px;line-height:1.6;padding:8px 10px;border-radius:6px;width:230px;white-space:normal;z-index:30;text-align:left;font-weight:400}" +
        ".lxfin-info .lxfin-tip::before{content:'';position:absolute;top:-5px;left:50%;transform:translateX(-50%);border:5px solid transparent;border-top:none;border-bottom:5px solid #202124}" +
        ".lxfin-info:hover .lxfin-tip{display:block}";
      document.head.appendChild(st);
    }
  }, []);
  useEffect(() => {
    const mv = (e: MouseEvent): void => {
      const r = resizeRef.current; if (!r) return;
      setColWidths((p) => ({ ...p, [r.col]: Math.max(60, r.startW + e.clientX - r.startX) }));
    };
    const up = (): void => { resizeRef.current = null; document.body.style.cursor = ""; };
    window.addEventListener("mousemove", mv); window.addEventListener("mouseup", up);
    return () => { window.removeEventListener("mousemove", mv); window.removeEventListener("mouseup", up); };
  }, []);

  const load = async (): Promise<void> => {
    setLoading(true);
    try {
      const r = await fetch(`/api/finance/item-cash-profit-v2?from=${from}&to=${to}&store_id=${encodeURIComponent(storeId)}&scope=${scope}&family=${family}`, { credentials: "include" });
      const d = (await r.json()) as Resp;
      if (!r.ok) throw new Error(d.error ?? String(r.status));
      setData(d); setPage(1);
    } catch (e) { setMsg("加载失败：" + (e instanceof Error ? e.message : String(e))); }
    finally { setLoading(false); }
  };
  useEffect(() => {
    void fetch("/api/finance/stores", { credentials: "include" }).then((r) => r.json())
      .then((d: { stores?: StoreOpt[] }) => setStores(d.stores ?? [])).catch(() => undefined);
    void load(); /* eslint-disable-next-line */
  }, []);
  useEffect(() => { if (!msg) return; const t = setTimeout(() => setMsg(""), 4200); return () => clearTimeout(t); }, [msg]);

  const V = (cell: Cell | undefined): number => (cell ? (cur === "CNY" ? cell.c : cell.u) : 0);
  const sym = cur === "CNY" ? "¥" : "$";
  const fmt = (v: number): string => `${v < 0 ? "-" : ""}${sym}${Math.abs(v).toLocaleString("zh-CN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

  const rows = data?.rows ?? [];
  const totalPages = Math.max(1, Math.ceil(rows.length / pageSize));
  useEffect(() => { if (page > totalPages) setPage(totalPages); }, [page, totalPages]);
  const paged = rows.slice((page - 1) * pageSize, page * pageSize);
  const colByKey = useMemo(() => { const m: Record<string, typeof COLS[number]> = {}; for (const c of COLS) m[c.key] = c; return m; }, []);
  // 列顺序 = 固定列归组在前（领星式，样板 FeishuRawSalesData.tsx:1997-2000）
  const orderedKeys = useMemo(() => {
    const vis = visibleCols.filter((k) => colByKey[k]);
    return [...vis.filter((k) => pinnedCols.includes(k)), ...vis.filter((k) => !pinnedCols.includes(k))];
  }, [visibleCols, pinnedCols, colByKey]);
  const cols = orderedKeys.map((k) => colByKey[k]);
  const tableW = cols.reduce((a, c) => a + (colWidths[c.key] ?? c.w), 0);
  const pinnedSet = useMemo(() => new Set(pinnedCols.filter((k) => visibleCols.includes(k))), [pinnedCols, visibleCols]);
  const pinLeftMap = useMemo(() => {
    const m: Record<string, number> = {}; let acc = 0;
    for (const c of cols) if (pinnedSet.has(c.key)) { m[c.key] = acc; acc += colWidths[c.key] ?? c.w; }
    return m; /* eslint-disable-next-line */
  }, [cols, colWidths, pinnedSet]);
  // 逐格内联 sticky（与样板同方案，根治表头/表体错位）
  const pinnedCellStyle = (key: string, isHeader: boolean): React.CSSProperties =>
    pinnedSet.has(key)
      ? { position: "sticky", left: pinLeftMap[key], zIndex: isHeader ? 7 : 2, boxShadow: "2px 0 4px -2px rgba(0,0,0,0.12)" }
      : {};
  const cfgOrdered = cfgSelected.filter((k) => colByKey[k]);
  const openColCfg = (): void => { setCfgSelected(visibleCols); setCfgPins(pinnedCols); setShowColCfg(true); };
  const applyColumnConfig = (): void => {
    setVisibleCols(cfgOrdered);
    setPinnedCols(cfgPins.filter((k) => cfgOrdered.includes(k)));
    setHlCell(null);
    setShowColCfg(false);
  };
  const startResize = (e: React.MouseEvent, key: string, th: HTMLElement): void => {
    e.preventDefault(); e.stopPropagation();
    resizeRef.current = { col: key, startX: e.clientX, startW: th.getBoundingClientRect().width };
    document.body.style.cursor = "col-resize";
  };
  const openHelp = (): void => {
    onNavigate?.("help");
    try { window.location.hash = "#/help?page=finance-item-cash-profit"; } catch { /* noop */ }
  };
  const totals = useMemo(() => {
    const t: Record<string, number> = {};
    for (const c of cols) t[c.key] = 0;
    for (const r of rows) {
      t.sold_qty += r.sold_qty; t.opening_used_qty += r.opening_used_qty;
      (["sale", "refund", "comp", "revenue", "wfs_fee", "ads", "storage", "inbound", "purchase", "firstmile", "opening_cost", "other_item", "expense", "profit"] as const)
        .forEach((k) => { t[k] += V(r[k]); });
    }
    return t; /* eslint-disable-next-line */
  }, [rows, cur]);

  const exportCsv = (): void => {
    const head = cols.map((c) => c.label);
    const dataRows: (string | number)[][] = [head];
    for (const r of rows) {
      dataRows.push(cols.map((c) => {
        if (c.key === "store_name") return r.store_name;
        if (c.key === "item_id") return r.item_id;
        if (c.key === "sku") return (r.skus ?? []).join("|");
        if (c.key === "msku") return (r.mskus ?? []).join("|");
        if (c.key === "sold_qty") return r.sold_qty;
        if (c.key === "opening_used_qty") return r.opening_used_qty;
        return V(r[c.key as keyof Row] as Cell);
      }));
    }
    const csv = "﻿" + dataRows.map((row) => row.map((v) => `"${String(v).replace(/"/g, '""')}"`).join(",")).join("\n");
    const a = document.createElement("a");
    a.href = URL.createObjectURL(new Blob([csv], { type: "text/csv;charset=utf-8" }));
    a.download = `单品现金利润v2_${from}_${to}_${scope}_${cur}.csv`;
    a.click(); URL.revokeObjectURL(a.href);
  };

  const cellStyle = (align: "left" | "right"): React.CSSProperties =>
    ({ textAlign: align, padding: "7px 10px", fontSize: "12px", borderTop: "1px solid #f3f4f6", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis", fontVariantNumeric: "tabular-nums" });
  const money = (v: number, opt?: { bold?: boolean; posGreen?: boolean }): React.ReactNode => (
    <span style={{ color: v < 0 ? C.neg : opt?.posGreen && v > 0 ? C.green : undefined, fontWeight: opt?.bold ? 700 : undefined }}>{fmt(v)}</span>
  );
  const multi = (a: string[]): React.ReactNode => {
    if (!a || !a.length) return <span style={{ color: C.txt3 }}>—</span>;
    return <span style={{ color: C.txt2, fontSize: "11px" }} title={a.join("\n")}>{a.length > 2 ? `${a.slice(0, 2).join(", ")} +${a.length - 2}` : a.join(", ")}</span>;
  };
  const cell = (r: Row, key: string): React.ReactNode => {
    switch (key) {
      case "store_name": return <span style={{ color: C.txt2 }}>{r.store_name}</span>;
      case "item_id": return <b title={r.is_clean ? "可直归（该本地SKU全库只对应此唯一店铺+ITEMID）" : "需分摊（该本地SKU跨多店或多ITEMID）"}><ItemIdLink itemId={r.item_id} />{r.is_clean ? "" : " ⚠"}</b>;
      case "sku": return multi(r.skus ?? []);
      case "msku": return multi(r.mskus ?? []);
      case "sold_qty": return r.sold_qty == null ? <span style={{ color: C.txt3 }}>—</span> : r.sold_qty.toLocaleString("zh-CN");
      case "opening_used_qty": return r.opening_used_qty == null ? <span style={{ color: C.txt3 }}>—</span> : r.opening_used_qty.toLocaleString("zh-CN");
      case "revenue": return money(V(r.revenue), { bold: true });
      case "expense": return money(-Math.abs(V(r.expense)));
      case "profit": return money(V(r.profit), { bold: true, posGreen: true });
      case "ads": case "storage": case "inbound": case "purchase": case "firstmile": case "opening_cost": {
        const c0 = r[key as keyof Row] as Cell | undefined;
        return c0 == null ? <span style={{ color: C.txt3 }}>—</span> : money(-V(c0));
      }
      default: {
        const c0 = r[key as keyof Row] as Cell | undefined;
        return c0 == null ? <span style={{ color: C.txt3 }}>—</span> : money(V(c0));
      }
    }
  };

  const kpi = data?.kpi;
  const kpiCard = (label: string, val: string, sub?: string): React.ReactNode => (
    <div style={{ ...card, padding: "10px 14px", minWidth: "160px" }}>
      <div style={{ fontSize: "11px", color: C.txt3 }}>{label}</div>
      <div style={{ fontSize: "17px", fontWeight: 700, marginTop: "2px" }}>{val}</div>
      {sub && <div style={{ fontSize: "10px", color: C.txt3, marginTop: "2px" }}>{sub}</div>}
    </div>
  );

  return (
    <div>
      <p style={{ color: C.txt2, margin: "0 0 10px", fontSize: "12px", lineHeight: 1.6 }}>
        <b>按「店铺 + ITEM_ID」出数</b>（v2，批13 第一批）。记账口径与原「单品现金利润」页完全一致：切点 <b>2026-05-01</b>；
        切点前采购/头程现金已压缩为期初，老货按期初池 FIFO 消耗计成本；海外仓/Miami 虚拟库存不计。
        默认只出<b>可直归</b> item（该本地SKU 全库只对应唯一「店铺+ITEMID」，采购份额恒 100%、零分摊争议），
        其余 item 汇总在下方「范围外」卡片，总量不失真。
      </p>

      {/* §1 工具条 */}
      <div style={{ ...lxTB.filterWrap, display: "flex", alignItems: "center", gap: "10px", flexWrap: "wrap" }}>
        <span style={{ fontSize: "13px", fontWeight: 700, color: "#374151" }}>💰 单品现金利润 · ITEMID</span>
        <input type="month" min="2026-05" style={{ ...lxTB.filterInput, width: "128px" }} value={from} onChange={(e) => setFrom(e.target.value)} />
        <span style={{ color: C.txt3 }}>~</span>
        <input type="month" min="2026-05" style={{ ...lxTB.filterInput, width: "128px" }} value={to} onChange={(e) => setTo(e.target.value)} />
        <select style={{ ...lxTB.filterSelect, width: "190px" }} value={storeId} onChange={(e) => setStoreId(e.target.value)}>
          <option value="">全部店铺</option>
          {stores.map((s) => <option key={s.store_id} value={s.store_id}>{s.store_name}</option>)}
        </select>
        <select style={{ ...lxTB.filterSelect, width: "132px" }} value={scope} onChange={(e) => setScope(e.target.value as "clean" | "all")} title="clean=只出可直归item（零分摊争议）；all=全部item（含需分摊的）">
          <option value="clean">可直归</option>
          <option value="all">全部item</option>
        </select>
        <select style={{ ...lxTB.filterSelect, width: "150px" }} value={family} onChange={(e) => setFamily(e.target.value as "yc200" | "all")} title="YC00200+ 为需求方口径的新品；其余前缀（JJ/BG/YM/HK）多为老品">
          <option value="yc200">YC00200+ 新品</option>
          <option value="all">全部SKU</option>
        </select>
        <select style={{ ...lxTB.filterSelect, width: "96px" }} value={cur} onChange={(e) => setCur(e.target.value as "CNY" | "USD")} title="展示币种（折算按上月领星「我的汇率」）">
          <option value="CNY">CNY ¥</option>
          <option value="USD">USD $</option>
        </select>
        <button style={lxTB.searchBtn} disabled={loading} onClick={() => void load()}>{loading ? "查询中…" : "查询"}</button>
        <span style={{ color: C.txt2, fontSize: "12px" }}>{data ? `${data.from}~${data.to} · 共 ${rows.length} 行 · 第 ${page}/${totalPages} 页` : ""}</span>
        <div style={{ flex: 1 }} />
        <button style={lxTB.iconBtn} title="隐藏 / 显示 顶部KPI" onClick={() => setKpiHidden(!kpiHidden)}><span style={{ fontSize: "14px", lineHeight: 1 }}>▤</span></button>
        <button style={lxTB.iconBtn} title="刷新" onClick={() => void load()} disabled={loading}><IconRefresh /></button>
        <button style={lxTB.iconBtn} title="帮助（取值口径/切点规则）" onClick={openHelp}><IconHelp /></button>
        <button style={lxTB.iconBtn} title="下载 CSV（当前币种）" onClick={exportCsv}><IconDownload /></button>
        <button style={lxTB.iconBtn} title="列配置（显隐/排序/固定≤7列）" onClick={openColCfg}><IconColumns /></button>
        <button style={lxTB.iconBtn} title="列宽重置（恢复默认列宽）" onClick={() => setColWidths({})}><span style={{ fontSize: "14px", lineHeight: 1 }}>↔</span></button>
      </div>
      <div style={{ fontSize: "11px", color: C.txt3, margin: "-4px 0 10px" }}>
        拖列头右缘调列宽（列宽重置见右侧 ↔）· 点单元格高亮所在行列，再点取消 · 折算=各归属月「上一个月」领星我的汇率 · 列配置内 📌 可固定至多 7 列（表格左侧冻结，默认店铺+ITEM_ID）
        <span style={{ marginLeft: "8px" }}>⚠ 标记 = 该行需分摊（本地SKU 跨多店或多ITEMID）</span>
        {data?.fx_missing?.length ? <span style={{ color: C.neg, marginLeft: "8px" }}>⚠️ 缺汇率月份：{data.fx_missing.join(", ")}</span> : null}
      </div>

      {msg && <div style={{ ...card, padding: "10px 14px", color: C.amber, marginBottom: "10px", border: "1px solid #f9ab00", background: "#fef7e0" }}>{msg}</div>}

      {/* 列配置弹窗（领星式，样板 FeishuRawSalesData.tsx:2272-2345；会话内不持久化） */}
      {showColCfg && (
        <div style={{ position: "fixed", inset: 0, background: "rgba(15,23,42,0.4)", zIndex: 1000, display: "flex", alignItems: "center", justifyContent: "center" }} onClick={() => setShowColCfg(false)}>
          <div style={{ background: "#fff", borderRadius: "12px", width: "680px", maxHeight: "78vh", display: "flex", flexDirection: "column", overflow: "hidden", boxShadow: "0 8px 32px rgba(0,0,0,0.18)" }} onClick={(e) => e.stopPropagation()}>
            <div style={{ padding: "12px 16px", borderBottom: "1px solid #e5e7eb", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <span style={{ fontSize: "14px", fontWeight: 700, color: "#374151" }}>列配置</span>
              <button onClick={() => setShowColCfg(false)} style={{ border: "none", background: "none", fontSize: "18px", cursor: "pointer", color: "#9ca3af" }}>×</button>
            </div>
            <div style={{ display: "flex", flex: 1, overflow: "hidden" }}>
              <div style={{ flex: 1, padding: "10px 14px", overflowY: "auto" }}>
                {COLS.map((col) => (
                  <label key={col.key} style={{ display: "flex", alignItems: "center", gap: "6px", padding: "4px 0", cursor: "pointer", fontSize: "13px" }}>
                    <input type="checkbox" checked={cfgSelected.includes(col.key)}
                      onChange={() => {
                        setCfgSelected((prev) => prev.includes(col.key) ? prev.filter((c) => c !== col.key) : [...prev, col.key]);
                        setCfgPins((prev) => prev.filter((c) => c !== col.key));
                      }} />
                    <span style={{ color: "#374151" }}>{col.label}</span>
                  </label>
                ))}
              </div>
              <div style={{ width: "230px", borderLeft: "1px solid #e5e7eb", padding: "10px 10px", overflowY: "auto", background: "#f8fafc" }}>
                <div style={{ fontSize: "12px", color: "#64748b", marginBottom: "2px" }}>已选 {cfgOrdered.length} 列 · 拖动调顺序</div>
                <div style={{ fontSize: "11px", color: "#94a3b8", marginBottom: "6px" }}>📌最多固定{MAX_PINNED_COLUMNS}项（表格左侧冻结）</div>
                {cfgOrdered.map((key, idx) => {
                  const isPin = cfgPins.includes(key);
                  return (
                    <div key={key} draggable
                      onDragStart={() => { dragColIdxRef.current = idx; }}
                      onDragOver={(e) => e.preventDefault()}
                      onDrop={() => {
                        const from = dragColIdxRef.current; dragColIdxRef.current = null;
                        if (from === null || from === idx) return;
                        const view = [...cfgOrdered];
                        const [moved] = view.splice(from, 1);
                        view.splice(idx, 0, moved);
                        setCfgSelected(view);
                      }}
                      style={{ display: "flex", alignItems: "center", gap: "4px", padding: "4px 2px", fontSize: "12px",
                        borderRadius: "4px", cursor: "grab", background: isPin ? "#eef2ff" : "transparent", borderBottom: "1px solid #f1f5f9" }}>
                      <span style={{ color: "#cbd5e1", fontSize: "13px", lineHeight: 1 }} title="拖动排序">⠿</span>
                      <span style={{ flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                        {isPin && <span style={{ fontSize: "10px" }}>📌</span>}{colByKey[key]?.label ?? key}
                      </span>
                      <span onClick={() => setCfgSelected((prev) => [key, ...prev.filter((c) => c !== key)])} title="置顶"
                        style={{ color: "#64748b", cursor: "pointer", fontSize: "12px" }}>⬆</span>
                      <span onClick={() => setCfgPins((prev) => {
                          if (prev.includes(key)) return prev.filter((c) => c !== key);
                          if (prev.length + 1 > MAX_PINNED_COLUMNS) { setMsg(`最多可固定${MAX_PINNED_COLUMNS}项`); return prev; }
                          return [...prev, key];
                        })} title={isPin ? "取消固定" : "固定（左侧冻结）"}
                        style={{ color: isPin ? "#2563eb" : "#94a3b8", cursor: "pointer", fontSize: "12px" }}>📌</span>
                      <span onClick={() => {
                          setCfgSelected((prev) => prev.filter((c) => c !== key));
                          setCfgPins((prev) => prev.filter((c) => c !== key));
                        }} title="删除" style={{ color: "#ef4444", cursor: "pointer", fontSize: "14px" }}>×</span>
                    </div>
                  );
                })}
              </div>
            </div>
            <div style={{ padding: "10px 16px", borderTop: "1px solid #e5e7eb", display: "flex", gap: "8px", justifyContent: "flex-end" }}>
              <button style={lxTB.resetBtn} onClick={() => { setCfgSelected(COLS.map((c) => c.key)); setCfgPins(DEFAULT_PINNED); }}>重置默认</button>
              <button style={lxTB.resetBtn} onClick={() => setShowColCfg(false)}>取消</button>
              <button style={lxTB.searchBtn} onClick={applyColumnConfig}>应用</button>
            </div>
          </div>
        </div>
      )}

      {!kpiHidden && kpi && (
        <div style={{ display: "flex", gap: "10px", flexWrap: "wrap", marginBottom: "12px" }}>
          {kpiCard("现金利润（区间）", cur === "CNY" ? `¥${kpi.profit_cny.toLocaleString("zh-CN")}` : `$${kpi.profit_usd.toLocaleString("zh-CN")}`)}
          {kpiCard("本次口径行数", `${kpi.row_cnt.toLocaleString("zh-CN")}`, `其中可直归 ${kpi.clean_cnt.toLocaleString("zh-CN")} 行 · scope=${data?.scope} · family=${data?.family}`)}
          {kpiCard("期初存货（05-01）", `¥${kpi.opening_value.toLocaleString("zh-CN")}`, "全量期初池（本页新品应不占用）")}
          {kpiCard("期初池余量", `¥${kpi.pool_remain_value.toLocaleString("zh-CN")}`, `${kpi.pool_remain_qty.toLocaleString("zh-CN")} 件（截至所选止月）`)}
          {kpiCard("惠州仓存货", `¥${kpi.huizhou_value.toLocaleString("zh-CN")}`, `${kpi.huizhou_qty.toLocaleString("zh-CN")} 件 · 批次价 · 国内仓计资产`)}
          <div style={{ ...card, padding: "10px 14px", background: "#fafafa", maxWidth: "460px" }}>
            <div style={{ fontSize: "11px", color: C.txt3 }}>不计入（口径）</div>
            <div style={{ fontSize: "11px", color: C.txt2, marginTop: "4px", lineHeight: 1.6 }}>{data?.excluded_note}</div>
          </div>
        </div>
      )}

      {/* 范围外汇总：保证总量不失真 */}
      {data?.excluded && data.excluded.rows > 0 && (
        <div style={{ ...card, padding: "10px 14px", marginBottom: "10px", background: "#fffdf7", border: "1px solid #f3e8c8" }}>
          <b style={{ fontSize: "12px" }}>📦 范围外 item 汇总（未计入上表，第二批接分摊逻辑后并入）</b>
          <span style={{ fontSize: "12px", color: C.txt2, marginLeft: "10px" }}>
            {data.excluded.rows} 个 (店铺,ITEMID) · 收入 {fmt(V(data.excluded.revenue))} · 支出 {fmt(V(data.excluded.expense))}
          </span>
        </div>
      )}

      {data?.sentinels?.length ? (
        <div style={{ display: "flex", gap: "8px", flexWrap: "wrap", marginBottom: "10px" }}>
          {data.sentinels.map((s0) => (
            <span key={s0.name} title={`${s0.note}\n基准 ${s0.expect} vs 实际 ${s0.actual}（差 ${s0.diff}）`}
              style={{ fontSize: "11px", padding: "3px 10px", borderRadius: "12px", border: `1px solid ${s0.ok ? "#c6e7cf" : "#f4c7c3"}`, background: s0.ok ? "#e6f4ea" : "#fce8e6", color: s0.ok ? C.green : C.neg, cursor: "help" }}>
              {s0.ok ? "✓" : "✗"} {s0.name}{s0.ok ? "" : ` 差${s0.diff}`}
            </span>
          ))}
          <span style={{ fontSize: "11px", color: C.txt3, alignSelf: "center" }}>哨兵比总量、与聚合键无关，数值应与原页面完全一致</span>
        </div>
      ) : null}

      {/* §8 主表 */}
      <div style={{ ...card, padding: 0, overflow: "auto", maxHeight: "58vh" }}>
        <table style={{ width: tableW, minWidth: "100%", borderCollapse: "collapse", tableLayout: "fixed" }}>
          <colgroup>{cols.map((c, ci) => <col key={c.key} style={{ width: (colWidths[c.key] ?? c.w) + "px", ...(hlCell && hlCell.col === ci ? { background: "#eef2ff" } : {}) }} />)}</colgroup>
          <thead>
            <tr>
              {cols.map((col) => (
                <th key={col.key}
                  style={{ position: "sticky", top: 0, zIndex: 5, textAlign: col.align, padding: "8px 10px", fontSize: "12px", color: C.txt2, background: "#f9fafb", whiteSpace: "nowrap", userSelect: "none", boxShadow: "inset 0 -1px 0 #e5e7eb", ...pinnedCellStyle(col.key, true), ...(pinnedSet.has(col.key) ? { top: 0, background: "#f9fafb" } : {}) }}>
                  {col.label}
                  {col.tip && <i className="lxfin-info">i<span className="lxfin-tip">{col.tip}</span></i>}
                  <span className="lx-colresize" onMouseDown={(e) => startResize(e, col.key, e.currentTarget.parentElement as HTMLElement)} onClick={(e) => e.stopPropagation()} />
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {paged.map((r, i) => {
              const rowBg = hlCell ? (hlCell.row === i ? "#eef2ff" : "transparent") : (i % 2 === 0 ? "#fff" : "#fafafa");
              const pinBg = hlCell && hlCell.row === i ? "#eef2ff" : (i % 2 === 0 ? "#fff" : "#fafafa");
              return (
                <tr key={r.store_id + "||" + r.item_id} style={{ background: rowBg }}>
                  {cols.map((col, ci) => (
                    <td key={col.key}
                      onClick={(e) => {
                        if ((e.target as HTMLElement).closest("a")) return; // 交互控件内点击不触发（context TASK_CHANGE_LOG:1075）
                        setHlCell((prev) => (prev && prev.row === i && prev.col === ci ? null : { row: i, col: ci }));
                      }}
                      style={{ ...cellStyle(col.align), ...pinnedCellStyle(col.key, false), ...(pinnedSet.has(col.key) ? { background: pinBg } : {}) }}>
                      {cell(r, col.key)}
                    </td>
                  ))}
                </tr>
              );
            })}
            {!rows.length && !loading && (
              <tr><td style={{ ...cellStyle("left"), textAlign: "center", color: C.txt2, padding: "22px" }} colSpan={cols.length}>所选区间/口径无数据</td></tr>
            )}
          </tbody>
          {rows.length > 0 && (
            <tfoot>
              <tr>
                {cols.map((col, i) => (
                  <td key={col.key} style={{ position: "sticky", bottom: 0, background: "#eef2ff", fontWeight: 700, color: "#3730a3", borderTop: "2px solid #c7d2fe", textAlign: col.align, padding: "8px 10px", fontSize: "12px", whiteSpace: "nowrap", ...(pinnedSet.has(col.key) ? { left: pinLeftMap[col.key], zIndex: 6 } : { zIndex: 4 }) }}>
                    {i === 0 ? `总计（${rows.length}行）`
                      : col.key === "item_id" || col.key === "sku" || col.key === "msku" ? ""
                      : col.key === "sold_qty" || col.key === "opening_used_qty" ? totals[col.key].toLocaleString("zh-CN")
                      : ["ads", "storage", "inbound", "purchase", "firstmile", "opening_cost", "expense"].includes(col.key) ? fmt(-Math.abs(totals[col.key]))
                      : fmt(totals[col.key])}
                  </td>
                ))}
              </tr>
            </tfoot>
          )}
        </table>
      </div>

      {/* §8.2 翻页 */}
      <div style={{ display: "flex", alignItems: "center", gap: "6px", flexWrap: "wrap", margin: "10px 0" }}>
        <span style={{ fontSize: "12px", color: C.txt2 }}>每页</span>
        {PAGE_SIZE_OPTIONS.map((n) => (
          <button key={n} style={pageBtn(pageSize === n, false)} onClick={() => { setPageSize(n); setPage(1); }}>{n}</button>
        ))}
        <span style={{ width: "10px" }} />
        <button style={pageBtn(false, page <= 1)} disabled={page <= 1} onClick={() => setPage(1)}>首页</button>
        <button style={pageBtn(false, page <= 1)} disabled={page <= 1} onClick={() => setPage(page - 1)}>上一页</button>
        {Array.from({ length: Math.min(5, totalPages) }, (_, i) => {
          const start = Math.max(1, Math.min(page - 2, totalPages - 4));
          const pg = start + i;
          return pg <= totalPages ? <button key={pg} style={pageBtn(pg === page, false)} onClick={() => setPage(pg)}>{pg}</button> : null;
        })}
        <button style={pageBtn(false, page >= totalPages)} disabled={page >= totalPages} onClick={() => setPage(page + 1)}>下一页</button>
        <button style={pageBtn(false, page >= totalPages)} disabled={page >= totalPages} onClick={() => setPage(totalPages)}>末页</button>
        <span style={{ fontSize: "12px", color: C.txt3 }}>共 {rows.length} 条</span>
        <span style={{ fontSize: "12px", color: C.txt3 }}>跳至</span>
        <input type="number" min={1} max={totalPages} defaultValue={page} style={{ ...lxTB.filterInput, width: "60px", padding: "4px 8px" }}
          onKeyDown={(e) => { if (e.key === "Enter") { const v = Number((e.target as HTMLInputElement).value); if (v >= 1 && v <= totalPages) setPage(v); } }} />
        <span style={{ fontSize: "12px", color: C.txt3 }}>页</span>
      </div>

      {/* 店铺级行 */}
      {data?.store_rows?.length ? (
        <div style={{ ...card, padding: "12px 14px", marginBottom: "12px" }}>
          <b style={{ fontSize: "13px" }}>🏪 店铺级项目（参与店铺合计，不摊到单品）</b>
          <span style={{ fontSize: "11px", color: C.txt3, marginLeft: "8px" }}>
            赔付返还/广告未映射/采购未归属为账单中无 ItemID 或未匹配上的净额，单列亮出不再混黑箱
          </span>
          <table style={{ width: "100%", borderCollapse: "collapse", marginTop: "8px", fontSize: "12px" }}>
            <thead><tr>{[
              { h: "店铺", a: "left" }, { h: "SEM站外费", a: "right" }, { h: "官方测评费", a: "right" },
              { h: "赔付返还", a: "right" }, { h: "广告未映射", a: "right" }, { h: "采购未归属", a: "right" },
              { h: "其他店铺级", a: "right" }, { h: "未映射msku数", a: "right" },
            ].map((c0) => (
              <th key={c0.h} style={{ textAlign: c0.a as "left" | "right", padding: "5px 8px", color: C.txt2, background: "#f9fafb" }}>{c0.h}</th>
            ))}</tr></thead>
            <tbody>
              {data.store_rows.map((r) => (
                <tr key={r.store_id}>
                  <td style={{ padding: "5px 8px", borderTop: "1px solid #f3f4f6" }}>{r.store_name}</td>
                  <td style={{ padding: "5px 8px", borderTop: "1px solid #f3f4f6", textAlign: "right" }}>{money(V(r.sem))}</td>
                  <td style={{ padding: "5px 8px", borderTop: "1px solid #f3f4f6", textAlign: "right" }}>{money(V(r.review))}</td>
                  <td style={{ padding: "5px 8px", borderTop: "1px solid #f3f4f6", textAlign: "right" }}>{money(V(r.comp), { posGreen: true })}</td>
                  <td style={{ padding: "5px 8px", borderTop: "1px solid #f3f4f6", textAlign: "right" }}>{money(V(r.ads_unmapped))}</td>
                  <td style={{ padding: "5px 8px", borderTop: "1px solid #f3f4f6", textAlign: "right" }}>{r.purchase_unmapped == null ? <span style={{ color: C.txt3 }}>—</span> : money(-V(r.purchase_unmapped))}</td>
                  <td style={{ padding: "5px 8px", borderTop: "1px solid #f3f4f6", textAlign: "right" }}>{money(V(r.other))}</td>
                  <td style={{ padding: "5px 8px", borderTop: "1px solid #f3f4f6", textAlign: "right", color: r.unmapped_cnt ? C.amber : C.txt3 }}>{r.unmapped_cnt == null ? "—" : r.unmapped_cnt.toLocaleString("zh-CN")}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
    </div>
  );
}
