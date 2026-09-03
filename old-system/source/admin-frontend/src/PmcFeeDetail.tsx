/**
 * PmcFeeDetail.tsx — 智能PMC·仓储费 / 入库运输 明细页（2026-08-18 新增，样板=OrderProfitV2 全合规页）
 * 两个独立入口共用本组件：kind="storage"(#/pmc/storage-fee) / kind="inbound"(#/pmc/inbound-freight)
 * 视图（仿沃尔玛 Seller Center）：账单(默认，账期原行) / 自定义日期(仓储=日摊求和；入库=账期交集原行，费用不按天拆分)
 * UI_STANDARDS 对照（逐条读原文实现）：
 *   §1工具条+元信息 §2帮助壳内跳转 §5列宽拖动+重置+提示文案 §6KPI可隐藏 §7表头ⓘ §8吸顶/吸底/翻页
 *   §9 hash路由 §11列配置=领星式680px弹窗(草稿态) §12数值0与空值可区分 §13行列高亮十字#eef2ff §16筛选一律LxMultiSelect多选
 * 接口：GET /api/pmc/fee-detail/{storage|inbound}/list?mode=bill|custom&date_start&date_end（登录即可读）
 */
import { useEffect, useMemo, useRef, useState } from "react";
import { lxTB, IconRefresh, IconHelp, IconDownload, IconColumns } from "./LxToolbar";
import { ItemIdLink } from "./ItemIdLink";
import { DateRangePicker, DATE_QUICK_OPTIONS, fmtDateYmd } from "./LxDateRange";
import LxMultiSelect from "./LxMultiSelect";

type Kind = "storage" | "inbound";
type Mode = "bill" | "custom";

interface RowAny { [k: string]: string | number | null | undefined }
interface Resp {
  mode: Mode; latest_sync_time: string | null; rows: RowAny[];
  daily_min?: string; daily_max?: string; period_min?: string; period_max?: string;
  date_start?: string; date_end?: string; error?: string;
}

const C = { blue: "#1a73e8", txt2: "#5f6368", neg: "#d93025", green: "#188038" };
const card: React.CSSProperties = { background: "#fff", border: "1px solid #e5e7eb", borderRadius: "10px" };
const PAGE_SIZES = [50, 100, 200];
const MAX_PINNED_COLUMNS = 7;   // §11.4
const HL_BG = "#eef2ff";        // §13
const pageBtn = (active: boolean, disabled: boolean): React.CSSProperties => ({ padding: "5px 12px", borderRadius: "5px", border: "1px solid #e5e7eb", cursor: disabled ? "not-allowed" : "pointer", background: active ? "#6366f1" : "#fff", color: active ? "#fff" : "#374151", fontWeight: active ? 700 : 400, fontSize: "13px", opacity: disabled ? 0.5 : 1 });

interface Col { key: string; label: string; w: number; align: "left" | "right"; tip?: string; num?: boolean; int?: boolean; cur?: boolean; noTotal?: boolean; dec?: number }

const COMMON_PRODUCT_COLS: Col[] = [
  { key: "store_name", label: "店铺", w: 150, align: "left", tip: "事实表store_id经dim_store/dim_store_config映射店铺名" },
  { key: "msku", label: "MSKU", w: 130, align: "left", tip: "沃尔玛账单原文SKU列=MSKU" },
  { key: "sku", label: "SKU", w: 96, align: "left", tip: "本地SKU=dim_product(店铺+商品ID+MSKU)，历史下架品可能为空显示—" },
  { key: "owner", label: "负责人", w: 76, align: "left", tip: "dim_product 负责人（店铺+商品ID+MSKU，兜底店铺+商品ID）" },
  { key: "item_id", label: "商品ID", w: 116, align: "left", tip: "导入时经 dim_product 映射回填（当前100%覆盖）" },
];

const STORAGE_BILL_COLS: Col[] = [
  ...COMMON_PRODUCT_COLS,
  { key: "gtin", label: "GTIN", w: 130, align: "left", tip: "沃尔玛仓储报告原文GTIN" },
  { key: "report_start", label: "账期起", w: 92, align: "left", tip: "沃尔玛仓储报告 report period 起日（约两周一期）" },
  { key: "report_end", label: "账期止", w: 92, align: "left", tip: "沃尔玛仓储报告 report period 止日（含）" },
  { key: "days_in_period", label: "计费天数", w: 74, align: "right", num: true, int: true, tip: "账单原文 Days in report period" },
  { key: "avg_units_standard", dec: 3, label: "标准件均量", w: 90, align: "right", num: true, noTotal: true, tip: "账单原文：报告期日均标准仓储件数（件均量不做合计）" },
  { key: "avg_units_longterm", dec: 3, label: "长期件均量", w: 90, align: "right", num: true, noTotal: true, tip: "账单原文：报告期日均长期仓储(>365天)件数（件均量不做合计）" },
  { key: "original_amount", dec: 5, label: "原始金额$", w: 88, align: "right", num: true, cur: true, tip: "折扣前仓储费（账单原文 Original amount）" },
  { key: "discount_savings", dec: 5, label: "折扣减免$", w: 88, align: "right", num: true, cur: true, tip: "沃尔玛折扣减免（账单原文 Discount savings）" },
  { key: "final_storage_fee", dec: 5, label: "最终仓储费$", w: 96, align: "right", num: true, cur: true, tip: "实收仓储费=原始金额−折扣减免；导入守恒门禁：Σ本列↔账单头部Total 差>$0.5整批拒收；官方公式=单件日费率×件均量×天数−折扣" },
  { key: "unit_fee_standard", label: "标准单件日费$", dec: 6, w: 104, align: "right", num: true, noTotal: true, tip: "账单原文 Standard: daily storage fee per unit——1-9月标准仓储单件每日费率；仅新版报告含此列，历史账期重导后补齐，缺失显示—" },
  { key: "unit_fee_peak", label: "旺季单件日费$", dec: 6, w: 104, align: "right", num: true, noTotal: true, tip: "账单原文 Peak: daily storage fee per unit——10-12月旺季单件每日费率；缺失显示—" },
  { key: "unit_fee_lt366", label: "长期366-450日费$", dec: 6, w: 118, align: "right", num: true, noTotal: true, tip: "账单原文 Long-term (366-450 days): daily storage fee per unit——库龄366-450天单件每日费率；缺失显示—" },
  { key: "unit_fee_lt450", label: "长期450+日费$", dec: 6, w: 108, align: "right", num: true, noTotal: true, tip: "账单原文 Long-term (450+ days): daily storage fee per unit——库龄超450天单件每日费率；缺失显示—" },
  { key: "length_in", dec: 3, label: "长(in)", w: 66, align: "right", num: true, noTotal: true, tip: "履约中心实测包装长度(英寸)，沃尔玛计费依据；与实物差异明显可开Case申诉（见WFS费用异常帮助）；缺失显示—" },
  { key: "width_in", dec: 3, label: "宽(in)", w: 66, align: "right", num: true, noTotal: true, tip: "履约中心实测包装宽度(英寸)；缺失显示—" },
  { key: "height_in", dec: 3, label: "高(in)", w: 66, align: "right", num: true, noTotal: true, tip: "履约中心实测包装高度(英寸)；缺失显示—" },
  { key: "weight_lb", dec: 3, label: "重量(lb)", w: 72, align: "right", num: true, noTotal: true, tip: "履约中心实测包装重量(磅)；缺失显示—" },
  { key: "avg_units_peak", dec: 3, label: "旺季件均量", w: 84, align: "right", num: true, noTotal: true, tip: "账单原文：报告期内按旺季费率计费的日均件数；缺失显示—" },
  { key: "avg_units_lt366", dec: 3, label: "长期366-450件均", w: 112, align: "right", num: true, noTotal: true, tip: "账单原文：报告期内按长期(366-450天)费率计费的日均件数；缺失显示—" },
  { key: "avg_units_lt450", dec: 3, label: "长期450+件均", w: 100, align: "right", num: true, noTotal: true, tip: "账单原文：报告期内按长期(450+天)费率计费的日均件数；缺失显示—" },
  { key: "source_task_id", label: "导入批次", w: 156, align: "left", tip: "财务工具仓储CSV导入批次号（WMSTOR-日期-序号），可追溯RAW原文" },
];

const STORAGE_CUSTOM_COLS: Col[] = [
  ...COMMON_PRODUCT_COLS,
  { key: "gtin", label: "GTIN", w: 130, align: "left", tip: "日摊表继承账单GTIN" },
  { key: "days_covered", label: "覆盖天数", w: 74, align: "right", num: true, int: true, noTotal: true, tip: "所选区间内该SKU有日摊记录的天数；小于区间天数=部分日期无账期覆盖（未出账）" },
  { key: "storage_fee", label: "仓储费$", w: 96, align: "right", num: true, cur: true, tip: "fact_storage_fee_daily：账期总额÷账期天数均摊到日后按所选区间求和（末日吸收舍入差，逐期守恒）；区间取全量时=账单合计" },
];

const INBOUND_COLS: Col[] = [
  { key: "store_name", label: "店铺", w: 150, align: "left", tip: "事实表store_id经dim_store/dim_store_config映射店铺名" },
  { key: "settlement_month", label: "结算月", w: 76, align: "left", tip: "费用归属结算月（沃尔玛账单）" },
  { key: "report_start", label: "账期起", w: 92, align: "left", tip: "沃尔玛入库运输报告期起日；自定义日期视图=账期与所选区间有交集的行" },
  { key: "report_end", label: "账期止", w: 92, align: "left", tip: "沃尔玛入库运输报告期止日（含）" },
  { key: "cargo_code", label: "货件号", w: 120, align: "left", tip: "沃尔玛账单Shipment ID=领星货件单号（WFA/WFB后缀通配，探针15实锤）" },
  { key: "shipment_id", label: "领星货件ID", w: 100, align: "left", tip: "领星货件id（关联fact_wfs_shipment/fact_wfs_shipment_item）" },
  { key: "msku", label: "MSKU", w: 130, align: "left", tip: "货件明细分摊到的品；未分摊(none)行为空显示—" },
  { key: "sku", label: "SKU", w: 96, align: "left", tip: "本地SKU=dim_product，兜底领星货件明细sku；为空显示—" },
  { key: "owner", label: "负责人", w: 76, align: "left", tip: "dim_product 负责人" },
  { key: "item_id", label: "商品ID", w: 116, align: "left", tip: "dim_product映射（分摊行100%覆盖）" },
  { key: "gtin", label: "GTIN", w: 130, align: "left", tip: "领星货件明细(fact_wfs_shipment_item)按 货件+MSKU 关联；关联不上显示—" },
  { key: "declare_num", label: "申报数量", w: 76, align: "right", num: true, int: true, tip: "分摊所用数量（主口径=已发货数，兜底申报数）" },
  { key: "freight_total", label: "货件运费$", w: 90, align: "right", num: true, cur: true, noTotal: true, tip: "该货件账单运费总额；同货件多品行重复显示本值，合计行按货件去重求和（不逐行加总）" },
  { key: "alloc_amount", label: "分摊金额$", w: 90, align: "right", num: true, cur: true, tip: "=货件运费×该品数量占比；Σ分摊=货件运费（守恒）" },
  { key: "alloc_basis", label: "分摊依据", w: 84, align: "left", tip: "shipped=按已发货数(主口径)；declare=按申报数兜底；none=货件未匹配整额留存(中间态)；pool=货件档案缺失按同账期占比二次分摊" },
  { key: "source_task_id", label: "导入批次", w: 156, align: "left", tip: "财务工具入库运输CSV导入批次号（WMINB-日期-序号），可追溯RAW原文" },
];

const BASIS_LABEL: Record<string, string> = { shipped: "按发货数", declare: "按申报数", none: "未分摊", pool: "池摊" };

// §12：数值0必须显示0，仅 null/undefined 显示占位符；禁 falsy 写法
const fm = (v: number | null | undefined, int = false): string => {
  if (v == null) return "-";
  if (int) return String(Math.round(v));
  return v.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
};

export default function PmcFeeDetail({ kind, onNavigate }: { kind: Kind; onNavigate?: (p: string) => void }): JSX.Element {
  const title = kind === "storage" ? "仓储费" : "入库运输";
  const helpKey = kind === "storage" ? "pmc-storage-fee" : "pmc-inbound-freight";

  const [mode, setMode] = useState<Mode>("bill");
  const [data, setData] = useState<Resp | null>(null);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState("");
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [activeQuick, setActiveQuick] = useState<number | null>(3);
  const [kw, setKw] = useState("");
  const [store, setStore] = useState<string[]>([]);
  const [owner, setOwner] = useState<string[]>([]);
  const [period, setPeriod] = useState<string[]>([]); // 仓储=账期，入库=结算月（§16 多选）
  const [applied, setApplied] = useState<{ kw: string; stores: string[]; owners: string[]; periods: string[] }>({ kw: "", stores: [], owners: [], periods: [] });
  const [kpiHidden, setKpiHidden] = useState(false);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(50);
  const [jump, setJump] = useState("");
  const [sortKey, setSortKey] = useState<string>("report_start");
  const [sortDir, setSortDir] = useState<1 | -1>(-1);
  const [colW, setColW] = useState<Record<string, number>>({});
  const [tipKey, setTipKey] = useState("");
  const [hl, setHl] = useState<{ row: string; col: string } | null>(null);

  const COLS: Col[] = useMemo(() =>
    kind === "inbound" ? INBOUND_COLS : mode === "bill" ? STORAGE_BILL_COLS : STORAGE_CUSTOM_COLS,
  [kind, mode]);
  const ALL_KEYS = useMemo(() => COLS.map((c) => c.key), [COLS]);
  const colByKey = (k: string): Col => COLS.find((c) => c.key === k) as Col;
  const DEFAULT_PINNED = useMemo(() => ["store_name", "msku"].filter((k) => ALL_KEYS.includes(k)), [ALL_KEYS]);

  // §11 列配置：生效态 + 弹窗草稿态（kind/mode 切换时重置为全列）
  const [selectedCols, setSelectedCols] = useState<string[]>(ALL_KEYS);
  const [pinnedCols, setPinnedCols] = useState<string[]>(DEFAULT_PINNED);
  const [showColumnConfig, setShowColumnConfig] = useState(false);
  const [cfgSelected, setCfgSelected] = useState<string[]>(ALL_KEYS);
  const [cfgPins, setCfgPins] = useState<string[]>(DEFAULT_PINNED);
  const dragColIdxRef = useRef<number | null>(null);
  useEffect(() => { setSelectedCols(ALL_KEYS); setPinnedCols(DEFAULT_PINNED); }, [ALL_KEYS, DEFAULT_PINNED]);

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
  }, []);

  // 2026-08-19 修复（批B-5同款）：店铺/负责人下拉选项跨加载累积并集，禁止从当前返回数据派生——
  // 否则窄日期区间返回的行会把选项自身过滤（如 06-06~06-12 只剩4店），且已选店铺不在选项表时
  // LxMultiSelect 兜底显示原始 store_id 数字。进页默认账单视图=全量数据，首次加载即得完整选项。
  const [storeOptAcc, setStoreOptAcc] = useState<Record<string, string>>({});
  const [ownerOptAcc, setOwnerOptAcc] = useState<string[]>([]);
  const load = (m: Mode, f?: string, t?: string): void => {
    setLoading(true); setErr("");
    const q = new URLSearchParams({ mode: m });
    if (m === "custom") {
      if (f) q.set("date_start", f);
      if (t) q.set("date_end", t);
    }
    fetch(`/api/pmc/fee-detail/${kind === "storage" ? "storage" : "inbound"}/list?${q.toString()}`, { credentials: "include" })
      .then((r) => r.json())
      .then((d: Resp) => {
        if (d.error) { setErr(d.error); return; }
        setData(d); setPage(1);
        setStoreOptAcc((prev) => {
          const acc = { ...prev };
          for (const r of d.rows ?? []) {
            const id = String(r.store_id);
            const name = String(r.store_name || id);
            if (!acc[id] || acc[id] === id) acc[id] = name; // 有名字的覆盖纯id占位，绝不反向退化
          }
          return acc;
        });
        setOwnerOptAcc((prev) => {
          const s = new Set(prev);
          for (const r of d.rows ?? []) if (r.owner) s.add(String(r.owner));
          return Array.from(s);
        });
        if (m === "custom") { setFrom(d.date_start ?? ""); setTo(d.date_end ?? ""); }
      })
      .catch((e) => setErr(String(e)))
      .finally(() => setLoading(false));
  };
  useEffect(() => { load(mode, from, to); }, [kind]); // eslint-disable-line react-hooks/exhaustive-deps

  const switchMode = (m: Mode): void => {
    if (m === mode) return;
    setMode(m); setPage(1); setHl(null);
    // 2026-08-19 修复：账期筛选残留会泄漏到自定义视图（自定义行无 report_start/report_end，
    // 拼出 "undefined~undefined" 永不匹配 → 全部行被滤成 0），切视图时必须清空账期筛选
    setPeriod([]);
    setApplied((a) => ({ ...a, periods: [] }));
    setSortKey(m === "custom" && kind === "storage" ? "storage_fee" : "report_start"); setSortDir(-1);
    load(m, "", "");
  };

  // 自定义日期：快捷项锚点=数据最新可用日
  const anchorDate = (): string => (kind === "storage" ? data?.daily_max : data?.period_max) || fmtDateYmd(new Date());
  const handleQuick = (days: number): void => {
    const anchor = anchorDate();
    let s = anchor;
    if (days === -1) s = `${anchor.slice(0, 8)}01`;
    else if (days > 1) s = fmtDateYmd(new Date(Date.parse(`${anchor}T00:00:00`) - (days - 1) * 86400000));
    setActiveQuick(days); setFrom(s); setTo(anchor);
    load("custom", s, anchor);
  };

  const doSearch = (): void => { setApplied({ kw: kw.trim(), stores: store, owners: owner, periods: period }); setPage(1); };
  const doReset = (): void => {
    setKw(""); setStore([]); setOwner([]); setPeriod([]);
    setApplied({ kw: "", stores: [], owners: [], periods: [] });
    setPage(1);
    load(mode, mode === "custom" ? from : "", mode === "custom" ? to : "");
  };

  const stores = useMemo(() =>
    Object.entries(storeOptAcc).sort((a, b) => a[1].localeCompare(b[1])),
  [storeOptAcc]);
  const owners = useMemo(() => [...ownerOptAcc].sort((a, b) => a.localeCompare(b)), [ownerOptAcc]);
  const periods = useMemo(() => {
    const s = new Set<string>();
    for (const r of data?.rows ?? []) {
      if (kind === "inbound") { if (r.settlement_month) s.add(String(r.settlement_month)); }
      else if (mode === "bill" && r.report_start) s.add(`${r.report_start}~${r.report_end}`);
    }
    return Array.from(s).sort((a, b) => b.localeCompare(a));
  }, [data, kind, mode]);

  const filtered = useMemo(() => {
    const a = applied;
    return (data?.rows ?? []).filter((r) => {
      if (a.kw) {
        const k = a.kw.toLowerCase();
        const hay = [r.msku, r.sku, r.item_id, r.gtin, r.store_name, r.cargo_code, r.shipment_id, r.owner]
          .map((v) => String(v ?? "").toLowerCase());
        if (!hay.some((h) => h.includes(k))) return false;
      }
      if (a.stores.length > 0 && !a.stores.includes(String(r.store_id))) return false;
      if (a.owners.length > 0 && !a.owners.includes(String(r.owner ?? ""))) return false;
      // 视图守卫（2026-08-19）：账期筛选仅在有账期字段的视图生效（入库/仓储账单），自定义视图行无账期字段不参与过滤
      if (a.periods.length > 0 && (kind === "inbound" || mode === "bill")) {
        const pv = kind === "inbound" ? String(r.settlement_month ?? "") : `${r.report_start}~${r.report_end}`;
        if (!a.periods.includes(pv)) return false;
      }
      return true;
    });
  }, [data, applied, kind, mode]);

  const sorted = useMemo(() => {
    const rows = [...filtered];
    rows.sort((a, b) => {
      const av = a[sortKey], bv = b[sortKey];
      if (typeof av === "number" || typeof bv === "number" || av === null || bv === null) {
        return ((Number(av ?? -Infinity)) - (Number(bv ?? -Infinity))) * sortDir;
      }
      return String(av ?? "").localeCompare(String(bv ?? "")) * sortDir;
    });
    return rows;
  }, [filtered, sortKey, sortDir]);

  const totalPages = Math.max(1, Math.ceil(sorted.length / pageSize));
  const curPage = Math.min(page, totalPages);
  const pageRows = sorted.slice((curPage - 1) * pageSize, curPage * pageSize);
  const pageWin = useMemo(() => {
    const win: number[] = [];
    let s = Math.max(1, curPage - 2);
    const e = Math.min(totalPages, s + 4);
    s = Math.max(1, e - 4);
    for (let i = s; i <= e; i++) win.push(i);
    return win;
  }, [curPage, totalPages]);

  // 合计（当前筛选全量）：货件运费按货件去重求和，件均量/覆盖天数不合计
  const totals = useMemo(() => {
    const t: Record<string, number> = {};
    const cargoSeen = new Set<string>();
    let cargoFreight = 0;
    for (const r of sorted) {
      for (const c of COLS) {
        if (!c.num || c.noTotal) continue;
        t[c.key] = (t[c.key] ?? 0) + Number(r[c.key] ?? 0);
      }
      if (kind === "inbound") {
        const ck = `${r.store_id}|${r.cargo_code}|${r.report_start}`;
        if (!cargoSeen.has(ck)) { cargoSeen.add(ck); cargoFreight += Number(r.freight_total ?? 0); }
      }
    }
    t.__cargo_freight = cargoFreight;
    t.__cargo_cnt = cargoSeen.size;
    return t;
  }, [sorted, COLS, kind]);

  // KPI（当前筛选全量）
  const kpis = useMemo(() => {
    if (kind === "storage" && mode === "bill") {
      const ps = new Set(sorted.map((r) => `${r.store_id}|${r.report_start}~${r.report_end}`));
      return [
        { label: "SKU行数", val: String(sorted.length) },
        { label: "店铺×账期数", val: String(ps.size) },
        { label: "原始金额", val: `$${fm(totals.original_amount ?? 0)}` },
        { label: "折扣减免", val: `$${fm(totals.discount_savings ?? 0)}`, color: C.green },
        { label: "最终仓储费", val: `$${fm(totals.final_storage_fee ?? 0)}`, color: C.neg },
      ];
    }
    if (kind === "storage") {
      return [
        { label: "SKU行数", val: String(sorted.length) },
        { label: "日期区间", val: from && to ? `${from} ~ ${to}` : "-" },
        { label: "仓储费合计", val: `$${fm(totals.storage_fee ?? 0)}`, color: C.neg },
      ];
    }
    const unalloc = sorted.filter((r) => r.alloc_basis === "none").reduce((s, r) => s + Number(r.alloc_amount ?? 0), 0);
    return [
      { label: "货件数", val: String(totals.__cargo_cnt ?? 0) },
      { label: "分摊行数", val: String(sorted.length) },
      { label: "货件运费(去重)", val: `$${fm(totals.__cargo_freight ?? 0)}` },
      { label: "分摊金额合计", val: `$${fm(totals.alloc_amount ?? 0)}`, color: C.neg },
      { label: "未分摊金额", val: `$${fm(unalloc)}`, color: unalloc > 0 ? C.neg : undefined },
    ];
  }, [kind, mode, sorted, totals, from, to]);

  // §11.5 固定列归组在前 + 列宽累加left偏移，逐格内联sticky
  const visCols = useMemo(() => {
    const pin = selectedCols.filter((k) => pinnedCols.includes(k));
    const rest = selectedCols.filter((k) => !pinnedCols.includes(k));
    return [...pin, ...rest].map(colByKey).filter(Boolean);
  }, [selectedCols, pinnedCols, COLS]); // eslint-disable-line react-hooks/exhaustive-deps
  const pinLeft = useMemo(() => {
    const m: Record<string, number> = {};
    let acc = 0;
    for (const c of visCols) {
      if (!pinnedCols.includes(c.key)) break;
      m[c.key] = acc;
      acc += colW[c.key] ?? c.w;
    }
    return m;
  }, [visCols, pinnedCols, colW]);
  const pinStyle = (key: string, kindStyle: "head" | "body" | "foot"): React.CSSProperties =>
    pinLeft[key] !== undefined
      ? { position: "sticky", left: pinLeft[key], zIndex: kindStyle === "head" ? 7 : kindStyle === "foot" ? 6 : 2, boxShadow: "2px 0 4px -2px rgba(0,0,0,0.12)" }
      : {};

  const openColumnConfig = (): void => { setCfgSelected(selectedCols); setCfgPins(pinnedCols); setShowColumnConfig(true); };
  const applyColumnConfig = (): void => {
    setSelectedCols(cfgSelected.length ? cfgSelected : ALL_KEYS);
    setPinnedCols(cfgPins);
    setShowColumnConfig(false);
  };

  const startResize = (e: React.MouseEvent, key: string, th: HTMLElement): void => {
    e.preventDefault();
    const startX = e.clientX, startW = th.offsetWidth;
    const move = (ev: MouseEvent): void => setColW((w) => ({ ...w, [key]: Math.max(48, startW + ev.clientX - startX) }));
    const up = (): void => { document.removeEventListener("mousemove", move); document.removeEventListener("mouseup", up); };
    document.addEventListener("mousemove", move); document.addEventListener("mouseup", up);
  };

  const exportCsv = (): void => {
    const cols = visCols;
    const head = cols.map((c) => c.label).join(",");
    const lines = sorted.map((r) => cols.map((c) => {
      let v: unknown = r[c.key];
      if (c.key === "alloc_basis") v = BASIS_LABEL[String(v)] ?? v;
      if (typeof v === "string") return `"${v.replace(/"/g, '""')}"`;
      return String(v ?? "");
    }).join(","));
    const blob = new Blob(["﻿" + [head, ...lines].join("\n")], { type: "text/csv;charset=utf-8" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    const suffix = mode === "bill" ? "账单" : `${from}_${to}`;
    a.download = `${title}_${suffix}.csv`;
    a.click();
  };

  const syncText = data?.latest_sync_time
    ? new Date(data.latest_sync_time.replace(" ", "T")).toLocaleString("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" })
    : "加载中";
  const kpiTile = (label: string, val: string, color?: string): JSX.Element => (
    <div key={label} style={{ ...card, padding: "12px 16px", minWidth: 140 }}>
      <div style={{ fontSize: 12, color: C.txt2 }}>{label}</div>
      <div style={{ fontSize: 20, fontWeight: 700, color: color ?? "#111827", marginTop: 4 }}>{val}</div>
    </div>
  );
  const modeBtn = (m: Mode, label: string): JSX.Element => (
    <button onClick={() => switchMode(m)}
      style={{ padding: "5px 14px", fontSize: 13, cursor: "pointer", border: "1px solid #e5e7eb", background: mode === m ? "#6366f1" : "#fff", color: mode === m ? "#fff" : "#374151", fontWeight: mode === m ? 700 : 400, borderRadius: m === "bill" ? "6px 0 0 6px" : "0 6px 6px 0" }}>{label}</button>
  );

  return (
    <div style={{ padding: 16 }}>
      {/* §1 工具条 + 元信息 */}
      <div style={{ ...lxTB.filterWrap, display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap", position: "relative" }}>
        <span style={{ fontWeight: 700, fontSize: 15, color: "#111827" }}>{title}</span>
        <span style={{ display: "inline-flex" }}>{modeBtn("bill", "账单")}{modeBtn("custom", "自定义日期")}</span>
        <span style={{ fontSize: 12, color: C.txt2 }}>共 {sorted.length} 行 · 同步 {syncText} · 第 {curPage}/{totalPages} 页</span>
        <span style={{ flex: 1 }} />
        <input placeholder="MSKU/SKU/商品ID/GTIN/货件号…" value={kw} onChange={(e) => setKw(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter") doSearch(); }} style={{ ...lxTB.filterInput, width: 190 }} />
        <LxMultiSelect placeholder="全部店铺" minWidth={140}
          options={stores.map(([id, name]) => ({ value: id, label: name }))}
          selected={store} onChange={setStore} />
        <LxMultiSelect placeholder="全部负责人" minWidth={110}
          options={owners.map((o) => ({ value: o, label: o }))}
          selected={owner} onChange={setOwner} />
        {(kind === "inbound" || mode === "bill") && (
          <LxMultiSelect placeholder={kind === "inbound" ? "全部结算月" : "全部账期"} minWidth={120} menuMinWidth={300}
            options={periods.map((p) => ({ value: p, label: p }))}
            selected={period} onChange={setPeriod} />
        )}
        {mode === "custom" && (
          <DateRangePicker start={from} end={to} quickOptions={DATE_QUICK_OPTIONS} activeQuick={activeQuick}
            onQuick={handleQuick}
            onRange={(s, e) => { setActiveQuick(null); setFrom(s); setTo(e); load("custom", s, e); }} />
        )}
        <button style={lxTB.searchBtn} onClick={doSearch} disabled={loading}>{loading ? "查询中…" : "搜索"}</button>
        <button style={lxTB.resetBtn} onClick={doReset}>重置</button>
        <button style={lxTB.iconBtn} title="隐藏 / 显示 顶部KPI" onClick={() => setKpiHidden(!kpiHidden)}><span style={{ fontSize: 14, lineHeight: 1 }}>▤</span></button>
        <button style={lxTB.iconBtn} title="列配置" onClick={openColumnConfig}><IconColumns /></button>
        <button style={lxTB.resetBtn} onClick={() => setColW({})}>列宽重置</button>
        <button style={lxTB.iconBtn} title="刷新" onClick={() => load(mode, from, to)}><IconRefresh /></button>
        <button style={lxTB.iconBtn} title="帮助" onClick={() => { window.location.hash = `#/help?page=${helpKey}`; onNavigate?.("help"); }}><IconHelp /></button>
        <button style={lxTB.iconBtn} title="导出CSV（当前筛选全部行）" onClick={exportCsv}><IconDownload /></button>
      </div>

      {err && <div style={{ color: C.neg, padding: 8 }}>{err}</div>}

      {/* §6 KPI */}
      {!kpiHidden && (
        <div style={{ display: "flex", gap: 12, margin: "12px 0", flexWrap: "wrap" }}>
          {kpis.map((k) => kpiTile(k.label, k.val, (k as { color?: string }).color))}
        </div>
      )}

      {/* §5.3 提示文案 */}
      <div style={{ fontSize: 12, color: "#9aa0a6", margin: "0 0 6px 2px" }}>
        拖列头右缘调列宽 · 点表头排序（▼▲） · 点单元格高亮行列 · {kind === "storage" ? (mode === "bill" ? "账单视图=沃尔玛仓储报告账期原行" : "自定义日期=账期费用按天均摊后区间求和") : "入库运输为货件一次性费用，自定义日期=账期与区间有交集的行，金额不按天拆分"}
      </div>

      {/* §8 表格 */}
      <div style={{ ...card, overflow: "auto", maxHeight: "calc(100vh - 290px)" }}>
        <table style={{ borderCollapse: "separate", borderSpacing: 0, width: "100%", fontSize: 13 }}>
          <colgroup>
            {visCols.map((col) => <col key={col.key} style={hl?.col === col.key ? { background: HL_BG } : undefined} />)}
          </colgroup>
          <thead>
            <tr>
              {visCols.map((col) => (
                <th key={col.key}
                  style={{ position: "sticky", top: 0, zIndex: 5, textAlign: col.align, padding: "8px 10px", fontSize: 12, color: C.txt2, background: "#f9fafb", whiteSpace: "nowrap", userSelect: "none", boxShadow: "inset 0 -1px 0 #e5e7eb", width: colW[col.key] ?? col.w, minWidth: 48, cursor: "pointer", ...pinStyle(col.key, "head") }}
                  onClick={() => { if (sortKey === col.key) setSortDir(sortDir === 1 ? -1 : 1); else { setSortKey(col.key); setSortDir(-1); } }}>
                  <span style={{ position: "relative", display: "inline-flex", alignItems: "center", gap: 3 }}>
                    {col.label}
                    {sortKey === col.key && <span style={{ fontSize: 10 }}>{sortDir === -1 ? "▼" : "▲"}</span>}
                    {col.tip && (
                      <span onMouseEnter={() => setTipKey(col.key)} onMouseLeave={() => setTipKey("")} onClick={(e) => e.stopPropagation()}
                        style={{ color: "#9aa0a6", cursor: "help", fontSize: 11 }}>ⓘ
                        {tipKey === col.key && (
                          <span style={{ position: "absolute", top: 20, right: 0, zIndex: 20, background: "#202124", color: "#fff", padding: "8px 10px", borderRadius: 6, fontSize: 12, width: 250, whiteSpace: "normal", textAlign: "left", lineHeight: 1.5, fontWeight: 400 }}>{col.tip}</span>
                        )}
                      </span>
                    )}
                  </span>
                  <span className="lx-colresize" onMouseDown={(e) => startResize(e, col.key, e.currentTarget.parentElement as HTMLElement)} onClick={(e) => e.stopPropagation()} />
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {pageRows.map((r, i) => {
              const rowKey = `${r.store_id}|${r.msku ?? ""}|${r.cargo_code ?? ""}|${r.report_start ?? ""}|${r.report_end ?? ""}`;
              const rowHl = hl?.row === rowKey;
              const rowBg = hl ? (rowHl ? HL_BG : "transparent") : i % 2 ? "#fafafa" : "#fff";
              return (
                <tr key={rowKey} style={{ background: rowBg }}>
                  {visCols.map((col) => {
                    const v = r[col.key];
                    let cell: React.ReactNode;
                    if (col.key === "item_id") cell = v ? <ItemIdLink itemId={String(v)} /> : "—";
                    else if (col.key === "alloc_basis") cell = BASIS_LABEL[String(v)] ?? String(v ?? "—");
                    else if (col.dec) cell = v == null ? "-" : (v as number).toLocaleString("en-US", { minimumFractionDigits: col.dec, maximumFractionDigits: col.dec });
                    else if (col.num) cell = fm(v as number | null, col.int);
                    else cell = String(v ?? "") || "—";
                    const neg = col.num && typeof v === "number" && v < 0;
                    const pinnedCell = pinLeft[col.key] !== undefined;
                    const cellBg = rowHl || hl?.col === col.key ? HL_BG : pinnedCell ? (hl ? "#fff" : i % 2 ? "#fafafa" : "#fff") : undefined;
                    return (
                      <td key={col.key}
                        onClick={(e) => {
                          if ((e.target as HTMLElement).closest("a,button,input,select")) return;
                          setHl(rowHl && hl?.col === col.key ? null : { row: rowKey, col: col.key });
                        }}
                        style={{ padding: "7px 10px", textAlign: col.align, whiteSpace: "nowrap", borderBottom: "1px solid #f3f4f6", cursor: "pointer", background: cellBg, color: neg ? C.neg : undefined, ...pinStyle(col.key, "body") }}>{cell}</td>
                    );
                  })}
                </tr>
              );
            })}
            {pageRows.length === 0 && <tr><td colSpan={visCols.length} style={{ padding: 24, textAlign: "center", color: C.txt2 }}>{loading ? "加载中…" : "无数据"}</td></tr>}
          </tbody>
          <tfoot>
            <tr>
              {visCols.map((col) => {
                let v = "";
                if (col.key === "store_name") v = `总计（${sorted.length}行）`;
                else if (col.key === "freight_total" && kind === "inbound") v = fm(totals.__cargo_freight ?? 0);
                else if (col.num && !col.noTotal && col.key in totals) v = fm(totals[col.key], col.int);
                return <td key={col.key} style={{ position: "sticky", bottom: 0, background: "#eef2ff", fontWeight: 700, color: "#3730a3", borderTop: "2px solid #c7d2fe", textAlign: col.align, padding: "8px 10px", fontSize: 12, whiteSpace: "nowrap", zIndex: pinLeft[col.key] !== undefined ? 6 : 4, ...(pinLeft[col.key] !== undefined ? { left: pinLeft[col.key] } : {}) }}>{v}</td>;
              })}
            </tr>
          </tfoot>
        </table>
      </div>

      {/* §8 翻页 */}
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginTop: 10, fontSize: 13 }}>
        <select value={pageSize} onChange={(e) => { setPageSize(Number(e.target.value)); setPage(1); }} style={{ ...lxTB.filterSelect, width: 100 }}>
          {PAGE_SIZES.map((n) => <option key={n} value={n}>{n} 条/页</option>)}
        </select>
        <button style={pageBtn(false, curPage <= 1)} disabled={curPage <= 1} onClick={() => setPage(1)}>首页</button>
        <button style={pageBtn(false, curPage <= 1)} disabled={curPage <= 1} onClick={() => setPage(curPage - 1)}>上一页</button>
        {pageWin.map((p) => <button key={p} style={pageBtn(p === curPage, false)} onClick={() => setPage(p)}>{p}</button>)}
        <button style={pageBtn(false, curPage >= totalPages)} disabled={curPage >= totalPages} onClick={() => setPage(curPage + 1)}>下一页</button>
        <button style={pageBtn(false, curPage >= totalPages)} disabled={curPage >= totalPages} onClick={() => setPage(totalPages)}>末页</button>
        <span style={{ color: C.txt2 }}>共 {sorted.length} 条 · 跳至</span>
        <input value={jump} onChange={(e) => setJump(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter") { const n = Number(jump); if (n >= 1 && n <= totalPages) setPage(n); setJump(""); } }} style={{ ...lxTB.filterInput, width: 52 }} />
        <span style={{ color: C.txt2 }}>页</span>
      </div>

      {/* §11 列配置弹窗（照样板 FeishuRawSalesData:2272，逐要素一致） */}
      {showColumnConfig && (
        <div style={{ position: "fixed", inset: 0, background: "rgba(15,23,42,0.4)", zIndex: 1000, display: "flex", alignItems: "center", justifyContent: "center" }}
          onClick={() => setShowColumnConfig(false)}>
          <div style={{ background: "#fff", borderRadius: "12px", width: "680px", maxHeight: "78vh", display: "flex", flexDirection: "column", overflow: "hidden", boxShadow: "0 8px 32px rgba(0,0,0,0.18)" }}
            onClick={(e) => e.stopPropagation()}>
            <div style={{ padding: "12px 16px", borderBottom: "1px solid #e5e7eb", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <span style={{ fontSize: "14px", fontWeight: 700, color: "#374151" }}>列配置</span>
              <button onClick={() => setShowColumnConfig(false)} style={{ border: "none", background: "none", fontSize: "18px", cursor: "pointer", color: "#9ca3af" }}>×</button>
            </div>
            <div style={{ display: "flex", flex: 1, overflow: "hidden" }}>
              <div style={{ flex: 1, padding: "10px 14px", overflowY: "auto" }}>
                {ALL_KEYS.map((k) => (
                  <label key={k} style={{ display: "flex", alignItems: "center", gap: "6px", padding: "4px 0", cursor: "pointer", fontSize: "13px" }}>
                    <input type="checkbox" checked={cfgSelected.includes(k)}
                      onChange={() => {
                        setCfgSelected((prev) => prev.includes(k) ? prev.filter((c) => c !== k) : [...prev, k]);
                        setCfgPins((prev) => prev.filter((c) => c !== k));
                      }} />
                    <span style={{ color: "#374151" }}>{colByKey(k).label}</span>
                  </label>
                ))}
              </div>
              <div style={{ width: "230px", borderLeft: "1px solid #e5e7eb", padding: "10px 10px", overflowY: "auto", background: "#f8fafc" }}>
                <div style={{ fontSize: "12px", color: "#64748b", marginBottom: "2px" }}>已选 {cfgSelected.length} 列 · 拖动调顺序</div>
                <div style={{ fontSize: "11px", color: "#94a3b8", marginBottom: "6px" }}>📌最多固定{MAX_PINNED_COLUMNS}项（表格左侧冻结）</div>
                {cfgSelected.map((k, idx) => {
                  const isPin = cfgPins.includes(k);
                  return (
                    <div key={k} draggable
                      onDragStart={() => { dragColIdxRef.current = idx; }}
                      onDragOver={(e) => e.preventDefault()}
                      onDrop={() => {
                        const fromIdx = dragColIdxRef.current;
                        dragColIdxRef.current = null;
                        if (fromIdx === null || fromIdx === idx) return;
                        const view = [...cfgSelected];
                        const [moved] = view.splice(fromIdx, 1);
                        view.splice(idx, 0, moved);
                        setCfgSelected(view);
                      }}
                      style={{ display: "flex", alignItems: "center", gap: "4px", padding: "4px 2px", fontSize: "12px", borderRadius: "4px", cursor: "grab", background: isPin ? "#eef2ff" : "transparent", borderBottom: "1px solid #f1f5f9" }}>
                      <span style={{ color: "#cbd5e1", fontSize: "13px", lineHeight: 1 }} title="拖动排序">⠿</span>
                      <span style={{ flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                        {isPin && <span style={{ fontSize: "10px" }}>📌</span>}{colByKey(k).label}
                      </span>
                      <span onClick={() => setCfgSelected((prev) => [k, ...prev.filter((c) => c !== k)])} title="置顶"
                        style={{ color: "#64748b", cursor: "pointer", fontSize: "12px" }}>⬆</span>
                      <span onClick={() => setCfgPins((prev) => {
                          if (prev.includes(k)) return prev.filter((c) => c !== k);
                          if (prev.length + 1 > MAX_PINNED_COLUMNS) { alert(`最多可固定${MAX_PINNED_COLUMNS}项`); return prev; }
                          return [...prev, k];
                        })} title={isPin ? "取消固定" : "固定（左侧冻结）"}
                        style={{ color: isPin ? "#2563eb" : "#94a3b8", cursor: "pointer", fontSize: "12px" }}>📌</span>
                      <span onClick={() => {
                          setCfgSelected((prev) => prev.filter((c) => c !== k));
                          setCfgPins((prev) => prev.filter((c) => c !== k));
                        }} title="删除"
                        style={{ color: "#ef4444", cursor: "pointer", fontSize: "14px" }}>×</span>
                    </div>
                  );
                })}
              </div>
            </div>
            <div style={{ padding: "10px 16px", borderTop: "1px solid #e5e7eb", display: "flex", gap: "8px", justifyContent: "flex-end" }}>
              <button style={lxTB.resetBtn} onClick={() => { setCfgSelected(ALL_KEYS); setCfgPins(DEFAULT_PINNED); }}>重置默认</button>
              <button style={lxTB.resetBtn} onClick={() => setShowColumnConfig(false)}>取消</button>
              <button style={lxTB.searchBtn} onClick={applyColumnConfig}>应用</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
