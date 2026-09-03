/**
 * lingxingDailyMetricsService.ts
 *
 * 领星每日利润指标服务
 * 数据来源：FACT 表（领星 API） + dim_product（负责人，飞书来源） + dim_product_cost_config（成本，飞书+领星）
 *
 * 计算规则：
 *   汇率       = 6.6（写死）
 *   佣金率     = CN2501-掌上便捷 / CN2502-悦斯电子 → 15%；其余（含新增店铺）→ 12%
 *   悦斯CS规则 = 店铺 CN2502-悦斯电子 且 MSKU 以 CS 开头：WFS费=$4, 采购=¥200, 头程=¥1（写死，不查表）
 *   广告占比   = ad_spend / sales_amount
 *   佣金       = sales_amount × 佣金率
 *   毛利润     = sales_amount - ad_spend - delivery_fee×sales_qty - 佣金 - (purchase_cost + first_mile)×sales_qty / 6.6
 *   毛利率     = 毛利润 / sales_amount
 */

import * as mysql from "mysql2/promise";

// ── 常量 ──────────────────────────────────────────────────────────────────────

const EXCHANGE_RATE = 6.6;
const DEFAULT_COMMISSION_RATE = 0.12;

// 悦斯 CS 产品写死成本
const YUESI_CS_WFS_FEE = 4;           // WFS配送费 $4
const YUESI_CS_PURCHASE_COST = 200;   // 采购成本 ¥200
const YUESI_CS_FIRST_MILE = 1;        // 头程成本 ¥1

// ── 类型 ──────────────────────────────────────────────────────────────────────

export interface DailyMetricsRow {
  stat_date: string;
  store_name: string;
  item_id: string;
  msku: string;
  sku: string;
  owner: string;
  sales_qty: number;
  sales_amount: number;
  ad_spend: number;
  delivery_fee: number;
  purchase_cost: number;
  first_mile_shipping_cost: number;
  available_stock: number;
  wfs_available_stock: number;
  stock_days: number | null;
  commission_rate: number;
  ad_ratio: number;
  gross_profit: number;
  gross_margin: number;
}

export interface DailyMetricsResult {
  stat_date: string;
  total: number;
  page: number;
  page_size: number;
  rows: DailyMetricsRow[];
}

export interface DailyMetricsParams {
  stat_date: string;
  store_id?: string;
  keyword?: string;
  page?: number;
  page_size?: number;
}

// ── 业务规则 ──────────────────────────────────────────────────────────────────

function getCommissionRate(storeName: string): number {
  if (
    storeName.includes("CN2501-掌上便捷") ||
    storeName.includes("CN2502-悦斯电子")
  ) {
    return 0.15;
  }
  return DEFAULT_COMMISSION_RATE;
}

function isYuesiCs(storeName: string, msku: string): boolean {
  return (
    storeName.includes("CN2502-悦斯电子") &&
    msku.toUpperCase().startsWith("CS")
  );
}

interface CalcInput {
  store_name: string;
  msku: string;
  sales_qty: number;
  sales_amount: number;
  ad_spend: number;
  delivery_fee: number | null;
  purchase_cost: number | null;
  first_mile_shipping_cost: number | null;
}

interface CalcOutput {
  commission_rate: number;
  delivery_fee: number;
  purchase_cost: number;
  first_mile_shipping_cost: number;
  ad_ratio: number;
  gross_profit: number;
  gross_margin: number;
}

function calcMetrics(input: CalcInput): CalcOutput {
  const commissionRate = getCommissionRate(input.store_name);

  // 悦斯 CS 成本写死，覆盖表中值
  let wfsFee = Number(input.delivery_fee ?? 0);
  let purchaseCost = Number(input.purchase_cost ?? 0);
  let firstMile = Number(input.first_mile_shipping_cost ?? 0);

  if (isYuesiCs(input.store_name, input.msku)) {
    wfsFee = YUESI_CS_WFS_FEE;
    purchaseCost = YUESI_CS_PURCHASE_COST;
    firstMile = YUESI_CS_FIRST_MILE;
  }

  const salesAmount = Number(input.sales_amount ?? 0);
  const adSpend = Number(input.ad_spend ?? 0);
  const salesQty = Number(input.sales_qty ?? 0);

  const commission = salesAmount * commissionRate;
  const grossProfit =
    salesAmount -
    adSpend -
    wfsFee * salesQty -
    commission -
    ((purchaseCost + firstMile) * salesQty) / EXCHANGE_RATE;

  const grossMargin = salesAmount > 0 ? grossProfit / salesAmount : 0;
  const adRatio = salesAmount > 0 ? adSpend / salesAmount : 0;

  return {
    commission_rate: commissionRate,
    delivery_fee: wfsFee,
    purchase_cost: purchaseCost,
    first_mile_shipping_cost: firstMile,
    ad_ratio: Math.round(adRatio * 10000) / 10000,
    gross_profit: Math.round(grossProfit * 100) / 100,
    gross_margin: Math.round(grossMargin * 10000) / 10000,
  };
}

// ── DB 连接 ───────────────────────────────────────────────────────────────────

function getDb(): Promise<mysql.Connection> {
  return mysql.createConnection({
    host: process.env.DB_HOST ?? "127.0.0.1",
    port: Number(process.env.DB_PORT ?? 3306),
    user: process.env.DB_USER ?? "",
    password: process.env.DB_PASSWORD ?? "",
    database: process.env.DB_NAME ?? "walmart_ai_data",
  });
}

// ── 主查询 ────────────────────────────────────────────────────────────────────

export async function queryDailyMetrics(
  params: DailyMetricsParams,
): Promise<DailyMetricsResult> {
  const {
    stat_date,
    store_id = "",
    keyword = "",
    page = 1,
    page_size = 50,
  } = params;

  const pageNum = Math.max(1, page);
  const pageSz = Math.min(200, Math.max(1, page_size));
  const offset = (pageNum - 1) * pageSz;

  // ── WHERE 条件 ───────────────────────────────────────────────────────────
  const conditions: string[] = ["f.stat_date = ?", "f.platform = 'walmart'"];
  const bindParams: (string | number)[] = [stat_date];

  if (store_id) {
    conditions.push("f.store_id = ?");
    bindParams.push(store_id);
  }
  if (keyword) {
    conditions.push("(f.item_id LIKE ? OR f.msku LIKE ?)");
    bindParams.push(`%${keyword}%`, `%${keyword}%`);
  }

  const where = conditions.join(" AND ");

  const db = await getDb();
  try {
    // ── COUNT ────────────────────────────────────────────────────────────
    const [cntRows] = await db.query<mysql.RowDataPacket[]>(
      `SELECT COUNT(*) AS total FROM fact_sales_daily f WHERE ${where}`,
      bindParams,
    );
    const total = Number((cntRows as { total: number }[])[0]?.total ?? 0);

    // ── 主查询：5 张表 JOIN ───────────────────────────────────────────────
    // ads 子查询：按 item_id+store_id+日期 SUM 广告花费（广告表有多条广告组记录）
    const [rawRows] = await db.query<mysql.RowDataPacket[]>(
      `SELECT
         DATE_FORMAT(f.stat_date, '%Y-%m-%d') AS stat_date,
         f.store_name,
         f.item_id,
         f.msku,
         COALESCE(f.sku, '')                          AS sku,
         COALESCE(dp.owner, '')                       AS owner,
         f.sales_qty,
         ROUND(f.sales_amount, 2)                     AS sales_amount,
         ROUND(COALESCE(ads.ad_spend, 0), 2)          AS ad_spend,
         COALESCE(dpc.delivery_fee, 0)                AS delivery_fee,
         COALESCE(dpc.purchase_cost, 0)               AS purchase_cost,
         COALESCE(dpc.first_mile_shipping_cost, 0)    AS first_mile_shipping_cost,
         COALESCE(inv.available_stock, 0)             AS available_stock,
         COALESCE(inv.wfs_available_stock, 0)         AS wfs_available_stock,
         inv.stock_days
       FROM fact_sales_daily f
       LEFT JOIN (
         SELECT store_id, item_id, stat_date,
                ROUND(SUM(ad_spend), 2) AS ad_spend
         FROM   fact_ads_product_daily
         WHERE  platform = 'walmart'
         GROUP  BY store_id, item_id, stat_date
       ) ads
         ON  ads.item_id   = f.item_id
         AND ads.store_id  = f.store_id
         AND ads.stat_date = f.stat_date
       LEFT JOIN fact_inventory_daily inv
         ON  inv.item_id       = f.item_id
         AND inv.store_id      = f.store_id
         AND inv.snapshot_date = f.stat_date
         AND inv.platform      = 'walmart'
       LEFT JOIN dim_product dp
         ON  dp.item_id  = f.item_id
         AND dp.store_id = f.store_id
         AND dp.platform = 'walmart'
       LEFT JOIN dim_product_cost_config dpc
         ON  dpc.item_id  = f.item_id
         AND dpc.store_id = f.store_id
         AND dpc.platform = 'walmart'
         AND dpc.status   = 'active'
       WHERE ${where}
       ORDER BY f.sales_amount DESC
       LIMIT ? OFFSET ?`,
      [...bindParams, pageSz, offset],
    );

    // ── 计算利润指标 ─────────────────────────────────────────────────────
    const rows: DailyMetricsRow[] = (rawRows as mysql.RowDataPacket[]).map(
      (r) => {
        const metrics = calcMetrics({
          store_name: String(r.store_name ?? ""),
          msku: String(r.msku ?? ""),
          sales_qty: Number(r.sales_qty ?? 0),
          sales_amount: Number(r.sales_amount ?? 0),
          ad_spend: Number(r.ad_spend ?? 0),
          delivery_fee: r.delivery_fee != null ? Number(r.delivery_fee) : null,
          purchase_cost:
            r.purchase_cost != null ? Number(r.purchase_cost) : null,
          first_mile_shipping_cost:
            r.first_mile_shipping_cost != null
              ? Number(r.first_mile_shipping_cost)
              : null,
        });

        return {
          stat_date: String(r.stat_date ?? ""),
          store_name: String(r.store_name ?? ""),
          item_id: String(r.item_id ?? ""),
          msku: String(r.msku ?? ""),
          sku: String(r.sku ?? ""),
          owner: String(r.owner ?? ""),
          sales_qty: Number(r.sales_qty ?? 0),
          sales_amount: Number(r.sales_amount ?? 0),
          ad_spend: Number(r.ad_spend ?? 0),
          delivery_fee: metrics.delivery_fee,
          purchase_cost: metrics.purchase_cost,
          first_mile_shipping_cost: metrics.first_mile_shipping_cost,
          available_stock: Number(r.available_stock ?? 0),
          wfs_available_stock: Number(r.wfs_available_stock ?? 0),
          stock_days: r.stock_days != null ? Number(r.stock_days) : null,
          commission_rate: metrics.commission_rate,
          ad_ratio: metrics.ad_ratio,
          gross_profit: metrics.gross_profit,
          gross_margin: metrics.gross_margin,
        };
      },
    );

    return { stat_date, total, page: pageNum, page_size: pageSz, rows };
  } finally {
    await db.end();
  }
}
