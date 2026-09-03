/**
 * SalesDashboard.tsx
 *
 * 产品负责人经营看板 / 公司销售驾驶舱（:3001 admin-frontend）
 * 接口：/api/lingxing-sales/dashboard 、 /dashboard/owner-products 、 /dashboard/trends
 *
 * v1：筛选区 → 公司指标卡片 → 负责人经营排行 → 下钻明细 → 产品异常区
 * v2：环比对比卡片 + 公司趋势（图+表）+ 负责人排名变化 + 负责人趋势（下钻内）
 *
 * 日期规则（美国业务日与中国时间存在同步差，中国约 16 点后才有美国前一业务日数据）：
 *   最新数据日 = MAX(stat_date)（默认）；昨天 = 中国当前日期-3；
 *   近7天 = D-9~D-3；近30天 = D-32~D-3；本月 = 本月1日~D-3（空范围时兜底最新数据日所在月）；
 *   自定义日期不偏移。
 */

import { useState, useEffect, useCallback, useReducer, useMemo } from "react";
import { ItemIdLink } from "./ItemIdLink";

const API_BASE = "/api/lingxing-sales";

// ── 类型 ──────────────────────────────────────────────────────────────────────

interface StoreOption { store_id: string; store_name: string; }

interface Meta {
  date_from: string; date_to: string;
  latest_sales_date: string | null;
  inventory_snapshot_date: string | null;
  avg_window_days: number;
  exchange_rate: number;
  commission_note: string;
  platform_fee_available: boolean;
  stock_note: string;
  ad_note: string;
}

interface Cards {
  sales_amount: number; order_count: number;
  gross_profit: number; gross_margin: number | null;
  ad_spend: number; ad_sales: number;
  acos: number | null; tacos: number | null;
  wfs_item_count: number; exception_item_count: number;
}

interface RankRow {
  owner: string; product_total: number; product_with_sales: number;
  sales_amount: number; order_count: number; refund_amount: number;
  ad_spend: number; ad_sales: number; acos: number | null; tacos: number | null;
  gross_profit: number; gross_margin: number | null;
  wfs_stock: number; stock_days: number | null; exception_count: number;
}

interface ExRow {
  owner: string; code: string; label: string;
  product_count: number; null_count: number; zero_count: number;
  affected_sales: number; affected_ad_spend: number;
}

interface DashboardData { meta: Meta; cards: Cards; ownerRanking: RankRow[]; exceptions: ExRow[]; }

interface ProductRow {
  store_id: string; store_name: string; item_id: string; msku: string; sku: string;
  product_name: string; owner: string; owner_source: string;
  sales_qty: number; order_count: number; sales_amount: number; refund_amount: number;
  delivery_fee: number | null; purchase_cost: number | null; first_mile_shipping_cost: number | null;
  cost_source: string; commission_rate: number; commission: number; platform_fee_ref: number | null;
  gross_profit_ex_ad: number; available_stock: number; wfs_available_stock: number;
  stock_days: number | null; exceptions: string[];
}

interface AdItemRow {
  store_id: string; store_name: string; item_id: string; owner: string; owner_source: string;
  sku_known: string; ad_spend: number; ad_sales: number; ad_orders: number;
  item_sales_amount: number; acos: number | null; tacos: number | null; exceptions: string[];
}

interface DetailData {
  meta: { date_from: string; date_to: string; owner: string; exception_type: string };
  rows: ProductRow[]; ad_item_rows: AdItemRow[];
}

// v2 类型
interface TrendPoint {
  stat_date: string; sales_amount: number; order_count: number;
  ad_spend: number; ad_sales: number; gross_profit: number;
  gross_margin: number | null; acos: number | null; tacos: number | null;
}

interface ComparisonMetric {
  key: string; label: string; ratio: boolean;
  current: number | null; previous: number | null;
  change: number | null; change_pct: number | null;
}

interface OwnerChangeRow {
  owner: string;
  sales_current: number; sales_previous: number; sales_change: number; sales_change_pct: number | null;
  gross_current: number; gross_previous: number; gross_change: number;
  margin_current: number | null; margin_previous: number | null; margin_change: number | null;
  tacos_current: number | null; tacos_previous: number | null; tacos_change: number | null;
  exception_count: number;
}

interface TrendsData {
  dateRange: { date_from: string; date_to: string; compare_from: string; compare_to: string; latest_sales_date?: string | null };
  companyTrend: TrendPoint[];
  ownerTrend: TrendPoint[];
  comparison: { metrics: ComparisonMetric[] };
  ownerRankingChanges: OwnerChangeRow[];
}

// ── 工具 ──────────────────────────────────────────────────────────────────────

async function apiFetch<T>(url: string): Promise<T> {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  const data = await res.json();
  if (data && typeof data === "object" && "error" in data && (data as { error?: string }).error) {
    throw new Error(String((data as { error: string }).error));
  }
  return data as T;
}

function fmtNum(n: number | null | undefined, digits = 0): string {
  if (n == null) return "—";
  return n.toLocaleString("zh-CN", { minimumFractionDigits: digits, maximumFractionDigits: digits });
}
function fmtMoney(n: number | null | undefined): string { return n == null ? "—" : "$" + fmtNum(n, 2); }
function fmtPct(n: number | null | undefined): string { return n == null ? "—" : (n * 100).toFixed(2) + "%"; }
function fmtCost(n: number | null | undefined): string {
  if (n === null || n === undefined) return "未配置";
  if (n === 0) return "0（异常）";
  return fmtNum(n, 2);
}

// 本地时区日期（中国），避免 toISOString 的 UTC 偏差
function pad2(n: number): string { return String(n).padStart(2, "0"); }
function localISO(d: Date): string { return `${d.getFullYear()}-${pad2(d.getMonth() + 1)}-${pad2(d.getDate())}`; }
function localDaysAgo(n: number): string { const d = new Date(); d.setDate(d.getDate() - n); return localISO(d); }
function localMonthStart(): string { const d = new Date(); return `${d.getFullYear()}-${pad2(d.getMonth() + 1)}-01`; }

// 本月的上期 = 上月同期（同样天数，封顶上月末）
function monthCompareRange(from: string, to: string): { cf: string; ct: string } {
  const f = new Date(`${from}T00:00:00`);
  const prevStart = new Date(f.getFullYear(), f.getMonth() - 1, 1);
  const prevEnd = new Date(f.getFullYear(), f.getMonth(), 0);
  const days = Math.max(0, Math.floor((Date.parse(to) - Date.parse(from)) / 86400000));
  const ctDate = new Date(prevStart); ctDate.setDate(prevStart.getDate() + days);
  return { cf: localISO(prevStart), ct: localISO(ctDate > prevEnd ? prevEnd : ctDate) };
}

const EXCEPTION_LABELS: Record<string, string> = {
  sales_no_sku: "有销售但SKU为空",
  ad_no_sku: "有广告花费但SKU为空",
  missing_purchase_cost: "缺采购成本",
  missing_first_mile_cost: "缺头程成本",
  missing_delivery_fee: "缺WFS配送费",
  ad_no_sales: "广告花费>0但销售额=0",
};

const UNASSIGNED_LABEL = "未分配";
const FILTER_STORAGE_KEY = "salesDashboard.filters.v2";

type OwnerMode = "single" | "multi";
type CompareRangeType = "auto" | "7d" | "30d" | "custom";
type ProductStatusFilter = "all" | "active" | "inactive";
type CostFilter = "all" | "missing_purchase_cost" | "missing_first_mile_cost" | "missing_delivery_fee";
type AdFilter = "all" | "with_ads" | "without_ads" | "high_acos";
type ProfitFilter = "all" | "positive" | "negative" | "low_margin";

interface FilterState {
  ownerMode: OwnerMode;
  owners: string[];
  productStatus: ProductStatusFilter;
  costFilter: CostFilter;
  adFilter: AdFilter;
  profitFilter: ProfitFilter;
  compareRangeType: CompareRangeType;
  customCompareDays: number;
}

type FilterAction =
  | { type: "setOwnerMode"; ownerMode: OwnerMode }
  | { type: "setOwners"; owners: string[] }
  | { type: "toggleOwner"; owner: string; allOwners: string[] }
  | { type: "clearOwners" }
  | { type: "selectOnlyOwner"; owner: string }
  | { type: "setProductStatus"; value: ProductStatusFilter }
  | { type: "setCostFilter"; value: CostFilter }
  | { type: "setAdFilter"; value: AdFilter }
  | { type: "setProfitFilter"; value: ProfitFilter }
  | { type: "setCompareRangeType"; value: CompareRangeType }
  | { type: "setCustomCompareDays"; value: number };

const defaultFilters: FilterState = {
  ownerMode: "single",
  owners: [],
  productStatus: "all",
  costFilter: "all",
  adFilter: "all",
  profitFilter: "all",
  compareRangeType: "auto",
  customCompareDays: 30,
};

function uniqOwners(owners: string[]): string[] {
  return [...new Set(owners.map((o) => o.trim()).filter(Boolean))];
}

function readStoredFilters(): FilterState {
  try {
    const raw = window.localStorage.getItem(FILTER_STORAGE_KEY);
    if (!raw) return defaultFilters;
    const parsed = JSON.parse(raw) as Partial<FilterState>;
    return {
      ...defaultFilters,
      ...parsed,
      ownerMode: parsed.ownerMode === "multi" ? "multi" : "single",
      owners: uniqOwners(Array.isArray(parsed.owners) ? parsed.owners : []),
      customCompareDays: Math.max(1, Math.min(180, Number(parsed.customCompareDays ?? 30) || 30)),
    };
  } catch {
    return defaultFilters;
  }
}

function filterReducer(state: FilterState, action: FilterAction): FilterState {
  switch (action.type) {
    case "setOwnerMode": {
      const owners = action.ownerMode === "single" ? state.owners.slice(0, 1) : state.owners;
      return { ...state, ownerMode: action.ownerMode, owners };
    }
    case "setOwners":
      return { ...state, owners: state.ownerMode === "single" ? uniqOwners(action.owners).slice(0, 1) : uniqOwners(action.owners) };
    case "toggleOwner": {
      if (state.ownerMode === "single") return { ...state, owners: [action.owner] };
      const current = new Set(state.owners);
      if (current.has(action.owner)) current.delete(action.owner);
      else current.add(action.owner);
      return { ...state, owners: [...current].filter((o) => action.allOwners.includes(o)) };
    }
    case "clearOwners":
      return { ...state, owners: [] };
    case "selectOnlyOwner":
      return { ...state, owners: [action.owner] };
    case "setProductStatus":
      return { ...state, productStatus: action.value };
    case "setCostFilter":
      return { ...state, costFilter: action.value };
    case "setAdFilter":
      return { ...state, adFilter: action.value };
    case "setProfitFilter":
      return { ...state, profitFilter: action.value };
    case "setCompareRangeType":
      return { ...state, compareRangeType: action.value };
    case "setCustomCompareDays":
      return { ...state, customCompareDays: Math.max(1, Math.min(180, Math.floor(action.value) || 1)) };
    default:
      return state;
  }
}

function dateRangeByDays(days: number): { from: string; to: string } {
  return { from: localDaysAgo(days + 2), to: localDaysAgo(3) };
}

function previousRange(from: string, to: string, daysOverride?: number): { cf: string; ct: string } {
  const days = daysOverride ?? (Math.floor((Date.parse(to) - Date.parse(from)) / 86400000) + 1);
  const ctDate = new Date(`${from}T00:00:00`);
  ctDate.setDate(ctDate.getDate() - 1);
  const cfDate = new Date(ctDate);
  cfDate.setDate(ctDate.getDate() - days + 1);
  return { cf: localISO(cfDate), ct: localISO(ctDate) };
}

function cardsFromRanking(rows: RankRow[], base: Cards): Cards {
  const sales = rows.reduce((s, r) => s + r.sales_amount, 0);
  const adSpend = rows.reduce((s, r) => s + r.ad_spend, 0);
  const adSales = rows.reduce((s, r) => s + r.ad_sales, 0);
  const gross = rows.reduce((s, r) => s + r.gross_profit, 0);
  return {
    ...base,
    sales_amount: Math.round(sales * 100) / 100,
    order_count: rows.reduce((s, r) => s + r.order_count, 0),
    gross_profit: Math.round(gross * 100) / 100,
    gross_margin: sales > 0 ? Math.round((gross / sales) * 10000) / 10000 : null,
    ad_spend: Math.round(adSpend * 100) / 100,
    ad_sales: Math.round(adSales * 100) / 100,
    acos: adSales > 0 ? Math.round((adSpend / adSales) * 10000) / 10000 : null,
    tacos: sales > 0 ? Math.round((adSpend / sales) * 10000) / 10000 : null,
    wfs_item_count: rows.reduce((s, r) => s + (r.wfs_stock > 0 ? r.product_with_sales : 0), 0),
    exception_item_count: rows.reduce((s, r) => s + r.exception_count, 0),
  };
}

function applyClientFilters(data: DashboardData, filters: FilterState): DashboardData {
  const selected = new Set(filters.owners);
  const ownerSelected = selected.size > 0;
  const ownerHasCostException = new Set(
    data.exceptions.filter((e) => filters.costFilter === "all" || e.code === filters.costFilter).map((e) => e.owner),
  );
  let ranking = data.ownerRanking.filter((r) => !ownerSelected || selected.has(r.owner));

  if (filters.costFilter !== "all") ranking = ranking.filter((r) => ownerHasCostException.has(r.owner));
  if (filters.adFilter === "with_ads") ranking = ranking.filter((r) => r.ad_spend > 0);
  if (filters.adFilter === "without_ads") ranking = ranking.filter((r) => r.ad_spend === 0);
  if (filters.adFilter === "high_acos") ranking = ranking.filter((r) => (r.acos ?? 0) > 0.3);
  if (filters.profitFilter === "positive") ranking = ranking.filter((r) => r.gross_profit > 0);
  if (filters.profitFilter === "negative") ranking = ranking.filter((r) => r.gross_profit < 0);
  if (filters.profitFilter === "low_margin") ranking = ranking.filter((r) => (r.gross_margin ?? 1) < 0.1);
  if (filters.productStatus === "inactive") ranking = [];

  const allowedOwners = new Set(ranking.map((r) => r.owner));
  const exceptions = data.exceptions.filter((e) =>
    allowedOwners.has(e.owner) && (filters.costFilter === "all" || e.code === filters.costFilter),
  );
  return { ...data, cards: cardsFromRanking(ranking, data.cards), ownerRanking: ranking, exceptions };
}

// ── 小组件 ────────────────────────────────────────────────────────────────────

function Card({ label, value, sub, warn }: { label: string; value: string; sub?: string; warn?: boolean }) {
  return (
    <div style={{
      background: "#fff", border: `1px solid ${warn ? "#fecaca" : "#e5e7eb"}`, borderRadius: 10,
      padding: "12px 16px", minWidth: 130, flex: "1 1 130px",
    }}>
      <div style={{ fontSize: 12, color: "#6b7280", marginBottom: 4 }}>{label}</div>
      <div style={{ fontSize: 20, fontWeight: 700, color: warn ? "#dc2626" : "#111827" }}>{value}</div>
      {sub && <div style={{ fontSize: 11, color: "#9ca3af", marginTop: 2 }}>{sub}</div>}
    </div>
  );
}

function Th({ label, sortKey, sort, onSort }: {
  label: string; sortKey?: string;
  sort?: { key: string; desc: boolean }; onSort?: (k: string) => void;
}) {
  const sortable = Boolean(sortKey && onSort);
  const active = sortable && sort?.key === sortKey;
  return (
    <th
      onClick={sortable ? () => onSort!(sortKey!) : undefined}
      style={{
        padding: "8px 10px", background: "#f8fafc", borderBottom: "2px solid #e5e7eb",
        textAlign: "left", whiteSpace: "nowrap", fontWeight: 600,
        color: active ? "#4f46e5" : "#374151", cursor: sortable ? "pointer" : "default",
        userSelect: "none",
      }}
    >
      {label}{active ? (sort!.desc ? " ↓" : " ↑") : ""}
    </th>
  );
}

const tdStyle: React.CSSProperties = {
  padding: "7px 10px", borderBottom: "1px solid #f1f5f9", whiteSpace: "nowrap", color: "#374151",
};

// ── v2：纯 SVG 折线图（无外部依赖） ──────────────────────────────────────────────

function MiniLineChart({ points, value, fmt }: {
  points: TrendPoint[];
  value: (p: TrendPoint) => number | null;
  fmt: (n: number) => string;
}) {
  const vals = points.map((p) => value(p));
  const nums = vals.filter((v): v is number => v !== null && Number.isFinite(v));
  if (points.length === 0 || nums.length === 0) {
    return <div style={{ padding: 24, textAlign: "center", color: "#9ca3af", fontSize: 13 }}>暂无趋势数据</div>;
  }
  const W = 720; const H = 180; const PL = 56; const PR = 12; const PT = 14; const PB = 26;
  let min = Math.min(...nums); let max = Math.max(...nums);
  if (min > 0) min = 0;
  if (max === min) max = min + 1;
  const x = (i: number) => PL + (W - PL - PR) * (points.length <= 1 ? 0.5 : i / (points.length - 1));
  const y = (v: number) => PT + (H - PT - PB) * (1 - (v - min) / (max - min));

  let path = "";
  let started = false;
  vals.forEach((v, i) => {
    if (v === null || !Number.isFinite(v)) { started = false; return; }
    path += `${started ? "L" : "M"}${x(i).toFixed(1)},${y(v).toFixed(1)} `;
    started = true;
  });
  const zeroY = min < 0 && max > 0 ? y(0) : null;

  return (
    <svg viewBox={`0 0 ${W} ${H}`} style={{ width: "100%", maxWidth: 900, display: "block" }}>
      <line x1={PL} y1={PT} x2={PL} y2={H - PB} stroke="#e5e7eb" />
      <line x1={PL} y1={H - PB} x2={W - PR} y2={H - PB} stroke="#e5e7eb" />
      {zeroY !== null && <line x1={PL} y1={zeroY} x2={W - PR} y2={zeroY} stroke="#fca5a5" strokeDasharray="4 3" />}
      <text x={PL - 6} y={y(max) + 4} textAnchor="end" fontSize="10" fill="#6b7280">{fmt(max)}</text>
      <text x={PL - 6} y={y(min) + 4} textAnchor="end" fontSize="10" fill="#6b7280">{fmt(min)}</text>
      <path d={path.trim()} fill="none" stroke="#4f46e5" strokeWidth="2" />
      {vals.map((v, i) => (v === null || !Number.isFinite(v)) ? null : (
        <circle key={i} cx={x(i)} cy={y(v)} r="2.6" fill="#4f46e5">
          <title>{points[i].stat_date}: {fmt(v)}</title>
        </circle>
      ))}
      <text x={PL} y={H - 8} fontSize="10" fill="#6b7280">{points[0].stat_date}</text>
      <text x={W - PR} y={H - 8} textAnchor="end" fontSize="10" fill="#6b7280">{points[points.length - 1].stat_date}</text>
    </svg>
  );
}

const TREND_METRICS: { key: string; label: string; ratio: boolean; value: (p: TrendPoint) => number | null }[] = [
  { key: "sales_amount", label: "销售额", ratio: false, value: (p) => p.sales_amount },
  { key: "ad_spend", label: "广告花费", ratio: false, value: (p) => p.ad_spend },
  { key: "gross_profit", label: "毛利额", ratio: false, value: (p) => p.gross_profit },
  { key: "gross_margin", label: "毛利率", ratio: true, value: (p) => p.gross_margin },
  { key: "tacos", label: "TACOS", ratio: true, value: (p) => p.tacos },
];

function TrendBlock({ points, title }: { points: TrendPoint[]; title: string }) {
  const [metricKey, setMetricKey] = useState("sales_amount");
  const [showTable, setShowTable] = useState(false);
  const metric = TREND_METRICS.find((m) => m.key === metricKey) ?? TREND_METRICS[0];
  const fmt = metric.ratio ? ((n: number) => (n * 100).toFixed(1) + "%") : ((n: number) => "$" + fmtNum(n, 0));

  return (
    <div>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 6, alignItems: "center", marginBottom: 8 }}>
        <span style={{ fontSize: 13, fontWeight: 600, color: "#374151", marginRight: 6 }}>{title}</span>
        {TREND_METRICS.map((m) => (
          <button key={m.key} onClick={() => setMetricKey(m.key)} style={{
            padding: "3px 10px", borderRadius: 6, fontSize: 12, cursor: "pointer",
            border: metricKey === m.key ? "1px solid #4f46e5" : "1px solid #e5e7eb",
            background: metricKey === m.key ? "#eef2ff" : "#fff",
            color: metricKey === m.key ? "#4f46e5" : "#374151",
          }}>{m.label}</button>
        ))}
        <button onClick={() => setShowTable((s) => !s)} style={ghostBtn}>{showTable ? "收起表格" : "展开表格"}</button>
      </div>
      <MiniLineChart points={points} value={metric.value} fmt={fmt} />
      {showTable && (
        <div style={{ overflowX: "auto", marginTop: 8 }}>
          <table style={tableStyle}>
            <thead>
              <tr>{["日期", "销售额", "订单量", "广告花费", "广告销售额", "毛利额", "毛利率", "ACOS", "TACOS"].map((h) => <Th key={h} label={h} />)}</tr>
            </thead>
            <tbody>
              {points.map((p) => (
                <tr key={p.stat_date}>
                  <td style={tdStyle}>{p.stat_date}</td>
                  <td style={tdStyle}>{fmtMoney(p.sales_amount)}</td>
                  <td style={tdStyle}>{fmtNum(p.order_count)}</td>
                  <td style={tdStyle}>{fmtMoney(p.ad_spend)}</td>
                  <td style={tdStyle}>{fmtMoney(p.ad_sales)}</td>
                  <td style={{ ...tdStyle, color: p.gross_profit < 0 ? "#dc2626" : "#059669" }}>{fmtMoney(p.gross_profit)}</td>
                  <td style={tdStyle}>{fmtPct(p.gross_margin)}</td>
                  <td style={tdStyle}>{fmtPct(p.acos)}</td>
                  <td style={tdStyle}>{fmtPct(p.tacos)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

// ── v2：环比对比卡片 ──────────────────────────────────────────────────────────

// 指标涨了是好事还是坏事（决定颜色）：+1 涨=绿；-1 涨=红；0 中性
const METRIC_POLARITY: Record<string, number> = {
  sales_amount: 1, order_count: 1, ad_sales: 1, gross_profit: 1, gross_margin: 1,
  acos: -1, tacos: -1, ad_spend: 0,
};

function CompareCards({ metrics, rangeNote }: { metrics: ComparisonMetric[]; rangeNote: string }) {
  return (
    <div>
      <div style={{ fontSize: 12, color: "#6b7280", marginBottom: 8 }}>{rangeNote}</div>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 10 }}>
        {metrics.map((m) => {
          const fmtV = m.ratio ? fmtPct : (m.key === "order_count" ? (n: number | null) => fmtNum(n) : fmtMoney);
          const up = (m.change ?? 0) > 0;
          const flat = m.change === null || m.change === 0;
          const polarity = METRIC_POLARITY[m.key] ?? 0;
          const color = flat || polarity === 0 ? "#6b7280" : (up ? polarity : -polarity) > 0 ? "#059669" : "#dc2626";
          const changeText = m.change === null ? "—"
            : m.ratio ? `${up ? "+" : ""}${(m.change * 100).toFixed(1)}pct`
            : `${up ? "+" : ""}${m.key === "order_count" ? fmtNum(m.change) : fmtMoney(m.change)}${m.change_pct !== null ? `（${up ? "+" : ""}${(m.change_pct * 100).toFixed(1)}%）` : ""}`;
          return (
            <div key={m.key} style={{
              background: "#fff", border: "1px solid #e5e7eb", borderRadius: 10,
              padding: "10px 14px", minWidth: 150, flex: "1 1 150px",
            }}>
              <div style={{ fontSize: 12, color: "#6b7280" }}>{m.label}</div>
              <div style={{ fontSize: 18, fontWeight: 700, color: "#111827", margin: "2px 0" }}>{fmtV(m.current)}</div>
              <div style={{ fontSize: 11, color: "#9ca3af" }}>上期 {fmtV(m.previous)}</div>
              <div style={{ fontSize: 12, fontWeight: 600, color, marginTop: 2 }}>
                {flat ? "持平" : up ? "▲ " : "▼ "}{changeText}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ── v2：负责人排名变化表 ──────────────────────────────────────────────────────

function OwnerChangesTable({ rows, onOwnerClick }: { rows: OwnerChangeRow[]; onOwnerClick: (o: string) => void }) {
  const [sort, setSort] = useState<{ key: string; desc: boolean }>({ key: "sales_change", desc: true });
  const onSort = (key: string) => setSort((s) => (s.key === key ? { key, desc: !s.desc } : { key, desc: true }));
  const sorted = [...rows].sort((a, b) => {
    const av = (a as unknown as Record<string, number | null>)[sort.key] ?? -Infinity;
    const bv = (b as unknown as Record<string, number | null>)[sort.key] ?? -Infinity;
    return sort.desc ? Number(bv) - Number(av) : Number(av) - Number(bv);
  });
  const chg = (v: number | null, pct = false, badWhenUp = false) => {
    if (v === null) return <span style={{ color: "#9ca3af" }}>—</span>;
    const up = v > 0;
    const color = v === 0 ? "#6b7280" : (up !== badWhenUp) ? "#059669" : "#dc2626";
    const text = pct ? `${up ? "+" : ""}${(v * 100).toFixed(1)}pct` : `${up ? "+" : ""}${fmtMoney(v)}`;
    return <span style={{ color, fontWeight: 600 }}>{text}</span>;
  };
  return (
    <div style={{ overflowX: "auto" }}>
      <table style={tableStyle}>
        <thead>
          <tr>
            <Th label="负责人" />
            <Th label="本期销售额" sortKey="sales_current" sort={sort} onSort={onSort} />
            <Th label="上期销售额" sortKey="sales_previous" sort={sort} onSort={onSort} />
            <Th label="销售额变化" sortKey="sales_change" sort={sort} onSort={onSort} />
            <Th label="本期毛利额" sortKey="gross_current" sort={sort} onSort={onSort} />
            <Th label="上期毛利额" sortKey="gross_previous" sort={sort} onSort={onSort} />
            <Th label="毛利额变化" sortKey="gross_change" sort={sort} onSort={onSort} />
            <Th label="本期毛利率" sortKey="margin_current" sort={sort} onSort={onSort} />
            <Th label="毛利率变化" sortKey="margin_change" sort={sort} onSort={onSort} />
            <Th label="本期TACOS" sortKey="tacos_current" sort={sort} onSort={onSort} />
            <Th label="TACOS变化" sortKey="tacos_change" sort={sort} onSort={onSort} />
            <Th label="异常商品数" sortKey="exception_count" sort={sort} onSort={onSort} />
          </tr>
        </thead>
        <tbody>
          {sorted.length === 0 && <tr><td colSpan={12} style={{ textAlign: "center", color: "#9ca3af", padding: "30px 0" }}>暂无数据</td></tr>}
          {sorted.map((r) => (
            <tr key={r.owner} onClick={() => onOwnerClick(r.owner)} style={{ cursor: "pointer", background: r.owner === UNASSIGNED_LABEL ? "#fffbeb" : undefined }}>
              <td style={{ ...tdStyle, fontWeight: 600 }}>{r.owner}</td>
              <td style={tdStyle}>{fmtMoney(r.sales_current)}</td>
              <td style={tdStyle}>{fmtMoney(r.sales_previous)}</td>
              <td style={tdStyle}>{chg(r.sales_change)}{r.sales_change_pct !== null && <span style={{ fontSize: 11, color: "#9ca3af" }}>（{r.sales_change_pct > 0 ? "+" : ""}{(r.sales_change_pct * 100).toFixed(1)}%）</span>}</td>
              <td style={tdStyle}>{fmtMoney(r.gross_current)}</td>
              <td style={tdStyle}>{fmtMoney(r.gross_previous)}</td>
              <td style={tdStyle}>{chg(r.gross_change)}</td>
              <td style={tdStyle}>{fmtPct(r.margin_current)}</td>
              <td style={tdStyle}>{chg(r.margin_change, true)}</td>
              <td style={tdStyle}>{fmtPct(r.tacos_current)}</td>
              <td style={tdStyle}>{chg(r.tacos_change, true, true)}</td>
              <td style={{ ...tdStyle, color: r.exception_count > 0 ? "#dc2626" : "#9ca3af" }}>{fmtNum(r.exception_count)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function OwnerFilterDropdown({
  owners, selected, mode, onMode, onToggle, onClear, onAll,
}: {
  owners: string[];
  selected: string[];
  mode: OwnerMode;
  onMode: (mode: OwnerMode) => void;
  onToggle: (owner: string) => void;
  onClear: () => void;
  onAll: () => void;
}) {
  const [search, setSearch] = useState("");
  const selectedSet = new Set(selected);
  const shown = owners.filter((o) => o.toLowerCase().includes(search.trim().toLowerCase()));
  const label = selected.length === 0 ? "负责人筛选" : mode === "single" ? selected[0] : `已选 ${selected.length} 人`;

  return (
    <details style={{ position: "relative" }}>
      <summary style={{
        ...inputStyle, listStyle: "none", cursor: "pointer", minWidth: 150,
        color: selected.length ? "#4f46e5" : "#374151", fontWeight: selected.length ? 600 : 400,
      }}>
        {label}
      </summary>
      <div style={{
        position: "absolute", zIndex: 20, top: 34, left: 0, width: 280, background: "#fff",
        border: "1px solid #e5e7eb", borderRadius: 10, boxShadow: "0 12px 30px rgba(15,23,42,0.16)",
        padding: 10,
      }}>
        <div style={{ display: "flex", gap: 6, marginBottom: 8 }}>
          {(["single", "multi"] as OwnerMode[]).map((m) => (
            <button key={m} onClick={() => onMode(m)} style={{
              ...ghostBtn,
              background: mode === m ? "#eef2ff" : "#fff",
              borderColor: mode === m ? "#4f46e5" : "#e5e7eb",
              fontWeight: mode === m ? 700 : 400,
            }}>{m === "single" ? "单选" : "多选"}</button>
          ))}
          <button onClick={onClear} style={{ ...ghostBtn, marginLeft: "auto" }}>清空筛选</button>
        </div>
        <input
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="搜索负责人"
          style={{ ...inputStyle, width: "100%", marginBottom: 8 }}
        />
        {mode === "multi" && (
          <label style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 13, padding: "5px 4px", borderBottom: "1px solid #f1f5f9" }}>
            <input type="checkbox" checked={owners.length > 0 && selected.length === owners.length} onChange={(e) => e.currentTarget.checked ? onAll() : onClear()} />
            全选
          </label>
        )}
        <div style={{ maxHeight: 260, overflowY: "auto", paddingTop: 4 }}>
          {shown.length === 0 && <div style={{ padding: 12, color: "#9ca3af", fontSize: 13 }}>无匹配负责人</div>}
          {shown.map((owner) => (
            <label key={owner} style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 13, padding: "6px 4px", cursor: "pointer" }}>
              <input
                type={mode === "single" ? "radio" : "checkbox"}
                checked={selectedSet.has(owner)}
                onChange={() => onToggle(owner)}
              />
              <span>{owner}</span>
            </label>
          ))}
        </div>
      </div>
    </details>
  );
}

function CompareRangeControl({ filters, dispatch }: {
  filters: FilterState;
  dispatch: (action: FilterAction) => void;
}) {
  return (
    <div style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "center", marginBottom: 10 }}>
      <span style={{ fontSize: 12, color: "#6b7280" }}>环比周期</span>
      <select
        value={filters.compareRangeType}
        onChange={(e) => dispatch({ type: "setCompareRangeType", value: e.target.value as CompareRangeType })}
        style={inputStyle}
      >
        <option value="auto">自动（当前范围等长前推）</option>
        <option value="7d">7天</option>
        <option value="30d">30天</option>
        <option value="custom">自定义</option>
      </select>
      {filters.compareRangeType === "custom" && (
        <>
          <input
            type="number"
            min={1}
            max={180}
            value={filters.customCompareDays}
            onChange={(e) => dispatch({ type: "setCustomCompareDays", value: Number(e.target.value) })}
            style={{ ...inputStyle, width: 82 }}
          />
          <span style={{ fontSize: 12, color: "#6b7280" }}>天 vs 前N天</span>
        </>
      )}
    </div>
  );
}

// ── 主组件 ────────────────────────────────────────────────────────────────────

const QUICK_RANGES = ["最新数据日", "昨天", "近7天", "近30天", "本月", "自定义"] as const;

export default function SalesDashboard() {
  const [stores, setStores] = useState<StoreOption[]>([]);
  const [quick, setQuick] = useState<(typeof QUICK_RANGES)[number]>("近30天");
  const [dateFrom, setDateFrom] = useState(() => dateRangeByDays(30).from);
  const [dateTo, setDateTo] = useState(() => dateRangeByDays(30).to);
  const [cmpFrom, setCmpFrom] = useState("");   // 上期覆盖（"本月"用上月同期）
  const [cmpTo, setCmpTo] = useState("");
  const [storeId, setStoreId] = useState("");
  const [keyword, setKeyword] = useState("");
  const [kwInput, setKwInput] = useState("");
  const [filters, dispatchFilters] = useReducer(filterReducer, undefined, readStoredFilters);

  const [data, setData] = useState<DashboardData | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const [trends, setTrends] = useState<TrendsData | null>(null);
  const [trendsLoading, setTrendsLoading] = useState(false);
  const [trendsError, setTrendsError] = useState("");

  const [sort, setSort] = useState<{ key: string; desc: boolean }>({ key: "sales_amount", desc: true });

  const [detail, setDetail] = useState<DetailData | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailTitle, setDetailTitle] = useState("");
  const [ownerTrend, setOwnerTrend] = useState<TrendPoint[] | null>(null);

  useEffect(() => {
    apiFetch<StoreOption[]>(`${API_BASE}/stores`).then(setStores).catch(() => setStores([]));
  }, []);

  useEffect(() => {
    window.localStorage.setItem(FILTER_STORAGE_KEY, JSON.stringify(filters));
  }, [filters]);

  // ── 快捷日期（美国业务日规则：D = 中国当前日期） ──────────────────────────────
  function applyQuick(q: (typeof QUICK_RANGES)[number]) {
    setQuick(q);
    setCmpFrom(""); setCmpTo("");
    if (q === "最新数据日") { setDateFrom(""); setDateTo(""); }
    else if (q === "昨天") { const d = localDaysAgo(3); setDateFrom(d); setDateTo(d); }
    else if (q === "近7天") { setDateFrom(localDaysAgo(9)); setDateTo(localDaysAgo(3)); }
    else if (q === "近30天") { const r = dateRangeByDays(30); setDateFrom(r.from); setDateTo(r.to); }
    else if (q === "本月") {
      const start = localMonthStart();
      const end = localDaysAgo(3);
      let from = start; let to = end;
      if (start > end) {
        // 本月还没有可用数据：兜底最新有数据日所在月；无 meta 时兜底上月完整月
        const latest = data?.meta.latest_sales_date;
        if (latest) { from = latest.slice(0, 7) + "-01"; to = latest; }
        else {
          const now = new Date();
          const prev1 = new Date(now.getFullYear(), now.getMonth() - 1, 1);
          const prevEnd = new Date(now.getFullYear(), now.getMonth(), 0);
          from = localISO(prev1); to = localISO(prevEnd);
        }
      }
      setDateFrom(from); setDateTo(to);
      const { cf, ct } = monthCompareRange(from, to);   // 上期 = 上月同期
      setCmpFrom(cf); setCmpTo(ct);
    }
    // 自定义：保留当前输入，不偏移
  }

  const buildQuery = useCallback((extra?: Record<string, string>) => {
    const p = new URLSearchParams();
    if (dateFrom) p.set("date_from", dateFrom);
    if (dateTo) p.set("date_to", dateTo);
    if (storeId) p.set("store_id", storeId);
    if (filters.ownerMode === "single" && filters.owners.length === 1) p.set("owner", filters.owners[0]);
    if (keyword) p.set("keyword", keyword);
    for (const [k, v] of Object.entries(extra ?? {})) if (v) p.set(k, v);
    return p.toString();
  }, [dateFrom, dateTo, storeId, filters.ownerMode, filters.owners, keyword]);

  const compareOverride = useMemo(() => {
    if (!dateFrom || !dateTo) return { cf: cmpFrom, ct: cmpTo };
    if (filters.compareRangeType === "auto") return { cf: cmpFrom, ct: cmpTo };
    const days = filters.compareRangeType === "7d" ? 7 : filters.compareRangeType === "30d" ? 30 : filters.customCompareDays;
    return previousRange(dateFrom, dateTo, days);
  }, [cmpFrom, cmpTo, dateFrom, dateTo, filters.compareRangeType, filters.customCompareDays]);

  const loadDashboard = useCallback(async () => {
    setLoading(true); setError(""); setDetail(null); setOwnerTrend(null);
    try {
      setData(await apiFetch<DashboardData>(`${API_BASE}/dashboard?${buildQuery()}`));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setData(null);
    } finally {
      setLoading(false);
    }
  }, [buildQuery]);

  const loadTrends = useCallback(async () => {
    setTrendsLoading(true); setTrendsError("");
    try {
      const q = buildQuery({ compare_from: compareOverride.cf, compare_to: compareOverride.ct });
      setTrends(await apiFetch<TrendsData>(`${API_BASE}/dashboard/trends?${q}`));
    } catch (e) {
      setTrendsError(e instanceof Error ? e.message : String(e));
      setTrends(null);
    } finally {
      setTrendsLoading(false);
    }
  }, [buildQuery, compareOverride]);

  useEffect(() => { void loadDashboard(); }, [loadDashboard]);
  useEffect(() => { void loadTrends(); }, [loadTrends]);

  async function loadDetail(owner: string, exceptionType?: string) {
    setDetailLoading(true);
    setOwnerTrend(null);
    setDetailTitle(exceptionType
      ? `${owner} · ${EXCEPTION_LABELS[exceptionType] ?? exceptionType}`
      : `${owner} · 产品明细`);
    try {
      const q = buildQuery({ owner, exception_type: exceptionType ?? "" });
      setDetail(await apiFetch<DetailData>(`${API_BASE}/dashboard/owner-products?${q}`));
      if (!exceptionType) {
        // 负责人趋势（失败不影响明细展示）
        try {
          const tq = buildQuery({ owner, compare_from: compareOverride.cf, compare_to: compareOverride.ct });
          const t = await apiFetch<TrendsData>(`${API_BASE}/dashboard/trends?${tq}`);
          setOwnerTrend(t.ownerTrend.length > 0 ? t.ownerTrend : t.companyTrend);
        } catch { setOwnerTrend(null); }
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setDetail(null);
    } finally {
      setDetailLoading(false);
    }
  }

  function onSort(key: string) {
    setSort((s) => (s.key === key ? { key, desc: !s.desc } : { key, desc: true }));
  }

  const owners = useMemo(() => uniqOwners([...(data?.ownerRanking ?? []).map((r) => r.owner), ...filters.owners]).sort((a, b) => a.localeCompare(b, "zh-CN")), [data, filters.owners]);
  const visibleData = useMemo(() => data ? applyClientFilters(data, filters) : null, [data, filters]);
  const visibleTrends = useMemo(() => {
    if (!trends) return null;
    if (filters.owners.length === 0) return trends;
    const selected = new Set(filters.owners);
    return { ...trends, ownerRankingChanges: trends.ownerRankingChanges.filter((r) => selected.has(r.owner)) };
  }, [trends, filters.owners]);
  const visibleRanking = [...(visibleData?.ownerRanking ?? [])].sort((a, b) => {
    const av = (a as unknown as Record<string, number | null>)[sort.key] ?? -Infinity;
    const bv = (b as unknown as Record<string, number | null>)[sort.key] ?? -Infinity;
    return sort.desc ? Number(bv) - Number(av) : Number(av) - Number(bv);
  });
  const meta = visibleData?.meta;
  const cards = visibleData?.cards;

  return (
    <div style={{ padding: 20, background: "#f3f4f6", minHeight: "calc(100vh - 44px)" }}>
      {/* ── 筛选区 ── */}
      <div style={{ background: "#fff", border: "1px solid #e5e7eb", borderRadius: 10, padding: 14, marginBottom: 14 }}>
        <div style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "center" }}>
          {QUICK_RANGES.map((q) => (
            <button key={q} onClick={() => applyQuick(q)} style={{
              padding: "5px 12px", borderRadius: 6, fontSize: 13, cursor: "pointer",
              border: quick === q ? "1px solid #4f46e5" : "1px solid #e5e7eb",
              background: quick === q ? "#eef2ff" : "#fff",
              color: quick === q ? "#4f46e5" : "#374151", fontWeight: quick === q ? 600 : 400,
            }}>{q}</button>
          ))}
          <input type="date" value={dateFrom} onChange={(e) => { setDateFrom(e.target.value); setQuick("自定义"); setCmpFrom(""); setCmpTo(""); }}
            style={inputStyle} />
          <span style={{ color: "#9ca3af" }}>~</span>
          <input type="date" value={dateTo} onChange={(e) => { setDateTo(e.target.value); setQuick("自定义"); setCmpFrom(""); setCmpTo(""); }}
            style={inputStyle} />
          <OwnerFilterDropdown
            owners={owners}
            selected={filters.owners}
            mode={filters.ownerMode}
            onMode={(ownerMode) => dispatchFilters({ type: "setOwnerMode", ownerMode })}
            onToggle={(owner) => dispatchFilters({ type: "toggleOwner", owner, allOwners: owners })}
            onClear={() => dispatchFilters({ type: "clearOwners" })}
            onAll={() => dispatchFilters({ type: "setOwners", owners })}
          />
          <select value={storeId} onChange={(e) => setStoreId(e.target.value)} style={inputStyle}>
            <option value="">全部店铺</option>
            {stores.map((s) => <option key={s.store_id} value={s.store_id}>{s.store_name}</option>)}
          </select>
          <select value={filters.productStatus} onChange={(e) => dispatchFilters({ type: "setProductStatus", value: e.target.value as ProductStatusFilter })} style={inputStyle}>
            <option value="all">全部阶段</option>
            <option value="active">active</option>
            <option value="inactive">inactive</option>
          </select>
          <select value={filters.costFilter} onChange={(e) => dispatchFilters({ type: "setCostFilter", value: e.target.value as CostFilter })} style={inputStyle}>
            <option value="all">全部成本状态</option>
            <option value="missing_purchase_cost">缺采购成本</option>
            <option value="missing_first_mile_cost">缺头程成本</option>
            <option value="missing_delivery_fee">缺WFS费用</option>
          </select>
          <select value={filters.adFilter} onChange={(e) => dispatchFilters({ type: "setAdFilter", value: e.target.value as AdFilter })} style={inputStyle}>
            <option value="all">全部广告状态</option>
            <option value="with_ads">有广告</option>
            <option value="without_ads">无广告</option>
            <option value="high_acos">高ACOS(&gt;30%)</option>
          </select>
          <select value={filters.profitFilter} onChange={(e) => dispatchFilters({ type: "setProfitFilter", value: e.target.value as ProfitFilter })} style={inputStyle}>
            <option value="all">全部利润状态</option>
            <option value="positive">正利润</option>
            <option value="negative">负利润</option>
            <option value="low_margin">低毛利(&lt;10%)</option>
          </select>
          <input
            value={kwInput}
            onChange={(e) => setKwInput(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter") setKeyword(kwInput.trim()); }}
            placeholder="ItemID / MSKU / SKU / 产品名 / 负责人"
            style={{ ...inputStyle, width: 240 }}
          />
          <button onClick={() => setKeyword(kwInput.trim())} style={primaryBtn}>搜索</button>
          {keyword && (
            <button onClick={() => { setKeyword(""); setKwInput(""); }} style={ghostBtn}>清除搜索</button>
          )}
        </div>
        <div style={{ marginTop: 8, fontSize: 12, color: "#6b7280" }}>
          {meta && (
            <>
              数据日期：{meta.date_from === meta.date_to ? meta.date_from : `${meta.date_from} ~ ${meta.date_to}`}
              {meta.latest_sales_date && `（最新有数据日：${meta.latest_sales_date}）`}
              {meta.inventory_snapshot_date && ` · 库存快照：${meta.inventory_snapshot_date}`}
              {` · 库存天数窗口：近${meta.avg_window_days}天`}
              <br />
            </>
          )}
          <span style={{ color: "#b45309" }}>
            ⓘ 数据按美国业务日同步（中国时间约 16 点后取得美国前一业务日数据），快捷日期已自动避开最近未完成同步的日期；自定义日期不偏移。
          </span>
          {filters.productStatus === "inactive" && (
            <span style={{ color: "#b45309", marginLeft: 8 }}>当前接口仅返回 active 经营数据，inactive 会显示为空。</span>
          )}
        </div>
      </div>

      {loading && <div style={{ padding: 40, textAlign: "center", color: "#6b7280" }}>加载中...</div>}
      {error && <div style={{ padding: 14, background: "#fff5f5", border: "1px solid #fecaca", borderRadius: 8, color: "#dc2626", marginBottom: 14 }}>请求失败：{error}</div>}

      {!loading && visibleData && cards && (
        <>
          {/* ── 公司整体指标卡片 ── */}
          <div style={{ display: "flex", flexWrap: "wrap", gap: 10, marginBottom: 14 }}>
            <Card label="销售额" value={fmtMoney(cards.sales_amount)} />
            <Card label="订单量" value={fmtNum(cards.order_count)} />
            <Card label="毛利额" value={fmtMoney(cards.gross_profit)} warn={cards.gross_profit < 0} />
            <Card label="毛利率" value={fmtPct(cards.gross_margin)} warn={(cards.gross_margin ?? 0) < 0} />
            <Card label="广告花费" value={fmtMoney(cards.ad_spend)} />
            <Card label="广告销售额" value={fmtMoney(cards.ad_sales)} />
            <Card label="ACOS" value={fmtPct(cards.acos)} />
            <Card label="TACOS" value={fmtPct(cards.tacos)} />
            <Card label="WFS库存商品数" value={fmtNum(cards.wfs_item_count)} sub={meta?.inventory_snapshot_date ? `快照 ${meta.inventory_snapshot_date}` : undefined} />
            <Card label="异常商品数" value={fmtNum(cards.exception_item_count)} warn={cards.exception_item_count > 0} />
          </div>

          {/* ── v2：环比对比 ── */}
          <div style={sectionStyle}>
            <div style={sectionTitle}>环比对比 <span style={noteStyle}>本期 vs 上期 · 比例类指标按百分点(pct)</span></div>
            <CompareRangeControl filters={filters} dispatch={dispatchFilters} />
            {trendsLoading && <div style={{ padding: 20, textAlign: "center", color: "#6b7280", fontSize: 13 }}>加载中...</div>}
            {trendsError && <div style={{ fontSize: 13, color: "#dc2626" }}>趋势数据加载失败：{trendsError}</div>}
            {!trendsLoading && visibleTrends && (
              <CompareCards
                metrics={visibleTrends.comparison.metrics}
                rangeNote={`本期 ${visibleTrends.dateRange.date_from} ~ ${visibleTrends.dateRange.date_to} · 上期 ${visibleTrends.dateRange.compare_from} ~ ${visibleTrends.dateRange.compare_to}`}
              />
            )}
          </div>

          {/* ── v2：公司趋势 ── */}
          <div style={sectionStyle}>
            <div style={sectionTitle}>公司趋势 <span style={noteStyle}>使用当前筛选日期范围，逐日展示</span></div>
            {!trendsLoading && visibleTrends && <TrendBlock points={visibleTrends.companyTrend} title="指标：" />}
            {trendsLoading && <div style={{ padding: 20, textAlign: "center", color: "#6b7280", fontSize: 13 }}>加载中...</div>}
          </div>

          {/* ── 负责人经营排行 ── */}
          <div style={sectionStyle}>
            <div style={sectionTitle}>负责人经营排行 <span style={noteStyle}>点击行查看产品明细与负责人趋势 · 点击表头排序</span></div>
            <div style={{ overflowX: "auto" }}>
              <table style={tableStyle}>
                <thead>
                  <tr>
                    <Th label="负责人" />
                    <Th label="负责产品数" sortKey="product_total" sort={sort} onSort={onSort} />
                    <Th label="有销量产品数" sortKey="product_with_sales" sort={sort} onSort={onSort} />
                    <Th label="销售额" sortKey="sales_amount" sort={sort} onSort={onSort} />
                    <Th label="订单量" sortKey="order_count" sort={sort} onSort={onSort} />
                    <Th label="广告花费" sortKey="ad_spend" sort={sort} onSort={onSort} />
                    <Th label="广告销售额" sortKey="ad_sales" sort={sort} onSort={onSort} />
                    <Th label="ACOS" sortKey="acos" sort={sort} onSort={onSort} />
                    <Th label="TACOS" sortKey="tacos" sort={sort} onSort={onSort} />
                    <Th label="毛利额" sortKey="gross_profit" sort={sort} onSort={onSort} />
                    <Th label="毛利率" sortKey="gross_margin" sort={sort} onSort={onSort} />
                    <Th label="WFS库存" sortKey="wfs_stock" sort={sort} onSort={onSort} />
                    <Th label="库存天数" sortKey="stock_days" sort={sort} onSort={onSort} />
                    <Th label="异常商品数" sortKey="exception_count" sort={sort} onSort={onSort} />
                  </tr>
                </thead>
                <tbody>
                  {visibleRanking.length === 0 && (
                    <tr><td colSpan={14} style={{ textAlign: "center", color: "#9ca3af", padding: "36px 0" }}>暂无数据</td></tr>
                  )}
                  {visibleRanking.map((r) => (
                    <tr key={r.owner} onClick={() => void loadDetail(r.owner)}
                        style={{ cursor: "pointer", background: r.owner === UNASSIGNED_LABEL ? "#fffbeb" : undefined }}>
                      <td style={{ ...tdStyle, fontWeight: 600, color: r.owner === UNASSIGNED_LABEL ? "#b45309" : "#111827" }}>
                        {r.owner}
                        <button
                          onClick={(e) => { e.stopPropagation(); dispatchFilters({ type: "selectOnlyOwner", owner: r.owner }); void loadDetail(r.owner); }}
                          style={{ ...ghostBtn, marginLeft: 8 }}
                        >仅筛选此项</button>
                      </td>
                      <td style={tdStyle}>{fmtNum(r.product_total)}</td>
                      <td style={tdStyle}>{fmtNum(r.product_with_sales)}</td>
                      <td style={tdStyle}>{fmtMoney(r.sales_amount)}</td>
                      <td style={tdStyle}>{fmtNum(r.order_count)}</td>
                      <td style={tdStyle}>{fmtMoney(r.ad_spend)}</td>
                      <td style={tdStyle}>{fmtMoney(r.ad_sales)}</td>
                      <td style={tdStyle}>{fmtPct(r.acos)}</td>
                      <td style={tdStyle}>{fmtPct(r.tacos)}</td>
                      <td style={{ ...tdStyle, color: r.gross_profit < 0 ? "#dc2626" : "#059669", fontWeight: 600 }}>{fmtMoney(r.gross_profit)}</td>
                      <td style={{ ...tdStyle, color: (r.gross_margin ?? 0) < 0 ? "#dc2626" : "#374151" }}>{fmtPct(r.gross_margin)}</td>
                      <td style={tdStyle}>{fmtNum(r.wfs_stock)}</td>
                      <td style={tdStyle}>{r.stock_days == null ? "—" : fmtNum(r.stock_days, 1)}</td>
                      <td style={{ ...tdStyle, color: r.exception_count > 0 ? "#dc2626" : "#9ca3af", fontWeight: r.exception_count > 0 ? 700 : 400 }}>{fmtNum(r.exception_count)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          {/* ── v2：负责人排名变化 ── */}
          <div style={sectionStyle}>
            <div style={sectionTitle}>负责人排名变化 <span style={noteStyle}>本期 vs 上期 · 点击表头切换排序（销售额/毛利额/毛利率/TACOS 变化）· 点击行下钻</span></div>
            {!trendsLoading && visibleTrends && (
              <OwnerChangesTable rows={visibleTrends.ownerRankingChanges} onOwnerClick={(o) => void loadDetail(o)} />
            )}
            {trendsLoading && <div style={{ padding: 20, textAlign: "center", color: "#6b7280", fontSize: 13 }}>加载中...</div>}
          </div>

          {/* ── 下钻明细（含负责人趋势） ── */}
          {(detailLoading || detail) && (
            <div style={sectionStyle}>
              <div style={sectionTitle}>
                {detailTitle}
                <button onClick={() => { setDetail(null); setOwnerTrend(null); }} style={{ ...ghostBtn, marginLeft: 12 }}>关闭</button>
              </div>
              {detailLoading && <div style={{ padding: 30, textAlign: "center", color: "#6b7280" }}>加载中...</div>}
              {!detailLoading && detail && (
                <>
                  {ownerTrend && ownerTrend.length > 0 && (
                    <div style={{ marginBottom: 14, paddingBottom: 10, borderBottom: "1px dashed #e5e7eb" }}>
                      <TrendBlock points={ownerTrend} title="负责人趋势：" />
                    </div>
                  )}
                  <div style={{ fontSize: 12, color: "#6b7280", marginBottom: 8 }}>
                    {meta?.ad_note} · {meta?.stock_note} · {meta?.commission_note}
                  </div>
                  <DetailTables detail={detail} />
                </>
              )}
            </div>
          )}

          {/* ── 产品异常区 ── */}
          <div style={sectionStyle}>
            <div style={sectionTitle}>产品异常区 <span style={noteStyle}>范围：筛选期内有销售或有广告花费的商品 · 未配置(null)与配置为0分开统计</span></div>
            <div style={{ overflowX: "auto" }}>
              <table style={tableStyle}>
                <thead>
                  <tr>
                    <Th label="负责人" />
                    <Th label="异常类型" />
                    <Th label="异常产品数" />
                    <Th label="其中未配置" />
                    <Th label="其中配置为0" />
                    <Th label="影响销售额" />
                    <Th label="影响广告花费" />
                    <Th label="操作" />
                  </tr>
                </thead>
                <tbody>
                  {(visibleData.exceptions ?? []).length === 0 && (
                    <tr><td colSpan={8} style={{ textAlign: "center", color: "#9ca3af", padding: "36px 0" }}>暂无异常</td></tr>
                  )}
                  {(visibleData.exceptions ?? []).map((e, i) => (
                    <tr key={i}>
                      <td style={tdStyle}>{e.owner}</td>
                      <td style={{ ...tdStyle, color: "#dc2626", fontWeight: 600 }}>{e.label}</td>
                      <td style={tdStyle}>{fmtNum(e.product_count)}</td>
                      <td style={tdStyle}>{e.null_count > 0 ? fmtNum(e.null_count) : "—"}</td>
                      <td style={tdStyle}>{e.zero_count > 0 ? fmtNum(e.zero_count) : "—"}</td>
                      <td style={tdStyle}>{fmtMoney(e.affected_sales)}</td>
                      <td style={tdStyle}>{fmtMoney(e.affected_ad_spend)}</td>
                      <td style={tdStyle}>
                        <button onClick={() => void loadDetail(e.owner, e.code)} style={ghostBtn}>查看明细</button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}
    </div>
  );
}

// ── 下钻明细表 ────────────────────────────────────────────────────────────────

function DetailTables({ detail }: { detail: DetailData }) {
  const PAGE = 50;
  const [page, setPage] = useState(1);
  const [adPage, setAdPage] = useState(1);
  useEffect(() => { setPage(1); setAdPage(1); }, [detail]);

  const rows = detail.rows.slice((page - 1) * PAGE, page * PAGE);
  const adRows = detail.ad_item_rows.slice((adPage - 1) * PAGE, adPage * PAGE);

  return (
    <>
      <div style={{ fontSize: 13, fontWeight: 600, color: "#374151", margin: "6px 0" }}>
        产品明细（MSKU 级，共 {detail.rows.length} 条）
      </div>
      <div style={{ overflowX: "auto" }}>
        <table style={tableStyle}>
          <thead>
            <tr>
              {["日期", "负责人", "店铺", "ItemID", "MSKU", "SKU", "产品名", "销售额", "退款额", "订单量", "销量",
                "WFS配送费", "采购成本", "头程成本", "佣金", "毛利额(未扣广告)", "毛利率", "WFS库存", "库存天数", "异常状态"]
                .map((h) => <Th key={h} label={h} />)}
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 && <tr><td colSpan={20} style={{ textAlign: "center", color: "#9ca3af", padding: "30px 0" }}>暂无数据</td></tr>}
            {rows.map((r, i) => {
              const margin = r.sales_amount > 0 ? r.gross_profit_ex_ad / r.sales_amount : null;
              return (
                <tr key={i} style={{ background: r.exceptions.length > 0 ? "#fff7ed" : undefined }}>
                  <td style={tdStyle}>{detail.meta.date_from === detail.meta.date_to ? detail.meta.date_from : `${detail.meta.date_from}~${detail.meta.date_to}`}</td>
                  <td style={tdStyle}>{r.owner}{r.owner_source === "product_table" ? "（商品表）" : ""}</td>
                  <td style={tdStyle}>{r.store_name}</td>
                  <td style={tdStyle}><ItemIdLink itemId={r.item_id} /></td>
                  <td style={tdStyle}>{r.msku || "—"}</td>
                  <td style={{ ...tdStyle, color: r.sku ? "#374151" : "#dc2626" }}>{r.sku || "空"}</td>
                  <td style={{ ...tdStyle, maxWidth: 200, overflow: "hidden", textOverflow: "ellipsis" }}>{r.product_name || "—"}</td>
                  <td style={tdStyle}>{fmtMoney(r.sales_amount)}</td>
                  <td style={tdStyle}>{r.refund_amount > 0 ? fmtMoney(r.refund_amount) : "—"}</td>
                  <td style={tdStyle}>{fmtNum(r.order_count)}</td>
                  <td style={tdStyle}>{fmtNum(r.sales_qty)}</td>
                  <td style={{ ...tdStyle, color: r.delivery_fee ? "#374151" : "#dc2626" }}>{fmtCost(r.delivery_fee)}</td>
                  <td style={{ ...tdStyle, color: r.purchase_cost ? "#374151" : "#dc2626" }}>{fmtCost(r.purchase_cost)}{r.cost_source === "yuesi_cs_fixed" ? "（CS固定）" : ""}</td>
                  <td style={{ ...tdStyle, color: r.first_mile_shipping_cost ? "#374151" : "#dc2626" }}>{fmtCost(r.first_mile_shipping_cost)}</td>
                  <td style={tdStyle}>{fmtMoney(r.commission)}（{fmtPct(r.commission_rate)}）</td>
                  <td style={{ ...tdStyle, color: r.gross_profit_ex_ad < 0 ? "#dc2626" : "#059669", fontWeight: 600 }}>{fmtMoney(r.gross_profit_ex_ad)}</td>
                  <td style={tdStyle}>{fmtPct(margin)}</td>
                  <td style={tdStyle}>{fmtNum(r.wfs_available_stock)}</td>
                  <td style={tdStyle}>{r.stock_days == null ? "—" : fmtNum(r.stock_days, 1)}</td>
                  <td style={{ ...tdStyle, color: "#dc2626", fontSize: 12 }}>
                    {r.exceptions.length > 0 ? r.exceptions.map((c) => EXCEPTION_LABELS[c] ?? c).join("；") : "—"}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <SimplePager total={detail.rows.length} page={page} pageSize={PAGE} onPage={setPage} />

      <div style={{ fontSize: 13, fontWeight: 600, color: "#374151", margin: "16px 0 6px" }}>
        广告表现（ItemID 级，不分摊到 MSKU，共 {detail.ad_item_rows.length} 条）
      </div>
      <div style={{ overflowX: "auto" }}>
        <table style={tableStyle}>
          <thead>
            <tr>
              {["负责人", "店铺", "ItemID", "SKU", "广告花费", "广告销售额", "广告订单", "ACOS", "该Item总销售额", "TACOS", "异常状态"]
                .map((h) => <Th key={h} label={h} />)}
            </tr>
          </thead>
          <tbody>
            {adRows.length === 0 && <tr><td colSpan={11} style={{ textAlign: "center", color: "#9ca3af", padding: "30px 0" }}>暂无数据</td></tr>}
            {adRows.map((r, i) => (
              <tr key={i} style={{ background: r.exceptions.length > 0 ? "#fff7ed" : undefined }}>
                <td style={tdStyle}>{r.owner}{r.owner_source === "product_table" ? "（商品表）" : ""}</td>
                <td style={tdStyle}>{r.store_name}</td>
                <td style={tdStyle}><ItemIdLink itemId={r.item_id} /></td>
                <td style={{ ...tdStyle, color: r.sku_known || !r.exceptions.includes("ad_no_sku") ? "#374151" : "#dc2626" }}>
                  {r.sku_known || (r.exceptions.includes("ad_no_sku") ? "空" : "—")}
                </td>
                <td style={tdStyle}>{fmtMoney(r.ad_spend)}</td>
                <td style={tdStyle}>{fmtMoney(r.ad_sales)}</td>
                <td style={tdStyle}>{fmtNum(r.ad_orders)}</td>
                <td style={tdStyle}>{fmtPct(r.acos)}</td>
                <td style={tdStyle}>{fmtMoney(r.item_sales_amount)}</td>
                <td style={tdStyle}>{fmtPct(r.tacos)}</td>
                <td style={{ ...tdStyle, color: "#dc2626", fontSize: 12 }}>
                  {r.exceptions.length > 0 ? r.exceptions.map((c) => EXCEPTION_LABELS[c] ?? c).join("；") : "—"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <SimplePager total={detail.ad_item_rows.length} page={adPage} pageSize={PAGE} onPage={setAdPage} />
    </>
  );
}

function SimplePager({ total, page, pageSize, onPage }: { total: number; page: number; pageSize: number; onPage: (p: number) => void }) {
  const totalPages = Math.ceil(total / pageSize);
  if (totalPages <= 1) return null;
  return (
    <div style={{ display: "flex", gap: 6, justifyContent: "center", marginTop: 10, alignItems: "center", fontSize: 12 }}>
      <button disabled={page <= 1} onClick={() => onPage(page - 1)} style={ghostBtn}>上页</button>
      <span style={{ color: "#6b7280" }}>{page} / {totalPages}</span>
      <button disabled={page >= totalPages} onClick={() => onPage(page + 1)} style={ghostBtn}>下页</button>
    </div>
  );
}

// ── 样式 ──────────────────────────────────────────────────────────────────────

const inputStyle: React.CSSProperties = {
  padding: "5px 10px", borderRadius: 6, border: "1px solid #e5e7eb", fontSize: 13,
  color: "#374151", background: "#fff", outline: "none",
};
const primaryBtn: React.CSSProperties = {
  padding: "5px 14px", borderRadius: 6, border: "none", fontSize: 13, cursor: "pointer",
  background: "#4f46e5", color: "#fff", fontWeight: 600,
};
const ghostBtn: React.CSSProperties = {
  padding: "4px 10px", borderRadius: 6, border: "1px solid #e5e7eb", fontSize: 12,
  cursor: "pointer", background: "#fff", color: "#4f46e5",
};
const sectionStyle: React.CSSProperties = {
  background: "#fff", border: "1px solid #e5e7eb", borderRadius: 10, padding: 14, marginBottom: 14,
};
const sectionTitle: React.CSSProperties = {
  fontSize: 15, fontWeight: 700, color: "#111827", marginBottom: 10,
};
const noteStyle: React.CSSProperties = { fontSize: 12, color: "#9ca3af", fontWeight: 400, marginLeft: 8 };
const tableStyle: React.CSSProperties = { width: "100%", borderCollapse: "collapse", fontSize: 13 };
