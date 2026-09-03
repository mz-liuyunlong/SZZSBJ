/**
 * AiFinanceTools.tsx — AI财务系统 · 财务工具（2026-08-13 批7d，UI_STANDARDS 合规版）
 * 汇率：**只读展示领星汇率**（fact_lingxing_fx_rate）。需求方 2026-08-13 决定不再人工录入，
 *   主口径=my_rate「我的汇率」（领星算单品成本用的就是它，折算必须同源）。
 *   人工台账 biz_finance_exchange_rate 与后端 /fx/list、/fx/upsert 保留不删（历史审计+兜底），仅前端不再提供写入。
 * §1 LxToolbar工具条+元信息 · §2 帮助壳内(#/help?page=finance-tools) · §5 列宽拖动 ·
 * §8 总计吸底+翻页+表头吸顶 · §9 #/finance/tools。
 * 权限：读=登录即可；写=超管或 finance_fx 权限（后端 requirePermission 强制，前端仅控显隐）。
 */
import { useEffect, useMemo, useRef, useState } from "react";
import { lxTB, IconRefresh, IconHelp, IconDownload } from "./LxToolbar";

interface FxRow {
  id: number; rate_month: string; currency_code: string; currency_name: string; icon: string;
  rate_org: string | number; my_rate: string | number; lx_update_time: string | null; synced_at: string;
}
interface CurOpt { code: string; name: string }

const C = { blue: "#1a73e8", txt2: "#5f6368", txt3: "#9aa0a6", line: "#dadce0", neg: "#d93025", green: "#188038", amber: "#b06f00" };
const card: React.CSSProperties = { background: "#fff", border: "1px solid #e5e7eb", borderRadius: "10px" };
const iconBtnWrap: React.CSSProperties = { width: "30px", height: "30px", display: "inline-flex", alignItems: "center", justifyContent: "center", border: `1px solid ${C.line}`, borderRadius: "6px", background: "#fff", cursor: "pointer" };
const PAGE_SIZES = [50, 100, 200];
const pageBtn = (active: boolean, disabled: boolean): React.CSSProperties => ({ padding: "5px 12px", borderRadius: "5px", border: "1px solid #e5e7eb", cursor: disabled ? "not-allowed" : "pointer", background: active ? "#6366f1" : "#fff", color: active ? "#fff" : "#374151", fontWeight: active ? 700 : 400, fontSize: "13px", opacity: disabled ? 0.5 : 1 });
const inp: React.CSSProperties = { padding: "6px 10px", borderRadius: "6px", border: "1px solid #d1d5db", fontSize: "12px", boxSizing: "border-box" };
const btn: React.CSSProperties = { padding: "6px 14px", borderRadius: "6px", border: "1px solid #d1d5db", background: "#fff", fontSize: "12px", cursor: "pointer" };
// 内嵌历史表专用小档位（主列表页仍用 PAGE_SIZES=[50,100,200]，此处表体较短故用小档位，UI_STANDARDS §7 控件顺序不变）
const MINI_SIZES = [10, 20, 50];

/** 折叠区标题栏：折叠箭头 + 标题 + 条数 + 刷新 + 帮助（图标顺序遵 UI_STANDARDS §1：刷新→帮助） */
function SectionBar({ title, count, open, onToggle, onRefresh, onHelp, busy, filterValue, onFilter, storeOpts }: {
  title: string; count: number; open: boolean; onToggle: () => void;
  onRefresh: () => void; onHelp: () => void; busy?: boolean;
  filterValue?: string; onFilter?: (v: string) => void; storeOpts?: string[];
}) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: "8px", marginTop: "10px", paddingTop: "8px", borderTop: "1px solid #f3f4f6" }}>
      <button onClick={onToggle} title={open ? "收起" : "展开"}
        style={{ ...iconBtnWrap, width: "24px", height: "24px", fontSize: "11px", color: C.txt2, lineHeight: 1 }}>
        {open ? "\u25be" : "\u25b8"}
      </button>
      <b style={{ fontSize: "12px", color: "#374151" }}>{title}</b>
      <span style={{ fontSize: "11px", color: C.txt3 }}>共 {count} 条</span>
      {open && onFilter && (
        <select value={filterValue ?? ""} onChange={(e) => onFilter(e.target.value)}
          style={{ ...inp, width: "200px", padding: "4px 8px", fontSize: "11px", marginLeft: "6px" }}>
          <option value="">全部店铺</option>
          {(storeOpts ?? []).map((n) => (<option key={n} value={n}>{n}</option>))}
        </select>
      )}
      <div style={{ flex: 1 }} />
      <button style={{ ...iconBtnWrap, width: "26px", height: "26px" }} title="刷新" onClick={onRefresh} disabled={busy}><IconRefresh /></button>
      <button style={{ ...iconBtnWrap, width: "26px", height: "26px" }} title="帮助（口径与操作说明）" onClick={onHelp}><IconHelp /></button>
    </div>
  );
}

/** 内嵌表分页条（UI_STANDARDS §7：每页档位 · 首页 · 上一页 · 页码窗口(≤5) · 下一页 · 末页 · 共N条 · 跳至） */
function MiniPager({ total, page, size, onPage, onSize }: {
  total: number; page: number; size: number; onPage: (p: number) => void; onSize: (s: number) => void;
}) {
  const totalPages = Math.max(1, Math.ceil(total / size));
  const cur = Math.min(page, totalPages);
  const pb = (active: boolean, disabled: boolean): React.CSSProperties => ({ ...pageBtn(active, disabled), padding: "3px 9px", fontSize: "11px" });
  return (
    <div style={{ display: "flex", alignItems: "center", gap: "6px", flexWrap: "wrap", marginTop: "8px" }}>
      <span style={{ fontSize: "11px", color: C.txt2 }}>每页</span>
      {MINI_SIZES.map((s) => (<button key={s} style={pb(s === size, false)} onClick={() => onSize(s)}>{s}</button>))}
      <span style={{ width: "8px" }} />
      <button style={pb(false, cur <= 1)} disabled={cur <= 1} onClick={() => onPage(1)}>首页</button>
      <button style={pb(false, cur <= 1)} disabled={cur <= 1} onClick={() => onPage(cur - 1)}>上一页</button>
      {Array.from({ length: Math.min(5, totalPages) }, (_, i) => {
        const pnum = Math.max(1, Math.min(cur - 2, totalPages - 4)) + i;
        return pnum <= totalPages ? (<button key={pnum} style={pb(pnum === cur, false)} onClick={() => onPage(pnum)}>{pnum}</button>) : null;
      })}
      <button style={pb(false, cur >= totalPages)} disabled={cur >= totalPages} onClick={() => onPage(cur + 1)}>下一页</button>
      <button style={pb(false, cur >= totalPages)} disabled={cur >= totalPages} onClick={() => onPage(totalPages)}>末页</button>
      <span style={{ fontSize: "11px", color: C.txt3 }}>共 {total} 条</span>
      <span style={{ fontSize: "11px", color: C.txt3 }}>跳至</span>
      <input type="number" min={1} max={totalPages} defaultValue={cur}
        style={{ ...inp, width: "52px", padding: "3px 6px", fontSize: "11px" }}
        onKeyDown={(e) => { if (e.key === "Enter") { const v = Number((e.target as HTMLInputElement).value); if (v >= 1 && v <= totalPages) onPage(v); } }} />
      <span style={{ fontSize: "11px", color: C.txt3 }}>页</span>
    </div>
  );
}
const n2 = (v: unknown): number => { const n = Number(v); return Number.isFinite(n) ? n : 0; };

const COLS: { key: string; label: string; w: number; align: "left" | "right"; tip?: string }[] = [
  { key: "rate_month", label: "生效月份", w: 100, align: "left" },
  { key: "currency_code", label: "币种", w: 90, align: "left" },
  { key: "currency_name", label: "币种名", w: 110, align: "left" },
  { key: "rate_org", label: "官方汇率", w: 120, align: "right", tip: "领星取自中国银行官方汇率；仅供参考，不参与折算" },
  { key: "my_rate", label: "我的汇率", w: 130, align: "right", tip: "财务在领星【设置→汇率管理】录入的自定义汇率。**折算主口径**：领星计算单品成本(WFS入库成本等)优先用它，本系统折算与其同源。实测领星摊头程费用时取的是发货月【上一个月】的我的汇率。" },
  { key: "lx_update_time", label: "领星更新时间", w: 150, align: "left", tip: "该币种汇率在领星侧最后修改时间" },
  { key: "synced_at", label: "同步时间", w: 150, align: "left", tip: "本系统最后一次从领星拉取该行的时间" },
];

// 可输入搜索的店铺下拉（原生 datalist 联想；输入店铺名/编号即可过滤，仿广告导入工具）
function StoreSearch({ stores, value, onChange, listId, style }: {
  stores: { store_id: string; store_name: string }[];
  value: string; onChange: (id: string) => void; listId: string; style?: React.CSSProperties;
}) {
  const [q, setQ] = useState("");
  const sel = stores.find((s) => s.store_id === value);
  const shown = q !== "" || !sel ? q : sel.store_name;
  const resolve = (text: string): void => {
    setQ(text);
    const exact = stores.find((s) => s.store_name === text);
    if (exact) { onChange(exact.store_id); return; }
    const subs = stores.filter((s) => s.store_name.includes(text) || s.store_id.includes(text));
    onChange(text && subs.length === 1 ? subs[0].store_id : "");
  };
  return (
    <span>
      <input list={listId} style={style} placeholder="选择/输入店铺搜索" value={shown} autoComplete="off"
        onChange={(e) => resolve(e.target.value)} />
      <datalist id={listId}>{stores.map((s) => <option key={s.store_id} value={s.store_name} />)}</datalist>
    </span>
  );
}

export default function AiFinanceTools({ onNavigate }: { onNavigate?: (key: string) => void }) {
  const [rows, setRows] = useState<FxRow[]>([]);
  const [canWrite, setCanWrite] = useState(false);
  const [canImport, setCanImport] = useState(false); // 导入权限：超管/财务角色/finance_import
  const [syncedAt, setSyncedAt] = useState("");
  const [loading, setLoading] = useState(false);
  const [msg, setMsg] = useState("");
  const [pageSize, setPageSize] = useState(50);
  const [page, setPage] = useState(1);
  const [fxOpen, setFxOpen] = useState(false);   // 汇率区默认收起（需求方 2026-08-14：打开网页时为折叠状态）
  const [colWidths, setColWidths] = useState<Record<string, number>>({});
  const resizeRef = useRef<{ col: string; startX: number; startW: number } | null>(null);
  // 录入/编辑表单
  const [curCode, setCurCode] = useState("USD");
  const [curOpts, setCurOpts] = useState<CurOpt[]>([]);
  // 仓储费导入（批4）
  interface StoreOpt { store_id: string; store_name: string }
  interface StorageBatch { store_name: string; report_start: string; report_end: string; sku_cnt: number; fee_sum: number; discount_sum: number; task_id: string; imported_at: string; operator?: string }
  const [stores, setStores] = useState<StoreOpt[]>([]);
  const [selStore, setSelStore] = useState("");
  const [csvFile, setCsvFile] = useState<File | null>(null);
  const [importing, setImporting] = useState(false);
  const [impResult, setImpResult] = useState<string>("");
  const [storageList, setStorageList] = useState<StorageBatch[]>([]);
  const [storOpen, setStorOpen] = useState(false);     // 默认折叠（需求方 2026-08-14：三个区块打开网页时全部为折叠状态）
  const [storPage, setStorPage] = useState(1);
  const [storSize, setStorSize] = useState(10);
  const [storBusy, setStorBusy] = useState(false);
  const [storFilter, setStorFilter] = useState("");   // 历史表店铺筛选
  const loadStorage = async (): Promise<void> => {
    try {
      const r = await fetch("/api/finance/storage/list", { credentials: "include" });
      const d = (await r.json()) as { rows?: StorageBatch[] };
      setStorageList(d.rows ?? []);
    } catch { /* noop */ }
  };
  // 入库运输导入（批5）
  interface InbBatch { store_name: string; report_start: string; report_end: string; shipment_cnt: number; alloc_rows: number; freight_sum: number; unmatched_sum: number; task_id: string; imported_at: string; operator?: string }
  const [selStore2, setSelStore2] = useState("");
  const [inbFile, setInbFile] = useState<File | null>(null);
  const [inbImporting, setInbImporting] = useState(false);
  const [inbResult, setInbResult] = useState("");
  const [inbList, setInbList] = useState<InbBatch[]>([]);
  const [inbOpen, setInbOpen] = useState(false);       // 默认折叠（需求方 2026-08-14：三个区块打开网页时全部为折叠状态）
  const [inbPage, setInbPage] = useState(1);
  const [inbSize, setInbSize] = useState(10);
  const [inbBusy, setInbBusy] = useState(false);
  const [inbFilter, setInbFilter] = useState("");     // 历史表店铺筛选
  const loadInbound = async (): Promise<void> => {
    try {
      const r = await fetch("/api/finance/inbound/list", { credentials: "include" });
      const d = (await r.json()) as { rows?: InbBatch[] };
      setInbList(d.rows ?? []);
    } catch { /* noop */ }
  };
  // 未匹配留存重分摊（批5c）
  interface UnmRow { store_id: string; store_name: string; cargo_code: string; report_start: string; report_end: string; amount: number; task_id: string }
  const [unmList, setUnmList] = useState<UnmRow[]>([]);
  const [unmTotal, setUnmTotal] = useState(0);
  const [reBusy, setReBusy] = useState(false);
  const [reResult, setReResult] = useState("");
  const loadUnmatched = async (): Promise<void> => {
    try {
      const r = await fetch("/api/finance/inbound/unmatched", { credentials: "include" });
      const d = (await r.json()) as { rows?: UnmRow[]; total?: number };
      setUnmList(d.rows ?? []); setUnmTotal(Number(d.total ?? 0));
    } catch { /* noop */ }
  };
  const doReallocate = async (pool: boolean): Promise<void> => {
    if (pool && !window.confirm("二次分摊：把货件档案永久缺失的运费，按本账期已分摊运费占比摊到本期SKU上（标记 pool，可追溯）。\n仅在确认该货件无法回补时使用。继续？")) return;
    setReBusy(true); setReResult("");
    try {
      const r = await fetch("/api/finance/inbound/reallocate", {
        method: "POST", credentials: "include", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ pool }),
      });
      const d = (await r.json()) as { ok?: boolean; error?: string; handled?: number; matched?: number; pooled?: number; still_none?: number; moved_amount?: number; results?: Array<{ cargo_code: string; result: string; note?: string }> };
      if (!r.ok || !d.ok) { setMsg(d.error ?? "重分摊失败"); return; }
      const still = (d.results ?? []).filter((x) => x.result === "still_none");
      setReResult(`处理${d.handled}笔：✅回补匹配${d.matched} · 🔁二次分摊${d.pooled} · ⚠️仍未匹配${d.still_none}（落地金额$${d.moved_amount}）` +
        (still.length ? `；待办：${still.map((x) => x.cargo_code + "(" + (x.note ?? "") + ")").join("、")}` : ""));
      await loadInbound(); await loadUnmatched();
    } catch (e) { setMsg("重分摊失败：" + (e instanceof Error ? e.message : String(e))); }
    finally { setReBusy(false); }
  };
  const doInboundImport = async (): Promise<void> => {
    if (!selStore2) { setInbResult("⚠️ 请先选择店铺（入库运输）"); return; }
    if (!inbFile) { setInbResult("⚠️ 请选择入库运输报告CSV文件"); return; }
    setInbImporting(true); setInbResult("");
    try {
      const content = await inbFile.text();
      const r = await fetch("/api/finance/inbound-import", {
        method: "POST", credentials: "include", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ store_id: selStore2, filename: inbFile.name, content }),
      });
      const d = (await r.json()) as { ok?: boolean; error?: string; task_id?: string; report_start?: string; report_end?: string; rows?: number; shipments?: number; matched_shipments?: number; unmatched_shipments?: string[]; freight_total?: number; alloc_rows?: number; empty?: boolean; message?: string };
      if (!r.ok || !d.ok) { setInbResult("❌ 导入失败：" + (d.error ?? "未知错误")); return; }
      const um = d.unmatched_shipments ?? [];
      setInbResult(d.empty
        ? `✅ ${d.task_id}：${String(d.message ?? "该报告期无数据行，已留 0 记录")}`
        : `✅ ${d.task_id}：${d.report_start}~${d.report_end}，${d.rows}行/${d.shipments}货件，Σ运费$${d.freight_total}（请与Seller Center页面合计核对），匹配${d.matched_shipments}/${d.shipments}货件→分摊${d.alloc_rows}行` +
        (um.length ? `；⚠️未匹配货件（整额留存待回补）：${um.join("、")}` : ""));
      setInbFile(null);
      await loadInbound(); await loadUnmatched();
    } catch (e) { setInbResult("❌ 导入失败：" + (e instanceof Error ? e.message : String(e))); }
    finally { setInbImporting(false); }
  };
  useEffect(() => {
    void fetch("/api/finance/stores", { credentials: "include" }).then((r) => r.json())
      .then((d: { stores?: StoreOpt[] }) => setStores(d.stores ?? [])).catch(() => undefined);
    void loadStorage();
    void loadInbound();
    void loadUnmatched();
  }, []);
  const doImport = async (): Promise<void> => {
    if (!selStore) { setImpResult("⚠️ 请先选择店铺（报告是按店铺下载的）"); return; }
    if (!csvFile) { setImpResult("⚠️ 请选择仓储报告CSV文件"); return; }
    setImporting(true); setImpResult("");
    try {
      const content = await csvFile.text();
      const r = await fetch("/api/finance/storage-import", {
        method: "POST", credentials: "include", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ store_id: selStore, filename: csvFile.name, content }),
      });
      const d = (await r.json()) as { ok?: boolean; error?: string; task_id?: string; rows?: number; item_mapped?: number; total_reported?: number; total_computed?: number; diff?: number; report_start?: string; report_end?: string; empty?: boolean; message?: string };
      if (!r.ok || !d.ok) { setImpResult("❌ 导入失败：" + (d.error ?? "未知错误")); return; }
      setImpResult(d.empty
        ? `✅ ${d.task_id}：${String(d.message ?? "该报告期无数据行，已留 0 记录")}`
        : `✅ ${d.task_id}：${d.report_start}~${d.report_end}，${d.rows} SKU，导入Σ$${d.total_computed} = 报告Total $${d.total_reported}（差${d.diff}），ItemID映射 ${d.item_mapped}/${d.rows}`);
      setCsvFile(null);
      await loadStorage();
    } catch (e) { setImpResult("❌ 导入失败：" + (e instanceof Error ? e.message : String(e))); }
    finally { setImporting(false); }
  };

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
    if (typeof document !== "undefined" && !document.getElementById("lxfin-tip-css")) {
      const st = document.createElement("style");
      st.id = "lxfin-tip-css";
      st.textContent =
        ".lxfin-info{position:relative;display:inline-flex;align-items:center;justify-content:center;width:13px;height:13px;margin-left:3px;border:1px solid #9aa0a6;border-radius:50%;font-size:9px;color:#9aa0a6;cursor:help;font-style:normal;vertical-align:1px}" +
        ".lxfin-info .lxfin-tip{display:none;position:absolute;top:20px;left:50%;transform:translateX(-50%);background:#202124;color:#fff;font-size:11px;line-height:1.6;padding:8px 10px;border-radius:6px;width:230px;white-space:normal;z-index:30;text-align:left;font-weight:400}" +
        ".lxfin-info .lxfin-tip::before{content:'';position:absolute;top:-5px;left:50%;transform:translateX(-50%);border:5px solid transparent;border-top:none;border-bottom:5px solid #202124}" +
        ".lxfin-info:hover .lxfin-tip{display:block}";
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
      const r = await fetch(`/api/finance/fx/lingxing?currency=${encodeURIComponent(curCode)}`, { credentials: "include" });
      const d = (await r.json()) as { rows?: FxRow[]; can_write?: boolean; can_import?: boolean; currencies?: CurOpt[]; latest_sync_time?: string; error?: string };
      if (!r.ok) throw new Error(d.error ?? String(r.status));
      setRows(d.rows ?? []); setCanWrite(!!d.can_write); setCanImport(!!d.can_import);
      if (d.currencies?.length) setCurOpts(d.currencies);
      const t = d.latest_sync_time ? new Date(String(d.latest_sync_time).replace(" ", "T")) : null;
      setSyncedAt(t && !Number.isNaN(t.getTime()) ? t.toLocaleString("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" }) : new Date().toLocaleString("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" }));
    } catch (e) { setMsg("加载失败：" + (e instanceof Error ? e.message : String(e))); }
    finally { setLoading(false); }
  };
  useEffect(() => { void load(); /* eslint-disable-next-line */ }, [curCode]);
  useEffect(() => { if (!msg) return; const t = setTimeout(() => setMsg(""), 3800); return () => clearTimeout(t); }, [msg]);

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
  // 导入历史：店铺筛选后的派生列表 + 可选店铺清单（取自实际数据，避免列出无记录的店铺）
  const storStoreOpts = useMemo(
    () => Array.from(new Set(storageList.map((r) => r.store_name).filter(Boolean))).sort(),
    [storageList]);
  const storShown = useMemo(
    () => (storFilter ? storageList.filter((r) => r.store_name === storFilter) : storageList),
    [storageList, storFilter]);
  const inbStoreOpts = useMemo(
    () => Array.from(new Set(inbList.map((r) => r.store_name).filter(Boolean))).sort(),
    [inbList]);
  const inbShown = useMemo(
    () => (inbFilter ? inbList.filter((r) => r.store_name === inbFilter) : inbList),
    [inbList, inbFilter]);

  const openHelp = (): void => {
    onNavigate?.("help");
    try { window.location.hash = "#/help?page=finance-tools"; } catch { /* noop */ }
  };
  const exportCsv = (): void => {
    const data: (string | number)[][] = [["生效月份", "币种", "币种名", "官方汇率", "我的汇率", "领星更新时间", "同步时间"]];
    for (const r of rows) data.push([r.rate_month, r.currency_code, r.currency_name, n2(r.rate_org), n2(r.my_rate), r.lx_update_time ?? "", r.synced_at]);
    const csv = "﻿" + data.map((row) => row.map((v) => `"${String(v).replace(/"/g, '""')}"`).join(",")).join("\n");
    const a = document.createElement("a");
    a.href = URL.createObjectURL(new Blob([csv], { type: "text/csv;charset=utf-8" }));
    a.download = `AI财务_领星汇率_${curCode}_${syncedAt || "export"}.csv`;
    a.click(); URL.revokeObjectURL(a.href);
  };

  const cellStyle = (align: "left" | "right"): React.CSSProperties =>
    ({ textAlign: align, padding: "7px 10px", fontSize: "12px", borderTop: "1px solid #f3f4f6", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis", fontVariantNumeric: "tabular-nums" });
  const cell = (r: FxRow, key: string): React.ReactNode => {
    switch (key) {
      case "rate_month": return <b>{r.rate_month}</b>;
      case "currency_code": return <span style={{ color: C.txt2 }}>{r.icon ? r.icon + " " : ""}{r.currency_code}</span>;
      case "currency_name": return <span style={{ color: C.txt2 }}>{r.currency_name || "—"}</span>;
      case "rate_org": return <span style={{ color: C.txt2 }}>{n2(r.rate_org).toFixed(4)}</span>;
      case "my_rate": return n2(r.my_rate) > 0
        ? <span style={{ color: C.blue, fontWeight: 700 }}>{n2(r.my_rate).toFixed(4)}</span>
        : <span style={{ color: C.neg }} title="领星未设置我的汇率，折算将退用官方汇率">未设置</span>;
      case "lx_update_time": return <span style={{ color: C.txt2 }}>{r.lx_update_time || "—"}</span>;
      case "synced_at": return <span style={{ color: C.txt3 }}>{r.synced_at}</span>;
      default: return null;
    }
  };

  return (
    <div>
      <p style={{ color: C.txt2, margin: "0 0 12px", fontSize: "12px", lineHeight: 1.6 }}>
        AI财务基础工具。<b>汇率</b>已改为<b>直接取领星值</b>，本页只读展示、无需人工录入：折算主口径 =
        领星【设置 → 汇率管理】里的<b>「我的汇率」</b>（领星计算单品 WFS 入库成本用的就是它，我方折算与其同源，避免系统性偏差）。
        要改汇率请到领星后台改，本系统每次同步后自动生效。
      </p>

      {/* 币种筛选 + 折算口径说明（汇率已改为只读取领星值，无录入入口） */}
      <div style={{ ...card, padding: "12px 14px", marginBottom: "12px" }}>
        <div style={{ display: "flex", gap: "10px", alignItems: "center", flexWrap: "wrap" }}>
          <b style={{ fontSize: "13px" }}>💱 币种：</b>
          <select style={{ ...inp, width: "200px" }} value={curCode} onChange={(e) => setCurCode(e.target.value)}>
            <option value="USD">USD 美元（默认）</option>
            <option value="ALL">全部币种</option>
            {curOpts.filter((c) => c.code !== "USD").map((c) => (
              <option key={c.code} value={c.code}>{c.code} {c.name}</option>
            ))}
          </select>
          <span style={{ fontSize: "11px", color: C.txt3 }}>数据源：领星【设置 → 汇率管理】，本页只读；修改请在领星后台操作</span>
        </div>
        <div style={{ fontSize: "11px", color: C.txt2, marginTop: "6px", lineHeight: 1.7 }}>
          折算口径：<b>我的汇率(my_rate)</b> 为主，该月未设置时退用<b>官方汇率</b>并在数值处标红。<br />
          注意：领星把头程费用摊到单品时，用的是发货月<b>上一个月</b>的我的汇率（实测：4月发货单隐含 6.8367 ≈ 3月 6.8348；5月发货单隐含 6.85 ≈ 4月 6.8500），
          本系统折算已按同一规则处理，因此单品成本与领星后台一致。
        </div>
      </div>

      {/* 仓储费CSV导入（批4；有权限才显示） */}
      {canImport && (
        <div style={{ ...card, padding: "12px 14px", marginBottom: "12px" }}>
          <div style={{ display: "flex", gap: "10px", alignItems: "center", flexWrap: "wrap" }}>
            <b style={{ fontSize: "13px" }}>📦 仓储费导入：</b>
            <StoreSearch stores={stores} value={selStore} onChange={setSelStore} listId="dl-store-storage" style={{ ...inp, width: "220px" }} />
            <input type="file" accept=".csv" style={{ fontSize: "12px" }}
              onChange={(e) => setCsvFile(e.target.files?.[0] ?? null)} />
            <button style={{ ...btn, background: C.green, color: "#fff", border: `1px solid ${C.green}`, fontWeight: 600 }}
              disabled={importing} onClick={() => void doImport()}>{importing ? "导入中…" : "导入"}</button>
            <span style={{ fontSize: "11px", color: C.txt3 }}>Seller Center → WFS → 报告 → 仓储（下载框选「结算日期」按账期逐期下载，按店铺）· 守恒不平整批拒绝 · 同期重导=覆盖更新</span>
          </div>
          {impResult && <div style={{ marginTop: "8px", fontSize: "12px", color: C.green }}>{impResult}</div>}
          <SectionBar title="导入历史" count={storShown.length} open={storOpen}
            onToggle={() => setStorOpen(!storOpen)} busy={storBusy}
            onRefresh={() => { setStorBusy(true); void loadStorage().finally(() => setStorBusy(false)); }}
            onHelp={openHelp}
            filterValue={storFilter} onFilter={(v) => { setStorFilter(v); setStorPage(1); }}
            storeOpts={storStoreOpts} />
          {storOpen && storShown.length === 0 && (
            <div style={{ fontSize: "12px", color: C.txt3, padding: "10px 4px" }}>暂无导入记录</div>
          )}
          {storOpen && storShown.length > 0 && (
            <>
            <table style={{ width: "100%", borderCollapse: "collapse", marginTop: "10px", fontSize: "12px" }}>
              <thead><tr>
                {["店铺", "报告期", "SKU数", "仓储费Σ", "折扣节省Σ", "批次", "导入人", "导入时间"].map((h) => (
                  <th key={h} style={{ textAlign: "left", padding: "5px 8px", color: C.txt2, background: "#f9fafb", boxShadow: "inset 0 -1px 0 #e5e7eb" }}>{h}</th>
                ))}
              </tr></thead>
              <tbody>
                {storShown.slice((storPage - 1) * storSize, storPage * storSize).map((r) => (
                  <tr key={r.task_id + r.report_start}>
                    <td style={{ padding: "5px 8px", borderTop: "1px solid #f3f4f6" }}>{r.store_name}</td>
                    <td style={{ padding: "5px 8px", borderTop: "1px solid #f3f4f6" }}>{r.report_start} ~ {r.report_end}</td>
                    <td style={{ padding: "5px 8px", borderTop: "1px solid #f3f4f6" }}>{r.sku_cnt}</td>
                    <td style={{ padding: "5px 8px", borderTop: "1px solid #f3f4f6", color: C.blue, fontWeight: 600 }}>${Number(r.fee_sum).toFixed(2)}</td>
                    <td style={{ padding: "5px 8px", borderTop: "1px solid #f3f4f6", color: C.green }}>${Number(r.discount_sum).toFixed(2)}</td>
                    <td style={{ padding: "5px 8px", borderTop: "1px solid #f3f4f6", color: C.txt2 }}>{r.task_id}</td>
                    <td style={{ padding: "5px 8px", borderTop: "1px solid #f3f4f6" }}>{r.operator || "—"}</td>
                    <td style={{ padding: "5px 8px", borderTop: "1px solid #f3f4f6", color: C.txt2 }}>{r.imported_at}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <MiniPager total={storShown.length} page={storPage} size={storSize}
              onPage={setStorPage} onSize={(sz) => { setStorSize(sz); setStorPage(1); }} />
            </>
          )}
        </div>
      )}

      {/* 入库运输CSV导入（批5；有权限才显示） */}
      {canImport && (
        <div style={{ ...card, padding: "12px 14px", marginBottom: "12px" }}>
          <div style={{ display: "flex", gap: "10px", alignItems: "center", flexWrap: "wrap" }}>
            <b style={{ fontSize: "13px" }}>🚚 入库运输导入：</b>
            <StoreSearch stores={stores} value={selStore2} onChange={setSelStore2} listId="dl-store-inbound" style={{ ...inp, width: "220px" }} />
            <input type="file" accept=".csv" style={{ fontSize: "12px" }}
              onChange={(e) => setInbFile(e.target.files?.[0] ?? null)} />
            <button style={{ ...btn, background: C.green, color: "#fff", border: `1px solid ${C.green}`, fontWeight: 600 }}
              disabled={inbImporting} onClick={() => void doInboundImport()}>{inbImporting ? "导入中…" : "导入"}</button>
            <span style={{ fontSize: "11px", color: C.txt3 }}>Seller Center → WFS → 报告 → 入库运输（「结算日期」按账期下载）· 货件运费按已发货数自动分摊到品 · 同期重导=覆盖更新</span>
          </div>
          {inbResult && <div style={{ marginTop: "8px", fontSize: "12px", color: inbResult.includes("⚠️") ? C.amber : C.green }}>{inbResult}</div>}
          <SectionBar title="导入历史" count={inbShown.length} open={inbOpen}
            onToggle={() => setInbOpen(!inbOpen)} busy={inbBusy}
            onRefresh={() => { setInbBusy(true); void loadInbound().finally(() => setInbBusy(false)); }}
            onHelp={openHelp}
            filterValue={inbFilter} onFilter={(v) => { setInbFilter(v); setInbPage(1); }}
            storeOpts={inbStoreOpts} />
          {inbOpen && inbShown.length === 0 && (
            <div style={{ fontSize: "12px", color: C.txt3, padding: "10px 4px" }}>暂无导入记录</div>
          )}
          {inbOpen && inbShown.length > 0 && (
            <>
            <table style={{ width: "100%", borderCollapse: "collapse", marginTop: "10px", fontSize: "12px" }}>
              <thead><tr>
                {["店铺", "报告期", "货件数", "分摊行", "运费Σ", "未匹配留存Σ", "批次", "导入人", "导入时间"].map((h) => (
                  <th key={h} style={{ textAlign: "left", padding: "5px 8px", color: C.txt2, background: "#f9fafb", boxShadow: "inset 0 -1px 0 #e5e7eb" }}>{h}</th>
                ))}
              </tr></thead>
              <tbody>
                {inbShown.slice((inbPage - 1) * inbSize, inbPage * inbSize).map((r) => (
                  <tr key={r.task_id + r.report_start}>
                    <td style={{ padding: "5px 8px", borderTop: "1px solid #f3f4f6" }}>{r.store_name}</td>
                    <td style={{ padding: "5px 8px", borderTop: "1px solid #f3f4f6" }}>{r.report_start} ~ {r.report_end}</td>
                    <td style={{ padding: "5px 8px", borderTop: "1px solid #f3f4f6" }}>{r.shipment_cnt}</td>
                    <td style={{ padding: "5px 8px", borderTop: "1px solid #f3f4f6" }}>{r.alloc_rows}</td>
                    <td style={{ padding: "5px 8px", borderTop: "1px solid #f3f4f6", color: C.blue, fontWeight: 600 }}>${Number(r.freight_sum).toFixed(2)}</td>
                    <td style={{ padding: "5px 8px", borderTop: "1px solid #f3f4f6", color: Number(r.unmatched_sum) > 0 ? C.amber : C.txt3 }}>${Number(r.unmatched_sum).toFixed(2)}</td>
                    <td style={{ padding: "5px 8px", borderTop: "1px solid #f3f4f6", color: C.txt2 }}>{r.task_id}</td>
                    <td style={{ padding: "5px 8px", borderTop: "1px solid #f3f4f6" }}>{r.operator || "—"}</td>
                    <td style={{ padding: "5px 8px", borderTop: "1px solid #f3f4f6", color: C.txt2 }}>{r.imported_at}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <MiniPager total={inbShown.length} page={inbPage} size={inbSize}
              onPage={setInbPage} onSize={(sz) => { setInbSize(sz); setInbPage(1); }} />
            </>
          )}
          {unmTotal > 0 && (
            <div style={{ marginTop: "10px", padding: "8px 10px", background: "#fffbeb", border: "1px solid #fde68a", borderRadius: "6px" }}>
              <div style={{ display: "flex", gap: "10px", alignItems: "center", flexWrap: "wrap" }}>
                <b style={{ fontSize: "12px", color: "#92400e" }}>⚠️ 未匹配留存 ${unmTotal.toFixed(2)}（{unmList.length} 个货件）</b>
                <button style={{ ...btn, fontSize: "11px" }} disabled={reBusy} onClick={() => void doReallocate(false)}>
                  {reBusy ? "处理中…" : "① 重新匹配货件"}
                </button>
                <button style={{ ...btn, fontSize: "11px", background: C.amber, color: "#fff", border: `1px solid ${C.amber}` }} disabled={reBusy} onClick={() => void doReallocate(true)}>
                  ② 二次分摊到本期SKU
                </button>
              </div>
              <div style={{ fontSize: "11px", color: "#92400e", marginTop: "5px", lineHeight: 1.6 }}>
                含义：该货件号在货件档案里查不到，运费无法落到具体SKU，暂时整额挂在货件上（钱已入账、但没进单品成本）。<br />
                处置顺序：① 先回补货件同步再点「重新匹配货件」（最优，按已发货数分摊、可溯源）；② 确认是平台幽灵/历史遗留、永远补不回来的，才点「二次分摊」——按本账期已分摊运费占比摊到本期SKU，标记 pool，保证 Σ入账=Σ账单，不留挂账。
              </div>
              {reResult && <div style={{ fontSize: "11px", color: C.txt2, marginTop: "5px" }}>{reResult}</div>}
              <table style={{ width: "100%", borderCollapse: "collapse", marginTop: "8px", fontSize: "11px" }}>
                <thead><tr>
                  {["店铺", "货件号", "报告期", "金额", "批次"].map((h) => (
                    <th key={h} style={{ textAlign: "left", padding: "4px 8px", color: C.txt2 }}>{h}</th>
                  ))}
                </tr></thead>
                <tbody>
                  {unmList.map((r) => (
                    <tr key={r.store_id + r.cargo_code}>
                      <td style={{ padding: "4px 8px", borderTop: "1px solid #fde68a" }}>{r.store_name}</td>
                      <td style={{ padding: "4px 8px", borderTop: "1px solid #fde68a", fontWeight: 600 }}>{r.cargo_code}</td>
                      <td style={{ padding: "4px 8px", borderTop: "1px solid #fde68a" }}>{r.report_start} ~ {r.report_end}</td>
                      <td style={{ padding: "4px 8px", borderTop: "1px solid #fde68a", color: C.amber, fontWeight: 600 }}>${Number(r.amount).toFixed(2)}</td>
                      <td style={{ padding: "4px 8px", borderTop: "1px solid #fde68a", color: C.txt3 }}>{r.task_id}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {/* §1 标准工具条 */}
      <div style={{ ...lxTB.filterWrap, display: "flex", alignItems: "center", gap: "10px", flexWrap: "wrap" }}>
        <button onClick={() => setFxOpen(!fxOpen)} title={fxOpen ? "收起" : "展开"}
          style={{ ...iconBtnWrap, width: "24px", height: "24px", fontSize: "11px", color: C.txt2, lineHeight: 1 }}>
          {fxOpen ? "\u25be" : "\u25b8"}
        </button>
        <span style={{ fontSize: "13px", fontWeight: 700, color: "#374151", cursor: "pointer" }}
          onClick={() => setFxOpen(!fxOpen)}>💱 汇率（领星同步 · 只读）</span>
        <span style={{ color: C.txt2, fontSize: "12px" }}>共 {rows.length} 行 · 同步 {syncedAt || "-"} · 第 {page}/{totalPages} 页</span>
        <div style={{ flex: 1 }} />
        <button style={{ ...lxTB.iconBtn, ...iconBtnWrap }} title="刷新" onClick={() => void load()} disabled={loading}><IconRefresh /></button>
        <button style={{ ...lxTB.iconBtn, ...iconBtnWrap }} title="帮助（取值口径/权限）" onClick={openHelp}><IconHelp /></button>
        <button style={{ ...lxTB.iconBtn, ...iconBtnWrap }} title="下载 CSV" onClick={exportCsv}><IconDownload /></button>
      </div>
      {fxOpen && <div style={{ fontSize: "11px", color: C.txt3, margin: "-4px 0 10px" }}>
        拖列头右缘调列宽 · 缺月=领星该月无此币种数据 · 改汇率请到领星后台 ·
        <span style={{ color: C.blue, cursor: "pointer", marginLeft: "4px" }} onClick={() => setColWidths({})}>列宽重置</span>
      </div>}

      {msg && <div style={{ ...card, padding: "10px 14px", color: C.amber, marginBottom: "10px", border: "1px solid #f9ab00", background: "#fef7e0" }}>{msg}</div>}

      {/* §8 表格：表头吸顶 + 总计吸底（随汇率区折叠） */}
      {fxOpen && <div style={{ ...card, padding: 0, overflow: "auto", maxHeight: "62vh" }}>
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
              <tr key={r.id}>{cols.map((col) => <td key={col.key} style={cellStyle(col.align)}>{cell(r, col.key)}</td>)}</tr>
            ))}
            {!rows.length && !loading && (
              <tr><td style={{ ...cellStyle("left"), textAlign: "center", color: C.txt2, padding: "22px" }} colSpan={cols.length}>
                暂无汇率记录（请确认领星汇率同步任务已执行）
              </td></tr>
            )}
          </tbody>
          {rows.length > 0 && (
            <tfoot>
              <tr>
                {cols.map((col, i) => (
                  <td key={col.key} style={{ position: "sticky", bottom: 0, zIndex: 4, background: "#eef2ff", fontWeight: 700, color: "#3730a3", borderTop: "2px solid #c7d2fe", textAlign: col.align, padding: "8px 10px", fontSize: "12px", whiteSpace: "nowrap" }}>
                    {i === 0 ? `总计（${rows.length} 行）` : ""}
                  </td>
                ))}
              </tr>
            </tfoot>
          )}
        </table>
      </div>}

      {/* §8.2 翻页控件（随汇率区折叠） */}
      {fxOpen && <div style={{ display: "flex", alignItems: "center", gap: "6px", flexWrap: "wrap", marginTop: "10px" }}>
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
        <span style={{ fontSize: "12px", color: C.txt3 }}>共 {rows.length} 条</span>
        <span style={{ fontSize: "12px", color: C.txt3 }}>跳至</span>
        <input type="number" min={1} max={totalPages} defaultValue={page} style={{ ...lxTB.filterInput, width: "60px", padding: "4px 8px" }}
          onKeyDown={(e) => { if (e.key === "Enter") { const v = Number((e.target as HTMLInputElement).value); if (v >= 1 && v <= totalPages) setPage(v); } }} />
        <span style={{ fontSize: "12px", color: C.txt3 }}>页</span>
      </div>}
    </div>
  );
}
