/**
 * LxMultiSelect.tsx - 领星式多选筛选（2026-07-21 自 FeishuRawSalesData 提取为共享组件，
 * 实现逐字保持一致：全选/搜索/仅筛选此项/取消确定）。供 PmcCenter / ClearanceCenter 复用；
 * FeishuRawSalesData 内嵌版本保持不动（分叉文件不整改）。
 */
import { useEffect, useRef, useState } from "react";

export default function LxMultiSelect({ placeholder, options, selected, onChange, minWidth = 140, menuMinWidth = 230 }: {
  placeholder: string;
  options: Array<{ value: string; label: string }>;
  selected: string[];
  onChange: (v: string[]) => void;
  minWidth?: number;
  /** 下拉菜单最小宽度（可选，默认 230 与历史行为一致；长选项文本的页面可调宽避免截断，2026-08-19 加） */
  menuMinWidth?: number;
}) {
  const [open, setOpen] = useState(false);
  const [pending, setPending] = useState<string[]>(selected);
  const [kw, setKw] = useState("");
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => { if (open) { setPending(selected); setKw(""); } }, [open, selected]);
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  const shown = options.filter(o => !kw || o.label.includes(kw) || o.value.includes(kw));
  const allChecked = shown.length > 0 && shown.every(o => pending.includes(o.value));
  const toggleAll = () => setPending(allChecked
    ? pending.filter(v => !shown.some(o => o.value === v))
    : Array.from(new Set([...pending, ...shown.map(o => o.value)])));
  const toggleOne = (v: string) =>
    setPending(prev => prev.includes(v) ? prev.filter(x => x !== v) : [...prev, v]);

  const selLabel = (v: string) => options.find(o => o.value === v)?.label ?? v;
  const label = selected.length === 0 ? placeholder :
    selected.length === 1 ? selLabel(selected[0]) :
    `${selLabel(selected[0])} 等${selected.length}项`;

  return (
    <div ref={ref} style={{ position: "relative" }}>
      <button onClick={() => setOpen(o => !o)}
        style={{ border: "1px solid #d1d5db", borderRadius: 6, padding: "5px 26px 5px 10px",
          fontSize: 13, background: "#fff", cursor: "pointer", minWidth, textAlign: "left", position: "relative",
          color: selected.length ? "#111" : "#9ca3af" }}>
        {label}
        <span style={{ position: "absolute", right: 8, top: "50%", transform: "translateY(-50%)", color: "#9ca3af" }}>▾</span>
      </button>
      {open && (
        <div style={{ position: "absolute", top: "110%", left: 0, background: "#fff",
          border: "1px solid #e2e8f0", borderRadius: 8, boxShadow: "0 6px 20px rgba(0,0,0,.14)",
          zIndex: 120, minWidth: menuMinWidth, display: "flex", flexDirection: "column" }}>
          {options.length > 8 && (
            <div style={{ padding: "8px 10px 4px" }}>
              <input placeholder="搜索…" value={kw} onChange={e => setKw(e.target.value)}
                style={{ width: "100%", boxSizing: "border-box", border: "1px solid #d1d5db",
                  borderRadius: 6, padding: "5px 8px", fontSize: 12 }} />
            </div>
          )}
          <div style={{ maxHeight: 260, overflowY: "auto", padding: "4px 0" }}>
            <label style={{ display: "flex", alignItems: "center", gap: 8, padding: "6px 12px",
              cursor: "pointer", fontSize: 13, borderBottom: "1px solid #f1f5f9" }}>
              <input type="checkbox" checked={allChecked} onChange={toggleAll} />
              全选
            </label>
            {shown.map(o => (
              <div key={o.value}
                style={{ display: "flex", alignItems: "center", gap: 8, padding: "6px 12px", fontSize: 13 }}
                onMouseEnter={e => {
                  (e.currentTarget as HTMLElement).style.background = "#f0f7ff";
                  const only = (e.currentTarget as HTMLElement).querySelector("[data-only]") as HTMLElement | null;
                  if (only) only.style.visibility = "visible";
                }}
                onMouseLeave={e => {
                  (e.currentTarget as HTMLElement).style.background = "transparent";
                  const only = (e.currentTarget as HTMLElement).querySelector("[data-only]") as HTMLElement | null;
                  if (only) only.style.visibility = "hidden";
                }}>
                <input type="checkbox" checked={pending.includes(o.value)} onChange={() => toggleOne(o.value)}
                  style={{ cursor: "pointer" }} />
                <span style={{ flex: 1, cursor: "pointer", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}
                  title={o.label} onClick={() => toggleOne(o.value)}>{o.label}</span>
                <span data-only style={{ visibility: "hidden", color: "#2563eb", fontSize: 12, cursor: "pointer", flexShrink: 0 }}
                  onClick={() => setPending([o.value])}>仅筛选此项</span>
              </div>
            ))}
            {shown.length === 0 && <div style={{ padding: "10px 12px", fontSize: 12, color: "#94a3b8" }}>无匹配项</div>}
          </div>
          <div style={{ display: "flex", gap: 8, justifyContent: "flex-end", padding: "8px 10px",
            borderTop: "1px solid #f1f5f9" }}>
            <button onClick={() => setOpen(false)}
              style={{ padding: "4px 14px", border: "1px solid #d1d5db", borderRadius: 6, background: "#fff",
                cursor: "pointer", fontSize: 12 }}>取消</button>
            <button onClick={() => { onChange(pending); setOpen(false); }}
              style={{ padding: "4px 14px", border: "none", borderRadius: 6, background: "#2563eb",
                color: "#fff", cursor: "pointer", fontSize: 12, fontWeight: 600 }}>确定</button>
          </div>
        </div>
      )}
    </div>
  );
}
