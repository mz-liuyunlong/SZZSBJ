/**
 * lingxingSalesRoutes.ts
 *
 * Express 路由：/api/lingxing-sales/*  （:3001 adminServer）
 * 领星每日销售数据 —— 全部读 FACT 表（领星 API 来源），明细按 item_id LEFT JOIN dim_product 带出"负责人"（飞书来源）。
 *
 *   GET  /stores                                   店铺列表
 *   GET  /summary?date=                            销售/广告 汇总
 *   GET  /sales?date=&store_id=&keyword=&page=&page_size=     销售明细（含负责人）
 *   GET  /ads?date=&store_id=&keyword=&page=&page_size=       广告明细
 *   GET  /inventory?date=&store_id=&keyword=&page=&page_size= 库存明细（含负责人）
 *   GET  /sync-logs?limit=                         领星同步日志
 *
 * 在 adminServer.ts 注册：
 *   import lingxingSalesRoutes from "./lingxingSalesRoutes";
 *   app.use("/api/lingxing-sales", lingxingSalesRoutes);
 */

import { Router, Request, Response } from "express";
import * as mysql from "mysql2/promise";
import { queryDailyMetrics } from "./services/lingxingDailyMetricsService";
import { buildDashboard, buildOwnerProducts, buildTrends } from "./services/salesDashboardService";

const router = Router();

function getDb(): Promise<mysql.Connection> {
  return mysql.createConnection({
    host:     process.env.DB_HOST     ?? "127.0.0.1",
    port:     Number(process.env.DB_PORT ?? 3306),
    user:     process.env.DB_USER     ?? "",
    password: process.env.DB_PASSWORD ?? "",
    database: process.env.DB_NAME     ?? "walmart_ai_data",
  });
}

function yesterday(): string {
  const d = new Date();
  d.setDate(d.getDate() - 1);
  return d.toISOString().slice(0, 10);
}

function toInt(v: unknown, dflt: number): number {
  const n = Number(v);
  return Number.isFinite(n) && n > 0 ? Math.floor(n) : dflt;
}

// ── GET /stores ───────────────────────────────────────────────────────────────

router.get("/stores", async (_req: Request, res: Response): Promise<void> => {
  const db = await getDb();
  try {
    const [rows] = await db.query(
      "SELECT store_id, store_name FROM dim_store WHERE platform = 'walmart' ORDER BY store_name",
    );
    res.json(rows);
  } catch (e) {
    res.status(500).json({ error: String(e) });
  } finally {
    await db.end();
  }
});

// ── GET /summary ──────────────────────────────────────────────────────────────

router.get("/summary", async (req: Request, res: Response): Promise<void> => {
  const targetDate = String(req.query.date ?? "").trim() || yesterday();
  const db = await getDb();
  try {
    const [sales] = await db.query(
      `SELECT store_name,
              COUNT(DISTINCT item_id)      AS sku_count,
              SUM(sales_qty)               AS total_qty,
              ROUND(SUM(sales_amount), 2)  AS total_amount
       FROM fact_sales_daily
       WHERE stat_date = ? AND platform = 'walmart'
       GROUP BY store_id, store_name
       ORDER BY total_amount DESC`,
      [targetDate],
    );
    const [ads] = await db.query(
      `SELECT store_name,
              ROUND(SUM(ad_spend), 2)     AS total_spend,
              SUM(impressions)            AS total_impressions,
              SUM(clicks)                 AS total_clicks,
              SUM(orders)                 AS total_orders,
              ROUND(SUM(total_sales), 2)  AS total_ad_sales
       FROM fact_ads_product_daily
       WHERE stat_date = ? AND platform = 'walmart'
       GROUP BY store_id, store_name
       ORDER BY total_spend DESC`,
      [targetDate],
    );
    res.json({ date: targetDate, sales, ads });
  } catch (e) {
    res.status(500).json({ error: String(e) });
  } finally {
    await db.end();
  }
});

// ── GET /sales ────────────────────────────────────────────────────────────────

router.get("/sales", async (req: Request, res: Response): Promise<void> => {
  const targetDate = String(req.query.date ?? "").trim() || yesterday();
  const storeId    = String(req.query.store_id ?? "").trim();
  const keyword    = String(req.query.keyword ?? "").trim();
  const page       = toInt(req.query.page, 1);
  const pageSize   = toInt(req.query.page_size, 50);
  const offset     = (page - 1) * pageSize;

  const conditions = ["f.stat_date = ?", "f.platform = 'walmart'"];
  const params: (string | number)[] = [targetDate];
  if (storeId) { conditions.push("f.store_id = ?"); params.push(storeId); }
  if (keyword) { conditions.push("(f.item_id LIKE ? OR f.msku LIKE ?)"); params.push(`%${keyword}%`, `%${keyword}%`); }
  const where = conditions.join(" AND ");

  const db = await getDb();
  try {
    const [cntRows] = await db.query(
      `SELECT COUNT(*) AS total FROM fact_sales_daily f WHERE ${where}`,
      params,
    );
    const total = (cntRows as { total: number }[])[0].total;

    const [rows] = await db.query(
      `SELECT f.store_name, f.item_id, f.msku, f.sku,
              d.owner AS owner,
              f.sales_qty, f.order_count,
              ROUND(f.sales_amount, 2) AS sales_amount
       FROM fact_sales_daily f
       LEFT JOIN dim_product d
         ON d.item_id = f.item_id AND d.store_id = f.store_id AND d.platform = 'walmart'
       WHERE ${where}
       ORDER BY f.sales_amount DESC
       LIMIT ? OFFSET ?`,
      [...params, pageSize, offset],
    );
    res.json({ total, page, page_size: pageSize, rows });
  } catch (e) {
    res.status(500).json({ error: String(e) });
  } finally {
    await db.end();
  }
});

// ── GET /ads ──────────────────────────────────────────────────────────────────

router.get("/ads", async (req: Request, res: Response): Promise<void> => {
  const targetDate = String(req.query.date ?? "").trim() || yesterday();
  const storeId    = String(req.query.store_id ?? "").trim();
  const keyword    = String(req.query.keyword ?? "").trim();
  const page       = toInt(req.query.page, 1);
  const pageSize   = toInt(req.query.page_size, 50);
  const offset     = (page - 1) * pageSize;

  const conditions = ["f.stat_date = ?", "f.platform = 'walmart'"];
  const params: (string | number)[] = [targetDate];
  if (storeId) { conditions.push("f.store_id = ?"); params.push(storeId); }
  if (keyword) { conditions.push("(f.item_id LIKE ? OR f.campaign_name LIKE ?)"); params.push(`%${keyword}%`, `%${keyword}%`); }
  const where = conditions.join(" AND ");

  const db = await getDb();
  try {
    const [cntRows] = await db.query(
      `SELECT COUNT(*) AS total FROM fact_ads_product_daily f WHERE ${where}`,
      params,
    );
    const total = (cntRows as { total: number }[])[0].total;

    const [rows] = await db.query(
      `SELECT f.store_name, f.item_id, f.msku,
              d.owner AS owner,
              f.campaign_name, f.campaign_type, f.ad_group_name,
              f.impressions, f.clicks,
              ROUND(f.ctr, 4)        AS ctr,
              ROUND(f.ad_spend, 2)   AS ad_spend,
              f.orders,
              ROUND(f.total_sales, 2) AS total_sales,
              ROUND(f.acos, 4)       AS acos,
              ROUND(f.cpc, 4)        AS cpc,
              ROUND(f.roas, 4)       AS roas
       FROM fact_ads_product_daily f
       LEFT JOIN dim_product d
         ON d.item_id = f.item_id AND d.store_id = f.store_id AND d.platform = 'walmart'
       WHERE ${where}
       ORDER BY f.ad_spend DESC
       LIMIT ? OFFSET ?`,
      [...params, pageSize, offset],
    );
    res.json({ total, page, page_size: pageSize, rows });
  } catch (e) {
    res.status(500).json({ error: String(e) });
  } finally {
    await db.end();
  }
});

// ── GET /inventory ────────────────────────────────────────────────────────────

router.get("/inventory", async (req: Request, res: Response): Promise<void> => {
  const targetDate = String(req.query.date ?? "").trim() || yesterday();
  const storeId    = String(req.query.store_id ?? "").trim();
  const keyword    = String(req.query.keyword ?? "").trim();
  const page       = toInt(req.query.page, 1);
  const pageSize   = toInt(req.query.page_size, 50);
  const offset     = (page - 1) * pageSize;

  const conditions = ["f.snapshot_date = ?", "f.platform = 'walmart'"];
  const params: (string | number)[] = [targetDate];
  if (storeId) { conditions.push("f.store_id = ?"); params.push(storeId); }
  if (keyword) { conditions.push("(f.item_id LIKE ? OR f.msku LIKE ?)"); params.push(`%${keyword}%`, `%${keyword}%`); }
  const where = conditions.join(" AND ");

  const db = await getDb();
  try {
    const [cntRows] = await db.query(
      `SELECT COUNT(*) AS total FROM fact_inventory_daily f WHERE ${where}`,
      params,
    );
    const total = (cntRows as { total: number }[])[0].total;

    const [rows] = await db.query(
      `SELECT f.store_name, f.item_id, f.msku, f.sku,
              d.owner AS owner,
              f.available_stock, f.wfs_available_stock,
              f.warehouse_stock, f.inbound_stock,
              f.reserved_stock, f.stock_days
       FROM fact_inventory_daily f
       LEFT JOIN dim_product d
         ON d.item_id = f.item_id AND d.store_id = f.store_id AND d.platform = 'walmart'
       WHERE ${where}
       ORDER BY f.store_name, f.available_stock DESC
       LIMIT ? OFFSET ?`,
      [...params, pageSize, offset],
    );
    res.json({ total, page, page_size: pageSize, rows });
  } catch (e) {
    res.status(500).json({ error: String(e) });
  } finally {
    await db.end();
  }
});

// ── GET /daily-metrics ────────────────────────────────────────────────────────
//
// 利润明细接口：销售 + 广告 + 库存 + 成本 + 负责人 → 毛利润/毛利率/广告占比
//
// 参数：
//   date       YYYY-MM-DD（必填）
//   store_id   店铺 ID（可选）
//   keyword    ItemID / MSKU 模糊搜索（可选）
//   page       页码，默认 1
//   page_size  每页条数，默认 50，最大 200

router.get("/daily-metrics", async (req: Request, res: Response): Promise<void> => {
  const stat_date = String(req.query.date ?? "").trim();
  if (!stat_date || !/^\d{4}-\d{2}-\d{2}$/.test(stat_date)) {
    res.status(400).json({ error: "缺少或格式错误的 date 参数，应为 YYYY-MM-DD" });
    return;
  }

  try {
    const result = await queryDailyMetrics({
      stat_date,
      store_id:  String(req.query.store_id  ?? "").trim(),
      keyword:   String(req.query.keyword   ?? "").trim(),
      page:      Math.max(1, Number(req.query.page      ?? 1)),
      page_size: Math.min(200, Math.max(1, Number(req.query.page_size ?? 50))),
    });
    res.json(result);
  } catch (e) {
    res.status(500).json({ error: String(e) });
  }
});

// ── GET /dashboard ────────────────────────────────────────────────────────────
//
// 产品负责人经营看板（销售驾驶舱）聚合接口 —— 只读。
// 参数（全部可选）：
//   date_from / date_to  YYYY-MM-DD；缺省时自动取最新有数据日期（不默认今天/昨天）
//   store_id             店铺筛选
//   owner                负责人筛选（含"未分配"）
//   keyword              ItemID / MSKU / SKU / 产品名 / 负责人 模糊搜索
// 返回：{ meta, cards, ownerRanking, exceptions }

const DATE_RE = /^\d{4}-\d{2}-\d{2}$/;

function dashboardParams(req: Request) {
  const df = String(req.query.date_from ?? "").trim();
  const dt = String(req.query.date_to ?? "").trim();
  return {
    date_from: DATE_RE.test(df) ? df : undefined,
    date_to: DATE_RE.test(dt) ? dt : undefined,
    store_id: String(req.query.store_id ?? "").trim() || undefined,
    owner: String(req.query.owner ?? "").trim() || undefined,
    keyword: String(req.query.keyword ?? "").trim() || undefined,
    exception_type: String(req.query.exception_type ?? "").trim() || undefined,
  };
}

router.get("/dashboard", async (req: Request, res: Response): Promise<void> => {
  try {
    res.json(await buildDashboard(dashboardParams(req)));
  } catch (e) {
    res.status(500).json({ error: String(e) });
  }
});

// ── GET /dashboard/owner-products ─────────────────────────────────────────────
//
// 负责人下钻产品明细 —— 只读。参数同 /dashboard，另支持 exception_type 过滤异常明细。
// 返回：{ meta, rows(msku级明细), ad_item_rows(ItemID级广告) }

router.get("/dashboard/owner-products", async (req: Request, res: Response): Promise<void> => {
  try {
    res.json(await buildOwnerProducts(dashboardParams(req)));
  } catch (e) {
    res.status(500).json({ error: String(e) });
  }
});

// ── GET /dashboard/trends ─────────────────────────────────────────────────────
//
// v2 趋势与环比对比 —— 只读。参数同 /dashboard，另支持：
//   compare_from / compare_to  上期范围（可选，缺省=紧邻的等长上一周期；"本月"由前端传上月同期）
// 返回：{ dateRange, companyTrend, ownerTrend, comparison, ownerRankingChanges }

router.get("/dashboard/trends", async (req: Request, res: Response): Promise<void> => {
  try {
    const cf = String(req.query.compare_from ?? "").trim();
    const ct = String(req.query.compare_to ?? "").trim();
    res.json(await buildTrends({
      ...dashboardParams(req),
      compare_from: DATE_RE.test(cf) ? cf : undefined,
      compare_to: DATE_RE.test(ct) ? ct : undefined,
    }));
  } catch (e) {
    res.status(500).json({ error: String(e) });
  }
});

// ── GET /sync-logs ────────────────────────────────────────────────────────────

router.get("/sync-logs", async (req: Request, res: Response): Promise<void> => {
  const limit = toInt(req.query.limit, 20);
  const db = await getDb();
  try {
    const [rows] = await db.query(
      `SELECT task_id, task_name, status,
              pulled_count, inserted_count, updated_count,
              started_at, finished_at, error_message, extra_json
       FROM sync_task_log
       WHERE task_name = '领星每日销售入库'
       ORDER BY started_at DESC
       LIMIT ?`,
      [limit],
    );
    res.json(rows);
  } catch (e) {
    res.status(500).json({ error: String(e) });
  } finally {
    await db.end();
  }
});

export default router;
