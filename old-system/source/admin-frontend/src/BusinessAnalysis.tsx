/**
 * BusinessAnalysis.tsx — AI经营分析 Tab（#/business-analysis，2026-07-13 新增，隔离开发）
 *
 * 区块：
 *   ① 公司完成情况（月度/季度 × 销售额/毛利，龟兔进度条 🐰超前 🐢落后 🦄达成）
 *   ② 每人业绩完成表（迷你进度条，按完成率排序，全员透明）
 *   ③ 报表中心（ai_business_report 列表，受控HTML打开；手动生成待生成器转正后开放）
 *   ④ 目标设置（手动编辑 + 表格粘贴批量导入，双入口共用密码门禁 TARGET_EDIT_PASSWORD）
 *   ⑤ 目标变更历史（append-only 流水，全员可查）
 *
 * 后端：/api/ai-business/*（aiBusinessRoutes.ts）
 */

import { useState, useEffect, useCallback, useRef } from "react";

// ── 类型 ──────────────────────────────────────────────────────────────────────

interface MetricProgress { actual: number; target: number; pct: number | null; }
interface OwnerProgress {
  owner: string;
  month: { sales: MetricProgress; profit: MetricProgress };
  quarter: { sales: MetricProgress; profit: MetricProgress };
  hasTarget: boolean;
}
interface ProgressResp {
  monthKey: string; quarterKey: string; dataEnd: string;
  monthWindow: { start: string; end: string; timeProgressPct: number };
  quarterWindow: { start: string; end: string; timeProgressPct: number };
  company: {
    month: { sales: { actual: number; target: number }; profit: { actual: number; target: number } };
    quarter: { sales: { actual: number; target: number }; profit: { actual: number; target: number } };
  };
  company_ex_clearance?: {
    month: { sales: { actual: number; target: number }; profit: { actual: number; target: number } };
    quarter: { sales: { actual: number; target: number }; profit: { actual: number; target: number } };
  };
  rows: OwnerProgress[];
  rows_ex_clearance?: OwnerProgress[];
  error?: string;
}
interface TargetRow {
  id: number; target_type: string; period_key: string; owner: string;
  metric: string; target_value: string | number; updated_by: string; updated_at: string;
}
interface ChangeLogRow {
  id: number; period_key: string; owner: string; metric: string;
  old_value: string | number | null; new_value: string | number;
  action: string; change_source: string; changed_by: string; changed_at: string;
}
interface ReportRow {
  id: number; report_type: string; period_key: string; win_start: string; win_end: string;
  status: string; trigger_source: string; generated_at: string;
  completeness_json: unknown; filter_json?: unknown; notify_json?: unknown;
}

const REPORT_TYPE_LABEL: Record<string, string> = {
  weekly: "周报", monthly: "月报", quarterly: "季报", yearly: "年报",
};

/** 与生成器 safe_name 同规则：负责人名→页面文件名片段 */
function safeName(owner: string): string {
  return owner.replace(/[^\w一-鿿-]/g, "_");
}

// 已归并的旧负责人名（目标表历史0值行如实保留，展示层跳过；与后端 OWNER_ALIASES 同源）
const MERGED_OLD_OWNERS = new Set(["啊四"]);

// ── 工具 ──────────────────────────────────────────────────────────────────────

function fmt(n: number | null | undefined): string {
  if (n === null || n === undefined || !Number.isFinite(n)) return "—";
  return n.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function currentMonthKey(): string { return new Date().toISOString().slice(0, 7); }
function quarterOf(monthKey: string): string { const [y, m] = monthKey.split("-").map(Number); return (!y || !m) ? currentQuarterKey() : `${y}-Q${Math.ceil(m / 3)}`; }
function currentQuarterKey(): string {
  const d = new Date();
  return `${d.getFullYear()}-Q${Math.floor(d.getMonth() / 3) + 1}`;
}

/** 龟兔状态：达成🦄 / 超前🐰 / 落后🐢；无目标返回 null */
function animalOf(pct: number | null, timePct: number): string | null {
  if (pct === null) return null;
  if (pct >= 100) return "🦄";
  return pct >= timePct ? "🐰" : "🐢";
}

// ── 进度条组件（数据在上、条在下；时间基准线；渐变+动物标记） ─────────────────

function AnimalBar(props: {
  pct: number | null; timePct: number; height?: number; showLabel?: boolean;
}) {
  const { pct, timePct } = props;
  const h = props.height ?? 22;
  const showLabel = props.showLabel ?? true;
  const animal = animalOf(pct, timePct);
  const width = pct === null ? 0 : Math.min(100, Math.max(0, pct));
  const behind = pct !== null && pct < timePct && pct < 100;
  const done = pct !== null && pct >= 100;
  const track = pct === null ? "#eceff4" : done ? "#eeedfe" : behind ? "#faece7" : "#e1f5ee";
  const fill = done
    ? "linear-gradient(90deg,#afa9ec,#7f77dd,#a78bfa)"
    : behind
      ? "linear-gradient(90deg,#f5c4b3,#f0997b,#d85a30)"
      : "linear-gradient(90deg,#9fe1cb,#5dcaa5,#1d9e75)";
  const labelColor = done ? "#3c3489" : behind ? "#712b13" : "#085041";
  const diff = pct === null ? null : Math.round((pct - timePct) * 10) / 10;
  return (
    <div style={{ position: "relative", height: h + 8, marginTop: 6 }}>
      <div style={{ position: "absolute", top: 4, left: 0, right: 0, height: h, background: track, borderRadius: h / 2 }}>
        {pct !== null && (
          <div style={{ position: "absolute", left: 0, top: 0, height: h, width: `${width}%`, background: fill, borderRadius: h / 2, transition: "width .6s ease" }} />
        )}
        {timePct > 0 && timePct < 100 && (
          <div title={`时间进度 ${timePct}%`} style={{ position: "absolute", left: `${timePct}%`, top: -4, width: 2, height: h + 8, background: "#b4b2a9" }} />
        )}
        {animal && (
          <span style={{ position: "absolute", left: `calc(${width}% - ${h - 2}px)`, top: -3, fontSize: h - 2, lineHeight: 1, filter: "drop-shadow(0 1px 1px rgba(0,0,0,.2))" }}>
            {animal}
          </span>
        )}
        {showLabel && (
          <span style={{ position: "absolute", left: width > 55 ? "8px" : `calc(${Math.max(width, timePct)}% + ${h + 6}px)`, top: h / 2 - 8, fontSize: 12, fontWeight: 600, color: pct === null ? "#9aa1ac" : labelColor, whiteSpace: "nowrap" }}>
            {pct === null ? "目标待录入" : `${pct.toFixed(1)}%${diff !== null ? (diff >= 0 ? ` 超前${diff.toFixed(1)}pp` : ` 落后${Math.abs(diff).toFixed(1)}pp`) : ""}`}
          </span>
        )}
      </div>
    </div>
  );
}

// ── 主组件 ────────────────────────────────────────────────────────────────────

export default function BusinessAnalysis() {
  const [progress, setProgress] = useState<ProgressResp | null>(null);
  const [progressErr, setProgressErr] = useState("");
  const [view, setView] = useState<"month" | "quarter">("month");
  const [inclClearance, setInclClearance] = useState(true); // M6：含/不含清货（不含=排除当月 indicator=清货 的目标+业绩）
  const [progMonth, setProgMonth] = useState("");            // 经营分析选中月(空=等 months 定妥,防当前空月)
  const [progMonths, setProgMonths] = useState<string[]>([]);
  const progSeq = useRef(0);
  const [reports, setReports] = useState<ReportRow[]>([]);
  const [changeLog, setChangeLog] = useState<ChangeLogRow[]>([]);

  // 报表中心：查看筛选（负责人+类型必选，默认空=不展示；周期可选，空=近5份）
  const [rOwner, setROwner] = useState("");
  const [rType, setRType] = useState("");
  const [rPeriod, setRPeriod] = useState("");
  // 手动生成表单
  const [genType, setGenType] = useState("");
  const [genOwner, setGenOwner] = useState("");
  const [genStart, setGenStart] = useState("");
  const [genEnd, setGenEnd] = useState("");
  const [genMsg, setGenMsg] = useState("");
  const [genBusy, setGenBusy] = useState(false);

  // 目标设置状态
  const [tType, setTType] = useState<"monthly" | "quarterly">("monthly");
  const [tPeriod, setTPeriod] = useState(currentMonthKey());
  const [edit, setEdit] = useState<Record<string, { sales: string; profit: string }>>({});
  const [loadedTargets, setLoadedTargets] = useState<TargetRow[]>([]);
  const [newOwner, setNewOwner] = useState("");
  const [pasteText, setPasteText] = useState("");
  const [submitMsg, setSubmitMsg] = useState("");
  // 单品目标上卷 + 新品公式目标 + 主管确认（2026-07-16）
  const [selfReport, setSelfReport] = useState<Record<string, { sales: number; profit: number; planned: number; with_target: number }>>({});
  const [npTargets, setNpTargets] = useState<Record<string, { sales: number; profit: number; count: number }>>({});
  const [confirms, setConfirms] = useState<Record<string, { confirmed_by: string; created_at: string; confirmed_sales: number; confirmed_profit: number }>>({});
  const [rowPwd, setRowPwd] = useState<Record<string, string>>({}); // 每行独立主管确认密码（每次确认必输）
  const [confirmingOwner, setConfirmingOwner] = useState("");
  const [canEdit, setCanEdit] = useState(false);

  const loadProgress = useCallback(async () => {
    if (!progMonth) return;                                    // 月份未定前不加载(等 months)
    const seq = ++progSeq.current;
    try {
      const r = await fetch(`/api/ai-business/progress?month=${encodeURIComponent(progMonth)}&quarter=${encodeURIComponent(quarterOf(progMonth))}`);
      const d = (await r.json()) as ProgressResp;
      if (seq !== progSeq.current) return;                     // 竞态守卫:只认最新一次请求,晚到的旧月响应丢弃
      if (!r.ok || d.error) { setProgressErr(d.error ?? r.statusText); return; }
      setProgress(d);
      setProgressErr("");
    } catch (e) { if (seq === progSeq.current) setProgressErr(e instanceof Error ? e.message : String(e)); }
  }, [progMonth]);

  const loadReports = useCallback(async () => {
    try {
      const r = await fetch("/api/ai-business/reports?limit=50");
      const d = (await r.json()) as { rows?: ReportRow[] };
      setReports(d.rows ?? []);
    } catch { /* 列表加载失败不阻塞页面 */ }
  }, []);

  const loadTargets = useCallback(async (type: string, period: string) => {
    try {
      const r = await fetch(`/api/ai-business/targets?target_type=${type}&period_key=${encodeURIComponent(period)}`);
      const d = (await r.json()) as { rows?: TargetRow[]; can_edit?: boolean };
      setLoadedTargets(d.rows ?? []);
      setCanEdit(!!d.can_edit);
    } catch { setLoadedTargets([]); }
  }, []);

  const loadRefData = useCallback(async (type: string, period: string) => {
    if (type !== "monthly") { setSelfReport({}); setNpTargets({}); }
    try {
      if (type === "monthly") {
        const [r1, r2] = await Promise.all([
          fetch(`/api/ai-business/targets/self-report?period_key=${encodeURIComponent(period)}`),
          fetch(`/api/ai-business/targets/new-product?period_key=${encodeURIComponent(period)}`),
        ]);
        const d1 = (await r1.json()) as { rows?: Array<{ owner: string; sales: number; profit: number; planned: number; with_target: number }> };
        const d2 = (await r2.json()) as { byOwner?: Array<{ owner: string; sales: number; profit: number; count: number }> };
        const sr: typeof selfReport = {};
        (d1.rows ?? []).forEach((r) => { sr[r.owner] = { sales: Number(r.sales), profit: Number(r.profit), planned: Number(r.planned), with_target: Number(r.with_target) }; });
        setSelfReport(sr);
        const np: typeof npTargets = {};
        (d2.byOwner ?? []).forEach((r) => { np[r.owner] = { sales: Number(r.sales), profit: Number(r.profit), count: Number(r.count) }; });
        setNpTargets(np);
      }
      const r3 = await fetch(`/api/ai-business/targets/confirm-status?target_type=${type}&period_key=${encodeURIComponent(period)}`);
      const d3 = (await r3.json()) as { rows?: Array<{ owner: string; confirmed_by: string; created_at: string; confirmed_sales: number; confirmed_profit: number }> };
      const cf: typeof confirms = {};
      (d3.rows ?? []).forEach((r) => { cf[r.owner] = { confirmed_by: r.confirmed_by, created_at: String(r.created_at), confirmed_sales: Number(r.confirmed_sales), confirmed_profit: Number(r.confirmed_profit) }; });
      setConfirms(cf);
    } catch { /* 参考数据加载失败不阻塞编辑 */ }
  }, []);

  const loadChangeLog = useCallback(async () => {
    try {
      const r = await fetch("/api/ai-business/targets/change-log?limit=100");
      const d = (await r.json()) as { rows?: ChangeLogRow[] };
      setChangeLog(d.rows ?? []);
    } catch { /* 忽略 */ }
  }, []);

  // 可选月份=有数据的月份；默认最新有目标月(当前月有数据才用当前月)，防看当前空月
  useEffect(() => {
    let alive = true;
    void fetch("/api/ai-business/monthly-plan/months").then((r) => r.json()).then((d) => {
      if (!alive) return;
      const ms = Array.isArray(d.months) ? (d.months as string[]).filter((m) => /^\d{4}-\d{2}$/.test(m)) : [];
      setProgMonths(ms);
      setProgMonth(ms.includes(currentMonthKey()) ? currentMonthKey() : (ms[0] ?? currentMonthKey()));
    }).catch(() => { setProgMonth(currentMonthKey()); });
    return () => { alive = false; };
  }, []);
  useEffect(() => { loadProgress(); }, [loadProgress]);
  useEffect(() => { loadReports(); loadChangeLog(); }, [loadReports, loadChangeLog]);
  useEffect(() => { loadTargets(tType, tPeriod); loadRefData(tType, tPeriod); }, [tType, tPeriod, loadTargets, loadRefData]);

  // 目标编辑表初值：progress 里出现的负责人 ∪ 已有目标负责人
  useEffect(() => {
    const owners = new Set<string>();
    (progress?.rows ?? []).forEach((r) => { if (r.owner !== "(未分配)") owners.add(r.owner); });
    loadedTargets.forEach((t) => { if (!MERGED_OLD_OWNERS.has(t.owner)) owners.add(t.owner); });
    Object.keys(selfReport).forEach((o) => { if (o !== "(未分配)") owners.add(o); });
    const next: Record<string, { sales: string; profit: string }> = {};
    [...owners].sort((a, b) => a.localeCompare(b, "zh")).forEach((o) => {
      const s = loadedTargets.find((t) => t.owner === o && t.metric === "sales");
      const p = loadedTargets.find((t) => t.owner === o && t.metric === "profit");
      const sr = selfReport[o];
      // 默认填入自报合计（目标表已有值时以已有值优先，不覆盖）
      next[o] = {
        sales: s ? String(Number(s.target_value)) : (sr && sr.sales > 0 ? String(sr.sales) : ""),
        profit: p ? String(Number(p.target_value)) : (sr && sr.profit !== 0 ? String(sr.profit) : ""),
      };
    });
    setEdit(next);
  }, [progress, loadedTargets, selfReport]);

  // 主管确认（逐负责人；密码即身份；确认后该负责人本周期目标仅主管可改）
  async function confirmOwner(owner: string) {
    setSubmitMsg("");
    if (!canEdit) { setSubmitMsg("仅超管（林翔 / 陈佳聪）可编辑经营目标"); return; }
    const v = edit[owner] ?? { sales: "", profit: "" };
    const sales = Number(v.sales || 0);
    const profit = Number(v.profit || 0);
    if (!Number.isFinite(sales) || sales < 0 || !Number.isFinite(profit)) {
      setSubmitMsg(`${owner} 的目标值非法，无法确认`); return;
    }
    setConfirmingOwner(owner);
    try {
      const r = await fetch("/api/ai-business/targets/confirm", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ target_type: tType, period_key: tPeriod, owner, sales, profit }),
      });
      const d = (await r.json()) as { ok?: boolean; confirmed_by?: string; error?: string };
      if (!r.ok || !d.ok) { setSubmitMsg(`确认失败：${d.error ?? r.statusText}`); return; }
      setSubmitMsg(`✅ ${owner} 已确认（${d.confirmed_by}）`);
      await Promise.all([loadRefData(tType, tPeriod), loadTargets(tType, tPeriod), loadChangeLog()]);
    } catch (e) {
      setSubmitMsg(`网络错误：${e instanceof Error ? e.message : String(e)}`);
    } finally { setConfirmingOwner(""); }
  }

  // 粘贴导入解析：每行 "负责人 <tab/逗号> 销售额目标 <tab/逗号> 毛利目标"
  function applyPaste() {
    const lines = pasteText.split(/\r?\n/).map((l) => l.trim()).filter(Boolean);
    let applied = 0;
    const next = { ...edit };
    for (const line of lines) {
      const parts = line.split(/[\t,，]+/).map((s) => s.trim());
      if (parts.length < 2) continue;
      const owner = parts[0];
      if (!owner || /负责人|owner/i.test(owner)) continue; // 跳过表头
      const sales = parts[1] ?? "";
      const profit = parts[2] ?? "";
      next[owner] = {
        sales: sales.replace(/[$,¥￥\s]/g, ""),
        profit: profit.replace(/[$,¥￥\s]/g, ""),
      };
      applied++;
    }
    setEdit(next);
    setSubmitMsg(applied ? `已解析 ${applied} 行到下方表格，请逐行点"确认"写入（仅超管）` : "未解析到有效行（格式：负责人<Tab>销售额<Tab>毛利）");
  }

  // 差异预览
  // 2026-07-16 需求方拍板：批量「确认写入」通道移除，所有目标写入统一走每行主管确认（堵绕过锁定的旁路）

  function onTypeChange(t: "monthly" | "quarterly") {
    setTType(t);
    setTPeriod(t === "monthly" ? currentMonthKey() : currentQuarterKey());
  }

  const pw = progress;
  const win = view === "month" ? pw?.monthWindow : pw?.quarterWindow;
  const timePct = win?.timeProgressPct ?? 0;
  const compSrc = (!inclClearance && pw?.company_ex_clearance) ? pw.company_ex_clearance : pw?.company;
  const compM = compSrc?.[view === "month" ? "month" : "quarter"];
  const compSalesPct = compM && compM.sales.target > 0 ? Math.round((compM.sales.actual / compM.sales.target) * 1000) / 10 : null;
  const compProfitPct = compM && compM.profit.target > 0 ? Math.round((compM.profit.actual / compM.profit.target) * 1000) / 10 : null;

  // 2026-07-15 需求方：按毛利实际值排序（不按完成率）
  const rowSrc = (!inclClearance && pw?.rows_ex_clearance) ? pw.rows_ex_clearance : pw?.rows;
  const sortedRows = [...(rowSrc ?? [])].sort(
    (a, b) => b[view].profit.actual - a[view].profit.actual,
  );

  return (
    <div style={{ maxWidth: 1200, margin: "0 auto", padding: "20px 24px 60px", fontSize: 14, color: "#1e293b" }}>

      {/* ① 公司完成情况 */}
      <div style={C.sectionHead}>
        <span style={C.sectionTitle}>公司完成情况</span>
        <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
          <select value={progMonth} onChange={(e) => setProgMonth(e.target.value)} title="选择月份（可看历史月）"
            style={{ height: 30, border: "1px solid #dadce0", borderRadius: 8, background: "#fff", color: "#202124", fontSize: 13, padding: "0 10px", cursor: "pointer", outline: "none" }}>
            {progMonths.length === 0 && progMonth && <option value={progMonth}>{progMonth}</option>}
            {progMonths.map((m) => <option key={m} value={m}>{m}</option>)}
          </select>
          <button onClick={() => setView("month")} style={{ ...C.viewBtn, ...(view === "month" ? C.viewBtnOn : {}) }}>月度 {pw?.monthKey ?? ""}</button>
          <button onClick={() => setView("quarter")} style={{ ...C.viewBtn, ...(view === "quarter" ? C.viewBtnOn : {}) }}>季度 {pw?.quarterKey ?? ""}</button>
          <button onClick={() => setInclClearance((v) => !v)} title="切换公司完成情况是否含清货（不含=排除当月 indicator=清货 的目标+业绩；清货业绩到清货中心看）"
            style={{ ...C.viewBtn, ...(inclClearance ? {} : C.viewBtnOn) }}>{inclClearance ? "含清货" : "不含清货"}</button>
        </div>
        <span style={{ marginLeft: "auto", fontSize: 12, color: "#94a3b8" }}>
          {pw ? `数据到 ${pw.dataEnd}（D-2） ｜ 时间进度 ${timePct}%` : ""}
          <button onClick={loadProgress} style={C.miniBtn}>刷新</button>
        </span>
      </div>
      {progressErr && <div style={C.errBox}>加载失败：{progressErr}</div>}
      {pw && compM && (
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 14 }}>
          {([["销售额", compM.sales, compSalesPct], ["毛利润", compM.profit, compProfitPct]] as Array<[string, { actual: number; target: number }, number | null]>).map(([label, v, pct]) => (
            <div key={label} style={C.card}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", flexWrap: "wrap", gap: 6 }}>
                <span style={{ fontWeight: 600 }}>{label}（$）</span>
                <span style={{ fontSize: 13, color: "#64748b" }}>
                  目标 {v.target > 0 ? fmt(v.target) : "待录入"} ｜ 已完成 <b style={{ color: "#1e293b" }}>{fmt(v.actual)}</b>
                  {v.target > 0 && timePct > 0 && ` ｜ 预测期末 ${fmt(Math.round((v.actual / timePct) * 1000) / 10)}`}
                </span>
              </div>
              <AnimalBar pct={pct} timePct={timePct} height={24} />
            </div>
          ))}
        </div>
      )}

      {/* ② 每人业绩完成表 */}
      <div style={{ ...C.sectionHead, marginTop: 28 }}>
        <span style={C.sectionTitle}>每人业绩完成（按毛利排序）</span>
      </div>
      <div style={C.card}>
        {sortedRows.length === 0 && <div style={{ color: "#94a3b8", padding: 8 }}>暂无数据</div>}
        {sortedRows.map((r) => {
          const m = r[view];
          return (
            <div key={r.owner} style={{ display: "flex", gap: 14, alignItems: "flex-start", padding: "10px 0", borderBottom: "1px solid #f1f5f9" }}>
              <div style={{ width: 84, paddingTop: 4, fontWeight: 600, flexShrink: 0 }}>{r.owner}</div>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontSize: 12, color: "#64748b" }}>销售 {fmt(m.sales.actual)} / {m.sales.target > 0 ? fmt(m.sales.target) : "目标待录入"}</div>
                <AnimalBar pct={m.sales.pct} timePct={timePct} height={14} />
              </div>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontSize: 12, color: "#64748b" }}>毛利 {fmt(m.profit.actual)} / {m.profit.target > 0 ? fmt(m.profit.target) : "目标待录入"}</div>
                <AnimalBar pct={m.profit.pct} timePct={timePct} height={14} />
              </div>
            </div>
          );
        })}
      </div>

      {/* ③ 报表中心（v2：筛选必选才展示；手动生成自由窗口+负责人） */}
      <div style={{ ...C.sectionHead, marginTop: 28 }}>
        <span style={C.sectionTitle}>报表中心</span>
        <button onClick={loadReports} style={C.miniBtn}>刷新</button>
        {/* 2026-07-23 批5：帮助入口 → 帮助中心「经营周报、月报」（周四确认卡/19:30生成/手动生成纪律） */}
        <button onClick={() => window.open("#/help?page=weekly_report", "_blank")} style={C.miniBtn}
          title="帮助：周报/月报生成规则、周四确认卡与手动生成纪律">帮助</button>
      </div>
      <div style={C.card}>
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center", marginBottom: 10, fontSize: 12, color: "#64748b" }}>
          负责人<span style={{ color: "#d85a30" }}>*</span>
          <select value={rOwner} onChange={(e) => setROwner(e.target.value)} style={C.input}>
            <option value="">请选择</option>
            <option value="__company__">公司总览</option>
            {(pw?.rows ?? []).map((r) => r.owner).filter((o) => o !== "(未分配)").sort((a, b) => a.localeCompare(b, "zh"))
              .map((o) => <option key={o} value={o}>{o}</option>)}
            <option value="(未分配)">(未分配)</option>
          </select>
          报表类型<span style={{ color: "#d85a30" }}>*</span>
          <select value={rType} onChange={(e) => setRType(e.target.value)} style={C.input}>
            <option value="">请选择</option>
            {Object.entries(REPORT_TYPE_LABEL).map(([v, l]) => <option key={v} value={v}>{l}</option>)}
          </select>
          周期
          <input value={rPeriod} onChange={(e) => setRPeriod(e.target.value)} placeholder="如 2026-W29，留空=近5份" style={{ ...C.input, width: 150 }} />
        </div>
        {(!rOwner || !rType) ? (
          <div style={{ color: "#94a3b8", padding: 8 }}>请先选择负责人与报表类型</div>
        ) : (() => {
          const list = reports
            .filter((r) => r.report_type === rType)
            .filter((r) => {
              if (rOwner === "__company__") return true;
              try {
                const f = typeof r.filter_json === "string" ? JSON.parse(r.filter_json) : (r.filter_json as { owners?: unknown } | null);
                const ow = f?.owners;
                return !ow || ow === "all" || (Array.isArray(ow) && (ow as string[]).includes(rOwner));
              } catch { return true; }
            })
            .filter((r) => (rPeriod.trim() ? r.period_key === rPeriod.trim() : true))
            .slice(0, rPeriod.trim() ? 999 : 5);
          const openFile = rOwner === "__company__" ? "index.html" : `owner-${safeName(rOwner)}.html`;
          return list.length === 0 ? (
            <div style={{ color: "#94a3b8", padding: 8 }}>无符合条件的报表</div>
          ) : (
            <table style={C.table}>
              <thead><tr>
                <th style={C.th}>类型</th><th style={C.th}>周期</th><th style={C.th}>窗口</th>
                <th style={C.th}>状态</th><th style={C.th}>来源</th><th style={C.th}>生成时间</th><th style={C.th}>操作</th>
              </tr></thead>
              <tbody>
                {list.map((r) => (
                  <tr key={r.id}>
                    <td style={C.td}>{REPORT_TYPE_LABEL[r.report_type] ?? r.report_type}</td>
                    <td style={C.td}>{r.period_key}</td>
                    <td style={C.td}>{String(r.win_start).slice(0, 10)} ~ {String(r.win_end).slice(0, 10)}</td>
                    <td style={C.td}>{r.status === "success" ? "✅ 成功" : r.status}</td>
                    <td style={C.td}>{r.trigger_source}</td>
                    <td style={C.td}>{String(r.generated_at).replace("T", " ").slice(0, 19)}</td>
                    <td style={C.td}>
                      <a href={`/api/ai-business/reports/${r.id}/html/${encodeURIComponent(openFile)}`} target="_blank" rel="noreferrer" style={{ color: "#4f46e5" }}>
                        打开{rOwner === "__company__" ? "总览" : "个人页"}
                      </a>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          );
        })()}

        <div style={{ borderTop: "1px solid #e2e8f0", marginTop: 14, paddingTop: 12 }}>
          <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 8 }}>
            手动生成 <span style={{ fontWeight: 400, fontSize: 12, color: "#64748b" }}>
              （生成成功后自动推送：全部人=群+各负责人私聊；单人=仅私聊该负责人。最晚可选 {pw?.dataEnd ?? "—"}）</span>
          </div>
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center", fontSize: 12, color: "#64748b" }}>
            负责人<span style={{ color: "#d85a30" }}>*</span>
            <select value={genOwner} onChange={(e) => setGenOwner(e.target.value)} style={C.input}>
              <option value="">请选择</option>
              <option value="all">全部人</option>
              {(pw?.rows ?? []).map((r) => r.owner).filter((o) => o !== "(未分配)").sort((a, b) => a.localeCompare(b, "zh"))
                .map((o) => <option key={o} value={o}>{o}</option>)}
            </select>
            类型<span style={{ color: "#d85a30" }}>*</span>
            <select value={genType} onChange={(e) => setGenType(e.target.value)} style={C.input}>
              <option value="">请选择</option>
              {Object.entries(REPORT_TYPE_LABEL).map(([v, l]) => <option key={v} value={v}>{l}</option>)}
            </select>
            时间段<span style={{ color: "#d85a30" }}>*</span>
            <input type="date" value={genStart} max={pw?.dataEnd} onChange={(e) => setGenStart(e.target.value)} style={C.input} />
            ~
            <input type="date" value={genEnd} max={pw?.dataEnd} onChange={(e) => setGenEnd(e.target.value)} style={C.input} />
            <button disabled={genBusy} onClick={async () => {
              setGenMsg("");
              if (!genOwner || !genType || !genStart || !genEnd) { setGenMsg("负责人、类型、起止时间均为必选"); return; }
              if (genStart > genEnd) { setGenMsg("起日不能晚于末日"); return; }
              if (pw?.dataEnd && genEnd > pw.dataEnd) { setGenMsg(`末日数据未收口，最晚可选 ${pw.dataEnd}`); return; }
              if (!window.confirm(`确认生成并推送？\n类型：${REPORT_TYPE_LABEL[genType]}\n负责人：${genOwner === "all" ? "全部人（群+私聊推送）" : genOwner + "（仅私聊推送）"}\n窗口：${genStart} ~ ${genEnd}`)) return;
              setGenBusy(true);
              try {
                const r = await fetch("/api/ai-business/reports/generate", {
                  method: "POST", headers: { "Content-Type": "application/json" },
                  body: JSON.stringify({ report_type: genType, win_start: genStart, win_end: genEnd, owners: genOwner }),
                });
                const d = (await r.json()) as { ok?: boolean; message?: string; error?: string };
                setGenMsg(d.ok ? `✅ ${d.message ?? "已开始生成"}` : `生成失败：${d.error ?? r.statusText}`);
              } catch (e) {
                setGenMsg(`网络错误：${e instanceof Error ? e.message : String(e)}`);
              } finally { setGenBusy(false); }
            }} style={{ ...C.btn, opacity: genBusy ? 0.6 : 1 }}>{genBusy ? "提交中..." : "生成并推送"}</button>
          </div>
          {genMsg && <div style={{ marginTop: 8, fontSize: 13, color: genMsg.startsWith("✅") ? "#1d9e75" : "#d85a30" }}>{genMsg}</div>}
        </div>
      </div>

      {/* ④ 目标设置 */}
      <div style={{ ...C.sectionHead, marginTop: 28 }}>
        <span style={C.sectionTitle}>目标设置（仅超管可改，调整全程留痕）</span>
        <select value={tType} onChange={(e) => onTypeChange(e.target.value as "monthly" | "quarterly")} style={C.input}>
          <option value="monthly">月度</option>
          <option value="quarterly">季度</option>
        </select>
        <input value={tPeriod} onChange={(e) => setTPeriod(e.target.value)} placeholder={tType === "monthly" ? "2026-07" : "2026-Q3"} style={{ ...C.input, width: 110 }} />
      </div>
      <div style={C.card}>
        <div style={{ fontSize: 12, color: "#64748b", marginBottom: 8 }}>
          方式一：直接在表格修改 ｜ 方式二：从 Excel 复制粘贴到下框（列顺序：负责人、销售额目标、毛利目标）后点"解析"
        </div>
        <div style={{ display: "flex", gap: 8, marginBottom: 12 }}>
          <textarea value={pasteText} onChange={(e) => setPasteText(e.target.value)} rows={3}
            placeholder={"刘华媛\t120000\t15000\n江梓博\t100000\t12000"}
            style={{ flex: 1, border: "1px solid #e2e8f0", borderRadius: 8, padding: 8, fontSize: 13, fontFamily: "monospace" }} />
          <button onClick={applyPaste} style={{ ...C.btn, alignSelf: "flex-start" }}>解析到表格</button>
        </div>
        <table style={C.table}>
          <thead><tr>
            <th style={{ ...C.th, textAlign: "left" }}>负责人</th>
            {tType === "monthly" && <th style={C.th}>自报合计·销售额</th>}
            {tType === "monthly" && <th style={C.th}>自报合计·毛利</th>}
            <th style={C.th}>销售额目标（$）</th>
            <th style={C.th}>毛利目标（$）</th>
            {tType === "monthly" && <th style={C.th}>新品目标(系统)</th>}
            <th style={C.th}>主管确认</th>
          </tr></thead>
          <tbody>
            {Object.entries(edit).map(([owner, v]) => {
              const sr = selfReport[owner];
              const np = npTargets[owner];
              const cf = confirms[owner];
              return (
                <tr key={owner} style={cf ? { background: "#f0fdf4" } : undefined}>
                  <td style={{ ...C.td, textAlign: "left", fontWeight: 600 }}>{owner}</td>
                  {tType === "monthly" && (
                    <td style={{ ...C.td, color: "#64748b" }}>
                      {sr ? fmt(sr.sales) : "—"}
                      {sr && sr.with_target < sr.planned && <span style={{ color: "#d97706", fontSize: 11 }}>（{sr.planned - sr.with_target}未填）</span>}
                    </td>
                  )}
                  {tType === "monthly" && <td style={{ ...C.td, color: "#64748b" }}>{sr ? fmt(sr.profit) : "—"}</td>}
                  <td style={C.td}><input value={v.sales} onChange={(e) => setEdit((p) => ({ ...p, [owner]: { ...p[owner], sales: e.target.value } }))} style={C.cellInput} /></td>
                  <td style={C.td}><input value={v.profit} onChange={(e) => setEdit((p) => ({ ...p, [owner]: { ...p[owner], profit: e.target.value } }))} style={C.cellInput} /></td>
                  {tType === "monthly" && (
                    <td style={{ ...C.td, color: "#64748b", fontSize: 12 }}>
                      {np ? `+${fmt(np.sales)} / ${fmt(np.profit)}（${np.count}款）` : "—"}
                    </td>
                  )}
                  <td style={{ ...C.td, whiteSpace: "nowrap" }}>
                    <button onClick={() => confirmOwner(owner)} disabled={confirmingOwner === owner || !canEdit} title={canEdit ? "" : "仅超管可编辑"}
                      style={{ ...C.miniBtn, color: "#4f46e5" }}>
                      {confirmingOwner === owner ? "..." : (cf ? "重新确认" : "确认")}
                    </button>
                    {cf && (
                      <div style={{ fontSize: 11, color: "#166534", marginTop: 2 }}>
                        ✅ {cf.confirmed_by} {String(cf.created_at).slice(5, 16).replace("T", " ")}
                      </div>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
        <div style={{ display: "flex", gap: 8, marginTop: 10, alignItems: "center", flexWrap: "wrap" }}>
          <input value={newOwner} onChange={(e) => setNewOwner(e.target.value)} placeholder="新增负责人姓名" style={{ ...C.input, width: 140 }} />
          <button onClick={() => { const o = newOwner.trim(); if (o && !edit[o]) { setEdit((p) => ({ ...p, [o]: { sales: "", profit: "" } })); setNewOwner(""); } }} style={C.miniBtn}>+ 添加行</button>
          <span style={{ flex: 1 }} />
          <span style={{ fontSize: 12, color: "#94a3b8" }}>写入方式：逐行点「确认」写入（仅超管；含 Excel 粘贴解析后的写入）</span>
        </div>
        {submitMsg && <div style={{ marginTop: 8, fontSize: 13, color: submitMsg.includes("成功") || submitMsg.includes("✅") ? "#1d9e75" : "#d85a30" }}>{submitMsg}</div>}
        <div style={{ marginTop: 6, fontSize: 11.5, color: "#94a3b8" }}>
          自报合计=运营单品目标求和（未填完会标注）；可编辑格默认带入自报值，超管可调整后逐人"确认"（身份＝登录账号，操作留痕）；
          确认后该负责人本周期目标锁定、仅超管可再修改；最终业绩目标=确认值+新品目标（系统按上架天数×0.3单/天自动核算）。
        </div>
      </div>

      {/* ⑤ 变更历史 */}
      <div style={{ ...C.sectionHead, marginTop: 28 }}>
        <span style={C.sectionTitle}>目标变更历史（最近100条）</span>
        <button onClick={loadChangeLog} style={C.miniBtn}>刷新</button>
      </div>
      <div style={C.card}>
        {changeLog.length === 0 ? (
          <div style={{ color: "#94a3b8", padding: 8 }}>暂无变更记录</div>
        ) : (
          <table style={C.table}>
            <thead><tr>
              <th style={C.th}>时间</th><th style={C.th}>周期</th><th style={C.th}>负责人</th>
              <th style={C.th}>指标</th><th style={C.th}>旧值</th><th style={C.th}>新值</th>
              <th style={C.th}>动作</th><th style={C.th}>方式</th><th style={C.th}>调整人</th>
            </tr></thead>
            <tbody>
              {changeLog.map((c) => (
                <tr key={c.id}>
                  <td style={C.td}>{String(c.changed_at).replace("T", " ").slice(0, 19)}</td>
                  <td style={C.td}>{c.period_key}</td>
                  <td style={C.td}>{c.owner}</td>
                  <td style={C.td}>{c.metric === "sales" ? "销售额" : "毛利"}</td>
                  <td style={C.td}>{c.old_value === null ? "—" : fmt(Number(c.old_value))}</td>
                  <td style={C.td}>{fmt(Number(c.new_value))}</td>
                  <td style={C.td}>{c.action === "create" ? "新设" : "调整"}</td>
                  <td style={C.td}>{c.change_source === "import" ? "批量导入" : "手动"}</td>
                  <td style={C.td}>{c.changed_by}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}

// ── 样式 ──────────────────────────────────────────────────────────────────────

const C: Record<string, React.CSSProperties> = {
  sectionHead: { display: "flex", alignItems: "center", gap: 10, margin: "6px 0 10px" },
  sectionTitle: { fontSize: 16, fontWeight: 700, color: "#1e1b4b", borderLeft: "4px solid #6366f1", paddingLeft: 8 },
  card: { background: "white", border: "1px solid #e2e8f0", borderRadius: 12, padding: "14px 18px", boxShadow: "0 1px 4px rgba(0,0,0,.05)" },
  viewBtn: { background: "white", border: "1px solid #e2e8f0", borderRadius: 8, padding: "4px 12px", fontSize: 13, cursor: "pointer", color: "#64748b" },
  viewBtnOn: { background: "#6366f1", borderColor: "#6366f1", color: "white", fontWeight: 600 },
  miniBtn: { background: "white", border: "1px solid #e2e8f0", borderRadius: 8, padding: "3px 10px", fontSize: 12, cursor: "pointer", color: "#475569", marginLeft: 8 },
  btn: { background: "linear-gradient(135deg,#4f46e5,#7c3aed)", color: "white", border: "none", borderRadius: 8, padding: "8px 18px", fontSize: 13, fontWeight: 600, cursor: "pointer" },
  input: { border: "1px solid #e2e8f0", borderRadius: 8, padding: "5px 8px", fontSize: 13, outline: "none" },
  cellInput: { width: 110, border: "1px solid #e2e8f0", borderRadius: 6, padding: "4px 8px", fontSize: 13, textAlign: "right", outline: "none" },
  table: { width: "100%", borderCollapse: "collapse", fontSize: 13 },
  th: { padding: "6px 8px", background: "#f8fafc", borderBottom: "1px solid #e2e8f0", color: "#475569", textAlign: "center", whiteSpace: "nowrap" },
  td: { padding: "6px 8px", borderBottom: "1px solid #f1f5f9", textAlign: "center", whiteSpace: "nowrap" },
  errBox: { background: "#fff5f5", border: "1px solid #fecaca", color: "#dc2626", borderRadius: 8, padding: "8px 12px", marginBottom: 10, fontSize: 13 },
};
