/**
 * syncOrderProfitDaily.ts
 *
 * 订单利润 Beta：从 FACT/DIM 表生成每日订单利润 raw 快照。
 * 写入 raw_feishu_table，sheet_id=order_profit_daily。该 sheet_id 与飞书 Sheet 无关。
 *
 * 下游迁移（脱离飞书 <REDACTED_FEISHU_SHEET_ID>，产品管理 V1.2 之后）：
 * 负责人改读 dim_product.owner，WFS配送费改读 dim_product_cost_config.delivery_fee，
 * 不再 JOIN raw_feishu_table(sheet_id='<REDACTED_FEISHU_SHEET_ID>') 的旧飞书镜像数据。
 *
 * 用法：
 *   npm run sync:order-profit-daily -- --date=2026-06-26
 */

import "dotenv/config";
import * as crypto from "crypto";
import * as mysql from "mysql2/promise";

const SPREADSHEET_TOKEN = "<REDACTED_FEISHU_SPREADSHEET_TOKEN>";
const SHEET_ID = "<REDACTED_FEISHU_SHEET_ID>";
const SHEET_NAME = "订单利润";
const EXCHANGE_RATE = 6.6;

const YUESI_CS_WFS_FEE = 4;
const YUESI_CS_PURCHASE_COST = 200;
const YUESI_CS_FIRST_MILE = 1;

interface RawMetricRow extends mysql.RowDataPacket {
  stat_date: string;
  store_id: string;
  store_name: string;
  item_id: string;
  msku: string;
  sku: string;
  product_name: string;
  owner: string;
  sales_qty: number;
  sales_amount: number;
  ad_spend: number;
  wfs_stock: number;
  non_wfs_stock: number;
  wfs_fee: number;
  purchase_cost: number;
  first_mile: number;
}

interface ProfitMetrics {
  wfsFee: number;
  purchaseCost: number;
  firstMile: number;
  commissionRate: number;
  grossProfit: number;
  grossMargin: number;
  adRatio: number;
  costStatus: string;
}

function getArg(name: string): string {
  const prefix = `--${name}=`;
  const found = process.argv.slice(2).find((arg) => arg.startsWith(prefix));
  return found ? found.slice(prefix.length).trim() : "";
}

function todayChina(): string {
  const now = new Date();
  const utc = now.getTime() + now.getTimezoneOffset() * 60000;
  return new Date(utc + 8 * 3600000).toISOString().slice(0, 10);
}

function addDays(date: string, days: number): string {
  const d = new Date(`${date}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() + days);
  return d.toISOString().slice(0, 10);
}

function makeHash(...parts: string[]): string {
  return crypto.createHash("md5").update(parts.join("|")).digest("hex").slice(0, 64);
}

function dateToRowBase(date: string): number {
  // 2026-08-18 批B-9容量扩位：×1000→×10000（listing增长后单日已超1000行，×1000会溢出到邻日编码区间；
  // 全系统读方/删除方均按 row_json"日期" 工作，本编码仅写方内部防冲突用；INT上限内安全至公元2557年）
  const dayNum = Math.floor(new Date(`${date}T00:00:00Z`).getTime() / 86400000);
  return dayNum * 10000 + 1;
}

function n2(n: number): string {
  return (Number.isFinite(n) ? n : 0).toFixed(2);
}

function pct(n: number): string {
  return `${Math.round((Number.isFinite(n) ? n : 0) * 100)}%`;
}

function getCommissionRate(storeName: string): number {
  return (storeName.includes("CN2501") || storeName.includes("CN2502")) ? 0.15 : 0.12;
}

function isYuesiCs(storeName: string, msku: string): boolean {
  return storeName.includes("CN2502") && msku.toUpperCase().startsWith("CS");
}

function gradeByMargin(grossMargin: number): string {
  if (grossMargin > 0.25) return "S级【卓越款】";
  if (grossMargin >= 0.20) return "A级【稳健款】";
  if (grossMargin >= 0.15) return "B级【潜力稳健款】";
  if (grossMargin >= 0.08) return "C级【优化整改款】";
  return "D级【止损亏损款】";
}

function calcMetrics(row: RawMetricRow, totalSales: number, totalQty: number, totalAd: number): ProfitMetrics {
  const commissionRate = getCommissionRate(row.store_name);
  let wfsFee = Number(row.wfs_fee ?? 0);
  let purchaseCost = Number(row.purchase_cost ?? 0);
  let firstMile = Number(row.first_mile ?? 0);

  if (isYuesiCs(row.store_name, row.msku)) {
    wfsFee = YUESI_CS_WFS_FEE;
    purchaseCost = YUESI_CS_PURCHASE_COST;
    firstMile = YUESI_CS_FIRST_MILE;
  }

  const grossProfit = totalSales
    - totalAd
    - wfsFee * totalQty
    - totalSales * commissionRate
    - (purchaseCost + firstMile) * totalQty / EXCHANGE_RATE;

  const missing: string[] = [];
  if (purchaseCost <= 0) missing.push("缺采购成本");
  if (firstMile <= 0) missing.push("缺头程成本");
  if (wfsFee <= 0) missing.push("缺WFS配送费");

  return {
    wfsFee,
    purchaseCost,
    firstMile,
    commissionRate,
    grossProfit: Math.round(grossProfit * 100) / 100,
    grossMargin: totalSales > 0 ? Math.round(grossProfit / totalSales * 10000) / 10000 : 0,
    adRatio: totalSales > 0 ? Math.round(totalAd / totalSales * 10000) / 10000 : 0,
    costStatus: missing.length ? missing.join("/") : "完整",
  };
}

function getDb(): Promise<mysql.Connection> {
  return mysql.createConnection({
    host: process.env.DB_HOST ?? "127.0.0.1",
    port: Number(process.env.DB_PORT ?? 3306),
    user: process.env.DB_USER ?? "",
    password: process.env.DB_PASSWORD ?? "",
    database: process.env.DB_NAME ?? "walmart_ai_data",
  });
}

function costJoinSql(mskuExpr: string): string {
  return `
  LEFT JOIN (
    SELECT c.store_id,
           c.item_id,
           c.msku,
           MAX(c.purchase_cost) AS purchase_cost,
           MAX(c.first_mile_shipping_cost) AS first_mile_shipping_cost
    FROM dim_product_cost_config c
    WHERE c.platform = 'walmart'
      AND c.status = 'active'
      AND c.source_system = 'lingxing_api'
      AND c.purchase_cost IS NOT NULL
      AND c.first_mile_shipping_cost IS NOT NULL
      AND COALESCE(c.store_id, '') != ''
      AND COALESCE(c.item_id, '') != ''
      AND COALESCE(c.msku, '') != ''
      AND NOT EXISTS (
        SELECT 1
        FROM dim_product_cost_config newer
        WHERE newer.platform = 'walmart'
          AND newer.status = 'active'
          AND newer.source_system = 'lingxing_api'
          AND newer.purchase_cost IS NOT NULL
          AND newer.first_mile_shipping_cost IS NOT NULL
          AND newer.store_id = c.store_id
          AND newer.item_id = c.item_id
          AND newer.msku = c.msku
          AND (
            newer.effective_date > c.effective_date
            OR (newer.effective_date = c.effective_date AND newer.updated_at > c.updated_at)
            OR (newer.effective_date = c.effective_date AND newer.updated_at = c.updated_at AND newer.id > c.id)
          )
      )
    GROUP BY c.store_id, c.item_id, c.msku
  ) dpc_store
    ON dpc_store.store_id = base.store_id
   AND dpc_store.item_id = base.item_id
   AND dpc_store.msku = ${mskuExpr}
  LEFT JOIN (
    SELECT c.item_id,
           c.msku,
           MAX(c.purchase_cost) AS purchase_cost,
           MAX(c.first_mile_shipping_cost) AS first_mile_shipping_cost
    FROM dim_product_cost_config c
    WHERE c.platform = 'walmart'
      AND c.status = 'active'
      AND c.source_system = 'lingxing_api'
      AND c.purchase_cost IS NOT NULL
      AND c.first_mile_shipping_cost IS NOT NULL
      AND COALESCE(c.item_id, '') != ''
      AND COALESCE(c.msku, '') != ''
      AND NOT EXISTS (
        SELECT 1
        FROM dim_product_cost_config newer
        WHERE newer.platform = 'walmart'
          AND newer.status = 'active'
          AND newer.source_system = 'lingxing_api'
          AND newer.purchase_cost IS NOT NULL
          AND newer.first_mile_shipping_cost IS NOT NULL
          AND newer.item_id = c.item_id
          AND newer.msku = c.msku
          AND (
            newer.effective_date > c.effective_date
            OR (newer.effective_date = c.effective_date AND newer.updated_at > c.updated_at)
            OR (newer.effective_date = c.effective_date AND newer.updated_at = c.updated_at AND newer.id > c.id)
          )
      )
    GROUP BY c.item_id, c.msku
  ) dpc_item
    ON dpc_item.item_id = base.item_id
   AND dpc_item.msku = ${mskuExpr}
`;
}

// 下游迁移（脱离飞书 <REDACTED_FEISHU_SHEET_ID>）：WFS配送费改读 dim_product_cost_config.delivery_fee，
// 取"该字段自己的最新非空值"（不按整行 effective_date 决定，避免和 purchase_cost/first_mile 互相干扰），
// 逻辑与产品管理页面 GET /product-management 的读取口径一致。不再读 raw_feishu_table(sheet_id='<REDACTED_FEISHU_SHEET_ID>')。
function deliveryFeeJoinSql(mskuExpr: string): string {
  return `
  LEFT JOIN (
    SELECT c.store_id, c.item_id, c.msku, c.delivery_fee
    FROM dim_product_cost_config c
    WHERE c.platform = 'walmart'
      AND c.status = 'active'
      AND c.delivery_fee IS NOT NULL
      AND COALESCE(c.store_id, '') != ''
      AND COALESCE(c.item_id, '') != ''
      AND COALESCE(c.msku, '') != ''
      AND NOT EXISTS (
        SELECT 1
        FROM dim_product_cost_config newer
        WHERE newer.platform = 'walmart'
          AND newer.status = 'active'
          AND newer.delivery_fee IS NOT NULL
          AND newer.store_id = c.store_id
          AND newer.item_id = c.item_id
          AND newer.msku = c.msku
          AND (
            newer.effective_date > c.effective_date
            OR (newer.effective_date = c.effective_date AND newer.updated_at > c.updated_at)
            OR (newer.effective_date = c.effective_date AND newer.updated_at = c.updated_at AND newer.id > c.id)
          )
      )
  ) dfee_store
    ON dfee_store.store_id = base.store_id
   AND dfee_store.item_id = base.item_id
   AND dfee_store.msku = ${mskuExpr}
  LEFT JOIN (
    SELECT c.item_id, c.msku, c.delivery_fee
    FROM dim_product_cost_config c
    WHERE c.platform = 'walmart'
      AND c.status = 'active'
      AND c.delivery_fee IS NOT NULL
      AND COALESCE(c.item_id, '') != ''
      AND COALESCE(c.msku, '') != ''
      AND NOT EXISTS (
        SELECT 1
        FROM dim_product_cost_config newer
        WHERE newer.platform = 'walmart'
          AND newer.status = 'active'
          AND newer.delivery_fee IS NOT NULL
          AND newer.item_id = c.item_id
          AND newer.msku = c.msku
          AND (
            newer.effective_date > c.effective_date
            OR (newer.effective_date = c.effective_date AND newer.updated_at > c.updated_at)
            OR (newer.effective_date = c.effective_date AND newer.updated_at = c.updated_at AND newer.id > c.id)
          )
      )
  ) dfee_item
    ON dfee_item.item_id = base.item_id
   AND dfee_item.msku = ${mskuExpr}
  LEFT JOIN dim_product_wfs_fee_auto dfa
    ON dfa.platform = 'walmart'
   AND dfa.store_id = base.store_id
   AND dfa.msku = ${mskuExpr}
   AND dfa.fee IS NOT NULL
`;
}
// WFS费用自动化（2026-07-17 定稿）：dfa=结算口径自动值（每月刷新，众数），
// 优先级 自动 > 人工store > 人工item > 0；CS测品仍由下游 YUESI_CS_WFS_FEE 覆盖不受影响。

const RANGE_SQL = `
  SELECT
    DATE_FORMAT(base.stat_date, '%Y-%m-%d') AS stat_date,
    base.store_id,
    COALESCE(f.store_name, a.store_name, inv.store_name, '') AS store_name,
    base.item_id,
    COALESCE(f.msku, inv.msku, dp.msku, '') AS msku,
    COALESCE(f.sku, inv.sku, dp.sku, '') AS sku,
    COALESCE(dp.product_name, dp.item_name, '') AS product_name,
    COALESCE(dp.owner, '') AS owner,
    COALESCE(f.sales_qty, 0) AS sales_qty,
    ROUND(COALESCE(f.sales_amount, 0), 2) AS sales_amount,
    ROUND(
      COALESCE(a.ad_spend, 0) *
      CASE
        WHEN COALESCE(alloc.item_sales_amount, 0) > 0
          THEN COALESCE(f.sales_amount, 0) / alloc.item_sales_amount
        WHEN COALESCE(alloc.msku_count, 0) > 0
          THEN 1 / alloc.msku_count
        ELSE 0
      END,
      2
    ) AS ad_spend,
    COALESCE(inv.wfs_available_stock, 0) AS wfs_stock,
    GREATEST(COALESCE(inv.available_stock, 0) - COALESCE(inv.wfs_available_stock, 0), 0) AS non_wfs_stock,
    COALESCE(dfa.fee, dfee_store.delivery_fee, dfee_item.delivery_fee, 0) AS wfs_fee,
    COALESCE(dpc_store.purchase_cost, dpc_item.purchase_cost, 0) AS purchase_cost,
    COALESCE(dpc_store.first_mile_shipping_cost, dpc_item.first_mile_shipping_cost, 0) AS first_mile
  FROM (
    SELECT store_id, item_id, msku, stat_date FROM fact_sales_daily
      WHERE stat_date >= ? AND stat_date <= ? AND platform = 'walmart'
    UNION
    SELECT store_id, item_id, msku, snapshot_date AS stat_date FROM fact_inventory_daily
      WHERE snapshot_date >= ? AND snapshot_date <= ? AND platform = 'walmart'
    UNION
    SELECT p.store_id, p.item_id, p.msku, a0.stat_date
      FROM (SELECT DISTINCT store_id, item_id, stat_date FROM fact_ads_product_daily
             WHERE stat_date >= ? AND stat_date <= ? AND platform = 'walmart') a0
      JOIN dim_product p
        ON p.platform = 'walmart' AND p.store_id = a0.store_id AND p.item_id = a0.item_id
       AND COALESCE(p.msku, '') <> ''
  ) base
  LEFT JOIN fact_sales_daily f
    ON f.platform = 'walmart'
   AND f.store_id = base.store_id
   AND f.item_id = base.item_id
   AND COALESCE(f.msku, '') = COALESCE(base.msku, '')
   AND f.stat_date = base.stat_date
  LEFT JOIN (
    SELECT store_id, item_id, stat_date,
           MAX(store_name) AS store_name,
           ROUND(SUM(ad_spend), 2) AS ad_spend
    FROM fact_ads_product_daily
    WHERE platform = 'walmart'
      AND stat_date >= ? AND stat_date <= ?
    GROUP BY store_id, item_id, stat_date
  ) a
    ON a.store_id = base.store_id
   AND a.item_id = base.item_id
   AND a.stat_date = base.stat_date
  LEFT JOIN (
    SELECT
      b.store_id,
      b.item_id,
      b.stat_date,
      SUM(COALESCE(f2.sales_amount, 0)) AS item_sales_amount,
      COUNT(DISTINCT NULLIF(b.msku, '')) AS msku_count
    FROM (
      SELECT store_id, item_id, msku, stat_date FROM fact_sales_daily
        WHERE stat_date >= ? AND stat_date <= ? AND platform = 'walmart'
      UNION
      SELECT store_id, item_id, msku, snapshot_date AS stat_date FROM fact_inventory_daily
        WHERE snapshot_date >= ? AND snapshot_date <= ? AND platform = 'walmart'
    UNION
    SELECT p.store_id, p.item_id, p.msku, b0.stat_date
      FROM (SELECT DISTINCT store_id, item_id, stat_date FROM fact_ads_product_daily
             WHERE stat_date >= ? AND stat_date <= ? AND platform = 'walmart') b0
      JOIN dim_product p
        ON p.platform = 'walmart' AND p.store_id = b0.store_id AND p.item_id = b0.item_id
       AND COALESCE(p.msku, '') <> ''
    ) b
    LEFT JOIN fact_sales_daily f2
      ON f2.platform = 'walmart'
     AND f2.store_id = b.store_id
     AND f2.item_id = b.item_id
     AND COALESCE(f2.msku, '') = COALESCE(b.msku, '')
     AND f2.stat_date = b.stat_date
    GROUP BY b.store_id, b.item_id, b.stat_date
  ) alloc
    ON alloc.store_id = base.store_id
   AND alloc.item_id = base.item_id
   AND alloc.stat_date = base.stat_date
  LEFT JOIN fact_inventory_daily inv
    ON inv.platform = 'walmart'
   AND inv.store_id = base.store_id
   AND inv.item_id = base.item_id
   AND COALESCE(inv.msku, '') = COALESCE(base.msku, '')
   AND inv.snapshot_date = base.stat_date
  LEFT JOIN dim_product dp
    ON dp.platform = 'walmart'
   AND dp.store_id = base.store_id
   AND dp.item_id = base.item_id
   AND COALESCE(dp.msku, '') = COALESCE(base.msku, '')
  ${costJoinSql("COALESCE(base.msku, '')")}
  ${deliveryFeeJoinSql("COALESCE(base.msku, '')")}
  ORDER BY base.store_id, base.item_id, base.msku, base.stat_date
`;

function keyOf(row: Pick<RawMetricRow, "store_id" | "item_id" | "msku">): string {
  return `${row.store_id}___${row.item_id}___${row.msku}`;
}

async function fetchRangeRows(db: mysql.Connection, startDate: string, endDate: string): Promise<RawMetricRow[]> {
  // 2026-07-20 base/alloc 各新增广告驱动分支（断货烧广告行可见），?对数 5→7
  const [rows] = await db.query<RawMetricRow[]>(RANGE_SQL, [
    startDate, endDate,
    startDate, endDate,
    startDate, endDate,
    startDate, endDate,
    startDate, endDate,
    startDate, endDate,
    startDate, endDate,
  ]);
  return rows;
}

function buildThirtyDayGradeMap(rows: RawMetricRow[]): Map<string, string> {
  interface Bucket {
    sample: RawMetricRow;
    qty: number;
    sales: number;
    ad: number;
  }
  const buckets = new Map<string, Bucket>();
  for (const row of rows) {
    const key = keyOf(row);
    const bucket = buckets.get(key) ?? { sample: row, qty: 0, sales: 0, ad: 0 };
    bucket.qty += Number(row.sales_qty ?? 0);
    bucket.sales += Number(row.sales_amount ?? 0);
    bucket.ad += Number(row.ad_spend ?? 0);
    buckets.set(key, bucket);
  }

  const result = new Map<string, string>();
  for (const [key, bucket] of buckets) {
    const metrics = calcMetrics(bucket.sample, bucket.sales, bucket.qty, bucket.ad);
    result.set(key, gradeByMargin(metrics.grossMargin));
  }
  return result;
}

async function insertRows(
  db: mysql.Connection,
  targetDate: string,
  rows: Record<string, string>[],
): Promise<number> {
  // 2026-07-31 #1-3修复：源为空不删(避免领星返空清掉当天RAW);DELETE+INSERT同事务,失败回滚防半天数据
  if (rows.length === 0) return 0;

  const pulledAt = new Date();
  const extraJson = JSON.stringify({ source: "lingxing", purpose: "order_profit_beta" });
  const baseRowIndex = dateToRowBase(targetDate);
  let inserted = 0;
  const batchSize = 200;

  await db.beginTransaction();
  try {
    await db.query(
      `DELETE FROM raw_feishu_table
       WHERE spreadsheet_token = ? AND sheet_id = ?
         AND (
           data_date = ?
           OR JSON_UNQUOTE(JSON_EXTRACT(row_json, '$."日期"')) = ?
         )`,
      [SPREADSHEET_TOKEN, SHEET_ID, targetDate, targetDate],
    );

    for (let start = 0; start < rows.length; start += batchSize) {
      const batch = rows.slice(start, start + batchSize);
      const placeholders: string[] = [];
      const values: (string | number | Date)[] = [];

      for (let i = 0; i < batch.length; i++) {
        const rowIndex = baseRowIndex + start + i;
        const rowJsonStr = JSON.stringify(batch[i]);
        const rawHash = makeHash(SPREADSHEET_TOKEN, SHEET_ID, String(rowIndex), rowJsonStr);
        placeholders.push("('lingxing', ?, ?, ?, ?, ?, ?, ?, ?, ?)");
        values.push(SPREADSHEET_TOKEN, SHEET_ID, SHEET_NAME, rowIndex, rowJsonStr, targetDate, rawHash, pulledAt, extraJson);
      }

      await db.query(
        `INSERT INTO raw_feishu_table
           (source_system, spreadsheet_token, sheet_id, sheet_name,
            row_index, row_json, data_date, raw_hash, pulled_at, extra_json)
         VALUES ${placeholders.join(", ")}`,
        values,
      );
      inserted += batch.length;
    }

    await db.commit();
  } catch (e) {
    await db.rollback();
    throw e;
  }

  return inserted;
}

async function main(): Promise<void> {
  const targetDate = getArg("date") || process.argv.slice(2).find((arg) => /^\d{4}-\d{2}-\d{2}$/.test(arg)) || todayChina();
  if (!/^\d{4}-\d{2}-\d{2}$/.test(targetDate)) {
    console.error("日期格式错误，应为 YYYY-MM-DD");
    process.exit(1);
  }

  const thirtyStart = addDays(targetDate, -29);
  console.log("订单利润 Beta 每日 raw 同步");
  console.log(`数据日期: ${targetDate}`);
  console.log(`产品等级窗口: ${thirtyStart}~${targetDate}`);

  const db = await getDb();
  try {
    const dailyRows = await fetchRangeRows(db, targetDate, targetDate);
    const thirtyRows = await fetchRangeRows(db, thirtyStart, targetDate);
    const gradeMap = buildThirtyDayGradeMap(thirtyRows);

    const outputRows = dailyRows.map((row) => {
      const metrics = calcMetrics(row, Number(row.sales_amount ?? 0), Number(row.sales_qty ?? 0), Number(row.ad_spend ?? 0));
      const wfsStock = Number(row.wfs_stock ?? 0);
      const nonWfsStock = Number(row.non_wfs_stock ?? 0);
      return {
        "日期": targetDate,
        "店铺": String(row.store_name ?? ""),
        "店铺ID": String(row.store_id ?? ""),
        "商品ID": String(row.item_id ?? ""),
        "MSKU": String(row.msku ?? ""),
        "SKU": String(row.sku ?? ""),
        "品名": String(row.product_name ?? ""),
        "负责人": String(row.owner ?? ""),
        "产品阶段": "",
        "今日销量": String(Number(row.sales_qty ?? 0)),
        "今日销售额（$）": n2(Number(row.sales_amount ?? 0)),
        "广告花费（$）": n2(Number(row.ad_spend ?? 0)),
        "WFS可售库存": String(wfsStock),
        "非WFS库存": String(nonWfsStock),
        "在途库存": "0",
        "库存状态": wfsStock > 0 ? "有库存" : "无库存",
        "WFS配送费（$）": n2(metrics.wfsFee),
        "采购成本（￥）": n2(metrics.purchaseCost),
        "头程成本（￥）": n2(metrics.firstMile),
        "成本状态": metrics.costStatus,
        "店铺佣金率": pct(metrics.commissionRate),
        "毛利润（$）": n2(metrics.grossProfit),
        "毛利率": pct(metrics.grossMargin),
        "广告占比": pct(metrics.adRatio),
        "产品等级": gradeMap.get(keyOf(row)) ?? "D级【止损亏损款】",
      };
    });

    const inserted = await insertRows(db, targetDate, outputRows);
    console.log(`写入 sheet_id=${SHEET_ID}: ${inserted} 行`);
  } finally {
    await db.end();
  }
}

main().catch((err) => {
  console.error("订单利润 Beta 同步失败:", err);
  process.exit(1);
});
