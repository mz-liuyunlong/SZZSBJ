/**
 * OrderProfitV2.tsx — 订单利润 V2（2026-08-18 整改批B-2：按规范原文重做，禁自造）
 * 接口：GET /api/profit-v2/order-profit
 * UI_STANDARDS 对照（逐条读原文实现）：
 *   §1工具条 §5列宽拖动+重置+提示文案 §6KPI可隐藏 §7表头ⓘ §8吸顶/吸底/翻页 §9 hash=#/profit/order-v2
 *   §11列配置=领星式680px弹窗(左勾选/右已选拖动排序⠿⬆📌×/重置默认取消应用/草稿态)——样板FeishuRawSalesData:2272
 *   §12数值0与空值可区分(null才显示占位符,禁falsy写法) §13行列高亮=点格淡色十字#eef2ff,交互控件不触发
 *   日期筛选=领星式范围选择器（共享件 LxDateRange，快捷项+双月历），禁原生date输入
 * 全零行彻底隐藏（需求方定稿：任一数值非0才显示，无开关）；CS测品整行剔除。
 */
import { useMemo, useRef, useState, useEffect } from "react";
import { lxTB, IconRefresh, IconHelp, IconDownload, IconColumns } from "./LxToolbar";
import { ItemIdLink } from "./ItemIdLink";
import { DateRangePicker, DATE_QUICK_OPTIONS, fmtDateYmd } from "./LxDateRange";
import LxMultiSelect from "./LxMultiSelect";

interface Row {
  ad_ratio?: number | null;
  store_id: string; store_name: string; owner: string; item_id: string; msku: string; sku: string;
  sales: number; qty: number;
  excluded_sales: number; excluded_orders: number; excluded_qty: number;
  pc_unit: number; fl_unit: number; storage_unit: number; wfs_unit: number;
  refund_qty: number; refund_amount: number; refund_rate_30d: number | null;
  refund_qty_30d: number; qty_30d: number;
  ad: number; wfs: number; commission: number; purchase_cost: number; first_leg: number;
  storage: number; wfs_stock: number; gross_profit_old: number; order_profit: number;
  profit_rate: number | null; roi: number | null; cost_status: string;
}
interface Bucket { store_id: string; store_name: string; ad: number; items: number }
interface Resp {
  from: string; to: string; latest_biz_date: string; win30_start: string; inv_snapshot_date: string;
  kpi: { sales: number; excluded_sales: number; excluded_orders: number; order_profit: number; refund_amount: number;
    refund_rate_30d: number | null; refund_qty_30d_total: number; qty_30d_total: number;
    ad_total: number; ad_unattributed: number; cs_ad_dropped: number; row_cnt: number };
  rows: Row[]; store_ad_buckets: Bucket[]; caliber_note: string; error?: string;
}

const C = { blue: "#1a73e8", txt2: "#5f6368", neg: "#d93025", green: "#188038" };
const card: React.CSSProperties = { background: "#fff", border: "1px solid #e5e7eb", borderRadius: "10px" };
const PAGE_SIZES = [50, 100, 200];
const MAX_PINNED_COLUMNS = 7;                  // 领星同款上限（§11.4）
const DEFAULT_PINNED = ["store_name", "msku"]; // 默认固定列（§11.7 每页自定）
const HL_BG = "#eef2ff";                       // §13 十字高亮色
const pageBtn = (active: boolean, disabled: boolean): React.CSSProperties => ({ padding: "5px 12px", borderRadius: "5px", border: "1px solid #e5e7eb", cursor: disabled ? "not-allowed" : "pointer", background: active ? "#6366f1" : "#fff", color: active ? "#fff" : "#374151", fontWeight: active ? 700 : 400, fontSize: "13px", opacity: disabled ? 0.5 : 1 });

interface Col { key: string; label: string; w: number; align: "left" | "right"; tip?: string; num?: boolean; int?: boolean; pct?: boolean; cur?: boolean; unit6?: boolean; unit2?: boolean }
const COLS: Col[] = [
  { key: "store_name", label: "店铺", w: 150, align: "left", tip: "销售/费用=fact各表原生店铺；退货=售后接口原生店铺（店铺id精度已修复归一）" },
  { key: "owner", label: "负责人", w: 76, align: "left", tip: "dim_product(店铺+MSKU)；未命中时该MSKU全库唯一归属兜底；仍空=历史下架品" },
  { key: "item_id", label: "商品ID", w: 116, align: "left", tip: "该(店铺,MSKU)最新关联ItemID，经dim_product映射，同上兜底" },
  { key: "msku", label: "MSKU", w: 128, align: "left", tip: "本页行键=店铺+MSKU；CS测品整行剔除（行/合计/KPI均不含）" },
  { key: "sku", label: "SKU", w: 96, align: "left", tip: "本地SKU（dim_product.sku），与Beta同源；历史品可能为空" },
  { key: "sales", label: "销售额", w: 88, align: "right", num: true, cur: true, tip: "**不含送样单**。送样单=全额折扣单（折扣额=商品金额，即0元成交），其销售额和销量都不计入本列，被剔除的金额在右侧「剔除送样额」列。因此本列比领星/每日销售明细少一个送样额。注：仅能识别近31天的送样单（折扣数据窗口所限），更早的仍含在内" },
  { key: "excluded_sales", label: "剔除送样额", w: 92, align: "right", num: true, cur: true, tip: "本行被剔除的送样单金额合计（原价口径），仅作透明展示，不参与任何计算" },
  { key: "qty", label: "销量", w: 56, align: "right", num: true, int: true, tip: "saleStat族销量(extra_json.sales_qty)，整数展示" },
  { key: "refund_qty", label: "退货量", w: 62, align: "right", num: true, int: true, tip: "售后接口REFUND件数，售后申请日(美西站点时间)归因" },
  { key: "refund_amount", label: "退款额", w: 76, align: "right", num: true, cur: true, tip: "纯退款净额(含税)；产品/头程成本不计回；当天只退货=当天负利润" },
  { key: "refund_rate_30d", label: "退货率30天", w: 86, align: "right", num: true, pct: true, tip: "以结束日为锚近30天：退货件÷销量；合计行=Σ退货件÷Σ销量(综合退货率)" },
  { key: "ad", label: "广告费", w: 78, align: "right", num: true, cur: true, tip: "权威表全类型=SP(手动+自动)+SB+SV+SEM；item级按MSKU销售额份额分摊；SEM未归属在店铺桶(表下)；CS广告已剔除" },
  { key: "ad_ratio", label: "广告占比", w: 76, align: "right", num: true, pct: true, tip: "广告费÷销售额（本页新口径广告费含SEM/SB/SV）；销售额为0记 -；合计行=Σ广告费÷Σ销售额" },
  { key: "wfs", label: "WFS配送费", w: 86, align: "right", num: true, cur: true, tip: "单件实收配送费×销量（与Beta生成器同源）" },
  { key: "wfs_unit", label: "WFS配送单价$", w: 100, align: "right", num: true, unit2: true, tip: "单件实收WFS配送费（$，2位小数），取窗口内最新业务日快照；本列固定美元，不随币种切换换算" },
  { key: "commission", label: "佣金", w: 70, align: "right", num: true, cur: true, tip: "销售额×佣金率（CN2501/CN2502=15%，其余12%）" },
  { key: "purchase_cost", label: "采购成本", w: 80, align: "right", num: true, cur: true, tip: "当日快照单件采购价CNY×销量÷汇率6.6。注意：成本按**当日历史快照价**计，非成本配置表当前价，故与产品管理页现价可能不同（历史报表用当时成本才对得上当时利润）" },
  { key: "pc_unit", label: "采购单价¥", w: 88, align: "right", num: true, unit2: true, tip: "当日快照单件采购价（人民币，2位小数）；与产品管理页现价可能不同，见采购成本列说明。本列固定人民币，不随币种切换换算" },
  { key: "first_leg", label: "头程成本", w: 80, align: "right", num: true, cur: true, tip: "当日快照单件头程价CNY×销量÷汇率6.6（同为历史快照口径）" },
  { key: "fl_unit", label: "头程单价¥", w: 88, align: "right", num: true, unit2: true, tip: "当日快照单件头程价（人民币，2位小数）。本列固定人民币，不随币种切换换算" },
  { key: "storage", label: "仓储费", w: 70, align: "right", num: true, cur: true, tip: "账期总额÷天数日摊（账单驱动）；未出账期显示0（待出账）" },
  { key: "storage_unit", label: "仓储单价$", w: 96, align: "right", num: true, unit6: true, tip: "标准单价日费（$/件/天，6位小数），取该店该SKU最新账期的 unit_fee_standard，与「仓储费」页同源同值；显示「—」= 该店该SKU尚无仓储账单记录（未入仓/未出账），非费率为0；本列固定美元，不随币种切换换算" },
  { key: "wfs_stock", label: "WFS可售库存", w: 96, align: "right", num: true, int: true, tip: "fact_inventory_daily最新快照 wfs_available_stock，与「每日销售明细」同字段同源，恒为最新值不随日期筛选变化" },
  { key: "gross_profit_old", label: "毛利润(旧)", w: 84, align: "right", num: true, cur: true, tip: "旧口径毛利（含旧广告取数，不含退货/折扣/仓储），仅供领星对账" },
  { key: "order_profit", label: "订单利润", w: 86, align: "right", num: true, cur: true, tip: "净销售额−广告费−WFS配送费−佣金−采购成本−头程成本−退款额−仓储费；业务端毛利非财务净利" },
  { key: "profit_rate", label: "利润率", w: 66, align: "right", num: true, pct: true, tip: "订单利润÷净销售额" },
  { key: "roi", label: "ROI", w: 60, align: "right", num: true, tip: "投入产出比=订单利润×汇率6.6÷(采购成本+头程成本CNY)；无采购头程成本记 -" },
];
const ALL_KEYS = COLS.map((c) => c.key);
const colByKey = (k: string): Col => COLS.find((c) => c.key === k) as Col;

// §12：数值0必须显示0，仅 null/undefined 显示占位符；禁 falsy 写法
const fm = (v: number | null | undefined, pct = false, int = false): string => {
  if (v == null) return "-";
  if (pct) return `${(v * 100).toFixed(2)}%`;
  if (int) return String(Math.round(v));
  return v.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
};

export default function OrderProfitV2({ onNavigate }: { onNavigate?: (p: string) => void }): JSX.Element {
  const [data, setData] = useState<Resp | null>(null);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState("");
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [store, setStore] = useState<string[]>([]);   // 多选（§16）；接口store_id仅在单选1家时下推，其余前端过滤
  const [activeQuick, setActiveQuick] = useState<number | null>(1);
  const [kwType, setKwType] = useState<"keyword" | "sku" | "msku" | "item_id">("keyword");
  const [kw, setKw] = useState("");
  const [owner, setOwner] = useState<string[]>([]);   // 多选（§16）
  const [moreOpen, setMoreOpen] = useState(false);
  const [stockState, setStockState] = useState("");
  const [costState, setCostState] = useState("");
  const [gmMin, setGmMin] = useState(""); const [gmMax, setGmMax] = useState("");
  const [adMin, setAdMin] = useState(""); const [adMax, setAdMax] = useState("");
  const [applied, setApplied] = useState<{ kwType: string; kw: string; owners: string[]; stores: string[]; stockState: string; costState: string; gmMin: string; gmMax: string; adMin: string; adMax: string }>({ kwType: "keyword", kw: "", owners: [], stores: [], stockState: "", costState: "", gmMin: "", gmMax: "", adMin: "", adMax: "" });
  const [kpiHidden, setKpiHidden] = useState(false);
  const [currency, setCurrency] = useState<"USD" | "RMB">("USD"); // 固定汇率6.6，仅展示层换算
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(50);
  const [jump, setJump] = useState("");
  const [sortKey, setSortKey] = useState<string>("sales");
  const [sortDir, setSortDir] = useState<1 | -1>(-1);
  const [colW, setColW] = useState<Record<string, number>>({});
  const [tipKey, setTipKey] = useState("");
  // §11 列配置：生效态（selected=有序可见列，pins=固定列）+ 弹窗草稿态
  const [selectedCols, setSelectedCols] = useState<string[]>(ALL_KEYS);
  const [pinnedCols, setPinnedCols] = useState<string[]>(DEFAULT_PINNED);
  const [showColumnConfig, setShowColumnConfig] = useState(false);
  const [cfgSelected, setCfgSelected] = useState<string[]>(ALL_KEYS);
  const [cfgPins, setCfgPins] = useState<string[]>(DEFAULT_PINNED);
  const dragColIdxRef = useRef<number | null>(null);
  // §13 行列高亮
  const [hl, setHl] = useState<{ row: string; col: string } | null>(null);

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

  const load = (f?: string, t?: string): void => {
    // 店铺/负责人一律前端过滤（2026-08-18 BUG修复：下推后端会让选项列表被自身过滤掉，单店选后无法再选他店）
    setLoading(true); setErr("");
    const q = new URLSearchParams();
    if (f) q.set("from", f);
    if (t) q.set("to", t);
    fetch(`/api/profit-v2/order-profit?${q.toString()}`, { credentials: "include" })
      .then((r) => r.json())
      .then((d: Resp) => {
        if (d.error) { setErr(d.error); return; }
        for (const r of d.rows) r.ad_ratio = r.sales > 0 ? Math.round((r.ad / r.sales) * 10000) / 10000 : null;
        setData(d); setFrom(d.from); setTo(d.to); setPage(1);
      })
      .catch((e) => setErr(String(e)))
      .finally(() => setLoading(false));
  };
  useEffect(() => { load(); }, []);

  // 日期快捷项：锚点=最新业务日（美西日界）
  const anchorDate = (): string => data?.latest_biz_date || fmtDateYmd(new Date());
  const handleQuick = (days: number): void => {
    const anchor = anchorDate();
    let s = anchor, e = anchor;
    if (days === -1) s = `${anchor.slice(0, 8)}01`; // 本月
    else if (days > 1) s = fmtDateYmd(new Date(Date.parse(`${anchor}T00:00:00`) - (days - 1) * 86400000));
    setActiveQuick(days); setFrom(s); setTo(e);
    load(s, e);
  };

  const doSearch = (): void => {
    setApplied({ kwType, kw: kw.trim(), owners: owner, stores: store, stockState, costState, gmMin, gmMax, adMin, adMax });
    setPage(1); setMoreOpen(false);
    load(from, to);
  };
  const doReset = (): void => {
    setKw(""); setOwner([]); setStore([]); setStockState(""); setCostState("");
    setGmMin(""); setGmMax(""); setAdMin(""); setAdMax(""); setActiveQuick(1);
    setApplied({ kwType: "keyword", kw: "", owners: [], stores: [], stockState: "", costState: "", gmMin: "", gmMax: "", adMin: "", adMax: "" });
    setPage(1);
    load();
  };

  const stores = useMemo(() => {
    const m = new Map<string, string>();
    for (const r of data?.rows ?? []) if (!m.has(r.store_id)) m.set(r.store_id, r.store_name || r.store_id);
    return Array.from(m.entries()).sort((a, b) => a[1].localeCompare(b[1]));
  }, [data]);
  const owners = useMemo(() => {
    const s = new Set<string>();
    for (const r of data?.rows ?? []) if (r.owner) s.add(r.owner);
    return Array.from(s).sort((a, b) => a.localeCompare(b));
  }, [data]);

  const filtered = useMemo(() => {
    const a = applied;
    const num = (v: string): number | null => { const n = parseFloat(v); return Number.isFinite(n) ? n : null; };
    const gmMinN = num(a.gmMin), gmMaxN = num(a.gmMax), adMinN = num(a.adMin), adMaxN = num(a.adMax);
    return (data?.rows ?? []).filter((r) => {
      // 全零行彻底隐藏（需求方定稿：任一数值非0才显示，含WFS可售库存/退货，无开关）
      const anyNonZero = r.sales !== 0 || r.excluded_sales !== 0 || r.qty !== 0 || r.refund_qty !== 0 ||
        r.refund_amount !== 0 || r.ad !== 0 || r.wfs !== 0 || r.commission !== 0 ||
        r.purchase_cost !== 0 || r.first_leg !== 0 || r.storage !== 0 || r.wfs_stock !== 0 ||
        r.gross_profit_old !== 0 || r.order_profit !== 0;
      if (!anyNonZero) return false;
      if (a.kw) {
        const k = a.kw.toLowerCase();
        // 关键词=商品ID/MSKU/店铺名 模糊（Beta后端同款三列，feishuRawSalesRoutes:3195）
        const hit = a.kwType === "keyword"
          ? (r.item_id.toLowerCase().includes(k) || r.msku.toLowerCase().includes(k) || r.store_name.toLowerCase().includes(k))
          : String((r as unknown as Record<string, unknown>)[a.kwType] ?? "").toLowerCase().includes(k);
        if (!hit) return false;
      }
      if (a.owners.length > 0 && !a.owners.includes(r.owner)) return false;
      if (a.stores.length > 0 && !a.stores.includes(r.store_id)) return false;
      if (a.stockState === "has" && !(r.wfs_stock > 0)) return false;
      if (a.stockState === "none" && r.wfs_stock > 0) return false;
      if (a.costState === "full" && r.cost_status !== "完整") return false;
      if (a.costState === "missing" && (r.cost_status === "完整" || r.cost_status === "-")) return false;
      const gm = r.sales > 0 ? r.gross_profit_old / r.sales : null;
      if (gmMinN !== null && (gm === null || gm * 100 < gmMinN)) return false;
      if (gmMaxN !== null && (gm === null || gm * 100 > gmMaxN)) return false;
      const ar = r.sales > 0 ? r.ad / r.sales : null;
      if (adMinN !== null && (ar === null || ar * 100 < adMinN)) return false;
      if (adMaxN !== null && (ar === null || ar * 100 > adMaxN)) return false;
      return true;
    });
  }, [data, applied]);

  const sorted = useMemo(() => {
    const rows = [...filtered];
    rows.sort((a, b) => {
      const av = (a as unknown as Record<string, unknown>)[sortKey], bv = (b as unknown as Record<string, unknown>)[sortKey];
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

  const totals = useMemo(() => {
    const t = { sales: 0, excluded_sales: 0, qty: 0, refund_qty: 0, refund_amount: 0, ad: 0, wfs: 0, commission: 0, purchase_cost: 0, first_leg: 0, storage: 0, wfs_stock: 0, gross_profit_old: 0, order_profit: 0, refund_qty_30d: 0, qty_30d: 0 };
    for (const r of sorted) {
      t.sales += r.sales; t.excluded_sales += r.excluded_sales; t.qty += r.qty;
      t.refund_qty += r.refund_qty; t.refund_amount += r.refund_amount; t.ad += r.ad; t.wfs += r.wfs;
      t.commission += r.commission; t.purchase_cost += r.purchase_cost; t.first_leg += r.first_leg;
      t.storage += r.storage; t.wfs_stock += r.wfs_stock; t.gross_profit_old += r.gross_profit_old;
      t.order_profit += r.order_profit; t.refund_qty_30d += r.refund_qty_30d; t.qty_30d += r.qty_30d;
    }
    return t;
  }, [sorted]);

  // §11.5 固定列归组在前 + 列宽累加left偏移，逐格内联sticky
  const visCols = useMemo(() => {
    const pin = selectedCols.filter((k) => pinnedCols.includes(k));
    const rest = selectedCols.filter((k) => !pinnedCols.includes(k));
    return [...pin, ...rest].map(colByKey).filter(Boolean);
  }, [selectedCols, pinnedCols]);
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
  const pinStyle = (key: string, kind: "head" | "body" | "foot"): React.CSSProperties => {
    if (pinLeft[key] === undefined) return {};
    const w = colW[key] ?? (colByKey(key)?.w ?? 100);
    // 固定列宽度三值锁死：sticky偏移按配置宽累加，实际渲染宽必须与其一致，否则各固定列互相叠压（2026-08-18 BUG修复）
    return { position: "sticky", left: pinLeft[key], zIndex: kind === "head" ? 7 : kind === "foot" ? 6 : 2,
      width: w, minWidth: w, maxWidth: w, overflow: "hidden", textOverflow: "ellipsis",
      boxShadow: "2px 0 4px -2px rgba(0,0,0,0.12)" };
  };

  const openColumnConfig = (): void => { setCfgSelected(selectedCols); setCfgPins(pinnedCols); setShowColumnConfig(true); };
  const applyColumnConfig = (): void => {
    setSelectedCols(cfgOrderedSelected.length ? cfgOrderedSelected : ALL_KEYS);
    setPinnedCols(cfgPins);
    setShowColumnConfig(false);
  };
  // 固定列归组在前（§11.5 样板同法）：右栏显示、拖拽写回、应用生效均按此顺序
  const cfgOrderedSelected = [...cfgSelected.filter((k) => cfgPins.includes(k)), ...cfgSelected.filter((k) => !cfgPins.includes(k))];

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
      const v = (r as unknown as Record<string, unknown>)[c.key];
      if (typeof v === "string") return `"${v.replace(/"/g, '""')}"`;
      if (typeof v === "number" && c.cur) return String(Math.round(cv(v) * 100) / 100);
      return String(v ?? "");
    }).join(","));
    const blob = new Blob(["﻿" + [head, ...lines].join("\n")], { type: "text/csv;charset=utf-8" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `订单利润V2_${from}_${to}.csv`;
    a.click();
  };

  const RATE = 6.6;
  const sym = currency === "RMB" ? "¥" : "$";
  const cv = (v: number): number => currency === "RMB" ? v * RATE : v;
  const fmc = (v: number | null | undefined): string => v == null ? "-" : fm(cv(v));
  // KPI跟随筛选（2026-08-18需求方拍板：与合计行同源=筛选后行求和）；
  // 店铺级未归属广告桶：仅当店铺筛选命中该店、且无关键词/负责人/更多筛选时计入（桶无从按这些维度归属）
  const kpi = useMemo(() => {
    const a = applied;
    const otherFiltersActive = Boolean(a.kw || a.owners.length || a.stockState || a.costState || a.gmMin || a.gmMax || a.adMin || a.adMax);
    let bucketAd = 0;
    if (!otherFiltersActive) {
      for (const b of data?.store_ad_buckets ?? []) {
        if (a.stores.length === 0 || a.stores.includes(b.store_id)) bucketAd += b.ad;
      }
    }
    const t = { sales: 0, excluded: 0, order_profit: 0, refund_amount: 0, ad: 0, q30: 0, r30: 0 };
    for (const r of filtered) {
      t.sales += r.sales; t.excluded += r.excluded_sales;
      t.order_profit += r.order_profit; t.refund_amount += r.refund_amount; t.ad += r.ad;
      t.q30 += r.qty_30d; t.r30 += r.refund_qty_30d;
    }
    return {
      sales: t.sales, excluded_sales: t.excluded,
      order_profit: t.order_profit - bucketAd,
      refund_amount: t.refund_amount,
      refund_rate_30d: t.q30 > 0 ? t.r30 / t.q30 : null,
      ad_total: t.ad + bucketAd,
      bucket_included: bucketAd,
    };
  }, [filtered, applied, data]);
  const kpiTile = (label: string, val: string, color?: string): JSX.Element => (
    <div style={{ ...card, padding: "12px 16px", minWidth: 140 }}>
      <div style={{ fontSize: 12, color: C.txt2 }}>{label}</div>
      <div style={{ fontSize: 20, fontWeight: 700, color: color ?? "#111827", marginTop: 4 }}>{val}</div>
    </div>
  );

  return (
    <div style={{ padding: 16 }}>
      {/* §1 工具条 + Beta同款筛选（日期=领星式范围选择器） */}
      <div style={{ ...lxTB.filterWrap, display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap", position: "relative" }}>
        <span style={{ fontWeight: 700, fontSize: 15, color: "#111827" }}>订单利润 V2</span>
        <span style={{ fontSize: 12, color: C.txt2 }}>
          共 {sorted.length} 行 · 业务日 {data ? `${data.from} ~ ${data.to}` : "-"}（最新 {data?.latest_biz_date ?? "-"}）· 库存快照 {data?.inv_snapshot_date ?? "-"} · 第 {curPage}/{totalPages} 页
        </span>
        <span style={{ flex: 1 }} />
        <select value={kwType} onChange={(e) => setKwType(e.target.value as "keyword" | "sku" | "msku" | "item_id")} style={{ ...lxTB.filterSelect, width: 92 }}>
          <option value="keyword">关键词</option>
          <option value="sku">SKU</option>
          <option value="msku">MSKU</option>
          <option value="item_id">商品ID</option>
        </select>
        <input placeholder="搜索内容…" value={kw} onChange={(e) => setKw(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter") doSearch(); }} style={{ ...lxTB.filterInput, width: 130 }} />
        <LxMultiSelect placeholder="全部店铺" minWidth={150}
          options={stores.map(([id, name]) => ({ value: id, label: name }))}
          selected={store} onChange={setStore} />
        <LxMultiSelect placeholder="全部负责人" minWidth={120}
          options={owners.map((o) => ({ value: o, label: o }))}
          selected={owner} onChange={setOwner} />
        <DateRangePicker start={from} end={to} quickOptions={DATE_QUICK_OPTIONS} activeQuick={activeQuick}
          onQuick={handleQuick}
          onRange={(s, e) => { setActiveQuick(null); setFrom(s); setTo(e); load(s, e); }} />
        <select value={currency} onChange={(e) => setCurrency(e.target.value as "USD" | "RMB")} title="币种（固定汇率6.6，仅换算显示）" style={{ ...lxTB.filterSelect, width: 78 }}>
          <option value="USD">USD</option>
          <option value="RMB">RMB</option>
        </select>
        <button style={{ ...lxTB.resetBtn, color: moreOpen ? C.blue : "#6b7280" }} onClick={() => setMoreOpen(!moreOpen)}>更多筛选 {moreOpen ? "▴" : "▾"}</button>
        <button style={lxTB.searchBtn} onClick={doSearch} disabled={loading}>{loading ? "查询中…" : "搜索"}</button>
        <button style={lxTB.resetBtn} onClick={doReset}>重置</button>
        <button style={lxTB.iconBtn} title="隐藏 / 显示 顶部KPI" onClick={() => setKpiHidden(!kpiHidden)}><span style={{ fontSize: 14, lineHeight: 1 }}>▤</span></button>
        <button style={lxTB.iconBtn} title="列配置" onClick={openColumnConfig}><IconColumns /></button>
        <button style={lxTB.resetBtn} onClick={() => setColW({})}>列宽重置</button>
        <button style={lxTB.iconBtn} title="刷新" onClick={() => load(from, to)}><IconRefresh /></button>
        <button style={lxTB.iconBtn} title="帮助" onClick={() => { window.location.hash = "#/help?page=order-profit-v2"; onNavigate?.("help"); }}><IconHelp /></button>
        <button style={lxTB.iconBtn} title="导出CSV（当前筛选全部行）" onClick={exportCsv}><IconDownload /></button>

        {moreOpen && (
          <div style={{ position: "absolute", top: "100%", right: 0, zIndex: 30, background: "#fff", border: "1px solid #e5e7eb", borderRadius: 10, boxShadow: "0 8px 24px rgba(0,0,0,0.12)", padding: 16, width: 420, marginTop: 6 }}>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
              <label style={{ fontSize: 12, color: C.txt2 }}>库存状态
                <select value={stockState} onChange={(e) => setStockState(e.target.value)} style={{ ...lxTB.filterSelect, width: "100%", marginTop: 4 }}>
                  <option value="">全部库存</option>
                  <option value="has">有库存</option>
                  <option value="none">无库存</option>
                </select>
              </label>
              <label style={{ fontSize: 12, color: C.txt2 }}>成本状态
                <select value={costState} onChange={(e) => setCostState(e.target.value)} style={{ ...lxTB.filterSelect, width: "100%", marginTop: 4 }}>
                  <option value="">全部成本状态</option>
                  <option value="full">完整</option>
                  <option value="missing">有缺失</option>
                </select>
              </label>
              <label style={{ fontSize: 12, color: C.txt2 }}>毛利率最小值 (%)
                <input value={gmMin} onChange={(e) => setGmMin(e.target.value)} placeholder="如 10" style={{ ...lxTB.filterInput, width: "100%", marginTop: 4 }} />
              </label>
              <label style={{ fontSize: 12, color: C.txt2 }}>毛利率最大值 (%)
                <input value={gmMax} onChange={(e) => setGmMax(e.target.value)} placeholder="如 30" style={{ ...lxTB.filterInput, width: "100%", marginTop: 4 }} />
              </label>
              <label style={{ fontSize: 12, color: C.txt2 }}>广告占比最小值 (%)
                <input value={adMin} onChange={(e) => setAdMin(e.target.value)} placeholder="如 5" style={{ ...lxTB.filterInput, width: "100%", marginTop: 4 }} />
              </label>
              <label style={{ fontSize: 12, color: C.txt2 }}>广告占比最大值 (%)
                <input value={adMax} onChange={(e) => setAdMax(e.target.value)} placeholder="如 30" style={{ ...lxTB.filterInput, width: "100%", marginTop: 4 }} />
              </label>
            </div>
            <div style={{ display: "flex", justifyContent: "flex-end", gap: 8, marginTop: 14 }}>
              <button style={lxTB.resetBtn} onClick={() => setMoreOpen(false)}>取消</button>
              <button style={lxTB.searchBtn} onClick={doSearch}>搜索</button>
            </div>
          </div>
        )}
      </div>

      {err && <div style={{ color: C.neg, padding: 8 }}>{err}</div>}

      {/* §6 KPI */}
      {!kpiHidden && data && (
        <div style={{ display: "flex", gap: 12, margin: "12px 0", flexWrap: "wrap" }}>
          {kpiTile("销售额", `${sym}${fmc(kpi.sales)}`)}
          {kpiTile("剔除送样额", `${sym}${fmc(kpi.excluded_sales)}`, C.txt2)}
          {kpiTile("订单利润", `${sym}${fmc(kpi.order_profit)}`, kpi.order_profit >= 0 ? C.green : C.neg)}
          {kpiTile("订单利润率", kpi.sales > 0 ? `${((kpi.order_profit / kpi.sales) * 100).toFixed(2)}%` : "-", kpi.order_profit >= 0 ? C.green : C.neg)}
          {kpiTile("退款额", `${sym}${fmc(kpi.refund_amount)}`, C.neg)}
          {kpiTile("退货率(30天)", kpi.refund_rate_30d == null ? "-" : `${(kpi.refund_rate_30d * 100).toFixed(2)}%`)}
          {kpiTile("广告费(含SEM/SB/SV)", `${sym}${fmc(kpi.ad_total)}`)}
          {kpiTile("广告占比", kpi.sales > 0 ? `${((kpi.ad_total / kpi.sales) * 100).toFixed(2)}%` : "-")}
        </div>
      )}

      {/* §5.3 提示文案 */}
      <div style={{ fontSize: 12, color: "#9aa0a6", margin: "0 0 6px 2px" }}>拖列头右缘调列宽 · 点表头排序（▼▲） · 点单元格高亮行列 · CS测品已剔除 · 全零行不显示</div>

      {/* §8 表格（§13 colgroup 列色） */}
      <div style={{ ...card, overflow: "auto", maxHeight: "calc(100vh - 300px)" }}>
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
              const rowKey = `${r.store_id}|${r.msku}`;
              const rowHl = hl?.row === rowKey;
              // §13：高亮激活时其余行背景 transparent 让列色透出；未激活恢复斑马纹
              const rowBg = hl ? (rowHl ? HL_BG : "transparent") : i % 2 ? "#fafafa" : "#fff";
              return (
                <tr key={rowKey} style={{ background: rowBg }}>
                  {visCols.map((col) => {
                    const v = (r as unknown as Record<string, unknown>)[col.key];
                    let cell: React.ReactNode;
                    if (col.key === "item_id") cell = <ItemIdLink itemId={r.item_id} />;
                    else if (col.pct) cell = fm(v as number | null, true);
                    else if (col.key === "roi") cell = v == null ? "-" : (v as number).toFixed(2);
                    else if (col.unit6) cell = v == null || v === 0 ? "—" : (v as number).toFixed(6);
                    else if (col.unit2) cell = v == null ? "-" : (v as number).toFixed(2);
                    else if (col.num) cell = col.cur ? fmc(v as number) : fm(v as number, false, col.int);
                    else cell = String(v ?? "");
                    const neg = col.num && typeof v === "number" && v < 0;
                    const isProfit = col.key === "order_profit";
                    const pinnedCell = pinLeft[col.key] !== undefined;
                    const cellBg = rowHl || hl?.col === col.key ? HL_BG : pinnedCell ? (hl ? "#fff" : i % 2 ? "#fafafa" : "#fff") : undefined;
                    return (
                      <td key={col.key}
                        onClick={(e) => {
                          // §13：交互控件内点击不触发
                          if ((e.target as HTMLElement).closest("a,button,input,select")) return;
                          setHl(rowHl && hl?.col === col.key ? null : { row: rowKey, col: col.key });
                        }}
                        style={{ padding: "7px 10px", textAlign: col.align, whiteSpace: "nowrap", borderBottom: "1px solid #f3f4f6", cursor: "pointer", background: cellBg, color: neg ? C.neg : isProfit && typeof v === "number" && v > 0 ? C.green : undefined, fontWeight: isProfit ? 700 : undefined, ...pinStyle(col.key, "body") }}>{cell}</td>
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
                if (col.key === "store_name") v = "总计";
                else if (col.key === "refund_rate_30d") v = totals.qty_30d > 0 ? `${((totals.refund_qty_30d / totals.qty_30d) * 100).toFixed(2)}%` : "-";
                else if (col.key === "profit_rate") v = totals.sales > 0 ? `${((totals.order_profit / totals.sales) * 100).toFixed(2)}%` : "-";
                else if (col.key === "roi") { const den = (totals.purchase_cost + totals.first_leg) * 6.6; v = den > 0 ? (totals.order_profit * 6.6 / den).toFixed(2) : "-"; }
                else if (col.unit6 || col.unit2) v = "—";   // 单价列不做合计（口径无意义）
                else if (col.key === "ad_ratio") v = totals.sales > 0 ? `${((totals.ad / totals.sales) * 100).toFixed(2)}%` : "-";
                else if (col.key === "qty" || col.key === "refund_qty" || col.key === "wfs_stock") v = String(Math.round(totals[col.key as "qty"]));
                else if (col.key in totals) v = col.cur ? fmc(totals[col.key as keyof typeof totals]) : fm(totals[col.key as keyof typeof totals]);
                return <td key={col.key} style={{ position: "sticky", bottom: 0, background: "#eef2ff", fontWeight: 700, color: "#3730a3", borderTop: "2px solid #c7d2fe", textAlign: col.align, padding: "8px 10px", fontSize: 12, whiteSpace: "nowrap", zIndex: pinLeft[col.key] !== undefined ? 6 : 4, ...(pinLeft[col.key] !== undefined ? { left: pinLeft[col.key] } : {}) }}>{v}</td>;
              })}
            </tr>
          </tfoot>
        </table>
      </div>

      {(data?.store_ad_buckets.length ?? 0) > 0 && (
        <div style={{ ...card, marginTop: 10, padding: "10px 14px", fontSize: 13 }}>
          <b>店铺级未归属广告（已计入合计，未摊到品）：</b>
          {data!.store_ad_buckets.map((b) => (
            <span key={b.store_id} style={{ marginRight: 16 }}>{b.store_name || b.store_id}: <span style={{ color: C.neg }}>${fm(b.ad)}</span>（{b.items}个活动源）</span>
          ))}
          <span style={{ color: C.txt2 }}>—— 源头修复走SEM命名治理（活动名带ItemID后自动归位）</span>
        </div>
      )}

      {/* §8 翻页 */}
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginTop: 10, fontSize: 13 }}>
        <select value={pageSize} onChange={(e) => { setPageSize(Number(e.target.value)); setPage(1); }} style={{ ...lxTB.filterSelect, width: 100 }}>
          {PAGE_SIZES.map((n) => <option key={n} value={n}>{n} 条/页</option>)}
        </select>
        <button style={pageBtn(false, curPage <= 1)} disabled={curPage <= 1} onClick={() => setPage(curPage - 1)}>上一页</button>
        {pageWin.map((p) => <button key={p} style={pageBtn(p === curPage, false)} onClick={() => setPage(p)}>{p}</button>)}
        <button style={pageBtn(false, curPage >= totalPages)} disabled={curPage >= totalPages} onClick={() => setPage(curPage + 1)}>下一页</button>
        <span style={{ color: C.txt2 }}>跳至</span>
        <input value={jump} onChange={(e) => setJump(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter") { const n = Number(jump); if (n >= 1 && n <= totalPages) setPage(n); setJump(""); } }} style={{ ...lxTB.filterInput, width: 52 }} />
        <span style={{ color: C.txt2 }}>页 · 共 {sorted.length} 行</span>
      </div>
      {data && (
        <div style={{ marginTop: 8, fontSize: 12, color: C.txt2, lineHeight: 1.7 }}>
          <b>销售额不含送样单</b>（送样单=0元成交的全额折扣单，其金额见「剔除送样额」列）；CS测品不计入。<br />
          订单利润 = 销售额 − 广告费(SP+SB+SV+SEM) − WFS配送费 − 佣金 − 采购成本 − 头程成本 − 退款额 − 仓储费日摊；
          ROI = 订单利润×6.6 ÷ (采购+头程人民币)；成本取业务日当天的历史快照价；「毛利润(旧)」列为旧口径仅供对账。
        </div>
      )}

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
                {cfgOrderedSelected.map((k, idx) => {
                  const isPin = cfgPins.includes(k);
                  return (
                    <div key={k} draggable
                      onDragStart={() => { dragColIdxRef.current = idx; }}
                      onDragOver={(e) => e.preventDefault()}
                      onDrop={() => {
                        const fromIdx = dragColIdxRef.current;
                        dragColIdxRef.current = null;
                        if (fromIdx === null || fromIdx === idx) return;
                        const view = [...cfgOrderedSelected];
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
