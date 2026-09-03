/**
 * AiFinanceCredits.tsx — AI财务系统 · 返还明细（2026-08-12 批1，UI_STANDARDS 合规版）
 * §1 LxToolbar工具条+元信息(共N行·同步·第P/T页) · §2 帮助壳内(#/help?page=finance-credits) ·
 * §5 列宽拖动+重置 · §6 KPI可隐藏(▤) · §7 表头ⓘ口径悬停 · §8 总计吸底+翻页+表头吸顶 · §9 #/finance/credits。
 * 两个内页tab：平台返还明细(fact_ad_credit_detail 行级，含自发现other:*) / 佣金折扣(fact_commission_saving 账期聚合)。
 * 只读页面：数据经 /api/finance/*（只读路由）读FACT层；人工备注列仅展示。
 */
import { useEffect, useMemo, useRef, useState } from "react";
import { lxTB, IconRefresh, IconHelp, IconDownload, IconColumns } from "./LxToolbar";
import { ItemIdLink } from "./ItemIdLink";

interface CreditRow {
  id: number; store_id: string; store_name: string; posted_date: string;
  period_start: string | null; period_end: string | null; fee_category: string;
  transaction_type: string | null; transaction_desc: string | null;
  amount: string | number; currency_code: string; campaign_id: string; source_ref: string; remark: string | null;
}
interface CreditKpi { credit_sum: number; reversal_sum: number; net_sum: number; cnt: number; category_cnt: number }
interface CommRow {
  id: number; store_id: string; store_name: string; period_start: string; period_end: string;
  msku: string; item_id: string; incentive_program: string; saving_amount: string | number; txn_count: number; remark: string | null;
}
interface CommKpi { saving_sum: number; txn_sum: number; cnt: number; program_cnt: number }

const C = { blue: "#1a73e8", txt2: "#5f6368", txt3: "#9aa0a6", line: "#dadce0", neg: "#d93025", green: "#188038", amber: "#b06f00" };
const card: React.CSSProperties = { background: "#fff", border: "1px solid #e5e7eb", borderRadius: "10px" };
const PAGE_SIZE_OPTIONS = [50, 100, 200];
const pageBtn = (active: boolean, disabled: boolean): React.CSSProperties => ({ padding: "5px 12px", borderRadius: "5px", border: "1px solid #e5e7eb", cursor: disabled ? "not-allowed" : "pointer", background: active ? "#6366f1" : "#fff", color: active ? "#fff" : "#374151", fontWeight: active ? 700 : 400, fontSize: "13px", opacity: disabled ? 0.5 : 1 });
const n2 = (v: unknown): number => { const n = Number(v); return Number.isFinite(n) ? n : 0; };
const fmt = (v: unknown): string => { const n = n2(v); return (n < 0 ? "-$" : "$") + Math.abs(n).toFixed(2); };

// 类目中文名（自发现 other:* 未正式命名前展示「待命名」原始slug）
const CAT_LABEL: Record<string, string> = {
  ad_credit: "广告返还积分", wfs_refund: "WFS费用退款", lost_inventory: "丢货赔付",
  found_inventory: "找回冲销", damage_warehouse: "仓损赔付", sem: "SEM广告返还", sem_credit: "SEM返还",
  "other:wfs_discountadjustment": "WFS折扣返还(NSS)",
  wfs_discount_adjustment: "WFS折扣返还(NSS)", inventory_transfer: "库存转移费", wfs_charge_misc: "WFS杂项扣费",
};
const catLabel = (c: string): string => CAT_LABEL[c] ?? (c.startsWith("other:") ? "待命名:" + c.slice(6) : c);

// 财年口径（需求方2026-08-12定稿）：2月1日 ~ 次年1月31日；如 2026财年=2026-02-01~2027-01-31
const fyOf = (d: string): number => {
  const y = Number(d.slice(0, 4)); const m = Number(d.slice(5, 7));
  return m >= 2 ? y : y - 1;
};
const fyLabel = (fy: number): string => `${fy}财年（${fy}-02 ~ ${fy + 1}-01）`;

type Tab = "credits" | "commission";
type ColKey = string;
const CREDIT_COLS: { key: ColKey; label: string; w: number; align: "left" | "right"; hideable: boolean; sortable: boolean; tip?: string }[] = [
  { key: "posted_date", label: "入账日期", w: 92, align: "left", hideable: false, sortable: true, tip: "statement行入账日（transactionPostedTimestamp）" },
  { key: "store", label: "店铺", w: 150, align: "left", hideable: true, sortable: false, tip: "该返还行归属的沃尔玛店铺（statement 所属店铺账号）" },
  { key: "category", label: "返还类目", w: 130, align: "left", hideable: false, sortable: true, tip: "系统类目：白名单映射+自发现（other:*=尚未正式命名的新返还类型，发现即留档不漏项）" },
  { key: "ttype", label: "原类型", w: 90, align: "left", hideable: true, sortable: false, tip: "领星statement原transactionType" },
  { key: "tdesc", label: "原描述", w: 190, align: "left", hideable: true, sortable: false, tip: "领星statement原transactionDescription" },
  { key: "amount", label: "金额$", w: 92, align: "right", hideable: false, sortable: true, tip: "正=沃尔玛向我们返还入账；负=冲回（如找回库存冲销此前的丢货赔付）" },
  { key: "period", label: "所属账期", w: 150, align: "left", hideable: true, sortable: false, tip: "该行归属的店铺账单周期（结算归桶口径）" },
  { key: "campaign", label: "CampaignID", w: 100, align: "left", hideable: true, sortable: false, tip: "广告返还类目专有：该笔返还对应的广告活动ID；非广告类返还为空" },
  { key: "remark", label: "人工备注", w: 140, align: "left", hideable: true, sortable: false, tip: "运营人工备注，系统永不覆盖" },
];
const COMM_COLS: { key: ColKey; label: string; w: number; align: "left" | "right"; hideable: boolean; sortable: boolean; tip?: string }[] = [
  { key: "period", label: "账期", w: 150, align: "left", hideable: false, sortable: true, tip: "该聚合行所属的店铺账单周期（起~止），佣金折扣按账期聚合而非按日" },
  { key: "store", label: "店铺", w: 150, align: "left", hideable: true, sortable: false, tip: "该佣金折扣聚合行归属的沃尔玛店铺" },
  { key: "msku", label: "MSKU", w: 120, align: "left", hideable: false, sortable: false, tip: "平台变体 MSKU；佣金折扣在 (店铺,账期,MSKU,激励计划) 粒度聚合" },
  { key: "item", label: "商品ID", w: 110, align: "left", hideable: true, sortable: false, tip: "沃尔玛 ItemID，点击在新标签打开沃尔玛商品页；账单未带 ItemID 时为空" },
  { key: "program", label: "激励计划", w: 150, align: "left", hideable: true, sortable: true, tip: "commissionIncentiveProgram（如 New Seller Savings=新卖家佣金折扣）；高级协议店铺折扣可超公开上限，属正常" },
  { key: "saving", label: "佣金节省$", w: 100, align: "right", hideable: false, sortable: true, tip: "Σ Sale行commissionSaving（激励中心口径）；信息指标——佣金按折后实收，不参与现金守恒" },
  { key: "txn", label: "交易行数", w: 84, align: "right", hideable: true, sortable: true, tip: "该聚合行包含的 Sale 交易行数（笔数），用于判断折扣覆盖面；0 表示该账期无成交行" },
  { key: "remark", label: "人工备注", w: 140, align: "left", hideable: true, sortable: false, tip: "运营人工备注，系统永不覆盖" },
];

export default function AiFinanceCredits({ onNavigate }: { onNavigate?: (key: string) => void }) {
  const initTab: Tab = (typeof window !== "undefined" && window.location.hash.includes("tab=commission")) ? "commission" : "credits";
  const [tab, setTab] = useState<Tab>(initTab);
  const [cRows, setCRows] = useState<CreditRow[]>([]);
  const [cKpi, setCKpi] = useState<CreditKpi | null>(null);
  const [cats, setCats] = useState<string[]>([]);
  const [mRows, setMRows] = useState<CommRow[]>([]);
  const [mKpi, setMKpi] = useState<CommKpi | null>(null);
  const [programs, setPrograms] = useState<string[]>([]);
  const [syncedAt, setSyncedAt] = useState("");
  const [kw, setKw] = useState("");
  const [fy, setFy] = useState<number | "all">(() => fyOf(new Date().toISOString().slice(0, 10)));
  const [fStore, setFStore] = useState("");
  const [fCat, setFCat] = useState("");
  const [fFrom, setFFrom] = useState("");
  const [fTo, setFTo] = useState("");
  const [showKpi, setShowKpi] = useState(true);
  const [visible, setVisible] = useState<Set<string>>(new Set([...CREDIT_COLS, ...COMM_COLS].map((c) => c.key)));
  const [showColCfg, setShowColCfg] = useState(false);
  const [colWidths, setColWidths] = useState<Record<string, number>>({});
  const [sortKey, setSortKey] = useState<string>("");
  const [sortDir, setSortDir] = useState<1 | -1>(-1);
  const [pageSize, setPageSize] = useState(50);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(false);
  const [msg, setMsg] = useState("");
  const resizeRef = useRef<{ col: string; startX: number; startW: number } | null>(null);

  // §5 列宽把手 + §7 ⓘ气泡（复用全局样式id，已注入则跳过）
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

  const fmtSync = (t: string): string => {
    const d = t ? new Date(t.replace(" ", "T")) : null;
    return d && !Number.isNaN(d.getTime()) ? d.toLocaleString("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" }) : "";
  };
  const load = async (): Promise<void> => {
    setLoading(true);
    try {
      const [r1, r2] = await Promise.all([
        fetch("/api/finance/credits/list", { credentials: "include" }),
        fetch("/api/finance/commission-savings/list", { credentials: "include" }),
      ]);
      const d1 = (await r1.json()) as { rows?: CreditRow[]; kpi?: CreditKpi; categories?: string[]; latest_sync_time?: string; error?: string };
      const d2 = (await r2.json()) as { rows?: CommRow[]; kpi?: CommKpi; programs?: string[]; latest_sync_time?: string; error?: string };
      if (!r1.ok) throw new Error(d1.error ?? String(r1.status));
      if (!r2.ok) throw new Error(d2.error ?? String(r2.status));
      setCRows(d1.rows ?? []); setCKpi(d1.kpi ?? null); setCats(d1.categories ?? []);
      setMRows(d2.rows ?? []); setMKpi(d2.kpi ?? null); setPrograms(d2.programs ?? []);
      const t1 = String(d1.latest_sync_time ?? ""), t2 = String(d2.latest_sync_time ?? "");
      setSyncedAt(fmtSync(t1 > t2 ? t1 : t2)); // 只用后端 latest_sync_time；后端为空时留空=暴露缺陷，禁止用浏览器时间伪装
    } catch (e) { setMsg("加载失败：" + (e instanceof Error ? e.message : String(e))); }
    finally { setLoading(false); }
  };
  useEffect(() => { void load(); /* eslint-disable-next-line */ }, []);
  useEffect(() => { if (!msg) return; const t = setTimeout(() => setMsg(""), 3800); return () => clearTimeout(t); }, [msg]);

  const switchTab = (t: Tab): void => {
    setTab(t); setKw(""); setFStore(""); setFCat(""); setSortKey(""); setPage(1);
    try { window.location.hash = t === "commission" ? "#/finance/credits?tab=commission" : "#/finance/credits"; } catch { /* noop */ }
  };

  const stores = useMemo(() => {
    const s = new Set<string>();
    (tab === "credits" ? cRows.map((r) => r.store_name) : mRows.map((r) => r.store_name)).forEach((x) => x && s.add(x));
    return Array.from(s).sort();
  }, [tab, cRows, mRows]);

  // 财年选项（按当前tab数据实际覆盖的财年，倒序）
  const fyOptions = useMemo(() => {
    const s = new Set<number>();
    cRows.forEach((r) => s.add(fyOf(r.posted_date)));
    mRows.forEach((r) => s.add(fyOf(r.period_start)));
    return Array.from(s).sort((a, b) => b - a);
  }, [cRows, mRows]);
  const inFy = (d: string): boolean => fy === "all" || fyOf(d) === fy;

  // 筛选+排序（客户端；行级数据量小）
  const viewC = useMemo(() => {
    if (tab !== "credits") return [] as CreditRow[];
    let out = cRows.filter((r) => inFy(r.posted_date));
    if (fStore) out = out.filter((r) => r.store_name === fStore);
    if (fCat) out = out.filter((r) => r.fee_category === fCat);
    if (fFrom) out = out.filter((r) => r.posted_date >= fFrom);
    if (fTo) out = out.filter((r) => r.posted_date <= fTo);
    const q = kw.trim().toLowerCase();
    if (q) out = out.filter((r) => (r.transaction_desc ?? "").toLowerCase().includes(q) || (r.transaction_type ?? "").toLowerCase().includes(q) || r.fee_category.toLowerCase().includes(q) || catLabel(r.fee_category).includes(kw.trim()) || (r.campaign_id ?? "").includes(kw.trim()));
    if (sortKey === "amount") out.sort((a, b) => (n2(a.amount) - n2(b.amount)) * sortDir);
    else if (sortKey === "category") out.sort((a, b) => a.fee_category.localeCompare(b.fee_category) * sortDir);
    else if (sortKey === "posted_date") out.sort((a, b) => a.posted_date.localeCompare(b.posted_date) * sortDir);
    return out;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tab, cRows, fy, fStore, fCat, fFrom, fTo, kw, sortKey, sortDir]);

  const viewM = useMemo(() => {
    if (tab !== "commission") return [] as CommRow[];
    let out = mRows.filter((r) => inFy(r.period_start));
    if (fStore) out = out.filter((r) => r.store_name === fStore);
    if (fCat) out = out.filter((r) => r.incentive_program === fCat);
    if (fFrom) out = out.filter((r) => r.period_end >= fFrom);
    if (fTo) out = out.filter((r) => r.period_start <= fTo);
    const q = kw.trim().toLowerCase();
    if (q) out = out.filter((r) => r.msku.toLowerCase().includes(q) || r.item_id.includes(kw.trim()) || r.incentive_program.toLowerCase().includes(q));
    if (sortKey === "saving") out.sort((a, b) => (n2(a.saving_amount) - n2(b.saving_amount)) * sortDir);
    else if (sortKey === "txn") out.sort((a, b) => (a.txn_count - b.txn_count) * sortDir);
    else if (sortKey === "program") out.sort((a, b) => a.incentive_program.localeCompare(b.incentive_program) * sortDir);
    else if (sortKey === "period") out.sort((a, b) => a.period_start.localeCompare(b.period_start) * sortDir);
    return out;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tab, mRows, fy, fStore, fCat, fFrom, fTo, kw, sortKey, sortDir]);

  const viewLen = tab === "credits" ? viewC.length : viewM.length;
  const totalPages = Math.max(1, Math.ceil(viewLen / pageSize));
  useEffect(() => { setPage(1); }, [tab, fy, fStore, fCat, fFrom, fTo, kw, sortKey, sortDir, pageSize]);
  useEffect(() => { if (page > totalPages) setPage(totalPages); }, [page, totalPages]);

  const totC = useMemo(() => viewC.reduce((t, r) => { const a = n2(r.amount); return { amt: t.amt + a, pos: t.pos + (a >= 0 ? a : 0), neg: t.neg + (a < 0 ? a : 0) }; }, { amt: 0, pos: 0, neg: 0 }), [viewC]);
  const totM = useMemo(() => viewM.reduce((t, r) => ({ sv: t.sv + n2(r.saving_amount), tx: t.tx + n2(r.txn_count) }), { sv: 0, tx: 0 }), [viewM]);

  const COLS = tab === "credits" ? CREDIT_COLS : COMM_COLS;
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
    try { window.location.hash = "#/help?page=finance-credits"; } catch { /* noop */ }
  };
  const exportCsv = (): void => {
    let data: (string | number)[][];
    let name: string;
    if (tab === "credits") {
      data = [["入账日期", "店铺", "返还类目", "系统类目slug", "原类型", "原描述", "金额", "账期始", "账期止", "CampaignID", "人工备注"]];
      for (const r of viewC) data.push([r.posted_date, r.store_name, catLabel(r.fee_category), r.fee_category, r.transaction_type ?? "", r.transaction_desc ?? "", n2(r.amount), r.period_start ?? "", r.period_end ?? "", r.campaign_id, r.remark ?? ""]);
      name = "返还明细";
    } else {
      data = [["账期始", "账期止", "店铺", "MSKU", "商品ID", "激励计划", "佣金节省", "交易行数", "人工备注"]];
      for (const r of viewM) data.push([r.period_start, r.period_end, r.store_name, r.msku, r.item_id, r.incentive_program, n2(r.saving_amount), r.txn_count, r.remark ?? ""]);
      name = "佣金折扣";
    }
    const csv = "﻿" + data.map((row) => row.map((v) => `"${String(v).replace(/"/g, '""')}"`).join(",")).join("\n");
    const a = document.createElement("a");
    a.href = URL.createObjectURL(new Blob([csv], { type: "text/csv;charset=utf-8" }));
    a.download = `AI财务_${name}_${syncedAt || "export"}.csv`;
    a.click(); URL.revokeObjectURL(a.href);
  };

  // §6 KPI（2026-08-12 需求方定稿：按项目=类目/激励计划 显示财年总额；财年=2月~次年1月，随财年下拉切换；点卡片=按该项目筛选表格）
  const kpiCards = useMemo(() => {
    if (tab === "credits") {
      const byCat = new Map<string, { amt: number; cnt: number }>();
      let net = 0, cnt = 0;
      for (const r of cRows) {
        if (!inFy(r.posted_date)) continue;
        const a = n2(r.amount); net += a; cnt += 1;
        const e = byCat.get(r.fee_category) ?? { amt: 0, cnt: 0 };
        e.amt += a; e.cnt += 1; byCat.set(r.fee_category, e);
      }
      const cards = [{ lbl: fy === "all" ? "净额（全部年度）" : "净额（本财年）", val: fmt(net), sub: `${cnt} 笔`, bg: "#e8f0fe", fg: C.blue, k: "" }];
      Array.from(byCat.entries()).sort((a, b) => Math.abs(b[1].amt) - Math.abs(a[1].amt)).forEach(([cat, e]) => {
        cards.push({
          lbl: catLabel(cat), val: fmt(e.amt), sub: `${e.cnt} 笔`,
          bg: e.amt >= 0 ? (cat.startsWith("other:") ? "#fef7e0" : "#e6f4ea") : "#fce8e6",
          fg: e.amt >= 0 ? (cat.startsWith("other:") ? C.amber : C.green) : C.neg, k: cat,
        });
      });
      return cards;
    }
    const byProg = new Map<string, { amt: number; cnt: number }>();
    let sum = 0, cnt = 0;
    for (const r of mRows) {
      if (!inFy(r.period_start)) continue;
      const a = n2(r.saving_amount); sum += a; cnt += 1;
      const e = byProg.get(r.incentive_program) ?? { amt: 0, cnt: 0 };
      e.amt += a; e.cnt += 1; byProg.set(r.incentive_program, e);
    }
    const cards = [{ lbl: fy === "all" ? "佣金折扣Σ（全部年度）" : "佣金折扣Σ（本财年）", val: fmt(sum), sub: `${cnt} 聚合行`, bg: "#e8f0fe", fg: C.blue, k: "" }];
    Array.from(byProg.entries()).sort((a, b) => b[1].amt - a[1].amt).forEach(([prog, e]) => {
      cards.push({ lbl: prog || "（未标注计划）", val: fmt(e.amt), sub: `${e.cnt} 聚合行`, bg: "#e6f4ea", fg: C.green, k: prog });
    });
    return cards;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tab, cRows, mRows, fy]);

  const cellStyle = (align: "left" | "right"): React.CSSProperties =>
    ({ textAlign: align, padding: "7px 10px", fontSize: "12px", borderTop: "1px solid #f3f4f6", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis", fontVariantNumeric: "tabular-nums" });
  const catChip = (c: string): React.CSSProperties =>
    c.startsWith("other:") ? { background: "#fef7e0", color: C.amber } : c === "found_inventory" ? { background: "#f1f3f4", color: C.txt2 } : { background: "#e6f4ea", color: C.green };

  const cellC = (r: CreditRow, key: string): React.ReactNode => {
    switch (key) {
      case "posted_date": return r.posted_date;
      case "store": return <span style={{ color: C.txt2 }}>{r.store_name}</span>;
      case "category": return <span title={r.fee_category} style={{ padding: "2px 10px", borderRadius: "12px", fontSize: "12px", ...catChip(r.fee_category) }}>{catLabel(r.fee_category)}</span>;
      case "ttype": return <span style={{ color: C.txt2 }}>{r.transaction_type || "—"}</span>;
      case "tdesc": return <span title={r.transaction_desc ?? ""}>{r.transaction_desc || "—"}</span>;
      case "amount": { const a = n2(r.amount); return <span style={{ color: a >= 0 ? C.green : C.neg, fontWeight: 600 }}>{a >= 0 ? "+" : ""}{fmt(a)}</span>; }
      case "period": return r.period_start ? `${r.period_start} ~ ${r.period_end ?? ""}` : "—";
      case "campaign": return r.campaign_id || "—";
      case "remark": return <span title={r.remark ?? ""} style={{ color: C.txt2 }}>{r.remark || "—"}</span>;
      default: return null;
    }
  };
  const cellM = (r: CommRow, key: string): React.ReactNode => {
    switch (key) {
      case "period": return `${r.period_start} ~ ${r.period_end}`;
      case "store": return <span style={{ color: C.txt2 }}>{r.store_name}</span>;
      case "msku": return <b>{r.msku || "—"}</b>;
      case "item": return r.item_id ? <ItemIdLink itemId={r.item_id} /> : "—";
      case "program": return r.incentive_program || "—";
      case "saving": return <span style={{ color: C.green, fontWeight: 600 }}>+{fmt(r.saving_amount)}</span>;
      case "txn": return r.txn_count.toLocaleString();
      case "remark": return <span title={r.remark ?? ""} style={{ color: C.txt2 }}>{r.remark || "—"}</span>;
      default: return null;
    }
  };
  const tfootCell = (key: string): string => {
    if (tab === "credits") {
      if (key === "posted_date") return `总计（${viewC.length}行）`;
      if (key === "amount") return fmt(totC.amt);
      if (key === "category") return `入${fmt(totC.pos)}/冲${fmt(totC.neg)}`;
    } else {
      if (key === "period") return `总计（${viewM.length}行）`;
      if (key === "saving") return fmt(totM.sv);
      if (key === "txn") return totM.tx.toLocaleString();
    }
    return "";
  };

  return (
    <div>
      <p style={{ color: C.txt2, margin: "0 0 12px", fontSize: "12px", lineHeight: 1.6 }}>
        沃尔玛向我们返钱的全景留档：店铺账单(statement)行级自动捕捉——白名单类目 + 自发现（未知返还类型自动带「待命名」标签浮出，不漏项）；
        <b>广告返还积分自2026-08-19起取自 Walmart Connect 广告发票内抵扣</b>（原描述带发票号可溯；statement同类行不再计入——Seller Center通道两边留痕会双计、信用卡通道statement无痕会漏计）；
        佣金折扣为激励中心口径的信息指标（佣金按折后实收，不参与现金守恒）。数据只读，来源 AI财务数据管道每日同步。
      </p>

      {/* 内页tab（§9：hash二级后缀 #/finance/credits[?tab=commission]） */}
      <div style={{ display: "flex", gap: "8px", marginBottom: "10px" }}>
        {(["credits", "commission"] as const).map((t) => (
          <button key={t} onClick={() => switchTab(t)}
            style={{ padding: "6px 16px", borderRadius: "6px", fontSize: "13px", fontWeight: 600, cursor: "pointer",
              border: tab === t ? `1px solid ${C.blue}` : "1px solid #d1d5db",
              background: tab === t ? C.blue : "#fff", color: tab === t ? "#fff" : "#374151" }}>
            {t === "credits" ? "平台返还明细" : "佣金折扣"}
          </button>
        ))}
      </div>

      {/* §1 标准工具条 */}
      <div style={{ ...lxTB.filterWrap, display: "flex", alignItems: "center", gap: "10px", flexWrap: "wrap" }}>
        <select value={String(fy)} onChange={(e) => setFy(e.target.value === "all" ? "all" : Number(e.target.value))} style={{ ...lxTB.filterInput, width: "185px", fontWeight: 600 }}>
          <option value="all">全部年度</option>
          {fyOptions.map((y) => <option key={y} value={y}>{fyLabel(y)}</option>)}
        </select>
        <input type="date" value={fFrom} onChange={(e) => setFFrom(e.target.value)} style={{ ...lxTB.filterInput, width: "130px" }} />
        <span style={{ color: C.txt3 }}>~</span>
        <input type="date" value={fTo} onChange={(e) => setFTo(e.target.value)} style={{ ...lxTB.filterInput, width: "130px" }} />
        <select value={fStore} onChange={(e) => setFStore(e.target.value)} style={{ ...lxTB.filterInput, width: "170px" }}>
          <option value="">全部店铺</option>
          {stores.map((s) => <option key={s} value={s}>{s}</option>)}
        </select>
        <select value={fCat} onChange={(e) => setFCat(e.target.value)} style={{ ...lxTB.filterInput, width: "160px" }}>
          <option value="">{tab === "credits" ? "全部类目" : "全部激励计划"}</option>
          {(tab === "credits" ? cats : programs).map((c) => <option key={c} value={c}>{tab === "credits" ? catLabel(c) : c}</option>)}
        </select>
        <input placeholder={tab === "credits" ? "搜索 描述/类型/类目/CampaignID…" : "搜索 MSKU/商品ID/激励计划…"} value={kw} onChange={(e) => setKw(e.target.value)}
          style={{ ...lxTB.filterInput, width: "220px" }} />
        <span style={{ color: C.txt2, fontSize: "12px" }}>共 {viewLen} 行 · 同步 {syncedAt || "-"} · 第 {page}/{totalPages} 页</span>
        <div style={{ flex: 1 }} />
        <button style={lxTB.iconBtn} title="隐藏 / 显示 顶部KPI" onClick={() => setShowKpi((v) => !v)}><span style={{ color: C.txt2, fontSize: "14px" }}>▤</span></button>
        <button style={lxTB.iconBtn} title="刷新" onClick={() => void load()} disabled={loading}><IconRefresh /></button>
        <button style={lxTB.iconBtn} title="帮助（类目口径/自发现规则）" onClick={openHelp}><IconHelp /></button>
        <button style={lxTB.iconBtn} title="下载 CSV（当前筛选）" onClick={exportCsv}><IconDownload /></button>
        <button style={lxTB.iconBtn} title="列配置" onClick={() => setShowColCfg(true)}><IconColumns /></button>
        <button style={lxTB.iconBtn} title="列宽重置（恢复默认列宽）" onClick={() => setColWidths({})}><span style={{ fontSize: "14px", lineHeight: 1 }}>↔</span></button>
      </div>

      <div style={{ fontSize: "11px", color: C.txt3, margin: "-4px 0 10px" }}>
        拖列头右缘调列宽 · 点值列表头排序（↑↓⇅）· ▤ 收起顶部KPI · KPI=各项目财年总额（财年=2月~次年1月，左侧下拉切换），点卡片按该项目筛选 · 「待命名」=自发现的新返还类型，待正式命名归类 · 列宽重置见右侧工具区 ↔
      </div>

      {/* §6 KPI 可隐藏：按项目（类目/激励计划）的财年总额；点卡片=按该项目筛选表格 */}
      {showKpi && kpiCards.length > 0 && (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(150px, 1fr))", gap: "10px", marginBottom: "12px" }}>
          {kpiCards.map((k) => (
            <div key={k.lbl} onClick={() => { if (k.k) setFCat(fCat === k.k ? "" : k.k); }}
              style={{ background: k.bg, borderRadius: "10px", padding: "10px 12px", cursor: k.k ? "pointer" : "default",
                outline: k.k && fCat === k.k ? `2px solid ${C.blue}` : "none" }}>
              <div style={{ fontSize: "12px", color: k.fg, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{k.lbl}</div>
              <div style={{ fontSize: "20px", fontWeight: 700, color: k.fg, whiteSpace: "nowrap" }}>{k.val}</div>
              <div style={{ fontSize: "11px", color: k.fg, opacity: 0.75 }}>{k.sub}</div>
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
              <span style={{ fontSize: "14px", fontWeight: 700, color: "#374151" }}>列配置（{tab === "credits" ? "平台返还明细" : "佣金折扣"}）</span>
              <button onClick={() => setShowColCfg(false)} style={{ border: "none", background: "none", fontSize: "18px", cursor: "pointer", color: "#9ca3af" }}>×</button>
            </div>
            {COLS.map((col) => (
              <label key={col.key} style={{ display: "flex", alignItems: "center", gap: "8px", padding: "5px 0", cursor: col.hideable ? "pointer" : "not-allowed", fontSize: "13px", opacity: col.hideable ? 1 : 0.5 }}>
                <input type="checkbox" checked={visible.has(col.key)} disabled={!col.hideable}
                  onChange={() => setVisible((prev) => { const s = new Set(prev); if (s.has(col.key)) { s.delete(col.key); } else { s.add(col.key); } return s; })} />
                <span style={{ color: "#374151" }}>{col.label}</span>
              </label>
            ))}
            <div style={{ display: "flex", gap: "8px", justifyContent: "flex-end", marginTop: "10px" }}>
              <button style={lxTB.resetBtn} onClick={() => setVisible(new Set([...CREDIT_COLS, ...COMM_COLS].map((c) => c.key)))}>全选</button>
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
                    {col.tip && <i className="lxfin-info" onClick={(e) => e.stopPropagation()}>i<span className="lxfin-tip">{col.tip}</span></i>}
                    {col.sortable && <span style={{ color: active ? C.blue : "#c7cbd4", marginLeft: "3px" }}>{active ? (sortDir === 1 ? "↑" : "↓") : "⇅"}</span>}
                    <span className="lx-colresize" onMouseDown={(e) => startResize(e, col.key, e.currentTarget.parentElement as HTMLElement)} onClick={(e) => e.stopPropagation()} />
                  </th>
                );
              })}
            </tr>
          </thead>
          <tbody>
            {tab === "credits"
              ? viewC.slice((page - 1) * pageSize, page * pageSize).map((r) => (
                  <tr key={r.id}>{cols.map((col) => <td key={col.key} style={cellStyle(col.align)}>{cellC(r, col.key)}</td>)}</tr>
                ))
              : viewM.slice((page - 1) * pageSize, page * pageSize).map((r) => (
                  <tr key={r.id}>{cols.map((col) => <td key={col.key} style={cellStyle(col.align)}>{cellM(r, col.key)}</td>)}</tr>
                ))}
            {!viewLen && !loading && <tr><td style={{ ...cellStyle("left"), textAlign: "center", color: C.txt2, padding: "22px" }} colSpan={cols.length}>无数据</td></tr>}
          </tbody>
          {viewLen > 0 && (
            <tfoot>
              <tr>
                {cols.map((col) => (
                  <td key={col.key} style={{ position: "sticky", bottom: 0, zIndex: 4, background: "#eef2ff", fontWeight: 700, color: "#3730a3", borderTop: "2px solid #c7d2fe", textAlign: col.align, padding: "8px 10px", fontSize: "12px", whiteSpace: "nowrap", fontVariantNumeric: "tabular-nums" }}>
                    {tfootCell(col.key)}
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
        {PAGE_SIZE_OPTIONS.map((ps) => <button key={ps} style={pageBtn(pageSize === ps, false)} onClick={() => { setPageSize(ps); setPage(1); }}>{ps}</button>)}
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
        <span style={{ fontSize: "12px", color: C.txt3 }}>共 {viewLen} 条</span>
        <span style={{ fontSize: "12px", color: C.txt3 }}>跳至</span>
        <input type="number" min={1} max={totalPages} defaultValue={page} style={{ ...lxTB.filterInput, width: "60px", padding: "4px 8px" }}
          onKeyDown={(e) => { if (e.key === "Enter") { const v = Number((e.target as HTMLInputElement).value); if (v >= 1 && v <= totalPages) setPage(v); } }} />
        <span style={{ fontSize: "12px", color: C.txt3 }}>页</span>
      </div>
    </div>
  );
}
