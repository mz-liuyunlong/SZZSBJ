/**
 * Attendance.tsx — AI人力·考勤（月度核算）
 * 合规(UI_STANDARDS): §1 LxToolbar 工具条(共N行·同步·第P/T页 + 刷新/帮助/下载/列配置/列宽重置) + 筛选栏;
 *   §2 帮助壳内 #/help?page=attendance; §5 列宽可拖+重置+提示。配色仅 Google。
 */
import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { lxTB, IconRefresh, IconHelp, IconDownload, IconColumns } from "./LxToolbar";

const PAGE_KEY = "attendance";
const C = {
  primary: "#1a73e8", ink: "#202124", ink2: "#5f6368", muted: "#80868b", line: "#e8eaed",
  surface: "#ffffff", headBg: "#f8f9fa",
  green: "#1e8e3e", greenBg: "#e6f4ea", amber: "#b06000", amberBg: "#feefc3",
  orange: "#c5570b", red: "#c5221f", redBg: "#fce8e6", blue: "#1967d2", blueBg: "#e8f0fe", grayBg: "#f1f3f4",
};

interface Item {
  open_id: string; name: string; scheduled: number; present: number; late: number; early: number;
  lack: number; absent: number; leave_h: number; out_h: number; overtime_h: number; rate: number;
}
interface Kpi { people: number; full_attendance: number; abnormal: number; avg_rate: number; late_total: number; absent_total: number; }

const COLS: Array<{ k: string; label: string; w: number; left?: boolean; lock?: boolean }> = [
  { k: "name", label: "姓名", w: 110, left: true, lock: true },
  { k: "scheduled", label: "应出勤", w: 68 }, { k: "present", label: "实出勤", w: 68 },
  { k: "late", label: "迟到", w: 58 }, { k: "early", label: "早退", w: 58 },
  { k: "lack", label: "缺卡", w: 58 }, { k: "absent", label: "旷工", w: 58 },
  { k: "leave_h", label: "请假h", w: 68 }, { k: "overtime_h", label: "加班h", w: 68 },
  { k: "rate", label: "出勤率", w: 76 }, { k: "status", label: "状态", w: 92 },
];
const DEFAULT_W: Record<string, number> = Object.fromEntries(COLS.map((c) => [c.k, c.w]));
const ALL_KEYS = COLS.map((c) => c.k);
const STATUS_OPTS = [
  { v: "", l: "全部状态" }, { v: "full", l: "全勤" }, { v: "warn", l: "迟到/早退" },
  { v: "bad", l: "异常(缺卡/旷工)" }, { v: "leave", l: "有请假" }, { v: "nocard", l: "免打卡" },
];

const card: React.CSSProperties = { background: C.surface, border: "1px solid " + C.line, borderRadius: "12px" };
function Badge({ text, fg, bg }: { text: string; fg: string; bg: string }) {
  return <span style={{ display: "inline-block", padding: "2px 9px", borderRadius: "6px", fontSize: "12px", fontWeight: 600, color: fg, background: bg }}>{text}</span>;
}
function statusOf(it: Item): { text: string; fg: string; bg: string; kind: string } {
  if (it.scheduled === 0) return { text: "免打卡", fg: C.ink2, bg: C.grayBg, kind: "nocard" };
  if (it.absent > 0 || it.lack > 0) return { text: "异常", fg: C.red, bg: C.redBg, kind: "bad" };
  if (it.late > 0 || it.early > 0) return { text: "迟到/早退", fg: C.amber, bg: C.amberBg, kind: "warn" };
  return { text: "全勤", fg: C.green, bg: C.greenBg, kind: "full" };
}

export default function Attendance({ onNavigate }: { onNavigate?: (k: string) => void } = {}) {
  const [months, setMonths] = useState<string[]>([]);
  const [month, setMonth] = useState("");
  const [items, setItems] = useState<Item[]>([]);
  const [kpi, setKpi] = useState<Kpi | null>(null);
  const [sync, setSync] = useState("");
  const [err, setErr] = useState("");
  const [colW, setColW] = useState<Record<string, number>>({ ...DEFAULT_W });
  const [visible, setVisible] = useState<Record<string, boolean>>(Object.fromEntries(ALL_KEYS.map((k) => [k, true])));
  const [showColCfg, setShowColCfg] = useState(false);
  const [q, setQ] = useState("");
  const [status, setStatus] = useState("");
  const drag = useRef<{ k: string; x: number; w: number } | null>(null);

  useEffect(() => {
    fetch("/api/hr/attendance/months", { credentials: "include" })
      .then((r) => { if (r.status === 403) { setErr("无权限：考勤仅超级管理员 / 人事可见。"); return null; } return r.json(); })
      .then((d) => { if (!d) return; const ms: string[] = d.months || []; setMonths(ms); if (ms.length) setMonth(ms[0]); else setErr("暂无考勤数据（等待同步落库）。"); })
      .catch(() => setErr("加载失败，请稍后重试。"));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const load = useCallback((m: string) => {
    if (!m) return;
    fetch("/api/hr/attendance/monthly?month=" + encodeURIComponent(m), { credentials: "include" })
      .then((r) => { if (r.status === 403) { setErr("无权限：考勤仅超级管理员 / 人事可见。"); return null; } return r.json(); })
      .then((d) => { if (!d) return; if (d.error) { setErr(d.error); return; } setErr(""); setKpi(d.kpi); setItems(d.items || []); setSync(d.latest_sync_time || ""); })
      .catch(() => setErr("加载失败，请稍后重试。"));
  }, []);
  useEffect(() => { if (month) load(month); }, [month, load]);

  const onResizeDown = (k: string, e: React.MouseEvent) => {
    e.preventDefault();
    drag.current = { k, x: e.clientX, w: colW[k] ?? DEFAULT_W[k] };
    const move = (ev: MouseEvent) => { const d = drag.current; if (!d) return; setColW((p) => ({ ...p, [d.k]: Math.max(50, d.w + (ev.clientX - d.x)) })); };
    const up = () => { drag.current = null; window.removeEventListener("mousemove", move); window.removeEventListener("mouseup", up); };
    window.addEventListener("mousemove", move); window.addEventListener("mouseup", up);
  };

  // 筛选 + 排序(打卡人员在前,免打卡在后)
  const rows = useMemo(() => {
    const kw = q.trim();
    const f = items.filter((r) => {
      if (kw && !r.name.includes(kw)) return false;
      if (status) {
        const k = statusOf(r).kind;
        if (status === "leave") { if (!(r.leave_h > 0)) return false; }
        else if (k !== status) return false;
      }
      return true;
    });
    const a = f.filter((x) => x.scheduled > 0), b = f.filter((x) => x.scheduled === 0);
    return [...a, ...b];
  }, [items, q, status]);

  const shownCols = useMemo(() => COLS.filter((c) => visible[c.k]), [visible]);

  function exportCsv() {
    const cs = shownCols;
    const head = cs.map((c) => c.label);
    const val = (r: Item, k: string): string | number => k === "status" ? statusOf(r).text : (r as any)[k];
    const lines = [head.join(",")].concat(rows.map((r) => cs.map((c) => val(r, c.k)).join(",")));
    const blob = new Blob(["﻿" + lines.join("\n")], { type: "text/csv;charset=utf-8" });
    const a = document.createElement("a"); a.href = URL.createObjectURL(blob); a.download = "考勤核算_" + (month || "") + ".csv"; a.click();
  }
  function openHelp() { if (onNavigate) onNavigate("help"); window.location.hash = "#/help?page=" + PAGE_KEY; }

  const cell: React.CSSProperties = { padding: "9px 12px", textAlign: "center", fontSize: "13px", whiteSpace: "nowrap", borderBottom: "1px solid " + C.line, fontVariantNumeric: "tabular-nums", overflow: "hidden", textOverflow: "ellipsis" };
  function renderCell(r: Item, k: string): React.ReactNode {
    const mut = (v: number) => v || <span style={{ color: C.muted }}>0</span>;
    switch (k) {
      case "name": return <span style={{ fontWeight: 600 }}>{r.name}</span>;
      case "scheduled": return mut(r.scheduled);
      case "present": return mut(r.present);
      case "late": return <span style={{ color: r.late ? C.amber : C.muted, fontWeight: r.late ? 700 : 400 }}>{r.late}</span>;
      case "early": return <span style={{ color: r.early ? C.amber : C.muted }}>{r.early}</span>;
      case "lack": return <span style={{ color: r.lack ? C.orange : C.muted }}>{r.lack}</span>;
      case "absent": return <span style={{ color: r.absent ? C.red : C.muted, fontWeight: r.absent ? 700 : 400 }}>{r.absent}</span>;
      case "leave_h": return <span style={{ color: r.leave_h ? C.blue : C.muted }}>{r.leave_h || 0}</span>;
      case "overtime_h": return <span style={{ color: r.overtime_h ? C.ink : C.muted }}>{r.overtime_h || 0}</span>;
      case "rate": return <span style={{ fontWeight: 700, color: r.scheduled === 0 ? C.muted : r.rate >= 100 ? C.green : r.rate >= 90 ? C.ink : C.red }}>{r.scheduled === 0 ? "-" : r.rate + "%"}</span>;
      case "status": { const s = statusOf(r); return <Badge text={s.text} fg={s.fg} bg={s.bg} />; }
      default: return null;
    }
  }

  const kpiTiles = kpi ? [
    { v: kpi.people, l: "在册人数" }, { v: kpi.full_attendance, l: "全勤", ok: true }, { v: kpi.abnormal, l: "有异常", bad: true },
    { v: <>{kpi.avg_rate}<span style={{ fontSize: 13, color: C.muted }}>%</span></>, l: "平均出勤率" },
    { v: kpi.late_total, l: "迟到合计(次)" }, { v: kpi.absent_total, l: "旷工合计(天)", bad: true },
  ] : [];
  const hasFilter = !!q.trim() || !!status;

  return (
    <div style={{ padding: "16px 4px 40px", color: C.ink, fontSize: "13.5px" }}>
      <style>{".lx-cr{position:absolute;top:0;right:0;height:100%;width:9px;cursor:col-resize;user-select:none;}.lx-cr::after{content:'';position:absolute;right:4px;top:22%;height:56%;width:2px;background:#dadce0;border-radius:1px;}.lx-cr:hover::after{background:#1a73e8;top:0;height:100%;}"}</style>

      <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 12 }}>
        <div style={{ fontSize: 17, fontWeight: 700 }}>考勤 · 月度核算</div>
        <span style={{ fontSize: 12, color: C.muted }}>数据源：飞书假勤（熵基打卡）· 只读</span>
      </div>

      {/* 筛选栏(§1 标准) */}
      <div style={{ ...(lxTB.filterWrap as React.CSSProperties), display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
        <select value={month} onChange={(e) => setMonth(e.target.value)} style={lxTB.filterSelect as React.CSSProperties}>
          {months.length === 0 && <option value="">(暂无)</option>}
          {months.map((m) => <option key={m} value={m}>{m}</option>)}
        </select>
        <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="搜索姓名" style={lxTB.filterInput as React.CSSProperties} />
        <select value={status} onChange={(e) => setStatus(e.target.value)} style={lxTB.filterSelect as React.CSSProperties}>
          {STATUS_OPTS.map((o) => <option key={o.v} value={o.v}>{o.l}</option>)}
        </select>
        {hasFilter && <button style={lxTB.resetBtn as React.CSSProperties} onClick={() => { setQ(""); setStatus(""); }}>重置筛选</button>}
        {hasFilter && <span style={{ fontSize: 12, color: C.primary, fontWeight: 600 }}>● 筛选生效</span>}
      </div>

      {/* 工具条(§1 元信息 + 图标组) */}
      <div style={{ display: "flex", alignItems: "center", gap: 8, margin: "12px 0" }}>
        <span style={{ flex: 1 }} />
        <span style={{ fontSize: 12, color: C.muted, whiteSpace: "nowrap", marginRight: 4 }}>
          共 <b style={{ color: C.ink2 }}>{rows.length}</b> 行 · 同步 <b style={{ color: C.ink2 }}>{sync || "—"}</b> · 第 <b style={{ color: C.ink2 }}>1</b>/1 页
        </span>
        <button style={lxTB.iconBtn} title="刷新" onClick={() => load(month)}><IconRefresh /></button>
        <button style={lxTB.iconBtn} title="帮助" onClick={openHelp}><IconHelp /></button>
        <button style={lxTB.iconBtn} title="导出CSV" onClick={exportCsv}><IconDownload /></button>
        <div style={{ position: "relative", display: "inline-flex" }}>
          <button style={lxTB.iconBtn} title="列配置" onClick={() => setShowColCfg((v) => !v)}><IconColumns /></button>
          {showColCfg && (
            <div style={{ position: "absolute", top: 30, right: 0, zIndex: 20, ...card, boxShadow: "0 4px 16px rgba(0,0,0,.14)", padding: "8px 4px", minWidth: 150 }}>
              <div style={{ fontSize: 12, color: C.muted, padding: "2px 10px 6px" }}>显示列</div>
              {COLS.map((c) => (
                <label key={c.k} style={{ display: "flex", alignItems: "center", gap: 8, padding: "5px 10px", fontSize: 13, cursor: c.lock ? "default" : "pointer", color: c.lock ? C.muted : C.ink }}>
                  <input type="checkbox" checked={!!visible[c.k]} disabled={c.lock} onChange={(e) => setVisible((p) => ({ ...p, [c.k]: e.target.checked }))} />
                  {c.label}{c.lock ? "（固定）" : ""}
                </label>
              ))}
              <div style={{ borderTop: "1px solid " + C.line, marginTop: 4, paddingTop: 4, display: "flex", gap: 6, padding: "6px 10px 2px" }}>
                <button style={{ ...(lxTB.resetBtn as React.CSSProperties), padding: "3px 8px", fontSize: 12 }} onClick={() => setVisible(Object.fromEntries(ALL_KEYS.map((k) => [k, true])))}>全显示</button>
                <button style={{ ...(lxTB.resetBtn as React.CSSProperties), padding: "3px 8px", fontSize: 12 }} onClick={() => { setColW({ ...DEFAULT_W }); }}>列宽重置</button>
              </div>
            </div>
          )}
        </div>
      </div>
      <div style={{ fontSize: 12, color: C.muted, marginBottom: 12 }}>拖列头右缘调列宽 · 列配置隐藏/显示列 · 异常行高亮 · 免打卡=管理层/不走打卡机</div>

      {err && <div style={{ ...card, padding: "16px 18px", marginBottom: 16, color: C.red, background: C.redBg, borderColor: "#f5c6c2" }}>{err}</div>}

      {kpi && (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(6,1fr)", gap: 12, marginBottom: 16 }}>
          {kpiTiles.map((k, i) => (
            <div key={i} style={{ ...card, padding: "12px 14px" }}>
              <div style={{ fontSize: 22, fontWeight: 700, color: (k as any).bad ? C.red : (k as any).ok ? C.green : C.ink, fontVariantNumeric: "tabular-nums" }}>{k.v}</div>
              <div style={{ fontSize: 12, color: C.ink2, marginTop: 2 }}>{k.l}</div>
            </div>
          ))}
        </div>
      )}

      <div style={{ ...card, overflow: "hidden" }}>
        <div style={{ overflowX: "auto" }}>
          <table style={{ borderCollapse: "collapse", width: "100%", tableLayout: "fixed", minWidth: 640 }}>
            <colgroup>{shownCols.map((c) => <col key={c.k} style={{ width: (colW[c.k] ?? c.w) + "px" }} />)}</colgroup>
            <thead><tr>
              {shownCols.map((c) => (
                <th key={c.k} style={{ position: "relative", padding: "10px 12px", textAlign: c.left ? "left" : "center", background: C.headBg, color: C.ink2, fontWeight: 600, fontSize: "12px", whiteSpace: "nowrap", borderBottom: "1px solid " + C.line }}>
                  {c.label}<span className="lx-cr" onMouseDown={(e) => onResizeDown(c.k, e)} />
                </th>
              ))}
            </tr></thead>
            <tbody>
              {rows.length === 0 && (<tr><td style={{ ...cell, textAlign: "center", color: C.muted }} colSpan={shownCols.length}>暂无数据{hasFilter ? "（筛选无匹配）" : ""}</td></tr>)}
              {rows.map((r) => {
                const abn = r.absent > 0 || r.lack > 0; const warn = r.late > 0 || r.early > 0;
                return (
                  <tr key={r.open_id} style={{ background: abn ? C.redBg : warn ? "#fffdf6" : "#fff" }}>
                    {shownCols.map((c) => (<td key={c.k} style={{ ...cell, textAlign: c.left ? "left" : "center" }}>{renderCell(r, c.k)}</td>))}
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>

      <div style={{ marginTop: 12, fontSize: 12, color: C.muted, lineHeight: 1.7 }}>
        口径：应出勤=飞书排班工作日（大小周由排班定，公司非工作日已排除）；实出勤=排班日有打卡；
        加班=下班后额外打卡超时（无加班审批，纯打卡口径）；免打卡=管理层/不走打卡机（不计应出勤）。
      </div>
    </div>
  );
}
