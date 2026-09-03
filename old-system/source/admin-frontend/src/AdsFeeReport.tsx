/**
 * AdsFeeReport.tsx — 广告系统·广告费用报表（2026-08-19 新增，样板=PmcFeeDetail 全合规页）
 * 入口：广告系统菜单「广告费用报表」(#/ads/fee-report，type=native)
 * v3（2026-08-19 需求方定稿）：仅保留汇总视图（自定义日期区间），按天明细去除（财务只需汇总），
 *   账单/扣款方式拆分为独立页「广告账单扣费」(AdsBillFee.tsx，#/ads/bill-fee)。
 * v4（2026-08-19 需求方追加）：SEM纳入本报表（新增广告类型"SEM广告"；sem行已自带item_id/msku，
 *   近30天归属覆盖率100%实证）；「广告账单扣费」页不含SEM（SEM走店铺账单结算，无Connect发票）。
 * 背景（需求方拍板）：财务每月下载广告费用明细，粒度=店铺-ITEMID-MSKU-SKU。数据源 fact_ads_product_daily 非sem部分
 *   已与 Walmart Connect 发票逐张 $0.01 对平（2026-08-19 全量对账+10%抽样RAW重算全过）。
 * UI_STANDARDS 对照（逐条读原文实现）：
 *   §1工具条+元信息 §2帮助壳内跳转 §5列宽拖动+重置+提示文案 §6KPI可隐藏 §7表头ⓘ §8吸顶/吸底/翻页
 *   §9 hash路由 §11列配置=领星式680px弹窗(草稿态) §12数值0与空值可区分 §13行列高亮十字#eef2ff §16筛选一律LxMultiSelect多选
 * 接口：GET /api/finance/ads-fee/list?granularity=month&date_start&date_end（登录即可读）
 */
import { useEffect, useMemo, useRef, useState } from "react";
import { lxTB, IconRefresh, IconHelp, IconDownload, IconColumns } from "./LxToolbar";
import { ItemIdLink } from "./ItemIdLink";
import { DateRangePicker, DATE_QUICK_OPTIONS, fmtDateYmd } from "./LxDateRange";
import LxMultiSelect from "./LxMultiSelect";

interface RowAny { [k: string]: string | number | null | undefined }
interface Resp {
  granularity: string; latest_sync_time: string | null; rows: RowAny[];
  data_min?: string; data_max?: string; date_start?: string; date_end?: string; error?: string;
}

const C = { blue: "#1a73e8", txt2: "#5f6368", neg: "#d93025", green: "#188038" };
const card: React.CSSProperties = { background: "#fff", border: "1px solid #e5e7eb", borderRadius: "10px" };
const PAGE_SIZES = [50, 100, 200];
const MAX_PINNED_COLUMNS = 7;   // §11.4
const HL_BG = "#eef2ff";        // §13
const pageBtn = (active: boolean, disabled: boolean): React.CSSProperties => ({ padding: "5px 12px", borderRadius: "5px", border: "1px solid #e5e7eb", cursor: disabled ? "not-allowed" : "pointer", background: active ? "#6366f1" : "#fff", color: active ? "#fff" : "#374151", fontWeight: active ? 700 : 400, fontSize: "13px", opacity: disabled ? 0.5 : 1 });

interface Col { key: string; label: string; w: number; align: "left" | "right"; tip?: string; num?: boolean; int?: boolean; cur?: boolean; noTotal?: boolean }

// 广告类型标签（fact_ads_product_daily.campaign_type 实际取值；unknown=历史行类型列为空）
const TYPE_LABEL: Record<string, string> = {
  sponsoredProducts: "SP商品推广",
  sba: "SB品牌推广",
  video: "SV视频推广",
  sem: "SEM广告",
  unknown: "未标类型",
};

const COLS: Col[] = [
  { key: "store_name", label: "店铺", w: 150, align: "left", tip: "事实表store_id经dim_store/dim_store_config映射店铺名" },
  { key: "item_id", label: "商品ID", w: 116, align: "left", tip: "广告接口原生ItemID（费用归属主键）" },
  { key: "msku", label: "MSKU", w: 130, align: "left", tip: "广告接口原生值，为空时按产品档案(店铺+商品ID)兜底回填；同商品ID多MSKU时取其一，以商品ID为准" },
  { key: "sku", label: "SKU", w: 96, align: "left", tip: "本地SKU=dim_product(店铺+商品ID+MSKU，兜底店铺+商品ID)，历史下架品可能为空显示—" },
  { key: "owner", label: "负责人", w: 76, align: "left", tip: "dim_product 负责人（店铺+商品ID+MSKU，兜底店铺+商品ID）" },
  { key: "ad_type", label: "广告类型", w: 96, align: "left", tip: "SP商品推广(含手动+自动)/SB品牌推广/SV视频推广/SEM广告（2026-08-19起SEM纳入本报表；SEM明细页仍见「SEM广告数据」）" },
  { key: "days_covered", label: "投放天数", w: 74, align: "right", num: true, int: true, noTotal: true, tip: "所选区间内该品该类型有花费记录的天数" },
  { key: "ad_spend", label: "广告花费$", w: 96, align: "right", num: true, cur: true, tip: "区间内花费合计；SP/SB/SV已与Walmart Connect发票逐张$0.01对平，SEM已与店铺账单对账（SEM哨兵）；最近1~2天为T+2到账滞后" },
];
const ALL_KEYS = COLS.map((c) => c.key);
const colByKey = (k: string): Col => COLS.find((c) => c.key === k) as Col;
const DEFAULT_PINNED = ["store_name", "item_id"];

// §12：数值0必须显示0，仅 null/undefined 显示占位符；禁 falsy 写法
const fm = (v: number | null | undefined, int = false): string => {
  if (v == null) return "-";
  if (int) return String(Math.round(v));
  return v.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
};

export default function AdsFeeReport({ onNavigate }: { onNavigate?: (p: string) => void }): JSX.Element {
  const title = "广告费用报表";
  const helpKey = "ads-fee-report";

  const [data, setData] = useState<Resp | null>(null);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState("");
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [activeQuick, setActiveQuick] = useState<number | null>(-1); // -1=本月（缺省=数据最新日所在月）
  const [kw, setKw] = useState("");
  const [store, setStore] = useState<string[]>([]);
  const [owner, setOwner] = useState<string[]>([]);
  const [adType, setAdType] = useState<string[]>([]);
  const [applied, setApplied] = useState<{ kw: string; stores: string[]; owners: string[]; types: string[] }>({ kw: "", stores: [], owners: [], types: [] });
  const [kpiHidden, setKpiHidden] = useState(false);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(50);
  const [jump, setJump] = useState("");
  const [sortKey, setSortKey] = useState<string>("ad_spend");
  const [sortDir, setSortDir] = useState<1 | -1>(-1);
  const [colW, setColW] = useState<Record<string, number>>({});
  const [tipKey, setTipKey] = useState("");
  const [hl, setHl] = useState<{ row: string; col: string } | null>(null);

  // §11 列配置：生效态 + 弹窗草稿态
  const [selectedCols, setSelectedCols] = useState<string[]>(ALL_KEYS);
  const [pinnedCols, setPinnedCols] = useState<string[]>(DEFAULT_PINNED);
  const [showColumnConfig, setShowColumnConfig] = useState(false);
  const [cfgSelected, setCfgSelected] = useState<string[]>(ALL_KEYS);
  const [cfgPins, setCfgPins] = useState<string[]>(DEFAULT_PINNED);
  const dragColIdxRef = useRef<number | null>(null);

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
  }, []);

  const load = (f?: string, t?: string): void => {
    setLoading(true); setErr("");
    const q = new URLSearchParams({ granularity: "month" });
    if (f) q.set("date_start", f);
    if (t) q.set("date_end", t);
    fetch(`/api/finance/ads-fee/list?${q.toString()}`, { credentials: "include" })
      .then((r) => r.json())
      .then((d: Resp) => {
        if (d.error) { setErr(d.error); return; }
        setData(d); setPage(1);
        if (d.date_start) { setFrom(d.date_start); setTo(d.date_end ?? ""); }
      })
      .catch((e) => setErr(String(e)))
      .finally(() => setLoading(false));
  };
  useEffect(() => { load(from, to); }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // 快捷项锚点=数据最新可用日
  const anchorDate = (): string => data?.data_max || fmtDateYmd(new Date());
  const handleQuick = (days: number): void => {
    const anchor = anchorDate();
    let s = anchor;
    if (days === -1) s = `${anchor.slice(0, 8)}01`;
    else if (days > 1) s = fmtDateYmd(new Date(Date.parse(`${anchor}T00:00:00`) - (days - 1) * 86400000));
    setActiveQuick(days); setFrom(s); setTo(anchor);
    load(s, anchor);
  };

  const doSearch = (): void => { setApplied({ kw: kw.trim(), stores: store, owners: owner, types: adType }); setPage(1); };
  const doReset = (): void => {
    setKw(""); setStore([]); setOwner([]); setAdType([]);
    setApplied({ kw: "", stores: [], owners: [], types: [] });
    setPage(1);
    load(from, to);
  };

  const stores = useMemo(() => {
    const m = new Map<string, string>();
    for (const r of data?.rows ?? []) if (!m.has(String(r.store_id))) m.set(String(r.store_id), String(r.store_name || r.store_id));
    return Array.from(m.entries()).sort((a, b) => a[1].localeCompare(b[1]));
  }, [data]);
  const owners = useMemo(() => {
    const s = new Set<string>();
    for (const r of data?.rows ?? []) if (r.owner) s.add(String(r.owner));
    return Array.from(s).sort((a, b) => a.localeCompare(b));
  }, [data]);
  const adTypes = useMemo(() => {
    const s = new Set<string>();
    for (const r of data?.rows ?? []) if (r.ad_type) s.add(String(r.ad_type));
    return Array.from(s).sort((a, b) => a.localeCompare(b));
  }, [data]);

  const filtered = useMemo(() => {
    const a = applied;
    return (data?.rows ?? []).filter((r) => {
      if (a.kw) {
        // 2026-08-24 需求方拍板：纯数字输入=商品ID全等匹配（避免搜 1001 混入 20138100180 等子串命中）；
        // 非纯数字维持原子串匹配，不改运营既有搜索习惯。
        if (/^\d+$/.test(a.kw)) {
          if (String(r.item_id ?? "") !== a.kw) return false;
        } else {
          const k = a.kw.toLowerCase();
          const hay = [r.msku, r.sku, r.item_id, r.store_name, r.owner]
            .map((v) => String(v ?? "").toLowerCase());
          if (!hay.some((h) => h.includes(k))) return false;
        }
      }
      if (a.stores.length > 0 && !a.stores.includes(String(r.store_id))) return false;
      if (a.owners.length > 0 && !a.owners.includes(String(r.owner ?? ""))) return false;
      if (a.types.length > 0 && !a.types.includes(String(r.ad_type ?? ""))) return false;
      return true;
    });
  }, [data, applied]);

  const sorted = useMemo(() => {
    const rows = [...filtered];
    rows.sort((a, b) => {
      const av = a[sortKey], bv = b[sortKey];
      if (typeof av === "number" || typeof bv === "number" || av === null || bv === null) {
        return ((Number(av ?? -Infinity)) - (Number(bv ?? -Infinity))) * sortDir;
      }
      return String(av ?? "").localeCompare(String(bv ?? "")) * sortDir;
    });
    return rows;
  }, [filtered, sortKey, sortDir]);

  const totalPages = Math.max(1, Math.ceil(sorted.length / pageSize));
  const curPage = Math.min(page, totalPages);
  const pageRows = sorted.slice((curPage - 1) * pageSize, curPage * pageSize);
  const pageWin = useMemo(() => {
    const win: number[] = [];
    let s = Math.max(1, curPage - 2);
    const e = Math.min(totalPages, s + 4);
    s = Math.max(1, e - 4);
    for (let i = s; i <= e; i++) win.push(i);
    return win;
  }, [curPage, totalPages]);

  // 合计（当前筛选全量）
  const totals = useMemo(() => {
    const t: Record<string, number> = {};
    for (const r of sorted) {
      for (const c of COLS) {
        if (!c.num || c.noTotal) continue;
        t[c.key] = (t[c.key] ?? 0) + Number(r[c.key] ?? 0);
      }
    }
    return t;
  }, [sorted]);

  // KPI（当前筛选全量）：总花费 + 分类型小计
  const kpis = useMemo(() => {
    const byType = new Map<string, number>();
    for (const r of sorted) {
      const k = String(r.ad_type ?? "unknown");
      byType.set(k, (byType.get(k) ?? 0) + Number(r.ad_spend ?? 0));
    }
    const tiles: { label: string; val: string; color?: string }[] = [
      { label: "汇总行数", val: String(sorted.length) },
      { label: "日期区间", val: from && to ? `${from} ~ ${to}` : "-" },
      { label: "广告花费合计", val: `$${fm(totals.ad_spend ?? 0)}`, color: C.neg },
    ];
    for (const [k, v] of Array.from(byType.entries()).sort((a, b) => b[1] - a[1])) {
      tiles.push({ label: TYPE_LABEL[k] ?? k, val: `$${fm(v)}` });
    }
    return tiles;
  }, [sorted, totals, from, to]);

  // §11.5 固定列归组在前 + 列宽累加left偏移，逐格内联sticky
  const visCols = useMemo(() => {
    const pin = selectedCols.filter((k) => pinnedCols.includes(k));
    const rest = selectedCols.filter((k) => !pinnedCols.includes(k));
    return [...pin, ...rest].map(colByKey).filter(Boolean);
  }, [selectedCols, pinnedCols]);
  const pinLeft = useMemo(() => {
    const m: Record<string, number> = {};
    let acc = 0;
    for (const c of visCols) {
      if (!pinnedCols.includes(c.key)) break;
      m[c.key] = acc;
      acc += colW[c.key] ?? c.w;
    }
    return m;
  }, [visCols, pinnedCols, colW]);
  const pinStyle = (key: string, kindStyle: "head" | "body" | "foot"): React.CSSProperties =>
    pinLeft[key] !== undefined
      ? { position: "sticky", left: pinLeft[key], zIndex: kindStyle === "head" ? 7 : kindStyle === "foot" ? 6 : 2, boxShadow: "2px 0 4px -2px rgba(0,0,0,0.12)" }
      : {};

  const openColumnConfig = (): void => { setCfgSelected(selectedCols); setCfgPins(pinnedCols); setShowColumnConfig(true); };
  const applyColumnConfig = (): void => {
    setSelectedCols(cfgSelected.length ? cfgSelected : ALL_KEYS);
    setPinnedCols(cfgPins);
    setShowColumnConfig(false);
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
    const lines = sorted.map((r) => cols.map((c) => {
      let v: unknown = r[c.key];
      if (c.key === "ad_type") v = TYPE_LABEL[String(v)] ?? v;
      if (typeof v === "string") return `"${v.replace(/"/g, '""')}"`;
      return String(v ?? "");
    }).join(","));
    const blob = new Blob(["﻿" + [head, ...lines].join("\n")], { type: "text/csv;charset=utf-8" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `${title}_汇总_${from}_${to}.csv`;
    a.click();
  };

  const syncText = data?.latest_sync_time
    ? new Date(data.latest_sync_time.replace(" ", "T")).toLocaleString("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" })
    : "加载中";
  const kpiTile = (label: string, val: string, color?: string): JSX.Element => (
    <div key={label} style={{ ...card, padding: "12px 16px", minWidth: 140 }}>
      <div style={{ fontSize: 12, color: C.txt2 }}>{label}</div>
      <div style={{ fontSize: 20, fontWeight: 700, color: color ?? "#111827", marginTop: 4 }}>{val}</div>
    </div>
  );

  return (
    <div style={{ padding: 16 }}>
      {/* §1 工具条 + 元信息 */}
      <div style={{ ...lxTB.filterWrap, display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap", position: "relative" }}>
        <span style={{ fontWeight: 700, fontSize: 15, color: "#111827" }}>{title}</span>
        <span style={{ fontSize: 12, color: C.txt2 }}>共 {sorted.length} 行 · 同步 {syncText} · 第 {curPage}/{totalPages} 页</span>
        <span style={{ flex: 1 }} />
        <input placeholder="MSKU/SKU/商品ID…" value={kw} onChange={(e) => setKw(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter") doSearch(); }} style={{ ...lxTB.filterInput, width: 160 }} />
        <LxMultiSelect placeholder="全部店铺" minWidth={140}
          options={stores.map(([id, name]) => ({ value: id, label: name }))}
          selected={store} onChange={setStore} />
        <LxMultiSelect placeholder="全部负责人" minWidth={110}
          options={owners.map((o) => ({ value: o, label: o }))}
          selected={owner} onChange={setOwner} />
        <LxMultiSelect placeholder="全部广告类型" minWidth={120}
          options={adTypes.map((t) => ({ value: t, label: TYPE_LABEL[t] ?? t }))}
          selected={adType} onChange={setAdType} />
        <DateRangePicker start={from} end={to} quickOptions={DATE_QUICK_OPTIONS} activeQuick={activeQuick}
          onQuick={handleQuick}
          onRange={(s, e) => { setActiveQuick(null); setFrom(s); setTo(e); load(s, e); }} />
        <button style={lxTB.searchBtn} onClick={doSearch} disabled={loading}>{loading ? "查询中…" : "搜索"}</button>
        <button style={lxTB.resetBtn} onClick={doReset}>重置</button>
        <button style={lxTB.iconBtn} title="隐藏 / 显示 顶部KPI" onClick={() => setKpiHidden(!kpiHidden)}><span style={{ fontSize: 14, lineHeight: 1 }}>▤</span></button>
        <button style={lxTB.iconBtn} title="列配置" onClick={openColumnConfig}><IconColumns /></button>
        <button style={lxTB.resetBtn} onClick={() => setColW({})}>列宽重置</button>
        <button style={lxTB.iconBtn} title="刷新" onClick={() => load(from, to)}><IconRefresh /></button>
        <button style={lxTB.iconBtn} title="帮助" onClick={() => { window.location.hash = `#/help?page=${helpKey}`; onNavigate?.("help"); }}><IconHelp /></button>
        <button style={lxTB.iconBtn} title="导出CSV（当前筛选全部行）" onClick={exportCsv}><IconDownload /></button>
      </div>

      {err && <div style={{ color: C.neg, padding: 8 }}>{err}</div>}

      {/* §6 KPI */}
      {!kpiHidden && (
        <div style={{ display: "flex", gap: 12, margin: "12px 0", flexWrap: "wrap" }}>
          {kpis.map((k) => kpiTile(k.label, k.val, k.color))}
        </div>
      )}

      {/* §5.3 提示文案 */}
      <div style={{ fontSize: 12, color: "#9aa0a6", margin: "0 0 6px 2px" }}>
        拖列头右缘调列宽 · 点表头排序（▼▲） · 点单元格高亮行列 · 本页=全部广告类型(SP/SB/SV+SEM)按品汇总，发票级扣款见「广告账单扣费」页，SEM明细另见「SEM广告数据」页 · SP/SB/SV已与Connect发票对平、SEM已与店铺账单对账（最近1~2天T+2到账滞后） · 仅显示区间内有花费的行
      </div>

      {/* §8 表格 */}
      <div style={{ ...card, overflow: "auto", maxHeight: "calc(100vh - 290px)" }}>
        <table style={{ borderCollapse: "separate", borderSpacing: 0, width: "100%", fontSize: 13 }}>
          <colgroup>
            {visCols.map((col) => <col key={col.key} style={hl?.col === col.key ? { background: HL_BG } : undefined} />)}
          </colgroup>
          <thead>
            <tr>
              {visCols.map((col) => (
                <th key={col.key}
                  style={{ position: "sticky", top: 0, zIndex: 5, textAlign: col.align, padding: "8px 10px", fontSize: 12, color: C.txt2, background: "#f9fafb", whiteSpace: "nowrap", userSelect: "none", boxShadow: "inset 0 -1px 0 #e5e7eb", width: colW[col.key] ?? col.w, minWidth: 48, cursor: "pointer", ...pinStyle(col.key, "head") }}
                  onClick={() => { if (sortKey === col.key) setSortDir(sortDir === 1 ? -1 : 1); else { setSortKey(col.key); setSortDir(-1); } }}>
                  <span style={{ position: "relative", display: "inline-flex", alignItems: "center", gap: 3 }}>
                    {col.label}
                    {sortKey === col.key && <span style={{ fontSize: 10 }}>{sortDir === -1 ? "▼" : "▲"}</span>}
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
            {pageRows.map((r, i) => {
              const rowKey = `${r.store_id}|${r.item_id ?? ""}|${r.msku ?? ""}|${r.ad_type ?? ""}`;
              const rowHl = hl?.row === rowKey;
              const rowBg = hl ? (rowHl ? HL_BG : "transparent") : i % 2 ? "#fafafa" : "#fff";
              return (
                <tr key={rowKey} style={{ background: rowBg }}>
                  {visCols.map((col) => {
                    const v = r[col.key];
                    let cell: React.ReactNode;
                    if (col.key === "item_id") cell = v ? <ItemIdLink itemId={String(v)} /> : "—";
                    else if (col.key === "ad_type") cell = TYPE_LABEL[String(v)] ?? String(v ?? "—");
                    else if (col.num) cell = fm(v as number | null, col.int);
                    else cell = String(v ?? "") || "—";
                    const neg = col.num && typeof v === "number" && v < 0;
                    const pinnedCell = pinLeft[col.key] !== undefined;
                    const cellBg = rowHl || hl?.col === col.key ? HL_BG : pinnedCell ? (hl ? "#fff" : i % 2 ? "#fafafa" : "#fff") : undefined;
                    return (
                      <td key={col.key}
                        onClick={(e) => {
                          if ((e.target as HTMLElement).closest("a,button,input,select")) return;
                          setHl(rowHl && hl?.col === col.key ? null : { row: rowKey, col: col.key });
                        }}
                        style={{ padding: "7px 10px", textAlign: col.align, whiteSpace: "nowrap", borderBottom: "1px solid #f3f4f6", cursor: "pointer", background: cellBg, color: neg ? C.neg : undefined, ...pinStyle(col.key, "body") }}>{cell}</td>
                    );
                  })}
                </tr>
              );
            })}
            {pageRows.length === 0 && <tr><td colSpan={visCols.length} style={{ padding: 24, textAlign: "center", color: C.txt2 }}>{loading ? "加载中…" : "无数据"}</td></tr>}
          </tbody>
          <tfoot>
            <tr>
              {visCols.map((col) => {
                let v = "";
                if (col.key === "store_name") v = `总计（${sorted.length}行）`;
                else if (col.num && !col.noTotal && col.key in totals) v = fm(totals[col.key], col.int);
                return <td key={col.key} style={{ position: "sticky", bottom: 0, background: "#eef2ff", fontWeight: 700, color: "#3730a3", borderTop: "2px solid #c7d2fe", textAlign: col.align, padding: "8px 10px", fontSize: 12, whiteSpace: "nowrap", zIndex: pinLeft[col.key] !== undefined ? 6 : 4, ...(pinLeft[col.key] !== undefined ? { left: pinLeft[col.key] } : {}) }}>{v}</td>;
              })}
            </tr>
          </tfoot>
        </table>
      </div>

      {/* §8 翻页 */}
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginTop: 10, fontSize: 13 }}>
        <select value={pageSize} onChange={(e) => { setPageSize(Number(e.target.value)); setPage(1); }} style={{ ...lxTB.filterSelect, width: 100 }}>
          {PAGE_SIZES.map((n) => <option key={n} value={n}>{n} 条/页</option>)}
        </select>
        <button style={pageBtn(false, curPage <= 1)} disabled={curPage <= 1} onClick={() => setPage(1)}>首页</button>
        <button style={pageBtn(false, curPage <= 1)} disabled={curPage <= 1} onClick={() => setPage(curPage - 1)}>上一页</button>
        {pageWin.map((p) => <button key={p} style={pageBtn(p === curPage, false)} onClick={() => setPage(p)}>{p}</button>)}
        <button style={pageBtn(false, curPage >= totalPages)} disabled={curPage >= totalPages} onClick={() => setPage(curPage + 1)}>下一页</button>
        <button style={pageBtn(false, curPage >= totalPages)} disabled={curPage >= totalPages} onClick={() => setPage(totalPages)}>末页</button>
        <span style={{ color: C.txt2 }}>共 {sorted.length} 条 · 跳至</span>
        <input value={jump} onChange={(e) => setJump(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter") { const n = Number(jump); if (n >= 1 && n <= totalPages) setPage(n); setJump(""); } }} style={{ ...lxTB.filterInput, width: 52 }} />
        <span style={{ color: C.txt2 }}>页</span>
      </div>

      {/* §11 列配置弹窗（照样板 FeishuRawSalesData:2272，逐要素一致） */}
      {showColumnConfig && (
        <div style={{ position: "fixed", inset: 0, background: "rgba(15,23,42,0.4)", zIndex: 1000, display: "flex", alignItems: "center", justifyContent: "center" }}
          onClick={() => setShowColumnConfig(false)}>
          <div style={{ background: "#fff", borderRadius: "12px", width: "680px", maxHeight: "78vh", display: "flex", flexDirection: "column", overflow: "hidden", boxShadow: "0 8px 32px rgba(0,0,0,0.18)" }}
            onClick={(e) => e.stopPropagation()}>
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
                        setCfgSelected((prev) => prev.includes(k) ? prev.filter((c) => c !== k) : [...prev, k]);
                        setCfgPins((prev) => prev.filter((c) => c !== k));
                      }} />
                    <span style={{ color: "#374151" }}>{colByKey(k).label}</span>
                  </label>
                ))}
              </div>
              <div style={{ width: "230px", borderLeft: "1px solid #e5e7eb", padding: "10px 10px", overflowY: "auto", background: "#f8fafc" }}>
                <div style={{ fontSize: "12px", color: "#64748b", marginBottom: "2px" }}>已选 {cfgSelected.length} 列 · 拖动调顺序</div>
                <div style={{ fontSize: "11px", color: "#94a3b8", marginBottom: "6px" }}>📌最多固定{MAX_PINNED_COLUMNS}项（表格左侧冻结）</div>
                {cfgSelected.map((k, idx) => {
                  const isPin = cfgPins.includes(k);
                  return (
                    <div key={k} draggable
                      onDragStart={() => { dragColIdxRef.current = idx; }}
                      onDragOver={(e) => e.preventDefault()}
                      onDrop={() => {
                        const fromIdx = dragColIdxRef.current;
                        dragColIdxRef.current = null;
                        if (fromIdx === null || fromIdx === idx) return;
                        const view = [...cfgSelected];
                        const [moved] = view.splice(fromIdx, 1);
                        view.splice(idx, 0, moved);
                        setCfgSelected(view);
                      }}
                      style={{ display: "flex", alignItems: "center", gap: "4px", padding: "4px 2px", fontSize: "12px", borderRadius: "4px", cursor: "grab", background: isPin ? "#eef2ff" : "transparent", borderBottom: "1px solid #f1f5f9" }}>
                      <span style={{ color: "#cbd5e1", fontSize: "13px", lineHeight: 1 }} title="拖动排序">⠿</span>
                      <span style={{ flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                        {isPin && <span style={{ fontSize: "10px" }}>📌</span>}{colByKey(k).label}
                      </span>
                      <span onClick={() => setCfgSelected((prev) => [k, ...prev.filter((c) => c !== k)])} title="置顶"
                        style={{ color: "#64748b", cursor: "pointer", fontSize: "12px" }}>⬆</span>
                      <span onClick={() => setCfgPins((prev) => {
                          if (prev.includes(k)) return prev.filter((c) => c !== k);
                          if (prev.length + 1 > MAX_PINNED_COLUMNS) { alert(`最多可固定${MAX_PINNED_COLUMNS}项`); return prev; }
                          return [...prev, k];
                        })} title={isPin ? "取消固定" : "固定（左侧冻结）"}
                        style={{ color: isPin ? "#2563eb" : "#94a3b8", cursor: "pointer", fontSize: "12px" }}>📌</span>
                      <span onClick={() => {
                          setCfgSelected((prev) => prev.filter((c) => c !== k));
                          setCfgPins((prev) => prev.filter((c) => c !== k));
                        }} title="删除"
                        style={{ color: "#ef4444", cursor: "pointer", fontSize: "14px" }}>×</span>
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
