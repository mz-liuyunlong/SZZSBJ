/**
 * LxDateRange.tsx — 领星式日期范围选择器共享件（2026-08-18 自 FeishuRawSalesData.tsx:584 提取，逐字一致）
 * 规范：所有列表页日期筛选一律用本件（快捷项+双月历+点选起止日），禁止各页用原生 <input type="date">。
 * FeishuRawSalesData 内嵌版本保持不动（分叉大文件不整改，同 LxToolbar 策略）。
 */
import { useEffect, useRef, useState } from "react";

export function fmtDateYmd(d: Date): string {
  const p = (x: number) => String(x).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
}

export const DATE_QUICK_OPTIONS = [
  { label: "今天", days: 1 },
  { label: "近5天", days: 5 },
  { label: "近7天", days: 7 },
  { label: "近15天", days: 15 },
  { label: "近30天", days: 30 },
  { label: "本月", days: -1 },
];

export function DateRangePicker({ start, end, quickOptions, activeQuick, onQuick, onRange }: {
  start: string; end: string;
  quickOptions: Array<{ days: number; label: string }>;
  activeQuick: number | null;
  onQuick: (days: number) => void;
  onRange: (start: string, end: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const [viewMonth, setViewMonth] = useState<Date>(() => {
    const base = end ? new Date(`${end}T00:00:00`) : new Date();
    return new Date(base.getFullYear(), base.getMonth() - 1, 1); // 左月=结束月的上一月
  });
  const [pendStart, setPendStart] = useState<string>("");
  const wrapRef = useRef<HTMLSpanElement>(null);

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (wrapRef.current && !wrapRef.current.contains(e.target as Node)) { setOpen(false); setPendStart(""); }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  const pickDay = (ymd: string) => {
    if (!pendStart) { setPendStart(ymd); return; }
    const s = pendStart <= ymd ? pendStart : ymd;
    const e = pendStart <= ymd ? ymd : pendStart;
    setPendStart("");
    setOpen(false);
    onRange(s, e);
  };

  const renderMonth = (base: Date) => {
    const y = base.getFullYear();
    const m = base.getMonth();
    const firstDow = new Date(y, m, 1).getDay();
    const daysInMonth = new Date(y, m + 1, 0).getDate();
    const cells: Array<string | null> = [];
    for (let i = 0; i < firstDow; i++) cells.push(null);
    for (let d = 1; d <= daysInMonth; d++) cells.push(fmtDateYmd(new Date(y, m, d)));
    const inRange = (ymd: string) => {
      const s = pendStart || start;
      const e = pendStart ? "" : end;
      if (pendStart) return ymd === pendStart;
      return s && e && ymd >= s && ymd <= e;
    };
    const isEdge = (ymd: string) => ymd === (pendStart || start) || (!pendStart && ymd === end);
    return (
      <div style={{ width: "224px" }}>
        <div style={{ textAlign: "center", fontSize: "13px", fontWeight: 600, color: "#374151", marginBottom: "4px" }}>
          {y} 年 {m + 1} 月
        </div>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(7, 32px)", fontSize: "12px", color: "#9ca3af", textAlign: "center" }}>
          {["日", "一", "二", "三", "四", "五", "六"].map((w) => <span key={w} style={{ padding: "2px 0" }}>{w}</span>)}
        </div>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(7, 32px)" }}>
          {cells.map((ymd, i) => ymd === null
            ? <span key={`e${i}`} />
            : (
              <button key={ymd} type="button" onClick={() => pickDay(ymd)}
                style={{ border: "none", cursor: "pointer", fontSize: "12px", padding: "5px 0",
                  borderRadius: isEdge(ymd) ? "50%" : 0,
                  background: isEdge(ymd) ? "#6366f1" : inRange(ymd) ? "#eef2ff" : "transparent",
                  color: isEdge(ymd) ? "#fff" : "#374151" }}>
                {Number(ymd.slice(8))}
              </button>
            ))}
        </div>
      </div>
    );
  };

  const nextMonth = new Date(viewMonth.getFullYear(), viewMonth.getMonth() + 1, 1);
  return (
    <span ref={wrapRef} style={{ position: "relative", display: "inline-flex" }}>
      <button type="button" onClick={() => setOpen((v) => !v)}
        style={{ display: "inline-flex", alignItems: "center", gap: "6px", padding: "6px 10px",
          borderRadius: "6px", border: "1px solid #e5e7eb", background: "#fff", fontSize: "13px",
          color: start || end ? "#374151" : "#9ca3af", cursor: "pointer", whiteSpace: "nowrap" }}>
        {start || "开始日期"} <span style={{ color: "#9ca3af" }}>-</span> {end || "结束日期"} <span>📅</span>
      </button>
      {open && (
        <div style={{ position: "absolute", top: "110%", left: 0, zIndex: 60, background: "#fff",
          border: "1px solid #e5e7eb", borderRadius: "10px", boxShadow: "0 8px 24px rgba(0,0,0,0.15)",
          display: "flex", padding: "10px" }}>
          <div style={{ width: "88px", borderRight: "1px solid #f1f5f9", paddingRight: "6px", marginRight: "10px" }}>
            {quickOptions.map((opt) => (
              <div key={opt.days}
                onClick={() => { setOpen(false); setPendStart(""); onQuick(opt.days); }}
                style={{ padding: "6px 8px", fontSize: "12px", cursor: "pointer", borderRadius: "5px",
                  color: activeQuick === opt.days ? "#4f46e5" : "#374151",
                  background: activeQuick === opt.days ? "#eef2ff" : "transparent" }}>
                {opt.label}
              </div>
            ))}
          </div>
          <div>
            <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "2px" }}>
              <button type="button" style={{ border: "none", background: "none", cursor: "pointer", color: "#6b7280" }}
                onClick={() => setViewMonth(new Date(viewMonth.getFullYear(), viewMonth.getMonth() - 1, 1))}>‹</button>
              <span style={{ fontSize: "11px", color: "#94a3b8", alignSelf: "center" }}>
                {pendStart ? `已选起点 ${pendStart}，请选结束日` : "点选开始日与结束日"}
              </span>
              <button type="button" style={{ border: "none", background: "none", cursor: "pointer", color: "#6b7280" }}
                onClick={() => setViewMonth(new Date(viewMonth.getFullYear(), viewMonth.getMonth() + 1, 1))}>›</button>
            </div>
            <div style={{ display: "flex", gap: "14px" }}>
              {renderMonth(viewMonth)}
              {renderMonth(nextMonth)}
            </div>
          </div>
        </div>
      )}
    </span>
  );
}
