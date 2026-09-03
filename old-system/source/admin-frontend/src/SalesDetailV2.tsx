/**
 * SalesDetailV2.tsx — 每日销售明细 V2（2026-08-19 批C-1）
 * 接口：GET /api/sales-detail-v2/list（服务端分页/排序/筛选）+ /options
 * UI_STANDARDS：§1工具条 §5列宽拖动+重置+提示 §6KPI可隐藏 §7表头ⓘ §8吸顶/吸底/翻页
 *   §9 hash=#/sales-detail-v2 §11列配置(领星式弹窗) §12数值0可区分 §13行列高亮 §16筛选多选
 * 与旧「每日销售明细」的区别：读FACT层（旧页直查RAW违反分层铁律）+ 补齐V2数据链；旧页并行对账后下线。
 */
import { useEffect, useMemo, useRef, useState } from "react";
import { lxTB, IconRefresh, IconHelp, IconDownload, IconColumns } from "./LxToolbar";
import { ItemIdLink } from "./ItemIdLink";
import { DateRangePicker, DATE_QUICK_OPTIONS, fmtDateYmd } from "./LxDateRange";
import LxMultiSelect from "./LxMultiSelect";

interface Row {
  stat_date: string; store_id: string; store_name: string; owner: string;
  item_id: string; msku: string; sku: string; product_name: string;
  qty: number; sales: number; excluded_sales: number;
  refund_qty: number; refund_amount: number; refund_rate_30d: number | null;
  ad: number; wfs: number; commission: number; purchase_cost: number; first_leg: number; storage: number;
  pc_unit: number; fl_unit: number; storage_unit: number; wfs_unit: number;
  wfs_stock: number; gross_profit_old: number; order_profit: number;
  profit_rate: number | null; roi: number | null; ad_ratio: number | null;
  cost_status: string; ops_log: string; sys_ops_log: string; sys_ops_red: string;
}
interface Totals {
  qty: number; sales: number; excluded_sales: number; refund_qty: number; refund_amount: number;
  ad: number; wfs: number; commission: number; purchase_cost: number; first_leg: number;
  storage: number; gross_profit_old: number; order_profit: number;
  profit_rate: number | null; ad_ratio: number | null; roi: number | null;
  wfs_stock: number; pc_unit: number | null; fl_unit: number | null; storage_unit: number | null; wfs_unit: number | null;
}
interface Resp {
  from: string; to: string; latest_biz_date: string; days: number;
  single_item: boolean; max_days: number;
  page: number; page_size: number; total: number;
  rows: Row[]; totals: Totals; caliber_note: string; error?: string;
}

const C = { blue: "#1a73e8", txt2: "#5f6368", neg: "#d93025", green: "#188038" };
const card: React.CSSProperties = { background: "#fff", border: "1px solid #e5e7eb", borderRadius: "10px" };
const PAGE_SIZES = [50, 100, 200];
const MAX_PINNED_COLUMNS = 7;
const DEFAULT_PINNED = ["stat_date", "msku"];
const HL_BG = "#eef2ff";
const pageBtn = (active: boolean, disabled: boolean): React.CSSProperties => ({ padding: "5px 12px", borderRadius: "5px", border: "1px solid #e5e7eb", cursor: disabled ? "not-allowed" : "pointer", background: active ? "#6366f1" : "#fff", color: active ? "#fff" : "#374151", fontWeight: active ? 700 : 400, fontSize: "13px", opacity: disabled ? 0.5 : 1 });

interface Col { key: string; label: string; w: number; align: "left" | "right"; tip?: string; num?: boolean; int?: boolean; pct?: boolean; cur?: boolean; unit6?: boolean; unit2?: boolean; log?: boolean }
const COLS: Col[] = [
  { key: "stat_date", label: "日期", w: 96, align: "left", tip: "业务日（美西日界，与领星saleStat同源）" },
  { key: "store_name", label: "店铺", w: 140, align: "left" },
  { key: "owner", label: "负责人", w: 76, align: "left", tip: "dim_product.owner（店铺+MSKU）" },
  { key: "item_id", label: "商品ID", w: 112, align: "left" },
  { key: "msku", label: "MSKU", w: 120, align: "left", tip: "行粒度=日期+店铺+MSKU；CS测品已剔除" },
  { key: "sku", label: "SKU", w: 92, align: "left", tip: "本地SKU；为空=领星未绑定SKU（绑定后成本才能取到）" },
  { key: "product_name", label: "品名", w: 160, align: "left" },
  { key: "qty", label: "销量", w: 56, align: "right", num: true, int: true, tip: "当日销量，已扣除送样单件数" },
  { key: "sales", label: "销售额", w: 88, align: "right", num: true, cur: true, tip: "**当日销售额，不含送样单**（全额折扣单=0元成交，其金额见右侧「剔除送样额」）；因此比领星少一个送样额" },
  { key: "excluded_sales", label: "剔除送样额", w: 92, align: "right", num: true, cur: true, tip: "当日被剔除的送样单金额（原价口径），仅作透明展示不参与计算" },
  { key: "refund_qty", label: "退货量", w: 62, align: "right", num: true, int: true, tip: "当日退货件数（售后申请日归因）；某天可能只有退货没销售→当天利润为负" },
  { key: "refund_amount", label: "退款额", w: 78, align: "right", num: true, cur: true, tip: "当日退款净额（含税）；产品/头程成本不计回" },
  { key: "refund_rate_30d", label: "退货率30天", w: 88, align: "right", num: true, pct: true, tip: "按品计算：以查询**结束日**为锚的近30天退货件÷销量；同一品所有日期行显示同一个值（非当日值）" },
  { key: "ad", label: "广告费", w: 78, align: "right", num: true, cur: true, tip: "当日权威表全类型=SP(手动+自动)+SB+SV+SEM；item级按当日各MSKU销售额份额分摊" },
  { key: "ad_ratio", label: "广告占比", w: 78, align: "right", num: true, pct: true, tip: "当日广告费÷当日销售额" },
  { key: "wfs", label: "WFS配送费", w: 88, align: "right", num: true, cur: true, tip: "当日单件实收配送费×当日销量" },
  { key: "wfs_unit", label: "WFS配送单价$", w: 100, align: "right", num: true, unit2: true, tip: "当日单件实收WFS配送费（$，2位小数）；固定美元不随币种切换" },
  { key: "commission", label: "佣金", w: 70, align: "right", num: true, cur: true, tip: "当日销售额×佣金率（CN2501/CN2502=15%，其余12%）" },
  { key: "purchase_cost", label: "采购成本", w: 82, align: "right", num: true, cur: true, tip: "当日快照单价×当日销量÷6.6。成本按**当日历史快照价**，非当前配置价" },
  { key: "pc_unit", label: "采购单价¥", w: 88, align: "right", num: true, unit2: true, tip: "当日快照单件采购价（人民币，2位小数）；固定人民币不随币种切换" },
  { key: "first_leg", label: "头程成本", w: 82, align: "right", num: true, cur: true, tip: "当日快照单价×当日销量÷6.6（历史快照口径）" },
  { key: "fl_unit", label: "头程单价¥", w: 88, align: "right", num: true, unit2: true, tip: "当日快照单件头程价（人民币，2位小数）；固定人民币不随币种切换" },
  { key: "storage", label: "仓储费", w: 74, align: "right", num: true, cur: true, tip: "当日仓储费日摊额（账期总额÷天数）；账期未出账显示0" },
  { key: "storage_unit", label: "仓储单价$", w: 92, align: "right", num: true, unit6: true, tip: "标准单价日费（$/件/天，6位小数），取该店该SKU最新账期；显示「—」=尚无仓储账单记录；固定美元不随币种切换" },
  { key: "wfs_stock", label: "WFS可售库存", w: 96, align: "right", num: true, int: true, tip: "**当日库存快照**（与旧明细页一致，逐日变化）；合计行显示各品最新快照之和" },
  { key: "gross_profit_old", label: "毛利润(旧)", w: 88, align: "right", num: true, cur: true, tip: "旧口径当日毛利（含旧广告取数，不含退货/仓储），仅供与领星对账" },
  { key: "order_profit", label: "订单利润", w: 88, align: "right", num: true, cur: true, tip: "当日销售额−广告费−WFS配送费−佣金−采购成本−头程成本−退款额−仓储费；业务端毛利非财务净利" },
  { key: "profit_rate", label: "利润率", w: 68, align: "right", num: true, pct: true, tip: "当日订单利润÷当日销售额；合计行=Σ利润÷Σ销售额（加权）" },
  { key: "roi", label: "ROI", w: 60, align: "right", num: true, tip: "当日订单利润×6.6÷当日(采购+头程人民币)；合计行=Σ利润×6.6÷Σ成本（加权）" },
  { key: "cost_status", label: "成本状态", w: 92, align: "left", tip: "有销量时检查三项成本是否齐全" },
  { key: "sys_ops_log", label: "系统运营日志", w: 180, align: "left", log: true, tip: "当日系统运营日志（event_ops_action_log 快照差分自动检出）；显示前20字，点单元格看全文；核对不一致的条目红色加粗" },
  { key: "ops_log", label: "运营日志", w: 180, align: "left", log: true, tip: "当日运营日志（biz_product_operation_log）；显示前20字，点单元格看全文；无日志显示「运营无动作」" },
];
const ALL_KEYS = COLS.map((c) => c.key);
const colByKey = (k: string): Col => COLS.find((c) => c.key === k) as Col;

// 2026-08-22：「系统运营日志」与「运营日志」是不可拆分的一对，勾选/删除/置顶/固定/拖动一律成对，顺序恒为系统在前。
const SYS_KEY = "sys_ops_log";
const OPS_KEY = "ops_log";
function opsLogPair(k: string): string[] {
  return (k === SYS_KEY || k === OPS_KEY) ? [SYS_KEY, OPS_KEY] : [k];
}
function glueOpsPair(keys: string[]): string[] {
  if (!keys.includes(SYS_KEY) || !keys.includes(OPS_KEY)) return keys;
  const rest = keys.filter((k) => k !== SYS_KEY);
  const at = rest.indexOf(OPS_KEY);
  return [...rest.slice(0, at), SYS_KEY, ...rest.slice(at)];
}

const fm = (v: number | null | undefined, pct = false, int = false): string => {
  if (v == null) return "-";
  if (pct) return `${(v * 100).toFixed(2)}%`;
  if (int) return String(Math.round(v));
  return v.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
};

export default function SalesDetailV2({ onNavigate }: { onNavigate?: (p: string) => void }): JSX.Element {
  const [data, setData] = useState<Resp | null>(null);
  const [opts, setOpts] = useState<{ stores: Array<{ value: string; label: string }>; owners: string[] }>({ stores: [], owners: [] });
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState("");
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [activeQuick, setActiveQuick] = useState<number | null>(7);
  const [kwType, setKwType] = useState<"keyword" | "sku" | "msku" | "item_id">("keyword");
  const [kw, setKw] = useState("");
  const [stores, setStores] = useState<string[]>([]);
  const [owners, setOwners] = useState<string[]>([]);
  const [moreOpen, setMoreOpen] = useState(false);
  const [stockState, setStockState] = useState("");
  const [costState, setCostState] = useState("");
  const [gmMin, setGmMin] = useState(""); const [gmMax, setGmMax] = useState("");
  const [adMin, setAdMin] = useState(""); const [adMax, setAdMax] = useState("");
  const [kpiHidden, setKpiHidden] = useState(false);
  const [currency, setCurrency] = useState<"USD" | "RMB">("USD");
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(50);
  const [jump, setJump] = useState("");
  const [sortKey, setSortKey] = useState("stat_date");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("desc");
  const [colW, setColW] = useState<Record<string, number>>({});
  const [tipKey, setTipKey] = useState("");
  const [selectedCols, setSelectedCols] = useState<string[]>(ALL_KEYS);
  const [pinnedCols, setPinnedCols] = useState<string[]>(DEFAULT_PINNED);
  const [showColumnConfig, setShowColumnConfig] = useState(false);
  const [cfgSelected, setCfgSelected] = useState<string[]>(ALL_KEYS);
  const [cfgPins, setCfgPins] = useState<string[]>(DEFAULT_PINNED);
  const dragColIdxRef = useRef<number | null>(null);
  const [hl, setHl] = useState<{ row: string; col: string } | null>(null);
  const [logModal, setLogModal] = useState<{ title: string; text: string; colLabel?: string } | null>(null);

  useEffect(() => {
    if (typeof document !== "undefined" && !document.getElementById("lx-colresize-css")) {
      const st = document.createElement("style");
      st.id = "lx-colresize-css";
      st.textContent =
        ".lx-colresize{position:absolute;top:0;right:-4px;width:9px;height:100%;cursor:col-resize;user-select:none;z-index:3;display:flex;align-items:center;justify-content:center}" +
        ".lx-colresize::after{content:'';width:2px;height:56%;background:#dadce0;border-radius:1px;transition:background .12s,height .12s,width .12s}" +
        ".lx-colresize:hover::after{background:#1a73e8;width:3px;height:100%}";
      document.head.appendChild(st);
    }
    void fetch("/api/sales-detail-v2/options", { credentials: "include" })
      .then((r) => r.json()).then((d) => { if (!d.error) setOpts(d); }).catch(() => undefined);
  }, []);

  const load = (over?: Partial<{ from: string; to: string; page: number; pageSize: number; sortKey: string; sortDir: string }>): void => {
    setLoading(true); setErr("");
    const q = new URLSearchParams();
    const f = over?.from ?? from, t = over?.to ?? to;
    if (f) q.set("from", f);
    if (t) q.set("to", t);
    if (kw) { q.set("kw", kw); q.set("kw_type", kwType); }
    if (stores.length) q.set("stores", stores.join(","));
    if (owners.length) q.set("owners", owners.join(","));
    if (stockState) q.set("stock_state", stockState);
    if (costState) q.set("cost_state", costState);
    if (gmMin) q.set("gm_min", gmMin);
    if (gmMax) q.set("gm_max", gmMax);
    if (adMin) q.set("ad_min", adMin);
    if (adMax) q.set("ad_max", adMax);
    q.set("page", String(over?.page ?? page));
    q.set("page_size", String(over?.pageSize ?? pageSize));
    q.set("sort", over?.sortKey ?? sortKey);
    q.set("dir", over?.sortDir ?? sortDir);
    fetch(`/api/sales-detail-v2/list?${q.toString()}`, { credentials: "include" })
      .then((r) => r.json())
      .then((d: Resp) => {
        if (d.error) { setErr(d.error); setLoading(false); return; }
        setData(d); setFrom(d.from); setTo(d.to);
      })
      .catch((e) => setErr(String(e)))
      .finally(() => setLoading(false));
  };
  useEffect(() => { load({ page: 1 }); }, []);

  const anchorDate = (): string => data?.latest_biz_date || fmtDateYmd(new Date());
  const handleQuick = (days: number): void => {
    const anchor = anchorDate();
    let s = anchor;
    if (days === -1) s = `${anchor.slice(0, 8)}01`;
    else if (days > 1) s = fmtDateYmd(new Date(Date.parse(`${anchor}T00:00:00`) - (days - 1) * 86400000));
    setActiveQuick(days); setFrom(s); setTo(anchor); setPage(1);
    load({ from: s, to: anchor, page: 1 });
  };
  const doSearch = (): void => { setPage(1); setMoreOpen(false); load({ page: 1 }); };
  const doReset = (): void => {
    setKw(""); setStores([]); setOwners([]); setStockState(""); setCostState("");
    setGmMin(""); setGmMax(""); setAdMin(""); setAdMax(""); setActiveQuick(7); setPage(1);
    const anchor = anchorDate();
    const s = fmtDateYmd(new Date(Date.parse(`${anchor}T00:00:00`) - 6 * 86400000));
    setFrom(s); setTo(anchor);
    setTimeout(() => load({ from: s, to: anchor, page: 1 }), 0);
  };

  const rows = data?.rows ?? [];
  const totals = data?.totals;
  const total = data?.total ?? 0;
  const totalPages = Math.max(1, Math.ceil(total / pageSize));
  const curPage = Math.min(page, totalPages);
  const pageWin = useMemo(() => {
    const win: number[] = [];
    let s = Math.max(1, curPage - 2);
    const e = Math.min(totalPages, s + 4);
    s = Math.max(1, e - 4);
    for (let i = s; i <= e; i++) win.push(i);
    return win;
  }, [curPage, totalPages]);

  const RATE = 6.6;
  const sym = currency === "RMB" ? "¥" : "$";
  const cv = (v: number): number => currency === "RMB" ? v * RATE : v;
  const fmc = (v: number | null | undefined): string => v == null ? "-" : fm(cv(v));

  const visCols = useMemo(() => {
    const pin = selectedCols.filter((k) => pinnedCols.includes(k));
    const rest = selectedCols.filter((k) => !pinnedCols.includes(k));
    return glueOpsPair([...pin, ...rest]).map(colByKey).filter(Boolean);
  }, [selectedCols, pinnedCols]);
  const pinLeft = useMemo(() => {
    const m: Record<string, number> = {};
    let acc = 0;
    for (const c of visCols) {
      if (!pinnedCols.includes(c.key)) break;
      m[c.key] = acc; acc += colW[c.key] ?? c.w;
    }
    return m;
  }, [visCols, pinnedCols, colW]);
  const pinStyle = (key: string, kind: "head" | "body" | "foot"): React.CSSProperties => {
    if (pinLeft[key] === undefined) return {};
    const w = colW[key] ?? (colByKey(key)?.w ?? 100);
    return { position: "sticky", left: pinLeft[key], zIndex: kind === "head" ? 7 : kind === "foot" ? 6 : 2,
      width: w, minWidth: w, maxWidth: w, overflow: "hidden", textOverflow: "ellipsis",
      boxShadow: "2px 0 4px -2px rgba(0,0,0,0.12)" };
  };
  const openColumnConfig = (): void => { setCfgSelected(selectedCols); setCfgPins(pinnedCols); setShowColumnConfig(true); };
  const cfgOrderedSelected = glueOpsPair([...cfgSelected.filter((k) => cfgPins.includes(k)), ...cfgSelected.filter((k) => !cfgPins.includes(k))]);
  const applyColumnConfig = (): void => {
    setSelectedCols(cfgOrderedSelected.length ? cfgOrderedSelected : ALL_KEYS);
    setPinnedCols(cfgPins); setShowColumnConfig(false);
  };
  const startResize = (e: React.MouseEvent, key: string, th: HTMLElement): void => {
    e.preventDefault();
    const startX = e.clientX, startW = th.offsetWidth;
    const move = (ev: MouseEvent): void => setColW((w) => ({ ...w, [key]: Math.max(48, startW + ev.clientX - startX) }));
    const up = (): void => { document.removeEventListener("mousemove", move); document.removeEventListener("mouseup", up); };
    document.addEventListener("mousemove", move); document.addEventListener("mouseup", up);
  };
  const exportCsv = (): void => {
    const cols = visCols;
    const head = cols.map((c) => c.label).join(",");
    const lines = rows.map((r) => cols.map((c) => {
      const v = (r as unknown as Record<string, unknown>)[c.key];
      if (typeof v === "string") return `"${v.replace(/"/g, '""')}"`;
      if (typeof v === "number" && c.cur) return String(Math.round(cv(v) * 100) / 100);
      return String(v ?? "");
    }).join(","));
    const blob = new Blob(["﻿" + [head, ...lines].join("\n")], { type: "text/csv;charset=utf-8" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `每日销售明细V2_${from}_${to}_第${curPage}页.csv`;
    a.click();
  };

  const kpiTile = (label: string, val: string, color?: string): JSX.Element => (
    <div style={{ ...card, padding: "12px 16px", minWidth: 130 }}>
      <div style={{ fontSize: 12, color: C.txt2 }}>{label}</div>
      <div style={{ fontSize: 19, fontWeight: 700, color: color ?? "#111827", marginTop: 4 }}>{val}</div>
    </div>
  );

  return (
    <div style={{ padding: 16 }}>
      <div style={{ ...lxTB.filterWrap, display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap", position: "relative" }}>
        <span style={{ fontWeight: 700, fontSize: 15, color: "#111827" }}>每日销售明细 V2</span>
        <span style={{ fontSize: 12, color: C.txt2 }}>
          共 {total} 行 · 业务日 {data ? `${data.from} ~ ${data.to}` : "-"} · 第 {curPage}/{totalPages} 页
          {data?.single_item ? " · 已锁定单品（可查一年）" : ` · 最长${data?.max_days ?? 31}天`}
        </span>
        <span style={{ flex: 1 }} />
        <select value={kwType} onChange={(e) => setKwType(e.target.value as "keyword")} style={{ ...lxTB.filterSelect, width: 92 }}>
          <option value="keyword">关键词</option>
          <option value="sku">SKU</option>
          <option value="msku">MSKU</option>
          <option value="item_id">商品ID</option>
        </select>
        <input placeholder="搜索内容…" value={kw} onChange={(e) => setKw(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter") doSearch(); }} style={{ ...lxTB.filterInput, width: 130 }} />
        <LxMultiSelect placeholder="全部店铺" minWidth={150} options={opts.stores} selected={stores} onChange={setStores} />
        <LxMultiSelect placeholder="全部负责人" minWidth={120} options={opts.owners.map((o) => ({ value: o, label: o }))} selected={owners} onChange={setOwners} />
        <DateRangePicker start={from} end={to} quickOptions={DATE_QUICK_OPTIONS} activeQuick={activeQuick}
          onQuick={handleQuick}
          onRange={(s, e) => { setActiveQuick(null); setFrom(s); setTo(e); setPage(1); load({ from: s, to: e, page: 1 }); }} />
        <select value={currency} onChange={(e) => setCurrency(e.target.value as "USD")} title="币种（固定汇率6.6，仅换算显示）" style={{ ...lxTB.filterSelect, width: 78 }}>
          <option value="USD">USD</option>
          <option value="RMB">RMB</option>
        </select>
        <button style={{ ...lxTB.resetBtn, color: moreOpen ? C.blue : "#6b7280" }} onClick={() => setMoreOpen(!moreOpen)}>更多筛选 {moreOpen ? "▴" : "▾"}</button>
        <button style={lxTB.searchBtn} onClick={doSearch} disabled={loading}>{loading ? "查询中…" : "搜索"}</button>
        <button style={lxTB.resetBtn} onClick={doReset}>重置</button>
        <button style={lxTB.iconBtn} title="隐藏 / 显示 顶部KPI" onClick={() => setKpiHidden(!kpiHidden)}><span style={{ fontSize: 14, lineHeight: 1 }}>▤</span></button>
        <button style={lxTB.iconBtn} title="列配置" onClick={openColumnConfig}><IconColumns /></button>
        <button style={lxTB.resetBtn} onClick={() => setColW({})}>列宽重置</button>
        <button style={lxTB.iconBtn} title="刷新" onClick={() => load()}><IconRefresh /></button>
        <button style={lxTB.iconBtn} title="帮助" onClick={() => { window.location.hash = "#/help?page=sales-detail-v2"; onNavigate?.("help"); }}><IconHelp /></button>
        <button style={lxTB.iconBtn} title="导出当前页CSV" onClick={exportCsv}><IconDownload /></button>

        {moreOpen && (
          <div style={{ position: "absolute", top: "100%", right: 0, zIndex: 30, background: "#fff", border: "1px solid #e5e7eb", borderRadius: 10, boxShadow: "0 8px 24px rgba(0,0,0,0.12)", padding: 16, width: 420, marginTop: 6 }}>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
              <label style={{ fontSize: 12, color: C.txt2 }}>库存状态
                <select value={stockState} onChange={(e) => setStockState(e.target.value)} style={{ ...lxTB.filterSelect, width: "100%", marginTop: 4 }}>
                  <option value="">全部库存</option><option value="has">有库存</option><option value="none">无库存</option>
                </select>
              </label>
              <label style={{ fontSize: 12, color: C.txt2 }}>成本状态
                <select value={costState} onChange={(e) => setCostState(e.target.value)} style={{ ...lxTB.filterSelect, width: "100%", marginTop: 4 }}>
                  <option value="">全部成本状态</option><option value="full">完整</option><option value="missing">有缺失</option>
                </select>
              </label>
              <label style={{ fontSize: 12, color: C.txt2 }}>毛利率最小值 (%)
                <input value={gmMin} onChange={(e) => setGmMin(e.target.value)} style={{ ...lxTB.filterInput, width: "100%", marginTop: 4 }} />
              </label>
              <label style={{ fontSize: 12, color: C.txt2 }}>毛利率最大值 (%)
                <input value={gmMax} onChange={(e) => setGmMax(e.target.value)} style={{ ...lxTB.filterInput, width: "100%", marginTop: 4 }} />
              </label>
              <label style={{ fontSize: 12, color: C.txt2 }}>广告占比最小值 (%)
                <input value={adMin} onChange={(e) => setAdMin(e.target.value)} style={{ ...lxTB.filterInput, width: "100%", marginTop: 4 }} />
              </label>
              <label style={{ fontSize: 12, color: C.txt2 }}>广告占比最大值 (%)
                <input value={adMax} onChange={(e) => setAdMax(e.target.value)} style={{ ...lxTB.filterInput, width: "100%", marginTop: 4 }} />
              </label>
            </div>
            <div style={{ display: "flex", justifyContent: "flex-end", gap: 8, marginTop: 14 }}>
              <button style={lxTB.resetBtn} onClick={() => setMoreOpen(false)}>取消</button>
              <button style={lxTB.searchBtn} onClick={doSearch}>搜索</button>
            </div>
          </div>
        )}
      </div>

      {err && <div style={{ color: C.neg, padding: 8 }}>{err}</div>}

      {!kpiHidden && totals && (
        <div style={{ display: "flex", gap: 12, margin: "12px 0", flexWrap: "wrap" }}>
          {kpiTile("销售额", `${sym}${fmc(totals.sales)}`)}
          {kpiTile("销量", String(totals.qty))}
          {kpiTile("订单利润", `${sym}${fmc(totals.order_profit)}`, totals.order_profit >= 0 ? C.green : C.neg)}
          {kpiTile("利润率", totals.profit_rate == null ? "-" : `${(totals.profit_rate * 100).toFixed(2)}%`, totals.order_profit >= 0 ? C.green : C.neg)}
          {kpiTile("退款额", `${sym}${fmc(totals.refund_amount)}`, C.neg)}
          {kpiTile("广告费", `${sym}${fmc(totals.ad)}`)}
          {kpiTile("广告占比", totals.ad_ratio == null ? "-" : `${(totals.ad_ratio * 100).toFixed(2)}%`)}
          {kpiTile("剔除送样额", `${sym}${fmc(totals.excluded_sales)}`, C.txt2)}
        </div>
      )}

      <div style={{ fontSize: 12, color: "#9aa0a6", margin: "0 0 6px 2px" }}>
        拖列头右缘调列宽 · 点表头排序（▼▲） · 点单元格高亮行列 · 点运营日志看全文 · CS测品已剔除 · 全零行不显示 · 销售额不含送样单
      </div>

      <div style={{ ...card, overflow: "auto", maxHeight: "calc(100vh - 300px)" }}>
        <table style={{ borderCollapse: "separate", borderSpacing: 0, width: "100%", fontSize: 13 }}>
          <colgroup>{visCols.map((col) => <col key={col.key} style={hl?.col === col.key ? { background: HL_BG } : undefined} />)}</colgroup>
          <thead>
            <tr>
              {visCols.map((col) => (
                <th key={col.key}
                  style={{ position: "sticky", top: 0, zIndex: 5, textAlign: col.align, padding: "8px 10px", fontSize: 12, color: C.txt2, background: "#f9fafb", whiteSpace: "nowrap", userSelect: "none", boxShadow: "inset 0 -1px 0 #e5e7eb", width: colW[col.key] ?? col.w, minWidth: 48, cursor: "pointer", ...pinStyle(col.key, "head") }}
                  onClick={() => {
                    const nd = sortKey === col.key ? (sortDir === "asc" ? "desc" : "asc") : "desc";
                    setSortKey(col.key); setSortDir(nd); setPage(1);
                    load({ sortKey: col.key, sortDir: nd, page: 1 });
                  }}>
                  <span style={{ position: "relative", display: "inline-flex", alignItems: "center", gap: 3 }}>
                    {col.label}
                    {sortKey === col.key && <span style={{ fontSize: 10 }}>{sortDir === "desc" ? "▼" : "▲"}</span>}
                    {col.tip && (
                      <span onMouseEnter={() => setTipKey(col.key)} onMouseLeave={() => setTipKey("")} onClick={(e) => e.stopPropagation()}
                        style={{ color: "#9aa0a6", cursor: "help", fontSize: 11 }}>ⓘ
                        {tipKey === col.key && (
                          <span style={{ position: "absolute", top: 20, right: 0, zIndex: 20, background: "#202124", color: "#fff", padding: "8px 10px", borderRadius: 6, fontSize: 12, width: 250, whiteSpace: "normal", textAlign: "left", lineHeight: 1.5, fontWeight: 400 }}>{col.tip}</span>
                        )}
                      </span>
                    )}
                  </span>
                  <span className="lx-colresize" onMouseDown={(e) => startResize(e, col.key, e.currentTarget.parentElement as HTMLElement)} onClick={(e) => e.stopPropagation()} />
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((r, i) => {
              const rowKey = `${r.stat_date}|${r.store_id}|${r.msku}`;
              const rowHl = hl?.row === rowKey;
              const rowBg = hl ? (rowHl ? HL_BG : "transparent") : i % 2 ? "#fafafa" : "#fff";
              return (
                <tr key={rowKey} style={{ background: rowBg }}>
                  {visCols.map((col) => {
                    const v = (r as unknown as Record<string, unknown>)[col.key];
                    let cell: React.ReactNode;
                    if (col.key === "item_id") cell = <ItemIdLink itemId={r.item_id} />;
                    else if (col.log) {
                      const red = col.key === "sys_ops_log" ? String((r as unknown as Record<string, unknown>).sys_ops_red ?? "").trim() : "";
                      const rest = String(v ?? "").trim();
                      const full = red && rest ? `${red}；${rest}` : (red || rest);
                      const cut = full.length > 20 ? `${full.slice(0, 20)}…` : full;
                      const redShown = cut.slice(0, Math.min(red.length, cut.length));
                      const restShown = cut.slice(redShown.length);
                      cell = full
                        ? <span title="点击看全文" style={{ color: "#374151" }}>{redShown && <span style={{ color: "#dc2626", fontWeight: 700 }}>{redShown}</span>}{restShown}</span>
                        : <span style={{ color: "#9aa0a6" }}>{col.key === "sys_ops_log" ? "无系统记录" : "运营无动作"}</span>;
                    }
                    else if (col.pct) cell = fm(v as number | null, true);
                    else if (col.key === "roi") cell = v == null ? "-" : (v as number).toFixed(2);
                    else if (col.unit6) cell = v == null || v === 0 ? "—" : (v as number).toFixed(6);
                    else if (col.unit2) cell = v == null ? "-" : (v as number).toFixed(2);
                    else if (col.num) cell = col.cur ? fmc(v as number) : fm(v as number, false, col.int);
                    else cell = String(v ?? "");
                    const neg = col.num && typeof v === "number" && v < 0;
                    const isProfit = col.key === "order_profit";
                    const pinned = pinLeft[col.key] !== undefined;
                    const cellBg = rowHl || hl?.col === col.key ? HL_BG : pinned ? (hl ? "#fff" : i % 2 ? "#fafafa" : "#fff") : undefined;
                    return (
                      <td key={col.key}
                        onClick={(e) => {
                          if ((e.target as HTMLElement).closest("a,button,input,select")) return;
                          if (col.log) {
                            const red2 = col.key === "sys_ops_log" ? String((r as unknown as Record<string, unknown>).sys_ops_red ?? "").trim() : "";
                            const rest2 = String(v ?? "").trim();
                            const full2 = red2 && rest2 ? `${red2}；${rest2}` : (red2 || rest2);
                            if (full2) {
                              setLogModal({ title: `${r.stat_date}　${r.msku}　${r.store_name}`, text: full2, colLabel: col.label });
                              return;
                            }
                          }
                          setHl(rowHl && hl?.col === col.key ? null : { row: rowKey, col: col.key });
                        }}
                        style={{ padding: "7px 10px", textAlign: col.align, whiteSpace: "nowrap", borderBottom: "1px solid #f3f4f6", cursor: "pointer", background: cellBg, color: neg ? C.neg : isProfit && typeof v === "number" && v > 0 ? C.green : undefined, fontWeight: isProfit ? 700 : undefined, ...pinStyle(col.key, "body") }}>{cell}</td>
                    );
                  })}
                </tr>
              );
            })}
            {rows.length === 0 && <tr><td colSpan={visCols.length} style={{ padding: 24, textAlign: "center", color: C.txt2 }}>{loading ? "加载中…" : "无数据"}</td></tr>}
          </tbody>
          <tfoot>
            <tr>
              {visCols.map((col) => {
                let v = "";
                const t = totals;
                if (!t) v = "";
                else if (col.key === "stat_date") v = "总计";
                else if (col.key === "profit_rate") v = t.profit_rate == null ? "-" : `${(t.profit_rate * 100).toFixed(2)}%`;
                else if (col.key === "ad_ratio") v = t.ad_ratio == null ? "-" : `${(t.ad_ratio * 100).toFixed(2)}%`;
                else if (col.key === "roi") v = t.roi == null ? "-" : t.roi.toFixed(2);
                else if (col.key === "refund_rate_30d") v = "—";
                else if (col.key === "pc_unit") v = t.pc_unit == null ? "—" : t.pc_unit.toFixed(2);
                else if (col.key === "fl_unit") v = t.fl_unit == null ? "—" : t.fl_unit.toFixed(2);
                else if (col.key === "wfs_unit") v = t.wfs_unit == null ? "—" : t.wfs_unit.toFixed(2);
                else if (col.key === "storage_unit") v = t.storage_unit == null ? "—" : t.storage_unit.toFixed(6);
                else if (col.key === "qty" || col.key === "refund_qty" || col.key === "wfs_stock") v = String(Math.round(t[col.key as "qty"]));
                else if (col.key in t) v = col.cur ? fmc(t[col.key as keyof Totals] as number) : fm(t[col.key as keyof Totals] as number);
                return <td key={col.key} style={{ position: "sticky", bottom: 0, background: "#eef2ff", fontWeight: 700, color: "#3730a3", borderTop: "2px solid #c7d2fe", textAlign: col.align, padding: "8px 10px", fontSize: 12, whiteSpace: "nowrap", zIndex: pinLeft[col.key] !== undefined ? 6 : 4, ...(pinLeft[col.key] !== undefined ? { left: pinLeft[col.key] } : {}) }}>{v}</td>;
              })}
            </tr>
          </tfoot>
        </table>
      </div>

      <div style={{ display: "flex", alignItems: "center", gap: 8, marginTop: 10, fontSize: 13 }}>
        <select value={pageSize} onChange={(e) => { const n = Number(e.target.value); setPageSize(n); setPage(1); load({ pageSize: n, page: 1 }); }} style={{ ...lxTB.filterSelect, width: 100 }}>
          {PAGE_SIZES.map((n) => <option key={n} value={n}>{n} 条/页</option>)}
        </select>
        <button style={pageBtn(false, curPage <= 1)} disabled={curPage <= 1} onClick={() => { setPage(curPage - 1); load({ page: curPage - 1 }); }}>上一页</button>
        {pageWin.map((p) => <button key={p} style={pageBtn(p === curPage, false)} onClick={() => { setPage(p); load({ page: p }); }}>{p}</button>)}
        <button style={pageBtn(false, curPage >= totalPages)} disabled={curPage >= totalPages} onClick={() => { setPage(curPage + 1); load({ page: curPage + 1 }); }}>下一页</button>
        <span style={{ color: C.txt2 }}>跳至</span>
        <input value={jump} onChange={(e) => setJump(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter") { const n = Number(jump); if (n >= 1 && n <= totalPages) { setPage(n); load({ page: n }); } setJump(""); } }} style={{ ...lxTB.filterInput, width: 52 }} />
        <span style={{ color: C.txt2 }}>页 · 共 {total} 行</span>
      </div>
      {data && <div style={{ marginTop: 8, fontSize: 12, color: C.txt2, lineHeight: 1.7 }}>{data.caliber_note}</div>}

      {logModal && (
        <div style={{ position: "fixed", inset: 0, background: "rgba(15,23,42,0.4)", zIndex: 1000, display: "flex", alignItems: "center", justifyContent: "center" }} onClick={() => setLogModal(null)}>
          <div style={{ background: "#fff", borderRadius: 12, width: 620, maxHeight: "70vh", display: "flex", flexDirection: "column", overflow: "hidden", boxShadow: "0 8px 32px rgba(0,0,0,0.18)" }} onClick={(e) => e.stopPropagation()}>
            <div style={{ padding: "12px 16px", borderBottom: "1px solid #e5e7eb", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <span style={{ fontSize: 14, fontWeight: 700, color: "#374151" }}>{logModal.colLabel ?? "运营日志"} · {logModal.title}</span>
              <button onClick={() => setLogModal(null)} style={{ border: "none", background: "none", fontSize: 18, cursor: "pointer", color: "#9ca3af" }}>×</button>
            </div>
            <div style={{ padding: 16, overflowY: "auto", whiteSpace: "pre-wrap", fontSize: 13, lineHeight: 1.8, color: "#374151" }}>{logModal.text}</div>
          </div>
        </div>
      )}

      {showColumnConfig && (
        <div style={{ position: "fixed", inset: 0, background: "rgba(15,23,42,0.4)", zIndex: 1000, display: "flex", alignItems: "center", justifyContent: "center" }} onClick={() => setShowColumnConfig(false)}>
          <div style={{ background: "#fff", borderRadius: "12px", width: "680px", maxHeight: "78vh", display: "flex", flexDirection: "column", overflow: "hidden", boxShadow: "0 8px 32px rgba(0,0,0,0.18)" }} onClick={(e) => e.stopPropagation()}>
            <div style={{ padding: "12px 16px", borderBottom: "1px solid #e5e7eb", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <span style={{ fontSize: "14px", fontWeight: 700, color: "#374151" }}>列配置</span>
              <button onClick={() => setShowColumnConfig(false)} style={{ border: "none", background: "none", fontSize: "18px", cursor: "pointer", color: "#9ca3af" }}>×</button>
            </div>
            <div style={{ display: "flex", flex: 1, overflow: "hidden" }}>
              <div style={{ flex: 1, padding: "10px 14px", overflowY: "auto" }}>
                {ALL_KEYS.map((k) => (
                  <label key={k} style={{ display: "flex", alignItems: "center", gap: "6px", padding: "4px 0", cursor: "pointer", fontSize: "13px" }}>
                    <input type="checkbox" checked={cfgSelected.includes(k)}
                      onChange={() => {
                        const pair = opsLogPair(k);
                        setCfgSelected((prev) => prev.includes(k)
                          ? prev.filter((c) => !pair.includes(c))
                          : [...prev.filter((c) => !pair.includes(c)), ...pair]);
                        setCfgPins((prev) => prev.filter((c) => !pair.includes(c)));
                      }} />
                    <span style={{ color: "#374151" }}>{colByKey(k).label}</span>
                  </label>
                ))}
              </div>
              <div style={{ width: "230px", borderLeft: "1px solid #e5e7eb", padding: "10px 10px", overflowY: "auto", background: "#f8fafc" }}>
                <div style={{ fontSize: "12px", color: "#64748b", marginBottom: "2px" }}>已选 {cfgSelected.length} 列 · 拖动调顺序</div>
                <div style={{ fontSize: "11px", color: "#94a3b8", marginBottom: "6px" }}>📌最多固定{MAX_PINNED_COLUMNS}项（表格左侧冻结）</div>
                {cfgOrderedSelected.map((k, idx) => {
                  const isPin = cfgPins.includes(k);
                  return (
                    <div key={k} draggable
                      onDragStart={() => { dragColIdxRef.current = idx; }}
                      onDragOver={(e) => e.preventDefault()}
                      onDrop={() => {
                        const fromIdx = dragColIdxRef.current;
                        dragColIdxRef.current = null;
                        if (fromIdx === null || fromIdx === idx) return;
                        const view = [...cfgOrderedSelected];
                        const movedKey = view[fromIdx];
                        const targetKey = view[idx];
                        const pair = opsLogPair(movedKey).filter((c) => view.includes(c));
                        if (pair.length === 1) {
                          const [moved] = view.splice(fromIdx, 1);
                          view.splice(idx, 0, moved);
                          setCfgSelected(glueOpsPair(view));
                          return;
                        }
                        if (pair.includes(targetKey)) return;
                        const rest = view.filter((c) => !pair.includes(c));
                        let pos = rest.indexOf(targetKey);
                        if (pos < 0) pos = rest.length;
                        if (fromIdx < idx) pos += 1;
                        setCfgSelected(glueOpsPair([...rest.slice(0, pos), ...pair, ...rest.slice(pos)]));
                      }}
                      style={{ display: "flex", alignItems: "center", gap: "4px", padding: "4px 2px", fontSize: "12px", borderRadius: "4px", cursor: "grab", background: isPin ? "#eef2ff" : "transparent", borderBottom: "1px solid #f1f5f9" }}>
                      <span style={{ color: "#cbd5e1", fontSize: "13px", lineHeight: 1 }} title="拖动排序">⠿</span>
                      <span style={{ flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                        {isPin && <span style={{ fontSize: "10px" }}>📌</span>}{colByKey(k).label}
                      </span>
                      <span onClick={() => setCfgSelected((prev) => { const pair = opsLogPair(k).filter((c) => prev.includes(c)); return glueOpsPair([...pair, ...prev.filter((c) => !pair.includes(c))]); })} title="置顶" style={{ color: "#64748b", cursor: "pointer", fontSize: "12px" }}>⬆</span>
                      <span onClick={() => setCfgPins((prev) => {
                          const pair = opsLogPair(k).filter((c) => cfgSelected.includes(c));
                          if (prev.includes(k)) return prev.filter((c) => !pair.includes(c));
                          const toAdd = pair.filter((c) => !prev.includes(c));
                          if (prev.length + toAdd.length > MAX_PINNED_COLUMNS) { alert(`最多可固定${MAX_PINNED_COLUMNS}项`); return prev; }
                          return [...prev, ...toAdd];
                        })} title={isPin ? "取消固定" : "固定（左侧冻结）"} style={{ color: isPin ? "#2563eb" : "#94a3b8", cursor: "pointer", fontSize: "12px" }}>📌</span>
                      <span onClick={() => { const pair = opsLogPair(k); setCfgSelected((prev) => prev.filter((c) => !pair.includes(c))); setCfgPins((prev) => prev.filter((c) => !pair.includes(c))); }} title="删除" style={{ color: "#ef4444", cursor: "pointer", fontSize: "14px" }}>×</span>
                    </div>
                  );
                })}
              </div>
            </div>
            <div style={{ padding: "10px 16px", borderTop: "1px solid #e5e7eb", display: "flex", gap: "8px", justifyContent: "flex-end" }}>
              <button style={lxTB.resetBtn} onClick={() => { setCfgSelected(ALL_KEYS); setCfgPins(DEFAULT_PINNED); }}>重置默认</button>
              <button style={lxTB.resetBtn} onClick={() => setShowColumnConfig(false)}>取消</button>
              <button style={lxTB.searchBtn} onClick={applyColumnConfig}>应用</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
