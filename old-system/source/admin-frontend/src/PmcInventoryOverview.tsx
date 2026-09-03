/**
 * PmcInventoryOverview.tsx - 智能PMC · 库存一览表（2026-08-03，隔离新组件，只读）
 * 维度 ITEMID→MSKU×店铺；库存数量 = 已采购 + 本地仓库 + 在途 + WFS在库；非WFS 独立展示。本期仅数量。
 * UI 遵循 context/UI_STANDARDS：§1 工具条(元信息+刷新/帮助/下载/列配置) · §2 帮助壳内 · §5 列宽拖动+重置+提示 · §6 KPI可隐藏。
 * 数据源 /api/pmc/inventory/overview（挂 /api/pmc/ 下复用现有 nginx 代理）。
 */
import { useEffect, useMemo, useRef, useState } from "react";
import LxMultiSelect from "./LxMultiSelect";
import { ItemIdLink } from "./ItemIdLink";
import { lxTB, IconRefresh, IconHelp, IconDownload, IconColumns } from "./LxToolbar";

interface Child { store_id: string; store_name: string; msku: string; in_transit: number; wfs: number; non_wfs: number; }
interface Group {
  item_id: string; sku: string; owner: string; is_clearance: number;
  alloc_local: number; alloc_po: number;
  in_transit_sum: number; wfs_sum: number; non_wfs_sum: number; inv_qty: number; children: Child[];
}
interface Kpi { item_count: number; listing_rows: number; inv_qty_total: number; wfs_total: number; non_wfs_total: number; in_transit_total: number; }

const C = { blue: "#1a73e8", blueTxt: "#1967d2", txt: "#202124", txt2: "#5f6368", txt3: "#9aa0a6", line: "#dadce0", neg: "#d93025", purple: "#8430ce" };
const card: React.CSSProperties = { background: "#fff", border: "1px solid #e5e7eb", borderRadius: "10px" };
const iconBtnWrap: React.CSSProperties = { width: "30px", height: "30px", display: "inline-flex", alignItems: "center", justifyContent: "center", border: `1px solid ${C.line}`, borderRadius: "6px", background: "#fff", cursor: "pointer" };
const nfmt = (n: number): string => (Math.round(n)).toLocaleString();
const PAGE_SIZES = [50, 100, 200];
const pageBtn = (active: boolean, disabled: boolean): React.CSSProperties => ({ padding: "5px 12px", borderRadius: "5px", border: "1px solid #e5e7eb", cursor: disabled ? "not-allowed" : "pointer", background: active ? "#6366f1" : "#fff", color: active ? "#fff" : "#374151", fontWeight: active ? 700 : 400, fontSize: "13px", opacity: disabled ? 0.5 : 1 });

type ColKey = "id" | "store" | "owner" | "po" | "local" | "transit" | "wfs" | "invqty" | "nonwfs";
const COLS: { key: ColKey; label: string; w: number; align: "left" | "right"; hideable: boolean; sortable: boolean; sortField?: keyof Group }[] = [
  { key: "id", label: "MSKU / SKU", w: 240, align: "left", hideable: false, sortable: false },
  { key: "store", label: "店铺", w: 150, align: "left", hideable: true, sortable: false },
  { key: "owner", label: "负责人", w: 90, align: "left", hideable: true, sortable: false },
  { key: "po", label: "已采购", w: 90, align: "right", hideable: true, sortable: true, sortField: "alloc_po" },
  { key: "local", label: "本地仓库", w: 90, align: "right", hideable: true, sortable: true, sortField: "alloc_local" },
  { key: "transit", label: "在途", w: 80, align: "right", hideable: true, sortable: true, sortField: "in_transit_sum" },
  { key: "wfs", label: "WFS在库", w: 90, align: "right", hideable: true, sortable: true, sortField: "wfs_sum" },
  { key: "invqty", label: "库存数量", w: 100, align: "right", hideable: true, sortable: true, sortField: "inv_qty" },
  { key: "nonwfs", label: "非WFS(独立)", w: 96, align: "right", hideable: true, sortable: true, sortField: "non_wfs_sum" },
];

export default function PmcInventoryOverview({ onNavigate }: { onNavigate?: (key: string) => void }) {
  const [groups, setGroups] = useState<Group[]>([]);
  const [kpi, setKpi] = useState<Kpi | null>(null);
  const [stores, setStores] = useState<string[]>([]);
  const [owners, setOwners] = useState<string[]>([]);
  const [fStore, setFStore] = useState<string[]>([]);
  const [fOwner, setFOwner] = useState<string[]>([]);
  const [kw, setKw] = useState("");
  const [loading, setLoading] = useState(false);
  const [msg, setMsg] = useState("");
  const [showKpi, setShowKpi] = useState(true);
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set());
  const [syncedAt, setSyncedAt] = useState("");
  const [visible, setVisible] = useState<Set<ColKey>>(new Set(COLS.map((c) => c.key)));
  const [showColCfg, setShowColCfg] = useState(false);
  const [colWidths, setColWidths] = useState<Record<string, number>>({});
  const [sortKey, setSortKey] = useState<keyof Group | "">("inv_qty");
  const [sortDir, setSortDir] = useState<1 | -1>(-1);
  const [pageSize, setPageSize] = useState(50);
  const [page, setPage] = useState(1);
  const resizeRef = useRef<{ col: string; startX: number; startW: number } | null>(null);

  useEffect(() => {
    if (typeof document !== "undefined" && !document.getElementById("lx-colresize-css")) {
      const st = document.createElement("style");
      st.id = "lx-colresize-css";
      st.textContent =
        ".lx-colresize{position:absolute;top:0;right:-4px;width:9px;height:100%;cursor:col-resize;user-select:none;z-index:3;display:flex;align-items:center;justify-content:center}" +
        ".lx-colresize::after{content:'';width:2px;height:56%;background:#dadce0;border-radius:1px;transition:background .12s,height .12s,width .12s}" +
        ".lx-colresize:hover::after{background:#1a73e8;width:3px;height:100%}" +
        ".lxinv-row:hover td{background:#eef2ff}";
      document.head.appendChild(st);
    }
    const onMove = (e: MouseEvent): void => {
      const r = resizeRef.current; if (!r) return;
      const w = Math.max(60, r.startW + (e.clientX - r.startX));
      setColWidths((prev) => ({ ...prev, [r.col]: w }));
    };
    const onUp = (): void => { resizeRef.current = null; document.body.style.cursor = ""; };
    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onUp);
    return () => { window.removeEventListener("mousemove", onMove); window.removeEventListener("mouseup", onUp); };
  }, []);

  const load = async (): Promise<void> => {
    setLoading(true); setMsg("");
    try {
      const qs = new URLSearchParams();
      if (fStore.length === 1) qs.set("store", fStore[0]);
      if (fOwner.length === 1) qs.set("owner", fOwner[0]);
      if (kw.trim()) qs.set("kw", kw.trim());
      const res = await fetch(`/api/pmc/inventory/overview?${qs.toString()}`);
      const data = await res.json();
      if (!data.ok) { setMsg(data.error || "加载失败"); setGroups([]); setKpi(null); return; }
      setGroups(data.groups ?? []); setKpi(data.kpi ?? null);
      setStores(data.stores ?? []); setOwners(data.owners ?? []);
      setSyncedAt(new Date().toLocaleString("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" }));
    } catch (e) { setMsg(e instanceof Error ? e.message : String(e)); setGroups([]); setKpi(null); }
    finally { setLoading(false); }
  };
  useEffect(() => { void load(); /* eslint-disable-next-line */ }, []);

  const view = useMemo(() => {
    let out = groups.slice();
    if (fStore.length) out = out.filter((g) => g.children.some((c) => fStore.includes(c.store_name)));
    if (fOwner.length) out = out.filter((g) => fOwner.includes(g.owner));
    const k = kw.trim().toLowerCase();
    if (k) out = out.filter((g) => g.item_id.toLowerCase().includes(k) || g.sku.toLowerCase().includes(k) || g.children.some((c) => c.msku.toLowerCase().includes(k)));
    if (sortKey) out.sort((a, b) => ((a[sortKey] as number) - (b[sortKey] as number)) * sortDir);
    return out;
  }, [groups, fStore, fOwner, kw, sortKey, sortDir]);

  const totalPages = Math.max(1, Math.ceil(view.length / pageSize));
  useEffect(() => { setPage(1); }, [fStore, fOwner, kw, sortKey, sortDir, pageSize]);
  useEffect(() => { if (page > totalPages) setPage(totalPages); }, [page, totalPages]);
  const pagedView = view.slice((page - 1) * pageSize, page * pageSize);
  const totals = useMemo(() => view.reduce((t, g) => ({
    po: t.po + g.alloc_po, local: t.local + g.alloc_local, transit: t.transit + g.in_transit_sum,
    wfs: t.wfs + g.wfs_sum, invqty: t.invqty + g.inv_qty, nonwfs: t.nonwfs + g.non_wfs_sum,
  }), { po: 0, local: 0, transit: 0, wfs: 0, invqty: 0, nonwfs: 0 }), [view]);

  const cols = COLS.filter((c) => visible.has(c.key));
  const tableW = cols.reduce((a, c) => a + (colWidths[c.key] ?? c.w), 0);
  const toggle = (id: string): void => setCollapsed((p) => { const s = new Set(p); s.has(id) ? s.delete(id) : s.add(id); return s; });
  const onSort = (col: typeof COLS[number]): void => {
    if (!col.sortable || !col.sortField) return;
    if (sortKey === col.sortField) setSortDir((d) => (d === 1 ? -1 : 1));
    else { setSortKey(col.sortField); setSortDir(-1); }
  };
  const startResize = (e: React.MouseEvent, key: string, th: HTMLElement): void => {
    e.preventDefault(); e.stopPropagation();
    resizeRef.current = { col: key, startX: e.clientX, startW: th.getBoundingClientRect().width };
    document.body.style.cursor = "col-resize";
  };
  const openHelp = (): void => {
    onNavigate?.("help");
    try { window.location.hash = "#/help?page=pmc-inventory"; } catch { /* noop */ }
  };
  const exportCsv = (): void => {
    const header = ["层级", "ITEMID/MSKU", "SKU", "店铺", "负责人", "已采购", "本地仓库", "在途", "WFS在库", "库存数量", "非WFS"];
    const rows: (string | number)[][] = [header];
    for (const g of view) {
      rows.push(["组", g.item_id, g.sku, `${g.children.length}店铺`, g.owner, g.alloc_po, g.alloc_local, g.in_transit_sum, g.wfs_sum, g.inv_qty, g.non_wfs_sum]);
      for (const c of g.children) rows.push(["明细", c.msku, g.sku, c.store_name, g.owner, "", "", c.in_transit, c.wfs, c.in_transit + c.wfs, c.non_wfs]);
    }
    const csv = "﻿" + rows.map((r) => r.map((v) => `"${String(v).replace(/"/g, '""')}"`).join(",")).join("\n");
    const a = document.createElement("a");
    a.href = URL.createObjectURL(new Blob([csv], { type: "text/csv;charset=utf-8" }));
    a.download = `库存一览表_${syncedAt || "export"}.csv`;
    a.click(); URL.revokeObjectURL(a.href);
  };

  const poTotal = groups.reduce((a, g) => a + g.alloc_po, 0);
  const kpiCards = kpi ? [
    { lbl: "商品数 (ITEMID)", val: kpi.item_count, bg: "#e8f0fe", fg: C.blueTxt },
    { lbl: "已采购总数", val: poTotal, bg: "#e8eaf6", fg: "#3949ab" },
    { lbl: "库存总件数", val: kpi.inv_qty_total, bg: "#e6f4ea", fg: "#188038" },
    { lbl: "WFS在库件数", val: kpi.wfs_total, bg: "#e8f0fe", fg: C.blueTxt },
    { lbl: "在途件数", val: kpi.in_transit_total, bg: "#fef7e0", fg: "#b06000" },
    { lbl: "非WFS件数 (独立)", val: kpi.non_wfs_total, bg: "#f3e8fd", fg: C.purple },
  ] : [];

  const totalChildRows = view.reduce((a, g) => a + g.children.length, 0);

  const cellStyle = (align: "left" | "right", extra?: React.CSSProperties): React.CSSProperties =>
    ({ textAlign: align, padding: "7px 10px", fontSize: "12px", borderTop: "1px solid #f3f4f6", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis", fontVariantNumeric: "tabular-nums", ...extra });

  const groupCell = (g: Group, col: ColKey): React.ReactNode => {
    switch (col) {
      case "id": return (<><span style={{ color: C.blue, marginRight: "4px" }}>{collapsed.has(g.item_id) ? "▸" : "▾"}</span><ItemIdLink itemId={g.item_id} /><span style={{ color: C.txt3, marginLeft: "8px", fontSize: "11px" }}>SKU {g.sku || "—"}</span></>);
      case "store": return g.is_clearance === 1 ? <span style={{ background: "#dbeafe", color: "#1d4ed8", borderRadius: "9px", padding: "1px 8px", fontSize: "11px" }}>清货期</span> : (g.children.length > 1 ? <span style={{ color: C.txt3, fontSize: "11px" }}>{g.children.length} 店铺</span> : "");
      case "owner": return <span style={{ color: C.txt2 }}>👤 {g.owner || "—"}</span>;
      case "po": return nfmt(g.alloc_po);
      case "local": return nfmt(g.alloc_local);
      case "transit": return nfmt(g.in_transit_sum);
      case "wfs": return <span style={{ color: g.wfs_sum === 0 ? C.neg : undefined }}>{nfmt(g.wfs_sum)}</span>;
      case "invqty": return <b>{nfmt(g.inv_qty)}</b>;
      case "nonwfs": return <span style={{ color: C.purple }}>{nfmt(g.non_wfs_sum)}</span>;
    }
  };
  const childCell = (g: Group, c: Child, col: ColKey): React.ReactNode => {
    switch (col) {
      case "id": return <span style={{ fontWeight: 600 }}>{c.msku}</span>;
      case "store": return <span style={{ color: C.txt2 }}>{c.store_name || "—"}</span>;
      case "owner": return <span style={{ color: C.txt2 }}>{g.owner || "—"}</span>;
      case "po": case "local": return <span style={{ color: C.txt3 }}>—</span>;
      case "transit": return nfmt(c.in_transit);
      case "wfs": return <span style={{ color: c.wfs === 0 ? C.neg : undefined }}>{nfmt(c.wfs)}</span>;
      case "invqty": return <b>{nfmt(c.in_transit + c.wfs)}</b>;
      case "nonwfs": return <span style={{ color: C.purple }}>{nfmt(c.non_wfs)}</span>;
    }
  };

  return (
    <div>
      <p style={{ color: C.txt2, margin: "0 0 12px", fontSize: "12px", lineHeight: 1.6 }}>
        维度 ITEMID→MSKU×店铺。库存数量 = 已采购 + 本地仓库 + 在途 + WFS在库；非WFS 独立、只展示不计入库存数量。
        本地仓库/已采购为本地SKU级共享池（近30天销量分摊到 ITEMID，挂组头）；在途/WFS/非WFS 为店铺级（摊到子行）。本期不含成本/货值。
      </p>

      <div style={{ ...lxTB.filterWrap, display: "flex", alignItems: "center", gap: "10px", flexWrap: "wrap" }}>
        <LxMultiSelect placeholder="全部店铺" minWidth={150} options={stores.map((s) => ({ value: s, label: s }))} selected={fStore} onChange={setFStore} />
        <LxMultiSelect placeholder="全部负责人" minWidth={130} options={owners.map((s) => ({ value: s, label: s }))} selected={fOwner} onChange={setFOwner} />
        <input placeholder="搜索 ITEMID / MSKU / SKU…" value={kw} onChange={(e) => setKw(e.target.value)}
          style={{ ...lxTB.filterInput, width: "220px" }} onKeyDown={(e) => { if (e.key === "Enter") void load(); }} />
        <span style={{ color: C.txt2, fontSize: "12px" }}>共 {view.length} 商品 · {totalChildRows} 行 · 同步 {syncedAt || "-"} · 第 {page}/{totalPages} 页</span>
        <div style={{ flex: 1 }} />
        <button style={iconBtnWrap} title="隐藏 / 显示 顶部KPI" onClick={() => setShowKpi((v) => !v)}><span style={{ color: C.txt2, fontSize: "14px" }}>▤</span></button>
        <button style={{ ...lxTB.iconBtn, ...iconBtnWrap }} title="刷新" onClick={() => void load()} disabled={loading}><IconRefresh /></button>
        <button style={{ ...lxTB.iconBtn, ...iconBtnWrap }} title="帮助" onClick={openHelp}><IconHelp /></button>
        <button style={{ ...lxTB.iconBtn, ...iconBtnWrap }} title="下载 CSV（当前筛选）" onClick={exportCsv}><IconDownload /></button>
        <button style={{ ...lxTB.iconBtn, ...iconBtnWrap }} title="列配置" onClick={() => setShowColCfg(true)}><IconColumns /></button>
      </div>

      <div style={{ fontSize: "11px", color: C.txt3, margin: "-4px 0 10px" }}>
        拖列头右缘调列宽 · 点值列表头排序（↑↓⇅）· ▤ 收起顶部KPI · 组头可折叠 ·
        <span style={{ color: C.blue, cursor: "pointer", marginLeft: "4px" }} onClick={() => setColWidths({})}>列宽重置</span>
      </div>

      {showKpi && kpiCards.length > 0 && (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(130px, 1fr))", gap: "10px", marginBottom: "12px" }}>
          {kpiCards.map((k) => (
            <div key={k.lbl} style={{ background: k.bg, borderRadius: "10px", padding: "10px 12px" }}>
              <div style={{ fontSize: "12px", color: k.fg }}>{k.lbl}</div>
              <div style={{ fontSize: "22px", fontWeight: 700, color: k.fg }}>{nfmt(k.val)}</div>
            </div>
          ))}
        </div>
      )}

      {msg && <div style={{ ...card, padding: "10px 14px", color: C.neg, marginBottom: "10px" }}>{msg}</div>}

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

      <div style={{ ...card, padding: 0, overflow: "auto", maxHeight: "64vh" }}>
        <table style={{ width: tableW, minWidth: "100%", borderCollapse: "collapse", tableLayout: "fixed" }}>
          <colgroup>{cols.map((c) => <col key={c.key} style={{ width: (colWidths[c.key] ?? c.w) + "px" }} />)}</colgroup>
          <thead>
            <tr>
              {cols.map((col) => {
                const active = col.sortField && sortKey === col.sortField;
                return (
                  <th key={col.key} onClick={() => onSort(col)}
                    style={{ position: "sticky", top: 0, zIndex: 5, textAlign: col.align, padding: "8px 10px", fontSize: "12px", color: C.txt2, background: "#f9fafb", whiteSpace: "nowrap", cursor: col.sortable ? "pointer" : "default", userSelect: "none", boxShadow: "inset 0 -1px 0 #e5e7eb" }}>
                    {col.label}
                    {col.sortable && <span style={{ color: active ? C.blue : "#c7cbd4", marginLeft: "3px" }}>{active ? (sortDir === 1 ? "↑" : "↓") : "⇅"}</span>}
                    <span className="lx-colresize" onMouseDown={(e) => startResize(e, col.key, e.currentTarget.parentElement as HTMLElement)} onClick={(e) => e.stopPropagation()} />
                  </th>
                );
              })}
            </tr>
          </thead>
          <tbody>
            {pagedView.map((g) => {
              const open = !collapsed.has(g.item_id);
              return (
                <>
                  <tr key={g.item_id} onClick={() => toggle(g.item_id)} style={{ cursor: "pointer" }}>
                    {cols.map((col, i) => (
                      <td key={col.key} style={cellStyle(col.align, { background: "#f8faff", borderTop: "1px solid #e3e9f7", fontWeight: 600, borderLeft: col.key === "invqty" ? "1px solid #eceef1" : undefined })}>{groupCell(g, col.key)}</td>
                    ))}
                  </tr>
                  {open && g.children.map((c) => (
                    <tr className="lxinv-row" key={`${g.item_id}-${c.store_id}-${c.msku}`}>
                      {cols.map((col) => (
                        <td key={col.key} style={cellStyle(col.align, { borderLeft: col.key === "invqty" ? "1px solid #eceef1" : undefined })}>{childCell(g, c, col.key)}</td>
                      ))}
                    </tr>
                  ))}
                </>
              );
            })}
            {!view.length && !loading && (
              <tr><td style={{ ...cellStyle("left"), textAlign: "center", color: C.txt2 }} colSpan={cols.length}>无数据</td></tr>
            )}
          </tbody>
          {view.length > 0 && (
            <tfoot>
              <tr>
                {cols.map((col) => (
                  <td key={col.key} style={{ position: "sticky", bottom: 0, zIndex: 4, background: "#eef2ff", fontWeight: 700, color: "#3730a3", borderTop: "2px solid #c7d2fe", textAlign: col.align, padding: "8px 10px", fontSize: "12px", whiteSpace: "nowrap", fontVariantNumeric: "tabular-nums" }}>
                    {col.key === "id" ? `总计（${view.length} 商品）`
                      : col.key === "po" ? nfmt(totals.po)
                      : col.key === "local" ? nfmt(totals.local)
                      : col.key === "transit" ? nfmt(totals.transit)
                      : col.key === "wfs" ? nfmt(totals.wfs)
                      : col.key === "invqty" ? nfmt(totals.invqty)
                      : col.key === "nonwfs" ? nfmt(totals.nonwfs)
                      : ""}
                  </td>
                ))}
              </tr>
            </tfoot>
          )}
        </table>
      </div>

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
        <span style={{ fontSize: "12px", color: C.txt3 }}>共 {view.length} 商品</span>
        <span style={{ fontSize: "12px", color: C.txt3 }}>跳至</span>
        <input type="number" min={1} max={totalPages} defaultValue={page} style={{ ...lxTB.filterInput, width: "60px", padding: "4px 8px" }}
          onKeyDown={(e) => { if (e.key === "Enter") { const v = Number((e.target as HTMLInputElement).value); if (v >= 1 && v <= totalPages) setPage(v); } }} />
        <span style={{ fontSize: "12px", color: C.txt3 }}>页</span>
      </div>

      <div style={{ fontSize: "12px", color: C.txt2, marginTop: "8px", lineHeight: 1.6 }}>
        口径：库存数量 = 已采购 + 本地仓库 + 在途 + WFS在库；非WFS 独立不计入。
        已采购/本地仓库为本地SKU级共享池（近30天销量分摊，1:1直归·全0均摊，挂组头）；在途=未完结货件Σ(申报−签收)、WFS/非WFS 取最新快照，均按 MSKU×店铺摊到子行。
        已排除虚拟品(XY2007)与CS测品(msku CS开头)。本期仅数量，成本/货值后续接入。
      </div>
    </div>
  );
}
