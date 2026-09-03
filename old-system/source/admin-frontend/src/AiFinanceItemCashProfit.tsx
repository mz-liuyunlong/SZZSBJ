/**
 * AiFinanceItemCashProfit.tsx — AI财务 · 单品现金利润（2026-08-13 批12）
 * 口径：docs/单品现金利润页_取值口径定稿_v1.md + 需求方三项拍板
 *   ①主维度自然月区间（起止月多选）②主币 CNY 默认、可切 USD（仿领星原币种下拉）③早期评估区页底过渡
 * UI_STANDARDS：§1 工具条 §5 列宽拖动 §7 表头ⓘ §8 总计吸底+表头吸顶+翻页 §9 #/finance/item-cash-profit
 * 记账规则（帮助文详载）：切点 2026-05-01；期初=WFS快照×一刀价；切点前采购/头程现金不计；
 *   期初池按月FIFO消耗防双算；海外仓不计、惠州仓只进资产KPI。
 */
import { useEffect, useMemo, useRef, useState } from "react";
import { lxTB, IconRefresh, IconHelp, IconDownload } from "./LxToolbar";

interface Cell { c: number; u: number }
interface Row {
  store_id: string; store_name: string; sku: string;
  sale: Cell; refund: Cell; comp: Cell; wfs_fee: Cell; other_item: Cell;
  ads: Cell; storage: Cell; inbound: Cell; purchase: Cell; firstmile: Cell; opening_cost: Cell;
  sold_qty: number; opening_used_qty: number;
  revenue: Cell; expense: Cell; profit: Cell;
  mskus?: string[]; item_ids?: string[];
}
interface StoreRow { store_id: string; store_name: string; sem: Cell; review: Cell; comp: Cell; other: Cell; ads_unmapped: Cell; purchase_unmapped: Cell; unmapped_cnt: number }
interface EarlyRow { sku: string; revenue_usd: number; sold_qty: number; cost_cny: number | null }
interface Sentinel { name: string; expect: number; actual: number; diff: number; ok: boolean; note: string }
interface Resp {
  from: string; to: string; cutoff: string;
  kpi: { opening_value: number; pool_remain_qty: number; pool_remain_value: number; huizhou_value: number; huizhou_qty: number; profit_cny: number; profit_usd: number };
  rows: Row[]; store_rows: StoreRow[]; early: EarlyRow[]; early_store_level_usd: number;
  sentinels: Sentinel[]; fx_missing: string[]; excluded_note: string; error?: string;
}
interface StoreOpt { store_id: string; store_name: string }

const C = { blue: "#1a73e8", txt2: "#5f6368", txt3: "#9aa0a6", line: "#dadce0", neg: "#d93025", green: "#188038", amber: "#b06f00" };
const card: React.CSSProperties = { background: "#fff", border: "1px solid #e5e7eb", borderRadius: "10px" };
const inp: React.CSSProperties = { padding: "6px 10px", borderRadius: "6px", border: "1px solid #d1d5db", fontSize: "12px", boxSizing: "border-box" };
const iconBtnWrap: React.CSSProperties = { width: "30px", height: "30px", display: "inline-flex", alignItems: "center", justifyContent: "center", border: `1px solid ${C.line}`, borderRadius: "6px", background: "#fff", cursor: "pointer" };
const PAGE_SIZES = [50, 100, 200];
const pageBtn = (active: boolean, disabled: boolean): React.CSSProperties => ({ padding: "5px 12px", borderRadius: "5px", border: "1px solid #e5e7eb", cursor: disabled ? "not-allowed" : "pointer", background: active ? "#6366f1" : "#fff", color: active ? "#fff" : "#374151", fontWeight: active ? 700 : 400, fontSize: "13px", opacity: disabled ? 0.5 : 1 });

const COLS: { key: string; label: string; w: number; align: "left" | "right"; tip?: string }[] = [
  { key: "store_name", label: "店铺", w: 150, align: "left" },
  { key: "sku", label: "SKU", w: 100, align: "left" },
  { key: "msku", label: "MSKU", w: 130, align: "left", tip: "该 SKU 下的变体 MSKU（领星本地SKU→平台变体），最多展示12个" },
  { key: "item_id", label: "ITEM_ID", w: 120, align: "left", tip: "该 SKU 在本店铺的沃尔玛 ItemID（dim_product 映射），最多展示12个" },
  { key: "sold_qty", label: "销量", w: 74, align: "right", tip: "区间内结算销量（领星结算月度，store_id 已修复精度损坏）" },
  { key: "sale", label: "销售额", w: 100, align: "right", tip: "回款对账单 sale 类目净额，按账期止日归月" },
  { key: "refund", label: "退款", w: 90, align: "right", tip: "refund_keepit / return / seller_initiated 合计（负）" },
  { key: "comp", label: "赔付返还", w: 92, align: "right", tip: "丢失/找回/仓损/WFS费用退款/广告返还/NSS折扣/库存转移 净额±（账单多为店铺级无品，见下方店铺级表）" },
  { key: "revenue", label: "收入合计", w: 100, align: "right", tip: "销售额+退款+赔付返还" },
  { key: "wfs_fee", label: "WFS配送费", w: 96, align: "right", tip: "wfs_fulfillment（账单负号原样）" },
  { key: "ads", label: "广告费", w: 90, align: "right", tip: "SP/SB/SV 商品级实付合计（fact_ads_product_daily）；SEM 在店铺级行" },
  { key: "storage", label: "仓储费", w: 88, align: "right", tip: "仓储报告导入，账期起日归月" },
  { key: "inbound", label: "入库运输", w: 90, align: "right", tip: "货件级运费按已发货数分摊" },
  { key: "purchase", label: "采购现金", w: 96, align: "right", tip: "切点(2026-05-01)后采购单，下单日全额；切点前不计（一刀切）" },
  { key: "firstmile", label: "头程现金", w: 96, align: "right", tip: "切点后发货单实付头程按品分摊（含老货补入的发货）" },
  { key: "opening_cost", label: "期初消耗", w: 96, align: "right", tip: "期初池(05-01 WFS快照)按月FIFO：min(池余量,当月销量)×财务一刀价；耗尽即停防双算" },
  { key: "other_item", label: "其他按品", w: 92, align: "right", tip: "退货处理/弃置及未单列按品类目净额±（佣金已含在回款销售净额，不重复计）" },
  { key: "expense", label: "支出合计", w: 100, align: "right", tip: "WFS配送+广告+仓储+入库运输+采购+头程+期初消耗+其他按品（取扣费口径）" },
  { key: "profit", label: "现金利润", w: 104, align: "right", tip: "收入合计−支出合计" },
  { key: "opening_used_qty", label: "耗池量", w: 74, align: "right", tip: "本区间从期初池消耗的数量" },
];

const n2 = (v: unknown): number => { const n = Number(v); return Number.isFinite(n) ? n : 0; };

export default function AiFinanceItemCashProfit({ onNavigate }: { onNavigate?: (key: string) => void }) {
  const [data, setData] = useState<Resp | null>(null);
  const [loading, setLoading] = useState(false);
  const [msg, setMsg] = useState("");
  const [from, setFrom] = useState("2026-05");
  const [to, setTo] = useState(() => new Date().toISOString().slice(0, 7));
  const [storeId, setStoreId] = useState("");
  const [stores, setStores] = useState<StoreOpt[]>([]);
  const [cur, setCur] = useState<"CNY" | "USD">("CNY"); // 需求方：默认CNY，可切USD
  const [pageSize, setPageSize] = useState(50);
  const [page, setPage] = useState(1);
  const [colWidths, setColWidths] = useState<Record<string, number>>({});
  const [kpiHidden, setKpiHidden] = useState(false);
  const resizeRef = useRef<{ col: string; startX: number; startW: number } | null>(null);

  useEffect(() => {
    if (document.getElementById("lx-colresize-css")) return;
    const st = document.createElement("style"); st.id = "lx-colresize-css";
    st.textContent = `.lx-colresize{position:absolute;right:-4px;top:0;bottom:0;width:8px;cursor:col-resize;z-index:6}
      .lxfin-info{display:inline-block;margin-left:3px;width:13px;height:13px;line-height:13px;border-radius:50%;background:#e8eaed;color:#5f6368;font-size:9px;font-style:normal;text-align:center;cursor:help;position:relative}
      .lxfin-info .lxfin-tip{display:none;position:absolute;z-index:30;top:16px;left:50%;transform:translateX(-50%);background:#202124;color:#fff;font-size:11px;font-weight:400;line-height:1.5;padding:7px 10px;border-radius:6px;width:230px;white-space:normal;text-align:left}
      .lxfin-info:hover .lxfin-tip{display:block}`;
    document.head.appendChild(st);
  }, []);
  useEffect(() => {
    const mv = (e: MouseEvent): void => {
      const r = resizeRef.current; if (!r) return;
      setColWidths((p) => ({ ...p, [r.col]: Math.max(56, r.startW + e.clientX - r.startX) }));
    };
    const up = (): void => { resizeRef.current = null; document.body.style.cursor = ""; };
    window.addEventListener("mousemove", mv); window.addEventListener("mouseup", up);
    return () => { window.removeEventListener("mousemove", mv); window.removeEventListener("mouseup", up); };
  }, []);

  const load = async (): Promise<void> => {
    setLoading(true);
    try {
      const r = await fetch(`/api/finance/item-cash-profit?from=${from}&to=${to}&store_id=${encodeURIComponent(storeId)}`, { credentials: "include" });
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
  const cols = COLS;
  const tableW = cols.reduce((a, c) => a + (colWidths[c.key] ?? c.w), 0);
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
        if (c.key === "sku") return r.sku;
        if (c.key === "msku") return (r.mskus ?? []).join("|");
        if (c.key === "item_id") return (r.item_ids ?? []).join("|");
        if (c.key === "sold_qty") return r.sold_qty;
        if (c.key === "opening_used_qty") return r.opening_used_qty;
        return V(r[c.key as keyof Row] as Cell);
      }));
    }
    const csv = "﻿" + dataRows.map((row) => row.map((v) => `"${String(v).replace(/"/g, '""')}"`).join(",")).join("\n");
    const a = document.createElement("a");
    a.href = URL.createObjectURL(new Blob([csv], { type: "text/csv;charset=utf-8" }));
    a.download = `单品现金利润_${from}_${to}_${cur}.csv`;
    a.click(); URL.revokeObjectURL(a.href);
  };

  const cellStyle = (align: "left" | "right"): React.CSSProperties =>
    ({ textAlign: align, padding: "7px 10px", fontSize: "12px", borderTop: "1px solid #f3f4f6", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis", fontVariantNumeric: "tabular-nums" });
  const money = (v: number, opt?: { bold?: boolean; posGreen?: boolean }): React.ReactNode => (
    <span style={{ color: v < 0 ? C.neg : opt?.posGreen && v > 0 ? C.green : undefined, fontWeight: opt?.bold ? 700 : undefined }}>{fmt(v)}</span>
  );
  const cell = (r: Row, key: string): React.ReactNode => {
    switch (key) {
      case "store_name": return <span style={{ color: C.txt2 }}>{r.store_name}</span>;
      case "sku": return <b>{r.sku}</b>;
      case "msku": {
        const a = r.mskus ?? []; if (!a.length) return <span style={{ color: C.txt3 }}>—</span>;
        return <span style={{ color: C.txt2, fontSize: "11px" }} title={a.join("\n")}>{a.length > 2 ? `${a.slice(0, 2).join(", ")} +${a.length - 2}` : a.join(", ")}</span>;
      }
      case "item_id": {
        const a = r.item_ids ?? []; if (!a.length) return <span style={{ color: C.txt3 }}>—</span>;
        return <span style={{ color: C.txt2, fontSize: "11px" }} title={a.join("\n")}>{a.length > 2 ? `${a.slice(0, 2).join(", ")} +${a.length - 2}` : a.join(", ")}</span>;
      }
      case "sold_qty": return r.sold_qty || "—";
      case "opening_used_qty": return r.opening_used_qty || "—";
      case "revenue": return money(V(r.revenue), { bold: true });
      case "expense": return money(-Math.abs(V(r.expense)));
      case "profit": return money(V(r.profit), { bold: true, posGreen: true });
      case "ads": case "storage": case "inbound": case "purchase": case "firstmile": case "opening_cost": {
        const v = V(r[key as keyof Row] as Cell);
        return v ? money(-v) : <span style={{ color: C.txt3 }}>—</span>;
      }
      default: {
        const v = V(r[key as keyof Row] as Cell);
        return v ? money(v) : <span style={{ color: C.txt3 }}>—</span>;
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
        现金视角：钱袋子进出多少、压了多少。切点 <b>2026-05-01</b>；切点前采购/头程现金已压缩为期初（不重复计），
        老货按期初池 FIFO 消耗计成本。海外仓/Miami 虚拟库存不计；固定开支不进本表（财务口径见利润报表）。
      </p>

      {/* §1 工具条 */}
      <div style={{ ...lxTB.filterWrap, display: "flex", alignItems: "center", gap: "10px", flexWrap: "wrap" }}>
        <span style={{ fontSize: "13px", fontWeight: 700, color: "#374151" }}>💰 单品现金利润</span>
        <input type="month" min="2026-05" style={{ ...inp, width: "128px" }} value={from} onChange={(e) => setFrom(e.target.value)} />
        <span style={{ color: C.txt3 }}>~</span>
        <input type="month" min="2026-05" style={{ ...inp, width: "128px" }} value={to} onChange={(e) => setTo(e.target.value)} />
        <select style={{ ...inp, width: "190px" }} value={storeId} onChange={(e) => setStoreId(e.target.value)}>
          <option value="">全部店铺</option>
          {stores.map((s) => <option key={s.store_id} value={s.store_id}>{s.store_name}</option>)}
        </select>
        <select style={{ ...inp, width: "96px" }} value={cur} onChange={(e) => setCur(e.target.value as "CNY" | "USD")} title="展示币种（仿领星原币种；折算按上月领星「我的汇率」）">
          <option value="CNY">CNY ¥</option>
          <option value="USD">USD $</option>
        </select>
        <button style={{ ...inp, cursor: "pointer", background: C.blue, color: "#fff", border: `1px solid ${C.blue}`, fontWeight: 600 }} disabled={loading} onClick={() => void load()}>{loading ? "查询中…" : "查询"}</button>
        <span style={{ color: C.txt2, fontSize: "12px" }}>{data ? `${data.from}~${data.to} · 共 ${rows.length} 行 · 第 ${page}/${totalPages} 页` : ""}</span>
        <div style={{ flex: 1 }} />
        <button style={{ ...lxTB.iconBtn, ...iconBtnWrap }} title={kpiHidden ? "显示KPI" : "隐藏KPI"} onClick={() => setKpiHidden(!kpiHidden)}>{kpiHidden ? "▤" : "▦"}</button>
        <button style={{ ...lxTB.iconBtn, ...iconBtnWrap }} title="刷新" onClick={() => void load()} disabled={loading}><IconRefresh /></button>
        <button style={{ ...lxTB.iconBtn, ...iconBtnWrap }} title="帮助（取值口径/切点规则）" onClick={openHelp}><IconHelp /></button>
        <button style={{ ...lxTB.iconBtn, ...iconBtnWrap }} title="下载 CSV（当前币种）" onClick={exportCsv}><IconDownload /></button>
      </div>
      <div style={{ fontSize: "11px", color: C.txt3, margin: "-4px 0 10px" }}>
        拖列头右缘调列宽 · 折算=各归属月「上一个月」领星我的汇率（与领星摊费同源） ·
        <span style={{ color: C.blue, cursor: "pointer", marginLeft: "4px" }} onClick={() => setColWidths({})}>列宽重置</span>
        {data?.fx_missing?.length ? <span style={{ color: C.neg, marginLeft: "8px" }}>⚠️ 缺汇率月份：{data.fx_missing.join(", ")}</span> : null}
      </div>

      {msg && <div style={{ ...card, padding: "10px 14px", color: C.amber, marginBottom: "10px", border: "1px solid #f9ab00", background: "#fef7e0" }}>{msg}</div>}

      {/* §6 KPI（可隐藏） */}
      {!kpiHidden && kpi && (
        <div style={{ display: "flex", gap: "10px", flexWrap: "wrap", marginBottom: "12px" }}>
          {kpiCard("现金利润（区间）", cur === "CNY" ? `¥${kpi.profit_cny.toLocaleString("zh-CN")}` : `$${kpi.profit_usd.toLocaleString("zh-CN")}`)}
          {kpiCard("期初存货（05-01）", `¥${kpi.opening_value.toLocaleString("zh-CN")}`, "205 SKU × 财务一刀价")}
          {kpiCard("期初池余量", `¥${kpi.pool_remain_value.toLocaleString("zh-CN")}`, `${kpi.pool_remain_qty.toLocaleString("zh-CN")} 件（截至所选止月）`)}
          {kpiCard("惠州仓存货", `¥${kpi.huizhou_value.toLocaleString("zh-CN")}`, `${kpi.huizhou_qty.toLocaleString("zh-CN")} 件 · 批次价 · 国内仓计资产`)}
          <div style={{ ...card, padding: "10px 14px", background: "#fafafa" }}>
            <div style={{ fontSize: "11px", color: C.txt3 }}>不计入（口径）</div>
            <div style={{ fontSize: "11px", color: C.txt2, marginTop: "4px", lineHeight: 1.6 }}>{data?.excluded_note}</div>
          </div>
        </div>
      )}

      {/* 守恒哨兵 */}
      {data?.sentinels?.length ? (
        <div style={{ display: "flex", gap: "8px", flexWrap: "wrap", marginBottom: "10px" }}>
          {data.sentinels.map((s0) => (
            <span key={s0.name} title={`${s0.note}\n基准 ${s0.expect} vs 实际 ${s0.actual}（差 ${s0.diff}）`}
              style={{ fontSize: "11px", padding: "3px 10px", borderRadius: "12px", border: `1px solid ${s0.ok ? "#c6e7cf" : "#f4c7c3"}`, background: s0.ok ? "#e6f4ea" : "#fce8e6", color: s0.ok ? C.green : C.neg, cursor: "help" }}>
              {s0.ok ? "✓" : "✗"} {s0.name}{s0.ok ? "" : ` 差${s0.diff}`}
            </span>
          ))}
        </div>
      ) : null}

      {/* §8 主表 */}
      <div style={{ ...card, padding: 0, overflow: "auto", maxHeight: "58vh" }}>
        <table style={{ width: tableW, minWidth: "100%", borderCollapse: "collapse", tableLayout: "fixed" }}>
          <colgroup>{cols.map((c) => <col key={c.key} style={{ width: (colWidths[c.key] ?? c.w) + "px" }} />)}</colgroup>
          <thead>
            <tr>
              {cols.map((col) => (
                <th key={col.key}
                  style={{ position: "sticky", top: 0, zIndex: 5, textAlign: col.align, padding: "8px 10px", fontSize: "12px", color: C.txt2, background: "#f9fafb", whiteSpace: "nowrap", userSelect: "none", boxShadow: "inset 0 -1px 0 #e5e7eb" }}>
                  {col.label}
                  {col.tip && <i className="lxfin-info">i<span className="lxfin-tip">{col.tip}</span></i>}
                  <span className="lx-colresize" onMouseDown={(e) => startResize(e, col.key, e.currentTarget.parentElement as HTMLElement)} onClick={(e) => e.stopPropagation()} />
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {paged.map((r) => (
              <tr key={r.store_id + r.sku}>{cols.map((col) => <td key={col.key} style={cellStyle(col.align)}>{cell(r, col.key)}</td>)}</tr>
            ))}
            {!rows.length && !loading && (
              <tr><td style={{ ...cellStyle("left"), textAlign: "center", color: C.txt2, padding: "22px" }} colSpan={cols.length}>所选区间无数据</td></tr>
            )}
          </tbody>
          {rows.length > 0 && (
            <tfoot>
              <tr>
                {cols.map((col, i) => (
                  <td key={col.key} style={{ position: "sticky", bottom: 0, zIndex: 4, background: "#eef2ff", fontWeight: 700, color: "#3730a3", borderTop: "2px solid #c7d2fe", textAlign: col.align, padding: "8px 10px", fontSize: "12px", whiteSpace: "nowrap" }}>
                    {i === 0 ? `合计（${rows.length} 行）`
                      : col.key === "sku" || col.key === "msku" || col.key === "item_id" ? ""
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
        {PAGE_SIZES.map((n) => (
          <button key={n} style={pageBtn(pageSize === n, false)} onClick={() => { setPageSize(n); setPage(1); }}>{n}</button>
        ))}
        <div style={{ flex: 1 }} />
        <button style={pageBtn(false, page <= 1)} disabled={page <= 1} onClick={() => setPage(1)}>首页</button>
        <button style={pageBtn(false, page <= 1)} disabled={page <= 1} onClick={() => setPage(page - 1)}>上一页</button>
        <span style={{ fontSize: "12px", color: C.txt2 }}>{page}/{totalPages}</span>
        <button style={pageBtn(false, page >= totalPages)} disabled={page >= totalPages} onClick={() => setPage(page + 1)}>下一页</button>
        <button style={pageBtn(false, page >= totalPages)} disabled={page >= totalPages} onClick={() => setPage(totalPages)}>末页</button>
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
                  <td style={{ padding: "5px 8px", borderTop: "1px solid #f3f4f6", textAlign: "right" }}>{V(r.purchase_unmapped) ? money(-V(r.purchase_unmapped)) : <span style={{ color: C.txt3 }}>—</span>}</td>
                  <td style={{ padding: "5px 8px", borderTop: "1px solid #f3f4f6", textAlign: "right" }}>{money(V(r.other))}</td>
                  <td style={{ padding: "5px 8px", borderTop: "1px solid #f3f4f6", textAlign: "right", color: r.unmapped_cnt ? C.amber : C.txt3 }}>{r.unmapped_cnt || "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}

      {/* 早期评估区（页底过渡；需求方拍板） */}
      {data?.early?.length ? (
        <div style={{ ...card, padding: "12px 14px", marginBottom: "12px", background: "#fffdf7", border: "1px solid #f3e8c8" }}>
          <b style={{ fontSize: "13px" }}>🕰️ 早期评估区（2026-01 ~ 04 · 切点前 · 只读参考）</b>
          <span style={{ fontSize: "11px", color: C.txt3, marginLeft: "8px" }}>
            收入=回款实额(USD)；成本=财务一刀价×结算销量(CNY)；无一刀价显示—；店铺级净额 ${data.early_store_level_usd.toLocaleString("zh-CN")}
          </span>
          <table style={{ width: "100%", borderCollapse: "collapse", marginTop: "8px", fontSize: "12px" }}>
            <thead><tr>{["SKU", "回款净额(USD)", "销量", "一刀成本(CNY)", "评估差额ⓘ"].map((h) => (
              <th key={h} style={{ textAlign: h === "SKU" ? "left" : "right", padding: "5px 8px", color: C.txt2, background: "#faf6ea" }}>{h}</th>
            ))}</tr></thead>
            <tbody>
              {data.early.slice(0, 60).map((r) => (
                <tr key={r.sku}>
                  <td style={{ padding: "5px 8px", borderTop: "1px solid #f3ecd8" }}><b>{r.sku}</b></td>
                  <td style={{ padding: "5px 8px", borderTop: "1px solid #f3ecd8", textAlign: "right" }}>${r.revenue_usd.toFixed(2)}</td>
                  <td style={{ padding: "5px 8px", borderTop: "1px solid #f3ecd8", textAlign: "right" }}>{r.sold_qty || "—"}</td>
                  <td style={{ padding: "5px 8px", borderTop: "1px solid #f3ecd8", textAlign: "right" }}>{r.cost_cny === null ? <span style={{ color: C.amber }}>—（无一刀价）</span> : `¥${r.cost_cny.toFixed(2)}`}</td>
                  <td style={{ padding: "5px 8px", borderTop: "1px solid #f3ecd8", textAlign: "right", color: C.txt3 }} title="两币种未折算的粗评估：仅供判断早期盈亏方向">{r.cost_cny === null ? "—" : "参考"}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {data.early.length > 60 && <div style={{ fontSize: "11px", color: C.txt3, marginTop: "6px" }}>仅展示回款额前 60 个 SKU（共 {data.early.length} 个），完整数据用下载或 SQL。</div>}
        </div>
      ) : null}
    </div>
  );
}
