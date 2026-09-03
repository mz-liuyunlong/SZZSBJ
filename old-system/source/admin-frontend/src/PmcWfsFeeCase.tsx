/**
 * PmcWfsFeeCase.tsx — 智能PMC · WFS费用异常跟进（2026-08-12 v2，UI_STANDARDS 合规版）
 * §1 LxToolbar工具条+元信息(共N行·同步·第P/T页) · §2 帮助壳内(#/help?page=pmc-wfs-fee) ·
 * §5 列宽拖动(可见把手)+列宽重置+提示 · §6 KPI可隐藏(▤) · §7 表头ⓘ口径悬停 · §8 总计行吸底+翻页+表头吸顶。
 * 业务：判定=实收费率(结算)>人工配送费；抽屉=判定依据+Case号(必填可多个)+跟进日志(可编辑保存)+状态操作。
 */
import { useEffect, useMemo, useRef, useState } from "react";
import { lxTB, IconRefresh, IconHelp, IconDownload, IconColumns } from "./LxToolbar";
import { ItemIdLink } from "./ItemIdLink";

interface Row {
  id: number; store_id: string; store_name: string; item_id: string; msku: string; owner_name: string;
  manual_fee: string | number; actual_fee: string | number; total_units: number; est_recover: string | number;
  status: string; case_nos: string; reason: string; follow_log: string | null; log_updated_at: string | null;
  claim_amount: string | number | null; recovered_amount: string | number | null;
  decided_by: string; approved_by: string; approved_at: string | null; done_at: string | null;
  first_alert_at: string | null; remark: string; created_date: string; log_stale: number;
}
interface Kpi { waiting: number; following: number; approving: number; done: number; closed: number; est_open: number; recovered_total: number }
interface Me { display_name?: string; is_superadmin?: boolean }

const C = { blue: "#1a73e8", txt2: "#5f6368", txt3: "#9aa0a6", line: "#dadce0", neg: "#d93025", green: "#188038", amber: "#b06f00" };
const card: React.CSSProperties = { background: "#fff", border: "1px solid #e5e7eb", borderRadius: "10px" };
const iconBtnWrap: React.CSSProperties = { width: "30px", height: "30px", display: "inline-flex", alignItems: "center", justifyContent: "center", border: `1px solid ${C.line}`, borderRadius: "6px", background: "#fff", cursor: "pointer" };
const PAGE_SIZES = [50, 100, 200];
const pageBtn = (active: boolean, disabled: boolean): React.CSSProperties => ({ padding: "5px 12px", borderRadius: "5px", border: "1px solid #e5e7eb", cursor: disabled ? "not-allowed" : "pointer", background: active ? "#6366f1" : "#fff", color: active ? "#fff" : "#374151", fontWeight: active ? 700 : 400, fontSize: "13px", opacity: disabled ? 0.5 : 1 });
const ST_LABEL: Record<string, string> = { waiting: "待运营确认", following: "跟进中", approving: "待林翔审批", done: "已追回", closed: "已关闭(不追)" };
const ST_ORDER: Record<string, number> = { following: 0, waiting: 1, approving: 2, done: 3, closed: 4 };
const ST_CHIP: Record<string, React.CSSProperties> = {
  waiting: { background: "#fce8e6", color: "#d93025" }, following: { background: "#e8f0fe", color: "#1a73e8" },
  approving: { background: "#fef7e0", color: "#b06f00" }, done: { background: "#e6f4ea", color: "#188038" },
  closed: { background: "#f1f3f4", color: "#5f6368" },
};
const n2 = (v: unknown): number => { const n = Number(v); return Number.isFinite(n) ? n : 0; };
const fmt = (v: unknown): string => "$" + n2(v).toFixed(2);
const inp: React.CSSProperties = { padding: "6px 10px", borderRadius: "6px", border: "1px solid #d1d5db", fontSize: "12px", width: "100%", boxSizing: "border-box" };
const btn: React.CSSProperties = { padding: "6px 14px", borderRadius: "6px", border: "1px solid #d1d5db", background: "#fff", fontSize: "12px", cursor: "pointer" };

type ColKey = "prod" | "item" | "store" | "owner" | "created" | "manual" | "actual" | "diff" | "units" | "est" | "status" | "log" | "back";
const COLS: { key: ColKey; label: string; w: number; align: "left" | "right"; hideable: boolean; sortable: boolean; tip?: string }[] = [
  { key: "prod", label: "产品(MSKU)", w: 118, align: "left", hideable: false, sortable: false },
  { key: "item", label: "商品ID", w: 118, align: "left", hideable: true, sortable: false },
  { key: "store", label: "店铺", w: 140, align: "left", hideable: true, sortable: false },
  { key: "owner", label: "负责人", w: 80, align: "left", hideable: true, sortable: false },
  { key: "created", label: "立案时间", w: 92, align: "left", hideable: true, sortable: true },
  { key: "manual", label: "人工配送费", w: 92, align: "right", hideable: true, sortable: true, tip: "成本配置人工维护的WFS配送费（dim_product_cost_config.delivery_fee，店铺级优先）" },
  { key: "actual", label: "实收费率", w: 88, align: "right", hideable: true, sortable: true, tip: "Walmart结算真实扣费折算的单件费率（近60天逐单配对取众数，每周一刷新）" },
  { key: "diff", label: "单件差", w: 80, align: "right", hideable: true, sortable: true, tip: "实收费率 − 人工配送费；>0 即判定多收立案" },
  { key: "units", label: "累计销量", w: 84, align: "right", hideable: true, sortable: true, tip: "该店铺该MSKU全历史累计销量（fact_sales_daily，全部订单口径）" },
  { key: "est", label: "预估追回", w: 92, align: "right", hideable: true, sortable: true, tip: "单件差 × 累计销量（估算值；逐单精算二期）" },
  { key: "status", label: "状态", w: 116, align: "left", hideable: false, sortable: true },
  { key: "log", label: "跟进日志", w: 240, align: "left", hideable: true, sortable: false, tip: "最新一条跟进日志摘要；点 ✏️ 编辑（每周必写，未更新扣绩效）；Case号在编辑面板内填写" },
  { key: "back", label: "已追回", w: 84, align: "right", hideable: true, sortable: true, tip: "完成时填写的实际到账追回金额" },
];
const SORT_VAL: Record<string, (r: Row) => number | string> = {
  created: (r) => r.created_date, manual: (r) => n2(r.manual_fee), actual: (r) => n2(r.actual_fee),
  diff: (r) => n2(r.actual_fee) - n2(r.manual_fee), units: (r) => r.total_units, est: (r) => n2(r.est_recover),
  status: (r) => ST_ORDER[r.status] ?? 9, back: (r) => n2(r.recovered_amount),
};

export default function PmcWfsFeeCase({ onNavigate }: { onNavigate?: (key: string) => void }) {
  const [rows, setRows] = useState<Row[]>([]);
  const [kpi, setKpi] = useState<Kpi | null>(null);
  const [me, setMe] = useState<Me>({});
  const [kw, setKw] = useState("");
  const [fStatus, setFStatus] = useState("");
  const [syncedAt, setSyncedAt] = useState("");
  const [showKpi, setShowKpi] = useState(true);
  const [visible, setVisible] = useState<Set<ColKey>>(new Set(COLS.map((c) => c.key)));
  const [showColCfg, setShowColCfg] = useState(false);
  const [colWidths, setColWidths] = useState<Record<string, number>>({});
  const [sortKey, setSortKey] = useState<ColKey | "">("");
  const [sortDir, setSortDir] = useState<1 | -1>(-1);
  const [pageSize, setPageSize] = useState(50);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(false);
  const [msg, setMsg] = useState("");
  const [cur, setCur] = useState<Row | null>(null);
  const [caseIn, setCaseIn] = useState("");
  const [logIn, setLogIn] = useState("");
  const [amtIn, setAmtIn] = useState("");
  const [reasonIn, setReasonIn] = useState("");
  const resizeRef = useRef<{ col: string; startX: number; startW: number } | null>(null);

  // §5 列宽把手 CSS + §7 表头ⓘ气泡 CSS
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
    if (typeof document !== "undefined" && !document.getElementById("lxwfs-tip-css")) {
      const st = document.createElement("style");
      st.id = "lxwfs-tip-css";
      st.textContent =
        ".lxwfs-info{position:relative;display:inline-flex;align-items:center;justify-content:center;width:13px;height:13px;margin-left:3px;border:1px solid #9aa0a6;border-radius:50%;font-size:9px;color:#9aa0a6;cursor:help;font-style:normal;vertical-align:1px}" +
        ".lxwfs-info .lxwfs-tip{display:none;position:absolute;top:20px;left:50%;transform:translateX(-50%);background:#202124;color:#fff;font-size:11px;line-height:1.6;padding:8px 10px;border-radius:6px;width:230px;white-space:normal;z-index:30;text-align:left;font-weight:400}" +
        ".lxwfs-info .lxwfs-tip::before{content:'';position:absolute;top:-5px;left:50%;transform:translateX(-50%);border:5px solid transparent;border-top:none;border-bottom:5px solid #202124}" +
        ".lxwfs-info:hover .lxwfs-tip{display:block}" +
        ".lxwfs-row:hover td{background:#eef2ff;cursor:pointer}";
      document.head.appendChild(st);
    }
    const onMove = (e: MouseEvent): void => {
      const r = resizeRef.current; if (!r) return;
      setColWidths((prev) => ({ ...prev, [r.col]: Math.max(60, r.startW + (e.clientX - r.startX)) }));
    };
    const onUp = (): void => { resizeRef.current = null; document.body.style.cursor = ""; };
    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onUp);
    return () => { window.removeEventListener("mousemove", onMove); window.removeEventListener("mouseup", onUp); };
  }, []);

  const load = async (): Promise<void> => {
    setLoading(true);
    try {
      const r = await fetch("/api/pmc/wfs-fee/list", { credentials: "include" });
      const d = (await r.json()) as { rows?: Row[]; kpi?: Kpi; latest_sync_time?: string; error?: string };
      if (!r.ok) throw new Error(d.error ?? String(r.status));
      setRows(d.rows ?? []); setKpi(d.kpi ?? null);
      const t = d.latest_sync_time ? new Date(String(d.latest_sync_time).replace(" ", "T")) : null;
      setSyncedAt(t && !Number.isNaN(t.getTime()) ? t.toLocaleString("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" }) : new Date().toLocaleString("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" }));
    } catch (e) { setMsg("加载失败：" + (e instanceof Error ? e.message : String(e))); }
    finally { setLoading(false); }
  };
  useEffect(() => { void load(); /* eslint-disable-next-line */ }, []);
  useEffect(() => {
    void fetch("/api/auth/me", { credentials: "include" }).then((r) => (r.ok ? r.json() : null))
      .then((d) => { if (d) setMe(d as Me); }).catch(() => undefined);
  }, []);
  useEffect(() => { if (!msg) return; const t = setTimeout(() => setMsg(""), 3800); return () => clearTimeout(t); }, [msg]);

  const meName = String(me.display_name ?? "").trim();
  const isSuper = !!me.is_superadmin;
  const isApprover = isSuper || meName === "林翔";
  const canOperate = (r: Row): boolean => isSuper || (!!meName && meName === r.owner_name);

  const view = useMemo(() => {
    let out = rows.slice();
    if (fStatus) out = out.filter((r) => r.status === fStatus);
    const q = kw.trim().toLowerCase();
    if (q) out = out.filter((r) => r.msku.toLowerCase().includes(q) || r.item_id.includes(q) || r.owner_name.includes(kw.trim()) || (r.case_nos ?? "").includes(kw.trim()) || (r.store_name ?? "").toLowerCase().includes(q));
    if (sortKey && SORT_VAL[sortKey]) {
      const f = SORT_VAL[sortKey];
      out.sort((a, b) => { const av = f(a), bv = f(b); return (av < bv ? -1 : av > bv ? 1 : 0) * sortDir; });
    } else {
      out.sort((a, b) => (ST_ORDER[a.status] ?? 9) - (ST_ORDER[b.status] ?? 9) || a.created_date.localeCompare(b.created_date));
    }
    return out;
  }, [rows, fStatus, kw, sortKey, sortDir]);

  const totalPages = Math.max(1, Math.ceil(view.length / pageSize));
  useEffect(() => { setPage(1); }, [fStatus, kw, sortKey, sortDir, pageSize]);
  useEffect(() => { if (page > totalPages) setPage(totalPages); }, [page, totalPages]);
  const paged = view.slice((page - 1) * pageSize, page * pageSize);
  const totals = useMemo(() => view.reduce((t, r) => ({
    units: t.units + r.total_units, est: t.est + n2(r.est_recover), back: t.back + n2(r.recovered_amount),
  }), { units: 0, est: 0, back: 0 }), [view]);

  const cols = COLS.filter((c) => visible.has(c.key));
  const tableW = cols.reduce((a, c) => a + (colWidths[c.key] ?? c.w), 0);
  const startResize = (e: React.MouseEvent, key: string, th: HTMLElement): void => {
    e.preventDefault(); e.stopPropagation();
    resizeRef.current = { col: key, startX: e.clientX, startW: th.getBoundingClientRect().width };
    document.body.style.cursor = "col-resize";
  };
  const onSort = (col: typeof COLS[number]): void => {
    if (!col.sortable) return;
    if (sortKey === col.key) setSortDir((d) => (d === 1 ? -1 : 1));
    else { setSortKey(col.key); setSortDir(-1); }
  };
  const openHelp = (): void => {
    onNavigate?.("help");
    try { window.location.hash = "#/help?page=pmc-wfs-fee"; } catch { /* noop */ }
  };
  const exportCsv = (): void => {
    const header = ["MSKU", "ItemID", "店铺", "负责人", "立案时间", "人工配送费", "实收费率", "单件差", "累计销量", "预估追回", "状态", "Case号", "索赔", "已追回", "跟进日志"];
    const data: (string | number)[][] = [header];
    for (const r of view) data.push([r.msku, r.item_id, r.store_name || r.store_id, r.owner_name, r.created_date, n2(r.manual_fee), n2(r.actual_fee), Math.round((n2(r.actual_fee) - n2(r.manual_fee)) * 100) / 100, r.total_units, n2(r.est_recover), ST_LABEL[r.status] ?? r.status, r.case_nos, n2(r.claim_amount), n2(r.recovered_amount), (r.follow_log ?? "").replace(/\n/g, " / ")]);
    const csv = "﻿" + data.map((row) => row.map((v) => `"${String(v).replace(/"/g, '""')}"`).join(",")).join("\n");
    const a = document.createElement("a");
    a.href = URL.createObjectURL(new Blob([csv], { type: "text/csv;charset=utf-8" }));
    a.download = `WFS费用异常跟进_${syncedAt || "export"}.csv`;
    a.click(); URL.revokeObjectURL(a.href);
  };

  const post = async (body: Record<string, unknown>): Promise<boolean> => {
    try {
      const r = await fetch("/api/pmc/wfs-fee/update", {
        method: "POST", credentials: "include", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
      });
      const d = (await r.json()) as { ok?: boolean; error?: string };
      if (!r.ok || !d.ok) { setMsg(d.error ?? "操作失败"); return false; }
      return true;
    } catch (e) { setMsg("请求失败：" + (e instanceof Error ? e.message : String(e))); return false; }
  };
  const openDrawer = (r: Row): void => { setCur(r); setCaseIn(r.case_nos ?? ""); setLogIn(r.follow_log ?? ""); setAmtIn(""); setReasonIn(""); };
  const refreshCur = async (): Promise<void> => {
    const r2 = await fetch("/api/pmc/wfs-fee/list", { credentials: "include" });
    const d = (await r2.json()) as { rows?: Row[]; kpi?: Kpi };
    setRows(d.rows ?? []); setKpi(d.kpi ?? null);
    if (cur) {
      const nr = (d.rows ?? []).find((x) => x.id === cur.id) ?? null;
      setCur(nr); if (nr) { setCaseIn(nr.case_nos ?? ""); setLogIn(nr.follow_log ?? ""); }
    }
  };
  const act = async (action: string, extra?: Record<string, unknown>): Promise<void> => {
    if (!cur) return;
    if (await post({ id: cur.id, action, ...(extra ?? {}) })) {
      const ok: Record<string, string> = {
        follow: "已转跟进中，请每周写跟进日志", nofollow: "已提交林翔审批", giveup: "已提交林翔审批",
        done: "已闭环 🎉", approve: "已同意关闭", reject: "已驳回，转回跟进中", save_cases: "Case号已保存", save_log: "跟进日志已保存",
      };
      setMsg(ok[action] ?? "已保存");
      await refreshCur();
    }
  };
  const doDone = async (): Promise<void> => {
    const m = amtIn.match(/([\d.]+)\s*[\/｜| ]\s*([\d.]+)/);
    if (!m) { setMsg("完成时填写：索赔金额/追回金额，如 544.16/544.16"); return; }
    await act("done", { claim_amount: Number(m[1]), recovered_amount: Number(m[2]) });
  };

  const kpiCards = kpi ? [
    { lbl: "待运营确认", val: String(kpi.waiting), bg: "#fce8e6", fg: C.neg, k: "waiting" },
    { lbl: "跟进中", val: String(kpi.following), bg: "#e8f0fe", fg: C.blue, k: "following" },
    { lbl: "待林翔审批", val: String(kpi.approving), bg: "#fef7e0", fg: C.amber, k: "approving" },
    { lbl: "预估追回(未闭环)", val: fmt(kpi.est_open), bg: "#fce8e6", fg: C.neg, k: "" },
    { lbl: "累计追回", val: fmt(kpi.recovered_total), bg: "#e6f4ea", fg: C.green, k: "done" },
  ] : [];

  const cellStyle = (align: "left" | "right", extra?: React.CSSProperties): React.CSSProperties =>
    ({ textAlign: align, padding: "7px 10px", fontSize: "12px", borderTop: "1px solid #f3f4f6", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis", fontVariantNumeric: "tabular-nums", ...extra });
  const cellOf = (r: Row, col: ColKey): React.ReactNode => {
    switch (col) {
      case "prod": return <b>{r.msku}</b>;
      case "item": return r.item_id ? <ItemIdLink itemId={r.item_id} /> : "—";
      case "store": return <span style={{ color: C.txt2 }}>{r.store_name || r.store_id}</span>;
      case "owner": return <span style={{ color: C.txt2 }}>{r.owner_name || "—"}</span>;
      case "created": return r.created_date;
      case "manual": return fmt(r.manual_fee);
      case "actual": return fmt(r.actual_fee);
      case "diff": return <span style={{ color: C.neg, fontWeight: 600 }}>+{fmt(n2(r.actual_fee) - n2(r.manual_fee))}</span>;
      case "units": return r.total_units.toLocaleString();
      case "est": return <span style={{ color: C.neg, fontWeight: 600 }}>{fmt(r.est_recover)}</span>;
      case "status": return (<>
        <span style={{ padding: "2px 10px", borderRadius: "12px", fontSize: "12px", ...(ST_CHIP[r.status] ?? {}) }}>{ST_LABEL[r.status] ?? r.status}</span>
        {Number(r.log_stale) === 1 && <div style={{ color: C.neg, fontSize: "11px" }}>⚠ 本周日志未更新</div>}
      </>);
      case "log": {
        const lines = String(r.follow_log ?? "").split("\n").map((x) => x.trim()).filter(Boolean);
        const last = lines.length ? lines[lines.length - 1] : "";
        return (
          <span style={{ display: "inline-flex", alignItems: "center", gap: "6px", maxWidth: "100%" }}>
            <button style={{ padding: "2px 8px", borderRadius: "5px", border: `1px solid ${C.blue}`, background: "#fff", color: C.blue, fontSize: "11px", cursor: "pointer", flexShrink: 0 }}
              onClick={(e) => { e.stopPropagation(); openDrawer(r); }}>✏️ {last ? "编辑" : "写日志"}</button>
            <span style={{ overflow: "hidden", textOverflow: "ellipsis", color: last ? undefined : C.txt3 }} title={String(r.follow_log ?? "")}>{last || "（未写）"}</span>
          </span>
        );
      }
      case "back": return r.recovered_amount != null && n2(r.recovered_amount) > 0 ? <span style={{ color: C.green }}>{fmt(r.recovered_amount)}</span> : "—";
    }
  };

  return (
    <div>
      <p style={{ color: C.txt2, margin: "0 0 12px", fontSize: "12px", lineHeight: 1.6 }}>
        判定：实收费率（Walmart 结算真实扣费，每周一刷新）&gt; 人工配送费（成本配置）即多收立案，全部订单口径；预估追回=单件差×累计销量。
        流程：卡片/页面确认「需要跟进」（Case号必填）→ 每周写跟进日志（未更新扣绩效）→ 退款到账点完成；「无需跟进/放弃」送林翔审批。
      </p>

      {/* §1 标准工具条 */}
      <div style={{ ...lxTB.filterWrap, display: "flex", alignItems: "center", gap: "10px", flexWrap: "wrap" }}>
        <select value={fStatus} onChange={(e) => setFStatus(e.target.value)} style={{ ...lxTB.filterInput, width: "130px" }}>
          <option value="">全部状态</option>
          {Object.entries(ST_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
        </select>
        <input placeholder="搜索 MSKU / ItemID / 店铺 / 负责人 / Case号…" value={kw} onChange={(e) => setKw(e.target.value)}
          style={{ ...lxTB.filterInput, width: "250px" }} />
        <span style={{ color: C.txt2, fontSize: "12px" }}>共 {view.length} 行 · 同步 {syncedAt || "-"} · 第 {page}/{totalPages} 页</span>
        <div style={{ flex: 1 }} />
        <button style={iconBtnWrap} title="隐藏 / 显示 顶部KPI" onClick={() => setShowKpi((v) => !v)}><span style={{ color: C.txt2, fontSize: "14px" }}>▤</span></button>
        <button style={{ ...lxTB.iconBtn, ...iconBtnWrap }} title="刷新" onClick={() => void load()} disabled={loading}><IconRefresh /></button>
        <button style={{ ...lxTB.iconBtn, ...iconBtnWrap }} title="帮助（开Case教程/日志写法）" onClick={openHelp}><IconHelp /></button>
        <button style={{ ...lxTB.iconBtn, ...iconBtnWrap }} title="下载 CSV（当前筛选）" onClick={exportCsv}><IconDownload /></button>
        <button style={{ ...lxTB.iconBtn, ...iconBtnWrap }} title="列配置" onClick={() => setShowColCfg(true)}><IconColumns /></button>
      </div>

      <div style={{ fontSize: "11px", color: C.txt3, margin: "-4px 0 10px" }}>
        拖列头右缘调列宽 · 点值列表头排序（↑↓⇅）· ▤ 收起顶部KPI · 行点击查看/操作 · 默认排序：跟进中最前·按立案时间从旧到新 ·
        <span style={{ color: C.blue, cursor: "pointer", marginLeft: "4px" }} onClick={() => setColWidths({})}>列宽重置</span>
      </div>

      {/* §6 KPI 可隐藏 */}
      {showKpi && kpiCards.length > 0 && (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(150px, 1fr))", gap: "10px", marginBottom: "12px" }}>
          {kpiCards.map((k) => (
            <div key={k.lbl} onClick={() => setFStatus(fStatus === k.k && k.k ? "" : k.k)}
              style={{ background: k.bg, borderRadius: "10px", padding: "10px 12px", cursor: k.k ? "pointer" : "default", outline: fStatus === k.k && k.k ? `2px solid ${C.blue}` : "none" }}>
              <div style={{ fontSize: "12px", color: k.fg }}>{k.lbl}</div>
              <div style={{ fontSize: "22px", fontWeight: 700, color: k.fg }}>{k.val}</div>
            </div>
          ))}
        </div>
      )}

      {msg && <div style={{ ...card, padding: "10px 14px", color: C.amber, marginBottom: "10px", border: "1px solid #f9ab00", background: "#fef7e0" }}>{msg}</div>}

      {/* 列配置弹窗 */}
      {showColCfg && (
        <div style={{ position: "fixed", inset: 0, background: "rgba(15,23,42,0.4)", zIndex: 1000, display: "flex", alignItems: "center", justifyContent: "center" }} onClick={() => setShowColCfg(false)}>
          <div style={{ background: "#fff", borderRadius: "12px", width: "320px", padding: "14px 16px", boxShadow: "0 8px 32px rgba(0,0,0,0.18)" }} onClick={(e) => e.stopPropagation()}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "10px" }}>
              <span style={{ fontSize: "14px", fontWeight: 700, color: "#374151" }}>列配置</span>
              <button onClick={() => setShowColCfg(false)} style={{ border: "none", background: "none", fontSize: "18px", cursor: "pointer", color: "#9ca3af" }}>×</button>
            </div>
            {COLS.map((col) => (
              <label key={col.key} style={{ display: "flex", alignItems: "center", gap: "8px", padding: "5px 0", cursor: col.hideable ? "pointer" : "not-allowed", fontSize: "13px", opacity: col.hideable ? 1 : 0.5 }}>
                <input type="checkbox" checked={visible.has(col.key)} disabled={!col.hideable}
                  onChange={() => setVisible((prev) => { const s = new Set(prev); s.has(col.key) ? s.delete(col.key) : s.add(col.key); return s; })} />
                <span style={{ color: "#374151" }}>{col.label}</span>
              </label>
            ))}
            <div style={{ display: "flex", gap: "8px", justifyContent: "flex-end", marginTop: "10px" }}>
              <button style={lxTB.resetBtn} onClick={() => setVisible(new Set(COLS.map((c) => c.key)))}>全选</button>
              <button style={lxTB.searchBtn} onClick={() => setShowColCfg(false)}>完成</button>
            </div>
          </div>
        </div>
      )}

      {/* §8 表格：表头吸顶 + 总计吸底 */}
      <div style={{ ...card, padding: 0, overflow: "auto", maxHeight: "62vh" }}>
        <table style={{ width: tableW, minWidth: "100%", borderCollapse: "collapse", tableLayout: "fixed" }}>
          <colgroup>{cols.map((c) => <col key={c.key} style={{ width: (colWidths[c.key] ?? c.w) + "px" }} />)}</colgroup>
          <thead>
            <tr>
              {cols.map((col) => {
                const active = col.sortable && sortKey === col.key;
                return (
                  <th key={col.key} onClick={() => onSort(col)}
                    style={{ position: "sticky", top: 0, zIndex: 5, textAlign: col.align, padding: "8px 10px", fontSize: "12px", color: C.txt2, background: "#f9fafb", whiteSpace: "nowrap", cursor: col.sortable ? "pointer" : "default", userSelect: "none", boxShadow: "inset 0 -1px 0 #e5e7eb" }}>
                    {col.label}
                    {col.tip && <i className="lxwfs-info" onClick={(e) => e.stopPropagation()}>i<span className="lxwfs-tip">{col.tip}</span></i>}
                    {col.sortable && <span style={{ color: active ? C.blue : "#c7cbd4", marginLeft: "3px" }}>{active ? (sortDir === 1 ? "↑" : "↓") : "⇅"}</span>}
                    <span className="lx-colresize" onMouseDown={(e) => startResize(e, col.key, e.currentTarget.parentElement as HTMLElement)} onClick={(e) => e.stopPropagation()} />
                  </th>
                );
              })}
            </tr>
          </thead>
          <tbody>
            {paged.map((r) => (
              <tr key={r.id} className="lxwfs-row" onClick={() => openDrawer(r)}>
                {cols.map((col) => <td key={col.key} style={cellStyle(col.align)}>{cellOf(r, col.key)}</td>)}
              </tr>
            ))}
            {!view.length && !loading && <tr><td style={{ ...cellStyle("left"), textAlign: "center", color: C.txt2, padding: "22px" }} colSpan={cols.length}>无数据</td></tr>}
          </tbody>
          {view.length > 0 && (
            <tfoot>
              <tr>
                {cols.map((col) => (
                  <td key={col.key} style={{ position: "sticky", bottom: 0, zIndex: 4, background: "#eef2ff", fontWeight: 700, color: "#3730a3", borderTop: "2px solid #c7d2fe", textAlign: col.align, padding: "8px 10px", fontSize: "12px", whiteSpace: "nowrap", fontVariantNumeric: "tabular-nums" }}>
                    {col.key === "prod" ? `总计（${view.length} 行）`
                      : col.key === "units" ? totals.units.toLocaleString()
                      : col.key === "est" ? fmt(totals.est)
                      : col.key === "back" ? fmt(totals.back)
                      : ""}
                  </td>
                ))}
              </tr>
            </tfoot>
          )}
        </table>
      </div>

      {/* §8.2 翻页控件 */}
      <div style={{ display: "flex", alignItems: "center", gap: "6px", flexWrap: "wrap", marginTop: "10px" }}>
        <span style={{ fontSize: "12px", color: C.txt2 }}>每页</span>
        {PAGE_SIZES.map((ps) => <button key={ps} style={pageBtn(pageSize === ps, false)} onClick={() => { setPageSize(ps); setPage(1); }}>{ps}</button>)}
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
        <span style={{ fontSize: "12px", color: C.txt3 }}>共 {view.length} 条</span>
        <span style={{ fontSize: "12px", color: C.txt3 }}>跳至</span>
        <input type="number" min={1} max={totalPages} defaultValue={page} style={{ ...lxTB.filterInput, width: "60px", padding: "4px 8px" }}
          onKeyDown={(e) => { if (e.key === "Enter") { const v = Number((e.target as HTMLInputElement).value); if (v >= 1 && v <= totalPages) setPage(v); } }} />
        <span style={{ fontSize: "12px", color: C.txt3 }}>页</span>
      </div>

      {/* 案件抽屉 */}
      {cur && (
        <>
          <div onClick={() => setCur(null)} style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,.35)", zIndex: 900 }} />
          <div style={{ position: "fixed", top: 0, right: 0, width: "580px", maxWidth: "92vw", height: "100%", background: "#fff", zIndex: 910, boxShadow: "-2px 0 12px rgba(0,0,0,.15)", display: "flex", flexDirection: "column" }}>
            <div style={{ padding: "14px 18px", borderBottom: "1px solid #e5e7eb", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <b style={{ fontSize: "15px" }}>{cur.msku} · WFS费用异常跟进</b>
              <button style={{ ...btn, border: "none" }} onClick={() => setCur(null)}>✕</button>
            </div>
            <div style={{ padding: "14px 18px", overflowY: "auto", flex: 1 }}>
              <div style={{ marginBottom: "14px", fontSize: "12px", display: "grid", gridTemplateColumns: "1fr 1fr", gap: "4px 16px" }}>
                <div>状态：<span style={{ padding: "2px 10px", borderRadius: "12px", ...(ST_CHIP[cur.status] ?? {}) }}>{ST_LABEL[cur.status] ?? cur.status}</span></div>
                <div>负责人：{cur.owner_name || "—"}</div>
                <div>立案时间：{cur.created_date}</div>
                <div>索赔/追回：{cur.claim_amount != null ? fmt(cur.claim_amount) : "—"} / {cur.recovered_amount != null ? fmt(cur.recovered_amount) : "—"}</div>
                {cur.decided_by && <div>操作人：{cur.decided_by}</div>}
                {cur.approved_by && <div>审批：{cur.approved_by}</div>}
              </div>
              <div style={{ background: "#f8f9fa", border: "1px solid #e5e7eb", borderRadius: "6px", padding: "10px", fontSize: "12px", lineHeight: 1.8, marginBottom: "14px" }}>
                <b>判定依据（系统只读，全部订单口径）</b><br />
                人工WFS配送费（成本配置）：<b>{fmt(cur.manual_fee)}</b>／件 ｜ 实收费率（Walmart结算众数）：<b style={{ color: C.neg }}>{fmt(cur.actual_fee)}</b>／件<br />
                单件多收 <b style={{ color: C.neg }}>+{fmt(n2(cur.actual_fee) - n2(cur.manual_fee))}</b> × 累计 {cur.total_units} 件 = 预估追回 <b style={{ color: C.neg }}>{fmt(cur.est_recover)}</b>
              </div>
              <div style={{ marginBottom: "14px" }}>
                <b style={{ fontSize: "13px" }}>Case号（必填，可多个，逗号分隔）</b>
                <input style={{ ...inp, marginTop: "6px" }} placeholder="如 250809-018876, 250810-022310" value={caseIn}
                  onChange={(e) => setCaseIn(e.target.value)} disabled={!canOperate(cur) || ["done", "closed"].includes(cur.status)} />
                {canOperate(cur) && !["done", "closed"].includes(cur.status) && cur.status !== "waiting" && (
                  <button style={{ ...btn, marginTop: "6px" }} onClick={() => void act("save_cases", { case_nos: caseIn })}>保存Case号</button>
                )}
              </div>
              {cur.reason && <div style={{ marginBottom: "14px", fontSize: "12px" }}><b>不跟进/放弃理由：</b>{cur.reason}</div>}
              <div style={{ marginBottom: "14px" }}>
                <b style={{ fontSize: "13px" }}>跟进日志（每周必写，未更新扣绩效；可编辑，改完点保存；写法见帮助中心）</b>
                <textarea style={{ ...inp, marginTop: "6px", minHeight: "170px", background: "#fffdf5", lineHeight: 1.8, resize: "vertical", fontFamily: "inherit" }}
                  placeholder={"模板(不符合不给保存)：MM-DD HH:MM 第N次跟进：做了什么/Walmart说了什么；下一步：xxx\n例：08-12 14:30 第2次跟进：Walmart要求补实测尺寸照片，已上传3张；下一步：等答复，08-19复查"}
                  value={logIn} onChange={(e) => setLogIn(e.target.value)} readOnly={!canOperate(cur)} />
                {canOperate(cur) && (
                  <span style={{ display: "inline-flex", gap: "8px", marginTop: "6px" }}>
                    <button style={{ ...btn }} onClick={() => {
                      const d = new Date();
                      const p2 = (n: number): string => String(n).padStart(2, "0");
                      const nth = logIn.split("\n").filter((x) => /第\d+次跟进/.test(x)).length + 1;
                      setLogIn((v) => (v ? v.replace(/\n*$/, "\n") : "") + `${p2(d.getMonth() + 1)}-${p2(d.getDate())} ${p2(d.getHours())}:${p2(d.getMinutes())} 第${nth}次跟进：`);
                    }}>＋插入模板行</button>
                    <button style={{ ...btn, background: C.blue, color: "#fff", border: `1px solid ${C.blue}` }} onClick={() => void act("save_log", { follow_log: logIn })}>保存日志</button>
                  </span>
                )}
                {cur.log_updated_at && <span style={{ fontSize: "11px", color: C.txt2, marginLeft: "8px" }}>上次保存：{String(cur.log_updated_at).replace("T", " ").slice(0, 16)}</span>}
              </div>
              <div style={{ marginBottom: "14px" }}>
                <b style={{ fontSize: "13px" }}>状态操作</b>
                <div style={{ display: "flex", gap: "8px", marginTop: "8px", flexWrap: "wrap", alignItems: "center" }}>
                  {canOperate(cur) && cur.status === "waiting" && (
                    <>
                      <button style={{ ...btn, background: C.blue, color: "#fff", border: `1px solid ${C.blue}` }} onClick={() => void act("follow", { case_nos: caseIn })}>✅ 需要跟进（Case号必填）</button>
                      <button style={{ ...btn, color: C.neg, border: `1px solid ${C.neg}` }} onClick={() => void act("nofollow", { reason: reasonIn })}>🚫 无需跟进（送林翔审批）</button>
                    </>
                  )}
                  {canOperate(cur) && cur.status === "following" && (
                    <>
                      <input style={{ ...inp, width: "220px" }} placeholder="完成：索赔/追回 如 544.16/544.16" value={amtIn} onChange={(e) => setAmtIn(e.target.value)} />
                      <button style={{ ...btn, background: C.green, color: "#fff", border: `1px solid ${C.green}` }} onClick={() => void doDone()}>✔ 完成</button>
                      <button style={{ ...btn, color: C.neg, border: `1px solid ${C.neg}` }} onClick={() => void act("giveup", { reason: reasonIn })}>放弃跟进（送审批）</button>
                    </>
                  )}
                  {isApprover && cur.status === "approving" && (
                    <>
                      <button style={{ ...btn, background: C.green, color: "#fff", border: `1px solid ${C.green}` }} onClick={() => void act("approve")}>✅ 同意关闭（不追）</button>
                      <button style={{ ...btn, color: C.neg, border: `1px solid ${C.neg}` }} onClick={() => void act("reject")}>↩️ 驳回（须跟进）</button>
                    </>
                  )}
                  {!canOperate(cur) && !(isApprover && cur.status === "approving") && (
                    <span style={{ fontSize: "11px", color: C.txt2 }}>仅负责人（{cur.owner_name || "未分配"}）或超管可操作此案</span>
                  )}
                </div>
                {(cur.status === "waiting" || cur.status === "following") && canOperate(cur) && (
                  <input style={{ ...inp, marginTop: "8px" }} placeholder="（可选）无需跟进/放弃的理由备注" value={reasonIn} onChange={(e) => setReasonIn(e.target.value)} />
                )}
                <div style={{ fontSize: "11px", color: C.txt2, marginTop: "6px" }}>无需跟进/放弃点击即送林翔审批（理由可选）；完成时填索赔/追回金额；人工列系统永不覆盖。</div>
              </div>
              <div style={{ fontSize: "11.5px", color: C.txt2, lineHeight: 1.9, borderLeft: "2px solid #e5e7eb", paddingLeft: "10px" }}>
                系统流转：{cur.created_date} 立案{cur.first_alert_at ? `｜首次通知 ${String(cur.first_alert_at).replace("T", " ").slice(0, 16)}` : ""}
                {cur.decided_by ? `｜${cur.decided_by} 确认` : ""}{cur.approved_by ? `｜${cur.approved_by} 审批(${String(cur.approved_at ?? "").replace("T", " ").slice(0, 16)})` : ""}
                {cur.done_at ? `｜完成 ${String(cur.done_at).replace("T", " ").slice(0, 16)}` : ""}
              </div>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
