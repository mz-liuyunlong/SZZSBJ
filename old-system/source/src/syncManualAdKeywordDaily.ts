/**
 * syncManualAdKeywordDaily.ts
 *
 * 从领星 API 拉取 Walmart 手动广告关键词数据，写入 fact_ads_keyword_daily
 *
 * 执行方式：
 *   npx ts-node src/syncManualAdKeywordDaily.ts
 *   npx ts-node src/syncManualAdKeywordDaily.ts --date=2026-06-20
 *   npx ts-node src/syncManualAdKeywordDaily.ts --startDate=2026-06-15 --endDate=2026-06-20
 *
 * 环境变量（.env）：
 *   DB_HOST / DB_PORT / DB_USER / DB_PASSWORD / DB_NAME
 *   LINGXING_APP_ID / LINGXING_APP_SECRET 等（通过 loadConfig 读取）
 *
 * v2（2026-07-16 数据质量修复）：
 *   1. 比率归一：领星API返回 ctr/cvr/acos 为百分数口径（诊断实测≈真实值×100），
 *      写入前÷100 统一为小数口径（与自动CSV一致）；roas 为自然比值不动。
 *   2. 全零行跳过：impressions/clicks/ad_spend/orders/total_sales 全为0的行不写FACT
 *      （历史97%行为全零，主要来自暂停的关键词/活动持续回传；RAW照常留痕）。
 */

import "dotenv/config";
import * as crypto from "crypto";
import * as mysql from "mysql2/promise";
import { loadConfig } from "./config";
import { LingxingClient } from "./lingxingClient";
import { STORES, StoreConfig } from "./syncDailyBaseData";
import { loadStores } from "./storeRegistry";

// ── 常量 ──────────────────────────────────────────────────────────────────────

const ITEM_PATH       = "/basicOpen/multiplatform/ads/reportAdItemSpList";
const KEYWORD_PATH    = "/basicOpen/multiplatform/ads/reportKeywordSpList";
const PAGE_SIZE       = 200;
const MAX_PAGES       = 50;
const TIMEOUT_MS      = 120000;
const TASK_NAME       = "manual_ad_keyword_sync";

// 限速配置
const DELAY_PAGE_MS   = 500;   // 每页请求间隔
const DELAY_STORE_MS  = 3000;  // 每个店铺间隔
const DELAY_DATE_MS   = 8000;  // 回填多天时每天间隔
const RETRY_MAX       = 5;     // 遇到限速错误最多重试次数
const RETRY_DELAY_MS  = 30000; // 限速重试等待时间（30s）

// ── 类型 ──────────────────────────────────────────────────────────────────────

type Row = Record<string, unknown>;

interface KeywordRow {
  stat_date:          string;
  platform:           string;
  store_id:           string;
  store_name:         string;
  advertiser_id:      string;
  campaign_id:        string;
  campaign_name:      string;
  campaign_type:      string;
  ad_group_id:        string;
  ad_group_name:      string;
  item_id:            string;
  msku:               string;
  keyword:            string;
  normalized_keyword: string;
  match_type:         string;
  keyword_type:       string;
  impressions:        number;
  clicks:             number;
  ctr:                number;
  ad_spend:           number;
  orders:             number;
  conversion_rate:    number;
  total_sales:        number;
  acos:               number;
  cpc:                number;
  cvr:                number;
  roas:               number;
  keyword_bid:        number | null;
  source_type:        string;
  source_system:      string;
  extra_json:         string;
}

// ── 工具函数 ──────────────────────────────────────────────────────────────────

function getArg(name: string, defaultValue = ""): string {
  const prefix = `--${name}=`;
  const arg = process.argv.find((a) => a.startsWith(prefix));
  return arg ? arg.slice(prefix.length) : defaultValue;
}

function getChinaDate(offsetDays = 0): string {
  const date = new Date();
  date.setUTCHours(date.getUTCHours() + 8);
  date.setUTCDate(date.getUTCDate() + offsetDays);
  return date.toISOString().slice(0, 10);
}

function toNum(v: unknown): number {
  if (typeof v === "number") return Number.isFinite(v) ? v : 0;
  const n = Number(String(v ?? "").replace(/,/g, "").replace("%", ""));
  return Number.isFinite(n) ? n : 0;
}

/** 百分数口径→小数口径（领星API ctr/cvr/acos 实测为百分数，2026-07-16 诊断定稿） */
function pctToFrac(v: unknown): number {
  return toNum(v) / 100;
}

function toStr(v: unknown): string {
  return String(v ?? "").trim();
}

function extractArray(data: unknown): Row[] {
  const check = (v: unknown): v is Row[] => Array.isArray(v);
  if (check(data)) return data;
  if (data && typeof data === "object") {
    const d = data as Record<string, unknown>;
    if (check(d.data)) return d.data;
    if (check(d.list)) return d.list;
    if (check(d.rows)) return d.rows;
    if (d.data && typeof d.data === "object") {
      const nested = d.data as Record<string, unknown>;
      if (check(nested.list)) return nested.list;
      if (check(nested.rows)) return nested.rows;
    }
  }
  return [];
}

function extractTotal(data: unknown): number {
  if (!data || typeof data !== "object") return 0;
  const d = data as Record<string, unknown>;
  const t = Number(d.total);
  if (Number.isFinite(t) && t > 0) return t;
  if (d.data && typeof d.data === "object") {
    const n = Number((d.data as Record<string, unknown>).total);
    if (Number.isFinite(n) && n > 0) return n;
  }
  return 0;
}

// ── 工具：延迟 ───────────────────────────────────────────────────────────────

function sleep(ms: number): Promise<void> {
  return new Promise((r) => setTimeout(r, ms));
}

// ── RAW 层：保存每页原始响应到 raw_lingxing_api ──────────────────────────────

async function saveRawPage(
  db: mysql.Connection,
  path: string,
  params: Record<string, unknown>,
  response: unknown,
  dataDate: string,
): Promise<void> {
  const rawJson  = JSON.stringify(response);
  const rawHash  = crypto.createHash("md5").update(rawJson).digest("hex").slice(0, 64);
  const reqJson  = JSON.stringify(params);
  await db.query(
    `INSERT IGNORE INTO raw_lingxing_api
       (api_path, request_method, request_params_json, response_json,
        response_code, is_success, data_date, raw_hash)
     VALUES (?, 'POST', ?, ?, '0', 1, ?, ?)`,
    [path, reqJson, rawJson, dataDate, rawHash],
  );
}

// ── API 分页拉取（含页间延迟 + 限速重试 + RAW 层写入） ───────────────────────

async function fetchAllPages(
  client: LingxingClient,
  path: string,
  baseParams: Record<string, unknown>,
  db: mysql.Connection,
  dataDate: string,
): Promise<Row[]> {
  const rows: Row[] = [];
  for (let page = 1; page <= MAX_PAGES; page++) {
    if (page > 1) await sleep(DELAY_PAGE_MS);

    let lastErr: unknown;
    let resp: Awaited<ReturnType<typeof client.request<unknown>>> | null = null;
    const pageParams = { ...baseParams, pageNum: page, pageSize: PAGE_SIZE, paging: true };

    for (let attempt = 0; attempt < RETRY_MAX; attempt++) {
      try {
        resp = await client.request<unknown>({
          method: "POST",
          path,
          params: pageParams,
          timeoutMs: TIMEOUT_MS,
        });
        break;
      } catch (e: unknown) {
        lastErr = e;
        const msg = e instanceof Error ? e.message : String(e);
        const isRateLimit = msg.includes("429") || msg.includes("503") || msg.includes("rate") || msg.includes("limit");
        if (isRateLimit && attempt < RETRY_MAX - 1) {
          console.log(`  ⏳ 触发限速，等待 ${RETRY_DELAY_MS / 1000}s 后重试（第 ${attempt + 1} 次）...`);
          await sleep(RETRY_DELAY_MS);
        } else {
          throw e;
        }
      }
    }
    if (!resp) throw lastErr ?? new Error("请求失败");

    // ── 写 RAW 层 ─────────────────────────────────────────────────────────────
    await saveRawPage(db, path, pageParams, resp.data, dataDate);

    const items = extractArray(resp.data);
    rows.push(...items);
    const total = extractTotal(resp.data);
    if (items.length < PAGE_SIZE || (total > 0 && rows.length >= total)) break;
  }
  return rows;
}

// ── 单店铺同步 ────────────────────────────────────────────────────────────────

async function syncStore(
  client: LingxingClient,
  store: StoreConfig,
  startDate: string,
  endDate: string,
): Promise<{ inserted: number; updated: number; skipped: number }> {
  if (!store.advertiserId) {
    console.log(`  ⚠️  ${store.storeName} 无 advertiserId，跳过`);
    return { inserted: 0, updated: 0, skipped: 0 };
  }

  // ── 建立 DB 连接（RAW + FACT 共用） ──────────────────────────────────────────
  const db = await mysql.createConnection({
    host:     process.env.DB_HOST     ?? "127.0.0.1",
    port:     Number(process.env.DB_PORT ?? 3306),
    user:     process.env.DB_USER     ?? "",
    password: process.env.DB_PASSWORD ?? "",
    database: process.env.DB_NAME     ?? "walmart_ai_data",
  });

  try {

  const baseParams = {
    advertiserIds: [store.advertiserId],
    campaignType: ["sponsoredProducts-manual"],
    startDate,
    endDate,
  };

  // 0.5 MSKU回填映射（2026-07-17 修复：上游商品维度接口6月下旬起不再返回msku/sku，
  //     RAW已证实为上游字段缺失。按 store_id+item_id 在 dim_product 唯一命中才回填，
  //     一品多MSKU不猜测保持空——与 <REDACTED_FEISHU_SHEET_ID> 展示补齐同一护栏）
  const [dimMskuRows] = await db.query<mysql.RowDataPacket[]>(
    `SELECT store_id, item_id, MAX(msku) AS msku
     FROM dim_product
     WHERE platform = 'walmart' AND COALESCE(msku,'') <> ''
     GROUP BY store_id, item_id
     HAVING COUNT(DISTINCT msku) = 1`,
  );
  const uniqueMskuMap = new Map<string, string>();
  for (const r of dimMskuRows) uniqueMskuMap.set(`${r.store_id}|${r.item_id}`, String(r.msku));

  // 1. 拉商品维度 → 建立 campaignId+adGroupId → itemId 映射（顺带写 RAW）
  console.log(`  📦 拉取商品维度数据...`);
  const itemRows = await fetchAllPages(client, ITEM_PATH, baseParams, db, startDate);
  const campaignItemMap = new Map<string, { item_id: string; msku: string }>();
  for (const r of itemRows) {
    const campaignId  = toStr(r.campaignId);
    const adGroupId   = toStr(r.adGroupId);
    const itemId      = toStr(r.itemId ?? r.platformProductId ?? r.productId);
    const msku        = toStr(r.msku ?? r.sku ?? "");
    if (campaignId && itemId) {
      const key = `${campaignId}|${adGroupId}`;
      if (!campaignItemMap.has(key)) {
        campaignItemMap.set(key, { item_id: itemId, msku });
      }
    }
  }
  console.log(`  📦 商品维度 ${itemRows.length} 条，映射 ${campaignItemMap.size} 个 campaign+adGroup`);

  // 2. 拉关键词维度（顺带写 RAW）
  console.log(`  🔑 拉取关键词数据...`);
  const kwRows = await fetchAllPages(client, KEYWORD_PATH, baseParams, db, startDate);
  console.log(`  🔑 关键词数据 ${kwRows.length} 条`);

  // 3. 组装写入数据
  const rows: KeywordRow[] = [];
  let zeroSkipped = 0; // v2：全零行（暂停实体持续零回传）跳过计数，必报不吞
  for (const r of kwRows) {
    const campaignId = toStr(r.campaignId);
    const adGroupId  = toStr(r.adGroupId);
    const key        = `${campaignId}|${adGroupId}`;
    const itemInfo   = campaignItemMap.get(key) ?? { item_id: "", msku: "" };
    // MSKU fallback（2026-07-17）：接口未返回时按 store+item 唯一命中回填
    if (!itemInfo.msku && itemInfo.item_id) {
      itemInfo.msku = uniqueMskuMap.get(`${store.storeId}|${itemInfo.item_id}`) ?? "";
    }

    const keyword     = toStr(r.keywordName ?? r.keyword ?? r.targetingText ?? "");
    const matchType   = toStr(r.matchType ?? "broad");
    const kwType      = toStr(r.targetingType ?? "manual");

    if (!keyword) continue;

    // v2：全零行不入FACT（暂停实体的持续零回传=无效数据；RAW已留痕可追溯）
    if (toNum(r.numAdsShown) === 0 && toNum(r.numAdsClicks) === 0
        && toNum(r.adSpend) === 0 && toNum(r.attributedOrders) === 0
        && toNum(r.attributedSales) === 0) {
      zeroSkipped++;
      continue;
    }

    rows.push({
      stat_date:          startDate,
      platform:           "walmart",
      store_id:           store.storeId,
      store_name:         toStr(r.mpSellerName ?? store.storeName),
      advertiser_id:      toStr(r.advertiserId ?? store.advertiserId),
      campaign_id:        campaignId,
      campaign_name:      toStr(r.campaignName),
      campaign_type:      toStr(r.campaignType ?? "sponsoredProducts"),
      ad_group_id:        adGroupId,
      ad_group_name:      toStr(r.adGroupName),
      item_id:            itemInfo.item_id,
      msku:               itemInfo.msku,
      keyword,
      normalized_keyword: keyword.toLowerCase().trim(),
      match_type:         matchType,
      keyword_type:       kwType,
      impressions:        toNum(r.numAdsShown),
      clicks:             toNum(r.numAdsClicks),
      ctr:                pctToFrac(r.ctr),
      ad_spend:           toNum(r.adSpend),
      orders:             toNum(r.attributedOrders),
      conversion_rate:    pctToFrac(r.cvr),
      total_sales:        toNum(r.attributedSales),
      acos:               pctToFrac(r.acos),
      cpc:                toNum(r.cpc),
      cvr:                pctToFrac(r.cvr),
      roas:               toNum(r.roas),
      keyword_bid:        r.keywordBid != null ? toNum(r.keywordBid) : null,
      source_type:        "manual_kw",
      source_system:      "lingxing",
      extra_json:         JSON.stringify({ keywordId: toStr(r.keywordId ?? r.key) }),
    });
  }

  if (zeroSkipped > 0) console.log(`  ⏭️  全零行跳过 ${zeroSkipped} 条（暂停/无流量实体，RAW已留痕）`);
  if (rows.length === 0) {
    console.log(`  ℹ️  无有效数据`);
    return { inserted: 0, updated: 0, skipped: 0 };
  }

  // 4. 写入 fact_ads_keyword_daily
  {
    const batchSql = `
      INSERT INTO fact_ads_keyword_daily
        (stat_date, platform, store_id, store_name, advertiser_id,
         campaign_id, campaign_name, campaign_type, ad_group_id, ad_group_name,
         item_id, msku, keyword, normalized_keyword, match_type, keyword_type,
         impressions, clicks, ctr, ad_spend, orders, conversion_rate,
         total_sales, acos, cpc, cvr, roas, keyword_bid, source_type, source_system, extra_json)
      VALUES ?
      ON DUPLICATE KEY UPDATE
        impressions     = VALUES(impressions),
        clicks          = VALUES(clicks),
        ctr             = VALUES(ctr),
        ad_spend        = VALUES(ad_spend),
        orders          = VALUES(orders),
        conversion_rate = VALUES(conversion_rate),
        total_sales     = VALUES(total_sales),
        acos            = VALUES(acos),
        cpc             = VALUES(cpc),
        roas            = VALUES(roas),
        keyword_bid     = VALUES(keyword_bid),
        extra_json      = VALUES(extra_json)
    `;

    // 写入前查行数，写入后对比，精确计算新增/更新
    const [[{ before }]] = await db.query<mysql.RowDataPacket[]>(
      `SELECT COUNT(*) AS \`before\` FROM fact_ads_keyword_daily
       WHERE stat_date=? AND store_id=? AND source_type='manual_kw'`,
      [startDate, store.storeId],
    );

    const BATCH = 500;
    for (let i = 0; i < rows.length; i += BATCH) {
      const batch = rows.slice(i, i + BATCH);
      const values = batch.map((row) => [
        row.stat_date, row.platform, row.store_id, row.store_name, row.advertiser_id,
        row.campaign_id, row.campaign_name, row.campaign_type, row.ad_group_id, row.ad_group_name,
        row.item_id, row.msku, row.keyword, row.normalized_keyword, row.match_type, row.keyword_type,
        row.impressions, row.clicks, row.ctr, row.ad_spend, row.orders, row.conversion_rate,
        row.total_sales, row.acos, row.cpc, row.cvr, row.roas, row.keyword_bid,
        row.source_type, row.source_system, row.extra_json,
      ]);
      await db.query<mysql.ResultSetHeader>(batchSql, [values]);
    }

    const [[{ after }]] = await db.query<mysql.RowDataPacket[]>(
      `SELECT COUNT(*) AS \`after\` FROM fact_ads_keyword_daily
       WHERE stat_date=? AND store_id=? AND source_type='manual_kw'`,
      [startDate, store.storeId],
    );

    const inserted = Math.max(0, Number(after) - Number(before));
    const updated  = rows.length - inserted;
    const skipped  = kwRows.length - rows.length;

    return { inserted, updated, skipped };
  }

  } finally {
    await db.end();
  }
}

// ── 写同步日志 ────────────────────────────────────────────────────────────────

async function writeTaskLog(params: {
  status: "success" | "failed";
  inserted: number;
  updated: number;
  skipped: number;
  error?: string;
}): Promise<void> {
  const db = await mysql.createConnection({
    host:     process.env.DB_HOST     ?? "127.0.0.1",
    port:     Number(process.env.DB_PORT ?? 3306),
    user:     process.env.DB_USER     ?? "",
    password: process.env.DB_PASSWORD ?? "",
    database: process.env.DB_NAME     ?? "walmart_ai_data",
  });
  try {
    await db.query(
      `INSERT INTO sync_task_log
         (task_name, source_system, target_table, status, inserted_count, updated_count, failed_count, finished_at, error_message)
       VALUES (?, 'lingxing_api', 'fact_ads_keyword_daily', ?, ?, ?, ?, NOW(), ?)`,
      [TASK_NAME, params.status, params.inserted, params.updated, params.skipped, params.error ?? null],
    );
  } finally {
    await db.end();
  }
}

// ── 主函数 ────────────────────────────────────────────────────────────────────

async function main(): Promise<void> {
  const dateArg      = getArg("date");
  const startDateArg = getArg("startDate");
  const endDateArg   = getArg("endDate");

  // 默认：前天（广告数据延迟 2 天）
  const defaultDate = getChinaDate(-2);
  const startDate   = startDateArg || dateArg || defaultDate;
  const endDate     = endDateArg   || dateArg || defaultDate;

  console.log("═".repeat(55));
  console.log(`  手动广告关键词同步  ${startDate} → ${endDate}`);
  console.log("═".repeat(55));

  const client = new LingxingClient(loadConfig());
  let totalInserted = 0;
  let totalUpdated  = 0;
  let totalSkipped  = 0;
  let errorMsg      = "";

  try {
    const activeStores = (await loadStores()).filter((s) => s.advertiserId);
    for (let si = 0; si < activeStores.length; si++) {
      const store = activeStores[si];
      if (si > 0) {
        console.log(`  ⏸  店铺间隔 ${DELAY_STORE_MS / 1000}s...`);
        await sleep(DELAY_STORE_MS);
      }
      console.log(`\n🏪 ${store.storeName}`);

      const start = new Date(startDate);
      const end   = new Date(endDate);
      let dayIndex = 0;
      for (let d = new Date(start); d <= end; d.setUTCDate(d.getUTCDate() + 1)) {
        if (dayIndex > 0) {
          console.log(`  ⏸  日期间隔 ${DELAY_DATE_MS / 1000}s...`);
          await sleep(DELAY_DATE_MS);
        }
        const dateStr = d.toISOString().slice(0, 10);
        console.log(`  📅 日期: ${dateStr}`);
        const { inserted, updated, skipped } = await syncStore(client, store, dateStr, dateStr);
        totalInserted += inserted;
        totalUpdated  += updated;
        totalSkipped  += skipped;
        const total = inserted + updated + skipped;
        console.log(`  ✅ 新增 ${inserted} | 更新 ${updated} | 跳过 ${skipped} | 合计 ${total}`);
        dayIndex++;
      }
    }

    await writeTaskLog({ status: "success", inserted: totalInserted, updated: totalUpdated, skipped: totalSkipped });
    console.log("\n" + "═".repeat(55));
    console.log(`✅ 同步完成  新增 ${totalInserted}  更新 ${totalUpdated}  跳过 ${totalSkipped}`);
    console.log("═".repeat(55));
  } catch (e: unknown) {
    errorMsg = e instanceof Error ? e.message : String(e);
    await writeTaskLog({ status: "failed", inserted: totalInserted, updated: totalUpdated, skipped: totalSkipped, error: errorMsg });
    console.error("\n❌ 同步失败:", errorMsg);
    process.exit(1);
  }
}

main();
