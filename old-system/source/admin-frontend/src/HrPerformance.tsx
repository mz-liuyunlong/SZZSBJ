/**
 * HrPerformance.tsx — AI 智能人事系统 · 运营绩效管理（新组件，零改旧页面）
 * Tab1 绩效台账（月度；标准工具条；明细在上/汇总在下；项目中文化；逐笔绩效说明+豁免）
 * Tab2 AI 运营日志评级表（周期维度，好/差两档，仅页面展示）—— 本次零改动
 *
 * 数据：biz_perf_deduction append-only（只读）；说明/豁免落人工层 biz_perf_deduction_note。
 * 豁免=exempt_status=1（不删原扣分行），合计排除已豁免。窗口=该扣分所属月的次月5号(含)前。
 * 工具条统一复用 LxToolbar/LxMultiSelect（产品管理同款，不自造）。身份硬鉴权待用户名系统。
 */
import React, { Fragment, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ItemIdLink } from "./ItemIdLink";
import LxMultiSelect from "./LxMultiSelect";
import { lxTB, IconRefresh, IconHelp, IconDownload, IconColumns } from "./LxToolbar";

interface WeekMeta { week_start: string; owners: number; good_total: number; bad_total: number; }
interface SummaryRow {
  owner_name: string; total_logs: number; substantive_logs: number; reviewed_logs: number;
  good_count: number; bad_count: number; ai_comment: string; status: string; updated_at: string;
}
interface ItemRow {
  owner_name: string; src_log_id: number; log_date: string; store_name: string; store_id: string;
  item_id: string; msku: string; log_excerpt: string; signals_excerpt: string;
  verdict: string; reason: string; suggestion: string;
}
interface MonthMeta { ym: string; records: number; }
interface DeductionRow {
  id: number; deduction_date: string; owner_name: string; points: number; entry_type: string; biz_type: string;
  store_id: string; item_id: string; msku: string; ref_event_id: number | null; note: string; created_at: string;
  explanation: string; explanation_by: string; explanation_at: string | null;
  exempt_status: number; exempt_by: string; exempt_at: string | null; exempt_reason: string;
  within_window: number;
  has_cert?: number;
}
interface DeductionOwner {
  owner_name: string; records: number; award_points: number; deduct_points: number;
  exempt_count: number; exempt_points: number; net_points: number;
}

// 项目（biz_type）→ 中文业务名
const BIZ_TYPE_LABEL: Record<string, string> = {
  unclaimed_product: "待认领超时",
  missing_wfs_fee: "缺WFS配送费",
  missing_gpt_keyword: "缺GPT关键词分析链接",
  missing_gpt_ads: "缺GPT广告分析链接",
  cs_test_alert: "CS测品异常预警",
  cs_test_alert_TEST: "CS测品预警(测试)",
  manual: "人工绩效",
};
const bizLabel = (t: string) => BIZ_TYPE_LABEL[t] ?? t;
// 项目筛选固定全量顺序（即使当前台账无数据也可选）
const ALL_BIZ_TYPES = ["unclaimed_product", "missing_wfs_fee", "missing_gpt_keyword", "missing_gpt_ads", "cs_test_alert", "manual"];

const box: React.CSSProperties = { background: "#fff", borderRadius: "10px", border: "1px solid #e5e7eb", padding: "16px 18px", marginBottom: "18px" };
const h2s: React.CSSProperties = { fontSize: "16px", fontWeight: 700, color: "#111827", marginBottom: "10px" };
const th: React.CSSProperties = { border: "1px solid #e5e7eb", background: "#f8fafc", padding: "6px 10px", textAlign: "left", fontSize: "12.5px", color: "#374151", whiteSpace: "nowrap" };
const td: React.CSSProperties = { border: "1px solid #eef0f3", padding: "6px 10px", fontSize: "13px", color: "#1f2329", verticalAlign: "top" };
const selS: React.CSSProperties = { padding: "5px 10px", borderRadius: "6px", border: "1px solid #d1d5db", fontSize: "13px" };
const miniBtn: React.CSSProperties = { fontSize: "12px", padding: "3px 9px", borderRadius: "5px", border: "1px solid #d1d5db", background: "#fff", cursor: "pointer" };

// 明细可选列（列配置开关；日期/负责人/分值/操作 常显）
const OPTIONAL_COLS: Array<{ key: string; label: string }> = [
  { key: "biz", label: "项目" },
  { key: "msku", label: "MSKU" },
  { key: "item", label: "ItemID" },
  { key: "note", label: "备注" },
  { key: "explanation", label: "绩效说明" },
  { key: "created", label: "落账时间" },
  { key: "cert", label: "凭证" },
];

export default function HrPerformance({ embedded, initialTab }: { embedded?: boolean; initialTab?: "ledger" | "review" } = {}) {
  const [tab, setTab] = useState<"ledger" | "review">(initialTab || "ledger");

  // —— 评级 Tab（Tab2）状态：本次零改动 ——
  const [weeks, setWeeks] = useState<WeekMeta[]>([]);
  const [week, setWeek] = useState("");
  const [summaries, setSummaries] = useState<SummaryRow[]>([]);
  const [items, setItems] = useState<ItemRow[]>([]);
  const [expanded, setExpanded] = useState<string>("");
  const [loading, setLoading] = useState(false);

  // —— 绩效台账 Tab（Tab1）状态 ——
  const [months, setMonths] = useState<MonthMeta[]>([]);
  const [month, setMonth] = useState("");
  const [dedRows, setDedRows] = useState<DeductionRow[]>([]);
  const [dedOwners, setDedOwners] = useState<DeductionOwner[]>([]);
  const [approvers, setApprovers] = useState<string[]>(["黄少如", "林翔"]);
  const [dedLoading, setDedLoading] = useState(false);
  // 筛选：inp=待应用（LxMultiSelect 确定后写入），app=已应用（搜索点击生效）——同产品管理
  const [inpOwners, setInpOwners] = useState<string[]>([]);
  const [inpBiz, setInpBiz] = useState<string[]>([]);
  const [inpExempt, setInpExempt] = useState<"all" | "active" | "exempted">("all");
  const [appOwners, setAppOwners] = useState<string[]>([]);
  const [appBiz, setAppBiz] = useState<string[]>([]);
  const [appExempt, setAppExempt] = useState<"all" | "active" | "exempted">("all");
  const [visCols, setVisCols] = useState<Set<string>>(new Set(["biz", "msku", "item", "note", "explanation", "cert"]));
  const [showCols, setShowCols] = useState(false);
  const [editExpl, setEditExpl] = useState<Record<number, string>>({});
  const [busyId, setBusyId] = useState<number>(0);
  const [exemptFor, setExemptFor] = useState<DeductionRow | null>(null);
  const [exemptBy, setExemptBy] = useState("");
  const [canExempt, setCanExempt] = useState(false);
  const [currentUser, setCurrentUser] = useState("");
  const [exemptReason, setExemptReason] = useState("");
  const [toast, setToast] = useState("");
  // 2026-07-30 人工绩效录入
  const [showManual, setShowManual] = useState(false);
  const [members, setMembers] = useState<string[]>([]);
  const [manOwner, setManOwner] = useState("");
  const [manType, setManType] = useState<"award" | "deduct">("deduct");
  const [manPoints, setManPoints] = useState("");
  const [manReason, setManReason] = useState("");
  const [manImg, setManImg] = useState("");
  const [manImgName, setManImgName] = useState("");
  const [manBusy, setManBusy] = useState(false);
  const [colW, setColW] = useState<Record<string, number>>({});
  const rsz = useRef<{ col: string; x: number; w: number } | null>(null);

  const flash = (m: string) => { setToast(m); window.setTimeout(() => setToast(""), 2600); };
  const openManual = async () => {
    setShowManual(true);
    if (!members.length) {
      try { const r = await fetch("/api/hr/perf/members"); const d = await r.json(); setMembers(Array.isArray(d.members) ? d.members : []); } catch { /* noop */ }
    }
  };
  const onPickImg = (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0]; if (!f) return;
    if (f.size > 8 * 1024 * 1024) { flash("图片过大（需 < 8MB）"); return; }
    const rd = new FileReader();
    rd.onload = () => { setManImg(String(rd.result || "")); setManImgName(f.name); };
    rd.readAsDataURL(f);
  };
  const submitManual = async () => {
    if (!manOwner) { flash("请选择被记分人"); return; }
    const pts = Math.abs(Number(manPoints) || 0);
    if (!pts || !Number.isFinite(pts)) { flash("请填写分数（正数）"); return; }
    if (manReason.trim().length < 2) { flash("请填写原因（≥2字）"); return; }
    setManBusy(true);
    try {
      const r = await fetch("/api/hr/perf/manual-entry", { method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ owner_name: manOwner, entry_type: manType, points: pts, reason: manReason.trim(), image_base64: manImg }) });
      const d = await r.json().catch(() => ({}));
      if (r.ok && d.ok) {
        flash(`已录入并通报（${(d.notify || []).join("、")}）`);
        setShowManual(false); setManOwner(""); setManPoints(""); setManReason(""); setManImg(""); setManImgName("");
        loadDeductions(month);
      } else { flash(d.error || "录入失败"); }
    } catch { flash("录入失败（网络/服务器）"); }
    finally { setManBusy(false); }
  };
  useEffect(() => {
    if (typeof document !== "undefined" && !document.getElementById("lx-colresize-css")) {
      const st = document.createElement("style"); st.id = "lx-colresize-css";
      st.textContent = ".lx-colresize{position:absolute;top:0;right:-4px;width:9px;height:100%;cursor:col-resize;user-select:none;z-index:3}.lx-colresize::after{content:'';position:absolute;top:22%;right:4px;width:2px;height:56%;background:#dadce0;border-radius:1px;transition:background .12s,height .12s,width .12s}.lx-colresize:hover::after{background:#1a73e8;width:3px;top:0;height:100%}";
      document.head.appendChild(st);
    }
    function onMove(e: MouseEvent) { const r = rsz.current; if (!r) return; const w = Math.max(48, r.w + (e.clientX - r.x)); setColW((p) => ({ ...p, [r.col]: w })); }
    function onUp() { rsz.current = null; document.body.style.cursor = ""; }
    window.addEventListener("mousemove", onMove); window.addEventListener("mouseup", onUp);
    return () => { window.removeEventListener("mousemove", onMove); window.removeEventListener("mouseup", onUp); };
  }, []);
  const RTh = ({ ck, extra, children }: { ck: string; extra?: React.CSSProperties; children: React.ReactNode }) => (
    <th style={{ ...th, ...(extra || {}), position: "relative", ...(colW[ck] ? { width: `${colW[ck]}px`, minWidth: `${colW[ck]}px` } : {}) }}>
      {children}
      <span className="lx-colresize" onMouseDown={(e) => { e.preventDefault(); const el = e.currentTarget.parentElement as HTMLElement; rsz.current = { col: ck, x: e.clientX, w: el.getBoundingClientRect().width }; document.body.style.cursor = "col-resize"; }} />
    </th>
  );

  // 初始化：评级周 + 台账月份
  useEffect(() => {
    (async () => {
      try {
        const r = await fetch("/api/hr/perf/weeks");
        const d = await r.json();
        const ws: WeekMeta[] = d.weeks ?? [];
        setWeeks(ws);
        if (ws.length > 0) setWeek(ws[0].week_start);
      } catch { setWeeks([]); }
      try {
        const r = await fetch("/api/hr/perf/deduction-months");
        const d = await r.json();
        const ms: MonthMeta[] = d.months ?? [];
        setMonths(ms);
        if (ms.length > 0) setMonth(ms[0].ym);
      } catch { setMonths([]); }
    })();
  }, []);

  const loadWeek = useCallback(async (w: string) => {
    if (!w) { setSummaries([]); setItems([]); return; }
    setLoading(true);
    try {
      const r = await fetch(`/api/hr/perf/log-review?week_start=${encodeURIComponent(w)}`);
      const d = await r.json();
      setSummaries(d.summaries ?? []);
      setItems(d.items ?? []);
    } catch { setSummaries([]); setItems([]); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { loadWeek(week); }, [week, loadWeek]);

  const loadDeductions = useCallback(async (m: string) => {
    setDedLoading(true);
    try {
      const q = m ? `?month=${encodeURIComponent(m)}` : "";
      const r = await fetch(`/api/hr/perf/deductions${q}`);
      const d = await r.json();
      setDedRows(d.rows ?? []);
      setDedOwners(d.by_owner ?? []);
      if (Array.isArray(d.exempt_approvers) && d.exempt_approvers.length) setApprovers(d.exempt_approvers);
      setCanExempt(!!d.can_exempt); setCurrentUser(String(d.current_user ?? ""));
      setEditExpl({});
    } catch { setDedRows([]); setDedOwners([]); }
    finally { setDedLoading(false); }
  }, []);
  useEffect(() => { if (month) loadDeductions(month); }, [month, loadDeductions]);

  const itemsOf = (owner: string, verdict: string) => items.filter((i) => i.owner_name === owner && i.verdict === verdict);

  // 筛选下拉选项
  const ownerOpts = useMemo(() => Array.from(new Set(dedRows.map((r) => r.owner_name))).sort().map((o) => ({ value: o, label: o })), [dedRows]);
  const bizOpts = useMemo(() => {
    const present = new Set(dedRows.map((r) => r.biz_type));
    const extra = [...present].filter((b) => !ALL_BIZ_TYPES.includes(b) && b);
    return [...ALL_BIZ_TYPES, ...extra].map((b) => ({ value: b, label: bizLabel(b) }));
  }, [dedRows]);
  const hasActiveFilters = appOwners.length > 0 || appBiz.length > 0 || appExempt !== "all";
  const applySearch = () => { setAppOwners(inpOwners); setAppBiz(inpBiz); setAppExempt(inpExempt); };
  const handleReset = () => { setInpOwners([]); setInpBiz([]); setInpExempt("all"); setAppOwners([]); setAppBiz([]); setAppExempt("all"); };

  const filtered = useMemo(() => dedRows.filter((r) => {
    if (appOwners.length && !appOwners.includes(r.owner_name)) return false;
    if (appBiz.length && !appBiz.includes(r.biz_type)) return false;
    if (appExempt === "exempted" && r.exempt_status !== 1) return false;
    if (appExempt === "active" && r.exempt_status === 1) return false;
    return true;
  }), [dedRows, appOwners, appBiz, appExempt]);

  const isDeduct = (r: DeductionRow) => (r.entry_type || "deduct") !== "award";

  const saveExplanation = async (r: DeductionRow) => {
    const text = (editExpl[r.id] ?? r.explanation ?? "").trim();
    if (!text) { flash("绩效说明不能为空"); return; }
    setBusyId(r.id);
    try {
      const resp = await fetch("/api/hr/perf/note/save", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ deduction_id: r.id, explanation: text }),
      });
      const d = await resp.json();
      if (!resp.ok) { flash(d.error ?? "保存失败"); return; }
      flash("绩效说明已保存");
      await loadDeductions(month);
    } catch (e) { flash("保存失败：" + (e instanceof Error ? e.message : String(e))); }
    finally { setBusyId(0); }
  };

  const submitExempt = async (revoke: boolean) => {
    if (!exemptFor) return;
    if (!canExempt) { flash("你没有绩效豁免权限（仅 人事 / 运营主管 / 超管）"); return; }
    setBusyId(exemptFor.id);
    try {
      const resp = await fetch("/api/hr/perf/exempt", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ deduction_id: exemptFor.id, exempt_reason: exemptReason, exempt: !revoke }),
      });
      const d = await resp.json();
      if (!resp.ok) { flash(d.error ?? "操作失败"); return; }
      flash(revoke ? "已撤销豁免" : "已豁免，该笔不计入扣分合计");
      setExemptFor(null); setExemptBy(""); setExemptReason("");
      await loadDeductions(month);
    } catch (e) { flash("操作失败：" + (e instanceof Error ? e.message : String(e))); }
    finally { setBusyId(0); }
  };

  const exportCsv = () => {
    const head = ["日期", "负责人", "方向", "分值", "项目", "MSKU", "ItemID", "备注", "绩效说明", "填写人", "是否豁免", "豁免人", "豁免理由", "落账时间"];
    const esc = (v: unknown) => `"${String(v ?? "").replace(/"/g, '""')}"`;
    const lines = filtered.map((r) => [
      r.deduction_date, r.owner_name, r.entry_type === "award" ? "加分" : "扣分", r.points, bizLabel(r.biz_type),
      r.msku, r.item_id, r.note, r.explanation, r.explanation_by,
      r.exempt_status === 1 ? "已豁免" : "", r.exempt_by, r.exempt_reason, r.created_at,
    ].map(esc).join(","));
    const csv = "﻿" + [head.map(esc).join(","), ...lines].join("\r\n");
    const blob = new Blob([csv], { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url; a.download = `绩效台账_${month || "全部"}.csv`;
    document.body.appendChild(a); a.click(); document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  const show = (k: string) => visCols.has(k);
  const toggleCol = (k: string) => setVisCols((prev) => { const n = new Set(prev); if (n.has(k)) n.delete(k); else n.add(k); return n; });

  return (
    <div style={{ maxWidth: "1180px", margin: "0 auto", padding: "18px 16px 40px", fontFamily: "-apple-system,'PingFang SC','Microsoft YaHei',sans-serif" }}>

      {!embedded && (
      <div style={{ display: "flex", gap: "8px", marginBottom: "16px" }}>
        {([["ledger", "🧾 绩效台账"], ["review", "📋 AI 运营日志评级"]] as const).map(([k, label]) => (
          <button key={k} onClick={() => setTab(k)}
            style={{ padding: "8px 20px", borderRadius: "8px", fontSize: "14px", fontWeight: 600, cursor: "pointer",
              border: tab === k ? "1px solid #6366f1" : "1px solid #d1d5db",
              background: tab === k ? "#6366f1" : "#fff", color: tab === k ? "#fff" : "#374151" }}>
            {label}
          </button>
        ))}
      </div>
      )}

      {toast && (
        <div style={{ position: "fixed", top: "16px", left: "50%", transform: "translateX(-50%)", zIndex: 1200,
          background: "#111827", color: "#fff", padding: "8px 16px", borderRadius: "8px", fontSize: "13px", boxShadow: "0 4px 14px rgba(0,0,0,0.2)" }}>
          {toast}
        </div>
      )}

      {tab === "ledger" && (
      <div style={box}>
        <div style={h2s}>🧾 绩效台账</div>

        {/* 标准工具条（产品管理同款：筛选 + 右侧 元信息 + 刷新/帮助/下载/列配置） */}
        <div style={{ ...lxTB.filterWrap, position: "relative", padding: "8px 12px" }}>
          <div style={{ display: "flex", gap: "6px", flexWrap: "wrap", alignItems: "center" }}>
            <select style={{ ...lxTB.filterSelect, width: "150px" }} value={month} onChange={(e) => setMonth(e.target.value)}>
              {months.length === 0 && <option value="">暂无台账月份</option>}
              {months.map((m) => <option key={m.ym} value={m.ym}>{m.ym}（{m.records} 条）</option>)}
            </select>
            {canExempt && <LxMultiSelect placeholder="全部负责人" minWidth={120} options={ownerOpts} selected={inpOwners} onChange={setInpOwners} />}
            <LxMultiSelect placeholder="全部项目" minWidth={120} options={bizOpts} selected={inpBiz} onChange={setInpBiz} />
            <select style={{ ...lxTB.filterSelect, width: "130px" }} value={inpExempt} onChange={(e) => setInpExempt(e.target.value as "all" | "active" | "exempted")}>
              <option value="all">全部（含豁免）</option>
              <option value="active">仅计分</option>
              <option value="exempted">仅已豁免</option>
            </select>
            <button style={lxTB.searchBtn} onClick={applySearch}>搜索</button>
            <button style={lxTB.resetBtn} onClick={handleReset}>重置</button>
            {hasActiveFilters && <span style={{ fontSize: "12px", color: "#6366f1", fontWeight: 600 }}>●筛选生效</span>}

            <span style={{ marginLeft: "auto", display: "flex", alignItems: "center", whiteSpace: "nowrap", flexShrink: 0 }}>
              <span style={{ fontSize: "12px", color: "#6b7280", whiteSpace: "nowrap" }}>
                共 <b style={{ color: "#374151" }}>{filtered.length}</b> 行 · 第 <b style={{ color: "#374151" }}>1</b>/1 页
              </span>
              <span style={{ display: "flex", alignItems: "center", gap: "2px", marginLeft: "10px", flexShrink: 0 }}>
                <button style={lxTB.iconBtn} title="刷新" onClick={() => loadDeductions(month)}><IconRefresh /></button>
                <button style={lxTB.iconBtn} title="帮助：本页规则与数据口径" onClick={() => window.open("#/help?page=hr_performance", "_blank")}><IconHelp /></button>
                <span style={{ width: "1px", height: "16px", background: "#e5e7eb", margin: "0 5px" }} />
                <button style={lxTB.iconBtn} title="下载（CSV，Excel 可打开）" onClick={exportCsv}><IconDownload /></button>
                <button style={lxTB.iconBtn} title="列配置" onClick={() => setShowCols(true)}><IconColumns /></button>
                <button style={{ ...lxTB.iconBtn, width: "auto", padding: "0 8px", fontSize: "12px", color: "#6b7280" }} title="拖列头右边缘调整列宽；点此恢复默认列宽" onClick={() => setColW({})}>列宽重置</button>
                {canExempt && <button style={{ ...lxTB.iconBtn, width: "auto", padding: "0 10px", fontSize: "12.5px", color: "#4f46e5", fontWeight: 600 }} title="人工绩效录入（加/扣分，通报本人+人事群）" onClick={openManual}>＋人工录入</button>}
              </span>
            </span>
          </div>
        </div>

        {dedLoading ? (
          <div style={{ color: "#9ca3af", fontSize: "13px" }}>加载中…</div>
        ) : dedRows.length === 0 ? (
          <div style={{ color: "#9ca3af", fontSize: "13px" }}>该月暂无绩效记录 ✅</div>
        ) : (
          <>
            {/* 明细（上） */}
            <div style={{ fontSize: "13px", fontWeight: 600, color: "#374151", margin: "4px 0 6px" }}>明细（{filtered.length} 条）</div>
            <div style={{ overflowX: "auto" }}>
            <table style={{ borderCollapse: "collapse", width: "100%", marginBottom: "16px" }}>
              <thead><tr>
                <RTh ck="date">日期</RTh>
                <RTh ck="owner">负责人</RTh>
                <RTh ck="points">分值</RTh>
                {show("biz") && <RTh ck="biz">项目</RTh>}
                {show("msku") && <RTh ck="msku">MSKU</RTh>}
                {show("item") && <RTh ck="item">ItemID</RTh>}
                {show("note") && <RTh ck="note">备注</RTh>}
                {show("explanation") && <RTh ck="expl" extra={{ minWidth: "220px" }}>绩效说明（本人填）</RTh>}
                {show("created") && <RTh ck="created">落账时间</RTh>}
                {show("cert") && <RTh ck="cert">凭证</RTh>}
                <RTh ck="exempt">豁免</RTh>
              </tr></thead>
              <tbody>{filtered.map((r) => {
                const exempted = r.exempt_status === 1;
                const editable = Number(r.within_window) === 1;
                const deduct = isDeduct(r);
                return (
                  <tr key={r.id} style={exempted ? { background: "#f9fafb" } : undefined}>
                    <td style={td}>{r.deduction_date}</td>
                    <td style={td}>{r.owner_name}</td>
                    <td style={{ ...td, fontWeight: 700, color: r.entry_type === "award" ? "#15803d" : "#d32f2f",
                      textDecoration: exempted ? "line-through" : "none", opacity: exempted ? 0.6 : 1 }}>
                      {r.entry_type === "award" ? `+${r.points}` : `-${r.points}`}
                    </td>
                    {show("biz") && <td style={td}>{bizLabel(r.biz_type)}</td>}
                    {show("msku") && <td style={td}>{r.msku}</td>}
                    {show("item") && <td style={td}><ItemIdLink itemId={r.item_id} /></td>}
                    {show("note") && <td style={{ ...td, maxWidth: "220px" }}>{r.note}</td>}
                    {show("explanation") && (
                      <td style={td}>
                        {editable ? (
                          <div style={{ display: "flex", gap: "6px", alignItems: "flex-start" }}>
                            <textarea
                              value={editExpl[r.id] ?? r.explanation ?? ""}
                              onChange={(e) => setEditExpl((p) => ({ ...p, [r.id]: e.target.value }))}
                              placeholder="填写说明以解释/纠误判"
                              maxLength={500}
                              style={{ width: "100%", minHeight: "38px", fontSize: "12.5px", padding: "5px 7px", borderRadius: "6px", border: "1px solid #d1d5db", resize: "vertical" }} />
                            <button style={{ ...miniBtn, whiteSpace: "nowrap" }} disabled={busyId === r.id}
                              onClick={() => saveExplanation(r)}>{busyId === r.id ? "…" : "保存"}</button>
                          </div>
                        ) : (
                          <span style={{ color: r.explanation ? "#1f2329" : "#9ca3af" }}>{r.explanation || "（未填 · 已锁定）"}</span>
                        )}
                        {r.explanation_by && <div style={{ fontSize: "11px", color: "#9ca3af", marginTop: "2px" }}>— {r.explanation_by}{r.explanation_at ? ` @${r.explanation_at}` : ""}</div>}
                      </td>
                    )}
                    {show("created") && <td style={{ ...td, color: "#6b7280", fontSize: "12px" }}>{r.created_at}</td>}
                    {show("cert") && <td style={td}>{r.has_cert ? <a href={`/api/hr/perf/cert/${r.id}`} target="_blank" rel="noreferrer" style={{ color: "#4f46e5", fontSize: "12px" }}>查看</a> : <span style={{ color: "#cbd5e1" }}>—</span>}</td>}
                    <td style={td}>
                      {!deduct ? (
                        <span style={{ color: "#9ca3af", fontSize: "12px" }}>—</span>
                      ) : exempted ? (
                        <div>
                          <span style={{ display: "inline-block", background: "#e5e7eb", color: "#374151", fontSize: "11.5px", padding: "2px 8px", borderRadius: "10px" }}>已豁免</span>
                          <div style={{ fontSize: "11px", color: "#9ca3af", marginTop: "2px" }}>{r.exempt_by}{r.exempt_at ? ` @${r.exempt_at}` : ""}</div>
                          {editable && (
                            <button style={{ ...miniBtn, marginTop: "3px" }} disabled={busyId === r.id}
                              onClick={() => { setExemptFor(r); setExemptBy(r.exempt_by || ""); setExemptReason(r.exempt_reason || ""); }}>撤销/改</button>
                          )}
                        </div>
                      ) : editable ? (
                        <button style={miniBtn} disabled={busyId === r.id}
                          onClick={() => { setExemptFor(r); setExemptBy(""); setExemptReason(""); }}>豁免</button>
                      ) : (
                        <span style={{ color: "#9ca3af", fontSize: "12px" }}>已锁定</span>
                      )}
                    </td>
                  </tr>
                );
              })}</tbody>
            </table>
            </div>

            {/* 汇总（下，给管理/人事看） */}
            <div style={{ fontSize: "13px", fontWeight: 600, color: "#374151", margin: "4px 0 6px" }}>按人汇总（扣分合计/净分已排除已豁免）</div>
            <table style={{ borderCollapse: "collapse", width: "100%" }}>
              <thead><tr>
                <th style={th}>负责人</th><th style={th}>记录数</th><th style={th}>加分合计</th>
                <th style={th}>扣分合计</th><th style={th}>已豁免</th><th style={th}>净分</th>
              </tr></thead>
              <tbody>{dedOwners.map((o) => (
                <tr key={o.owner_name}>
                  <td style={{ ...td, fontWeight: 600 }}>{o.owner_name}</td>
                  <td style={td}>{o.records}</td>
                  <td style={{ ...td, color: "#15803d", fontWeight: 700 }}>{Number(o.award_points) > 0 ? `+${o.award_points}` : "0"}</td>
                  <td style={{ ...td, color: "#d32f2f", fontWeight: 700 }}>{Number(o.deduct_points) > 0 ? `-${o.deduct_points}` : "0"}</td>
                  <td style={{ ...td, color: "#6b7280" }}>{Number(o.exempt_count) > 0 ? `${o.exempt_count} 笔 / 免 ${o.exempt_points} 分` : "—"}</td>
                  <td style={{ ...td, fontWeight: 700, color: Number(o.net_points) >= 0 ? "#15803d" : "#d32f2f" }}>{Number(o.net_points) >= 0 ? `+${o.net_points}` : o.net_points}</td>
                </tr>
              ))}</tbody>
            </table>
          </>
        )}
      </div>
      )}

      {/* 人工绩效录入弹层 */}
      {showManual && (
        <div style={{ position: "fixed", inset: 0, background: "rgba(15,23,42,0.4)", zIndex: 1000, display: "flex", alignItems: "center", justifyContent: "center" }}
          onClick={() => !manBusy && setShowManual(false)}>
          <div style={{ background: "#fff", borderRadius: "12px", width: "460px", maxWidth: "94vw", maxHeight: "90vh", overflowY: "auto", boxShadow: "0 8px 32px rgba(0,0,0,0.18)" }} onClick={(e) => e.stopPropagation()}>
            <div style={{ padding: "12px 16px", borderBottom: "1px solid #e5e7eb", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <span style={{ fontSize: "14px", fontWeight: 700, color: "#374151" }}>人工绩效录入</span>
              <button onClick={() => setShowManual(false)} style={{ border: "none", background: "none", fontSize: "18px", cursor: "pointer", color: "#9ca3af" }}>×</button>
            </div>
            <div style={{ padding: "14px 16px", display: "flex", flexDirection: "column", gap: "12px" }}>
              <div>
                <div style={{ fontSize: "12.5px", color: "#374151", marginBottom: "4px" }}>被记分人（公司在册）</div>
                <select value={manOwner} onChange={(e) => setManOwner(e.target.value)} style={{ width: "100%", padding: "7px 8px", borderRadius: "6px", border: "1px solid #d1d5db", fontSize: "13px" }}>
                  <option value="">请选择…</option>
                  {members.map((m) => <option key={m} value={m}>{m}</option>)}
                </select>
              </div>
              <div style={{ display: "flex", gap: "16px", alignItems: "center" }}>
                <label style={{ display: "flex", alignItems: "center", gap: "6px", fontSize: "13px", cursor: "pointer" }}>
                  <input type="radio" checked={manType === "deduct"} onChange={() => setManType("deduct")} /> 扣分
                </label>
                <label style={{ display: "flex", alignItems: "center", gap: "6px", fontSize: "13px", cursor: "pointer" }}>
                  <input type="radio" checked={manType === "award"} onChange={() => setManType("award")} /> 加分
                </label>
                <input type="number" min="1" step="1" value={manPoints} onChange={(e) => setManPoints(e.target.value)} placeholder="分数"
                  style={{ width: "90px", padding: "7px 8px", borderRadius: "6px", border: "1px solid #d1d5db", fontSize: "13px" }} />
                <span style={{ fontSize: "12.5px", color: "#6b7280" }}>分</span>
              </div>
              <div>
                <div style={{ fontSize: "12.5px", color: "#374151", marginBottom: "4px" }}>原因</div>
                <textarea value={manReason} onChange={(e) => setManReason(e.target.value)} placeholder="填写加/扣分原因"
                  style={{ width: "100%", minHeight: "60px", padding: "7px 8px", borderRadius: "6px", border: "1px solid #d1d5db", fontSize: "13px", resize: "vertical" }} />
              </div>
              <div>
                <div style={{ fontSize: "12.5px", color: "#374151", marginBottom: "4px" }}>凭证图片（可选，飞书通报内嵌）</div>
                <input type="file" accept="image/*" onChange={onPickImg} style={{ fontSize: "12.5px" }} />
                {manImg && <div style={{ marginTop: "8px" }}><img src={manImg} alt="凭证预览" style={{ maxWidth: "100%", maxHeight: "160px", borderRadius: "6px", border: "1px solid #e5e7eb" }} /><div style={{ fontSize: "11.5px", color: "#9ca3af", marginTop: "2px" }}>{manImgName} · <span style={{ cursor: "pointer", color: "#4f46e5" }} onClick={() => { setManImg(""); setManImgName(""); }}>移除</span></div></div>}
              </div>
              <div style={{ fontSize: "12px", color: canExempt ? "#166534" : "#b45309", background: canExempt ? "#e6f4ea" : "#fef3c7", padding: "7px 10px", borderRadius: "6px" }}>
                录入人＝当前登录账号 <b>{currentUser || "（你）"}</b>；提交后写入台账并飞书通报<b>本人 + 人事群</b>，操作留痕。
              </div>
              <div style={{ display: "flex", justifyContent: "flex-end", gap: "8px" }}>
                <button onClick={() => setShowManual(false)} disabled={manBusy} style={{ padding: "7px 14px", borderRadius: "6px", border: "1px solid #d1d5db", background: "#fff", fontSize: "13px", cursor: "pointer" }}>取消</button>
                <button onClick={submitManual} disabled={manBusy} style={{ padding: "7px 16px", borderRadius: "6px", border: "none", background: manType === "award" ? "#16a34a" : "#dc2626", color: "#fff", fontSize: "13px", fontWeight: 600, cursor: manBusy ? "not-allowed" : "pointer", opacity: manBusy ? 0.6 : 1 }}>
                  {manBusy ? "提交中…" : (manType === "award" ? "确认加分并通报" : "确认扣分并通报")}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* 列配置弹层 */}
      {showCols && (
        <div style={{ position: "fixed", inset: 0, background: "rgba(15,23,42,0.4)", zIndex: 1000, display: "flex", alignItems: "center", justifyContent: "center" }}
          onClick={() => setShowCols(false)}>
          <div style={{ background: "#fff", borderRadius: "12px", width: "360px", maxWidth: "92vw", overflow: "hidden", boxShadow: "0 8px 32px rgba(0,0,0,0.18)" }} onClick={(e) => e.stopPropagation()}>
            <div style={{ padding: "12px 16px", borderBottom: "1px solid #e5e7eb", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <span style={{ fontSize: "14px", fontWeight: 700, color: "#374151" }}>列配置</span>
              <button onClick={() => setShowCols(false)} style={{ border: "none", background: "none", fontSize: "18px", cursor: "pointer", color: "#9ca3af" }}>×</button>
            </div>
            <div style={{ padding: "10px 16px" }}>
              {OPTIONAL_COLS.map((c) => (
                <label key={c.key} style={{ display: "flex", alignItems: "center", gap: "8px", padding: "5px 0", cursor: "pointer", fontSize: "13px" }}>
                  <input type="checkbox" checked={show(c.key)} onChange={() => toggleCol(c.key)} />
                  <span style={{ color: "#374151" }}>{c.label}</span>
                </label>
              ))}
              <div style={{ fontSize: "12px", color: "#9ca3af", marginTop: "6px" }}>日期 / 负责人 / 分值 / 豁免 常显；会话内生效。</div>
            </div>
          </div>
        </div>
      )}

      {/* 豁免弹层 */}
      {exemptFor && (
        <div style={{ position: "fixed", inset: 0, background: "rgba(15,23,42,0.4)", zIndex: 1100, display: "flex", alignItems: "center", justifyContent: "center" }}
          onClick={() => setExemptFor(null)}>
          <div style={{ background: "#fff", borderRadius: "12px", padding: "18px 20px", width: "420px", maxWidth: "92vw" }} onClick={(e) => e.stopPropagation()}>
            <div style={{ fontSize: "15px", fontWeight: 700, marginBottom: "10px" }}>豁免扣分 · {exemptFor.msku}</div>
            <div style={{ fontSize: "12.5px", color: "#6b7280", marginBottom: "12px", lineHeight: 1.7 }}>
              {exemptFor.owner_name}｜{bizLabel(exemptFor.biz_type)}｜-{exemptFor.points} 分｜{exemptFor.deduction_date}<br />
              豁免后该笔从扣分合计/净分中免除，原始记录保留。
            </div>
            <div style={{ fontSize: "12.5px", marginBottom: "10px", padding: "8px 10px", borderRadius: 6, color: canExempt ? "#166534" : "#b45309", background: canExempt ? "#e6f4ea" : "#fef3c7" }}>
              {canExempt ? <>豁免人＝当前登录账号 <b>{currentUser || "（你）"}</b>，操作将留痕</> : "你没有绩效豁免权限，仅 人事 / 运营主管 / 超管 可操作"}
            </div>
            <div style={{ fontSize: "12.5px", color: "#374151", marginBottom: "4px" }}>豁免理由（可选）</div>
            <textarea value={exemptReason} onChange={(e) => setExemptReason(e.target.value)} maxLength={255}
              placeholder="为什么豁免这笔扣分" style={{ width: "100%", minHeight: "56px", fontSize: "13px", padding: "6px 8px", borderRadius: "6px", border: "1px solid #d1d5db", resize: "vertical", marginBottom: "12px" }} />
            <div style={{ display: "flex", gap: "8px", justifyContent: "flex-end" }}>
              <button style={{ ...lxTB.resetBtn, padding: "6px 14px" }} onClick={() => setExemptFor(null)}>取消</button>
              {exemptFor.exempt_status === 1 && (
                <button style={{ ...lxTB.resetBtn, padding: "6px 14px", borderColor: "#f59e0b", color: "#b45309" }} disabled={busyId === exemptFor.id || !canExempt} onClick={() => submitExempt(true)}>撤销豁免</button>
              )}
              <button style={{ ...lxTB.searchBtn, padding: "6px 16px" }} disabled={busyId === exemptFor.id || !canExempt} onClick={() => submitExempt(false)}>
                {busyId === exemptFor.id ? "…" : "确认豁免"}
              </button>
            </div>
          </div>
        </div>
      )}

      {tab === "review" && (
      <div style={box}>
        <div style={{ display: "flex", alignItems: "center", gap: "12px", marginBottom: "10px" }}>
          <div style={{ ...h2s, marginBottom: 0 }}>📋 AI 运营日志评级表（周）</div>
          <select style={selS} value={week} onChange={(e) => setWeek(e.target.value)}>
            {weeks.length === 0 && <option value="">暂无评估周</option>}
            {weeks.map((w) => (
              <option key={w.week_start} value={w.week_start}>{w.week_start} 起一周（好{w.good_total}/差{w.bad_total}）</option>
            ))}
          </select>
          {loading && <span style={{ fontSize: "12px", color: "#9ca3af" }}>加载中…</span>}
        </div>
        <div style={{ fontSize: "12.5px", color: "#6b7280", marginBottom: "8px" }}>
          每周四 23:00 AI 随机抽查 20 个 ItemID（周期=上周五~本周四），逐产品评估其周期内全部日志行：有基础行但未填/仅无运营话术的天数直接记差；实质日志按两要素（动作+调整目的/依据）评好/差，后续观察计划为鼓励项（现阶段放宽，后续收紧）；V1 仅页面展示、不扣分。默认按差评占比排序，明细按 ItemID 汇总展示。
        </div>
        {summaries.length === 0 ? (
          <div style={{ color: "#9ca3af", fontSize: "13px" }}>该周暂无评估结果</div>
        ) : (
          <table style={{ borderCollapse: "collapse", width: "100%" }}>
            <thead><tr>
              <th style={th}>负责人</th><th style={th}>日志行</th><th style={th}>实质日志</th><th style={th}>送评</th>
              <th style={th}>👍 好</th><th style={th}>👎 差</th><th style={th}>AI 点评</th><th style={th}>状态</th><th style={th}>明细</th>
            </tr></thead>
            <tbody>{summaries.map((s0) => (
              <Fragment key={s0.owner_name}>
                <tr>
                  <td style={{ ...td, fontWeight: 700 }}>{s0.owner_name}</td>
                  <td style={td}>{s0.total_logs}</td>
                  <td style={td}>{s0.substantive_logs}</td>
                  <td style={td}>{s0.reviewed_logs}{s0.status === "truncated" ? "（截断）" : ""}</td>
                  <td style={{ ...td, color: "#15803d", fontWeight: 700 }}>{s0.good_count}</td>
                  <td style={{ ...td, color: "#d32f2f", fontWeight: 700 }}>{s0.bad_count}</td>
                  <td style={{ ...td, maxWidth: "360px" }}>{s0.status === "failed" ? <span style={{ color: "#9ca3af" }}>本周未出分（AI 调用失败）</span> : s0.ai_comment}</td>
                  <td style={td}>{s0.status}</td>
                  <td style={td}>
                    <button style={{ fontSize: "12px", padding: "3px 10px", borderRadius: "5px", border: "1px solid #d1d5db", background: "#fff", cursor: "pointer" }}
                      onClick={() => setExpanded(expanded === s0.owner_name ? "" : s0.owner_name)}>
                      {expanded === s0.owner_name ? "收起" : "展开"}
                    </button>
                  </td>
                </tr>
                {expanded === s0.owner_name && (
                  <tr key={`${s0.owner_name}-detail`}>
                    <td style={{ ...td, background: "#fafafa" }} colSpan={9}>
                      {(["bad", "good"] as const).map((v) => {
                        const list = itemsOf(s0.owner_name, v);
                        if (!list.length) return null;
                        // 2026-07-23 需求方指令：同一 ItemID 的日志汇总在一起展示（组内按日期排序）
                        const byIt = new Map<string, ItemRow[]>();
                        for (const it of list) {
                          const k = `${it.msku}|${it.item_id}`;
                          if (!byIt.has(k)) byIt.set(k, []);
                          byIt.get(k)!.push(it);
                        }
                        return (
                          <div key={v} style={{ marginBottom: "10px" }}>
                            <div style={{ fontWeight: 700, fontSize: "13px", color: v === "good" ? "#15803d" : "#d32f2f", margin: "6px 0" }}>
                              {v === "good" ? "👍 好的日志" : "👎 待改进日志"}（{list.length} 条 · {byIt.size} 个产品）
                            </div>
                            {Array.from(byIt.entries()).map(([k, rows]) => {
                              const first = rows[0];
                              const sorted = [...rows].sort((a, b) => a.log_date.localeCompare(b.log_date));
                              return (
                                <div key={k} style={{ borderLeft: `3px solid ${v === "good" ? "#34a853" : "#d32f2f"}`, background: "#fff", borderRadius: "6px", padding: "8px 10px", margin: "6px 0", fontSize: "12.5px", lineHeight: 1.7 }}>
                                  <div style={{ fontWeight: 700, color: "#1f2329", borderBottom: "1px solid #f2f3f5", paddingBottom: "4px", marginBottom: "4px" }}>
                                    📦 {first.msku} ｜ ItemID <ItemIdLink itemId={first.item_id} /> ｜ {first.store_name || first.store_id}（{rows.length} 条）
                                  </div>
                                  {sorted.map((it) => (
                                    <div key={it.src_log_id} style={{ margin: "4px 0 8px" }}>
                                      <div><b>{it.log_date}</b> ｜ <b>日志：</b>{it.log_excerpt || "（未填）"}</div>
                                      {it.signals_excerpt && <div style={{ color: "#92400e" }}><b>当日提醒：</b>{it.signals_excerpt}</div>}
                                      <div style={{ color: v === "good" ? "#15803d" : "#d32f2f" }}><b>AI 判定：</b>{it.reason}</div>
                                      {it.suggestion && <div style={{ color: "#4f46e5" }}><b>改进建议：</b>{it.suggestion}</div>}
                                    </div>
                                  ))}
                                </div>
                              );
                            })}
                          </div>
                        );
                      })}
                    </td>
                  </tr>
                )}
              </Fragment>
            ))}</tbody>
          </table>
        )}
      </div>
      )}
    </div>
  );
}
