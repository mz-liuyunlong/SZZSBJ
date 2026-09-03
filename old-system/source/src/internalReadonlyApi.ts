/**
 * internalReadonlyApi.ts
 *
 * Internal readonly data API for coworkers.
 * - Auth: Authorization: Bearer ${INTERNAL_READONLY_API_TOKEN}
 * - Allows only whitelisted GET endpoints.
 * - Blocks write/sync/import/upload/update/delete routes with 403 after auth.
 * - Never executes caller-provided SQL.
 */

import { Router, Request, Response, NextFunction } from "express";
import * as mysql from "mysql2/promise";

const router = Router();
const DEFAULT_PAGE_SIZE = 50;
const MAX_PAGE_SIZE = 500;

type QueryParam = string | number;
type RowObject = Record<string, unknown>;

interface PageInput {
  page: number;
  pageSize: number;
  offset: number;
}

interface DateFilter {
  sql: string;
  params: QueryParam[];
  note: "single" | "range" | "default_recent_7_days";
}

function getDb(): Promise<mysql.Connection> {
  return mysql.createConnection({
    host: process.env.READONLY_DB_HOST ?? process.env.DB_HOST ?? "127.0.0.1",
    port: Number(process.env.READONLY_DB_PORT ?? process.env.DB_PORT ?? 3306),
    user: process.env.READONLY_DB_USER ?? process.env.DB_USER ?? "",
    password: process.env.READONLY_DB_PASSWORD ?? process.env.DB_PASSWORD ?? "",
    database: process.env.READONLY_DB_NAME ?? process.env.DB_NAME ?? "walmart_ai_data",
    dateStrings: true,
  });
}

function readBearerToken(req: Request): string {
  const auth = req.headers.authorization ?? "";
  return auth.startsWith("Bearer ") ? auth.slice(7).trim() : "";
}

function isWriteLikePath(path: string): boolean {
  // /lingxing-sales/sync-tasks 是只读查询接口，虽含 "sync-" 但非写类路径，显式豁免，避免被只读网关误判为写类而 403。
  // 兼容 adminServer 双挂载：根挂载 app.use("/") 命中时 req.path 带 /api/internal-readonly 前缀，两种形态都豁免。
  if (
    path === "/lingxing-sales/sync-tasks" ||
    path === "/api/internal-readonly/lingxing-sales/sync-tasks"
  ) {
    return false;
  }
  return (
    path === "/lingxing-sales/sync-daily" ||
    path.startsWith("/sync/") ||
    path === "/sync" ||
    path.startsWith("/import/") ||
    path === "/import" ||
    path.startsWith("/upload/") ||
    path === "/upload" ||
    /(^|\/)(sync|delete|update)(-|\/|$)/i.test(path)
  );
}

function isReadonlyApiPath(path: string): boolean {
  return (
    path === "/lingxing-sales/daily-overview" ||
    path === "/lingxing-sales/sync-tasks" ||
    path === "/ads/product-daily" ||
    path === "/ads/keyword-daily" ||
    path === "/inventory/daily" ||
    path === "/products" ||
    path === "/owners" ||
    path === "/keywords" ||
    path === "/events" ||
    path === "/ai-analysis" ||
    path === "/raw/feishu" ||
    path === "/raw/lingxing" ||
    path === "/walmart-ads/list" ||
    path === "/feishu-raw-sales/data" ||
    path === "/sales-detail/list" ||
    isWriteLikePath(path)
  );
}

function authReadonly(req: Request, res: Response, next: NextFunction): void {
  const expected = process.env.INTERNAL_READONLY_API_TOKEN?.trim();
  const actual = readBearerToken(req);
  const ok = Boolean(expected) && actual === expected;

  console.log(JSON.stringify({
    event: "internal_readonly_api_call",
    time: new Date().toISOString(),
    method: req.method,
    path: req.path,
    query: req.query,
    ip: req.ip,
    user_agent: req.headers["user-agent"] ?? "",
    role: ok ? "readonly_admin" : "unauthorized",
  }));

  if (!ok) {
    res.status(401).json({ error: "Unauthorized" });
    return;
  }

  if (req.method !== "GET" || isWriteLikePath(req.path)) {
    res.status(403).json({ error: "readonly_admin only allows GET readonly queries" });
    return;
  }

  next();
}

function pageInput(req: Request): PageInput {
  const page = Math.max(1, Math.floor(Number(req.query.page ?? 1)) || 1);
  const rawPageSize = Math.floor(Number(req.query.page_size ?? DEFAULT_PAGE_SIZE)) || DEFAULT_PAGE_SIZE;
  const pageSize = Math.min(MAX_PAGE_SIZE, Math.max(1, rawPageSize));
  return { page, pageSize, offset: (page - 1) * pageSize };
}

function addCommonFilters(
  req: Request,
  alias: string,
  dateColumn?: string,
  dateParam = "date",
): { conditions: string[]; params: QueryParam[] } {
  const conditions: string[] = [];
  const params: QueryParam[] = [];
  const date = String(req.query[dateParam] ?? "").trim();
  const store = String(req.query.store ?? req.query.store_name ?? "").trim();
  const storeId = String(req.query.store_id ?? "").trim();
  const itemId = String(req.query.item_id ?? "").trim();
  const msku = String(req.query.msku ?? "").trim();

  if (date && dateColumn) {
    conditions.push(`${alias}.${dateColumn} = ?`);
    params.push(date);
  }
  if (store) {
    conditions.push(`${alias}.store_name = ?`);
    params.push(store);
  }
  if (storeId) {
    conditions.push(`${alias}.store_id = ?`);
    params.push(storeId);
  }
  if (itemId) {
    conditions.push(`${alias}.item_id = ?`);
    params.push(itemId);
  }
  if (msku) {
    conditions.push(`${alias}.msku = ?`);
    params.push(msku);
  }

  return { conditions, params };
}

function whereSql(conditions: string[]): string {
  return conditions.length ? `WHERE ${conditions.join(" AND ")}` : "";
}

const RAW_UNSUPPORTED_BUSINESS_PARAMS = ["store", "store_name", "store_id", "item_id", "msku"];
function rejectRawBusinessParams(req: Request, res: Response): boolean {
  // RAW 表（raw_feishu_table / raw_lingxing_api）无 store/item/msku 独立列，业务值在 row_json/response_json 里。
  // 传这些业务列会拼出不存在的列条件而抛 Unknown column(500)。此处提前拦成 400，明确“RAW 接口不支持业务列过滤”。
  const present = RAW_UNSUPPORTED_BUSINESS_PARAMS.filter(
    (k) => String(req.query[k] ?? "").trim() !== "",
  );
  if (present.length) {
    res.status(400).json({
      error: "Unsupported query parameter for RAW endpoint",
      unsupported_params: present,
    });
    return true;
  }
  return false;
}

function queryString(req: Request, key: string): string {
  return String(req.query[key] ?? "").trim();
}

function validateDate(value: string, field: string, res: Response): boolean {
  if (!value) return true;
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) {
    res.status(400).json({ error: `Invalid ${field}`, expected: "YYYY-MM-DD" });
    return false;
  }
  return true;
}

function optionalDateRangeFilter(
  req: Request,
  res: Response,
  alias: string,
  dateColumn: string,
): { sql: string; params: QueryParam[] } | null | undefined {
  const date = queryString(req, "date");
  const dateStart = queryString(req, "date_start");
  const dateEnd = queryString(req, "date_end");

  if (
    !validateDate(dateStart, "date_start", res) ||
    !validateDate(dateEnd, "date_end", res)
  ) {
    return undefined;
  }
  if (date) {
    return null;
  }
  if (dateStart && dateEnd) {
    return { sql: `${alias}.${dateColumn} BETWEEN ? AND ?`, params: [dateStart, dateEnd] };
  }
  if (dateStart) {
    return { sql: `${alias}.${dateColumn} >= ?`, params: [dateStart] };
  }
  if (dateEnd) {
    return { sql: `${alias}.${dateColumn} <= ?`, params: [dateEnd] };
  }
  return null;
}

function parseNumberParam(req: Request, key: string, res: Response): number | undefined {
  const raw = queryString(req, key);
  if (!raw) return undefined;
  const value = Number(raw);
  if (!Number.isFinite(value)) {
    res.status(400).json({ error: `Invalid ${key}`, expected: "number" });
    return undefined;
  }
  return value;
}

function salesDetailDateFilter(req: Request, res: Response): DateFilter | undefined {
  const date = queryString(req, "date");
  const dateStart = queryString(req, "date_start");
  const dateEnd = queryString(req, "date_end");
  if (
    !validateDate(date, "date", res) ||
    !validateDate(dateStart, "date_start", res) ||
    !validateDate(dateEnd, "date_end", res)
  ) {
    return undefined;
  }
  if (date) {
    return { sql: "s.stat_date = ?", params: [date], note: "single" };
  }
  if (dateStart && dateEnd) {
    return { sql: "s.stat_date BETWEEN ? AND ?", params: [dateStart, dateEnd], note: "range" };
  }
  if (dateStart) {
    return { sql: "s.stat_date >= ?", params: [dateStart], note: "range" };
  }
  if (dateEnd) {
    return { sql: "s.stat_date <= ?", params: [dateEnd], note: "range" };
  }
  return {
    sql: "s.stat_date >= DATE_SUB(CURDATE(), INTERVAL 6 DAY)",
    params: [],
    note: "default_recent_7_days",
  };
}

function shouldRedactKey(key: string): boolean {
  return /(password|passwd|pwd|token|secret|authorization|cookie|file_path|server_path|env)/i.test(key);
}

function redactSensitivePairs(text: string): string {
  return text
    .replace(
      /("(?:app_secret|access_token|refresh_token|token|api_key|sign|authorization|cookie|password|passwd|pwd|secret)"\s*:\s*")([^"]*)(")/gi,
      '$1[REDACTED]$3',
    )
    .replace(
      /((?:app_secret|access_token|refresh_token|token|api_key|sign|authorization|cookie|password|passwd|pwd|secret)\s*[=:]\s*)([^,\s]+)/gi,
      '$1[REDACTED]',
    )
    .replace(/Bearer\s+[A-Za-z0-9._-]+/gi, "Bearer [REDACTED]");
}

function sanitizeObjectEntries(value: RowObject): RowObject {
  const out: RowObject = {};
  for (const [childKey, childValue] of Object.entries(value)) {
    out[childKey] = shouldRedactKey(childKey)
      ? "[REDACTED]"
      : sanitizeValue(childValue, childKey);
  }
  return out;
}

function sanitizeStringValue(value: string): string {
  if (/(Bearer\s+[A-Za-z0-9._-]+|access_token|refresh_token|app_secret|api_key|sign)/i.test(value)) {
    return redactSensitivePairs(value);
  }
  return value;
}

function sanitizeValue(value: unknown, key = ""): unknown {
  if (shouldRedactKey(key)) return "[REDACTED]";
  if (value instanceof Date) return value.toISOString();
  if (Object.prototype.toString.call(value) === "[object Date]") {
    return (value as Date).toISOString();
  }
  if (
    value &&
    typeof value === "object" &&
    typeof (value as { getTime?: unknown }).getTime === "function" &&
    typeof (value as { toISOString?: unknown }).toISOString === "function"
  ) {
    return (value as Date).toISOString();
  }
  if (Array.isArray(value)) return value.map((item) => sanitizeValue(item));
  if (value && typeof value === "object") {
    return sanitizeObjectEntries(value as RowObject);
  }
  if (typeof value === "string") {
    return sanitizeStringValue(value);
  }
  return value;
}

function sanitizeRow(row: mysql.RowDataPacket): RowObject {
  return sanitizeValue(row) as RowObject;
}

async function pagedQuery(
  req: Request,
  res: Response,
  countSql: string,
  dataSql: string,
  params: QueryParam[],
): Promise<void> {
  const { page, pageSize, offset } = pageInput(req);
  const db = await getDb();
  try {
    const [countRows] = await db.query<mysql.RowDataPacket[]>(countSql, params);
    const total = Number(countRows[0]?.total ?? 0);
    const [rows] = await db.query<mysql.RowDataPacket[]>(dataSql, [...params, pageSize, offset]);
    res.json({ role: "readonly_admin", total, page, page_size: pageSize, rows: rows.map(sanitizeRow) });
  } catch (e) {
    res.status(500).json({ error: "Query failed" });
    console.error("[internal-readonly] query failed:", e instanceof Error ? e.message : String(e));
  } finally {
    await db.end();
  }
}

router.use((req: Request, res: Response, next: NextFunction): void => {
  // 任务H-Stage3.1/3.2：Admin 后台自身业务路由跳过只读网关，交给后面的 Basic Auth + 业务路由处理，
  // 避免路径含 update/sync 关键词被误判为只读管辖而 401/403。
  // Stage3.2 安全边界：携带 Bearer 的请求（readonly_admin token）绝不允许进入 Admin 业务路由，直接 403，
  //   防止 readonly Bearer 直连应用端口穿透到 /api/feishu-raw-sales/* 等写接口（生产 app 层 Basic Auth 未强制）。
  //   只读 API 经 /api/internal-readonly 挂载访问，req.path 已剥离前缀，不会命中下列 /api 前缀。
  const adminBusinessPrefixes = [
    "/api/feishu-raw-sales/",
    "/api/lingxing-sales/",
    "/api/admin/",
    "/api/hr/",
    "/api/pmc/",
  ];
  const isAdminBusinessRoute = adminBusinessPrefixes.some(
    (p) => req.path.startsWith(p) || (req.originalUrl ?? "").startsWith(p),
  );
  if (isAdminBusinessRoute) {
    if (/^Bearer\s+/i.test(String(req.headers.authorization ?? ""))) {
      res.status(403).json({ error: "readonly_admin is not allowed for admin business routes" });
      return;
    }
    next("router");
    return;
  }
  const blocksAllMethods = req.method === "PUT" || req.method === "PATCH" || req.method === "DELETE";
  if (!blocksAllMethods && !isReadonlyApiPath(req.path)) {
    next("router");
    return;
  }
  next();
});

router.use(authReadonly);

router.get("/lingxing-sales/daily-overview", async (req, res) => {
  const date = String(req.query.date ?? "").trim();
  if (!date) {
    res.status(400).json({ error: "date is required" });
    return;
  }

  const { conditions, params } = addCommonFilters(req, "s", "stat_date");
  const where = whereSql(["s.platform = 'walmart'", ...conditions]);
  const adsSubquery = `
    SELECT stat_date, platform, store_id, item_id, msku, SUM(ad_spend) AS ad_spend
    FROM fact_ads_product_daily
    GROUP BY stat_date, platform, store_id, item_id, msku
  `;
  const inventorySubquery = `
    SELECT snapshot_date, platform, store_id, item_id, msku, MAX(wfs_available_stock) AS wfs_available_stock
    FROM fact_inventory_daily
    GROUP BY snapshot_date, platform, store_id, item_id, msku
  `;

  await pagedQuery(
    req,
    res,
    `SELECT COUNT(*) AS total FROM fact_sales_daily s ${where}`,
    `SELECT
       s.stat_date, s.store_name, s.item_id, s.msku, s.sales_qty,
       ROUND(s.sales_amount, 2) AS sales_amount,
       ROUND(COALESCE(a.ad_spend, 0), 2) AS ad_spend,
       COALESCE(i.wfs_available_stock, 0) AS wfs_available_stock,
       po.owner_name AS owner_name,
       c.purchase_cost, c.logistics_cost
     FROM fact_sales_daily s
     LEFT JOIN (${adsSubquery}) a
       ON a.stat_date = s.stat_date AND a.platform = s.platform
      AND a.store_id = s.store_id AND a.item_id = s.item_id AND a.msku = s.msku
     LEFT JOIN (${inventorySubquery}) i
       ON i.snapshot_date = s.stat_date AND i.platform = s.platform
      AND i.store_id = s.store_id AND i.item_id = s.item_id AND i.msku = s.msku
     LEFT JOIN dim_product_owner po
       ON po.platform = s.platform AND po.store_id = s.store_id
      AND po.item_id = s.item_id AND po.msku = s.msku AND po.status = 'active'
     LEFT JOIN dim_product_cost_config c
       ON c.platform = s.platform AND c.store_id = s.store_id
      AND c.item_id = s.item_id AND c.msku = s.msku AND c.status = 'active'
     ${where}
     ORDER BY s.sales_amount DESC, s.item_id ASC
     LIMIT ? OFFSET ?`,
    params,
  );
});

router.get("/lingxing-sales/sync-tasks", async (req, res) => {
  const { conditions, params } = addCommonFilters(req, "l", undefined);
  const status = String(req.query.status ?? "").trim();
  if (status) {
    conditions.push("l.status = ?");
    params.push(status);
  }
  const where = whereSql(conditions);
  await pagedQuery(
    req,
    res,
    `SELECT COUNT(*) AS total FROM sync_task_log l ${where}`,
    `SELECT task_id, task_name, source_system, target_table, started_at, finished_at,
            status, pulled_count, inserted_count, updated_count, failed_count, error_message
     FROM sync_task_log l
     ${where}
     ORDER BY started_at DESC
     LIMIT ? OFFSET ?`,
    params,
  );
});

router.get("/ads/product-daily", async (req, res) => {
  const { conditions, params } = addCommonFilters(req, "a", "stat_date");
  const where = whereSql(["a.platform = 'walmart'", ...conditions]);
  await pagedQuery(
    req,
    res,
    `SELECT COUNT(*) AS total FROM fact_ads_product_daily a ${where}`,
    `SELECT stat_date, store_name, advertiser_id, campaign_id, campaign_name,
            campaign_type, ad_group_id, ad_group_name, item_id, msku,
            impressions, clicks, ctr, ad_spend, orders, total_sales, acos, cpc, cvr, roas
     FROM fact_ads_product_daily a
     ${where}
     ORDER BY stat_date DESC, ad_spend DESC
     LIMIT ? OFFSET ?`,
    params,
  );
});

router.get("/walmart-ads/list", async (req, res) => {
  const { conditions, params } = addCommonFilters(req, "a", "stat_date");
  const campaignId = String(req.query.campaign_id ?? "").trim();
  const campaignName = String(req.query.campaign_name ?? "").trim();
  const adGroupId = String(req.query.ad_group_id ?? "").trim();
  const adGroupName = String(req.query.ad_group_name ?? "").trim();
  const advertiserId = String(req.query.advertiser_id ?? "").trim();

  if (campaignId) {
    conditions.push("a.campaign_id = ?");
    params.push(campaignId);
  }
  if (campaignName) {
    conditions.push("a.campaign_name LIKE ?");
    params.push(`%${campaignName}%`);
  }
  if (adGroupId) {
    conditions.push("a.ad_group_id = ?");
    params.push(adGroupId);
  }
  if (adGroupName) {
    conditions.push("a.ad_group_name LIKE ?");
    params.push(`%${adGroupName}%`);
  }
  if (advertiserId) {
    conditions.push("a.advertiser_id = ?");
    params.push(advertiserId);
  }

  const where = whereSql(["a.platform = 'walmart'", ...conditions]);
  await pagedQuery(
    req,
    res,
    `SELECT COUNT(*) AS total FROM fact_ads_product_daily a ${where}`,
    `SELECT id, stat_date, store_id, store_name, advertiser_id, campaign_id,
            campaign_name, campaign_type, ad_group_id, ad_group_name, item_id,
            msku, impressions, clicks, ctr, ad_spend, orders, total_sales,
            acos, cpc, cvr, roas, source_system, created_at, updated_at
     FROM fact_ads_product_daily a
     ${where}
     ORDER BY stat_date DESC, id DESC
     LIMIT ? OFFSET ?`,
    params,
  );
});

router.get("/ads/keyword-daily", async (req, res) => {
  const { conditions, params } = addCommonFilters(req, "k", "stat_date");
  const keyword = String(req.query.keyword ?? "").trim();
  const dateRangeFilter = optionalDateRangeFilter(req, res, "k", "stat_date");
  if (dateRangeFilter === undefined) {
    return;
  }
  if (keyword) {
    conditions.push("(k.keyword LIKE ? OR k.normalized_keyword LIKE ?)");
    params.push(`%${keyword}%`, `%${keyword.toLowerCase()}%`);
  }
  if (dateRangeFilter) {
    conditions.push(dateRangeFilter.sql);
    params.push(...dateRangeFilter.params);
  }
  const where = whereSql(["k.platform = 'walmart'", ...conditions]);
  await pagedQuery(
    req,
    res,
    `SELECT COUNT(*) AS total FROM fact_ads_keyword_daily k ${where}`,
    `SELECT stat_date, store_name, campaign_id, campaign_name, ad_group_id,
            ad_group_name, item_id, item_name, msku, keyword, normalized_keyword,
            match_type, keyword_type, impressions, clicks, ctr, ad_spend, orders,
            conversion_rate, total_sales, acos, cpc, cvr, roas, keyword_bid, source_type
     FROM fact_ads_keyword_daily k
     ${where}
     ORDER BY stat_date DESC, ad_spend DESC
     LIMIT ? OFFSET ?`,
    params,
  );
});

router.get("/inventory/daily", async (req, res) => {
  const { conditions, params } = addCommonFilters(req, "i", "snapshot_date");
  const where = whereSql(["i.platform = 'walmart'", ...conditions]);
  await pagedQuery(
    req,
    res,
    `SELECT COUNT(*) AS total FROM fact_inventory_daily i ${where}`,
    `SELECT snapshot_date, store_name, item_id, msku, sku, available_stock,
            non_wfs_available_stock, wfs_available_stock, warehouse_stock,
            inbound_stock, reserved_stock, stock_days
     FROM fact_inventory_daily i
     ${where}
     ORDER BY snapshot_date DESC, store_name ASC, item_id ASC
     LIMIT ? OFFSET ?`,
    params,
  );
});

router.get("/products", async (req, res) => {
  const { conditions, params } = addCommonFilters(req, "p", undefined);
  const owner = String(req.query.owner ?? "").trim();
  if (owner) {
    conditions.push("p.owner = ?");
    params.push(owner);
  }
  const where = whereSql(["p.platform = 'walmart'", ...conditions]);
  await pagedQuery(
    req,
    res,
    `SELECT COUNT(*) AS total FROM dim_product p ${where}`,
    `SELECT store_id, store_name, item_id, msku, sku, asin, product_name, item_name,
            category, brand, owner, status, fulfillment_type, source_system, updated_at
     FROM dim_product p
     ${where}
     ORDER BY updated_at DESC, store_name ASC, item_id ASC
     LIMIT ? OFFSET ?`,
    params,
  );
});

router.get("/owners", async (req, res) => {
  const owner = String(req.query.owner ?? req.query.owner_name ?? "").trim();
  const conditions: string[] = [];
  const params: QueryParam[] = [];
  if (owner) {
    conditions.push("o.owner_name = ?");
    params.push(owner);
  }
  const where = whereSql(conditions);
  await pagedQuery(
    req,
    res,
    `SELECT COUNT(*) AS total FROM dim_owner o ${where}`,
    `SELECT owner_id, owner_name, department, role_name, feishu_user_id, status, updated_at
     FROM dim_owner o
     ${where}
     ORDER BY owner_name ASC
     LIMIT ? OFFSET ?`,
    params,
  );
});

router.get("/keywords", async (req, res) => {
  const keyword = String(req.query.keyword ?? "").trim();
  const conditions = ["k.platform = 'walmart'"];
  const params: QueryParam[] = [];
  if (keyword) {
    conditions.push("(k.keyword_text LIKE ? OR k.normalized_keyword LIKE ?)");
    params.push(`%${keyword}%`, `%${keyword.toLowerCase()}%`);
  }
  const where = whereSql(conditions);
  await pagedQuery(
    req,
    res,
    `SELECT COUNT(*) AS total FROM dim_keyword k ${where}`,
    `SELECT keyword_id, keyword_text, normalized_keyword, keyword_type, platform,
            first_seen_at, last_seen_at, updated_at
     FROM dim_keyword k
     ${where}
     ORDER BY last_seen_at DESC, keyword_id DESC
     LIMIT ? OFFSET ?`,
    params,
  );
});

router.get("/events", async (req, res) => {
  const { conditions, params } = addCommonFilters(req, "e", "event_date");
  const eventType = String(req.query.event_type ?? "").trim();
  const status = String(req.query.status ?? "").trim();
  if (eventType) {
    conditions.push("e.event_type = ?");
    params.push(eventType);
  }
  if (status) {
    conditions.push("e.status = ?");
    params.push(status);
  }
  const where = whereSql(["e.platform = 'walmart'", ...conditions]);
  await pagedQuery(
    req,
    res,
    `SELECT COUNT(*) AS total FROM biz_event e ${where}`,
    `SELECT event_id, event_date, event_type, severity, store_id, store_name,
            item_id, msku, keyword, campaign_id, ad_group_id, owner, title,
            reason, suggestion, status, source_table, source_key, detected_by,
            created_at, updated_at, resolved_at
     FROM biz_event e
     ${where}
     ORDER BY event_date DESC, event_id DESC
     LIMIT ? OFFSET ?`,
    params,
  );
});

router.get("/ai-analysis", async (req, res) => {
  const { conditions, params } = addCommonFilters(req, "a", "analysis_date");
  const analysisType = String(req.query.analysis_type ?? "").trim();
  if (analysisType) {
    conditions.push("a.analysis_type = ?");
    params.push(analysisType);
  }
  const where = whereSql(conditions);
  await pagedQuery(
    req,
    res,
    `SELECT COUNT(*) AS total FROM ai_analysis_result a ${where}`,
    `SELECT analysis_id, analysis_date, analysis_type, platform, store_id,
            item_id, msku, keyword, model_name, prompt_version, conclusion,
            recommendation, risk_score, confidence, source_event_id, created_at
     FROM ai_analysis_result a
     ${where}
     ORDER BY analysis_date DESC, analysis_id DESC
     LIMIT ? OFFSET ?`,
    params,
  );
});

router.get("/sales-detail/list", async (req, res) => {
  const sortMap: Record<string, string> = {
    stat_date: "stat_date",
    sales_amount: "sales_amount",
    sales_qty: "sales_qty",
    ad_spend: "ad_spend",
    ad_ratio: "ad_ratio",
    gross_margin: "gross_margin",
    gross_profit: "gross_profit",
    available_stock: "available_stock",
  };
  const allowedSort = Object.keys(sortMap);
  const sortBy = queryString(req, "sort_by") || "stat_date";
  const sortDirRaw = queryString(req, "sort_dir").toLowerCase() || "desc";
  if (!sortMap[sortBy]) {
    res.status(400).json({ error: "Invalid sort_by", allowed: allowedSort });
    return;
  }
  if (sortDirRaw !== "asc" && sortDirRaw !== "desc") {
    res.status(400).json({ error: "Invalid sort_dir", allowed: ["asc", "desc"] });
    return;
  }

  const dateFilter = salesDetailDateFilter(req, res);
  if (!dateFilter) return;

  const salesAmountMin = parseNumberParam(req, "sales_amount_min", res);
  if (res.headersSent) return;
  const salesAmountMax = parseNumberParam(req, "sales_amount_max", res);
  if (res.headersSent) return;
  const ordersMin = parseNumberParam(req, "orders_min", res);
  if (res.headersSent) return;
  const ordersMax = parseNumberParam(req, "orders_max", res);
  if (res.headersSent) return;
  const grossMarginMin = parseNumberParam(req, "gross_margin_min", res);
  if (res.headersSent) return;
  const grossMarginMax = parseNumberParam(req, "gross_margin_max", res);
  if (res.headersSent) return;
  const adRatioMin = parseNumberParam(req, "ad_ratio_min", res);
  if (res.headersSent) return;
  const adRatioMax = parseNumberParam(req, "ad_ratio_max", res);
  if (res.headersSent) return;

  const baseConditions = ["s.platform = 'walmart'", dateFilter.sql];
  const baseParams: QueryParam[] = [...dateFilter.params];
  const store = queryString(req, "store") || queryString(req, "store_name");
  const storeId = queryString(req, "store_id");
  const itemId = queryString(req, "item_id");
  const sku = queryString(req, "sku");
  const msku = queryString(req, "msku");
  const owner = queryString(req, "owner");
  const lifecycleStage = queryString(req, "lifecycle_stage");
  const profitLevel = queryString(req, "profit_level");
  const productManagementStatus = queryString(req, "product_management_status");

  if (store) {
    baseConditions.push("s.store_name = ?");
    baseParams.push(store);
  }
  if (storeId) {
    baseConditions.push("s.store_id = ?");
    baseParams.push(storeId);
  }
  if (itemId) {
    baseConditions.push("s.item_id = ?");
    baseParams.push(itemId);
  }
  if (sku) {
    baseConditions.push("s.sku = ?");
    baseParams.push(sku);
  }
  if (msku) {
    baseConditions.push("s.msku = ?");
    baseParams.push(msku);
  }
  if (owner) {
    baseConditions.push("COALESCE(bs.owner, p.owner) = ?");
    baseParams.push(owner);
  }
  if (lifecycleStage) {
    baseConditions.push("bs.lifecycle_stage = ?");
    baseParams.push(lifecycleStage);
  }
  if (profitLevel) {
    baseConditions.push("bs.profit_level = ?");
    baseParams.push(profitLevel);
  }
  if (productManagementStatus && productManagementStatus !== "all") {
    baseConditions.push("p.product_management_status = ?");
    baseParams.push(productManagementStatus);
  } else if (!productManagementStatus) {
    baseConditions.push("(p.product_management_status IS NULL OR p.product_management_status <> 'archived')");
  }
  if (salesAmountMin !== undefined) {
    baseConditions.push("s.sales_amount >= ?");
    baseParams.push(salesAmountMin);
  }
  if (salesAmountMax !== undefined) {
    baseConditions.push("s.sales_amount <= ?");
    baseParams.push(salesAmountMax);
  }
  if (ordersMin !== undefined) {
    baseConditions.push("s.order_count >= ?");
    baseParams.push(ordersMin);
  }
  if (ordersMax !== undefined) {
    baseConditions.push("s.order_count <= ?");
    baseParams.push(ordersMax);
  }

  const outerConditions: string[] = [];
  const outerParams: QueryParam[] = [];
  if (grossMarginMin !== undefined) {
    outerConditions.push("gross_margin >= ?");
    outerParams.push(grossMarginMin);
  }
  if (grossMarginMax !== undefined) {
    outerConditions.push("gross_margin <= ?");
    outerParams.push(grossMarginMax);
  }
  if (adRatioMin !== undefined) {
    outerConditions.push("ad_ratio >= ?");
    outerParams.push(adRatioMin);
  }
  if (adRatioMax !== undefined) {
    outerConditions.push("ad_ratio <= ?");
    outerParams.push(adRatioMax);
  }

  const baseWhere = whereSql(baseConditions);
  const outerWhere = whereSql(outerConditions);
  const queryParams = [...baseParams, ...outerParams];
  const { page, pageSize, offset } = pageInput(req);
  const sortColumn = sortMap[sortBy];
  const sortDir = sortDirRaw.toUpperCase();
  const adsSubquery = `
    SELECT stat_date, platform, store_id, item_id,
           SUM(ad_spend) AS ad_spend,
           SUM(total_sales) AS ad_sales,
           SUM(orders) AS ad_orders
    FROM fact_ads_product_daily
    GROUP BY stat_date, platform, store_id, item_id
  `;
  const baseSql = `
    SELECT
      s.stat_date,
      s.store_id,
      s.store_name,
      s.item_id,
      COALESCE(p.sku, s.sku) AS sku,
      s.msku,
      COALESCE(NULLIF(p.product_name, ''), p.item_name, bs.item_name) AS product_name,
      COALESCE(bs.owner, p.owner) AS owner,
      s.sales_qty,
      s.sales_amount,
      a.ad_spend,
      a.ad_sales,
      a.ad_orders,
      CASE
        WHEN a.ad_spend IS NULL THEN NULL
        ELSE a.ad_spend / NULLIF(s.sales_amount, 0)
      END AS ad_ratio,
      'item_level' AS ad_metric_scope,
      pf.gross_profit,
      pf.profit_rate AS gross_margin,
      i.available_stock,
      i.wfs_available_stock,
      bs.inventory_status,
      bs.lifecycle_stage,
      bs.profit_level,
      bs.problem_tags
    FROM fact_sales_daily s
    LEFT JOIN (${adsSubquery}) a
      ON a.stat_date = s.stat_date
     AND a.platform = s.platform
     AND a.store_id = s.store_id
     AND a.item_id = s.item_id
    LEFT JOIN fact_profit_daily pf
      ON pf.stat_date = s.stat_date
     AND pf.platform = s.platform
     AND pf.store_id = s.store_id
     AND pf.item_id = s.item_id
     AND pf.msku <=> s.msku
    LEFT JOIN fact_inventory_daily i
      ON i.snapshot_date = s.stat_date
     AND i.platform = s.platform
     AND i.store_id = s.store_id
     AND i.item_id = s.item_id
     AND i.msku <=> s.msku
    LEFT JOIN dim_product p
      ON p.platform = s.platform
     AND p.store_id = s.store_id
     AND p.item_id = s.item_id
     AND p.msku <=> s.msku
    LEFT JOIN dim_product_business_state bs
      ON bs.stat_date = s.stat_date
     AND bs.platform = s.platform
     AND bs.store_id = s.store_id
     AND bs.item_id = s.item_id
     AND bs.msku <=> s.msku
    ${baseWhere}
  `;

  const db = await getDb();
  try {
    const countSql = `SELECT COUNT(*) AS total FROM (${baseSql}) sales_detail ${outerWhere}`;
    const dataSql = `
      SELECT * FROM (${baseSql}) sales_detail
      ${outerWhere}
      ORDER BY ${sortColumn} ${sortDir}, item_id ASC, msku ASC
      LIMIT ? OFFSET ?
    `;
    const [countRows] = await db.query<mysql.RowDataPacket[]>(countSql, queryParams);
    const total = Number(countRows[0]?.total ?? 0);
    const [rows] = await db.query<mysql.RowDataPacket[]>(dataSql, [...queryParams, pageSize, offset]);
    res.json({ role: "readonly_admin", total, page, page_size: pageSize, rows: rows.map(sanitizeRow) });
  } catch (e) {
    res.status(500).json({ error: "Query failed" });
    console.error("[internal-readonly] sales-detail query failed:", e instanceof Error ? e.message : String(e));
  } finally {
    await db.end();
  }
});

router.get("/raw/feishu", async (req, res) => {
  if (rejectRawBusinessParams(req, res)) return;
  const { conditions, params } = addCommonFilters(req, "r", "data_date");
  const sheetId = String(req.query.sheet_id ?? "").trim();
  if (sheetId) {
    conditions.push("r.sheet_id = ?");
    params.push(sheetId);
  }
  const where = whereSql(conditions);
  await pagedQuery(
    req,
    res,
    `SELECT COUNT(*) AS total FROM raw_feishu_table r ${where}`,
    `SELECT id, source_system, sheet_id, sheet_name, row_index, row_json,
            data_date, pulled_at, created_at, updated_at
     FROM raw_feishu_table r
     ${where}
     ORDER BY id DESC
     LIMIT ? OFFSET ?`,
    params,
  );
});

router.get("/feishu-raw-sales/data", async (req, res) => {
  if (rejectRawBusinessParams(req, res)) return;
  const { conditions, params } = addCommonFilters(req, "r", "data_date");
  const sheetId = String(req.query.sheet_id ?? "").trim();
  const sheetName = String(req.query.sheet_name ?? "").trim();
  const keyword = String(req.query.keyword ?? "").trim();
  const rowIndex = String(req.query.row_index ?? "").trim();
  const sourceSystem = String(req.query.source_system ?? "").trim();

  if (sheetId) {
    conditions.push("r.sheet_id = ?");
    params.push(sheetId);
  }
  if (sheetName) {
    conditions.push("r.sheet_name LIKE ?");
    params.push(`%${sheetName}%`);
  }
  if (keyword) {
    conditions.push("r.row_json LIKE ?");
    params.push(`%${keyword}%`);
  }
  if (rowIndex) {
    conditions.push("r.row_index = ?");
    params.push(Number(rowIndex));
  }
  if (sourceSystem) {
    conditions.push("r.source_system = ?");
    params.push(sourceSystem);
  }

  const where = whereSql(conditions);
  await pagedQuery(
    req,
    res,
    `SELECT COUNT(*) AS total FROM raw_feishu_table r ${where}`,
    `SELECT id, source_system, sheet_id, sheet_name, row_index, row_json,
            data_date, pulled_at, created_at, updated_at
     FROM raw_feishu_table r
     ${where}
     ORDER BY id DESC
     LIMIT ? OFFSET ?`,
    params,
  );
});

router.get("/raw/lingxing", async (req, res) => {
  if (rejectRawBusinessParams(req, res)) return;
  const { conditions, params } = addCommonFilters(req, "r", "data_date");
  const apiPath = String(req.query.api_path ?? "").trim();
  if (apiPath) {
    conditions.push("r.api_path = ?");
    params.push(apiPath);
  }
  const where = whereSql(conditions);
  await pagedQuery(
    req,
    res,
    `SELECT COUNT(*) AS total FROM raw_lingxing_api r ${where}`,
    `SELECT id, source_system, api_path, request_method, request_params_json,
            response_json, response_code, is_success, error_message, data_date,
            pulled_at, created_at, updated_at
     FROM raw_lingxing_api r
     ${where}
     ORDER BY id DESC
     LIMIT ? OFFSET ?`,
    params,
  );
});

router.use((_req: Request, res: Response): void => {
  res.status(404).json({ error: "Readonly API endpoint not found" });
});

export default router;
