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

import { useState, useEffect, useCallback } from "react";

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
  rows: OwnerProgress[];
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

// ── 工具 ──────────────────────────────────────────────────────────────────────

function fmt(n: number | null | undefined): string {
  if (n === null || n === undefined || !Number.isFinite(n)) return "—";
  return n.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function currentMonthKey(): string { return new Date().toISOString().slice(0, 7); }
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
  const [genPwd, setGenPwd] = useState("");
  const [genMsg, setGenMsg] = useState("");
  const [genBusy, setGenBusy] = useState(false);

  // 目标设置状态
  const [tType, setTType] = useState<"monthly" | "quarterly">("monthly");
  const [tPeriod, setTPeriod] = useState(currentMonthKey());
  const [edit, setEdit] = useState<Record<string, { sales: string; profit: string }>>({});
  const [loadedTargets, setLoadedTargets] = useState<TargetRow[]>([]);
  const [newOwner, setNewOwner] = useState("");
  const [pasteText, setPasteText] = useState("");
  const [changedBy, setChangedBy] = useState("");
  const [password, setPassword] = useState("");
  const [submitMsg, setSubmitMsg] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const loadProgress = useCallback(async () => {
    try {
      const r = await fetch("/api/ai-business/progress");
      const d = (await r.json()) as ProgressResp;
      if (!r.ok || d.error) { setProgressErr(d.error ?? r.statusText); return; }
      setProgress(d);
      setProgressErr("");
    } catch (e) { setProgressErr(e instanceof Error ? e.message : String(e)); }
  }, []);

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
      const d = (await r.json()) as { rows?: TargetRow[] };
      setLoadedTargets(d.rows ?? []);
    } catch { setLoadedTargets([]); }
  }, []);

  const loadChangeLog = useCallback(async () => {
    try {
      const r = await fetch("/api/ai-business/targets/change-log?limit=100");
      const d = (await r.json()) as { rows?: ChangeLogRow[] };
      setChangeLog(d.rows ?? []);
    } catch { /* 忽略 */ }
  }, []);

  useEffect(() => { loadProgress(); loadReports(); loadChangeLog(); }, [loadProgress, loadReports, loadChangeLog]);
  useEffect(() => { loadTargets(tType, tPeriod); }, [tType, tPeriod, loadTargets]);

  // 目标编辑表初值：progress 里出现的负责人 ∪ 已有目标负责人
  useEffect(() => {
    const owners = new Set<string>();
    (progress?.rows ?? []).forEach((r) => { if (r.owner !== "(未分配)") owners.add(r.owner); });
    loadedTargets.forEach((t) => owners.add(t.owner));
    const next: Record<string, { sales: string; profit: string }> = {};
    [...owners].sort((a, b) => a.localeCompare(b, "zh")).forEach((o) => {
      const s = loadedTargets.find((t) => t.owner === o && t.metric === "sales");
      const p = loadedTargets.find((t) => t.owner === o && t.metric === "profit");
      next[o] = { sales: s ? String(Number(s.target_value)) : "", profit: p ? String(Number(p.target_value)) : "" };
    });
    setEdit(next);
  }, [progress, loadedTargets]);

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
    setSubmitMsg(applied ? `已解析 ${applied} 行到下方表格，请核对后输入密码提交` : "未解析到有效行（格式：负责人<Tab>销售额<Tab>毛利）");
  }

  // 差异预览
  function diffItems(): { items: Array<{ target_type: string; period_key: string; owner: string; metric: string; target_value: number }>; preview: string[] } {
    const items: Array<{ target_type: string; period_key: string; owner: string; metric: string; target_value: number }> = [];
    const preview: string[] = [];
    for (const [owner, v] of Object.entries(edit)) {
      for (const metric of ["sales", "profit"] as const) {
        const raw = v[metric].trim();
        if (raw === "") continue;
        const val = Number(raw);
        if (!Number.isFinite(val) || val < 0) continue;
        const old = loadedTargets.find((t) => t.owner === owner && t.metric === metric);
        const oldVal = old ? Math.round(Number(old.target_value) * 100) / 100 : null;
        const newVal = Math.round(val * 100) / 100;
        if (oldVal === newVal) continue;
        items.push({ target_type: tType, period_key: tPeriod, owner, metric, target_value: newVal });
        preview.push(`${owner} ${metric === "sales" ? "销售额" : "毛利"}: ${oldVal === null ? "（新设）" : fmt(oldVal)} → ${fmt(newVal)}`);
      }
    }
    return { items, preview };
  }

  async function submitTargets(source: "manual" | "import") {
    const { items, preview } = diffItems();
    if (items.length === 0) { setSubmitMsg("没有需要写入的变化"); return; }
    if (!changedBy.trim()) { setSubmitMsg("请填写调整人姓名"); return; }
    if (!password) { setSubmitMsg("请输入目标编辑密码"); return; }
    if (!window.confirm(`确认写入 ${items.length} 项变化？\n\n${preview.slice(0, 20).join("\n")}${preview.length > 20 ? `\n...共${preview.length}项` : ""}`)) return;
    setSubmitting(true);
    setSubmitMsg("");
    try {
      const r = await fetch("/api/ai-business/targets", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ password, changed_by: changedBy.trim(), change_source: source, items }),
      });
      const d = (await r.json()) as { ok?: boolean; created?: number; updated?: number; unchanged?: number; error?: string };
      if (!r.ok || !d.ok) { setSubmitMsg(`写入失败：${d.error ?? r.statusText}`); return; }
      setSubmitMsg(`写入成功：新建 ${d.created} ｜ 调整 ${d.updated} ｜ 无变化 ${d.unchanged}`);
      setPasteText("");
      await Promise.all([loadTargets(tType, tPeriod), loadProgress(), loadChangeLog()]);
    } catch (e) {
      setSubmitMsg(`网络错误：${e instanceof Error ? e.message : String(e)}`);
    } finally { setSubmitting(false); }
  }

  function onTypeChange(t: "monthly" | "quarterly") {
    setTType(t);
    setTPeriod(t === "monthly" ? currentMonthKey() : currentQuarterKey());
  }

  const pw = progress;
  const win = view === "month" ? pw?.monthWindow : pw?.quarterWindow;
  const timePct = win?.timeProgressPct ?? 0;
  const compM = pw?.company[view === "month" ? "month" : "quarter"];
  const compSalesPct = compM && compM.sales.target > 0 ? Math.round((compM.sales.actual / compM.sales.target) * 1000) / 10 : null;
  const compProfitPct = compM && compM.profit.target > 0 ? Math.round((compM.profit.actual / compM.profit.target) * 1000) / 10 : null;

  const sortedRows = [...(pw?.rows ?? [])].sort((a, b) => {
    const pa = a[view].sales.pct ?? -1;
    const pb = b[view].sales.pct ?? -1;
    return pb - pa;
  });

  return (
    <div style={{ maxWidth: 1200, margin: "0 auto", padding: "20px 24px 60px", fontSize: 14, color: "#1e293b" }}>

      {/* ① 公司完成情况 */}
      <div style={C.sectionHead}>
        <span style={C.sectionTitle}>公司完成情况</span>
        <div style={{ display: "flex", gap: 6 }}>
          <button onClick={() => setView("month")} style={{ ...C.viewBtn, ...(view === "month" ? C.viewBtnOn : {}) }}>月度 {pw?.monthKey ?? ""}</button>
          <button onClick={() => setView("quarter")} style={{ ...C.viewBtn, ...(view === "quarter" ? C.viewBtnOn : {}) }}>季度 {pw?.quarterKey ?? ""}</button>
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
        <span style={C.sectionTitle}>每人业绩完成（按销售额完成率排序）</span>
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
            <input type="password" value={genPwd} onChange={(e) => setGenPwd(e.target.value)} placeholder="密码" style={{ ...C.input, width: 100 }} />
            <button disabled={genBusy} onClick={async () => {
              setGenMsg("");
              if (!genOwner || !genType || !genStart || !genEnd) { setGenMsg("负责人、类型、起止时间均为必选"); return; }
              if (!genPwd) { setGenMsg("请输入密码"); return; }
              if (genStart > genEnd) { setGenMsg("起日不能晚于末日"); return; }
              if (pw?.dataEnd && genEnd > pw.dataEnd) { setGenMsg(`末日数据未收口，最晚可选 ${pw.dataEnd}`); return; }
              if (!window.confirm(`确认生成并推送？\n类型：${REPORT_TYPE_LABEL[genType]}\n负责人：${genOwner === "all" ? "全部人（群+私聊推送）" : genOwner + "（仅私聊推送）"}\n窗口：${genStart} ~ ${genEnd}`)) return;
              setGenBusy(true);
              try {
                const r = await fetch("/api/ai-business/reports/generate", {
                  method: "POST", headers: { "Content-Type": "application/json" },
                  body: JSON.stringify({ password: genPwd, report_type: genType, win_start: genStart, win_end: genEnd, owners: genOwner }),
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
        <span style={C.sectionTitle}>目标设置（密码门禁，调整全程留痕）</span>
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
            <th style={C.th}>销售额目标（$）</th>
            <th style={C.th}>毛利目标（$）</th>
          </tr></thead>
          <tbody>
            {Object.entries(edit).map(([owner, v]) => (
              <tr key={owner}>
                <td style={{ ...C.td, textAlign: "left", fontWeight: 600 }}>{owner}</td>
                <td style={C.td}><input value={v.sales} onChange={(e) => setEdit((p) => ({ ...p, [owner]: { ...p[owner], sales: e.target.value } }))} style={C.cellInput} /></td>
                <td style={C.td}><input value={v.profit} onChange={(e) => setEdit((p) => ({ ...p, [owner]: { ...p[owner], profit: e.target.value } }))} style={C.cellInput} /></td>
              </tr>
            ))}
          </tbody>
        </table>
        <div style={{ display: "flex", gap: 8, marginTop: 10, alignItems: "center", flexWrap: "wrap" }}>
          <input value={newOwner} onChange={(e) => setNewOwner(e.target.value)} placeholder="新增负责人姓名" style={{ ...C.input, width: 140 }} />
          <button onClick={() => { const o = newOwner.trim(); if (o && !edit[o]) { setEdit((p) => ({ ...p, [o]: { sales: "", profit: "" } })); setNewOwner(""); } }} style={C.miniBtn}>+ 添加行</button>
          <span style={{ flex: 1 }} />
          <input value={changedBy} onChange={(e) => setChangedBy(e.target.value)} placeholder="调整人姓名" style={{ ...C.input, width: 120 }} />
          <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} placeholder="目标编辑密码" style={{ ...C.input, width: 130 }} />
          <button onClick={() => submitTargets(pasteText.trim() ? "import" : "manual")} disabled={submitting} style={{ ...C.btn, opacity: submitting ? 0.6 : 1 }}>
            {submitting ? "写入中..." : "确认写入"}
          </button>
        </div>
        {submitMsg && <div style={{ marginTop: 8, fontSize: 13, color: submitMsg.includes("成功") ? "#1d9e75" : "#d85a30" }}>{submitMsg}</div>}
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
