/**
 * LingxingSalesData.tsx
 *
 * 领星每日销售数据查看页（:3001 admin-frontend）
 * 数据来源：领星 API 的 FACT 表（销售/广告/库存）；"负责人"列来自飞书 dim_product。
 * 接口：/api/lingxing-sales/*
 * Tab：汇总 / 销售明细 / 广告明细 / 库存明细；日期 + 店铺 + 关键词 + 分页。
 */

import { useState, useEffect, useCallback, type ReactNode } from "react";
import { ItemIdLink } from "./ItemIdLink";

const API_BASE = "/api/lingxing-sales";
const PAGE_SIZE = 50;

// ── 类型 ──────────────────────────────────────────────────────────────────────

interface StoreOption { store_id: string; store_name: string; }
interface SalesSummary { store_name: string; sku_count: number; total_qty: number; total_amount: number; }
interface AdSummary { store_name: string; total_spend: number; total_impressions: number; total_clicks: number; total_orders: number; total_ad_sales: number; }
interface SalesRow { store_name: string; item_id: string; msku: string; sku: string; owner: string | null; sales_qty: number; order_count: number; sales_amount: number; }
interface AdsRow { store_name: string; item_id: string; msku: string; owner: string | null; campaign_name: string; campaign_type: string; ad_group_name: string; impressions: number; clicks: number; ctr: number; ad_spend: number; orders: number; total_sales: number; acos: number; cpc: number; roas: number; }
interface InventoryRow { store_name: string; item_id: string; msku: string; sku: string; owner: string | null; available_stock: number; wfs_available_stock: number; warehouse_stock: number; inbound_stock: number; reserved_stock: number; stock_days: number | null; }
interface PagedResult<T> { total: number; page: number; page_size: number; rows: T[]; }
interface MetricsRow {
  stat_date: string; store_name: string; item_id: string; msku: string; sku: string; owner: string;
  sales_qty: number; sales_amount: number; ad_spend: number;
  delivery_fee: number; purchase_cost: number; first_mile_shipping_cost: number;
  available_stock: number; wfs_available_stock: number; stock_days: number | null;
  commission_rate: number; ad_ratio: number; gross_profit: number; gross_margin: number;
}
interface MetricsResult { stat_date: string; total: number; page: number; page_size: number; rows: MetricsRow[]; }

// ── 工具 ──────────────────────────────────────────────────────────────────────

function yesterday(): string {
  const d = new Date();
  d.setDate(d.getDate() - 1);
  return d.toISOString().slice(0, 10);
}

async function apiFetch<T>(url: string): Promise<T> {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

function fmtNum(n: number | null | undefined, digits = 0): string {
  if (n == null) return "—";
  return n.toLocaleString("zh-CN", { minimumFractionDigits: digits, maximumFractionDigits: digits });
}

function fmtPct(n: number | null | undefined): string {
  if (n == null) return "—";
  return (n * 100).toFixed(2) + "%";
}

// ── 分页 ──────────────────────────────────────────────────────────────────────

function Pagination({ total, page, pageSize, onPage }: { total: number; page: number; pageSize: number; onPage: (p: number) => void }) {
  const totalPages = Math.ceil(total / pageSize);
  if (totalPages <= 1) return null;

  const pages: number[] = [];
  const start = Math.max(1, Math.min(page - 2, totalPages - 4));
  for (let i = start; i <= Math.min(start + 4, totalPages); i++) pages.push(i);

  return (
    <div style={{ display: "flex", gap: 6, justifyContent: "center", marginTop: 14, alignItems: "center" }}>
      <button onClick={() => onPage(1)} disabled={page <= 1} style={btnStyle(false, page <= 1)}>首页</button>
      <button onClick={() => onPage(page - 1)} disabled={page <= 1} style={btnStyle(false, page <= 1)}>上页</button>
      {pages.map(p => (
        <button key={p} onClick={() => onPage(p)} style={btnStyle(p === page, false)}>{p}</button>
      ))}
      <button onClick={() => onPage(page + 1)} disabled={page >= totalPages} style={btnStyle(false, page >= totalPages)}>下页</button>
      <button onClick={() => onPage(totalPages)} disabled={page >= totalPages} style={btnStyle(false, page >= totalPages)}>末页</button>
      <span style={{ fontSize: 12, color: "#6b7280" }}>共 {total} 条 / {totalPages} 页</span>
    </div>
  );
}

function btnStyle(active: boolean, disabled: boolean): React.CSSProperties {
  return {
    padding: "4px 10px", borderRadius: 5, border: "1px solid #e5e7eb", cursor: disabled ? "not-allowed" : "pointer",
    background: active ? "#6366f1" : "#fff", color: active ? "#fff" : "#374151",
    fontWeight: active ? 700 : 400, fontSize: 12, opacity: disabled ? 0.5 : 1,
  };
}

// ── 表格 ──────────────────────────────────────────────────────────────────────

function DataTable({ headers, rows }: { headers: string[]; rows: ReactNode[][] }) {
  return (
    <div style={{ overflowX: "auto", borderRadius: 8, border: "1px solid #e5e7eb" }}>
      <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
        <thead>
          <tr>{headers.map(h => <th key={h} style={{ padding: "8px 12px", background: "#f8fafc", borderBottom: "2px solid #e5e7eb", textAlign: "left", whiteSpace: "nowrap", fontWeight: 600, color: "#374151" }}>{h}</th>)}</tr>
        </thead>
        <tbody>
          {rows.length === 0 && <tr><td colSpan={headers.length} style={{ textAlign: "center", color: "#9ca3af", padding: "40px 0" }}>暂无数据</td></tr>}
          {rows.map((row, i) => (
            <tr key={i} style={{ background: i % 2 === 0 ? "#fff" : "#fafafa" }}>
              {row.map((cell, j) => <td key={j} style={{ padding: "7px 12px", borderBottom: "1px solid #f1f5f9", whiteSpace: "nowrap", color: "#374151" }}>{cell ?? "—"}</td>)}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ── 主页面 ────────────────────────────────────────────────────────────────────

const TABS = ["汇总", "销售明细", "广告明细", "库存明细", "利润明细"];

export default function LingxingSalesData() {
  const [tab, setTab] = useState(0);
  const [targetDate, setTargetDate] = useState(yesterday());
  const [stores, setStores] = useState<StoreOption[]>([]);
  const [storeId, setStoreId] = useState("");
  const [keyword, setKeyword] = useState("");
  const [inputKw, setInputKw] = useState("");
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const [salesSummary, setSalesSummary] = useState<SalesSummary[]>([]);
  const [adSummary, setAdSummary] = useState<AdSummary[]>([]);
  const [salesData, setSalesData] = useState<PagedResult<SalesRow> | null>(null);
  const [adsData, setAdsData] = useState<PagedResult<AdsRow> | null>(null);
  const [invData, setInvData] = useState<PagedResult<InventoryRow> | null>(null);
  const [metricsData, setMetricsData] = useState<MetricsResult | null>(null);

  useEffect(() => {
    apiFetch<StoreOption[]>(`${API_BASE}/stores`).then(setStores).catch(() => {});
  }, []);

  const loadData = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const qs = () =>
        `date=${targetDate}&store_id=${encodeURIComponent(storeId)}&keyword=${encodeURIComponent(keyword)}&page=${page}&page_size=${PAGE_SIZE}`;

      if (tab === 0) {
        const res = await apiFetch<{ date: string; sales: SalesSummary[]; ads: AdSummary[] }>(
          `${API_BASE}/summary?date=${targetDate}`,
        );
        setSalesSummary(res.sales);
        setAdSummary(res.ads);
      } else if (tab === 1) {
        setSalesData(await apiFetch<PagedResult<SalesRow>>(`${API_BASE}/sales?${qs()}`));
      } else if (tab === 2) {
        setAdsData(await apiFetch<PagedResult<AdsRow>>(`${API_BASE}/ads?${qs()}`));
      } else if (tab === 3) {
        setInvData(await apiFetch<PagedResult<InventoryRow>>(`${API_BASE}/inventory?${qs()}`));
      } else {
        setMetricsData(await apiFetch<MetricsResult>(
          `${API_BASE}/daily-metrics?date=${targetDate}&store_id=${encodeURIComponent(storeId)}&keyword=${encodeURIComponent(keyword)}&page=${page}&page_size=${PAGE_SIZE}`,
        ));
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, [tab, targetDate, storeId, keyword, page]);

  useEffect(() => { loadData(); }, [loadData]);

  function handleSearch() { setKeyword(inputKw); setPage(1); }
  function handleTabChange(i: number) { setTab(i); setPage(1); setKeyword(""); setInputKw(""); }

  const summaryContent = (
    <div>
      <div style={{ fontWeight: 700, marginBottom: 8 }}>销售汇总</div>
      <DataTable
        headers={["店铺", "SKU数", "总销量", "总销售额($)"]}
        rows={salesSummary.map(r => [r.store_name, r.sku_count, fmtNum(r.total_qty), fmtNum(r.total_amount, 2)])}
      />
      <div style={{ fontWeight: 700, margin: "20px 0 8px" }}>广告汇总</div>
      <DataTable
        headers={["店铺", "广告花费($)", "曝光", "点击", "广告订单", "广告销售额($)"]}
        rows={adSummary.map(r => [r.store_name, fmtNum(r.total_spend, 2), fmtNum(r.total_impressions), fmtNum(r.total_clicks), fmtNum(r.total_orders), fmtNum(r.total_ad_sales, 2)])}
      />
    </div>
  );

  const salesContent = salesData && (
    <>
      <DataTable
        headers={["店铺", "ItemID", "MSKU", "SKU", "负责人", "销量", "订单数", "销售额($)"]}
        rows={salesData.rows.map(r => [r.store_name, <ItemIdLink itemId={r.item_id} />, r.msku, r.sku, r.owner, fmtNum(r.sales_qty), fmtNum(r.order_count), fmtNum(r.sales_amount, 2)])}
      />
      <Pagination total={salesData.total} page={page} pageSize={PAGE_SIZE} onPage={setPage} />
    </>
  );

  const adsContent = adsData && (
    <>
      <DataTable
        headers={["店铺", "ItemID", "MSKU", "负责人", "广告活动", "类型", "广告组", "曝光", "点击", "CTR", "花费($)", "订单", "广告销售($)", "ACOS", "CPC($)", "ROAS"]}
        rows={adsData.rows.map(r => [
          r.store_name, <ItemIdLink itemId={r.item_id} />, r.msku, r.owner, r.campaign_name, r.campaign_type, r.ad_group_name,
          fmtNum(r.impressions), fmtNum(r.clicks), fmtPct(r.ctr),
          fmtNum(r.ad_spend, 2), fmtNum(r.orders),
          fmtNum(r.total_sales, 2), fmtPct(r.acos),
          fmtNum(r.cpc, 4), fmtNum(r.roas, 2),
        ])}
      />
      <Pagination total={adsData.total} page={page} pageSize={PAGE_SIZE} onPage={setPage} />
    </>
  );

  const invContent = invData && (
    <>
      <DataTable
        headers={["店铺", "ItemID", "MSKU", "SKU", "负责人", "可售库存", "WFS库存", "仓库库存", "在途库存", "预留库存", "库存天数"]}
        rows={invData.rows.map(r => [
          r.store_name, <ItemIdLink itemId={r.item_id} />, r.msku, r.sku, r.owner,
          fmtNum(r.available_stock), fmtNum(r.wfs_available_stock),
          fmtNum(r.warehouse_stock), fmtNum(r.inbound_stock),
          fmtNum(r.reserved_stock),
          r.stock_days != null ? fmtNum(r.stock_days, 1) : "—",
        ])}
      />
      <Pagination total={invData.total} page={page} pageSize={PAGE_SIZE} onPage={setPage} />
    </>
  );

  const metricsContent = metricsData && (
    <>
      <DataTable
        headers={["日期", "店铺", "ItemID", "MSKU", "负责人", "销量", "销售额($)", "广告费($)", "广告占比", "WFS配送费($)", "佣金率", "采购成本(¥)", "头程成本(¥)", "毛利润($)", "毛利率", "WFS库存", "库存天数"]}
        rows={metricsData.rows.map(r => [
          r.stat_date,
          r.store_name,
          <ItemIdLink itemId={r.item_id} />,
          r.msku,
          r.owner || "—",
          fmtNum(r.sales_qty),
          fmtNum(r.sales_amount, 2),
          fmtNum(r.ad_spend, 2),
          fmtPct(r.ad_ratio),
          fmtNum(r.delivery_fee, 2),
          fmtPct(r.commission_rate),
          fmtNum(r.purchase_cost, 2),
          fmtNum(r.first_mile_shipping_cost, 2),
          fmtNum(r.gross_profit, 2),
          fmtPct(r.gross_margin),
          fmtNum(r.wfs_available_stock),
          r.stock_days != null ? fmtNum(r.stock_days, 1) : "—",
        ])}
      />
      <Pagination total={metricsData.total} page={page} pageSize={PAGE_SIZE} onPage={setPage} />
    </>
  );

  const contents = [summaryContent, salesContent, adsContent, invContent, metricsContent];

  return (
    <div style={{ padding: 20, fontFamily: "system-ui, sans-serif", color: "#1a1a2e", minHeight: "100vh", background: "#f5f6fa" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16 }}>
        <h2 style={{ margin: 0, fontSize: 20, fontWeight: 700 }}>领星每日销售数据</h2>
        <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
          <input type="date" value={targetDate} onChange={e => { setTargetDate(e.target.value); setPage(1); }}
            style={{ padding: "6px 10px", borderRadius: 6, border: "1px solid #e5e7eb", fontSize: 14 }} />
          <select value={storeId} onChange={e => { setStoreId(e.target.value); setPage(1); }}
            style={{ padding: "6px 10px", borderRadius: 6, border: "1px solid #e5e7eb", fontSize: 14 }}>
            <option value="">全部店铺</option>
            {stores.map(s => <option key={s.store_id} value={s.store_id}>{s.store_name}</option>)}
          </select>
        </div>
      </div>

      <div style={{ display: "flex", gap: 4, marginBottom: 16, borderBottom: "2px solid #e5e7eb" }}>
        {TABS.map((label, i) => (
          <button key={i} onClick={() => handleTabChange(i)}
            style={{ padding: "8px 16px", cursor: "pointer", border: "none", background: "none", fontSize: 14,
              fontWeight: tab === i ? 700 : 400, color: tab === i ? "#6366f1" : "#6b7280",
              borderBottom: tab === i ? "2px solid #6366f1" : "2px solid transparent",
              marginBottom: -2, borderRadius: "4px 4px 0 0" }}>
            {label}
          </button>
        ))}
      </div>

      {tab > 0 && (
        <div style={{ display: "flex", gap: 8, marginBottom: 12 }}>
          <input style={{ flex: 1, padding: "7px 12px", borderRadius: 6, border: "1px solid #e5e7eb", fontSize: 14 }}
            placeholder="ItemID / MSKU / 广告活动名..."
            value={inputKw} onChange={e => setInputKw(e.target.value)}
            onKeyDown={e => e.key === "Enter" && handleSearch()} />
          <button onClick={handleSearch} style={{ padding: "7px 16px", borderRadius: 6, border: "none", background: "#6366f1", color: "#fff", cursor: "pointer", fontSize: 14 }}>搜索</button>
          {keyword && <button onClick={() => { setKeyword(""); setInputKw(""); setPage(1); }}
            style={{ padding: "7px 16px", borderRadius: 6, border: "none", background: "#6b7280", color: "#fff", cursor: "pointer", fontSize: 14 }}>清除</button>}
        </div>
      )}

      <div style={{ background: "#fff", borderRadius: 12, padding: 16, boxShadow: "0 1px 4px rgba(0,0,0,0.08)" }}>
        {loading && <div style={{ textAlign: "center", color: "#9ca3af", padding: "40px 0" }}>加载中...</div>}
        {!loading && error && <div style={{ color: "#dc2626", padding: "20px 0" }}>⚠️ {error}</div>}
        {!loading && !error && contents[tab]}
      </div>
    </div>
  );
}
