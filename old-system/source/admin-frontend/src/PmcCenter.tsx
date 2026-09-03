/**
 * PmcCenter.tsx - AI智能PMC Tab（批④，2026-07-21 需求方定稿）
 * 列：SKU/产品ID/店铺负责人/WFS库存/在途/已采购/7日日销/可卖天数/货件情况(全部未完结)/补货建议/风险
 * 列配置与订单利润一致（勾选/拖拽/置顶/📌固定左冻结/应用重置）
 */
import { cloneElement, useCallback, useEffect, useRef, useState } from "react";
import LxMultiSelect from "./LxMultiSelect";
import { ItemIdLink } from "./ItemIdLink";

interface ShipInfo { id: string; status: string; received: number; declared: number; }
interface Row {
  store_id: string; store_name: string; item_id: string; mskus: string; sku: string; owner: string;
  stock: number; inbound: number;
  procurement: number; procurement_po: number; procurement_local: number; purchase_nearest: string;
  daily7: number; days_to_sell: number | null; shipments: ShipInfo[];
  suggestion: string; suggestion_qty: number; risk: string;
}
interface Kpi { total: number; out_of_stock: number; within7: number; need_replenish: number; inbound_total: number; procurement_total: number; }

const card: React.CSSProperties = { background: "#fff", border: "1px solid #e5e7eb", borderRadius: "10px", padding: "14px 16px", marginBottom: "12px" };
const th: React.CSSProperties = { textAlign: "left", padding: "8px 10px", fontSize: "12px", color: "#6b7280", background: "#f9fafb", whiteSpace: "nowrap", position: "sticky", top: 0, zIndex: 2 };
const td: React.CSSProperties = { padding: "7px 10px", fontSize: "12px", borderTop: "1px solid #f3f4f6", whiteSpace: "nowrap" };
const btn: React.CSSProperties = { padding: "5px 14px", borderRadius: "6px", border: "1px solid #d1d5db", background: "#fff", fontSize: "13px", cursor: "pointer" };
const primaryBtn: React.CSSProperties = { ...btn, background: "#4f46e5", color: "#fff", border: "1px solid #4f46e5" };
const sel: React.CSSProperties = { padding: "5px 8px", borderRadius: "6px", border: "1px solid #d1d5db", fontSize: "13px" };

function riskBadge(risk: string): React.CSSProperties {
  const base: React.CSSProperties = { padding: "1px 8px", borderRadius: "9px", fontSize: "11px", whiteSpace: "nowrap" };
  if (risk === "已断货") return { ...base, background: "#fee2e2", color: "#b91c1c" };
  if (risk === "≤7天") return { ...base, background: "#fef3c7", color: "#92400e" };
  if (risk === "≤14天") return { ...base, background: "#fef9c3", color: "#854d0e" };
  if (risk === "健康") return { ...base, background: "#dcfce7", color: "#166534" };
  if (risk === "清货中") return { ...base, background: "#dbeafe", color: "#1d4ed8" };
  return { ...base, background: "#f3f4f6", color: "#4b5563" };
}

export default function PmcCenter() {
  const [rows, setRows] = useState<Row[]>([]);
  const [kpi, setKpi] = useState<Kpi | null>(null);
  const [stores, setStores] = useState<string[]>([]);
  const [owners, setOwners] = useState<string[]>([]);
  const [risks, setRisks] = useState<string[]>([]);
  const [purchaseSynced, setPurchaseSynced] = useState(true);
  const [fStore, setFStore] = useState<string[]>([]);
  const [fOwner, setFOwner] = useState<string[]>([]);
  const [fRisk, setFRisk] = useState("");
  const [fSku, setFSku] = useState("");
  const [loading, setLoading] = useState(false);
  const [msg, setMsg] = useState("");
  const [sortCol, setSortCol] = useState("");
  const [sortDir, setSortDir] = useState<1 | -1>(1);

  const ALL_COLS = ["SKU", "商品ID", "店铺", "负责人", "WFS库存", "在途", "采购中", "7日日销", "可卖天数", "货件情况", "补货建议", "风险"];
  const MAX_PINNED_COLUMNS = 7;
  const COL_W: Record<string, string> = {
    "SKU": "120px", "商品ID": "140px", "店铺": "150px", "负责人": "80px", "WFS库存": "80px", "在途": "60px",
    "采购中": "120px", "7日日销": "80px", "可卖天数": "85px", "货件情况": "185px", "补货建议": "185px", "风险": "80px",
  };
  const [selectedCols, setSelectedCols] = useState<string[]>(() => {
    try {
      const saved = JSON.parse(localStorage.getItem("pmc_selected_cols") || "[]") as string[];
      const valid = saved.filter((c) => ALL_COLS.includes(c));
      return valid.length ? valid : ALL_COLS;
    } catch { return ALL_COLS; }
  });
  const [pinnedCols, setPinnedCols] = useState<string[]>(() => {
    try { return (JSON.parse(localStorage.getItem("pmc_pinned_cols") || "[]") as string[]).filter((c) => ALL_COLS.includes(c)); }
    catch { return []; }
  });
  const [showColCfg, setShowColCfg] = useState(false);
  const [cfgSelected, setCfgSelected] = useState<string[]>([]);
  const [cfgPins, setCfgPins] = useState<string[]>([]);
  const dragColIdxRef = useRef<number | null>(null);
  const visibleCols = [
    ...selectedCols.filter((c) => pinnedCols.includes(c)),
    ...selectedCols.filter((c) => !pinnedCols.includes(c)),
  ];
  const cfgOrderedSelected = [
    ...cfgSelected.filter((c) => cfgPins.includes(c)),
    ...cfgSelected.filter((c) => !cfgPins.includes(c)),
  ];
  const pinLeft: Record<string, number> = {};
  {
    let acc = 0;
    for (const c of visibleCols) {
      if (!pinnedCols.includes(c)) break;
      pinLeft[c] = acc;
      acc += parseInt(COL_W[c] ?? "100", 10);
    }
  }

  const load = useCallback(async () => {
    setLoading(true);
    setMsg("");
    try {
      const res = await fetch(`/api/pmc/list`);
      const data = await res.json();
      if (!res.ok || data.error) throw new Error(data.error || `HTTP ${res.status}`);
      setRows(data.rows ?? []);
      setKpi(data.kpi ?? null);
      setStores(data.stores ?? []);
      setOwners(data.owners ?? []);
      setRisks(data.risks ?? []);
      setPurchaseSynced(Boolean(data.purchase_synced));
    } catch (err) {
      setMsg(`加载失败：${String(err)}`);
    } finally {
      setLoading(false);
    }
  }, []);
  useEffect(() => { void load(); }, [load]);

  const SORT_VAL: Record<string, (r: Row) => string | number> = {
    "SKU": (r) => r.sku,
    "商品ID": (r) => r.item_id,
    "店铺": (r) => r.store_name,
    "负责人": (r) => r.owner,
    "WFS库存": (r) => r.stock,
    "在途": (r) => r.inbound,
    "采购中": (r) => r.procurement,
    "7日日销": (r) => r.daily7,
    "可卖天数": (r) => r.days_to_sell ?? (r.stock <= 0 ? -1 : 999999),
    "补货建议": (r) => -r.suggestion_qty,
    "风险": (r) => r.risk,
  };
  function onSort(col: string) {
    if (!SORT_VAL[col]) return;
    if (sortCol === col) setSortDir((d) => (d === 1 ? -1 : 1));
    else { setSortCol(col); setSortDir(1); }
  }
  function displayRows(): Row[] {
    let out = rows;
    if (fStore.length) out = out.filter((r) => fStore.includes(r.store_name));
    if (fOwner.length) out = out.filter((r) => fOwner.includes(r.owner));
    if (fRisk) out = out.filter((r) => r.risk === fRisk);
    const kw = fSku.trim().toLowerCase();
    if (kw) out = out.filter((r) => r.sku.toLowerCase().includes(kw) || r.mskus.toLowerCase().includes(kw) || r.item_id.includes(kw));
    if (sortCol && SORT_VAL[sortCol]) {
      const get = SORT_VAL[sortCol];
      out = [...out].sort((a, b) => {
        const va = get(a); const vb = get(b);
        if (typeof va === "number" && typeof vb === "number") return (va - vb) * sortDir;
        return String(va).localeCompare(String(vb), "zh") * sortDir;
      });
    }
    return out;
  }

  const kpiItems = kpi ? [
    { label: "在营产品", value: kpi.total, bg: "#f3f4f6", fg: "#374151" },
    { label: "已断货（有销量）", value: kpi.out_of_stock, bg: "#fee2e2", fg: "#b91c1c" },
    { label: "7天内断货", value: kpi.within7, bg: "#fef3c7", fg: "#92400e" },
    { label: "需补货", value: kpi.need_replenish, bg: "#fce7f3", fg: "#9d174d" },
    { label: "在途总量", value: kpi.inbound_total, bg: "#dbeafe", fg: "#1d4ed8" },
    { label: "采购中（按SKU）", value: kpi.procurement_total, bg: "#ede9fe", fg: "#5b21b6" },
  ] : [];

  return (
    <div>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(130px, 1fr))", gap: "10px", marginBottom: "12px" }}>
        {kpiItems.map((k) => (
          <div key={k.label} style={{ background: k.bg, borderRadius: "10px", padding: "10px 12px" }}>
            <div style={{ fontSize: "12px", color: k.fg }}>{k.label}</div>
            <div style={{ fontSize: "22px", fontWeight: 700, color: k.fg }}>{k.value.toLocaleString()}</div>
          </div>
        ))}
      </div>

      <div style={{ ...card, display: "flex", gap: "8px", alignItems: "center", flexWrap: "wrap" }}>
        <LxMultiSelect placeholder="全部店铺" minWidth={150}
          options={stores.map((s) => ({ value: s, label: s }))}
          selected={fStore} onChange={setFStore} />
        <LxMultiSelect placeholder="全部负责人" minWidth={120}
          options={owners.map((o) => ({ value: o, label: o }))}
          selected={fOwner} onChange={setFOwner} />
        <select style={sel} value={fRisk} onChange={(e) => setFRisk(e.target.value)}>
          <option value="">风险：全部</option>
          {risks.map((s) => <option key={s} value={s}>{s}</option>)}
        </select>
        <input style={{ ...sel, width: "150px" }} placeholder="SKU/MSKU/ItemID 搜索" value={fSku} onChange={(e) => setFSku(e.target.value)} />
        <button style={btn} onClick={() => void load()} disabled={loading}>{loading ? "加载中…" : "刷新"}</button>
        <button style={btn} onClick={() => { setCfgSelected(visibleCols); setCfgPins(pinnedCols); setShowColCfg(true); }}>列配置</button>
        {!purchaseSynced && <span style={{ fontSize: "12px", color: "#b45309", marginLeft: "auto" }}>已采购列：采购数据尚未同步（等 07:40 首跑）</span>}
      </div>

      {msg && <div style={{ ...card, color: "#b91c1c" }}>{msg}</div>}

      {showColCfg && (
        <div style={{ position: "fixed", inset: 0, background: "rgba(15,23,42,0.4)", zIndex: 1000, display: "flex", alignItems: "center", justifyContent: "center" }}
          onClick={() => setShowColCfg(false)}>
          <div style={{ background: "#fff", borderRadius: "12px", width: "680px", maxHeight: "78vh", display: "flex", flexDirection: "column", overflow: "hidden", boxShadow: "0 8px 32px rgba(0,0,0,0.18)" }}
            onClick={(e) => e.stopPropagation()}>
            <div style={{ padding: "12px 16px", borderBottom: "1px solid #e5e7eb", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <span style={{ fontSize: "14px", fontWeight: 700, color: "#374151" }}>列配置</span>
              <button onClick={() => setShowColCfg(false)} style={{ border: "none", background: "none", fontSize: "18px", cursor: "pointer", color: "#9ca3af" }}>×</button>
            </div>
            <div style={{ display: "flex", flex: 1, overflow: "hidden" }}>
              <div style={{ flex: 1, padding: "10px 14px", overflowY: "auto" }}>
                {ALL_COLS.map((col) => (
                  <label key={col} style={{ display: "flex", alignItems: "center", gap: "6px", padding: "4px 0", cursor: "pointer", fontSize: "13px" }}>
                    <input type="checkbox" checked={cfgSelected.includes(col)}
                      onChange={() => {
                        setCfgSelected((prev) => prev.includes(col) ? prev.filter((c) => c !== col) : [...prev, col]);
                        setCfgPins((prev) => prev.filter((c) => c !== col));
                      }} />
                    <span style={{ color: "#374151" }}>{col}</span>
                  </label>
                ))}
              </div>
              <div style={{ width: "230px", borderLeft: "1px solid #e5e7eb", padding: "10px 10px", overflowY: "auto", background: "#f8fafc" }}>
                <div style={{ fontSize: "12px", color: "#64748b", marginBottom: "2px" }}>已选 {cfgSelected.length} 列 · 拖动调顺序</div>
                <div style={{ fontSize: "11px", color: "#94a3b8", marginBottom: "6px" }}>📌最多固定{MAX_PINNED_COLUMNS}项（表格左侧冻结）</div>
                {cfgOrderedSelected.map((col, idx) => {
                  const isPin = cfgPins.includes(col);
                  return (
                    <div key={col} draggable
                      onDragStart={() => { dragColIdxRef.current = idx; }}
                      onDragOver={(e) => e.preventDefault()}
                      onDrop={() => {
                        const from = dragColIdxRef.current;
                        dragColIdxRef.current = null;
                        if (from === null || from === idx) return;
                        const view = [...cfgOrderedSelected];
                        const [moved] = view.splice(from, 1);
                        view.splice(idx, 0, moved);
                        setCfgSelected(view);
                      }}
                      style={{ display: "flex", alignItems: "center", gap: "4px", padding: "4px 2px", fontSize: "12px",
                        borderRadius: "4px", cursor: "grab", background: isPin ? "#eef2ff" : "transparent", borderBottom: "1px solid #f1f5f9" }}>
                      <span style={{ color: "#cbd5e1", fontSize: "13px", lineHeight: 1 }} title="拖动排序">⠿</span>
                      <span style={{ flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                        {isPin && <span style={{ fontSize: "10px" }}>📌</span>}{col}
                      </span>
                      <span onClick={() => setCfgSelected((prev) => [col, ...prev.filter((c) => c !== col)])} title="置顶"
                        style={{ color: "#64748b", cursor: "pointer", fontSize: "12px" }}>⬆</span>
                      <span onClick={() => setCfgPins((prev) => {
                          if (prev.includes(col)) return prev.filter((c) => c !== col);
                          if (prev.length >= MAX_PINNED_COLUMNS) { window.alert(`最多可固定${MAX_PINNED_COLUMNS}项`); return prev; }
                          return [...prev, col];
                        })} title={isPin ? "取消固定" : "固定（左侧冻结）"}
                        style={{ color: isPin ? "#2563eb" : "#94a3b8", cursor: "pointer", fontSize: "12px" }}>📌</span>
                      <span onClick={() => {
                          setCfgSelected((prev) => prev.filter((c) => c !== col));
                          setCfgPins((prev) => prev.filter((c) => c !== col));
                        }} title="删除"
                        style={{ color: "#ef4444", cursor: "pointer", fontSize: "14px" }}>×</span>
                    </div>
                  );
                })}
              </div>
            </div>
            <div style={{ padding: "10px 16px", borderTop: "1px solid #e5e7eb", display: "flex", gap: "8px", justifyContent: "flex-end" }}>
              <button style={btn} onClick={() => { setCfgSelected(ALL_COLS); setCfgPins([]); }}>重置默认</button>
              <button style={btn} onClick={() => setShowColCfg(false)}>取消</button>
              <button style={primaryBtn} onClick={() => {
                const ordered = [...cfgSelected.filter((c) => cfgPins.includes(c)), ...cfgSelected.filter((c) => !cfgPins.includes(c))];
                setSelectedCols(ordered);
                setPinnedCols(cfgPins);
                try {
                  localStorage.setItem("pmc_selected_cols", JSON.stringify(ordered));
                  localStorage.setItem("pmc_pinned_cols", JSON.stringify(cfgPins));
                } catch { /* 忽略 */ }
                setShowColCfg(false);
              }}>应用</button>
            </div>
          </div>
        </div>
      )}

      <style>{`.pmc-row:hover td { background: #eef2ff; }`}</style>
      <div style={{ ...card, padding: 0, overflow: "auto", maxHeight: "64vh" }}>
        <table style={{ width: "100%", borderCollapse: "collapse", tableLayout: "fixed" }}>
          <thead>
            <tr>
              {visibleCols.map((h) => (
                <th key={h}
                  style={{ ...th, width: COL_W[h], cursor: SORT_VAL[h] ? "pointer" : "default", userSelect: "none",
                    ...(pinnedCols.includes(h) ? { position: "sticky" as const, left: pinLeft[h], zIndex: 4, background: "#f1f5f9" } : {}) }}
                  onClick={() => onSort(h)}>
                  {h}{SORT_VAL[h] ? (sortCol === h ? (sortDir === 1 ? " ↑" : " ↓") : <span style={{ color: "#c7cbd4" }}> ⇅</span>) : ""}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {displayRows().map((r) => {
              const cells: Record<string, JSX.Element> = {
                "SKU": <td key="sku" style={td}>{r.sku}<br /><span style={{ color: "#6b7280" }}>{r.mskus}</span></td>,
                "商品ID": <td key="pid" style={td}><ItemIdLink itemId={r.item_id} /></td>,
                "店铺": <td key="st" style={{ ...td, color: "#6b7280" }}>{r.store_name}</td>,
                "负责人": <td key="ow" style={td}>{r.owner}</td>,
                "WFS库存": <td key="stk" style={{ ...td, textAlign: "right", color: r.stock === 0 ? "#b91c1c" : undefined, fontWeight: r.stock === 0 ? 700 : undefined }}>{r.stock}</td>,
                "在途": <td key="ib" style={{ ...td, textAlign: "right" }}>{r.inbound}</td>,
                "采购中": <td key="po" style={{ ...td, textAlign: "right" }}
                  title={`未到货采购 ${r.procurement_po} + 本地仓 ${r.procurement_local}（同SKU变体共享）`}>
                  {r.procurement > 0 ? (
                    <span>{r.procurement}
                      <span style={{ color: "#9ca3af", fontSize: "11px" }}>
                        <br />采购{r.procurement_po}·本地仓{r.procurement_local}
                        {r.purchase_nearest ? ` · ${r.purchase_nearest}到` : ""}
                      </span>
                    </span>
                  ) : <span style={{ color: "#9ca3af" }}>—</span>}
                </td>,
                "7日日销": <td key="d7" style={{ ...td, textAlign: "right" }}>{r.daily7}</td>,
                "可卖天数": <td key="ds" style={{ ...td, textAlign: "right" }}>{r.days_to_sell === null ? "—" : `${r.days_to_sell}天`}</td>,
                "货件情况": <td key="sh" style={{ ...td, whiteSpace: "normal" as const }}>
                  {r.shipments.length ? r.shipments.map((sp) => (
                    <div key={sp.id} style={{ fontSize: "11px", color: "#4b5563" }}>{sp.id} · {sp.status}（{sp.received}/{sp.declared}）</div>
                  )) : <span style={{ color: "#9ca3af" }}>无在途货件</span>}
                </td>,
                "补货建议": <td key="sg" style={{ ...td, whiteSpace: "normal" as const, color: r.suggestion.startsWith("立即") ? "#b91c1c" : undefined }}>{r.suggestion || <span style={{ color: "#9ca3af" }}>—</span>}</td>,
                "风险": <td key="rk" style={td}><span style={riskBadge(r.risk)}>{r.risk}</span></td>,
              };
              return (
                <tr className="pmc-row" key={`${r.store_id}-${r.item_id}`}>
                  {visibleCols.map((c) => pinnedCols.includes(c)
                    ? cloneElement(cells[c], {
                        style: { ...(cells[c].props as { style?: React.CSSProperties }).style,
                          position: "sticky", left: pinLeft[c], zIndex: 1, background: "#fff" },
                      })
                    : cells[c])}
                </tr>
              );
            })}
            {!displayRows().length && !loading && (
              <tr><td style={{ ...td, textAlign: "center", color: "#6b7280" }} colSpan={visibleCols.length}>无数据</td></tr>
            )}
          </tbody>
        </table>
      </div>
      <div style={{ fontSize: "12px", color: "#6b7280", marginTop: "8px" }}>
        口径：库存取最新快照；在途=未完结货件Σ(申报-已收)；7日日销=近7个数据日均值；虚拟产品(XY2007)已剔除；
        采购中=未到货采购Σ(计划-已收)+本地仓库存（按SKU，同SKU变体共享；创建货件扣本地仓后转入"在途"）；
        补货建议=70天目标（日销×70−库存−在途−采购中，清货期无建议）；货件情况=全部未完结货件（已收/申报）。
      </div>
    </div>
  );
}
