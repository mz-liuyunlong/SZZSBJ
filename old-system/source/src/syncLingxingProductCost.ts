/**
 * syncLingxingProductCost.ts
 *
 * 从领星 batchGetProductInfo 拉取产品成本，写入 dim_product_cost_config。
 *
 * 字段口径（严格）：
 *   cg_price                             → purchase_cost
 *   product_logistics_relation[US_cg_transport_costs] → first_mile_shipping_cost
 *   （飞书配送费 → last_mile_delivery_fee，由 syncFeishuItemOwnerToMysql.ts 负责，本脚本不触碰）
 *
 * 本脚本只写入/更新：
 *   purchase_cost / first_mile_shipping_cost / source_system / source_raw_id / updated_at
 *   绝对不覆盖：last_mile_delivery_fee / delivery_fee / dim_product_owner / dim_product_identity
 *
 * 用法：
 *   npx ts-node src/syncLingxingProductCost.ts                  # dry-run
 *   npx ts-node src/syncLingxingProductCost.ts --confirm-write  # 正式写入
 *   npx ts-node src/syncLingxingProductCost.ts --confirm-write --date=2026-06-25
 *
 * 前置条件（执行一次）：
 *   mysql walmart_ai_data < sql/004_add_cost_columns.sql
 */

import * as crypto from "crypto";
import * as mysql from "mysql2/promise";
import { loadConfig } from "./config";
import { LingxingClient } from "./lingxingClient";

// ── 常量 ──────────────────────────────────────────────────────────────────────

const SCRIPT_NAME = "syncLingxingProductCost";
const PRODUCT_COST_PATH = "/erp/sc/routing/data/local_inventory/batchGetProductInfo";
const BATCH_SIZE = 50;          // 每批 MSKU 数量
const DELAY_BATCH_MS = 1000;    // 批次间隔（ms）
const TIMEOUT_MS = 120_000;
const RETRY_MAX = 3;
const RETRY_DELAY_MS = 10_000;

// ── CLI 参数 ──────────────────────────────────────────────────────────────────

const DRY_RUN = !process.argv.includes("--confirm-write");

const EFFECTIVE_DATE = (() => {
  const arg = process.argv.find((a) => a.startsWith("--date="));
  if (arg) return arg.slice("--date=".length);
  return new Date().toISOString().slice(0, 10);
})();

// ── 类型 ──────────────────────────────────────────────────────────────────────

interface IdentityRow {
  platform: string;
  store_id: string;
  store_name: string;
  item_id: string;
  msku: string;
  sku: string;   // 本地 SKU（无店铺后缀），用于调接口
}

interface CostRecord {
  msku: string;
  purchaseCost: number | null;       // cg_price
  firstMileShipping: number | null;  // US_cg_transport_costs
}

interface UpsertResult {
  inserted: number;
  updated: number;
  unchanged: number;
}

// ── 工具函数 ──────────────────────────────────────────────────────────────────

function chunkArray<T>(arr: T[], size: number): T[][] {
  const result: T[][] = [];
  for (let i = 0; i < arr.length; i += size) result.push(arr.slice(i, i + size));
  return result;
}

function sleep(ms: number) {
  return new Promise<void>((r) => setTimeout(r, ms));
}

function parseNumber(value: unknown): number | null {
  const text = String(value ?? "").trim();
  if (!text) return null;
  const num = Number(text);
  return Number.isFinite(num) ? num : null;
}

// 悦斯CS规则：MSKU 以 CS 开头 → 采购 ¥200、头程 ¥1（写死）。
// 注：dim_product_identity 的 store_name 基本为空，无法用 CN2502 门槛；按业务规则只按 MSKU 前缀判定。
const YUESI_CS_PURCHASE_COST = 200;
const YUESI_CS_FIRST_MILE = 1;
function isYuesiCS(_storeName: string, msku: string): boolean {
  return String(msku ?? "").trim().toUpperCase().startsWith("CS");
}

/**
 * 从 product_logistics_relation 提取 US_cg_transport_costs（头程运费）
 * 字段可能是数组 [{US_cg_transport_costs: ...}, ...] 或单个对象
 */
function extractFirstMileShipping(value: unknown): number | null {
  if (Array.isArray(value)) {
    for (const item of value) {
      if (item && typeof item === "object" && "US_cg_transport_costs" in item) {
        return parseNumber((item as Record<string, unknown>).US_cg_transport_costs);
      }
    }
    return null;
  }
  if (value && typeof value === "object" && "US_cg_transport_costs" in value) {
    return parseNumber((value as Record<string, unknown>).US_cg_transport_costs);
  }
  return null;
}

async function withRetry<T>(label: string, fn: () => Promise<T>): Promise<T> {
  let lastErr: unknown;
  for (let attempt = 1; attempt <= RETRY_MAX; attempt++) {
    try {
      return await fn();
    } catch (err) {
      lastErr = err;
      console.warn(`  [重试 ${attempt}/${RETRY_MAX}] ${label}: ${String(err)}`);
      if (attempt < RETRY_MAX) await sleep(RETRY_DELAY_MS);
    }
  }
  throw lastErr;
}

function upsertCount(affectedRows: number): UpsertResult {
  // ON DUPLICATE KEY UPDATE: affectedRows 1=新增 2=更新 0=未变化
  if (affectedRows === 1) return { inserted: 1, updated: 0, unchanged: 0 };
  if (affectedRows === 2) return { inserted: 0, updated: 1, unchanged: 0 };
  return { inserted: 0, updated: 0, unchanged: 1 };
}

function hr(char = "─") {
  return char.repeat(60);
}

// ── RAW 层写入（每批一条）────────────────────────────────────────────────────

async function saveRawRecord(
  db: mysql.Connection,
  params: Record<string, unknown>,
  response: unknown,
): Promise<string> {
  const rawJson = JSON.stringify(response);
  const rawHash = crypto.createHash("md5").update(rawJson).digest("hex").slice(0, 64);
  const reqJson = JSON.stringify(params);

  await db.query(
    `INSERT IGNORE INTO raw_lingxing_api
       (api_path, request_method, request_params_json, response_json,
        response_code, is_success, data_date, raw_hash)
     VALUES (?, 'POST', ?, ?, '0', 1, ?, ?)`,
    [PRODUCT_COST_PATH, reqJson, rawJson, EFFECTIVE_DATE, rawHash],
  );

  return rawHash; // 返回用于 source_raw_id
}

// ── 主流程 ────────────────────────────────────────────────────────────────────

async function run() {
  console.log(hr("="));
  console.log(`${SCRIPT_NAME}`);
  console.log(`模式: ${DRY_RUN ? "DRY-RUN（只预览，不写入）" : "正式写入"}`);
  console.log(`生效日期: ${EFFECTIVE_DATE}`);
  console.log(hr("="));

  const cfg = loadConfig();
  const db = await mysql.createConnection({
    host:     process.env.DB_HOST     ?? "127.0.0.1",
    port:     Number(process.env.DB_PORT ?? 3306),
    user:     process.env.DB_USER     ?? "",
    password: process.env.DB_PASSWORD ?? "",
    database: process.env.DB_NAME     ?? "walmart_ai_data",
  });

  try {
    // ── Step 1: 读取 MSKU + 本地SKU 列表 ───────────────────────────────────
    // 关键：领星 batchGetProductInfo 的 skus 参数认的是【本地 SKU】(local_sku，无店铺后缀)，
    // 不是店铺 MSKU。identity.sku 为空时回退到 dim_product.sku，提高覆盖。
    console.log("\n[1/4] 从 dim_product_identity 读取 MSKU + 本地SKU 列表...");

    // 取数源 = dim_product_identity（飞书CS/负责人品）∪ dim_product（领星每日同步）∪ FACT 表（页面出现的全部产品）
    const [rows] = await db.query<mysql.RowDataPacket[]>(
      `SELECT platform, store_id, store_name, item_id, msku, MAX(sku) AS sku FROM (
         SELECT i.platform, i.store_id, i.store_name, i.item_id, i.msku,
                COALESCE(NULLIF(i.sku, ''), p.sku, '') AS sku
         FROM dim_product_identity i
         LEFT JOIN dim_product p
           ON p.item_id = i.item_id AND p.platform = i.platform
         WHERE i.msku IS NOT NULL AND i.msku != ''
         UNION ALL
         SELECT dp.platform, dp.store_id, dp.store_name, dp.item_id, dp.msku,
                COALESCE(dp.sku, '') AS sku
         FROM dim_product dp
         WHERE dp.platform = 'walmart' AND dp.msku IS NOT NULL AND dp.msku != ''
         UNION ALL
         SELECT 'walmart', fs.store_id, fs.store_name, fs.item_id, fs.msku, COALESCE(fs.sku, '')
         FROM fact_sales_daily fs
         WHERE fs.platform = 'walmart' AND fs.msku IS NOT NULL AND fs.msku != ''
         UNION ALL
         SELECT 'walmart', fi.store_id, fi.store_name, fi.item_id, fi.msku, COALESCE(fi.sku, '')
         FROM fact_inventory_daily fi
         WHERE fi.platform = 'walmart' AND fi.msku IS NOT NULL AND fi.msku != ''
       ) u
       GROUP BY platform, store_id, store_name, item_id, msku
       ORDER BY msku`,
    );

    const identities = rows as IdentityRow[];

    if (identities.length === 0) {
      console.log("  ⚠️  dim_product_identity 为空，请先运行飞书同步脚本");
      return;
    }

    // 按 (item_id|msku) 去重。关键：MSKU 不是 item_id 的唯一键——同一 MSKU 可对应多个 item_id（同款多次刊登），
    // 若只按 MSKU 去重，同 MSKU 的其它 item_id 拿不到成本，页面（按 item_id 关联）就显示 0。
    // 同一 (item_id|msku) 出现多行时，优先保留有本地 sku 的那行。
    const identityMap = new Map<string, IdentityRow>();
    for (const row of identities) {
      const key = `${row.item_id}|${row.msku}`;
      const existing = identityMap.get(key);
      if (!existing || (!String(existing.sku ?? "").trim() && String(row.sku ?? "").trim())) {
        identityMap.set(key, row);
      }
    }

    // 用【本地 SKU】去调接口（去重、去空）
    const allSkus = Array.from(
      new Set(
        [...identityMap.values()]
          .map((idn) => String(idn.sku ?? "").trim())
          .filter((s) => s !== ""),
      ),
    );
    const batches = chunkArray(allSkus, BATCH_SIZE);

    const mskuNoSku = [...identityMap.values()].filter((idn) => !String(idn.sku ?? "").trim()).length;
    console.log(`  dim_product_identity 总行数: ${identities.length}`);
    console.log(`  去重 item_id+MSKU: ${identityMap.size} 个`);
    console.log(`  去重 本地SKU（用于调接口）: ${allSkus.length} 个`);
    console.log(`  无本地SKU、无法取成本的 MSKU: ${mskuNoSku} 个`);
    console.log(`  分批数量: ${batches.length} 批（每批 ${BATCH_SIZE} 个）`);

    // ── Step 2: 调用领星 API ───────────────────────────────────────────────
    console.log("\n[2/4] 调用 batchGetProductInfo 接口...");

    const client = new LingxingClient(cfg);

    // msku → CostRecord（含 source_raw_id）
    const costMap = new Map<string, CostRecord & { rawHash: string }>();
    let apiErrorCount = 0;
    let totalApiItems = 0;

    for (const [i, batch] of batches.entries()) {
      const label = `批次 ${i + 1}/${batches.length}`;
      try {
        const params = { skus: batch };
        const response = await withRetry(label, () =>
          client.request<unknown>({
            method: "POST",
            path: PRODUCT_COST_PATH,
            params,
            timeoutMs: TIMEOUT_MS,
          }),
        );

        // ── RAW 层写入（每批一条，dry-run 不写）
        let rawHash = "dry-run";
        if (!DRY_RUN) {
          rawHash = await saveRawRecord(db, params, response);
        }

        const data = (response as { data?: unknown }).data;
        const items = Array.isArray(data) ? data : [];
        totalApiItems += items.length;

        for (const item of items) {
          if (!item || typeof item !== "object") continue;
          const rec = item as Record<string, unknown>;
          const sku = String(rec.sku ?? "").trim();   // 领星返回的是【本地 SKU】
          if (!sku) continue;

          costMap.set(sku, {
            msku: sku,
            purchaseCost: parseNumber(rec.cg_price),
            firstMileShipping: extractFirstMileShipping(rec.product_logistics_relation),
            rawHash,
          });
        }

        console.log(`  ✓ ${label}: 返回 ${items.length} 条`);
      } catch (err) {
        console.error(`  ✗ ${label} 失败: ${String(err)}`);
        apiErrorCount++;
      }

      if (i < batches.length - 1) await sleep(DELAY_BATCH_MS);
    }

    // 取每个 MSKU 的有效成本：CS 固定规则优先，否则按本地SKU 命中领星
    const effectiveCost = (idn: IdentityRow): (CostRecord & { rawHash: string }) | undefined => {
      if (isYuesiCS(idn.store_name, idn.msku)) {
        return { msku: idn.msku, purchaseCost: YUESI_CS_PURCHASE_COST, firstMileShipping: YUESI_CS_FIRST_MILE, rawHash: "fixed_cs_rule" };
      }
      const sku = String(idn.sku ?? "").trim();
      return sku ? costMap.get(sku) : undefined;
    };

    // ── Step 3: API 结果统计（按 MSKU 维度，一个本地SKU 可对应多个 MSKU）──────
    const skuWithPurchase = [...costMap.values()].filter((c) => c.purchaseCost !== null).length;
    const skuWithFirstMile = [...costMap.values()].filter((c) => c.firstMileShipping !== null).length;
    const csIdentities = [...identityMap.values()].filter((idn) => isYuesiCS(idn.store_name, idn.msku)).length;

    // 每个 MSKU 的有效成本（含 CS 固定规则）
    const costedIdentities = [...identityMap.values()].filter((idn) => {
      const c = effectiveCost(idn);
      return !!c && (c.purchaseCost !== null || c.firstMileShipping !== null);
    });

    console.log("\n[3/4] API 结果汇总:");
    console.log(`  API 总返回条数:                  ${totalApiItems}`);
    console.log(`  命中成本的本地SKU:               ${costMap.size}`);
    console.log(`    含 cg_price（采购成本）:        ${skuWithPurchase}`);
    console.log(`    含 US_cg_transport_costs（头程）: ${skuWithFirstMile}`);
    console.log(`  CS固定成本 MSKU（MSKU以CS开头，采购¥${YUESI_CS_PURCHASE_COST}/头程¥${YUESI_CS_FIRST_MILE}）: ${csIdentities}`);
    console.log(`  准备写入 dim_product_cost_config（按MSKU）: ${costedIdentities.length} 条`);
    console.log(`  API 错误批次: ${apiErrorCount}`);

    if (DRY_RUN) {
      console.log("\n  [DRY-RUN 样本预览]（前10条）:");
      let count = 0;
      for (const idn of costedIdentities) {
        const cost = effectiveCost(idn)!;
        console.log(
          `    MSKU: ${String(idn.msku).padEnd(16)} | 本地SKU: ${String(idn.sku).padEnd(12)} | 采购: ${String(cost.purchaseCost ?? "-").padStart(8)} | 头程: ${String(cost.firstMileShipping ?? "-").padStart(8)} | item_id: ${idn.item_id || "(未匹配)"}`,
        );
        if (++count >= 10) {
          console.log(`    ... 剩余 ${costedIdentities.length - count} 条`);
          break;
        }
      }
      console.log("\n" + hr("="));
      console.log("DRY-RUN 完成（未写入任何数据）");
      console.log("加 --confirm-write 参数正式写入");
      console.log(hr("="));
      return;
    }

    // ── Step 4: 写入 dim_product_cost_config ──────────────────────────────
    console.log("\n[4/4] 写入 dim_product_cost_config...");

    let totalInserted = 0;
    let totalUpdated = 0;
    let totalUnchanged = 0;
    let totalSkipped = 0;

    for (const identity of identityMap.values()) {
      const cost = effectiveCost(identity);
      if (!cost || (cost.purchaseCost === null && cost.firstMileShipping === null)) {
        totalSkipped++;
        continue;
      }

      const platform   = identity.platform   ?? "walmart";
      const store_id   = identity.store_id   ?? "";
      const store_name = identity.store_name ?? "";
      const item_id    = identity.item_id    ?? "";
      const msku       = identity.msku;

      // INSERT ... ON DUPLICATE KEY UPDATE
      // 只更新领星来源字段，绝对不触碰 last_mile_delivery_fee / delivery_fee
      const [result] = await db.query<mysql.ResultSetHeader>(
        `INSERT INTO dim_product_cost_config
           (platform, store_id, store_name, item_id, msku,
            purchase_cost, first_mile_shipping_cost,
            effective_date, source_system, source_raw_id)
         VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'lingxing_api', ?)
         ON DUPLICATE KEY UPDATE
           purchase_cost            = VALUES(purchase_cost),
           first_mile_shipping_cost = VALUES(first_mile_shipping_cost),
           source_system            = 'lingxing_api',
           source_raw_id            = VALUES(source_raw_id),
           updated_at               = CURRENT_TIMESTAMP`,
        [
          platform, store_id, store_name, item_id, msku,
          cost.purchaseCost,
          cost.firstMileShipping,
          EFFECTIVE_DATE,
          cost.rawHash,
        ],
      );

      const r = upsertCount(result.affectedRows);
      totalInserted += r.inserted;
      totalUpdated  += r.updated;
      totalUnchanged += r.unchanged;
    }

    // ── 结果 ────────────────────────────────────────────────────────────────
    console.log("\n" + hr("="));
    console.log("✅ 同步完成");
    console.log(`  新增: ${totalInserted}`);
    console.log(`  更新: ${totalUpdated}`);
    console.log(`  未变化: ${totalUnchanged}`);
    console.log(`  跳过（无成本数据）: ${totalSkipped}`);
    console.log(`  API 错误批次: ${apiErrorCount}`);
    console.log(hr());
    console.log("验证查询:");
    console.log("  SELECT msku, purchase_cost, first_mile_shipping_cost, last_mile_delivery_fee");
    console.log("  FROM dim_product_cost_config LIMIT 10;");
    console.log(hr("="));
  } finally {
    await db.end();
  }
}

run().catch((err) => {
  console.error(`${SCRIPT_NAME} 失败:`, err);
  process.exit(1);
});
