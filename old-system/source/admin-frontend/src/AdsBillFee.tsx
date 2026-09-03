/**
 * AdsBillFee.tsx — 广告系统·广告账单扣费（2026-08-19 自广告费用报表拆分独立，样板=PmcFeeDetail 全合规页）
 * 入口：广告系统菜单「广告账单扣费」(#/ads/bill-fee，type=native)
 * 背景（需求方拍板）：财务核对广告费从哪里扣（Seller Center=店铺余额，对店铺结算单；
 *   Credit Card=信用卡，店铺结算单无痕；Invoice=已出账待扣款）。一行=一张Walmart Connect发票。
 * UI_STANDARDS 对照（逐条读原文实现）：
 *   §1工具条+元信息 §2帮助壳内跳转 §5列宽拖动+重置+提示文案 §6KPI可隐藏 §7表头ⓘ §8吸顶/吸底/翻页
 *   §9 hash路由 §11列配置=领星式680px弹窗(草稿态) §12数值0与空值可区分 §13行列高亮十字#eef2ff §16筛选一律LxMultiSelect多选
 * 接口：GET /api/finance/ads-fee/list?granularity=bill（登录即可读，后端复用广告费用报表模块）
 */
import { useEffect, useMemo, useRef, useState } from "react";
import { lxTB, IconRefresh, IconHelp, IconDownload, IconColumns } from "./LxToolbar";
import LxMultiSelect from "./LxMultiSelect";

interface RowAny { [k: string]: string | number | null | undefined }
interface Resp { granularity: string; latest_sync_time: string | null; rows: RowAny[]; data_min?: string; data_max?: string; error?: string }

const C = { blue: "#1a73e8", txt2: "#5f6368", neg: "#d93025", green: "#188038" };
const card: React.CSSProperties = { background: "#fff", border: "1px solid #e5e7eb", borderRadius: "10px" };
const PAGE_SIZES = [50, 100, 200];
const MAX_PINNED_COLUMNS = 7;   // §11.4
const HL_BG = "#eef2ff";        // §13
const pageBtn = (active: boolean, disabled: boolean): React.CSSProperties => ({ padding: "5px 12px", borderRadius: "5px", border: "1px solid #e5e7eb", cursor: disabled ? "not-allowed" : "pointer", background: active ? "#6366f1" : "#fff", color: active ? "#fff" : "#374151", fontWeight: active ? 700 : 400, fontSize: "13px", opacity: disabled ? 0.5 : 1 });

interface Col { key: string; label: string; w: number; align: "left" | "right"; tip?: string; num?: boolean; int?: boolean; cur?: boolean; noTotal?: boolean }

const COLS: Col[] = [
  { key: "store_name", label: "店铺", w: 150, align: "left", tip: "发票账号经绑定表映射店铺（导入时防串店门禁校验）" },
  { key: "invoice_number", label: "发票号", w: 100, align: "left", tip: "Walmart Connect发票号（Invoice number），可回溯Connect后台原件" },
  { key: "period_start", label: "账期起", w: 92, align: "left", tip: "发票覆盖期间起日（发票原文，期间长短不固定）" },
  { key: "period_end", label: "账期止", w: 92, align: "left", tip: "发票覆盖期间止日（含）" },
  { key: "invoice_date", label: "发票日期", w: 92, align: "left", tip: "发票开具日（Invoice date）" },
  { key: "charge_date", label: "扣款日期", w: 92, align: "left", tip: "实际扣款日（Receipt版式）；待扣款Invoice版式显示—，扣款后重导同发票号自动回填" },
  { key: "line_count", label: "campaign行数", w: 96, align: "right", num: true, int: true, tip: "发票内campaign明细行数" },
  { key: "ad_spend", label: "广告花费$", w: 96, align: "right", num: true, cur: true, tip: "发票Total Ad Spend（已与日粒度数据逐张$0.01对平）" },
  { key: "credits_applied", label: "Credit抵扣$", w: 96, align: "right", num: true, cur: true, tip: "发票内广告返还抵扣（Total Ad Credits Applied，负数=抵扣）" },
  { key: "total_charged", label: "实扣金额$", w: 96, align: "right", num: true, cur: true, tip: "实际扣款额=广告花费+Credit抵扣；待扣款Invoice版式=应付额" },
  { key: "payment_method", label: "扣款方式", w: 150, align: "left", tip: "Seller Center(店铺余额,计入店铺结算单)/Credit Card(信用卡,店铺结算单无痕)/Invoice(待扣款)" },
  { key: "source_task_id", label: "导入批次", w: 156, align: "left", tip: "广告发票导入批次号（WMCINV-日期-序号），可追溯RAW原文行" },
];
const ALL_KEYS = COLS.map((c) => c.key);
const colByKey = (k: string): Col => COLS.find((c) => c.key === k) as Col;
const DEFAULT_PINNED = ["store_name", "invoice_number"];

// 扣款方式归一（原文含账号尾号，如 Seller Center (***9662)；筛选与KPI按归一值分组）
const payNorm = (v: unknown): string => {
  const s = String(v ?? "");
  if (s.startsWith("Seller Center")) return "Seller Center";
  if (s.startsWith("Credit Card")) return "Credit Card";
  if (s.startsWith("Invoice")) return "Invoice(待扣款)";
  return s || "—";
};

// §12：数值0必须显示0，仅 null/undefined 显示占位符；禁 falsy 写法
const fm = (v: number | null | undefined, int = false): string => {
  if (v == null) return "-";
  if (int) return String(Math.round(v));
  return v.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
};

export default function AdsBillFee({ onNavigate }: { onNavigate?: (p: string) => void }): JSX.Element {
  const title = "广告账单扣费";
  const helpKey = "ads-bill-fee";

  const [data, setData] = useState<Resp | null>(null);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState("");
  const [kw, setKw] = useState("");
  const [store, setStore] = useState<string[]>([]);
  const [period, setPeriod] = useState<string[]>([]);
  const [pay, setPay] = useState<string[]>([]);
  const [applied, setApplied] = useState<{ kw: string; stores: string[]; periods: string[]; pays: string[] }>({ kw: "", stores: [], periods: [], pays: [] });
  const [kpiHidden, setKpiHidden] = useState(false);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(50);
  const [jump, setJump] = useState("");
  const [sortKey, setSortKey] = useState<string>("period_start");
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

  const load = (): void => {
    setLoading(true); setErr("");
    fetch(`/api/finance/ads-fee/list?granularity=bill`, { credentials: "include" })
      .then((r) => r.json())
      .then((d: Resp) => {
        if (d.error) { setErr(d.error); return; }
        setData(d); setPage(1);
      })
      .catch((e) => setErr(String(e)))
      .finally(() => setLoading(false));
  };
  useEffect(() => { load(); }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const doSearch = (): void => { setApplied({ kw: kw.trim(), stores: store, periods: period, pays: pay }); setPage(1); };
  const doReset = (): void => {
    setKw(""); setStore([]); setPeriod([]); setPay([]);
    setApplied({ kw: "", stores: [], periods: [], pays: [] });
    setPage(1);
    load();
  };

  const stores = useMemo(() => {
    const m = new Map<string, string>();
    for (const r of data?.rows ?? []) if (!m.has(String(r.store_id))) m.set(String(r.store_id), String(r.store_name || r.store_id));
    return Array.from(m.entries()).sort((a, b) => a[1].localeCompare(b[1]));
  }, [data]);
  const periods = useMemo(() => {
    const s = new Set<string>();
    for (const r of data?.rows ?? []) if (r.period_start) s.add(`${r.period_start}~${r.period_end}`);
    return Array.from(s).sort((a, b) => b.localeCompare(a));
  }, [data]);
  const pays = useMemo(() => {
    const s = new Set<string>();
    for (const r of data?.rows ?? []) s.add(payNorm(r.payment_method));
    return Array.from(s).sort((a, b) => a.localeCompare(b));
  }, [data]);

  const filtered = useMemo(() => {
    const a = applied;
    return (data?.rows ?? []).filter((r) => {
      if (a.kw) {
        const k = a.kw.toLowerCase();
        const hay = [r.invoice_number, r.store_name, r.payment_method, r.source_task_id]
          .map((v) => String(v ?? "").toLowerCase());
        if (!hay.some((h) => h.includes(k))) return false;
      }
      if (a.stores.length > 0 && !a.stores.includes(String(r.store_id))) return false;
      if (a.periods.length > 0 && !a.periods.includes(`${r.period_start}~${r.period_end}`)) return false;
      if (a.pays.length > 0 && !a.pays.includes(payNorm(r.payment_method))) return false;
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

  // KPI（当前筛选全量）：发票数+花费/抵扣/实扣+分扣款方式实扣小计
  const kpis = useMemo(() => {
    const byPay = new Map<string, number>();
    for (const r of sorted) {
      const k = payNorm(r.payment_method);
      byPay.set(k, (byPay.get(k) ?? 0) + Number(r.total_charged ?? 0));
    }
    const tiles: { label: string; val: string; color?: string }[] = [
      { label: "发票数", val: String(sorted.length) },
      { label: "广告花费合计", val: `$${fm(totals.ad_spend ?? 0)}`, color: C.neg },
      { label: "Credit抵扣合计", val: `$${fm(totals.credits_applied ?? 0)}`, color: C.green },
      { label: "实扣合计", val: `$${fm(totals.total_charged ?? 0)}`, color: C.neg },
    ];
    for (const [k, v] of Array.from(byPay.entries()).sort((a, b) => b[1] - a[1])) {
      tiles.push({ label: `${k}实扣`, val: `$${fm(v)}` });
    }
    return tiles;
  }, [sorted, totals]);

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
      const v: unknown = r[c.key];
      if (typeof v === "string") return `"${v.replace(/"/g, '""')}"`;
      return String(v ?? "");
    }).join(","));
    const blob = new Blob(["﻿" + [head, ...lines].join("\n")], { type: "text/csv;charset=utf-8" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `${title}.csv`;
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
        <input placeholder="发票号/店铺…" value={kw} onChange={(e) => setKw(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter") doSearch(); }} style={{ ...lxTB.filterInput, width: 160 }} />
        <LxMultiSelect placeholder="全部店铺" minWidth={140}
          options={stores.map(([id, name]) => ({ value: id, label: name }))}
          selected={store} onChange={setStore} />
        <LxMultiSelect placeholder="全部账期" minWidth={120} menuMinWidth={300}
          options={periods.map((p) => ({ value: p, label: p }))}
          selected={period} onChange={setPeriod} />
        <LxMultiSelect placeholder="全部扣款方式" minWidth={130}
          options={pays.map((p) => ({ value: p, label: p }))}
          selected={pay} onChange={setPay} />
        <button style={lxTB.searchBtn} onClick={doSearch} disabled={loading}>{loading ? "查询中…" : "搜索"}</button>
        <button style={lxTB.resetBtn} onClick={doReset}>重置</button>
        <button style={lxTB.iconBtn} title="隐藏 / 显示 顶部KPI" onClick={() => setKpiHidden(!kpiHidden)}><span style={{ fontSize: 14, lineHeight: 1 }}>▤</span></button>
        <button style={lxTB.iconBtn} title="列配置" onClick={openColumnConfig}><IconColumns /></button>
        <button style={lxTB.resetBtn} onClick={() => setColW({})}>列宽重置</button>
        <button style={lxTB.iconBtn} title="刷新" onClick={load}><IconRefresh /></button>
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
        拖列头右缘调列宽 · 点表头排序（▼▲） · 点单元格高亮行列 · 一行=一张Walmart Connect发票 · Seller Center=店铺余额扣款（对店铺结算单）、Credit Card=信用卡扣款（店铺结算单无痕）、Invoice=已出账待扣款（扣款后重导自动更新）
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
              const rowKey = `${r.store_id}|${r.invoice_number ?? ""}`;
              const rowHl = hl?.row === rowKey;
              const rowBg = hl ? (rowHl ? HL_BG : "transparent") : i % 2 ? "#fafafa" : "#fff";
              return (
                <tr key={rowKey} style={{ background: rowBg }}>
                  {visCols.map((col) => {
                    const v = r[col.key];
                    let cell: React.ReactNode;
                    if (col.num) cell = fm(v as number | null, col.int);
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
