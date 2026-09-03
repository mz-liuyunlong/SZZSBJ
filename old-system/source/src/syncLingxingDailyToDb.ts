/**
 * syncLingxingDailyToDb.ts
 *
 * 领星销售数据入库 - 第一阶段
 *
 * 功能:
 *   - 从领星 API 拉取 walmart/list + saleStat + reportAdItemSpList
 *   - 写入 raw_lingxing_api / dim_store / dim_product
 *     / fact_inventory_daily / fact_sales_daily / fact_ads_product_daily
 *   - 全程记录到 sync_task_log
 *
 * 用法:
 *   npx ts-node src/syncLingxingDailyToDb.ts --date 2026-06-25
 *   npx ts-node src/syncLingxingDailyToDb.ts              # 默认昨日
 *
 * 注意:
 *   - 不修改任何已有脚本
 *   - 只写入已有表，不建新表
 *   - 脚本不可读不可写的接口不调用
 *   - Lingxing API 只能从服务器 8.145.43.239 调用（本地需提前加白名单）
 */

import "dotenv/config";
import * as crypto from "crypto";
import * as mysql from "mysql2/promise";
import { loadConfig } from "./config";
import { LingxingClient } from "./lingxingClient";
import { STORES, StoreConfig } from "./syncDailyBaseData";
import { loadStores } from "./storeRegistry";

// ── API 路径常量 ──────────────────────────────────────────────────────────────

const WALMART_LIST_PATH = "/basicOpen/multiplatform/walmart/list";
const SALE_STAT_PATH = "/basicOpen/platformStatisticsV2/saleStat/pageList";
const AD_ITEM_SP_PATH = "/basicOpen/multiplatform/ads/reportAdItemSpList";

// ── 分页参数 ──────────────────────────────────────────────────────────────────

const WALMART_PAGE_SIZE = 20;
const WALMART_MAX_PAGES = 200;
const SALE_STAT_PAGE_SIZE = 200;
const SALE_STAT_MAX_PAGES = 20;
const AD_PAGE_SIZE = 200;
const AD_MAX_PAGES = 30;
const TIMEOUT_MS = 120_000;
const MAX_RETRIES = 3;

// ── 类型 ──────────────────────────────────────────────────────────────────────

interface ProductInfo {
  itemId: string;
  msku: string;
  publishStatus: string;   // 2026-07-27 领星Walmart发布状态 status_name(PUBLISHED/UNPUBLISHED/...)
  sku: string;
  itemName: string;
  availableQty: number;
  nonWfsAvailableQty: number;
  wfsAvailableQty: number;
  warehouseQty: number;
  inboundQty: number;
  reservedQty: number;
  stockDays: number | null;
}

interface StoreStats {
  storeId: string;
  storeName: string;
  walmartListItems: number;
  dimProductUpserted: number;
  inventoryUpserted: number;
  salesUpserted: number;
  adUpserted: number;
  rawRecords: number;
  errorMessages: string[];
}

// ── 工具函数 ──────────────────────────────────────────────────────────────────

function toNum(v: unknown, fallback = 0): number {
  const n = Number(v);
  return Number.isFinite(n) ? n : fallback;
}

function toStr(v: unknown): string {
  return String(v ?? "").trim();
}

function toInt(v: unknown, fallback = 0): number {
  const n = Math.round(toNum(v, fallback));
  return Number.isFinite(n) ? n : fallback;
}

function md5(s: string): string {
  return crypto.createHash("md5").update(s).digest("hex").slice(0, 64);
}

// 2026-07-18 库存口径修复：walmart/list 无日期参数，返回的是"调用时刻"的实时库存。
// 库存快照必须打"拉取当日（中国时区）"标签，禁止贴 dataDate（T-2/回填历史日期）标签，
// 否则：①库存历史整体前移 ②backfill-daily-chain 滚动回填会用当下实时值覆盖历史快照（已实锤污染）。
// 改为恒写 CST 当天后，任何回填运行只会幂等刷新"今天"这一行，物理上无法触碰历史。
function cstToday(): string {
  return new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Shanghai" }).format(new Date());
}

function fiveDaysAgo(): string {
  const d = new Date();
  d.setDate(d.getDate() - 5);
  return d.toISOString().slice(0, 10);
}

function getCliDate(): string {
  // 同时支持 --date=YYYY-MM-DD 和 --date YYYY-MM-DD 两种写法
  let dateStr: string | undefined;
  const eqArg = process.argv.find((a) => a.startsWith("--date="));
  if (eqArg) {
    dateStr = eqArg.slice("--date=".length);
  } else {
    const idx = process.argv.findIndex((a) => a === "--date");
    if (idx >= 0 && process.argv[idx + 1]) dateStr = process.argv[idx + 1];
  }
  dateStr = dateStr ?? fiveDaysAgo();

  // 只校验格式
  if (!/^\d{4}-\d{2}-\d{2}$/.test(dateStr) || isNaN(new Date(dateStr).getTime())) {
    console.error(`❌ 日期格式错误: ${dateStr}，请使用 YYYY-MM-DD`);
    process.exit(1);
  }
  return dateStr;
}

function makeLxdbTag(): string {
  const now = new Date();
  const ts = now.toISOString().replace(/[-T:.Z]/g, "").slice(0, 14);
  return `LXDB-${ts}`;
}

async function sleep(ms: number): Promise<void> {
  await new Promise((r) => setTimeout(r, ms));
}

async function withRetry<T>(label: string, fn: () => Promise<T>): Promise<T> {
  let last: unknown;
  for (let i = 1; i <= MAX_RETRIES; i++) {
    try {
      return await fn();
    } catch (e) {
      last = e;
      console.warn(`  ⚠️  ${label} 失败 (${i}/${MAX_RETRIES}): ${e instanceof Error ? e.message : String(e)}`);
      if (i < MAX_RETRIES) await sleep(1000 * i);
    }
  }
  throw last instanceof Error ? last : new Error(String(last));
}

function extractList(data: unknown): unknown[] {
  if (Array.isArray(data)) return data;
  if (data && typeof data === "object") {
    const d = data as Record<string, unknown>;
    if (Array.isArray(d.list)) return d.list;
    if (Array.isArray(d.data)) return d.data;
    if (d.data && typeof d.data === "object") {
      const nested = d.data as Record<string, unknown>;
      if (Array.isArray(nested.list)) return nested.list;
      if (Array.isArray(nested.data)) return nested.data;
    }
    if (Array.isArray(d.rows)) return d.rows;
    if (Array.isArray(d.records)) return d.records;
  }
  return [];
}

function extractTotal(data: unknown): number {
  if (!data || typeof data !== "object") return 0;
  const d = data as Record<string, unknown>;
  const t = Number(d.total);
  if (Number.isFinite(t) && t > 0) return t;
  if (d.data && typeof d.data === "object") {
    const nested = d.data as Record<string, unknown>;
    const t2 = Number(nested.total);
    if (Number.isFinite(t2) && t2 > 0) return t2;
  }
  return 0;
}

/** 从 ad item record 中读取字段，支持多种命名方式 */
function readAdField(r: Record<string, unknown>, ...keys: string[]): unknown {
  for (const k of keys) {
    if (k in r && r[k] !== undefined && r[k] !== null && r[k] !== "") return r[k];
  }
  return undefined;
}

// ── DB 连接 ───────────────────────────────────────────────────────────────────

function getDb(): Promise<mysql.Connection> {
  return mysql.createConnection({
    host:     process.env.DB_HOST     ?? "127.0.0.1",
    port:     Number(process.env.DB_PORT ?? 3306),
    user:     process.env.DB_USER     ?? "",
    password: process.env.DB_PASSWORD ?? "",
    database: process.env.DB_NAME     ?? "walmart_ai_data",
  });
}

// ── RAW 层写入 ────────────────────────────────────────────────────────────────

async function insertRaw(
  db: mysql.Connection,
  apiPath: string,
  dataDate: string,
  page: number,
  responseBody: unknown,
  lxdbTag: string,
): Promise<number> {
  const bodyStr = JSON.stringify(responseBody);
  const hash = md5(`${apiPath}|${dataDate}|p${page}|${bodyStr}`);
  const extraJson = JSON.stringify({ lxdb_tag: lxdbTag, page });

  try {
    const [result] = await db.query<mysql.ResultSetHeader>(
      `INSERT IGNORE INTO raw_lingxing_api
         (source_system, api_path, request_method, data_date,
          response_json, is_success, raw_hash, extra_json, pulled_at)
       VALUES ('lingxing', ?, 'POST', ?, ?, 1, ?, ?, NOW())`,
      [apiPath, dataDate, bodyStr, hash, extraJson],
    );
    return result.insertId || 0;
  } catch (e) {
    // RAW 写入失败不阻断主流程，只打印警告
    console.warn(`  ⚠️  insertRaw 写入失败 (${apiPath} p${page}): ${e instanceof Error ? e.message : String(e)}`);
    return 0;
  }
}

// ── sync_task_log ─────────────────────────────────────────────────────────────

// 返回自增生成的 task_id（BIGINT）
async function logTaskStart(db: mysql.Connection, lxdbTag: string, dataDate: string): Promise<number> {
  const [result] = await db.query<mysql.ResultSetHeader>(
    `INSERT INTO sync_task_log
       (task_name, source_system, target_table, started_at, status, extra_json)
     VALUES ('领星每日销售入库', 'lingxing', 'fact_sales_daily,fact_inventory_daily,fact_ads_product_daily', NOW(), 'running', ?)`,
    [JSON.stringify({ lxdb_tag: lxdbTag, data_date: dataDate })],
  );
  return result.insertId;
}

async function logTaskEnd(
  db: mysql.Connection,
  dbTaskId: number,
  status: "success" | "failed",
  stats: StoreStats[],
  errorMsg?: string,
): Promise<void> {
  const totals = stats.reduce(
    (acc, s) => {
      acc.inserted += s.salesUpserted + s.inventoryUpserted + s.adUpserted;
      acc.updated += s.dimProductUpserted;
      acc.pulled += s.walmartListItems;
      return acc;
    },
    { inserted: 0, updated: 0, pulled: 0 },
  );

  await db.query(
    `UPDATE sync_task_log
     SET status = ?, finished_at = NOW(),
         pulled_count = ?, inserted_count = ?, updated_count = ?,
         error_message = ?,
         extra_json = JSON_MERGE_PATCH(COALESCE(extra_json, '{}'), ?)
     WHERE task_id = ?`,
    [
      status,
      totals.pulled,
      totals.inserted,
      totals.updated,
      errorMsg ?? null,
      JSON.stringify({ stores: stats }),
      dbTaskId,
    ],
  );
}

// ── DIM 层 upsert ─────────────────────────────────────────────────────────────

async function upsertDimStore(
  db: mysql.Connection,
  store: StoreConfig,
): Promise<void> {
  await db.query(
    `INSERT INTO dim_store (platform, store_id, store_name)
     VALUES ('walmart', ?, ?)
     ON DUPLICATE KEY UPDATE store_name = VALUES(store_name)`,
    [store.storeId, store.storeName],
  );
}

async function upsertDimProduct(
  db: mysql.Connection,
  store: StoreConfig,
  products: ProductInfo[],
): Promise<number> {
  let count = 0;
  for (const p of products) {
    // 2026-07-14 SKU修复：领星 walmart/list 对部分行（典型为-1U）返回 local_sku=null，
    // 防止空值覆盖已有非空 sku/item_name（探针实证 + TASK_CHANGE_LOG）
    await db.query(
      `INSERT INTO dim_product
         (platform, store_id, item_id, msku, sku, item_name, walmart_publish_status)
       VALUES ('walmart', ?, ?, ?, ?, ?, ?)
       ON DUPLICATE KEY UPDATE
         msku = VALUES(msku),
         sku  = IF(VALUES(sku) IS NULL OR VALUES(sku) = '', sku, VALUES(sku)),
         item_name = IF(VALUES(item_name) IS NULL OR VALUES(item_name) = '', item_name, VALUES(item_name)),
         walmart_publish_status = IF(VALUES(walmart_publish_status) IS NULL OR VALUES(walmart_publish_status) = '', walmart_publish_status, VALUES(walmart_publish_status))`,
      [store.storeId, p.itemId, p.msku, p.sku, p.itemName, p.publishStatus],
    );
    count++;
  }
  return count;
}

/**
 * 2026-07-14 SKU修复：保守自愈补齐。
 * 同一 platform+item_id 下若存在唯一的非空 SKU（跨店铺/变体行），
 * 将该 item 其余空 SKU 行补齐；存在多个不同非空 SKU 的 item 一律跳过（HAVING 保证）。
 * 每次产品同步后运行，首次运行即覆盖存量可补行（探针估算 84 行），此后持续自愈。
 * 注意：不做 MSKU 尾缀推导（需求方 2026-07-14 明确禁止）。
 */
async function backfillDimProductSkuFromSiblings(db: mysql.Connection): Promise<number> {
  const [result] = await db.query<mysql.ResultSetHeader>(
    `UPDATE dim_product d
     JOIN (
       SELECT item_id, MAX(sku) AS sku
       FROM dim_product
       WHERE platform = 'walmart' AND sku IS NOT NULL AND sku <> ''
       GROUP BY item_id
       HAVING COUNT(DISTINCT sku) = 1
     ) u ON u.item_id = d.item_id
     SET d.sku = u.sku
     WHERE d.platform = 'walmart' AND (d.sku IS NULL OR d.sku = '')`,
  );
  return result.affectedRows ?? 0;
}

// ── FACT: 库存 ────────────────────────────────────────────────────────────────

async function upsertFactInventory(
  db: mysql.Connection,
  store: StoreConfig,
  dataDate: string,
  products: ProductInfo[],
  rawId: number,
): Promise<number> {
  let count = 0;
  for (const p of products) {
    await db.query(
      `INSERT INTO fact_inventory_daily
         (snapshot_date, platform, store_id, store_name, item_id, msku, sku,
          available_stock, non_wfs_available_stock, wfs_available_stock, warehouse_stock,
          inbound_stock, reserved_stock, stock_days,
          source_system, source_raw_id)
       VALUES (?, 'walmart', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'lingxing', ?)
       ON DUPLICATE KEY UPDATE
         available_stock         = VALUES(available_stock),
         non_wfs_available_stock = VALUES(non_wfs_available_stock),
         wfs_available_stock     = VALUES(wfs_available_stock),
         warehouse_stock         = VALUES(warehouse_stock),
         inbound_stock           = VALUES(inbound_stock),
         reserved_stock          = VALUES(reserved_stock),
         stock_days              = VALUES(stock_days),
         source_raw_id           = VALUES(source_raw_id)`,
      [
        dataDate, store.storeId, store.storeName, p.itemId, p.msku, p.sku,
        p.availableQty,       // available_stock = 自发货可售 + WFS 可售
        p.nonWfsAvailableQty, // non_wfs_available_stock = 领星 available_quantity
        p.wfsAvailableQty,    // wfs_available_stock
        p.warehouseQty,       // warehouse_stock = 领星仓库库存字段
        p.inboundQty,
        p.reservedQty,
        p.stockDays,
        rawId,
      ],
    );
    count++;
  }
  return count;
}

// ── FACT: 销售 ────────────────────────────────────────────────────────────────

async function upsertFactSales(
  db: mysql.Connection,
  store: StoreConfig,
  dataDate: string,
  productMap: Map<string, ProductInfo>,
  qtyMap: Map<string, number>,
  amountMap: Map<string, number>,
  rawId: number,
  errorMessages?: string[],
): Promise<number> {
  // 合并 qty 和 amount 的 item_id 集合
  const allItemIds = new Set([...qtyMap.keys(), ...amountMap.keys()]);
  let count = 0;

  // 2026-08-13 加固：uq_fact_sales 唯一键含 msku，写 msku='' 的行会与后续正常行并存 → 同日同品销量双计
  // （实证：2026-08-09 item 20708417562 出现 CS400-1A 与空串两行，各 qty=2/$31.98）。
  // 故：productMap 未命中时先用 dim_product 按 (store_id,item_id) 兜底；仍无 msku 则跳过该行并告警，绝不写空串。
  const mskuFallback = new Map<string, { msku: string; sku: string }>();
  try {
    const [fbRows] = await db.query<mysql.RowDataPacket[]>(
      `SELECT item_id,
              COALESCE(MAX(NULLIF(TRIM(msku),'')),'') AS msku,
              COALESCE(MAX(NULLIF(TRIM(sku),'')),'')  AS sku
         FROM dim_product
        WHERE platform='walmart' AND store_id=? AND item_id IS NOT NULL AND item_id<>''
        GROUP BY item_id`,
      [store.storeId],
    );
    for (const r of fbRows) {
      mskuFallback.set(String(r.item_id), { msku: String(r.msku ?? ""), sku: String(r.sku ?? "") });
    }
  } catch (e) {
    console.warn(`    ⚠️ msku 兜底表读取失败（按未命中处理）: ${e instanceof Error ? e.message : String(e)}`);
  }
  const skippedItems: string[] = [];

  for (const itemId of allItemIds) {
    const qty = qtyMap.get(itemId) ?? 0;
    const amount = amountMap.get(itemId) ?? 0;
    const prod = productMap.get(itemId);
    const fb = mskuFallback.get(itemId);
    const msku = (prod?.msku || fb?.msku || "").trim();
    const sku = (prod?.sku || fb?.sku || "").trim();
    if (!msku) {
      skippedItems.push(`${itemId}(qty=${qty})`);
      continue;
    }

    await db.query(
      `INSERT INTO fact_sales_daily
         (stat_date, platform, store_id, store_name, item_id, msku, sku,
          sales_qty, order_count, sales_amount,
          source_system, source_raw_id)
       VALUES (?, 'walmart', ?, ?, ?, ?, ?, ?, ?, ?, 'lingxing', ?)
       ON DUPLICATE KEY UPDATE
         sales_qty    = VALUES(sales_qty),
         order_count  = VALUES(order_count),
         sales_amount = VALUES(sales_amount),
         source_raw_id = VALUES(source_raw_id)`,
      [dataDate, store.storeId, store.storeName, itemId, msku, sku,
       qty, qty, amount, rawId],
    );
    count++;
  }
  if (skippedItems.length) {
    const msg = `销量写入跳过 ${skippedItems.length} 个无msku商品(${store.storeName} ${dataDate}): ${skippedItems.slice(0, 10).join("、")}${skippedItems.length > 10 ? " …" : ""}`;
    console.warn(`    ⚠️ ${msg}`);
    errorMessages?.push(msg);
  }
  return count;
}

// ── FACT: 广告 ────────────────────────────────────────────────────────────────

async function upsertFactAds(
  db: mysql.Connection,
  store: StoreConfig,
  dataDate: string,
  adItems: Record<string, unknown>[],
  rawId: number,
): Promise<number> {
  let count = 0;

  for (const item of adItems) {
    const campaignId  = toStr(readAdField(item, "campaignId",  "campaign_id",  "cid") || "");
    const campaignName= toStr(readAdField(item, "campaignName","campaign_name","cn")  || "");
    const campaignType= toStr(readAdField(item, "campaignType","campaign_type","ct")  || "");
    const adGroupId   = toStr(readAdField(item, "adGroupId",   "ad_group_id",  "gid")|| "");
    const adGroupName = toStr(readAdField(item, "adGroupName", "ad_group_name","gn") || "");
    const itemId      = toStr(readAdField(item, "itemId",      "item_id",       "id")|| "");
    const msku        = toStr(readAdField(item, "msku",        "sku")                || "");
    const advertiser  = toStr(readAdField(item, "advertiserId","advertiser_id")       || store.advertiserId || "");

    if (!itemId) continue;

    const impressions = toInt(readAdField(item, "numAdsShown","impressions","adImpressions"));
    const clicks      = toInt(readAdField(item, "numAdsClicks","clicks","adClicks"));
    const ctr         = readAdField(item, "ctr","clickRate")    != null ? toNum(readAdField(item,"ctr","clickRate")) : null;
    const adSpend     = toNum(readAdField(item, "adSpend",     "spend","cost"));
    const orders      = toInt(readAdField(item, "attributedOrders","orders",      "orderNum","orderCount","conversionOrders"));
    const totalSales  = toNum(readAdField(item, "attributedSales","totalSales",  "adSales","revenue","sales"));
    const acos        = readAdField(item, "acos","acosRate")    != null ? toNum(readAdField(item,"acos","acosRate")) : null;
    const cpc         = readAdField(item, "cpc")                != null ? toNum(readAdField(item,"cpc")) : null;
    const cvr         = readAdField(item, "cvr","conversionRate")!=null? toNum(readAdField(item,"cvr","conversionRate")): null;
    const roas        = readAdField(item, "roas")               != null ? toNum(readAdField(item,"roas")) : null;

    await db.query(
      `INSERT INTO fact_ads_product_daily
         (stat_date, platform, store_id, store_name, advertiser_id,
          campaign_id, campaign_name, campaign_type,
          ad_group_id, ad_group_name,
          item_id, msku,
          impressions, clicks, ctr, ad_spend,
          orders, total_sales, acos, cpc, cvr, roas,
          source_system, source_raw_id)
       VALUES (?, 'walmart', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'lingxing', ?)
       ON DUPLICATE KEY UPDATE
         campaign_name = VALUES(campaign_name),
         campaign_type = VALUES(campaign_type),
         ad_group_name = VALUES(ad_group_name),
         msku          = VALUES(msku),
         impressions   = VALUES(impressions),
         clicks        = VALUES(clicks),
         ctr           = VALUES(ctr),
         ad_spend      = VALUES(ad_spend),
         orders        = VALUES(orders),
         total_sales   = VALUES(total_sales),
         acos          = VALUES(acos),
         cpc           = VALUES(cpc),
         cvr           = VALUES(cvr),
         roas          = VALUES(roas),
         source_raw_id = VALUES(source_raw_id)`,
      [
        dataDate, store.storeId, store.storeName, advertiser,
        campaignId, campaignName, campaignType,
        adGroupId, adGroupName,
        itemId, msku,
        impressions, clicks, ctr, adSpend,
        orders, totalSales, acos, cpc, cvr, roas,
        rawId,
      ],
    );
    count++;
  }
  return count;
}

// ── 解析 walmart/list 商品 ────────────────────────────────────────────────────

function parseProductInfo(item: unknown): ProductInfo | null {
  if (!item || typeof item !== "object") return null;
  const r = item as Record<string, unknown>;
  const itemId = toStr(r.item_id ?? r.itemId);
  if (!itemId) return null;
  const nonWfsAvailableQty = toInt(r.available_quantity ?? r.availableQuantity);
  const wfsAvailableQty = toInt(r.wfs_available_quantity ?? r.wfsAvailableQuantity);

  return {
    itemId,
    publishStatus:    toStr(r.status_name ?? r.status),   // 2026-07-27 Walmart发布状态
    msku:             toStr(r.msku),
    sku:              toStr(r.local_sku ?? r.sku),
    itemName:         toStr(r.local_name ?? r.item_name ?? r.name ?? r.title),
    availableQty:     nonWfsAvailableQty + wfsAvailableQty,
    nonWfsAvailableQty,
    wfsAvailableQty,
    warehouseQty:     toInt(r.warehouse_stock ?? r.warehouse_quantity ?? r.warehouseQty),
    inboundQty:       toInt(r.inbound_stock ?? r.inbound_quantity ?? r.inboundQty),
    reservedQty:      toInt(r.reserved_stock ?? r.reserved_quantity ?? r.reservedQty),
    stockDays:        r.stock_days != null ? toNum(r.stock_days) : null,
  };
}

// ── 解析 saleStat 行 ──────────────────────────────────────────────────────────

function mergeSaleStatRow(
  map: Map<string, number>,
  item: unknown,
): void {
  if (!item || typeof item !== "object") return;
  const r = item as Record<string, unknown>;
  const metric = toNum(r.volumeTotal ?? r.volume_total);

  // platform_product_id 可能是数组或单值
  let ids: string[] = [];
  const raw = r.platform_product_id ?? r.platformProductId;
  if (Array.isArray(raw)) {
    ids = raw.map(toStr).filter(Boolean);
  } else if (raw != null) {
    const s = toStr(raw);
    if (s) ids = [s];
  }

  for (const id of ids) {
    map.set(id, (map.get(id) ?? 0) + metric);
  }
}

// ── 单店铺同步 ────────────────────────────────────────────────────────────────

async function syncStore(
  db: mysql.Connection,
  client: LingxingClient,
  store: StoreConfig,
  dataDate: string,
  taskId: string,
): Promise<StoreStats> {
  const stats: StoreStats = {
    storeId: store.storeId,
    storeName: store.storeName,
    walmartListItems: 0,
    dimProductUpserted: 0,
    inventoryUpserted: 0,
    salesUpserted: 0,
    adUpserted: 0,
    rawRecords: 0,
    errorMessages: [],
  };

  console.log(`\n  ► 店铺: ${store.storeName} (${store.storeId})`);

  // ── 1. dim_store ─────────────────────────────────────────────────────────
  await upsertDimStore(db, store);

  // ── 2. walmart/list → dim_product + fact_inventory_daily ─────────────────

  const productMap = new Map<string, ProductInfo>(); // item_id → ProductInfo
  let lastWalmartRawId = 0;

  try {
    for (let page = 0; page < WALMART_MAX_PAGES; page++) {
      const offset = page * WALMART_PAGE_SIZE;

      const resp = await withRetry(`${store.storeName} walmart/list offset=${offset}`, () =>
        client.request<unknown>({
          method: "POST",
          path: WALMART_LIST_PATH,
          params: { offset, length: WALMART_PAGE_SIZE, store_ids: [store.storeId], status: [0, 1, 2, 3, 4, 5] },
          timeoutMs: TIMEOUT_MS,
        }),
      );

      const rawId = await insertRaw(db, WALMART_LIST_PATH, dataDate, page + 1, resp, taskId);
      if (rawId) { lastWalmartRawId = rawId; stats.rawRecords++; }

      const pageItems = extractList(resp.data);
      for (const item of pageItems) {
        const p = parseProductInfo(item);
        if (p) productMap.set(p.itemId, p);
      }

      if (pageItems.length < WALMART_PAGE_SIZE) break;
    }
  } catch (e) {
    stats.errorMessages.push(`walmart/list 失败: ${e instanceof Error ? e.message : String(e)}`);
  }

  stats.walmartListItems = productMap.size;
  console.log(`    商品数: ${productMap.size}`);

  // dim_product
  if (productMap.size > 0) {
    stats.dimProductUpserted = await upsertDimProduct(db, store, Array.from(productMap.values()));
    // 2026-07-14 SKU修复：同 item 唯一非空 SKU 自愈补齐（保守，冲突跳过）
    const skuFilled = await backfillDimProductSkuFromSiblings(db);
    if (skuFilled > 0) console.log(`    SKU补齐: ${skuFilled} 行（同item唯一SKU）`);
  }

  // fact_inventory_daily
  // 2026-07-18 库存口径修复：snapshot_date 恒为拉取当日（CST），不随 dataDate（见 cstToday 注释）
  if (productMap.size > 0) {
    const invSnapshotDate = cstToday();
    stats.inventoryUpserted = await upsertFactInventory(
      db, store, invSnapshotDate, Array.from(productMap.values()), lastWalmartRawId,
    );
    console.log(`    库存写入: ${stats.inventoryUpserted} (snapshot_date=${invSnapshotDate}，实时库存打拉取日标签)`);
  }

  // ── 3. saleStat → fact_sales_daily ───────────────────────────────────────

  const qtyMap    = new Map<string, number>();
  const amountMap = new Map<string, number>();
  let lastSaleRawId = 0;

  for (const [resultType, targetMap] of ([["1", qtyMap], ["3", amountMap]] as [string, Map<string, number>][])) {
    try {
      for (let page = 1; page <= SALE_STAT_MAX_PAGES; page++) {
        const resp = await withRetry(
          `${store.storeName} saleStat result_type=${resultType} page=${page}`,
          () => client.request<unknown>({
            method: "POST",
            path: SALE_STAT_PATH,
            params: {
              start_date: dataDate,
              end_date: dataDate,
              result_type: resultType,
              date_unit: "4",
              data_type: "1",
              page,
              length: SALE_STAT_PAGE_SIZE,
              sids: [store.storeId],
            },
            timeoutMs: TIMEOUT_MS,
          }),
        );

        const rawId = await insertRaw(
          db, SALE_STAT_PATH, dataDate,
          (resultType === "1" ? 0 : 10000) + page,
          resp, taskId,
        );
        if (rawId) { lastSaleRawId = rawId; stats.rawRecords++; }

        const pageItems = extractList(resp.data);
        for (const item of pageItems) mergeSaleStatRow(targetMap, item);

        if (pageItems.length < SALE_STAT_PAGE_SIZE) break;
      }
    } catch (e) {
      stats.errorMessages.push(
        `saleStat result_type=${resultType} 失败: ${e instanceof Error ? e.message : String(e)}`,
      );
    }
  }

  if (qtyMap.size > 0 || amountMap.size > 0) {
    stats.salesUpserted = await upsertFactSales(
      db, store, dataDate, productMap, qtyMap, amountMap, lastSaleRawId, stats.errorMessages,
    );
    console.log(`    销售写入: ${stats.salesUpserted} (qty来源 ${qtyMap.size} / amount来源 ${amountMap.size})`);
  }

  // ── 4. reportAdItemSpList → fact_ads_product_daily ───────────────────────

  if (!store.advertiserId) {
    console.log(`    广告: 无 advertiserId，跳过`);
  } else {
    const allAdItems: Record<string, unknown>[] = [];
    let lastAdRawId = 0;

    try {
      let fetched = 0;
      for (let pageNum = 1; pageNum <= AD_MAX_PAGES; pageNum++) {
        const resp = await withRetry(`${store.storeName} reportAdItemSpList page=${pageNum}`, () =>
          client.request<unknown>({
            method: "POST",
            path: AD_ITEM_SP_PATH,
            params: {
              advertiserIds: [store.advertiserId],
              campaignType: ["sponsoredProducts-manual", "sponsoredProducts-auto"],
              startDate: dataDate,
              endDate: dataDate,
              pageNum,
              pageSize: AD_PAGE_SIZE,
              paging: true,
            },
            timeoutMs: TIMEOUT_MS,
          }),
        );

        const rawId = await insertRaw(db, AD_ITEM_SP_PATH, dataDate, pageNum, resp, taskId);
        if (rawId) { lastAdRawId = rawId; stats.rawRecords++; }

        const pageItems = extractList(resp.data) as Record<string, unknown>[];
        fetched += pageItems.length;
        allAdItems.push(...pageItems);

        const total = extractTotal(resp.data);
        if (pageItems.length < AD_PAGE_SIZE || (total > 0 && fetched >= total)) break;
      }
    } catch (e) {
      stats.errorMessages.push(`ads 失败: ${e instanceof Error ? e.message : String(e)}`);
    }

    if (allAdItems.length > 0) {
      stats.adUpserted = await upsertFactAds(db, store, dataDate, allAdItems, lastAdRawId);
      console.log(`    广告写入: ${stats.adUpserted}`);
    }
  }

  if (stats.errorMessages.length > 0) {
    console.warn(`    ⚠️  错误: ${stats.errorMessages.join(" | ")}`);
  }

  return stats;
}

// ── 主入口 ────────────────────────────────────────────────────────────────────

// 2026-07-30 多MSKU同ItemID发布状态一致：把每个ItemID唯一的非空 walmart_publish_status 铺给其空状态兄弟MSKU行
// （仅填空、不覆盖非空；仅当该ItemID只有一个非空状态即无冲突时才铺，PUBLISHED/UNPUBLISHED并存则整组跳过）
async function propagatePublishStatusToSiblings(db: mysql.Connection): Promise<void> {
  const [res] = await db.query<mysql.ResultSetHeader>(
    `UPDATE dim_product d
     JOIN (
       SELECT platform, item_id,
              MAX(NULLIF(walmart_publish_status, '')) AS ps,
              COUNT(DISTINCT NULLIF(walmart_publish_status, '')) AS n_distinct
       FROM dim_product
       WHERE platform = 'walmart'
       GROUP BY platform, item_id
       HAVING ps IS NOT NULL AND n_distinct = 1
     ) x ON x.platform = d.platform AND x.item_id = d.item_id
     SET d.walmart_publish_status = x.ps, d.updated_at = NOW()
     WHERE d.platform = 'walmart' AND COALESCE(d.walmart_publish_status, '') = ''`,
  );
  console.log(`[publish-status 传播] 空状态兄弟MSKU行回填 ${res.affectedRows} 行（同ItemID唯一非空状态铺开）`);
}

async function main(): Promise<void> {
  const dataDate  = getCliDate();
  const lxdbTag   = makeLxdbTag();

  // 店铺来源改为 dim_store_config（读表失败自动回退写死 STORES）
  const stores = await loadStores();

  console.log(`\n══════════════════════════════════════════════════`);
  console.log(`  领星销售数据入库`);
  console.log(`  标签:     ${lxdbTag}`);
  console.log(`  数据日期: ${dataDate}`);
  console.log(`  店铺数:   ${stores.length}`);
  console.log(`══════════════════════════════════════════════════\n`);

  const db = await getDb();
  const cfg = loadConfig();
  const client = new LingxingClient(cfg);

  const dbTaskId = await logTaskStart(db, lxdbTag, dataDate);
  console.log(`  sync_task_log.task_id = ${dbTaskId}\n`);

  const allStats: StoreStats[] = [];
  let overallError: string | undefined;

  try {
    for (const store of stores) {
      const stats = await syncStore(db, client, store, dataDate, lxdbTag);
      allStats.push(stats);
    }
    // 2026-07-30 B: 多MSKU同ItemID发布状态一致——回填空状态兄弟MSKU行
    await propagatePublishStatusToSiblings(db);
  } catch (e) {
    overallError = e instanceof Error ? e.message : String(e);
    console.error(`\n❌ 顶层错误: ${overallError}`);
  }

  // 汇总
  const hasError = overallError || allStats.some((s) => s.errorMessages.length > 0);
  await logTaskEnd(db, dbTaskId, hasError ? "failed" : "success", allStats, overallError);
  await db.end();

  // 打印汇总
  console.log(`\n══ 完成 ═══════════════════════════════════════════`);
  for (const s of allStats) {
    const errFlag = s.errorMessages.length > 0 ? " ⚠️" : "";
    console.log(
      `  ${s.storeName}${errFlag}: ` +
      `商品 ${s.walmartListItems} | 库存 ${s.inventoryUpserted} | ` +
      `销售 ${s.salesUpserted} | 广告 ${s.adUpserted} | RAW ${s.rawRecords}`,
    );
  }
  console.log(`══════════════════════════════════════════════════\n`);

  if (hasError) process.exit(1);
}

main().catch((e) => {
  console.error("致命错误:", e);
  process.exit(1);
});
