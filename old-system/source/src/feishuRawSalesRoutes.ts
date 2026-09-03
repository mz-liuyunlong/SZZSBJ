/**
 * feishuRawSalesRoutes.ts
 *
 * Express 路由：/api/feishu-raw-sales/*
 *   GET  /sheets          — 4 个 Sheet 概览（行数 + 最新同步时间）
 *   GET  /filter-options  — 某 Sheet 的店铺下拉选项
 *   GET  /data            — 某 Sheet 分页数据（支持关键词 + 多维度筛选）
 *   GET  /sync-tasks      — 同步任务记录
 *   POST /sync            — 已停用：不再从飞书 Sheet 手动同步
 */

import { Router, Request, Response } from "express";
import { isValidExportToken, exportMaxRows } from "./helpRoutes";
import type { AuthedRequest } from "./authMiddleware";

/**
 * 2026-08-20 需求方拍板：旧版「每日销售明细(<REDACTED_FEISHU_SHEET_ID>)」与「订单利润 Beta(order_profit_daily)」
 * 仅超级管理员可访问（V2已接棒，旧页仅留作对账）。未认证的旧 Basic Auth 通道视同超管（与WFS版块同口径）。
 * 返回 true = 已拦截（调用方应 return）。
 */
const SUPERADMIN_ONLY_SHEETS = new Set<string>(["<REDACTED_FEISHU_SHEET_ID>", "order_profit_daily"]);
function blockNonSuperadmin(req: Request, res: Response): boolean {
  const u = (req as AuthedRequest).user;
  if (!u) return false; // 未认证通道（Basic Auth 冒烟/内部脚本）不拦，与既有权限口径一致
  const isSuper = Boolean(u.isSuperadmin) || (u.roles?.has("超管") ?? false);
  if (isSuper) return false;
  res.status(403).json({ error: "该页面已限制为超级管理员可见，请使用「订单利润 V2」或「每日销售明细 V2」" });
  return true;
}
import * as mysql from "mysql2/promise";

const router = Router();

const SPREADSHEET_TOKEN = "<REDACTED_FEISHU_SPREADSHEET_TOKEN>";

const TARGET_SHEETS = [
  { sheetId: "<REDACTED_FEISHU_SHEET_ID>", sheetName: "当日数据" },
  { sheetId: "<REDACTED_FEISHU_SHEET_ID>", sheetName: "每日销售明细" },
  { sheetId: "<REDACTED_FEISHU_SHEET_ID>", sheetName: "ItemID负责人" },
  { sheetId: "<REDACTED_FEISHU_SHEET_ID>", sheetName: "近期利润与广告" },
  { sheetId: "<REDACTED_FEISHU_SHEET_ID>", sheetName: "订单利润 Beta" },
  { sheetId: "<REDACTED_FEISHU_SHEET_ID>", sheetName: "CS测品分析 Beta" },
  { sheetId: "<REDACTED_FEISHU_SHEET_ID>", sheetName: "产品管理" },
];
const OWNER_SHEET_ID = "<REDACTED_FEISHU_SHEET_ID>";
const ORDER_PROFIT_SHEET_ID = "order_profit_daily";
const CS_TEST_SHEET_ID = "cs_test_analysis";
const PRODUCT_MANAGEMENT_SHEET_ID = "product_management";
const CS_TEST_AD_START_DATE = "2026-06-01";
// 历史遗留补丁：首广在6月、非WFS库存已为0的老数据，测品结束日期统一写此日期
const CS_TEST_HISTORICAL_END_DATE = "2026-06-27";
const CS_TEST_CACHE_TTL_MS = 2 * 60 * 1000;
const CS_TEST_CACHE_MAX_ENTRIES = 50;
/** 合计行数值解析（容忍 "1,234.56"/"12.3%"/"-"，与前端展示格式互逆）2026-07-17 合计行 */
function totalsNum(v: unknown): number {
  const s = String(v ?? "").replace(/[,%$]/g, "").trim();
  if (s === "" || s === "-") return 0;
  const n = Number(s);
  return Number.isFinite(n) ? n : 0;
}

/** CS测品合计：数值列求和，比率列按汇总重算（2026-07-17 领星式合计行） */
function csTestTotals(rows: Array<Record<string, string>>): Record<string, string> {
  const sum = (key: string) => rows.reduce((acc, r) => acc + totalsNum(r[key]), 0);
  const qty = sum("累计销量");
  const sales = sum("累计销售额（$）");
  const ad = sum("累计广告费（$）");
  const imp = sum("广告曝光");
  const clicks = sum("广告点击");
  const adOrders = sum("广告订单数");
  const naturalOrders = sum("自然订单数");
  const adSales = sum("广告销售额（$）");
  const pct = (a: number, b: number) => (b > 0 ? `${(a / b * 100).toFixed(2)}%` : "-");
  return {
    "测品天数": formatNumber(sum("测品天数"), 0),
    "非WFS库存": formatNumber(sum("非WFS库存"), 0),
    "累计销量": formatNumber(qty, 0),
    "有销量天数": formatNumber(sum("有销量天数"), 0),
    "日均销量": formatNumber(sum("日均销量"), 2),
    "累计销售额（$）": formatNumber(sales, 2),
    "累计广告费（$）": formatNumber(ad, 2),
    "广告费占比": pct(ad, sales),
    "广告曝光": formatNumber(imp, 0),
    "广告点击": formatNumber(clicks, 0),
    "CTR": pct(clicks, imp),
    "CPC": clicks > 0 ? formatNumber(ad / clicks, 2) : "-",
    "CVR": pct(adOrders, clicks),
    "ACOS": pct(ad, adSales),
    "自然订单数": formatNumber(naturalOrders, 0),
    "自然订单比例": pct(naturalOrders, naturalOrders + adOrders),
    "广告订单数": formatNumber(adOrders, 0),
    "广告销售额（$）": formatNumber(adSales, 2),
    "测款成本": formatNumber(sum("测款成本"), 2),
  };
}

const CS_TEST_RESPONSE_COLUMNS = [
  "店铺", "商品ID", "MSKU", "SKU", "负责人",
  "首次广告日期", "测品结束日期", "测品天数", "非WFS库存",
  "累计销量", "有销量天数", "日均销量", "累计销售额（$）",
  "累计广告费（$）", "广告费占比", "广告曝光", "广告点击",
  "CTR", "CPC", "CVR", "ACOS", "自然订单数", "自然订单比例",
  "广告订单数", "广告销售额（$）", "测款成本", "数据状态", "预警原因",
];
const PRODUCT_MANAGEMENT_COLUMNS = [
  "店铺ID", "店铺名称", "负责人", "ItemID", "MSKU", "SKU",
  "产品名称", "产品类型", "利润等级", "产品状态", "上架时间", "系统生命周期",
  "人工生命周期", "近90天销量", "当前库存", "在途库存", "近30天广告费", "停用原因",
  "产品成本（¥）", "头程运费（¥）", "WFS配送费（$）", "操作", "GPT分析",
];

// V1.1: 负责人筛选"缺负责人"哨兵值，产品状态枚举与中文映射
const MISSING_OWNER_SENTINEL = "__missing__";

/** 多选参数解析（2026-07-17 领星式多选）：逗号分隔→数组；空值→[]；单值向后兼容 */
function parseMultiText(value: unknown): string[] {
  return String(value ?? "").split(",").map((s) => s.trim()).filter(Boolean);
}
function inPlaceholders(n: number): string {
  return Array.from({ length: n }, () => "?").join(",");
}

/**
 * 人工字段变更审计（2026-07-17，归档事故根治项）：
 * dim_product 三个人工字段（product_management_status / owner / manual_lifecycle_stage）
 * 每次人工变更写一条 biz_event 留痕（操作人、旧值、新值）。
 * 审计写入失败只告警，绝不阻断业务操作。
 */
async function auditManualChange(
  db: mysql.Connection,
  args: {
    storeId: string; itemId: string; msku: string;
    field: string; oldValue: string; newValue: string;
    operator: string; reason?: string;
  },
): Promise<void> {
  try {
    await db.query(
      `INSERT INTO biz_event
         (event_date, event_type, platform, store_id, item_id, msku, owner,
          title, reason, severity, status, source_table, source_key, detected_by, extra_json)
       VALUES (CURDATE(), 'pm_manual_change', 'walmart', ?, ?, ?, '',
               ?, ?, 'info', 'resolved', 'dim_product', ?, 'manual', CAST(? AS JSON))`,
      [args.storeId, args.itemId, args.msku,
       `${args.field}: ${args.oldValue || "(空)"} → ${args.newValue || "(空)"}`,
       args.reason ?? "",
       `${args.storeId}:${args.itemId}:${args.msku}:${args.field}:${Date.now()}`,
       JSON.stringify({
         field: args.field, old: args.oldValue, new: args.newValue,
         operator: args.operator || "admin_ui", at: new Date().toISOString(),
       })],
    );
  } catch (e) {
    console.warn("[审计] biz_event 写入失败（不阻断业务）:", e instanceof Error ? e.message : String(e));
  }
}
const PRODUCT_MANAGEMENT_STATUS_LABEL: Record<string, string> = {
  active: "在用",
  inactive_candidate: "停用候选",
  inactive: "停用",
  archived: "归档",
};
function productManagementStatusLabel(status: unknown): string {
  const s = requiredText(status) || "active";
  return PRODUCT_MANAGEMENT_STATUS_LABEL[s] ?? s;
}

interface CsTestCacheEntry {
  createdAt: number;
  rows: Record<string, string>[];
  latestSyncTime: string | null;
}

const csTestCache = new Map<string, CsTestCacheEntry>();

function getFreshCsTestCache(key: string): CsTestCacheEntry | null {
  const cached = csTestCache.get(key);
  if (!cached) return null;
  if (Date.now() - cached.createdAt > CS_TEST_CACHE_TTL_MS) {
    csTestCache.delete(key);
    return null;
  }
  return cached;
}

function setCsTestCache(key: string, entry: CsTestCacheEntry) {
  if (csTestCache.size >= CS_TEST_CACHE_MAX_ENTRIES) {
    const oldestKey = csTestCache.keys().next().value;
    if (oldestKey) csTestCache.delete(oldestKey);
  }
  csTestCache.set(key, entry);
}

// ── DB 连接工厂 ───────────────────────────────────────────────────────────────

function getDb(): Promise<mysql.Connection> {
  return mysql.createConnection({
    host:     process.env.DB_HOST     ?? "127.0.0.1",
    port:     Number(process.env.DB_PORT ?? 3306),
    user:     process.env.DB_USER     ?? "",
    password: process.env.DB_PASSWORD ?? "",
    database: process.env.DB_NAME     ?? "walmart_ai_data",
  });
}

// ── SQL 工具函数 ──────────────────────────────────────────────────────────────

/**
 * 生成 row_json 中百分比字段的 SQL 转换表达式
 * 兼容格式: "15%" / "15" / "0.15" / "-12%"
 * 统一输出百分比数值（15.0 = 15%）
 */
function jsonTextExpr(fields: string[], rowJsonRef = "row_json"): string {
  const parts = fields.map((field) => {
    const escaped = field.replace(/"/g, '\\"');
    return `NULLIF(JSON_UNQUOTE(JSON_EXTRACT(${rowJsonRef}, '$."${escaped}"')), 'null')`;
  });
  return `COALESCE(${parts.join(", ")})`;
}

function pctSqlExpr(...fields: string[]): string {
  const ex = `TRIM(${jsonTextExpr(fields)})`;
  return `(CASE
    WHEN NULLIF(${ex}, '') IS NULL THEN NULL
    WHEN ${ex} LIKE '%\\%%'
      THEN CAST(REPLACE(${ex}, '%', '') AS DECIMAL(10,4))
    WHEN ABS(CAST(${ex} AS DECIMAL(10,6))) < 2
      THEN CAST(${ex} AS DECIMAL(10,6)) * 100
    ELSE CAST(${ex} AS DECIMAL(10,4))
  END)`;
}

function jsonNumberExpr(fields: string[], rowJsonRef = "row_json"): string {
  const ex = `REPLACE(TRIM(${jsonTextExpr(fields, rowJsonRef)}), ',', '')`;
  return `(CASE
    WHEN NULLIF(${ex}, '') IS NULL THEN 0
    ELSE CAST(REPLACE(${ex}, '%', '') AS DECIMAL(18,6))
  END)`;
}

/**
 * 日期字段 SQL 表达式：兼容 "2026-06-25" / "2026/06/25" / "2026.06.25"
 * 优先读 row_json.日期，其次 .date，最后 .data_date
 */
function dateSqlExpr(): string {
  const ex = `REPLACE(REPLACE(TRIM(${jsonTextExpr(["日期", "date", "data_date"])}), '/', '-'), '.', '-')`;
  return `(CASE
    WHEN NULLIF(${ex}, '') IS NULL THEN NULL
    ELSE COALESCE(
      STR_TO_DATE(${ex}, '%Y-%m-%d'),
      STR_TO_DATE(${ex}, '%Y-%c-%e'),
      DATE(${ex})
    )
  END)`;
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

function businessAvailableDate(): string {
  return addDays(todayChina(), -3);
}

function formatNumber(value: unknown, digits = 2): string {
  const n = Number(value ?? 0);
  return Number.isFinite(n) ? n.toFixed(digits) : (0).toFixed(digits);
}

function formatPct(value: unknown): string {
  const n = Number(value ?? 0);
  return Number.isFinite(n) ? `${Math.round(n)}%` : "0%";
}

function formatPct2(value: unknown): string {
  const n = Number(value ?? 0);
  return Number.isFinite(n) ? `${n.toFixed(2)}%` : "0.00%";
}

function formatDateOnly(value: unknown): string {
  if (!value) return "";
  if (value instanceof Date && !Number.isNaN(value.getTime())) {
    const y = value.getFullYear();
    const m = String(value.getMonth() + 1).padStart(2, "0");
    const d = String(value.getDate()).padStart(2, "0");
    return `${y}-${m}-${d}`;
  }
  const text = String(value).trim();
  if (!text) return "";
  const m = text.match(/\d{4}[-/]\d{1,2}[-/]\d{1,2}/);
  if (m) {
    const [y, mo, d] = m[0].replace(/\//g, "-").split("-");
    return `${y}-${mo.padStart(2, "0")}-${d.padStart(2, "0")}`;
  }
  const parsed = new Date(text);
  if (Number.isNaN(parsed.getTime())) return text;
  const y = parsed.getFullYear();
  const mo = String(parsed.getMonth() + 1).padStart(2, "0");
  const d = String(parsed.getDate()).padStart(2, "0");
  return `${y}-${mo}-${d}`;
}

type SortOrder = "asc" | "desc";

function normalizeSortOrder(value: unknown): SortOrder | null {
  const text = String(value ?? "").trim().toLowerCase();
  if (text === "asc" || text === "desc") return text;
  return null;
}

function resolveSortSql(
  sortFieldRaw: unknown,
  sortOrderRaw: unknown,
  allowedFields: Record<string, string>,
  defaultOrderSql: string,
): string {
  const sortField = String(sortFieldRaw ?? "").trim();
  const sortOrder = normalizeSortOrder(sortOrderRaw);
  if (!sortField || !sortOrder) return defaultOrderSql;
  const sqlField = allowedFields[sortField];
  if (!sqlField) return defaultOrderSql;
  return `${sqlField} ${sortOrder.toUpperCase()}`;
}

function blankToDash(value: unknown): string {
  const text = String(value ?? "").trim();
  return text ? text : "-";
}

function requiredText(value: unknown): string {
  return String(value ?? "").trim();
}

function nullableText(value: unknown): string | null {
  const text = requiredText(value);
  return text ? text : null;
}

function parseMoney(value: unknown): number | null {
  if (value === null || value === undefined || value === "") return null;
  const n = Number(String(value).replace(/[$,]/g, "").trim());
  return Number.isFinite(n) ? n : null;
}

function productManageKey(row: mysql.RowDataPacket): Record<string, string> {
  return {
    _platform: requiredText(row.platform || "walmart"),
    _store_id: requiredText(row.store_id),
    _store_name: requiredText(row.store_name),
    _item_id: requiredText(row.item_id),
    _msku: requiredText(row.msku),
    _sku: requiredText(row.sku),
    _walmart_publish_status: requiredText(row.walmart_publish_status),
  };
}

interface DailyDetailSupplementStats {
  owner_filled: number;
  owner_unresolved: number;
  owner_ambiguous: number;
  msku_filled: number;
  msku_unresolved: number;
  msku_ambiguous: number;
}

interface StoreMapRow extends mysql.RowDataPacket {
  store_name: string;
  store_id: string;
  store_id_count: number;
}

interface ProductLookupRow extends mysql.RowDataPacket {
  store_id: string;
  item_id: string;
  msku: string;
  owner: string;
}

function lookupKey(storeId: string, itemId: string): string {
  return `${storeId}|||${itemId}`;
}

function productLookupKey(storeId: string, itemId: string, msku: string): string {
  return `${lookupKey(storeId, itemId)}|||${msku}`;
}

function uniqueNonEmpty(values: string[]): string[] {
  return Array.from(new Set(values.map((v) => requiredText(v)).filter(Boolean)));
}

async function supplementDailyDetailRows(
  db: mysql.Connection,
  rows: Record<string, string>[],
): Promise<DailyDetailSupplementStats> {
  const stats: DailyDetailSupplementStats = {
    owner_filled: 0,
    owner_unresolved: 0,
    owner_ambiguous: 0,
    msku_filled: 0,
    msku_unresolved: 0,
    msku_ambiguous: 0,
  };
  if (rows.length === 0) return stats;

  const storeNames = uniqueNonEmpty(rows.map((row) => row["店铺"] || row.store_name));
  const itemIds = uniqueNonEmpty(rows.map((row) => row["商品ID"] || row["Item ID"] || row.item_id));
  if (storeNames.length === 0 || itemIds.length === 0) {
    for (const row of rows) {
      if (!requiredText(row["负责人"])) stats.owner_unresolved++;
      if (!requiredText(row["MSKU"])) stats.msku_unresolved++;
    }
    return stats;
  }

  const [storeRows] = await db.query<StoreMapRow[]>(
    `SELECT store_name, MIN(store_id) AS store_id, COUNT(DISTINCT store_id) AS store_id_count
     FROM (
       SELECT store_id, store_name FROM dim_store WHERE platform = 'walmart'
       UNION ALL
       SELECT store_id, store_name FROM dim_store_config WHERE platform = 'walmart' AND is_active = 1
     ) s
     WHERE store_name IN (?)
     GROUP BY store_name`,
    [storeNames],
  );

  const uniqueStoreByName = new Map<string, string>();
  const ambiguousStores = new Set<string>();
  for (const row of storeRows) {
    const name = requiredText(row.store_name);
    const count = Number(row.store_id_count ?? 0);
    if (name && count === 1) uniqueStoreByName.set(name, requiredText(row.store_id));
    else if (name) ambiguousStores.add(name);
  }

  const storeIds = uniqueNonEmpty(Array.from(uniqueStoreByName.values()));
  if (storeIds.length === 0) {
    for (const row of rows) {
      const storeName = requiredText(row["店铺"] || row.store_name);
      if (!requiredText(row["负责人"])) {
        if (ambiguousStores.has(storeName)) stats.owner_ambiguous++;
        else stats.owner_unresolved++;
      }
      if (!requiredText(row["MSKU"])) {
        if (ambiguousStores.has(storeName)) stats.msku_ambiguous++;
        else stats.msku_unresolved++;
      }
    }
    return stats;
  }

  const [productRows] = await db.query<ProductLookupRow[]>(
    `SELECT store_id, item_id, msku, owner
     FROM dim_product
     WHERE platform = 'walmart'
       AND store_id IN (?)
       AND item_id IN (?)`,
    [storeIds, itemIds],
  );

  const productsByItem = new Map<string, ProductLookupRow[]>();
  const productsByFullKey = new Map<string, ProductLookupRow>();
  for (const row of productRows) {
    const storeId = requiredText(row.store_id);
    const itemId = requiredText(row.item_id);
    const msku = requiredText(row.msku);
    const key = lookupKey(storeId, itemId);
    const list = productsByItem.get(key) ?? [];
    list.push(row);
    productsByItem.set(key, list);
    if (msku) productsByFullKey.set(productLookupKey(storeId, itemId, msku), row);
  }

  for (const row of rows) {
    const storeName = requiredText(row["店铺"] || row.store_name);
    const itemId = requiredText(row["商品ID"] || row["Item ID"] || row.item_id);
    const rawMsku = requiredText(row["MSKU"] || row.msku);
    const rawOwner = requiredText(row["负责人"] || row.owner);
    const storeId = uniqueStoreByName.get(storeName) ?? "";
    const storeAmbiguous = ambiguousStores.has(storeName);
    const itemProducts = storeId && itemId ? (productsByItem.get(lookupKey(storeId, itemId)) ?? []) : [];

    if (!rawMsku) {
      if (!storeId || !itemId || itemProducts.length === 0) {
        stats.msku_unresolved++;
      } else {
        const mskuValues = uniqueNonEmpty(itemProducts.map((p) => p.msku));
        if (mskuValues.length === 1) {
          row["MSKU"] = mskuValues[0];
          stats.msku_filled++;
        } else if (mskuValues.length > 1 || storeAmbiguous) {
          stats.msku_ambiguous++;
        } else {
          stats.msku_unresolved++;
        }
      }
    }

    if (!rawOwner) {
      let ownerValues: string[] = [];
      if (storeId && itemId && rawMsku) {
        const matched = productsByFullKey.get(productLookupKey(storeId, itemId, rawMsku));
        ownerValues = matched ? uniqueNonEmpty([matched.owner]) : [];
      } else if (storeId && itemId) {
        ownerValues = uniqueNonEmpty(itemProducts.map((p) => p.owner));
      }

      if (ownerValues.length === 1) {
        row["负责人"] = ownerValues[0];
        stats.owner_filled++;
      } else if (ownerValues.length > 1 || storeAmbiguous) {
        stats.owner_ambiguous++;
      } else {
        stats.owner_unresolved++;
      }
    }
  }

  return stats;
}

function jsonArrayText(value: unknown): string {
  if (Array.isArray(value)) return value.map((item) => String(item)).filter(Boolean).join("、") || "-";
  const text = String(value ?? "").trim();
  if (!text) return "-";
  try {
    const parsed = JSON.parse(text);
    if (Array.isArray(parsed)) return parsed.map((item) => String(item)).filter(Boolean).join("、") || "-";
  } catch {
    // MySQL JSON text may already be a plain string; fall through.
  }
  return text;
}

// ── GET /sheets ───────────────────────────────────────────────────────────────

router.get("/sheets", async (_req: Request, res: Response): Promise<void> => {
  const db = await getDb();
  try {
    const sheetIds = TARGET_SHEETS.map((s) => s.sheetId);

    const [rows] = await db.query<mysql.RowDataPacket[]>(
      `SELECT
         sheet_id,
         sheet_name,
         COUNT(*) AS total,
         MAX(pulled_at) AS latest_sync_time
       FROM raw_feishu_table
       WHERE spreadsheet_token = ? AND sheet_id IN (?)
       GROUP BY sheet_id, sheet_name`,
      [SPREADSHEET_TOKEN, sheetIds],
    );

    const dataMap = new Map<string, mysql.RowDataPacket>();
    for (const r of rows) dataMap.set(r.sheet_id as string, r);

    const [csRows] = await db.query<mysql.RowDataPacket[]>(
      `SELECT
         COUNT(DISTINCT CONCAT_WS('___', store_id, item_id, msku)) AS total,
         MAX(updated_at) AS latest_sync_time
       FROM dim_product
       WHERE platform = 'walmart' AND msku LIKE 'CS%'`,
    );
    const [productRows] = await db.query<mysql.RowDataPacket[]>(
      `SELECT COUNT(*) AS total, MAX(updated_at) AS latest_sync_time
       FROM dim_product
       WHERE platform = 'walmart'`,
    );

    const result = TARGET_SHEETS.map((s) => {
      if (s.sheetId === CS_TEST_SHEET_ID) {
        return {
          sheet_id: s.sheetId,
          sheet_name: s.sheetName,
          total: csRows[0]?.total ?? 0,
          latest_sync_time: csRows[0]?.latest_sync_time ?? null,
        };
      }
      if (s.sheetId === PRODUCT_MANAGEMENT_SHEET_ID) {
        return {
          sheet_id: s.sheetId,
          sheet_name: s.sheetName,
          total: productRows[0]?.total ?? 0,
          latest_sync_time: productRows[0]?.latest_sync_time ?? null,
        };
      }
      const d = dataMap.get(s.sheetId);
      return {
        sheet_id: s.sheetId,
        sheet_name: d?.sheet_name ?? s.sheetName,
        total: d?.total ?? 0,
        latest_sync_time: d?.latest_sync_time ?? null,
      };
    });

    res.json(result);
  } catch (err) {
    res.status(500).json({ error: String(err) });
  } finally {
    await db.end();
  }
});

// ── GET /filter-options ───────────────────────────────────────────────────────

router.get("/filter-options", async (req: Request, res: Response): Promise<void> => {
  if (SUPERADMIN_ONLY_SHEETS.has(String(req.query.sheet_id ?? "").trim()) && blockNonSuperadmin(req, res)) return;
  const sheetId = String(req.query.sheet_id ?? "").trim();
  if (!sheetId) {
    res.status(400).json({ error: "缺少 sheet_id 参数" });
    return;
  }

  const db = await getDb();
  try {
    if (sheetId === "operation_log") {
      const [storeRows] = await db.query<mysql.RowDataPacket[]>(
        "SELECT DISTINCT store_name AS store FROM biz_product_operation_log WHERE platform='walmart' AND store_name<>'' ORDER BY store_name",
      );
      const [ownerRows] = await db.query<mysql.RowDataPacket[]>(
        "SELECT DISTINCT owner FROM biz_product_operation_log WHERE platform='walmart' AND owner IS NOT NULL AND owner<>'' ORDER BY owner",
      );
      const [levelRows] = await db.query<mysql.RowDataPacket[]>(
        "SELECT DISTINCT profit_level_snapshot AS lv FROM biz_product_operation_log WHERE platform='walmart' AND profit_level_snapshot IS NOT NULL AND profit_level_snapshot<>'' AND profit_level_snapshot NOT IN ('A','B','C','D') ORDER BY profit_level_snapshot",
      );
      res.json({
        stores: storeRows.map((r) => String(r.store)),
        owners: ownerRows.map((r) => String(r.owner)),
        profit_levels: levelRows.map((r) => String(r.lv)),
      });
      return;
    }
    if (sheetId === PRODUCT_MANAGEMENT_SHEET_ID) {
      const [storeRows] = await db.query<mysql.RowDataPacket[]>(
        `SELECT DISTINCT
           COALESCE(NULLIF(p.store_name, ''), NULLIF(ds.store_name, ''), NULLIF(dc.store_name, ''), p.store_id) AS store
         FROM dim_product p
         LEFT JOIN dim_store ds ON ds.store_id = p.store_id
         LEFT JOIN dim_store_config dc
           ON dc.platform = p.platform AND dc.store_id = p.store_id AND dc.is_active = 1
         WHERE p.platform = 'walmart'
         HAVING store IS NOT NULL AND store != ''
         ORDER BY store`,
      );
      const [ownerRows] = await db.query<mysql.RowDataPacket[]>(
        `SELECT DISTINCT owner
         FROM (
           SELECT p.owner COLLATE utf8mb4_unicode_ci AS owner
           FROM dim_product p
           WHERE p.platform = 'walmart'
             AND COALESCE(p.product_management_status, 'active') = 'active'
             AND p.owner IS NOT NULL AND p.owner != '' AND p.owner != '未分配'
           UNION
           SELECT m.name COLLATE utf8mb4_unicode_ci AS owner
           FROM dim_feishu_member m
           WHERE m.employment_status = 'active'
         ) x
         WHERE owner IS NOT NULL AND owner != ''
         ORDER BY owner`,
      );
      const [levelRows] = await db.query<mysql.RowDataPacket[]>(
        `SELECT DISTINCT b.profit_level AS lv
         FROM dim_product_business_state b
         JOIN (
           SELECT platform, MAX(stat_date) AS stat_date
           FROM dim_product_business_state
           WHERE platform = 'walmart'
           GROUP BY platform
         ) m ON m.platform = b.platform AND m.stat_date = b.stat_date
         WHERE b.platform = 'walmart' AND b.profit_level IS NOT NULL AND b.profit_level <> ''
         ORDER BY b.profit_level`,
      );
      res.json({
        stores: storeRows.map((r) => r.store as string),
        owners: ownerRows.map((r) => r.owner as string),
        profit_levels: levelRows.map((r) => String(r.lv)),
      });
      return;
    }

    if (sheetId === CS_TEST_SHEET_ID) {
      const [storeRows] = await db.query<mysql.RowDataPacket[]>(
        `SELECT DISTINCT store_name AS store
         FROM (
           SELECT store_name FROM dim_product WHERE platform = 'walmart' AND msku LIKE 'CS%'
           UNION
           SELECT store_name FROM fact_sales_daily WHERE platform = 'walmart' AND msku LIKE 'CS%'
           UNION
           SELECT store_name FROM fact_inventory_daily WHERE platform = 'walmart' AND msku LIKE 'CS%'
         ) x
         WHERE store_name IS NOT NULL AND store_name != ''
         ORDER BY store`,
      );
      const [ownerRows] = await db.query<mysql.RowDataPacket[]>(
        `SELECT DISTINCT owner
         FROM (
           SELECT p.owner COLLATE utf8mb4_unicode_ci AS owner
           FROM dim_product p
           WHERE p.platform = 'walmart' AND p.msku LIKE 'CS%'
             AND COALESCE(p.product_management_status, 'active') = 'active'
             AND p.owner IS NOT NULL AND p.owner != '' AND p.owner != '未分配'
           UNION
           SELECT m.name COLLATE utf8mb4_unicode_ci AS owner
           FROM dim_feishu_member m
           WHERE m.employment_status = 'active'
         ) x
         WHERE owner IS NOT NULL AND owner != ''
         ORDER BY owner`,
      );
      res.json({
        stores: storeRows.map((r) => r.store as string),
        owners: ownerRows.map((r) => r.owner as string),
      });
      return;
    }

    // 优先读 row_json.店铺，其次 .store_name；去重 + 排序 + 过滤空值
    const [storeRows] = await db.query<mysql.RowDataPacket[]>(
      `SELECT DISTINCT
         ${jsonTextExpr(["店铺", "store_name"])} AS store
       FROM raw_feishu_table
       WHERE spreadsheet_token = ? AND sheet_id = ?
       HAVING store IS NOT NULL AND store != '' AND store != 'null'
       ORDER BY store`,
      [SPREADSHEET_TOKEN, sheetId],
    );

    const [ownerRows] = await db.query<mysql.RowDataPacket[]>(
      `SELECT DISTINCT owner
       FROM (
         SELECT p.owner COLLATE utf8mb4_unicode_ci AS owner
         FROM dim_product p
         WHERE p.platform = 'walmart'
           AND COALESCE(p.product_management_status, 'active') = 'active'
           AND p.owner IS NOT NULL AND p.owner != '' AND p.owner != '未分配'
         UNION
         SELECT m.name COLLATE utf8mb4_unicode_ci AS owner
         FROM dim_feishu_member m
         WHERE m.employment_status = 'active'
       ) owner_options
       WHERE owner IS NOT NULL AND owner != '' AND owner != 'null'
       ORDER BY owner`,
      [],
    );

    res.json({
      stores: storeRows.map((r) => r.store as string),
      owners: ownerRows.map((r) => r.owner as string),
    });
  } catch (err) {
    res.status(500).json({ error: String(err) });
  } finally {
    await db.end();
  }
});

// ── Product Management ───────────────────────────────────────────────────────
// product-management 数据源为 MySQL DIM/状态表，不读取飞书 <REDACTED_FEISHU_SHEET_ID>，不写飞书。
// 仅维护 dim_product.owner、manual_lifecycle_* 与 dim_product_cost_config.delivery_fee。

// ── GET /product-management ──────────────────────────────────────────────────

router.get("/product-management", async (req: Request, res: Response): Promise<void> => {
  const page = Math.max(1, Number(req.query.page ?? 1));
  // 2026-07-20 下载导出：携带有效导出令牌时放宽单页上限（普通请求仍封顶200）
  const exportCap = isValidExportToken(String(req.query.export_token ?? "").trim()) ? exportMaxRows() : 200;
  const pageSize = Math.min(exportCap, Math.max(1, Number(req.query.page_size ?? 50)));
  const offset = (page - 1) * pageSize;
  const sortField = requiredText(req.query.sort_field);
  const sortOrder = normalizeSortOrder(req.query.sort_order);
  const keyword = requiredText(req.query.keyword);
  const sku = requiredText(req.query.sku);
  const msku = requiredText(req.query.msku);
  const itemId = requiredText(req.query.item_id);
  const storeName = requiredText(req.query.store_name);
  const storeId = requiredText(req.query.store_id);
  const owner = requiredText(req.query.owner);
  const productType = requiredText(req.query.product_type || req.query.product_stage);
  const wfsFeeStatus = requiredText(req.query.wfs_fee_status).toLowerCase();
  const pmCostStatus = requiredText(req.query.pm_cost_status).toLowerCase(); // 2026-08-03 成本状态筛选(缺产品成本/缺头程运费,派生列外层过滤)
  const pmStatusParam = requiredText(req.query.product_management_status).toLowerCase();
  const manualLifecycle = requiredText(req.query.manual_lifecycle);
  const profitLevel = requiredText(req.query.profit_level);
  const gptLinkStatus = requiredText(req.query.gpt_link_status);

  const where: string[] = ["p.platform = 'walmart'"];
  const params: (string | number)[] = [];

  if (keyword) {
    const kw = `%${keyword}%`;
    where.push(`(
      p.store_id LIKE ? OR p.store_name LIKE ? OR ds.store_name LIKE ? OR dc.store_name LIKE ? OR p.owner LIKE ? OR
      p.item_id LIKE ? OR p.msku LIKE ? OR p.sku LIKE ? OR p.product_name LIKE ? OR p.item_name LIKE ?
    )`);
    params.push(kw, kw, kw, kw, kw, kw, kw, kw, kw, kw);
  }
  if (sku) {
    where.push("p.sku LIKE ?");
    params.push(`%${sku}%`);
  }
  if (msku) {
    where.push("p.msku LIKE ?");
    params.push(`%${msku}%`);
  }
  if (itemId) {
    where.push("p.item_id LIKE ?");
    params.push(`%${itemId}%`);
  }
  {
    // 2026-07-17 多选：store_name / owner 支持逗号分隔多值；缺负责人哨兵可与具名负责人共选（OR语义）
    const storeNames = parseMultiText(storeName);
    if (storeNames.length) {
      const ph = inPlaceholders(storeNames.length);
      where.push(`(p.store_id IN (${ph}) OR p.store_name IN (${ph}) OR ds.store_name IN (${ph}) OR dc.store_name IN (${ph}))`);
      params.push(...storeNames, ...storeNames, ...storeNames, ...storeNames);
    }
  }
  if (storeId) {
    where.push("p.store_id = ?");
    params.push(storeId);
  }
  {
    const owners = parseMultiText(owner);
    const wantMissing = owners.includes(MISSING_OWNER_SENTINEL);
    const named = owners.filter((o) => o !== MISSING_OWNER_SENTINEL);
    const oc: string[] = [];
    if (wantMissing) oc.push("(p.owner IS NULL OR p.owner = '' OR p.owner = '未分配')");
    if (named.length) {
      oc.push(`p.owner IN (${inPlaceholders(named.length)})`);
      params.push(...named);
    }
    if (oc.length) where.push(`(${oc.join(" OR ")})`);
  }
  if (productType === "CS测品") {
    where.push("p.msku LIKE 'CS%'");
  } else if (productType === "常规产品") {
    where.push("(p.msku IS NULL OR p.msku NOT LIKE 'CS%')");
  }
  // 产品状态筛选。默认（参数为空）= 非归档（active+inactive_candidate+inactive），符合"归档默认隐藏"要求。
  if (pmStatusParam === "all") {
    // 不加状态条件，展示全部（含归档）
  } else if (pmStatusParam === "active" || pmStatusParam === "inactive_candidate" || pmStatusParam === "inactive" || pmStatusParam === "archived") {
    where.push("p.product_management_status = ?");
    params.push(pmStatusParam);
  } else {
    // "" 或 "non_archived" 或其他非法值一律按默认处理
    where.push("p.product_management_status <> 'archived'");
  }
  // 2026-07-25 人工生命周期筛选（__unset__ = 未设置人工值；其余精确匹配 dim_product.manual_lifecycle_stage）
  if (manualLifecycle === "__unset__") {
    where.push("(p.manual_lifecycle_stage IS NULL OR TRIM(p.manual_lifecycle_stage) = '')");
  } else if (manualLifecycle) {
    where.push("TRIM(p.manual_lifecycle_stage) = ?");
    params.push(manualLifecycle);
  }

  const whereSql = where.join(" AND ");
  const productBaseFromSql = `FROM dim_product p
       LEFT JOIN dim_store ds ON ds.store_id = p.store_id
       LEFT JOIN dim_store_config dc
         ON dc.platform = p.platform AND dc.store_id = p.store_id AND dc.is_active = 1
       LEFT JOIN dim_product_wfs_fee_auto dfa
         ON dfa.platform = 'walmart' AND dfa.store_id = p.store_id AND dfa.msku = p.msku AND dfa.fee IS NOT NULL`;
  // V1.1: WFS配送费状态需要在 delivery_fee（joins之后的派生列）上过滤，
  // 放在外层 WHERE，不能和上面按 dim_product 原始列的条件混在一起。
  const outerConditions: string[] = [];
  if (wfsFeeStatus === "missing") {
    outerConditions.push("(msku NOT LIKE 'CS%' AND (delivery_fee IS NULL OR delivery_fee <= 0))");
  } else if (wfsFeeStatus === "filled") {
    outerConditions.push("(msku LIKE 'CS%' OR (delivery_fee IS NOT NULL AND delivery_fee > 0))");
  }
  // 2026-08-03 成本状态（purchase_cost/first_mile_shipping_cost 为 join 派生列，须外层过滤）
  if (pmCostStatus === "missing_purchase") {
    outerConditions.push("(purchase_cost IS NULL)");
  } else if (pmCostStatus === "missing_first_mile") {
    outerConditions.push("(first_mile_shipping_cost IS NULL)");
  }
  // 2026-07-29 利润等级筛选（bs.profit_level 派生列，外层过滤）
  if (profitLevel) {
    outerConditions.push("profit_level = ?");
    params.push(profitLevel);
  }
  // 2026-07-29 GPT分析筛选（按"缺"维度：缺关键词/缺广告 链接）
  if (gptLinkStatus === "missing_keyword") {
    outerConditions.push("has_kw = 0");
  } else if (gptLinkStatus === "missing_ads") {
    outerConditions.push("has_ads = 0");
  }
  const outerWhereSql = outerConditions.length ? `WHERE ${outerConditions.join(" AND ")}` : "";
  const orderBySql = resolveSortSql(
    sortField,
    sortOrder,
    {
      store_name: "store_name",
      owner: "owner",
      product_type: "product_type",
      launch_date: "launch_date",
      lifecycle: "lifecycle",
      system_lifecycle: "system_lifecycle_stage",
      wfs_delivery_fee: "delivery_fee",
      purchase_cost: "purchase_cost",
      first_mile_shipping_cost: "first_mile_shipping_cost",
      updated_at: "updated_at",
    },
    "updated_at DESC, item_id ASC, msku ASC",
  );

  const coreSelectSql = `WITH latest_state AS (
         SELECT b.*
         FROM dim_product_business_state b
         JOIN (
           SELECT platform, MAX(stat_date) AS stat_date
           FROM dim_product_business_state
           WHERE platform = 'walmart'
           GROUP BY platform
         ) m ON m.platform = b.platform AND m.stat_date = b.stat_date
       ),
       latest_fee_store AS (
         SELECT platform, store_id, item_id, msku, delivery_fee
         FROM (
           SELECT c.*,
                  ROW_NUMBER() OVER (
                    PARTITION BY platform, COALESCE(store_id, ''), item_id, COALESCE(msku, '')
                    ORDER BY effective_date DESC, updated_at DESC, id DESC
                  ) AS rn
           FROM dim_product_cost_config c
           WHERE platform = 'walmart'
             AND status = 'active'
             AND delivery_fee IS NOT NULL
         ) x
         WHERE rn = 1
       ),
       latest_fee_item AS (
         SELECT platform, item_id, msku, delivery_fee
         FROM (
           SELECT c.*,
                  ROW_NUMBER() OVER (
                    PARTITION BY platform, item_id, COALESCE(msku, '')
                    ORDER BY effective_date DESC, updated_at DESC, id DESC
                  ) AS rn
           FROM dim_product_cost_config c
           WHERE platform = 'walmart'
             AND status = 'active'
             AND delivery_fee IS NOT NULL
         ) x
         WHERE rn = 1
       ),
       latest_cost_item AS (
         SELECT platform, item_id, msku, purchase_cost, first_mile_shipping_cost
         FROM (
           SELECT c.*,
                  ROW_NUMBER() OVER (
                    PARTITION BY platform, item_id, COALESCE(msku, '')
                    ORDER BY effective_date DESC, updated_at DESC, id DESC
                  ) AS rn
           FROM dim_product_cost_config c
           WHERE platform = 'walmart'
             AND status = 'active'
             AND (purchase_cost IS NOT NULL OR first_mile_shipping_cost IS NOT NULL)
         ) x
         WHERE rn = 1
       ),
       sales_90d AS (
         SELECT platform, store_id, item_id, msku, SUM(sales_qty) AS sales_qty_90d
         FROM fact_sales_daily
         WHERE platform = 'walmart'
           AND stat_date >= DATE_SUB(CURDATE(), INTERVAL 90 DAY)
         GROUP BY platform, store_id, item_id, msku
       ),
       latest_inventory AS (
         SELECT f.platform, f.store_id, f.item_id, f.msku, f.available_stock, f.inbound_stock
         FROM fact_inventory_daily f
         JOIN (
           SELECT platform, store_id, item_id, msku, MAX(snapshot_date) AS snapshot_date
           FROM fact_inventory_daily
           WHERE platform = 'walmart'
           GROUP BY platform, store_id, item_id, msku
         ) m ON m.platform = f.platform
            AND m.store_id = f.store_id
            AND m.item_id = f.item_id
            AND COALESCE(m.msku, '') = COALESCE(f.msku, '')
            AND m.snapshot_date = f.snapshot_date
       ),
       ads_30d AS (
         SELECT platform, store_id, item_id, SUM(ad_spend) AS ad_spend_30d
         FROM fact_ads_product_daily
         WHERE platform = 'walmart'
           AND stat_date >= DATE_SUB(CURDATE(), INTERVAL 30 DAY)
         GROUP BY platform, store_id, item_id
       ),
       gpt_link_flags AS (
         SELECT item_id,
                MAX(link_type = 'keyword') AS has_kw,
                MAX(link_type = 'ads') AS has_ads
         FROM dim_product_gpt_link
         WHERE platform = 'walmart'
         GROUP BY item_id
       )
       SELECT
         p.platform,
         p.store_id,
         COALESCE(NULLIF(p.store_name, ''), NULLIF(ds.store_name, ''), NULLIF(dc.store_name, ''), '') AS store_name,
         p.owner,
         p.item_id,
         p.msku,
         p.sku,
         p.product_name,
         p.item_name,
         CASE WHEN COALESCE(p.msku, '') LIKE 'CS%' THEN 'CS测品' ELSE '常规产品' END AS product_type,
         p.launch_date,
         p.product_management_status,
         p.product_management_status_source,
         p.product_management_status_reason,
         p.product_management_status_updated_at,
         p.walmart_publish_status,
         p.manual_lifecycle_stage,
         p.manual_lifecycle_by,
         p.manual_lifecycle_at,
         p.manual_lifecycle_system_snapshot,
         COALESCE(NULLIF(TRIM(p.manual_lifecycle_stage), ''), bs.lifecycle_stage, bs.system_lifecycle_stage, '') AS lifecycle,
         COALESCE(bs.system_lifecycle_stage, '') AS system_lifecycle_stage,
         EXISTS(SELECT 1 FROM event_clearance_approval eca
                WHERE eca.platform = p.platform AND eca.store_id = p.store_id
                  AND eca.item_id = p.item_id AND eca.status = 'pending') AS clearance_pending,
         COALESCE(s90.sales_qty_90d, 0) AS sales_qty_90d,
         li.available_stock,
         li.inbound_stock,
         COALESCE(a30.ad_spend_30d, 0) AS ad_spend_30d,
         COALESCE(fs.delivery_fee, fi.delivery_fee) AS delivery_fee,
         lc.purchase_cost,
         lc.first_mile_shipping_cost,
         dfa.fee AS delivery_fee_auto,
         COALESCE(bs.profit_level, '') AS profit_level,
         COALESCE(glf.has_kw, 0) AS has_kw,
         COALESCE(glf.has_ads, 0) AS has_ads,
         p.updated_at
       ${productBaseFromSql}
       LEFT JOIN latest_state bs
         ON bs.platform = p.platform
        AND bs.item_id = p.item_id
        AND COALESCE(bs.msku, '') = COALESCE(p.msku, '')
        AND (
          COALESCE(bs.store_id, '') = COALESCE(p.store_id, '')
          OR (COALESCE(p.store_id, '') = '' AND COALESCE(bs.store_name, '') = COALESCE(p.store_name, ''))
        )
       LEFT JOIN latest_fee_store fs
         ON fs.platform = p.platform
        AND COALESCE(fs.store_id, '') = COALESCE(p.store_id, '')
        AND fs.item_id = p.item_id
        AND COALESCE(fs.msku, '') = COALESCE(p.msku, '')
       LEFT JOIN latest_fee_item fi
         ON fi.platform = p.platform
        AND fi.item_id = p.item_id
        AND COALESCE(fi.msku, '') = COALESCE(p.msku, '')
       LEFT JOIN latest_cost_item lc
         ON lc.platform = p.platform
        AND lc.item_id = p.item_id
        AND COALESCE(lc.msku, '') = COALESCE(p.msku, '')
       LEFT JOIN sales_90d s90
         ON s90.platform = p.platform
        AND s90.store_id = p.store_id
        AND s90.item_id = p.item_id
        AND COALESCE(s90.msku, '') = COALESCE(p.msku, '')
       LEFT JOIN latest_inventory li
         ON li.platform = p.platform
        AND li.store_id = p.store_id
        AND li.item_id = p.item_id
        AND COALESCE(li.msku, '') = COALESCE(p.msku, '')
       LEFT JOIN ads_30d a30
         ON a30.platform = p.platform
        AND a30.store_id = p.store_id
        AND a30.item_id = p.item_id
       LEFT JOIN gpt_link_flags glf
         ON glf.item_id = p.item_id
       WHERE ${whereSql}`;

  const db = await getDb();
  try {
    const [countRows] = await db.query<mysql.RowDataPacket[]>(
      `SELECT COUNT(*) AS total FROM (${coreSelectSql}) t ${outerWhereSql}`,
      params,
    );

    const [rows] = await db.query<mysql.RowDataPacket[]>(
      `SELECT * FROM (${coreSelectSql}) t
       ${outerWhereSql}
       ORDER BY ${orderBySql}
       LIMIT ? OFFSET ?`,
      [...params, pageSize, offset],
    );

    // 2026-07-23 GPT分析链接：批量取每个 ItemID 当前最新版本（keyword/ads），失败不影响列表
    const gptLinkMap = new Map<string, { keyword?: string; ads?: string }>();
    try {
      const linkItemIds = [...new Set(rows.map((r) => requiredText(r.item_id)).filter(Boolean))];
      if (linkItemIds.length > 0) {
        const [linkRows] = await db.query<mysql.RowDataPacket[]>(
          `SELECT l.item_id, l.link_type, l.url
           FROM dim_product_gpt_link l
           JOIN (
             SELECT item_id, link_type, MAX(effective_from) AS mx
             FROM dim_product_gpt_link
             WHERE platform = 'walmart' AND item_id IN (${linkItemIds.map(() => "?").join(",")})
             GROUP BY item_id, link_type
           ) t ON t.item_id = l.item_id AND t.link_type = l.link_type AND t.mx = l.effective_from
           WHERE l.platform = 'walmart'`,
          linkItemIds,
        );
        for (const lr of linkRows) {
          const lk = String(lr.item_id);
          if (!gptLinkMap.has(lk)) gptLinkMap.set(lk, {});
          const rec = gptLinkMap.get(lk)!;
          if (String(lr.link_type) === "keyword") rec.keyword = String(lr.url);
          if (String(lr.link_type) === "ads") rec.ads = String(lr.url);
        }
      }
    } catch (gptErr) {
      console.warn("[gpt-link] 产品管理链接查询失败（忽略，不影响列表）:", gptErr instanceof Error ? gptErr.message : String(gptErr));
    }
    const mapped = rows.map((row) => {
      const keys = productManageKey(row);
      const mskuText = requiredText(row.msku);
      const itemName = requiredText(row.item_name);
      const productName = requiredText(row.product_name) || itemName;
      const manualLifecycleStage = requiredText(row.manual_lifecycle_stage);
      const lifecycleStage = requiredText(row.lifecycle);
      const systemLifecycleStage = requiredText(row.system_lifecycle_stage);
      const manualLifecycleSystemSnapshot = requiredText(row.manual_lifecycle_system_snapshot);
      const manualLifecycleDisplay = manualLifecycleStage || systemLifecycleStage || "-";
      let lifecycleHighlight = "none";
      if (manualLifecycleStage && manualLifecycleStage !== systemLifecycleStage) {
        lifecycleHighlight = !manualLifecycleSystemSnapshot || manualLifecycleSystemSnapshot !== systemLifecycleStage
          ? "red"
          : "blue";
      }
      // 2026-07-20 批①：清货申请待审批标记（不改变生效状态，仅展示）
      const clearancePending = Number(row.clearance_pending ?? 0) === 1;
      const lifecycleDisplay = clearancePending
        ? `${manualLifecycleStage ? `[人工] ${manualLifecycleStage}` : lifecycleStage}（清货审批中）`
        : manualLifecycleStage ? `[人工] ${manualLifecycleStage}` : lifecycleStage;
      return {
        clearance_pending: clearancePending,
        ...keys,
        platform: requiredText(row.platform),
        store_id: requiredText(row.store_id),
        store_name: requiredText(row.store_name),
        owner: requiredText(row.owner),
        item_id: requiredText(row.item_id),
        msku: mskuText,
        sku: requiredText(row.sku),
        product_name: productName,
        item_name: itemName,
        product_type: mskuText.startsWith("CS") ? "CS测品" : "常规产品",
        launch_date: formatDateOnly(row.launch_date),
        lifecycle_stage: lifecycleStage,
        system_lifecycle_stage: systemLifecycleStage,
        manual_lifecycle_stage: manualLifecycleStage,
        manual_lifecycle_by: requiredText(row.manual_lifecycle_by),
        manual_lifecycle_at: row.manual_lifecycle_at ? String(row.manual_lifecycle_at) : "",
        manual_lifecycle_system_snapshot: manualLifecycleSystemSnapshot,
        manual_lifecycle_display: manualLifecycleDisplay,
        lifecycle_highlight: lifecycleHighlight,
        lifecycle_display: lifecycleDisplay,
        sales_qty_90d: formatNumber(row.sales_qty_90d, 0),
        available_stock: row.available_stock === null || row.available_stock === undefined ? "" : formatNumber(row.available_stock, 0),
        inbound_stock: row.inbound_stock === null || row.inbound_stock === undefined ? "" : formatNumber(row.inbound_stock, 0),
        ad_spend_30d: formatNumber(row.ad_spend_30d, 2),
        wfs_delivery_fee: row.delivery_fee === null || row.delivery_fee === undefined ? "" : formatNumber(row.delivery_fee, 2),
        purchase_cost: row.purchase_cost === null || row.purchase_cost === undefined ? "" : formatNumber(row.purchase_cost, 2),
        first_mile_shipping_cost: row.first_mile_shipping_cost === null || row.first_mile_shipping_cost === undefined ? "" : formatNumber(row.first_mile_shipping_cost, 2),
        product_management_status: requiredText(row.product_management_status) || "active",
        product_management_status_label: productManagementStatusLabel(row.product_management_status),
        product_management_status_source: requiredText(row.product_management_status_source),
        product_management_status_reason: requiredText(row.product_management_status_reason),
        product_management_status_updated_at: row.product_management_status_updated_at
          ? String(row.product_management_status_updated_at) : "",
        "店铺ID": requiredText(row.store_id),
        "店铺名称": requiredText(row.store_name),
        "负责人": requiredText(row.owner),
        "ItemID": requiredText(row.item_id),
        "MSKU": mskuText,
        "SKU": requiredText(row.sku),
        "产品名称": productName,
        "产品类型": mskuText.startsWith("CS") ? "CS测品" : "常规产品",
        "产品状态": productManagementStatusLabel(row.product_management_status),
        "上架时间": formatDateOnly(row.launch_date),
        "系统生命周期": systemLifecycleStage,
        "人工生命周期": manualLifecycleDisplay,
        "近90天销量": formatNumber(row.sales_qty_90d, 0),
        "当前库存": row.available_stock === null || row.available_stock === undefined ? "" : formatNumber(row.available_stock, 0),
        "在途库存": row.inbound_stock === null || row.inbound_stock === undefined ? "" : formatNumber(row.inbound_stock, 0),
        "近30天广告费": formatNumber(row.ad_spend_30d, 2),
        // 2026-08-03 新增：产品成本/头程运费（领星 cg_price / US_cg_transport_costs，人民币；sync:product-cost 每日19:00维护；只读展示）
        "产品成本（¥）": row.purchase_cost === null || row.purchase_cost === undefined ? "" : formatNumber(row.purchase_cost, 2),
        "头程运费（¥）": row.first_mile_shipping_cost === null || row.first_mile_shipping_cost === undefined ? "" : formatNumber(row.first_mile_shipping_cost, 2),
        "停用原因": requiredText(row.product_management_status_reason),
        // WFS费用自动化热修（2026-07-17）：本列必须纯数字（前端number输入框直接消费，带后缀会渲染为空）；
        // 自动值走独立字段 wfs_fee_auto，由前端以标签展示"生效X.XX（自动）"
        // CS测品显示兜底（2026-07-17）：新上CS无配置行时显示4.00（利润链本就硬覆盖CS=4，仅补显示；旧飞书默认写4链路已停用）
        "WFS配送费（$）": row.delivery_fee === null || row.delivery_fee === undefined
          ? (mskuText.startsWith("CS") ? "4.00" : "")
          : formatNumber(row.delivery_fee, 2),
        "wfs_fee_auto": row.delivery_fee_auto === null || row.delivery_fee_auto === undefined ? "" : formatNumber(row.delivery_fee_auto, 2),
        gpt_link_keyword: gptLinkMap.get(requiredText(row.item_id))?.keyword ?? "",
        gpt_link_ads: gptLinkMap.get(requiredText(row.item_id))?.ads ?? "",
        "利润等级": blankToDash(row.profit_level),
        "操作": "",
        "GPT分析": "",
      };
    });

    res.json({
      sheet_id: PRODUCT_MANAGEMENT_SHEET_ID,
      sheet_name: "产品管理",
      columns: PRODUCT_MANAGEMENT_COLUMNS,
      rows: mapped,
      total: Number(countRows[0]?.total ?? 0),
      page,
      page_size: pageSize,
      latest_sync_time: rows[0]?.updated_at ?? null,
    });
  } catch (err) {
    res.status(500).json({ error: String(err) });
  } finally {
    await db.end();
  }
});

// ── POST /product-management/update-owner ───────────────────────────────────

router.post("/product-management/update-owner", async (req: Request, res: Response): Promise<void> => {
  const platform = requiredText(req.body?.platform || "walmart");
  const storeId = requiredText(req.body?.store_id);
  const itemId = requiredText(req.body?.item_id);
  const msku = requiredText(req.body?.msku);
  const ownerName = requiredText(req.body?.owner);

  if (platform !== "walmart" || !itemId || !ownerName) {
    res.status(400).json({ error: "缺少必要参数 platform/item_id/owner" });
    return;
  }

  const db = await getDb();
  try {
    // 花名册资格校验(2026-07-11)：新负责人必须为在册人员（在册=在职，不在册=离职），
    // 防止通过直接请求或旧页面缓存把产品分配给离职人员
    const [rosterRows] = await db.query<mysql.RowDataPacket[]>(
      "SELECT 1 FROM dim_feishu_member WHERE name = ? AND employment_status = 'active' LIMIT 1",
      [ownerName],
    );
    if (rosterRows.length === 0) {
      res.status(400).json({ error: "负责人不在当前公司花名册，禁止分配" });
      return;
    }

    await db.beginTransaction();
    const [productRows] = await db.query<mysql.RowDataPacket[]>(
      `SELECT store_id, store_name, sku, product_name
       FROM (
         SELECT p.store_id,
                COALESCE(NULLIF(p.store_name, ''), NULLIF(ds.store_name, ''), NULLIF(dc.store_name, ''), '') AS store_name,
                p.sku,
                p.product_name
         FROM dim_product p
         LEFT JOIN dim_store ds ON ds.store_id = p.store_id
         LEFT JOIN dim_store_config dc
           ON dc.platform = p.platform AND dc.store_id = p.store_id AND dc.is_active = 1
         WHERE p.platform = ? AND p.item_id = ? AND COALESCE(p.msku, '') = COALESCE(?, '')
           AND COALESCE(p.store_id, '') = COALESCE(?, '')
       ) product_lookup
       LIMIT 1`,
      [platform, itemId, msku, storeId],
    );
    if (productRows.length === 0) {
      await db.rollback();
      res.status(404).json({ error: "未找到商品" });
      return;
    }

    const product = productRows[0];
    const resolvedStoreId = requiredText(product.store_id);
    const resolvedStoreName = requiredText(product.store_name);

    // 2026-07-24 #林翔重复根治：写 dim_owner 前先按 owner_name 查重，命中则复用现有行(正主)只置 active；
    // 未命中才插一行，且 department 显式给 '' 兜底，避免唯一键 (owner_name, department) 因 department=NULL 失效导致同名堆积。
    const [ownerExistingRows] = await db.query<mysql.RowDataPacket[]>(
      "SELECT owner_id FROM dim_owner WHERE owner_name = ? ORDER BY owner_id ASC LIMIT 1",
      [ownerName],
    );
    if (ownerExistingRows.length > 0) {
      await db.query(
        "UPDATE dim_owner SET status='active', updated_at=NOW() WHERE owner_id = ?",
        [ownerExistingRows[0].owner_id],
      );
    } else {
      await db.query(
        `INSERT INTO dim_owner (owner_name, department, status, created_at, updated_at)
         VALUES (?, '', 'active', NOW(), NOW())
         ON DUPLICATE KEY UPDATE status='active', updated_at=NOW()`,
        [ownerName],
      );
    }

    await db.query(
      `UPDATE dim_product_owner
       SET status = 'inactive', updated_at = NOW()
       WHERE platform = ?
         AND item_id = ?
         AND COALESCE(msku, '') = COALESCE(?, '')
         AND (
           COALESCE(store_id, '') = COALESCE(?, '')
           OR COALESCE(store_name, '') = COALESCE(?, '')
         )
         AND status = 'active'`,
      [platform, itemId, msku, resolvedStoreId, resolvedStoreName],
    );

    const [ownerRows] = await db.query<mysql.RowDataPacket[]>(
      `SELECT id
       FROM dim_product_owner
       WHERE platform = ?
         AND item_id = ?
         AND COALESCE(msku, '') = COALESCE(?, '')
         AND owner_name = ?
         AND COALESCE(store_name, '') = COALESCE(?, '')
       ORDER BY id DESC
       LIMIT 1`,
      [platform, itemId, msku, ownerName, resolvedStoreName],
    );

    if (ownerRows.length > 0) {
      await db.query(
        `UPDATE dim_product_owner
         SET store_id = ?, store_name = ?, status = 'active',
             effective_date = CURDATE(), source_system = 'product_management', updated_at = NOW()
         WHERE id = ?`,
        [nullableText(resolvedStoreId), nullableText(resolvedStoreName), ownerRows[0].id],
      );
    } else {
      await db.query(
        `INSERT INTO dim_product_owner
           (platform, store_id, store_name, item_id, msku, owner_name, status, effective_date, source_system, created_at, updated_at)
         VALUES (?, ?, ?, ?, ?, ?, 'active', CURDATE(), 'product_management', NOW(), NOW())`,
        [
          platform,
          nullableText(resolvedStoreId),
          nullableText(resolvedStoreName),
          itemId,
          nullableText(msku),
          ownerName,
        ],
      );
    }

    // 2026-07-17 审计：取旧负责人
    const [oldOwnerRows] = await db.query<mysql.RowDataPacket[]>(
      `SELECT COALESCE(owner,'') AS old_owner FROM dim_product
       WHERE platform = ? AND item_id = ? AND COALESCE(msku, '') = COALESCE(?, '')
         AND COALESCE(store_id, '') = COALESCE(?, '') LIMIT 1`,
      [platform, itemId, msku, resolvedStoreId],
    );

    await db.query(
      `UPDATE dim_product
       SET owner = ?, updated_at = NOW()
       WHERE platform = ? AND item_id = ? AND COALESCE(msku, '') = COALESCE(?, '')
         AND COALESCE(store_id, '') = COALESCE(?, '')`,
      [ownerName, platform, itemId, msku, resolvedStoreId],
    );

    await auditManualChange(db, {
      storeId: resolvedStoreId, itemId, msku, field: "owner",
      oldValue: String(oldOwnerRows[0]?.old_owner ?? ""), newValue: ownerName,
      operator: requiredText((req as AuthedRequest).user?.username) || requiredText(req.body?.operator_name) || "admin_ui",
    });

    await db.commit();
    res.json({ ok: true });
  } catch (err) {
    try { await db.rollback(); } catch {}
    res.status(500).json({ error: String(err) });
  } finally {
    await db.end();
  }
});

// ── POST /product-management/update-lifecycle ────────────────────────────────

router.post("/product-management/update-lifecycle", async (req: Request, res: Response): Promise<void> => {
  const platform = requiredText(req.body?.platform || "walmart");
  const storeId = requiredText(req.body?.store_id);
  const itemId = requiredText(req.body?.item_id);
  const msku = requiredText(req.body?.msku);
  const rawStage = req.body?.manual_lifecycle_stage;
  const operatorName = requiredText((req as AuthedRequest).user?.username) || requiredText(req.body?.operator_name);
  const stage = rawStage === null || rawStage === undefined ? "" : requiredText(rawStage);

  if (platform !== "walmart" || !storeId || !itemId) {
    res.status(400).json({ error: "缺少必要参数 platform/store_id/item_id" });
    return;
  }
  if (!operatorName || operatorName.length > 64) {
    res.status(400).json({ error: "operator_name 必填且长度不能超过 64" });
    return;
  }

  const db = await getDb();
  try {
    const [matchedRows] = await db.query<mysql.RowDataPacket[]>(
      `SELECT p.msku, p.manual_lifecycle_stage AS cur_manual_stage, bs.system_lifecycle_stage,
              COALESCE(NULLIF(TRIM(p.manual_lifecycle_stage), ''), bs.lifecycle_stage, bs.system_lifecycle_stage, '') AS effective_stage
       FROM dim_product p
       LEFT JOIN dim_product_business_state bs
         ON bs.platform = p.platform
        AND bs.store_id = p.store_id
        AND bs.item_id = p.item_id
        AND COALESCE(bs.msku, '') = COALESCE(p.msku, '')
        AND bs.stat_date = (
          SELECT MAX(stat_date) FROM dim_product_business_state WHERE platform = ?
        )
       WHERE p.platform = ? AND p.store_id = ? AND p.item_id = ? AND COALESCE(p.msku, '') = COALESCE(?, '')`,
      [platform, platform, storeId, itemId, msku],
    );
    const matched = matchedRows.length;
    if (matched !== 1) {
      res.status(matched === 0 ? 404 : 409).json({ error: `商品全键命中数=${matched}，未更新` });
      return;
    }
    const productMsku = requiredText(matchedRows[0]?.msku);
    const systemLifecycleStage = requiredText(matchedRows[0]?.system_lifecycle_stage);
    const effectiveStage = requiredText(matchedRows[0]?.effective_stage);
    const isCsProduct = productMsku.startsWith("CS");
    const allowed = isCsProduct
      ? new Set(["测品期", "测品结束"])
      : new Set(["新品期", "上升期", "稳定期", "清货期"]);
    if (stage && !allowed.has(stage)) {
      res.status(400).json({
        error: isCsProduct
          ? "CS测品 manual_lifecycle_stage 只允许 测品期 / 测品结束 / 空值"
          : "常规产品 manual_lifecycle_stage 只允许 新品期 / 上升期 / 稳定期 / 清货期 / 空值",
      });
      return;
    }

    // 2026-07-31 #1-2修复：整段写入(审批INSERT/撤销UPDATE + dim_product UPDATE + 审计)包一个事务,任一步失败整体回滚,避免审批态与业务态不一致
    await db.beginTransaction();
    // ── 2026-07-20 批①：设为清货期改申请制（需求方定稿：需林翔审批，按 ItemID 生效）──
    // 已处于清货期（人工/系统/存量）时允许直接写人工值（非状态跃迁）；否则写 pending 申请，
    // 不改 dim_product，每日 09:33 汇总卡送审。改成其他状态时自动撤销该 item 的待审批申请。
    if (stage === "清货期" && effectiveStage !== "清货期") {
      const [pendRows] = await db.query<mysql.RowDataPacket[]>(
        `SELECT id FROM event_clearance_approval
         WHERE platform = ? AND store_id = ? AND item_id = ? AND status = 'pending' LIMIT 1`,
        [platform, storeId, itemId],
      );
      if (pendRows.length > 0) {
        await db.rollback();
        res.status(409).json({ error: "该产品已有待审批的清货申请，请等待审批结果" });
        return;
      }
      const [itemRows] = await db.query<mysql.RowDataPacket[]>(
        `SELECT COALESCE(MAX(NULLIF(TRIM(store_name),'')),'') AS store_name,
                SUBSTRING(GROUP_CONCAT(DISTINCT NULLIF(TRIM(msku),'') SEPARATOR '/'), 1, 500) AS mskus,
                COALESCE(MAX(NULLIF(TRIM(sku),'')),'') AS sku,
                COALESCE(MAX(NULLIF(TRIM(owner),'')),'') AS owner
         FROM dim_product WHERE platform = ? AND store_id = ? AND item_id = ?`,
        [platform, storeId, itemId],
      );
      const [salesRows] = await db.query<mysql.RowDataPacket[]>(
        `SELECT SUM(COALESCE(sales_qty,0)) AS qty FROM fact_sales_daily
         WHERE platform = ? AND store_id = ? AND item_id = ?
           AND stat_date >= DATE_SUB((SELECT MAX(stat_date) FROM fact_sales_daily WHERE platform = ?), INTERVAL 29 DAY)`,
        [platform, storeId, itemId, platform],
      );
      const [invRows] = await db.query<mysql.RowDataPacket[]>(
        `SELECT SUM(COALESCE(wfs_available_stock,0)) AS wfs, SUM(COALESCE(inbound_stock,0)) AS inbound
         FROM fact_inventory_daily
         WHERE platform = ? AND store_id = ? AND item_id = ?
           AND snapshot_date = (SELECT MAX(snapshot_date) FROM fact_inventory_daily WHERE platform = ? AND store_id = ? AND item_id = ?)`,
        [platform, storeId, itemId, platform, storeId, itemId],
      );
      const sales30 = Number(salesRows[0]?.qty ?? 0);
      const stock = Number(invRows[0]?.wfs ?? 0);
      const inbound = Number(invRows[0]?.inbound ?? 0);
      const turnoverDays = sales30 > 0 ? Math.round(stock / (sales30 / 30)) : null;
      await db.query(
        `INSERT INTO event_clearance_approval
           (platform, store_id, store_name, item_id, mskus, sku, owner, applicant, metrics_json, status)
         VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending')`,
        [platform, storeId, String(itemRows[0]?.store_name ?? ''), itemId,
         String(itemRows[0]?.mskus ?? ''), String(itemRows[0]?.sku ?? ''), String(itemRows[0]?.owner ?? ''),
         operatorName, JSON.stringify({ sales30, stock, inbound, turnoverDays })],
      );
      await auditManualChange(db, {
        storeId, itemId, msku, field: "clearance_apply",
        oldValue: effectiveStage, newValue: "清货期(待审批)", operator: operatorName,
      });
      await db.commit();
      res.json({ ok: true, pending_approval: true, message: "清货申请已提交，明早 09:33 送林翔审批，通过后自动生效" });
      return;
    }
    if (stage !== "清货期") {
      const [cancelResult] = await db.query<mysql.ResultSetHeader>(
        `UPDATE event_clearance_approval SET status = 'cancelled'
         WHERE platform = ? AND store_id = ? AND item_id = ? AND status = 'pending'`,
        [platform, storeId, itemId],
      );
      if (cancelResult.affectedRows > 0) {
        await auditManualChange(db, {
          storeId, itemId, msku, field: "clearance_apply",
          oldValue: "清货期(待审批)", newValue: `已撤销(改为${stage || "清除"})`, operator: operatorName,
        });
      }
    }

    const [result] = await db.query<mysql.ResultSetHeader>(
      stage
        ? `UPDATE dim_product
          SET manual_lifecycle_stage = ?,
              manual_lifecycle_by = ?,
              manual_lifecycle_at = NOW(),
              manual_lifecycle_system_snapshot = ?,
               updated_at = NOW()
           WHERE platform = ? AND store_id = ? AND item_id = ? AND COALESCE(msku, '') = COALESCE(?, '')`
        : `UPDATE dim_product
           SET manual_lifecycle_stage = NULL,
               manual_lifecycle_by = NULL,
               manual_lifecycle_at = NULL,
               manual_lifecycle_system_snapshot = NULL,
               updated_at = NOW()
           WHERE platform = ? AND store_id = ? AND item_id = ? AND COALESCE(msku, '') = COALESCE(?, '')`,
      stage
        ? [stage, operatorName, systemLifecycleStage || null, platform, storeId, itemId, msku]
        : [platform, storeId, itemId, msku],
    );
    await auditManualChange(db, {
      storeId, itemId, msku, field: "manual_lifecycle_stage",
      oldValue: "", newValue: stage || "(清除)", operator: operatorName,
    });
    await db.commit();
    res.json({ ok: true, updated: result.affectedRows, manual_lifecycle_stage: stage || null });
  } catch (err) {
    try { await db.rollback(); } catch {}
    res.status(500).json({ error: String(err) });
  } finally {
    await db.end();
  }
});

// ── POST /product-management/update-wfs-fee ─────────────────────────────────

router.post("/product-management/update-wfs-fee", async (req: Request, res: Response): Promise<void> => {
  const platform = requiredText(req.body?.platform || "walmart");
  const storeId = requiredText(req.body?.store_id);
  const itemId = requiredText(req.body?.item_id);
  const msku = requiredText(req.body?.msku);
  const fee = parseMoney(req.body?.delivery_fee ?? req.body?.wfs_delivery_fee);

  if (platform !== "walmart" || !itemId || fee === null || fee < 0) {
    res.status(400).json({ error: "缺少必要参数 platform/item_id/delivery_fee，或金额无效" });
    return;
  }
  if (msku.startsWith("CS") && Math.abs(fee - 4) > 0.0001) {
    res.status(400).json({ error: "CS测品 WFS配送费固定为 4" });
    return;
  }

  const db = await getDb();
  try {
    await db.beginTransaction();
    const [productRows] = await db.query<mysql.RowDataPacket[]>(
      `SELECT store_id, store_name, sku
       FROM (
         SELECT p.store_id,
                COALESCE(NULLIF(p.store_name, ''), NULLIF(ds.store_name, ''), NULLIF(dc.store_name, ''), '') AS store_name,
                p.sku
         FROM dim_product p
         LEFT JOIN dim_store ds ON ds.store_id = p.store_id
         LEFT JOIN dim_store_config dc
           ON dc.platform = p.platform AND dc.store_id = p.store_id AND dc.is_active = 1
         WHERE p.platform = ? AND p.item_id = ? AND COALESCE(p.msku, '') = COALESCE(?, '')
           AND COALESCE(p.store_id, '') = COALESCE(?, '')
       ) product_lookup
       LIMIT 1`,
      [platform, itemId, msku, storeId],
    );
    if (productRows.length === 0) {
      await db.rollback();
      res.status(404).json({ error: "未找到商品" });
      return;
    }

    const product = productRows[0];
    const resolvedStoreId = requiredText(product.store_id);
    const resolvedStoreName = requiredText(product.store_name);
    const resolvedSku = requiredText(product.sku);

    const [costRows] = await db.query<mysql.RowDataPacket[]>(
      `SELECT id
       FROM dim_product_cost_config
       WHERE platform = ?
         AND item_id = ?
         AND COALESCE(msku, '') = COALESCE(?, '')
         AND effective_date = CURDATE()
         AND COALESCE(store_name, '') = COALESCE(?, '')
       ORDER BY id DESC
       LIMIT 1`,
      [platform, itemId, msku, resolvedStoreName],
    );

    if (costRows.length > 0) {
      await db.query(
        `UPDATE dim_product_cost_config
         SET store_id = ?, sku = ?, delivery_fee = ?, status = 'active',
             source_system = 'product_management', updated_at = NOW()
         WHERE id = ?`,
        [nullableText(resolvedStoreId), nullableText(resolvedSku), fee, costRows[0].id],
      );
    } else {
      await db.query(
        `INSERT INTO dim_product_cost_config
           (platform, store_id, store_name, item_id, msku, sku, delivery_fee, status, effective_date, source_system, created_at, updated_at)
         VALUES (?, ?, ?, ?, ?, ?, ?, 'active', CURDATE(), 'product_management', NOW(), NOW())`,
        [
          platform,
          nullableText(resolvedStoreId),
          nullableText(resolvedStoreName),
          itemId,
          nullableText(msku),
          nullableText(resolvedSku),
          fee,
        ],
      );
    }

    await db.commit();
    res.json({ ok: true });
  } catch (err) {
    try { await db.rollback(); } catch {}
    res.status(500).json({ error: String(err) });
  } finally {
    await db.end();
  }
});

// ── GET /product-management/owner-options ───────────────────────────────────
// 口径(2026-07-27 需求方定稿)：负责人下拉可新选人 = dim_app_user 中 在职 且 已注册(激活) 且 角色∈(运营主管,运营组员,超管)。
// 判定：is_active=1(在职)、password_hash<>'!'(已激活)、role_key ∈ (运营主管,运营组员,超管)。
// 注：超管按"超管角色"纳入(林翔/陈佳聪)，不按 is_superadmin 标记——故引导账号 admin(系统管理员,仅有标记无角色)不入下拉。
// 前端每行下拉额外保留"当前负责人"值(即便其已不符合上述条件，如历史/超管负责人)，不丢现有归属；仅"可新选"限定为合格运营。
// 保存链路 update-owner 支持新名字直接落库，不依赖 dim_owner。
router.get("/product-management/owner-options", async (_req: Request, res: Response): Promise<void> => {
  const db = await getDb();
  try {
    const [rows] = await db.query<mysql.RowDataPacket[]>(
      `SELECT u.display_name AS owner_name
         FROM dim_app_user u
         JOIN dim_app_user_role r ON r.user_id = u.id
        WHERE u.is_active = 1
          AND u.password_hash <> '!'
          AND COALESCE(NULLIF(u.display_name, ''), '') <> ''
          AND r.role_key IN ('运营主管', '运营组员', '超管')
        GROUP BY u.id, u.display_name
        ORDER BY u.display_name`,
    );
    res.json({
      owners: rows.map((r) => ({
        owner_name: requiredText(r.owner_name),
        feishu_user_id: "",
        status: "active",
      })),
    });
  } catch (err) {
    res.status(500).json({ error: String(err) });
  } finally {
    await db.end();
  }
});

// ── POST /product-management/update-gpt-link ─────────────────────────────────
// 2026-07-23 产品GPT分析链接：ItemID 维度版本表 dim_product_gpt_link（append-only）。
// 每次保存=插入新版本（不允许清空只能替换）；运营日志行按其 created_at 匹配"当时的链接"，
// 因此替换只影响之后新生成的日志行，历史行保留旧链接。
router.post("/product-management/update-gpt-link", async (req: Request, res: Response): Promise<void> => {
  const platform = requiredText(req.body?.platform || "walmart");
  const itemId = requiredText(req.body?.item_id);
  const linkType = requiredText(req.body?.link_type).toLowerCase();
  const url = requiredText(req.body?.url);
  if (!itemId || (linkType !== "keyword" && linkType !== "ads")) {
    res.status(400).json({ error: "缺少 item_id 或 link_type 非法（keyword/ads）" });
    return;
  }
  if (!/^https?:\/\/.+/.test(url) || url.length > 1000) {
    res.status(400).json({ error: "链接必须以 http(s):// 开头且不超过1000字符；不允许清空，只能替换为新链接" });
    return;
  }
  const db = await getDb();
  try {
    await db.query(
      `INSERT INTO dim_product_gpt_link (platform, item_id, link_type, url, updated_by)
       VALUES (?, ?, ?, ?, ?)`,
      [platform, itemId, linkType, url, requiredText((req as AuthedRequest).user?.username) || "admin_ui"],
    );
    res.json({ ok: true, item_id: itemId, link_type: linkType });
  } catch (err) {
    res.status(500).json({ error: String(err) });
  } finally {
    await db.end();
  }
});

// ── POST /product-management/update-status ───────────────────────────────────
// 人工状态操作：允许 archived / active / inactive。
// 系统只负责打 inactive_candidate 候选；真正 inactive 必须人工确认。
// archived 优先级最高：一旦归档，系统自动停用脚本（scripts/updateProductManagementStatus.ts）必须跳过。
router.post("/product-management/update-status", async (req: Request, res: Response): Promise<void> => {
  const platform = requiredText(req.body?.platform || "walmart");
  const storeId = requiredText(req.body?.store_id);
  const itemId = requiredText(req.body?.item_id);
  const msku = requiredText(req.body?.msku);
  const targetStatus = requiredText(req.body?.product_management_status).toLowerCase();
  const reasonInput = requiredText(req.body?.reason);
  const force = req.body?.force === true;  // 2026-07-30 人工特批：越过库存门槛(仍走完整审计)

  if (platform !== "walmart" || !itemId) {
    res.status(400).json({ error: "缺少必要参数 platform/item_id" });
    return;
  }
  if (targetStatus !== "archived" && targetStatus !== "active" && targetStatus !== "inactive") {
    res.status(400).json({ error: "product_management_status 只允许 archived / active / inactive" });
    return;
  }

  const reason = reasonInput || (
    targetStatus === "archived"
      ? "人工归档"
      : targetStatus === "inactive"
        ? "人工确认停用"
        : "人工恢复在用"
  );
  const operatorName = requiredText((req as AuthedRequest).user?.username) || requiredText(req.body?.operator_name) || "admin_ui";
  const db = await getDb();
  try {
    // 2026-07-18 归档护栏（2026-07-25 放宽）：库存 ≥ 5 或 有在途 一律不得归档
    // 2026-07-30 force=true 为人工特批：越过库存门槛直接归档（reason 记特批、仍走完整审计 auditManualChange）
    if (targetStatus === "archived" && !force) {
      // 2026-07-30 UNPUBLISHED(已下架)豁免库存门槛（A: 按 ItemID 级判断，兼容多MSKU历史遗留行）：
      //   本行为下架，或 本行状态空 且 该 ItemID 有下架行、无在线行 → 视为已下架放行。非下架品门槛不变。
      const [pubRows] = await db.query<mysql.RowDataPacket[]>(
        `SELECT
           MAX(CASE WHEN COALESCE(msku,'') = COALESCE(?, '') AND COALESCE(store_id,'') = COALESCE(?, '')
                    THEN UPPER(COALESCE(walmart_publish_status,'')) END) AS this_ps,
           SUM(UPPER(COALESCE(walmart_publish_status,'')) = 'UNPUBLISHED') AS n_unpub,
           SUM(UPPER(COALESCE(walmart_publish_status,'')) = 'PUBLISHED')   AS n_pub
         FROM dim_product WHERE platform = ? AND item_id = ?`,
        [msku, storeId, platform, itemId],
      );
      const thisPs = String(pubRows[0]?.this_ps ?? "");
      const nUnpub = Number(pubRows[0]?.n_unpub ?? 0);
      const nPub = Number(pubRows[0]?.n_pub ?? 0);
      const isUnpublished = thisPs === "UNPUBLISHED" || (thisPs === "" && nUnpub > 0 && nPub === 0);
      // 2026-07-25 需求方定稿：归档门槛「库存 < 5 且 无在途」（库存口径同列表「当前库存」= fact_inventory_daily.available_stock 最新快照总可售）；下架品免此门槛。
      if (!isUnpublished) {
        const [stockRows] = await db.query<mysql.RowDataPacket[]>(
          `SELECT COALESCE(SUM(available_stock), 0) AS stock,
                  COALESCE(SUM(inbound_stock), 0) AS inbound
           FROM fact_inventory_daily
           WHERE platform = ? AND snapshot_date = (SELECT MAX(snapshot_date) FROM fact_inventory_daily)
             AND item_id = ? AND COALESCE(msku,'') = COALESCE(?, '')
             AND COALESCE(store_id,'') = COALESCE(?, '')`,
          [platform, itemId, msku, storeId],
        );
        const curStock = Number(stockRows[0]?.stock ?? 0);
        const curInbound = Number(stockRows[0]?.inbound ?? 0);
        if (curStock >= 5 || curInbound > 0) {
          const parts: string[] = [];
          if (curStock >= 5) parts.push(`现库存 ${curStock} 件（需 < 5）`);
          if (curInbound > 0) parts.push(`在途 ${curInbound} 件（需为 0）`);
          res.status(400).json({
            error: `该商品${parts.join("、")}（最新快照），仅库存 < 5 且无在途的产品可归档；请先处理库存或等在途到货/清零后再归档`,
          });
          return;
        }
      }
    }
    // 2026-07-17 审计：先取旧值
    const [oldRows] = await db.query<mysql.RowDataPacket[]>(
      `SELECT COALESCE(product_management_status,'') AS old_status FROM dim_product
       WHERE platform = ? AND item_id = ? AND COALESCE(msku, '') = COALESCE(?, '')
         AND COALESCE(store_id, '') = COALESCE(?, '') LIMIT 1`,
      [platform, itemId, msku, storeId],
    );
    const oldStatus = String(oldRows[0]?.old_status ?? "");
    const [result] = await db.query<mysql.ResultSetHeader>(
      `UPDATE dim_product
       SET product_management_status = ?,
           product_management_status_source = 'manual',
           product_management_status_reason = ?,
           product_management_status_updated_at = NOW(),
           updated_at = NOW()
       WHERE platform = ? AND item_id = ? AND COALESCE(msku, '') = COALESCE(?, '')
         AND COALESCE(store_id, '') = COALESCE(?, '')`,
      [targetStatus, reason, platform, itemId, msku, storeId],
    );
    if (result.affectedRows === 0) {
      res.status(404).json({ error: "未找到商品，未更新任何行" });
      return;
    }
    await auditManualChange(db, {
      storeId, itemId, msku, field: "product_management_status",
      oldValue: oldStatus, newValue: targetStatus, operator: operatorName, reason,
    });
    res.json({ ok: true, updated: result.affectedRows });
  } catch (err) {
    res.status(500).json({ error: String(err) });
  } finally {
    await db.end();
  }
});

// ── GET /data ─────────────────────────────────────────────────────────────────

router.get("/data", async (req: Request, res: Response): Promise<void> => {
  const sheetId  = String(req.query.sheet_id ?? "").trim();
  if (SUPERADMIN_ONLY_SHEETS.has(sheetId) && blockNonSuperadmin(req, res)) return;
  const page     = Math.max(1, Number(req.query.page ?? 1));
  // 2026-07-20 下载导出：携带有效导出令牌时放宽单页上限（普通请求仍封顶200）
  const exportCap = isValidExportToken(String(req.query.export_token ?? "").trim()) ? exportMaxRows() : 200;
  const pageSize = Math.min(exportCap, Math.max(1, Number(req.query.page_size ?? 50)));
  const keyword  = String(req.query.keyword ?? "").trim();
  const sortField = requiredText(req.query.sort_field);
  const sortOrder = normalizeSortOrder(req.query.sort_order);
  const offset   = (page - 1) * pageSize;

  // 新增筛选参数
  const sku           = String(req.query.sku         ?? "").trim();
  const msku          = String(req.query.msku        ?? "").trim();
  const itemId        = String(req.query.item_id     ?? "").trim();
  const storeName     = String(req.query.store_name  ?? "").trim();
  const owner         = String(req.query.owner       ?? "").trim();
  const defaultDate   = businessAvailableDate();
  const dateStart     = String(req.query.date_start  || defaultDate).trim();
  const dateEnd       = String(req.query.date_end    || defaultDate).trim();
  const grossMinRaw   = req.query.gross_margin_min;
  const grossMaxRaw   = req.query.gross_margin_max;
  const adMinRaw      = req.query.ad_ratio_min;
  const adMaxRaw      = req.query.ad_ratio_max;

  const grossMin = (grossMinRaw !== undefined && grossMinRaw !== "") ? Number(grossMinRaw) : null;
  const grossMax = (grossMaxRaw !== undefined && grossMaxRaw !== "") ? Number(grossMaxRaw) : null;
  const adMin    = (adMinRaw    !== undefined && adMinRaw    !== "") ? Number(adMinRaw)    : null;
  const adMax    = (adMaxRaw    !== undefined && adMaxRaw    !== "") ? Number(adMaxRaw)    : null;

  if (!sheetId) {
    res.status(400).json({ error: "缺少 sheet_id 参数" });
    return;
  }

  // ── 构建 WHERE 条件 ──────────────────────────────────────────────────────────
  const conditions: string[] = [
    "spreadsheet_token = ?",
    "sheet_id = ?",
  ];
  const params: (string | number)[] = [SPREADSHEET_TOKEN, sheetId];

  // 2026-07-20 拍板：每日销售明细不含CS测品（CS看"CS测品分析"页）；仅 <REDACTED_FEISHU_SHEET_ID> 生效
  if (sheetId === "<REDACTED_FEISHU_SHEET_ID>") {
    conditions.push(`${jsonTextExpr(["MSKU", "msku"])} NOT LIKE 'CS%'`);
  }

  // 全文关键词
  if (keyword) {
    conditions.push("row_json LIKE ?");
    params.push(`%${keyword}%`);
  }

  // SKU（模糊）
  if (sku) {
    conditions.push(`${jsonTextExpr(["SKU", "sku"])} LIKE ?`);
    params.push(`%${sku}%`);
  }

  // MSKU（模糊）
  if (msku) {
    conditions.push(`${jsonTextExpr(["MSKU", "msku"])} LIKE ?`);
    params.push(`%${msku}%`);
  }

  // 商品ID（模糊，兼容三个字段名）
  if (itemId) {
    conditions.push(`${jsonTextExpr(["商品ID", "Item ID", "item_id"])} LIKE ?`);
    params.push(`%${itemId}%`);
  }

  // 店铺（精确匹配，兼容两个字段名；2026-07-17 支持逗号分隔多选）
  {
    const storeNames = parseMultiText(storeName);
    if (storeNames.length) {
      conditions.push(`${jsonTextExpr(["店铺", "store_name"])} IN (${inPlaceholders(storeNames.length)})`);
      params.push(...storeNames);
    }
  }

  // 负责人（下拉精确匹配）——2026-07-13 修复：
  // 旧版四源 OR 存在两处缺陷：
  //   ① <REDACTED_FEISHU_SHEET_ID> 退役镜像分支的商品ID比较未给外层表达式加别名，在子查询内被
  //     owner_row.row_json 遮蔽，退化为恒真——镜像中只要存在任意一条目标负责人
  //     记录即全量放行（实测 owner=刘华媛 时 834/834 行全部通过）；
  //   ② dim_product / dim_product_owner 分支按 item_id 泛匹配、不限店铺、不限
  //     status='active'，存在跨店铺与历史负责人污染风险。
  // 新口径（与订单利润 Beta 一致的"当前负责人"语义）：
  //   优先：当前快照行内负责人精确匹配（快照负责人每日由 dim_product 当前值写入，
  //         方案B每日回溯5天，口径可靠）；
  //   兜底：仅当行内负责人为空时，按 同店铺(店铺名经 dim_store 映射 store_id)+
  //         同 item_id 匹配 dim_product 当前负责人（单一权威来源）。
  //   已删除：<REDACTED_FEISHU_SHEET_ID> 退役镜像分支、dim_product_owner 分支、item 级跨店铺泛匹配。
  //   注：兜底 EXISTS 只连接 dim_product/dim_store（均无 row_json 列），
  //       外层 row_json 表达式不存在别名遮蔽问题。
  {
    // 2026-07-17 多选：负责人支持逗号分隔多值（口径不变：快照行内优先，dim_product 兜底）
    const owners = parseMultiText(owner);
    if (owners.length) {
      const ownerExprSql = jsonTextExpr(["负责人", "owner"]);
      const itemExprSql = jsonTextExpr(["商品ID", "Item ID", "item_id"]);
      const storeNameExprSql = jsonTextExpr(["店铺", "store_name"]);
      const ph = inPlaceholders(owners.length);
      conditions.push(`(
      ${ownerExprSql} IN (${ph})
      OR (
        COALESCE(${ownerExprSql}, '') = ''
        AND EXISTS (
          SELECT 1
          FROM dim_product dp
          JOIN dim_store ds
            ON ds.platform = 'walmart'
           AND ds.store_id = dp.store_id
          WHERE dp.platform = 'walmart'
            AND dp.item_id = ${itemExprSql}
            AND ds.store_name = ${storeNameExprSql}
            AND dp.owner IN (${ph})
        )
      )
    )`);
      params.push(...owners, ...owners);
    }
  }

  // 日期范围
  if (dateStart) {
    conditions.push(`${dateSqlExpr()} >= ?`);
    params.push(dateStart);
  }
  if (dateEnd) {
    conditions.push(`${dateSqlExpr()} <= ?`);
    params.push(dateEnd);
  }

  // 毛利率区间（百分比）
  if (grossMin !== null) {
    conditions.push(`${pctSqlExpr("毛利率", "近7天毛利率", "近5天毛利率")} >= ?`);
    params.push(grossMin);
  }
  if (grossMax !== null) {
    conditions.push(`${pctSqlExpr("毛利率", "近7天毛利率", "近5天毛利率")} <= ?`);
    params.push(grossMax);
  }

  // 广告占比区间（百分比）
  if (adMin !== null) {
    conditions.push(`${pctSqlExpr("广告占比", "近7天广告占比", "近5天广告占比")} >= ?`);
    params.push(adMin);
  }
  if (adMax !== null) {
    conditions.push(`${pctSqlExpr("广告占比", "近7天广告占比", "近5天广告占比")} <= ?`);
    params.push(adMax);
  }

  const where = conditions.join(" AND ");
  const orderBySql = sheetId === "<REDACTED_FEISHU_SHEET_ID>"
    ? resolveSortSql(
      sortField,
      sortOrder,
      {
        date: `${dateSqlExpr()}`,
        sales_amount: `${jsonNumberExpr(["今日销售额（$）", "今日销售额", "sales_amount"])}`,
        sales_qty: `${jsonNumberExpr(["今日销量", "sales_qty"])}`,
        order_count: `${jsonNumberExpr(["订单量", "order_count"])}`,
      },
      `${dateSqlExpr()} DESC, row_index DESC`,
    )
    : `${dateSqlExpr()} DESC, row_index DESC`;

  // ── 查询 ────────────────────────────────────────────────────────────────────
  const db = await getDb();
  try {
    const [metaRows] = await db.query<mysql.RowDataPacket[]>(
      `SELECT COUNT(*) AS total, MAX(pulled_at) AS latest_sync_time, MAX(sheet_name) AS sheet_name
       FROM raw_feishu_table WHERE ${where}`,
      params,
    );
    const total     = Number(metaRows[0]?.total ?? 0);
    const latest    = metaRows[0]?.latest_sync_time ?? null;
    const sheetName = metaRows[0]?.sheet_name ?? sheetId;

    const [dataRows] = await db.query<mysql.RowDataPacket[]>(
      `SELECT row_index, row_json
       FROM raw_feishu_table WHERE ${where}
       ORDER BY ${orderBySql}
       LIMIT ? OFFSET ?`,
      [...params, pageSize, offset],
    );

    const firstRow = dataRows[0]?.row_json as Record<string, string> | undefined;
    const columns: string[] = firstRow ? Object.keys(firstRow) : [];

    const rows = dataRows.map((r) => {
      const obj = (r.row_json ?? {}) as Record<string, unknown>;
      const cleaned: Record<string, string> = {};
      for (const [k, v] of Object.entries(obj)) {
        cleaned[k] = v === null || v === undefined ? "" : String(v);
      }
      return cleaned;
    });
    const supplementStats = sheetId === "<REDACTED_FEISHU_SHEET_ID>"
      ? await supplementDailyDetailRows(db, rows)
      : null;

    // 2026-07-20 拍板：WFS库存列改"最新快照实值"（库存FACT按拉取日打标签，
    // 历史业务日快照缺档时RAW字段为0，不代表真实库存）。按 店铺+商品ID 汇总最新快照覆盖。
    if (sheetId === "<REDACTED_FEISHU_SHEET_ID>" && rows.length > 0) {
      const [invRows] = await db.query<mysql.RowDataPacket[]>(
        `SELECT store_name, item_id, SUM(COALESCE(wfs_available_stock, 0)) AS wfs
           FROM fact_inventory_daily
          WHERE platform = 'walmart'
            AND snapshot_date = (SELECT MAX(snapshot_date) FROM fact_inventory_daily WHERE platform = 'walmart')
          GROUP BY store_name, item_id`,
      );
      const invMap = new Map<string, number>();
      for (const ir of invRows) {
        invMap.set(`${String(ir.store_name)}___${String(ir.item_id)}`, Number(ir.wfs ?? 0));
      }
      // 2026-08-11 需求方拍板：行日期>=2026-07-01 改「当日实际库存」（店铺+商品ID+行日期 的当日快照）；
      // 快照缺档日显示「缺档」（如07-16/17；缺档监测由数据哨兵负责，历史不估补）；
      // <2026-07-01 维持最新快照覆盖（2026-07-20拍板口径）。合计口径不变（筛选内产品最新快照去重求和）。
      const DAILY_INV_START = "2026-07-01";
      const dailyMap = new Map<string, number>();
      {
        const rowDates = rows.map((r) => String(r["日期"] ?? "")).filter((d) => /^\d{4}-\d{2}-\d{2}$/.test(d) && d >= DAILY_INV_START);
        const rowItems = [...new Set(rows.map((r) => String(r["商品ID"] ?? "")).filter(Boolean))];
        if (rowDates.length && rowItems.length) {
          const minD = rowDates.reduce((a, b) => (a < b ? a : b));
          const maxD = rowDates.reduce((a, b) => (a > b ? a : b));
          const [dRows] = await db.query<mysql.RowDataPacket[]>(
            `SELECT store_name, item_id, DATE_FORMAT(snapshot_date,'%Y-%m-%d') AS d,
                    SUM(COALESCE(wfs_available_stock, 0)) AS wfs
               FROM fact_inventory_daily
              WHERE platform = 'walmart' AND snapshot_date BETWEEN ? AND ?
                AND item_id IN (${rowItems.map(() => "?").join(",")})
              GROUP BY store_name, item_id, snapshot_date`,
            [minD, maxD, ...rowItems],
          );
          for (const ir of dRows) {
            dailyMap.set(`${String(ir.store_name)}___${String(ir.item_id)}___${String(ir.d)}`, Number(ir.wfs ?? 0));
          }
        }
      }
      for (const row of rows) {
        const d = String(row["日期"] ?? "");
        const key = `${row["店铺"] ?? ""}___${row["商品ID"] ?? ""}`;
        if (/^\d{4}-\d{2}-\d{2}$/.test(d) && d >= DAILY_INV_START) {
          const v = dailyMap.get(`${key}___${d}`);
          row["WFS可售库存"] = v === undefined ? "缺档" : String(v);
        } else {
          row["WFS可售库存"] = String(invMap.get(key) ?? 0);
        }
      }
    }

    // 合计行（2026-07-17 领星式）：当前筛选全量口径，数值列SUM、比率按汇总重算
    let totals: Record<string, string> | null = null;
    if (sheetId === "<REDACTED_FEISHU_SHEET_ID>") {
      const [tRows] = await db.query<mysql.RowDataPacket[]>(
        `SELECT
           SUM(${jsonNumberExpr(["今日销量", "sales_qty"])}) AS qty,
           SUM(${jsonNumberExpr(["订单量", "order_count"])}) AS orders,
           SUM(${jsonNumberExpr(["今日销售额（$）", "今日销售额", "sales_amount"])}) AS sales,
           SUM(${jsonNumberExpr(["毛利润（$）", "gross_profit"])}) AS profit,
           SUM(${jsonNumberExpr(["广告花费（$）", "ad_spend"])}) AS ad,
           SUM(${jsonNumberExpr(["WFS可售库存", "wfs_stock"])}) AS wfs,
           SUM(${jsonNumberExpr(["非WFS库存", "non_wfs_stock"])}) AS non_wfs,
           SUM(${jsonNumberExpr(["在途库存", "in_transit_stock"])}) AS in_transit
         FROM raw_feishu_table WHERE ${where}`,
        params,
      );
      const t = tRows[0] ?? {};
      const sales = Number(t.sales ?? 0);
      const profit = Number(t.profit ?? 0);
      const ad = Number(t.ad ?? 0);
      const [invTotalRows] = await db.query<mysql.RowDataPacket[]>(
        `SELECT SUM(inv.wfs) AS wfs FROM (
            SELECT DISTINCT ${jsonTextExpr(["店铺", "store_name"])} AS s_name,
                   ${jsonTextExpr(["商品ID", "Item ID", "item_id"])} AS i_id
              FROM raw_feishu_table WHERE ${where}
         ) t2
         JOIN (
            SELECT store_name, item_id, SUM(COALESCE(wfs_available_stock, 0)) AS wfs
              FROM fact_inventory_daily
             WHERE platform = 'walmart'
               AND snapshot_date = (SELECT MAX(snapshot_date) FROM fact_inventory_daily WHERE platform = 'walmart')
             GROUP BY store_name, item_id
         ) inv ON inv.store_name = t2.s_name AND inv.item_id = t2.i_id`,
        params,
      );
      totals = {
        "今日销量": formatNumber(t.qty, 0),
        "订单量": formatNumber(t.orders, 0),
        "今日销售额（$）": formatNumber(sales, 2),
        "毛利润（$）": formatNumber(profit, 2),
        "广告花费（$）": formatNumber(ad, 2),
        "毛利率": sales > 0 ? `${(profit / sales * 100).toFixed(2)}%` : "-",
        "广告占比": sales > 0 ? `${(ad / sales * 100).toFixed(2)}%` : "-",
        "WFS可售库存": formatNumber(invTotalRows[0]?.wfs ?? 0, 0),
        "非WFS库存": formatNumber(t.non_wfs, 0),
        "在途库存": formatNumber(t.in_transit, 0),
      };
    }

    res.json({
      sheet_id: sheetId,
      sheet_name: sheetName,
      columns,
      rows,
      total,
      page,
      page_size: pageSize,
      latest_sync_time: latest,
      supplement_stats: supplementStats,
      totals,
    });
  } catch (err) {
    res.status(500).json({ error: String(err) });
  } finally {
    await db.end();
  }
});

// ── GET /order-profit ─────────────────────────────────────────────────────────

router.get("/order-profit", async (req: Request, res: Response): Promise<void> => {
  if (blockNonSuperadmin(req, res)) return;
  const page = Math.max(1, Number(req.query.page ?? 1));
  // 2026-07-20 下载导出：携带有效导出令牌时放宽单页上限（普通请求仍封顶200）
  const exportCap = isValidExportToken(String(req.query.export_token ?? "").trim()) ? exportMaxRows() : 200;
  const pageSize = Math.min(exportCap, Math.max(1, Number(req.query.page_size ?? 50)));
  const offset = (page - 1) * pageSize;
  const sortField = requiredText(req.query.sort_field);
  const sortOrder = normalizeSortOrder(req.query.sort_order);

  const keyword = String(req.query.keyword ?? "").trim();
  const sku = String(req.query.sku ?? "").trim();
  const msku = String(req.query.msku ?? "").trim();
  const itemId = String(req.query.item_id ?? "").trim();
  const storeName = String(req.query.store_name ?? "").trim();
  const owner = String(req.query.owner ?? "").trim();
  const stockStatus = String(req.query.stock_status ?? "").trim();
  const productStage = String(req.query.product_stage ?? "").trim();
  const costStatus = String(req.query.cost_status ?? "").trim();
  const pmStatus = String(req.query.product_management_status ?? "").trim().toLowerCase();
  const grossMinRaw = req.query.gross_margin_min;
  const grossMaxRaw = req.query.gross_margin_max;
  const adMinRaw = req.query.ad_ratio_min;
  const adMaxRaw = req.query.ad_ratio_max;

  const defaultDate = businessAvailableDate();
  const dateStart = String(req.query.date_start || defaultDate).trim();
  const dateEnd = String(req.query.date_end || defaultDate).trim();

  const grossMin = (grossMinRaw !== undefined && grossMinRaw !== "") ? Number(grossMinRaw) : null;
  const grossMax = (grossMaxRaw !== undefined && grossMaxRaw !== "") ? Number(grossMaxRaw) : null;
  const adMin = (adMinRaw !== undefined && adMinRaw !== "") ? Number(adMinRaw) : null;
  const adMax = (adMaxRaw !== undefined && adMaxRaw !== "") ? Number(adMaxRaw) : null;

  const rawConditions: string[] = [
    "spreadsheet_token = ?",
    "sheet_id = ?",
    "data_date >= ?",
    "data_date <= ?",
  ];
  const rawParams: (string | number)[] = [SPREADSHEET_TOKEN, ORDER_PROFIT_SHEET_ID, dateStart, dateEnd];

  // 订单利润 Beta：剔除 MSKU 以 CS 开头的产品（CS 测品单独在「CS测品分析 Beta」看）
  rawConditions.push(`COALESCE(${jsonTextExpr(["MSKU", "msku"])}, '') NOT LIKE 'CS%'`);

  if (keyword) {
    rawConditions.push("row_json LIKE ?");
    rawParams.push(`%${keyword}%`);
  }
  if (sku) {
    rawConditions.push(`${jsonTextExpr(["SKU", "sku"])} LIKE ?`);
    rawParams.push(`%${sku}%`);
  }
  if (msku) {
    rawConditions.push(`${jsonTextExpr(["MSKU", "msku"])} LIKE ?`);
    rawParams.push(`%${msku}%`);
  }
  if (itemId) {
    rawConditions.push(`${jsonTextExpr(["商品ID", "Item ID", "item_id"])} LIKE ?`);
    rawParams.push(`%${itemId}%`);
  }
  {
    // 2026-07-17 多选店铺
    const storeNames = parseMultiText(storeName);
    if (storeNames.length) {
      rawConditions.push(`${jsonTextExpr(["店铺", "store_name"])} IN (${inPlaceholders(storeNames.length)})`);
      rawParams.push(...storeNames);
    }
  }
  // 负责人口径修复(2026-07-11)：owner 不再按 RAW 历史行内负责人过滤（历史负责人为空/变更
  // 会把完整窗口截断，如 20038302168 7天被截成3天）。owner 改为聚合后按当前
  // dim_product.owner 过滤（见 aggregateWithPmSql 的 current_owner 与 outerConditions）。

  const rawWhere = rawConditions.join(" AND ");
  const latestValue = (field: string) => (
    `SUBSTRING_INDEX(GROUP_CONCAT(NULLIF(${field}, '') ORDER BY row_date DESC SEPARATOR '|||'), '|||', 1)`
  );

  const baseSql = `
    SELECT
      data_date AS row_date,
      ${jsonTextExpr(["店铺", "store_name"])} AS store_name,
      ${jsonTextExpr(["店铺ID", "store_id"])} AS store_id,
      ${jsonTextExpr(["商品ID", "Item ID", "item_id"])} AS item_id,
      ${jsonTextExpr(["MSKU", "msku"])} AS msku,
      ${jsonTextExpr(["SKU", "sku"])} AS sku,
      ${jsonTextExpr(["品名", "product_name"])} AS product_name,
      ${jsonTextExpr(["负责人", "owner"])} AS owner,
      ${jsonTextExpr(["产品阶段", "product_stage"])} AS product_stage,
      ${jsonTextExpr(["库存状态", "stock_status"])} AS stock_status,
      ${jsonTextExpr(["成本状态", "cost_status"])} AS cost_status,
      ${jsonTextExpr(["产品等级", "product_level"])} AS product_level,
      ${jsonNumberExpr(["今日销量", "sales_qty"])} AS sales_qty,
      ${jsonNumberExpr(["今日销售额（$）", "sales_amount"])} AS sales_amount,
      ${jsonNumberExpr(["广告花费（$）", "ad_spend"])} AS ad_spend,
      ${jsonNumberExpr(["毛利润（$）", "gross_profit"])} AS gross_profit,
      ${jsonNumberExpr(["WFS可售库存", "wfs_stock"])} AS wfs_stock,
      ${jsonNumberExpr(["非WFS库存", "non_wfs_stock"])} AS non_wfs_stock,
      ${jsonNumberExpr(["在途库存", "in_transit_stock"])} AS in_transit_stock
    FROM raw_feishu_table
    WHERE ${rawWhere}
  `;

  const aggregateSql = `
    SELECT
      store_name,
      ${latestValue("store_id")} AS store_id,
      item_id,
      msku,
      ${latestValue("sku")} AS sku,
      ${latestValue("product_name")} AS product_name,
      ${latestValue("owner")} AS owner,
      COALESCE(${latestValue("product_stage")}, '') AS product_stage,
      ${latestValue("cost_status")} AS cost_status,
      ${latestValue("product_level")} AS product_level,
      COUNT(DISTINCT row_date) AS date_count,
      SUM(CASE WHEN sales_qty > 0 THEN 1 ELSE 0 END) AS sales_days,
      SUM(sales_qty) AS total_sales_qty,
      ROUND(SUM(sales_qty) / NULLIF(COUNT(DISTINCT row_date), 0), 2) AS avg_daily_sales_qty,
      ROUND(SUM(sales_amount), 2) AS total_sales_amount,
      ROUND(SUM(ad_spend), 2) AS total_ad_spend,
      ROUND(SUM(gross_profit), 2) AS total_gross_profit,
      ROUND(CASE WHEN SUM(sales_amount) > 0 THEN SUM(gross_profit) / SUM(sales_amount) * 100 ELSE 0 END, 2) AS gross_margin_pct,
      ROUND(CASE WHEN SUM(sales_amount) > 0 THEN SUM(ad_spend) / SUM(sales_amount) * 100 ELSE 0 END, 2) AS ad_ratio_pct,
      CAST(${latestValue("wfs_stock")} AS DECIMAL(18,2)) AS latest_wfs_stock,
      CAST(${latestValue("non_wfs_stock")} AS DECIMAL(18,2)) AS latest_non_wfs_stock,
      CAST(${latestValue("in_transit_stock")} AS DECIMAL(18,2)) AS latest_in_transit_stock,
      CASE WHEN CAST(${latestValue("wfs_stock")} AS DECIMAL(18,2)) > 0 THEN '有库存' ELSE '无库存' END AS latest_stock_status
    FROM (${baseSql}) base
    WHERE item_id IS NOT NULL AND item_id != '' AND msku IS NOT NULL AND msku != ''
    GROUP BY store_name, item_id, msku
  `;

  // 任务H-1D：为每个聚合行解析单个 product_management_status（标量子查询，避免 LEFT JOIN 行数放大）。
  // 匹配 dim_product：platform + item_id + msku +（store_id 优先，store_id 缺失时经 dim_store 用 store_name 兜底）。
  // 无法匹配则为 NULL（默认保留）。
  const aggregateWithPmSql = `
    SELECT agg0.*,
      (SELECT p.product_management_status
         FROM dim_product p
        WHERE p.platform = 'walmart'
          AND p.item_id = agg0.item_id
          AND COALESCE(p.msku, '') = COALESCE(agg0.msku, '')
          AND (
            (COALESCE(agg0.store_id, '') <> '' AND p.store_id = agg0.store_id)
            OR (COALESCE(agg0.store_id, '') = '' AND EXISTS (
                  SELECT 1 FROM dim_store ds
                   WHERE ds.platform = 'walmart'
                     AND ds.store_name = agg0.store_name
                     AND ds.store_id = p.store_id))
          )
        LIMIT 1) AS product_management_status,
      (SELECT p2.owner
         FROM dim_product p2
        WHERE p2.platform = 'walmart'
          AND p2.item_id = agg0.item_id
          AND COALESCE(p2.msku, '') = COALESCE(agg0.msku, '')
          AND (
            (COALESCE(agg0.store_id, '') <> '' AND p2.store_id = agg0.store_id)
            OR (COALESCE(agg0.store_id, '') = '' AND EXISTS (
                  SELECT 1 FROM dim_store ds2
                   WHERE ds2.platform = 'walmart'
                     AND ds2.store_name = agg0.store_name
                     AND ds2.store_id = p2.store_id))
          )
        LIMIT 1) AS current_owner,
      COALESCE(invl.wfs_available_stock, 0) AS live_wfs_stock,
      GREATEST(COALESCE(invl.available_stock, 0) - COALESCE(invl.wfs_available_stock, 0), 0) AS live_non_wfs_stock,
      CASE WHEN COALESCE(invl.wfs_available_stock, 0) > 0 THEN '有库存' ELSE '无库存' END AS live_stock_status
    FROM (${aggregateSql}) agg0
    LEFT JOIN fact_inventory_daily invl
      ON invl.platform = 'walmart'
     AND invl.snapshot_date = (SELECT MAX(snapshot_date) FROM fact_inventory_daily WHERE platform = 'walmart')
     AND invl.item_id = agg0.item_id
     AND COALESCE(invl.msku, '') = COALESCE(agg0.msku, '')
     AND (
       (COALESCE(agg0.store_id, '') <> '' AND invl.store_id = agg0.store_id)
       OR (COALESCE(agg0.store_id, '') = '' AND invl.store_name = agg0.store_name)
     )
  `;
  // 2026-07-20 拍板：库存三列中 WFS/非WFS 改"最新快照实值"（invl联最新snapshot_date），
  // RAW口径的 latest_wfs_stock/latest_non_wfs_stock 保留不删；在途库存仍取RAW。

  const outerConditions: string[] = [];
  const outerParams: (string | number)[] = [];
  // 负责人口径修复(2026-07-11)：按当前 dim_product.owner 筛商品，保留该商品窗口内全部 RAW 行
  {
    // 2026-07-17 多选负责人（口径不变：聚合后按当前 dim_product.owner 过滤）
    const owners = parseMultiText(owner);
    if (owners.length) {
      outerConditions.push(`TRIM(COALESCE(current_owner, '')) IN (${inPlaceholders(owners.length)})`);
      outerParams.push(...owners);
    }
  }
  if (stockStatus) {
    outerConditions.push("live_stock_status = ?");
    outerParams.push(stockStatus);
  }
  if (productStage) {
    outerConditions.push("COALESCE(product_stage, '') = ?");
    outerParams.push(productStage);
  }
  if (costStatus) {
    if (costStatus === "完整") {
      outerConditions.push("cost_status = ?");
      outerParams.push(costStatus);
    } else {
      outerConditions.push("cost_status LIKE ?");
      outerParams.push(`%${costStatus}%`);
    }
  }
  if (grossMin !== null) {
    outerConditions.push("gross_margin_pct >= ?");
    outerParams.push(grossMin);
  }
  if (grossMax !== null) {
    outerConditions.push("gross_margin_pct <= ?");
    outerParams.push(grossMax);
  }
  if (adMin !== null) {
    outerConditions.push("ad_ratio_pct >= ?");
    outerParams.push(adMin);
  }
  if (adMax !== null) {
    outerConditions.push("ad_ratio_pct <= ?");
    outerParams.push(adMax);
  }
  // 任务H-1D：默认排除 archived；product_management_status=all 时包含。无法匹配(NULL)默认保留。
  if (pmStatus !== "all") {
    outerConditions.push("(product_management_status IS NULL OR product_management_status <> 'archived')");
  }

  const outerWhere = outerConditions.length ? `WHERE ${outerConditions.join(" AND ")}` : "";
  const orderBySql = resolveSortSql(
    sortField,
    sortOrder,
    {
      total_sales_amount: "total_sales_amount",
      total_sales_qty: "total_sales_qty",
      total_gross_profit: "total_gross_profit",
      gross_margin_pct: "gross_margin_pct",
      total_ad_spend: "total_ad_spend",
      ad_ratio_pct: "ad_ratio_pct",
    },
    "total_sales_amount DESC, total_sales_qty DESC, item_id ASC",
  );
  const stateJoinSql = `
    LEFT JOIN dim_product_business_state bs
      ON bs.platform='walmart'
     AND bs.stat_date=(SELECT MAX(stat_date) FROM dim_product_business_state WHERE platform='walmart')
     AND bs.item_id=agg.item_id
     AND COALESCE(bs.msku, '')=COALESCE(agg.msku, '')
     AND (
       (COALESCE(agg.store_id, '') <> '' AND bs.store_id=agg.store_id)
       OR (COALESCE(agg.store_id, '') = '' AND bs.store_name=agg.store_name)
     )
  `;
  const db = await getDb();

  try {
    const [metaRows] = await db.query<mysql.RowDataPacket[]>(
      `SELECT COUNT(*) AS total, MAX(pulled_at) AS latest_sync_time
       FROM raw_feishu_table
       WHERE ${rawWhere}`,
      rawParams,
    );
    const latest = metaRows[0]?.latest_sync_time ?? null;

    const [countRows] = await db.query<mysql.RowDataPacket[]>(
      `SELECT COUNT(*) AS total FROM (${aggregateWithPmSql}) agg ${outerWhere}`,
      [...rawParams, ...outerParams],
    );
    const total = Number(countRows[0]?.total ?? 0);

    const [totalsRows] = await db.query<mysql.RowDataPacket[]>(
      `SELECT
         SUM(date_count) AS d, SUM(sales_days) AS sd, SUM(total_sales_qty) AS q,
         SUM(avg_daily_sales_qty) AS avg_q, SUM(total_sales_amount) AS s,
         SUM(total_ad_spend) AS a, SUM(total_gross_profit) AS g,
         SUM(live_wfs_stock) AS wfs, SUM(live_non_wfs_stock) AS non_wfs,
         SUM(latest_in_transit_stock) AS in_transit
       FROM (${aggregateWithPmSql}) agg ${outerWhere}`,
      [...rawParams, ...outerParams],
    );

    const [dataRows] = await db.query<mysql.RowDataPacket[]>(
      `SELECT
         agg.*,
         bs.product_type,
         bs.profit_level,
         bs.lifecycle_stage,
         bs.system_lifecycle_stage,
         bs.inventory_status AS business_inventory_status,
         bs.inventory_turnover_days,
         bs.ad_status,
         bs.problem_tags,
         DATE_FORMAT(bs.launch_date, '%Y-%m-%d') AS launch_date,
         DATE_FORMAT(bs.stat_date, '%Y-%m-%d') AS state_as_of
       FROM (${aggregateWithPmSql}) agg
       ${stateJoinSql}
       ${outerWhere}
       ORDER BY ${orderBySql}
       LIMIT ? OFFSET ?`,
      [...rawParams, ...outerParams, pageSize, offset],
    );

    const columns = [
      "店铺", "商品ID", "MSKU", "SKU", "品名", "负责人",
      "日期范围", "统计天数", "有销量天数", "累计销量", "日均销量",
      "累计销售额（$）", "累计广告费（$）", "累计毛利润（$）",
      "毛利率", "广告占比", "最新WFS库存", "最新非WFS库存",
      "在途库存", "库存状态", "成本状态",
      "产品类型", "利润等级", "生命周期", "经营库存状态",
      "库存周转天数", "广告状态", "问题标签", "上架时间", "状态日期",
    ];

    const rows = dataRows.map((r) => ({
      "店铺": String(r.store_name ?? ""),
      "商品ID": String(r.item_id ?? ""),
      "MSKU": String(r.msku ?? ""),
      "SKU": String(r.sku ?? ""),
      "品名": String(r.product_name ?? ""),
      // 负责人口径修复(2026-07-11)：优先展示当前 dim_product.owner，为空回退 RAW 历史负责人
      "负责人": String(r.current_owner ?? r.owner ?? ""),
      "日期范围": `${dateStart}~${dateEnd}`,
      "统计天数": String(r.date_count ?? 0),
      "有销量天数": String(r.sales_days ?? 0),
      "累计销量": formatNumber(r.total_sales_qty, 0),
      "日均销量": formatNumber(r.avg_daily_sales_qty, 2),
      "累计销售额（$）": formatNumber(r.total_sales_amount, 2),
      "累计广告费（$）": formatNumber(r.total_ad_spend, 2),
      "累计毛利润（$）": formatNumber(r.total_gross_profit, 2),
      "毛利率": formatPct(r.gross_margin_pct),
      "广告占比": formatPct(r.ad_ratio_pct),
      "最新WFS库存": formatNumber(r.live_wfs_stock, 0),
      "最新非WFS库存": formatNumber(r.live_non_wfs_stock, 0),
      "在途库存": formatNumber(r.latest_in_transit_stock, 0),
      "库存状态": String(r.live_stock_status ?? ""),
      "成本状态": String(r.cost_status ?? ""),
      "产品类型": blankToDash(r.product_type),
      "利润等级": blankToDash(r.profit_level),
      "生命周期": blankToDash(r.lifecycle_stage),
      "经营库存状态": blankToDash(r.business_inventory_status),
      "库存周转天数": r.inventory_turnover_days === null || r.inventory_turnover_days === undefined ? "-" : formatNumber(r.inventory_turnover_days, 1),
      "广告状态": blankToDash(r.ad_status),
      "问题标签": jsonArrayText(r.problem_tags),
      "上架时间": blankToDash(formatDateOnly(r.launch_date)),
      "状态日期": blankToDash(formatDateOnly(r.state_as_of)),
    }));

    // 合计行（2026-07-17 领星式）：筛选后聚合全量口径，比率按汇总重算
    const tt = totalsRows[0] ?? {};
    const tSales = Number(tt.s ?? 0);
    const tProfit = Number(tt.g ?? 0);
    const tAd = Number(tt.a ?? 0);
    const totals: Record<string, string> = {
      "统计天数": formatNumber(tt.d, 0),
      "有销量天数": formatNumber(tt.sd, 0),
      "累计销量": formatNumber(tt.q, 0),
      "日均销量": formatNumber(tt.avg_q, 2),
      "累计销售额（$）": formatNumber(tSales, 2),
      "累计广告费（$）": formatNumber(tAd, 2),
      "累计毛利润（$）": formatNumber(tProfit, 2),
      "毛利率": tSales > 0 ? `${(tProfit / tSales * 100).toFixed(2)}%` : "-",
      "广告占比": tSales > 0 ? `${(tAd / tSales * 100).toFixed(2)}%` : "-",
      "最新WFS库存": formatNumber(tt.wfs, 0),
      "最新非WFS库存": formatNumber(tt.non_wfs, 0),
      "在途库存": formatNumber(tt.in_transit, 0),
    };

    res.json({
      sheet_id: ORDER_PROFIT_SHEET_ID,
      sheet_name: "订单利润 Beta",
      columns,
      rows,
      total,
      page,
      page_size: pageSize,
      latest_sync_time: latest,
      totals,
    });
  } catch (err) {
    res.status(500).json({ error: String(err) });
  } finally {
    await db.end();
  }
});

// ── GET /cs-test-analysis ─────────────────────────────────────────────────────

router.get("/cs-test-analysis", async (req: Request, res: Response): Promise<void> => {
  const page = Math.max(1, Number(req.query.page ?? 1));
  // 2026-07-20 下载导出：携带有效导出令牌时放宽单页上限（普通请求仍封顶200）
  const exportCap = isValidExportToken(String(req.query.export_token ?? "").trim()) ? exportMaxRows() : 200;
  const pageSize = Math.min(exportCap, Math.max(1, Number(req.query.page_size ?? 50)));
  const offset = (page - 1) * pageSize;
  const sortField = requiredText(req.query.sort_field);
  const sortOrder = normalizeSortOrder(req.query.sort_order);

  const keyword = String(req.query.keyword ?? "").trim();
  const sku = String(req.query.sku ?? "").trim();
  const msku = String(req.query.msku ?? "").trim();
  const itemId = String(req.query.item_id ?? "").trim();
  const storeName = String(req.query.store_name ?? "").trim();
  const owner = String(req.query.owner ?? "").trim();
  const stockStatus = String(req.query.stock_status ?? "").trim();
  const dataStatus = String(req.query.cost_status ?? "").trim();
  const adMinRaw = req.query.ad_ratio_min;
  const adMaxRaw = req.query.ad_ratio_max;

  const defaultDate = businessAvailableDate();
  const dateStart = String(req.query.date_start || defaultDate).trim();
  const dateEnd = String(req.query.date_end || defaultDate).trim();

  const adMin = (adMinRaw !== undefined && adMinRaw !== "") ? Number(adMinRaw) : null;
  const adMax = (adMaxRaw !== undefined && adMaxRaw !== "") ? Number(adMaxRaw) : null;

  const adSpendMinRaw = req.query.ad_spend_min;
  const adSpendMaxRaw = req.query.ad_spend_max;
  const clicksMinRaw = req.query.clicks_min;
  const clicksMaxRaw = req.query.clicks_max;
  const testDaysMinRaw = req.query.test_days_min;
  const testDaysMaxRaw = req.query.test_days_max;

  const adSpendMin = (adSpendMinRaw !== undefined && adSpendMinRaw !== "") ? Number(adSpendMinRaw) : null;
  const adSpendMax = (adSpendMaxRaw !== undefined && adSpendMaxRaw !== "") ? Number(adSpendMaxRaw) : null;
  const clicksMin = (clicksMinRaw !== undefined && clicksMinRaw !== "") ? Number(clicksMinRaw) : null;
  const clicksMax = (clicksMaxRaw !== undefined && clicksMaxRaw !== "") ? Number(clicksMaxRaw) : null;
  const testDaysMin = (testDaysMinRaw !== undefined && testDaysMinRaw !== "") ? Number(testDaysMinRaw) : null;
  const testDaysMax = (testDaysMaxRaw !== undefined && testDaysMaxRaw !== "") ? Number(testDaysMaxRaw) : null;

  const cacheKey = JSON.stringify({
    keyword, sku, msku, itemId, storeName, owner, stockStatus, dataStatus,
    dateStart, dateEnd, adMin, adMax,
    adSpendMin, adSpendMax, clicksMin, clicksMax, testDaysMin, testDaysMax,
    sortField, sortOrder,
  });
  const cached = getFreshCsTestCache(cacheKey);
  if (cached) {
    res.json({
      sheet_id: CS_TEST_SHEET_ID,
      sheet_name: "CS测品分析 Beta",
      columns: CS_TEST_RESPONSE_COLUMNS,
      rows: cached.rows.slice(offset, offset + pageSize),
      total: cached.rows.length,
      page,
      page_size: pageSize,
      latest_sync_time: cached.latestSyncTime,
      totals: csTestTotals(cached.rows),
    });
    return;
  }

  const baseConditions = [
    "base.platform = 'walmart'",
    "base.msku LIKE 'CS%'",
  ];
  const baseParams: (string | number)[] = [];

  if (keyword) {
    baseConditions.push(`(
      base.item_id LIKE ? OR base.msku LIKE ? OR base.sku LIKE ? OR base.product_name LIKE ? OR base.store_name LIKE ? OR base.owner LIKE ?
    )`);
    baseParams.push(`%${keyword}%`, `%${keyword}%`, `%${keyword}%`, `%${keyword}%`, `%${keyword}%`, `%${keyword}%`);
  }
  if (sku) {
    baseConditions.push("base.sku LIKE ?");
    baseParams.push(`%${sku}%`);
  }
  if (msku) {
    baseConditions.push("base.msku LIKE ?");
    baseParams.push(`%${msku}%`);
  }
  if (itemId) {
    baseConditions.push("base.item_id LIKE ?");
    baseParams.push(`%${itemId}%`);
  }
  {
    // 2026-07-17 多选店铺/负责人
    const storeNames = parseMultiText(storeName);
    if (storeNames.length) {
      baseConditions.push(`base.store_name IN (${inPlaceholders(storeNames.length)})`);
      baseParams.push(...storeNames);
    }
    const owners = parseMultiText(owner);
    if (owners.length) {
      const ph = inPlaceholders(owners.length);
      baseConditions.push(`(base.owner IN (${ph}) OR owner_map.owner IN (${ph}))`);
      baseParams.push(...owners, ...owners);
    }
  }

  const baseWhere = baseConditions.join(" AND ");

  const db = await getDb();
  let productNameExpr = "COALESCE(product_name, '')";
  try {
    const [columnRows] = await db.query<mysql.RowDataPacket[]>(
      `SELECT COLUMN_NAME
       FROM INFORMATION_SCHEMA.COLUMNS
       WHERE TABLE_SCHEMA = DATABASE()
         AND TABLE_NAME = 'dim_product'
         AND COLUMN_NAME IN ('product_name', 'item_name')`,
    );
    const dimProductColumns = new Set(columnRows.map((row) => String(row.COLUMN_NAME)));
    productNameExpr = dimProductColumns.has("item_name")
      ? "COALESCE(product_name, item_name, '')"
      : "COALESCE(product_name, '')";
  } catch {
    productNameExpr = "COALESCE(product_name, '')";
  }

  const aggregateSql = `
    SELECT
      base.store_id,
      base.store_name,
      base.item_id,
      base.msku,
      base.sku,
      base.product_name,
      COALESCE(NULLIF(owner_map.owner, ''), NULLIF(base.owner, ''), '') AS owner,
      first_ad.first_ad_date AS first_ad_date,
      CASE
          WHEN first_ad.first_ad_date IS NULL THEN NULL
          WHEN COALESCE(inv.latest_non_wfs_stock, 0) > 0 THEN NULL
          WHEN inv.last_gt0_date IS NOT NULL AND DATE_ADD(inv.last_gt0_date, INTERVAL 1 DAY) >= first_ad.first_ad_date THEN DATE_FORMAT(DATE_ADD(inv.last_gt0_date, INTERVAL 1 DAY), '%Y-%m-%d')
          WHEN first_ad.first_ad_date <= '${CS_TEST_HISTORICAL_END_DATE}' THEN '${CS_TEST_HISTORICAL_END_DATE}'
          WHEN first_ad.first_ad_date <= '2026-07-21' THEN '2026-07-21'
          WHEN first_ad.last_ad_date IS NOT NULL THEN DATE_FORMAT(first_ad.last_ad_date, '%Y-%m-%d')
          ELSE NULL
        END AS test_end_date,
      CASE
          WHEN first_ad.first_ad_date IS NULL THEN 0
          WHEN COALESCE(inv.latest_non_wfs_stock, 0) <= 0 AND inv.last_gt0_date IS NOT NULL AND DATE_ADD(inv.last_gt0_date, INTERVAL 1 DAY) >= first_ad.first_ad_date THEN DATEDIFF(DATE_ADD(inv.last_gt0_date, INTERVAL 1 DAY), first_ad.first_ad_date) + 1
          WHEN COALESCE(inv.latest_non_wfs_stock, 0) <= 0 AND first_ad.first_ad_date <= '${CS_TEST_HISTORICAL_END_DATE}' THEN DATEDIFF('${CS_TEST_HISTORICAL_END_DATE}', first_ad.first_ad_date) + 1
          WHEN COALESCE(inv.latest_non_wfs_stock, 0) <= 0 AND first_ad.first_ad_date <= '2026-07-21' THEN DATEDIFF('2026-07-21', first_ad.first_ad_date) + 1
          WHEN COALESCE(inv.latest_non_wfs_stock, 0) <= 0 AND first_ad.last_ad_date IS NOT NULL THEN DATEDIFF(first_ad.last_ad_date, first_ad.first_ad_date) + 1
          WHEN COALESCE(inv.latest_non_wfs_stock, 0) <= 0 THEN NULL
          ELSE DATEDIFF(?, first_ad.first_ad_date) + 1
        END AS test_days,
      COALESCE(inv.latest_non_wfs_stock, 0) AS latest_non_wfs_stock,
      COALESCE(s.sales_days, 0) AS sales_days,
      COALESCE(s.total_sales_qty, 0) AS total_sales_qty,
      ROUND(CASE
          WHEN first_ad.first_ad_date IS NULL THEN 0
          WHEN COALESCE(inv.latest_non_wfs_stock, 0) <= 0 AND inv.last_gt0_date IS NOT NULL AND DATE_ADD(inv.last_gt0_date, INTERVAL 1 DAY) >= first_ad.first_ad_date THEN COALESCE(s.total_sales_qty, 0) / NULLIF(DATEDIFF(DATE_ADD(inv.last_gt0_date, INTERVAL 1 DAY), first_ad.first_ad_date) + 1, 0)
          WHEN COALESCE(inv.latest_non_wfs_stock, 0) <= 0 AND first_ad.first_ad_date <= '${CS_TEST_HISTORICAL_END_DATE}' THEN COALESCE(s.total_sales_qty, 0) / NULLIF(DATEDIFF('${CS_TEST_HISTORICAL_END_DATE}', first_ad.first_ad_date) + 1, 0)
          WHEN COALESCE(inv.latest_non_wfs_stock, 0) <= 0 AND first_ad.first_ad_date <= '2026-07-21' THEN COALESCE(s.total_sales_qty, 0) / NULLIF(DATEDIFF('2026-07-21', first_ad.first_ad_date) + 1, 0)
          WHEN COALESCE(inv.latest_non_wfs_stock, 0) <= 0 AND first_ad.last_ad_date IS NOT NULL THEN COALESCE(s.total_sales_qty, 0) / NULLIF(DATEDIFF(first_ad.last_ad_date, first_ad.first_ad_date) + 1, 0)
          WHEN COALESCE(inv.latest_non_wfs_stock, 0) <= 0 THEN NULL
          ELSE COALESCE(s.total_sales_qty, 0) / NULLIF(DATEDIFF(?, first_ad.first_ad_date) + 1, 0)
        END, 2) AS avg_daily_sales_qty,
      COALESCE(s.total_orders, 0) AS total_orders,
      ROUND(COALESCE(s.total_sales_amount, 0), 2) AS total_sales_amount,
      ROUND(COALESCE(ad.total_ad_spend, 0), 2) AS total_ad_spend,
      ROUND(CASE WHEN COALESCE(s.total_sales_amount, 0) > 0 THEN COALESCE(ad.total_ad_spend, 0) / s.total_sales_amount * 100 ELSE 0 END, 2) AS ad_ratio_pct,
      COALESCE(ad.impressions, 0) AS impressions,
      COALESCE(ad.clicks, 0) AS clicks,
      ROUND(CASE WHEN COALESCE(ad.impressions, 0) > 0 THEN ad.clicks / ad.impressions * 100 ELSE 0 END, 2) AS ctr_pct,
      ROUND(CASE WHEN COALESCE(ad.clicks, 0) > 0 THEN ad.total_ad_spend / ad.clicks ELSE 0 END, 2) AS cpc,
      COALESCE(ad.ad_orders, 0) AS ad_orders,
      ROUND(COALESCE(ad.ad_sales, 0), 2) AS ad_sales,
      ROUND(CASE WHEN COALESCE(ad.clicks, 0) > 0 THEN ad.ad_orders / ad.clicks * 100 ELSE 0 END, 2) AS cvr_pct,
      ROUND(CASE WHEN COALESCE(ad.ad_sales, 0) > 0 THEN ad.total_ad_spend / ad.ad_sales * 100 ELSE 0 END, 2) AS acos_pct,
      GREATEST(COALESCE(s.total_orders, 0) - COALESCE(ad.ad_orders, 0), 0) AS natural_orders,
      ROUND(CASE WHEN COALESCE(s.total_orders, 0) > 0 THEN GREATEST(s.total_orders - COALESCE(ad.ad_orders, 0), 0) / s.total_orders * 100 ELSE 0 END, 2) AS natural_order_ratio_pct,
      ROUND(COALESCE(s.total_sales_amount, 0) * 0.85 - COALESCE(ad.total_ad_spend, 0) - COALESCE(s.total_sales_amount, 0) - COALESCE(s.total_orders, 0) * 5, 2) AS test_cost,
      CASE
        WHEN first_ad.first_ad_date IS NULL THEN '缺首次广告日期'
        WHEN ad.ad_record_count = 0 THEN '缺广告数据'
        WHEN inv.latest_inventory_date IS NULL THEN '缺库存数据'
        ELSE '正常'
      END AS data_status,
      CASE WHEN COALESCE(inv.latest_non_wfs_stock, 0) > 0 THEN '有库存' ELSE '无库存' END AS stock_status
    FROM (
      SELECT
        platform,
        store_id,
        SUBSTRING_INDEX(GROUP_CONCAT(NULLIF(store_name, '') ORDER BY source_priority ASC, source_date DESC SEPARATOR '|||'), '|||', 1) AS store_name,
        item_id,
        msku,
        SUBSTRING_INDEX(GROUP_CONCAT(NULLIF(sku, '') ORDER BY source_priority ASC, source_date DESC SEPARATOR '|||'), '|||', 1) AS sku,
        SUBSTRING_INDEX(GROUP_CONCAT(NULLIF(product_name, '') ORDER BY source_priority ASC, source_date DESC SEPARATOR '|||'), '|||', 1) AS product_name,
        SUBSTRING_INDEX(GROUP_CONCAT(NULLIF(owner, '') ORDER BY source_priority ASC, source_date DESC SEPARATOR '|||'), '|||', 1) AS owner,
        SUBSTRING_INDEX(GROUP_CONCAT(NULLIF(launch_date, '') ORDER BY source_priority ASC, source_date DESC SEPARATOR '|||'), '|||', 1) AS launch_date
      FROM (
        SELECT
          1 AS source_priority,
          updated_at AS source_date,
          platform,
          store_id,
          store_name,
          item_id,
          msku,
          sku,
          ${productNameExpr} AS product_name,
          owner,
          DATE_FORMAT(launch_date, '%Y-%m-%d') AS launch_date
        FROM dim_product
        WHERE platform = 'walmart' AND msku LIKE 'CS%'
        UNION ALL
        SELECT
          2 AS source_priority,
          stat_date AS source_date,
          platform,
          store_id,
          store_name,
          item_id,
          msku,
          sku,
          '' AS product_name,
          '' AS owner,
          '' AS launch_date
        FROM fact_sales_daily
        WHERE platform = 'walmart' AND msku LIKE 'CS%' AND stat_date >= ? AND stat_date <= ?
        UNION ALL
        SELECT
          3 AS source_priority,
          snapshot_date AS source_date,
          platform,
          store_id,
          store_name,
          item_id,
          msku,
          sku,
          '' AS product_name,
          '' AS owner,
          '' AS launch_date
        FROM fact_inventory_daily
        WHERE platform = 'walmart' AND msku LIKE 'CS%' AND snapshot_date >= ? AND snapshot_date <= ?
      ) base_raw
      GROUP BY platform, store_id, item_id, msku
    ) base
    LEFT JOIN (
      SELECT
        item_id,
        SUBSTRING_INDEX(GROUP_CONCAT(NULLIF(owner_name, '') ORDER BY effective_date DESC, updated_at DESC SEPARATOR '|||'), '|||', 1) AS owner
      FROM dim_product_owner
      WHERE platform = 'walmart' AND status = 'active'
      GROUP BY item_id
    ) owner_map
      ON owner_map.item_id = base.item_id
    LEFT JOIN (
      SELECT store_id, item_id, MIN(stat_date) AS first_ad_date, MAX(stat_date) AS last_ad_date
      FROM fact_ads_product_daily
      WHERE platform = 'walmart' AND ad_spend > 0
      GROUP BY store_id, item_id
    ) first_ad
      ON first_ad.store_id = base.store_id AND first_ad.item_id = base.item_id
    LEFT JOIN (
      SELECT
        store_id,
        item_id,
        MIN(stat_date) AS first_ad_date,
        COUNT(*) AS ad_record_count,
        SUM(impressions) AS impressions,
        SUM(clicks) AS clicks,
        SUM(ad_spend) AS total_ad_spend,
        SUM(orders) AS ad_orders,
        SUM(total_sales) AS ad_sales
      FROM fact_ads_product_daily
      WHERE platform = 'walmart' AND IFNULL(?, '') IS NOT NULL AND IFNULL(?, '') IS NOT NULL /* 2026-07-25 广告改全历史累计(与销售 s 子查询同口径)；两占位仅保参数序 */
      GROUP BY store_id, item_id
    ) ad
      ON ad.store_id = base.store_id AND ad.item_id = base.item_id
    LEFT JOIN (
      SELECT
        store_id,
        item_id,
        msku,
        COUNT(DISTINCT CASE WHEN sales_qty > 0 THEN stat_date END) AS sales_days,
        SUM(sales_qty) AS total_sales_qty,
        SUM(COALESCE(NULLIF(order_count, 0), sales_qty)) AS total_orders,
        SUM(sales_amount) AS total_sales_amount
      FROM fact_sales_daily
      WHERE platform = 'walmart' AND IFNULL(?, '') IS NOT NULL AND IFNULL(?, '') IS NOT NULL /* 2026-07-24 测品累计=全历史；占位仅保参数序 */
      GROUP BY store_id, item_id, msku
    ) s
      ON s.store_id = base.store_id AND s.item_id = base.item_id AND COALESCE(s.msku, '') = COALESCE(base.msku, '')
    LEFT JOIN (
      SELECT
        i.store_id,
        i.item_id,
        i.msku,
        SUBSTRING_INDEX(GROUP_CONCAT(GREATEST(COALESCE(i.non_wfs_available_stock, 0), 0) ORDER BY i.snapshot_date DESC SEPARATOR ','), ',', 1) AS latest_non_wfs_stock,
        MAX(i.snapshot_date) AS latest_inventory_date,
        MAX(CASE WHEN GREATEST(COALESCE(i.non_wfs_available_stock, 0), 0) > 0 THEN i.snapshot_date END) AS last_gt0_date,
        MIN(CASE
          WHEN fa.first_ad_date IS NOT NULL
           AND i.snapshot_date >= fa.first_ad_date
           AND GREATEST(COALESCE(i.non_wfs_available_stock, 0), 0) <= 0
          THEN i.snapshot_date
        END) AS stock_out_date
      FROM fact_inventory_daily i
      LEFT JOIN (
        SELECT store_id, item_id, MIN(stat_date) AS first_ad_date
        FROM fact_ads_product_daily
        WHERE platform = 'walmart' AND ad_spend > 0
        GROUP BY store_id, item_id
      ) fa ON fa.store_id = i.store_id AND fa.item_id = i.item_id
      WHERE i.platform = 'walmart' AND IFNULL(?, '') IS NOT NULL AND IFNULL(?, '') IS NOT NULL /* 2026-07-24 全历史口径：真实归零日+最新库存；占位仅保参数序 */
      GROUP BY i.store_id, i.item_id, i.msku
    ) inv
      ON inv.store_id = base.store_id AND inv.item_id = base.item_id AND COALESCE(inv.msku, '') = COALESCE(base.msku, '')
    WHERE ${baseWhere}
      AND first_ad.first_ad_date IS NOT NULL
      AND first_ad.first_ad_date >= '${CS_TEST_AD_START_DATE}'
  `;

  const aggregateParams: (string | number)[] = [
    dateEnd,           // test_days DATEDIFF 兜底
    dateEnd,           // avg_daily DATEDIFF 兜底
    dateStart, dateEnd, // base fact_sales_daily
    dateStart, dateEnd, // base fact_inventory_daily
    dateStart, dateEnd, // ad 指标窗口
    dateStart, dateEnd, // s 销售窗口
    dateStart, dateEnd, // inv 库存窗口
    ...baseParams,
  ];

  const outerConditions: string[] = [];
  const outerParams: (string | number)[] = [];
  if (stockStatus) {
    outerConditions.push("stock_status = ?");
    outerParams.push(stockStatus);
  }
  if (dataStatus) {
    outerConditions.push("data_status = ?");
    outerParams.push(dataStatus);
  }
  if (adMin !== null) {
    outerConditions.push("ad_ratio_pct >= ?");
    outerParams.push(adMin);
  }
  if (adMax !== null) {
    outerConditions.push("ad_ratio_pct <= ?");
    outerParams.push(adMax);
  }
  if (adSpendMin !== null) {
    outerConditions.push("total_ad_spend >= ?");
    outerParams.push(adSpendMin);
  }
  if (adSpendMax !== null) {
    outerConditions.push("total_ad_spend <= ?");
    outerParams.push(adSpendMax);
  }
  if (clicksMin !== null) {
    outerConditions.push("clicks >= ?");
    outerParams.push(clicksMin);
  }
  if (clicksMax !== null) {
    outerConditions.push("clicks <= ?");
    outerParams.push(clicksMax);
  }
  if (testDaysMin !== null) {
    outerConditions.push("test_days >= ?");
    outerParams.push(testDaysMin);
  }
  if (testDaysMax !== null) {
    outerConditions.push("test_days <= ?");
    outerParams.push(testDaysMax);
  }
  const outerWhere = outerConditions.length ? `WHERE ${outerConditions.join(" AND ")}` : "";
  const orderBySql = resolveSortSql(
    sortField,
    sortOrder,
    {
      first_ad_date: "first_ad_date",
      test_days: "test_days",
      total_ad_spend: "total_ad_spend",
      clicks: "clicks",
      total_sales_amount: "total_sales_amount",
      total_sales_qty: "total_sales_qty",
      non_wfs_inventory: "latest_non_wfs_stock",
      test_end_date: "test_end_date",
      sales_days: "sales_days",
      avg_daily_sales_qty: "avg_daily_sales_qty",
      ad_ratio_pct: "ad_ratio_pct",
      impressions: "impressions",
      ctr_pct: "ctr_pct",
      cpc: "cpc",
      cvr_pct: "cvr_pct",
      acos_pct: "acos_pct",
      natural_orders: "natural_orders",
      natural_order_ratio_pct: "natural_order_ratio_pct",
      ad_orders: "ad_orders",
      ad_sales: "ad_sales",
      test_cost: "test_cost",
    },
    "latest_non_wfs_stock DESC, first_ad_date DESC, item_id ASC",
  );

  try {
    const [dataRows] = await db.query<mysql.RowDataPacket[]>(
      `SELECT * FROM (${aggregateSql}) agg
       ${outerWhere}
       ORDER BY ${orderBySql}`,
      [...aggregateParams, ...outerParams],
    );
    const total = dataRows.length;

    const [latestRows] = await db.query<mysql.RowDataPacket[]>(
      `SELECT MAX(updated_at) AS latest_sync_time
       FROM (
         SELECT updated_at FROM fact_sales_daily WHERE platform='walmart' AND msku LIKE 'CS%' AND stat_date >= ? AND stat_date <= ?
         UNION ALL
         SELECT updated_at FROM fact_inventory_daily WHERE platform='walmart' AND msku LIKE 'CS%' AND snapshot_date >= ? AND snapshot_date <= ?
         UNION ALL
         SELECT updated_at FROM fact_ads_product_daily WHERE platform='walmart' AND stat_date >= ? AND stat_date <= ?
       ) t`,
      [dateStart, dateEnd, dateStart, dateEnd, dateStart, dateEnd],
    );

    const [csAlertRows] = await db.query<mysql.RowDataPacket[]>(
      `SELECT id, store_id, item_id, msku, reason, status FROM biz_cs_test_alert WHERE platform = 'walmart'`,
    );
    const csAlertMap = new Map<string, mysql.RowDataPacket>();
    for (const a of csAlertRows) {
      csAlertMap.set(`${String(a.store_id ?? "")}|${String(a.item_id ?? "")}|${String(a.msku ?? "")}`, a);
    }
    const rows = dataRows.map((r) => {
      const _al = csAlertMap.get(`${String(r.store_id ?? "")}|${String(r.item_id ?? "")}|${String(r.msku ?? "")}`);
      return ({
      "店铺": String(r.store_name ?? ""),
      "商品ID": String(r.item_id ?? ""),
      "MSKU": String(r.msku ?? ""),
      "SKU": String(r.sku ?? ""),
      "负责人": String(r.owner ?? ""),
      "首次广告日期": formatDateOnly(r.first_ad_date),
      "测品结束日期": r.test_end_date === null || r.test_end_date === undefined ? "-" : formatDateOnly(r.test_end_date),
      "测品天数": r.test_days === null || r.test_days === undefined ? "-" : String(r.test_days),
      "非WFS库存": formatNumber(r.latest_non_wfs_stock, 0),
      "累计销量": formatNumber(r.total_sales_qty, 0),
      "有销量天数": String(r.sales_days ?? 0),
      "日均销量": r.avg_daily_sales_qty === null || r.avg_daily_sales_qty === undefined ? "-" : formatNumber(r.avg_daily_sales_qty, 2),
      "累计销售额（$）": formatNumber(r.total_sales_amount, 2),
      "累计广告费（$）": formatNumber(r.total_ad_spend, 2),
      "广告费占比": formatPct2(r.ad_ratio_pct),
      "广告曝光": formatNumber(r.impressions, 0),
      "广告点击": formatNumber(r.clicks, 0),
      "CTR": formatPct2(r.ctr_pct),
      "CPC": formatNumber(r.cpc, 2),
      "CVR": formatPct2(r.cvr_pct),
      "ACOS": formatPct2(r.acos_pct),
      "自然订单数": formatNumber(r.natural_orders, 0),
      "自然订单比例": formatPct2(r.natural_order_ratio_pct),
      "广告订单数": formatNumber(r.ad_orders, 0),
      "广告销售额（$）": formatNumber(r.ad_sales, 2),
      "测款成本": formatNumber(r.test_cost, 2),
      "数据状态": String(r.data_status ?? ""),
      "预警原因": _al ? String(_al.reason ?? "") : "",
      _cs_alert_id: _al ? String(_al.id) : "",
      _cs_alert_editable: _al ? "1" : "",
      _cs_alert_status: _al ? String(_al.status ?? "") : "",
      });
    });
    const latestSyncTime = latestRows[0]?.latest_sync_time ?? null;
    setCsTestCache(cacheKey, { createdAt: Date.now(), rows, latestSyncTime });

    res.json({
      sheet_id: CS_TEST_SHEET_ID,
      sheet_name: "CS测品分析 Beta",
      columns: CS_TEST_RESPONSE_COLUMNS,
      rows: rows.slice(offset, offset + pageSize),
      total,
      page,
      page_size: pageSize,
      latest_sync_time: latestSyncTime,
      totals: csTestTotals(rows),
    });
  } catch (err) {
    res.status(500).json({ error: String(err) });
  } finally {
    await db.end();
  }
});

// ── GET /cs-test-config ───────────────────────────────────────────────────────

// 2026-07-24 CS测品分析「预警原因」页面回填/编辑：写 biz_cs_test_alert.reason（≥15字）→ 消警(resolved) → 清CS缓存
router.post("/cs-test/save-alert-reason", async (req: Request, res: Response): Promise<void> => {
  const alertId = Number(req.body?.alert_id ?? 0);
  const reason = String(req.body?.reason ?? "").trim();
  const filledBy = requiredText(req.body?.filled_by) || "页面填写";
  if (!alertId) { res.status(400).json({ error: "缺少 alert_id" }); return; }
  if (reason.length < 15) { res.status(400).json({ error: `预警原因需不少于 15 字（当前 ${reason.length} 字）` }); return; }
  if (reason.length > 500) { res.status(400).json({ error: "预警原因不超过 500 字" }); return; }
  const db = await getDb();
  try {
    const [rows] = await db.query<mysql.RowDataPacket[]>(
      "SELECT id FROM biz_cs_test_alert WHERE id = ? LIMIT 1", [alertId],
    );
    if (rows.length === 0) { res.status(404).json({ error: `预警记录 #${alertId} 不存在` }); return; }
    await db.beginTransaction();
    await db.query(
      "UPDATE biz_cs_test_alert SET reason = ?, reason_by = ?, reason_at = NOW(), status = 'resolved' WHERE id = ?",
      [reason, filledBy, alertId],
    );
    await db.commit();
    csTestCache.clear();
    res.json({ ok: true, alert_id: alertId, reason });
  } catch (err) {
    try { await db.rollback(); } catch { /* ignore */ }
    res.status(500).json({ error: String(err) });
  } finally {
    await db.end();
  }
});

router.get("/cs-test-config", async (_req: Request, res: Response): Promise<void> => {
  const defaults = [
    { config_type: "基础规则", config_key: "MSKU前缀", config_value: "CS", description: "只分析 MSKU 以 CS 开头的自发货测品产品", enabled: 1 },
    { config_type: "成本规则", config_key: "平台扣点", config_value: "0.15", description: "测款成本按总销售额扣 15% 计算", enabled: 1 },
    { config_type: "成本规则", config_key: "单订单测品履约成本", config_value: "5", description: "每个订单固定扣 5 美元", enabled: 1 },
    { config_type: "公式", config_key: "测款成本", config_value: "总销售额*0.85-广告费-总销售额-订单量*5", description: "该值通常为负数，用于衡量测款消耗", enabled: 1 },
    { config_type: "周期规则", config_key: "测品天数", config_value: "首次广告日期~非WFS库存为0日期", description: "未归零时计算到查询结束日期", enabled: 1 },
    { config_type: "数据来源", config_key: "库存数据", config_value: "fact_inventory_daily.non_wfs_available_stock", description: "CS自发货非WFS库存、库存为0日期来自领星 available_quantity（非WFS可售）", enabled: 1 },
  ];

  const db = await getDb();
  try {
    const [rows] = await db.query<mysql.RowDataPacket[]>(
      `SELECT config_type, config_key, config_value, description, enabled
       FROM cs_test_product_config
       WHERE enabled = 1
       ORDER BY id ASC`,
    );
    res.json({ rows: rows.length ? rows : defaults, fallback: rows.length === 0 });
  } catch {
    res.json({ rows: defaults, fallback: true });
  } finally {
    await db.end();
  }
});

// ── GET /sync-tasks ───────────────────────────────────────────────────────────

router.get("/sync-tasks", async (_req: Request, res: Response): Promise<void> => {
  const db = await getDb();
  try {
    const [rows] = await db.query<mysql.RowDataPacket[]>(
      `SELECT sync_task_id, source_type, source_name, sheet_id, sheet_name,
              status, row_count, inserted_count, updated_count, skipped_count,
              started_at, finished_at, error_message
       FROM raw_sync_tasks
       WHERE source_type = 'feishu' AND source_name = 'sales_feishu_4_sheets'
       ORDER BY started_at DESC
       LIMIT 100`,
    );
    res.json(rows);
  } catch (err) {
    res.status(500).json({ error: String(err) });
  } finally {
    await db.end();
  }
});

// ── POST /sync ────────────────────────────────────────────────────────────────

router.post("/sync", async (_req: Request, res: Response): Promise<void> => {
  res.status(410).json({
    error: "飞书 Sheet 原始数据同步已停用；该页面只读取 MySQL 中已有数据，不再调用飞书接口写入 raw_feishu_table。",
  });
});

// ── GET /operation-log （任务H-Stage 2 运营日志 只读）────────────────────────
// 只读展示 biz_product_operation_log + 关联系统规则信号 biz_product_rule_signal_daily。
// 默认排除 archived（LEFT JOIN dim_product 判断）；无写入/编辑/保存接口。
router.get("/operation-log", async (req: Request, res: Response): Promise<void> => {
  const OPERATION_LOG_SHEET_ID = "operation_log";
  const page = Math.max(1, Number(req.query.page ?? 1));
  // 2026-07-20 下载导出：携带有效导出令牌时放宽单页上限（普通请求仍封顶200）
  const exportCap = isValidExportToken(String(req.query.export_token ?? "").trim()) ? exportMaxRows() : 200;
  const pageSize = Math.min(exportCap, Math.max(1, Number(req.query.page_size ?? 50)));
  const offset = (page - 1) * pageSize;

  const explicitDate = String(req.query.date ?? "").trim();
  const dateStart = String(req.query.date_start ?? "").trim();
  const dateEnd = String(req.query.date_end ?? "").trim();
  const owner = String(req.query.owner ?? "").trim();
  const store = String(req.query.store_name ?? req.query.store ?? "").trim();
  const keyword = String(req.query.keyword ?? "").trim();
  const msku = String(req.query.msku ?? "").trim();
  const itemId = String(req.query.item_id ?? "").trim();
  const profitLevel = String(req.query.profit_level ?? "").trim();
  const ruleLevel = String(req.query.rule_level ?? "").trim();
  const ruleCode = String(req.query.rule_code ?? "").trim();
  const hasRule = String(req.query.has_rule ?? "").trim().toLowerCase();
  const includeArchived = ["1", "true"].includes(String(req.query.include_archived ?? "").trim().toLowerCase());
  const productType = String(req.query.product_type ?? req.query.product_stage ?? "").trim();
  // 2026-07-15 新增筛选与排序（近30天口径列）
  const logFilled = String(req.query.log_filled ?? "").trim();
  const wfsStock = String(req.query.wfs_stock ?? "").trim();
  const adRatioMin = String(req.query.ad_ratio_min ?? "").trim();
  const adRatioMax = String(req.query.ad_ratio_max ?? "").trim();
  const sortField = String(req.query.sort_field ?? "").trim();
  const sortOrder = String(req.query.sort_order ?? "").trim().toLowerCase();

  const db = await getDb();
  try {
    const [latestRows] = await db.query<mysql.RowDataPacket[]>(
      "SELECT DATE_FORMAT(MAX(log_date), '%Y-%m-%d') AS d FROM biz_product_operation_log WHERE platform='walmart'",
    );
    const latestLogDate: string | null = latestRows[0]?.d ?? null;

    const fromJoin = `
      FROM biz_product_operation_log l
      LEFT JOIN dim_product p
        ON p.platform=l.platform AND p.store_id=l.store_id AND p.item_id=l.item_id AND p.msku=l.msku`;

    const ruleExistsSql = (extra: string) =>
      `EXISTS (SELECT 1 FROM biz_product_rule_signal_daily s
                WHERE s.signal_date=l.log_date AND s.platform=l.platform AND s.store_key=l.store_key
                  AND s.item_id=l.item_id AND s.msku=l.msku ${extra})`;

    // 默认视图取最近 7 个 log_date；有窄化筛选则不限日期（全历史）；显式日期最优先。
    const [recentDateRows] = await db.query<mysql.RowDataPacket[]>(
      "SELECT DISTINCT DATE_FORMAT(log_date,'%Y-%m-%d') AS d FROM biz_product_operation_log WHERE platform='walmart' ORDER BY d DESC LIMIT 7",
    );
    const recentDates = recentDateRows.map((r) => String(r.d));
    // 2026-07-15 修正：新三项筛选（已填/未填、WFS库存、广告占比）为视图细化，
    // 不触发"窄化筛选→全历史"窗口切换，保持默认 recent7（守恒：分组total之和=总total）
    const hasNarrowFilter = Boolean(owner || store || keyword || msku || itemId || profitLevel || ruleLevel || ruleCode || hasRule);

    const conds: string[] = ["l.platform='walmart'"];
    const params: (string | number)[] = [];
    let usedLogDate: string;
    if (explicitDate) {
      conds.push("l.log_date = ?"); params.push(explicitDate); usedLogDate = explicitDate;
    } else if (dateStart) {
      conds.push("l.log_date >= ?"); params.push(dateStart);
      conds.push("l.log_date <= ?"); params.push(dateEnd || dateStart);
      usedLogDate = `${dateStart}~${dateEnd || dateStart}`;
    } else if (hasNarrowFilter) {
      usedLogDate = "all"; // 有窄化筛选：全历史，不限日期
    } else if (recentDates.length > 0) {
      conds.push(`l.log_date IN (${recentDates.map(() => "?").join(",")})`);
      for (const d of recentDates) params.push(d);
      usedLogDate = `recent7:${recentDates[recentDates.length - 1]}~${recentDates[0]}`;
    } else {
      conds.push("1=0"); usedLogDate = "none";
    }
    // 2026-07-17 多选负责人/店铺
    {
      const owners = parseMultiText(owner);
      if (owners.length) {
        conds.push(`l.owner IN (${inPlaceholders(owners.length)})`);
        params.push(...owners);
      }
      const stores = parseMultiText(store);
      if (stores.length) {
        const ph = inPlaceholders(stores.length);
        conds.push(`(l.store_name IN (${ph}) OR l.store_id IN (${ph}))`);
        params.push(...stores, ...stores);
      }
    }
    if (keyword) { const k = `%${keyword}%`; conds.push("(l.item_id LIKE ? OR l.msku LIKE ? OR l.store_name LIKE ?)"); params.push(k, k, k); }
    if (msku) { conds.push("l.msku LIKE ?"); params.push(`%${msku}%`); }
    if (itemId) { conds.push("l.item_id LIKE ?"); params.push(`%${itemId}%`); }
    if (profitLevel) { conds.push("l.profit_level_snapshot = ?"); params.push(profitLevel); }
    if (productType === "CS测品") { conds.push("l.msku LIKE 'CS%'"); }
    if (productType === "常规产品") { conds.push("l.msku NOT LIKE 'CS%'"); }
    if (!includeArchived) { conds.push("(p.product_management_status IS NULL OR p.product_management_status <> 'archived')"); }
    if (ruleLevel) { conds.push(ruleExistsSql("AND s.rule_level = ?")); params.push(ruleLevel); }
    if (ruleCode) { conds.push(ruleExistsSql("AND s.rule_code = ?")); params.push(ruleCode); }
    if (hasRule === "1" || hasRule === "true") conds.push(ruleExistsSql(""));
    if (hasRule === "0" || hasRule === "false") conds.push(`NOT ${ruleExistsSql("")}`);
    // 2026-07-15：已填/未填（"今日无运营"也算已填）；WFS有无库存与广告占比引用指标联结
    let needMetricJoin = false;
    if (logFilled === "1") conds.push("COALESCE(l.log_content,'') <> ''");
    if (logFilled === "0") conds.push("COALESCE(l.log_content,'') = ''");
    if (wfsStock === "has") { conds.push("COALESCE(iv.wfs_stock,0) > 0"); needMetricJoin = true; }
    if (wfsStock === "none") { conds.push("COALESCE(iv.wfs_stock,0) = 0"); needMetricJoin = true; }
    if (adRatioMin !== "" && Number.isFinite(Number(adRatioMin))) {
      conds.push("bs.ad_ratio_30d IS NOT NULL AND bs.ad_ratio_30d * 100 >= ?"); params.push(Number(adRatioMin)); needMetricJoin = true;
    }
    if (adRatioMax !== "" && Number.isFinite(Number(adRatioMax))) {
      conds.push("bs.ad_ratio_30d IS NOT NULL AND bs.ad_ratio_30d * 100 <= ?"); params.push(Number(adRatioMax)); needMetricJoin = true;
    }
    const where = conds.join(" AND ");

    // 2026-07-15 加列（需求方A案·近30天口径）：business_state 现成30天字段 + 30天销量件数 + 最新WFS库存
    // 毛利率/广告占比在库中为小数分数（buildProductBusinessState 代码证据）
    const fromJoinData = `${fromJoin}
      LEFT JOIN (
        SELECT store_id, item_id, msku, sales_30d, gross_profit_30d, profit_rate_30d,
               ad_spend_30d, ad_ratio_30d
        FROM dim_product_business_state
        WHERE platform='walmart'
          AND stat_date=(SELECT MAX(stat_date) FROM dim_product_business_state)
      ) bs ON bs.store_id=l.store_id AND bs.item_id=l.item_id AND bs.msku=l.msku
      LEFT JOIN (
        SELECT store_id, item_id, msku, SUM(COALESCE(sales_qty,0)) AS qty_30d
        FROM fact_sales_daily
        WHERE platform='walmart' AND stat_date >= DATE_SUB(CURDATE(), INTERVAL 30 DAY)
        GROUP BY store_id, item_id, msku
      ) q30 ON q30.store_id=l.store_id AND q30.item_id=l.item_id AND q30.msku=l.msku
      LEFT JOIN (
        SELECT store_id, item_id, msku, SUM(COALESCE(wfs_available_stock,0)) AS wfs_stock
        FROM fact_inventory_daily
        WHERE platform='walmart'
          AND snapshot_date=(SELECT MAX(snapshot_date) FROM fact_inventory_daily)
        GROUP BY store_id, item_id, msku
      ) iv ON iv.store_id=l.store_id AND iv.item_id=l.item_id AND iv.msku=l.msku`;

    const [cntRows] = await db.query<mysql.RowDataPacket[]>(
      `SELECT COUNT(*) AS total ${needMetricJoin ? fromJoinData : fromJoin} WHERE ${where}`, params);
    const total = Number(cntRows[0]?.total ?? 0);

    // 排序白名单（点表头三态排序；NULL 恒排最后）
    const SORT_MAP: Record<string, string> = {
      log_date: "l.log_date", qty_30d: "q30.qty_30d", sales_30d: "bs.sales_30d",
      gross_profit_30d: "bs.gross_profit_30d", profit_rate_30d: "bs.profit_rate_30d",
      ad_spend_30d: "bs.ad_spend_30d", ad_ratio_30d: "bs.ad_ratio_30d", wfs_stock: "iv.wfs_stock",
    };
    const sortExpr = SORT_MAP[sortField];
    const sortDir = sortOrder === "asc" ? "ASC" : "DESC";
    const orderClause = sortExpr && (sortOrder === "asc" || sortOrder === "desc")
      ? `ORDER BY ${sortExpr} IS NULL, ${sortExpr} ${sortDir}, l.log_date DESC, l.item_id`
      : "ORDER BY l.log_date DESC, l.store_id, l.item_id, l.msku";

    const [dataRows] = await db.query<mysql.RowDataPacket[]>(
      `SELECT l.id, DATE_FORMAT(l.log_date,'%Y-%m-%d') AS log_date, DATE_FORMAT(l.editable_date,'%Y-%m-%d') AS editable_date,
              l.store_id, l.store_name, l.store_key, l.item_id, l.msku, l.owner, l.profit_level_snapshot,
              l.data_issue, l.solution, l.log_content, l.ai_diagnosis, l.is_locked, l.source, l.updated_at,
              CASE WHEN p.product_management_status='archived' THEN 1 ELSE 0 END AS archived,
              q30.qty_30d, bs.sales_30d, bs.gross_profit_30d, bs.profit_rate_30d,
              bs.ad_spend_30d, bs.ad_ratio_30d, iv.wfs_stock
       ${fromJoinData} WHERE ${where}
       ${orderClause}
       LIMIT ? OFFSET ?`,
      [...params, pageSize, offset],
    );

    const fmt2 = (v: unknown): string => (v === null || v === undefined ? "-" : Number(v).toFixed(2));
    const fmtInt = (v: unknown): string => (v === null || v === undefined ? "-" : String(Math.round(Number(v))));
    const fmtPct = (v: unknown): string => (v === null || v === undefined ? "-" : `${(Number(v) * 100).toFixed(1)}%`);

    // 关联本页系统规则信号（按 log_date IN 页内日期，再 JS 精确匹配 store_key+item_id+msku）
    const pageDates = [...new Set(dataRows.map((r) => String(r.log_date)))];
    const sigByKey = new Map<string, mysql.RowDataPacket[]>();
    if (pageDates.length > 0) {
      const [sigRows] = await db.query<mysql.RowDataPacket[]>(
        `SELECT DATE_FORMAT(signal_date,'%Y-%m-%d') AS signal_date, store_key, item_id, msku,
                rule_code, rule_name, rule_level, trigger_reason, suggested_action, should_notify,
                DATE_FORMAT(created_at,'%Y-%m-%d %H:%i') AS written_at
           FROM biz_product_rule_signal_daily
          WHERE platform='walmart' AND signal_date IN (?)
            AND rule_code NOT IN ('REGULAR_OUT_OF_STOCK_RISK','REGULAR_INVENTORY_BACKLOG','REGULAR_CLEARANCE_PRIORITY')
          ORDER BY FIELD(rule_level,'critical','warning','info','positive'), rule_code`,
        [pageDates],
      );
      for (const s of sigRows) {
        const k = `${s.signal_date}|${s.store_key}|${s.item_id}|${s.msku}`;
        const arr = sigByKey.get(k) ?? [];
        arr.push(s);
        sigByKey.set(k, arr);
      }
    }

    // 2026-08-22 第四单：系统运营日志——快照差分检出的运营动作（EVENT 层 event_ops_action_log）
    //   关联键用 store_id：实测三张表 store_key 与 store_id 逐行相同（9店 same_cnt=总行数）。
    //   highlight=1 的句子单独归入 _sys_red，前端红色加粗；本层只读，不做任何写入。
    //   2026-08-24 第八单：按需求方定稿格式重排——日期一行 / 类型分组 / 广告组二级分组 / 中文状态 / 换行展示
    //   （规范原文 _deploy_tmp/audit/20260823_系统运营日志_展示格式规范.md；弹窗已是 pre-wrap，换行直接生效）。
    const evByKey = new Map<string, mysql.RowDataPacket[]>();
    if (pageDates.length > 0) {
      const [evRows] = await db.query<mysql.RowDataPacket[]>(
        `SELECT DATE_FORMAT(event_date,'%Y-%m-%d') AS event_date, store_id, item_id, msku,
                action_type, object_type, object_name, old_value, new_value,
                ad_group_name, match_type, log_content, highlight
           FROM event_ops_action_log
          WHERE platform='walmart' AND event_date IN (?)
          ORDER BY highlight DESC, id`,
        [pageDates],
      );
      for (const e of evRows) {
        const k = `${e.event_date}|${e.store_id}|${e.item_id}|${e.msku}`;
        const arr = evByKey.get(k) ?? [];
        arr.push(e);
        evByKey.set(k, arr);
      }
    }
    // 展示格式辅助（仅拼文案，零写入）：状态/匹配类型中文表按领星前端与 apidoc 枚举（第七单定稿）
    const SYS_ST_CN: Record<string, string> = { live: "进行中", paused: "暂停", completed: "结束", proposal: "待审核",
      enabled: "启用", disabled: "禁用", scheduled: "已计划", rescheduled: "重新计划" };
    const SYS_MT_CN: Record<string, string> = { exact: "精准", broad: "广泛", phrase: "词组" };
    const sysStCn = (v: unknown): string => SYS_ST_CN[String(v ?? "").toLowerCase()] ?? (String(v ?? "") || "空");
    const sysMt = (v: unknown): string => { const c = SYS_MT_CN[String(v ?? "").toLowerCase()]; return c ? `（${c}）` : ""; };
    const sysStripDate = (v: unknown): string => String(v ?? "").trim().replace(/^\d{4}-\d{2}-\d{2}\s*/, "");
    /** 一个 (日期,店,品) 键内的事件 → 定稿格式多行文本（R1 日期一行 / R3 类型分组 / R5 广告组行 / R8 中文状态） */
    const formatSysOps = (evs: mysql.RowDataPacket[]): string => {
      if (evs.length === 0) return "";
      const date = String(evs[0].event_date ?? "");
      const priceLines: string[] = [];
      const adTopLines: string[] = [];                       // 活动/广告组级：不挂组头
      const kwByGroup = new Map<string, string[]>();          // 广告组名 → 关键词行（R5：组头必须单独占一行）
      for (const e of evs) {
        const at = String(e.action_type ?? ""), name = String(e.object_name ?? "");
        const ov = String(e.old_value ?? ""), nv = String(e.new_value ?? "");
        if (at === "price_change") { priceLines.push(sysStripDate(e.log_content)); continue; }
        if (String(e.object_type) === "keyword") {
          const g = String(e.ad_group_name ?? "") || "(未知广告组)";
          const arr = kwByGroup.get(g) ?? [];
          if (at === "keyword_add") arr.push(`新增关键词：${name}${sysMt(e.match_type)}`);
          else if (at === "ad_bid_change") arr.push(`${name}${sysMt(e.match_type)}：${ov} ${Number(nv) > Number(ov) ? "上调至" : "降至"} ${nv}`);
          else arr.push(`${name}${sysMt(e.match_type)}：${sysStCn(ov)} 改为 ${sysStCn(nv)}`);
          kwByGroup.set(g, arr);
          continue;
        }
        if (at === "campaign_add") adTopLines.push(`新增广告活动：${name}`);
        else if (at === "group_add") adTopLines.push(`新增广告组：${name}`);
        else if (at === "ad_budget_change") adTopLines.push(`${name}：预算 ${ov} ${Number(nv) > Number(ov) ? "上调至" : "下调至"} ${nv}`);
        else if (at === "ad_strategy_change") adTopLines.push(`${name}：竞价策略 ${ov || "空"} 改为 ${nv}`);
        else adTopLines.push(`${name}：${sysStCn(ov)} 改为 ${sysStCn(nv)}`);
      }
      const out: string[] = [date];
      out.push(...priceLines);
      if (adTopLines.length || kwByGroup.size) {
        out.push("广告日志");
        out.push(...adTopLines);
        for (const [g, lines] of kwByGroup) { out.push(`广告组：${g}`); out.push(...lines); }
      }
      return out.join("\n");
    };

    // Stage 2.2（2026-08-22 第四单）：「运营提醒」更名为「系统运营日志」。
    //   内容 = 系统事件（event_ops_action_log） + 规则摘要（trigger_reason 原文，含【近14天】口径） + 【数据问题】。
    //   已去掉 [level] 标签、【系统规则】/【系统建议】前缀与 suggested_action；库存三规则已在 SQL 层剔除。
    const columns = ["日期", "负责人", "店铺", "Item ID", "MSKU", "利润等级",
      "销量(近30天)", "销售额(近30天)$", "毛利润(近30天)$", "毛利率(近30天)",
      "广告费(近30天)$", "广告占比(近30天)", "WFS库存",
      "系统运营日志", "运营日志"];
    let rowsWithRule = 0;
    const rows = dataRows.map((r) => {
      const sigs = sigByKey.get(`${r.log_date}|${r.store_key}|${r.item_id}|${r.msku}`) ?? [];
      if (sigs.length > 0) rowsWithRule += 1;
      const evs = evByKey.get(`${r.log_date}|${r.store_id}|${r.item_id}|${r.msku}`) ?? [];
      // 红字段：仅 highlight=1（成交价与新价不一致，需人工在运营日志写实情）；2026-08-24 起换行分隔、去日期前缀
      const redText = evs.filter((e) => Number(e.highlight) === 1)
        .map((e) => sysStripDate(e.log_content)).filter(Boolean).join("\n");
      const evText = formatSysOps(evs.filter((e) => Number(e.highlight) !== 1));
      // 规则摘要：直接用 trigger_reason 原文（其中已含「【近14天】毛利率x%（C级）」这类口径），
      // 仅在前面补规则信号的写入时间；不再拼 rule_name、不再输出 suggested_action。
      const ruleText = sigs.length ? sigs.map((s) =>
        String(s.trigger_reason ?? "").trim() || String(s.rule_name ?? "").trim()
      ).filter(Boolean).join("；") : "";
      const writtenAt = sigs.length ? String(sigs[0].written_at ?? "").trim() : "";
      const dataIssue = String(r.data_issue ?? "").trim();
      const parts: string[] = [];
      if (evText) parts.push(evText);
      if (ruleText) parts.push(writtenAt ? `${writtenAt} 补写  ${ruleText}` : ruleText);
      if (dataIssue) parts.push(`【数据问题】${dataIssue}`);
      const alert = parts.length ? parts.join("\n") : (redText ? "" : "暂无提醒");
      return {
        "日期": String(r.log_date ?? ""),
        "负责人": String(r.owner ?? ""),
        "店铺": String(r.store_name ?? ""),
        "Item ID": String(r.item_id ?? ""),
        "MSKU": String(r.msku ?? ""),
        "利润等级": blankToDash(r.profit_level_snapshot),
        "销量(近30天)": fmtInt(r.qty_30d),
        "销售额(近30天)$": fmt2(r.sales_30d),
        "毛利润(近30天)$": fmt2(r.gross_profit_30d),
        "毛利率(近30天)": fmtPct(r.profit_rate_30d),
        "广告费(近30天)$": fmt2(r.ad_spend_30d),
        "广告占比(近30天)": fmtPct(r.ad_ratio_30d),
        "WFS库存": fmtInt(r.wfs_stock),
        "系统运营日志": alert,
        "运营日志": String(r.log_content ?? ""),
        // 隐藏字段：供前端行内编辑用（下划线开头，不在 columns 里渲染，也不进 CSV 导出）
        "_sys_red": redText,
        "_id": String(r.id ?? ""),
        "_editable": (String(r.source ?? "") === "system_base" && Number(r.is_locked) === 0) ? "1" : "0",
      };
    });

    // 下拉选项（店铺/负责人/利润等级），供前端筛选器填充
    const [storeOptRows] = await db.query<mysql.RowDataPacket[]>(
      "SELECT DISTINCT store_name FROM biz_product_operation_log WHERE platform='walmart' AND store_name<>'' ORDER BY store_name",
    );
    const [ownerOptRows] = await db.query<mysql.RowDataPacket[]>(
      "SELECT DISTINCT owner FROM biz_product_operation_log WHERE platform='walmart' AND owner IS NOT NULL AND owner<>'' ORDER BY owner",
    );
    const [levelOptRows] = await db.query<mysql.RowDataPacket[]>(
      "SELECT DISTINCT profit_level_snapshot FROM biz_product_operation_log WHERE platform='walmart' AND profit_level_snapshot IS NOT NULL AND profit_level_snapshot<>'' ORDER BY profit_level_snapshot",
    );

    // 2026-07-23 GPT分析链接：按行生成时刻(created_at)匹配当时版本——替换链接只影响新生成行
    try {
      const glTs = (x: unknown): number => { const d = new Date(String(x)); const n = d.getTime(); return Number.isFinite(n) ? n : 0; };
      const glRows = rows as unknown as Array<Record<string, string>>;
      const glIds = glRows.map((r0) => Number(r0["_id"])).filter((n) => Number.isFinite(n) && n > 0);
      const glItemIds = [...new Set(glRows.map((r0) => String(r0["Item ID"] ?? "").trim()).filter(Boolean))];
      if (glIds.length > 0 && glItemIds.length > 0) {
        const [glCaRows] = await db.query<mysql.RowDataPacket[]>(
          `SELECT id, created_at FROM biz_product_operation_log WHERE id IN (${glIds.map(() => "?").join(",")})`,
          glIds,
        );
        const glCaById = new Map<string, number>();
        for (const c of glCaRows) glCaById.set(String(c.id), glTs(c.created_at));
        const [glVerRows] = await db.query<mysql.RowDataPacket[]>(
          `SELECT item_id, link_type, url, effective_from
           FROM dim_product_gpt_link
           WHERE platform = 'walmart' AND item_id IN (${glItemIds.map(() => "?").join(",")})
           ORDER BY item_id, effective_from`,
          glItemIds,
        );
        for (const r0 of glRows) {
          const ca = glCaById.get(String(r0["_id"] ?? ""));
          if (!ca) continue;
          let glKw = "";
          let glAd = "";
          for (const v of glVerRows) {
            if (String(v.item_id) !== String(r0["Item ID"] ?? "").trim()) continue;
            const vt = glTs(v.effective_from);
            if (vt > 0 && vt <= ca) {
              if (String(v.link_type) === "keyword") glKw = String(v.url);
              if (String(v.link_type) === "ads") glAd = String(v.url);
            }
          }
          r0["_kw_link"] = glKw;
          r0["_ads_link"] = glAd;
        }
      }
    } catch (gptErr) {
      console.warn("[gpt-link] 运营日志链接匹配失败（忽略，不影响列表）:", gptErr instanceof Error ? gptErr.message : String(gptErr));
    }
    res.json({
      sheet_id: OPERATION_LOG_SHEET_ID,
      sheet_name: "运营日志",
      columns,
      rows,
      total,
      page,
      page_size: pageSize,
      stores: storeOptRows.map((r) => String(r.store_name)),
      owners: ownerOptRows.map((r) => String(r.owner)),
      profit_levels: levelOptRows.map((r) => String(r.profit_level_snapshot)),
      summary: {
        latest_log_date: latestLogDate,
        used_log_date: usedLogDate,
        total_rows: total,
        page_rows_with_rule: rowsWithRule,
        include_archived: includeArchived,
      },
    });
  } catch (err) {
    res.status(500).json({ error: String(err) });
  } finally {
    await db.end();
  }
});

// ── POST /operation-log/update （任务H-Stage3 运营日志写入）──────────────────
// 只允许改人工字段 log_content；仅 source='system_base' 且 is_locked=0 的行可写；迁移历史/锁定行只读。
// 不碰任何其它字段；不写 data_issue/solution/ai_diagnosis/系统字段。updated_by 记 'admin_ui'。
router.post("/operation-log/update", async (req: Request, res: Response): Promise<void> => {
  const id = Number(req.body?.id ?? 0);
  const logContent = typeof req.body?.log_content === "string" ? req.body.log_content : null;
  if (!id) { res.status(400).json({ error: "缺少 id" }); return; }
  if (logContent === null) { res.status(400).json({ error: "缺少 log_content" }); return; }

  const db = await getDb();
  try {
    const [result] = await db.query<mysql.ResultSetHeader>(
      `UPDATE biz_product_operation_log
          SET log_content = ?, updated_by = ?, updated_at = NOW()
        WHERE id = ? AND platform = 'walmart' AND source = 'system_base' AND is_locked = 0`,
      [logContent, requiredText((req as AuthedRequest).user?.username) || "admin_ui", id],
    );
    if (result.affectedRows === 0) {
      res.status(409).json({ error: "该行不存在或不可编辑（仅每日生成行 system_base 且未锁定可编辑，迁移历史只读）" });
      return;
    }
    res.json({ ok: true, updated: result.affectedRows });
  } catch (err) {
    res.status(500).json({ error: String(err) });
  } finally {
    await db.end();
  }
});

export default router;
