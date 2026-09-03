/**
 * syncProductCostToMysql.ts
 *
 * 从领星 batchGetProductInfo 接口拉取采购成本 + 头程成本，写入 dim_product_cost_config。
 *
 * 数据流:
 *   dim_product_identity (MySQL) → MSKU列表
 *   → /erp/sc/routing/data/local_inventory/batchGetProductInfo (50个/批)
 *   → cg_price (采购成本¥) + product_logistics_relation[US_cg_transport_costs] (头程成本¥)
 *   → raw_lingxing_api (RAW层)
 *   → dim_product_cost_config (UPSERT)
 *
 * 用法:
 *   npx ts-node src/syncProductCostToMysql.ts          # dry-run，只预览
 *   npx ts-node src/syncProductCostToMysql.ts --confirm-write   # 写入 MySQL
 *   npx ts-node src/syncProductCostToMysql.ts --confirm-write --date=2026-06-25
 */

import * as crypto from "crypto";
import * as mysql from "mysql2/promise";
import { loadConfig } from "./config";
import { LingxingClient } from "./lingxingClient";

// ── 常量 ──────────────────────────────────────────────────────────────────────

const PRODUCT_COST_PATH = "/erp/sc/routing/data/local_inventory/batchGetProductInfo";
const BATCH_SIZE = 50;
const DELAY_BATCH_MS = 1000;
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
}

interface CostInfo {
  purchaseCost: number | null;
  logisticsCost: number | null;
}

interface UpsertResult {
  inserted: number;
  updated: number;
}

// ── 工具函数 ──────────────────────────────────────────────────────────────────

function chunkArray<T>(arr: T[], size: number): T[][] {
  const result: T[][] = [];
  for (let i = 0; i < arr.length; i += size) {
    result.push(arr.slice(i, i + size));
  }
  return result;
}

function sleep(ms: number) {
  return new Promise((r) => setTimeout(r, ms));
}

function parseNumber(value: unknown): number | null {
  const text = String(value ?? "").trim();
  if (!text) return null;
  const num = Number(text);
  return Number.isFinite(num) ? num : null;
}

function extractUsTransportCost(value: unknown): number | null {
  if (Array.isArray(value)) {
    for (const item of value) {
      if (item && typeof item === "object" && "US_cg_transport_costs" in item) {
        return parseNumber((item as Record<string, unknown>).US_cg_transport_costs);
      }
    }
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
  // ON DUPLICATE KEY UPDATE: 1=新增, 2=更新, 0=未变化
  if (affectedRows === 1) return { inserted: 1, updated: 0 };
  if (affectedRows === 2) return { inserted: 0, updated: 1 };
  return { inserted: 0, updated: 0 };
}

// ── RAW 层写入 ────────────────────────────────────────────────────────────────

async function saveRawPage(
  db: mysql.Connection,
  params: Record<string, unknown>,
  response: unknown,
): Promise<void> {
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
}

// ── 主逻辑 ────────────────────────────────────────────────────────────────────

async function run() {
  console.log("=".repeat(60));
  console.log("领星产品成本同步 → dim_product_cost_config");
  console.log(`模式: ${DRY_RUN ? "DRY-RUN（预览）" : "正式写入"}`);
  console.log(`生效日期: ${EFFECTIVE_DATE}`);
  console.log("=".repeat(60));

  const cfg = loadConfig();
  const db = await mysql.createConnection({
    host: process.env.DB_HOST ?? "127.0.0.1",
    port: Number(process.env.DB_PORT ?? 3306),
    user: process.env.DB_USER ?? "",
    password: process.env.DB_PASSWORD ?? "",
    database: process.env.DB_NAME ?? "walmart_ai_data",
  });

  try {
    // ── 第一步：从 dim_product_identity 读取 MSKU 列表 ──────────────────────
    console.log("\n[1/4] 读取 dim_product_identity 中的 MSKU 列表...");

    const [identityRows] = await db.query<mysql.RowDataPacket[]>(
      `SELECT platform, store_id, store_name, item_id, msku
       FROM dim_product_identity
       WHERE msku IS NOT NULL AND msku != ''
       ORDER BY msku`,
    );

    const identities = identityRows as IdentityRow[];
    console.log(`  共 ${identities.length} 条商品身份记录`);

    if (identities.length === 0) {
      console.log("  ⚠️  dim_product_identity 为空，请先运行飞书同步脚本");
      return;
    }

    // MSKU → identity 映射（取第一条，通常唯一）
    const identityMap = new Map<string, IdentityRow>();
    for (const row of identities) {
      if (!identityMap.has(row.msku)) {
        identityMap.set(row.msku, row);
      }
    }

    const mskus = Array.from(identityMap.keys());
    const batches = chunkArray(mskus, BATCH_SIZE);
    console.log(`  去重后 ${mskus.length} 个唯一 MSKU，分 ${batches.length} 批请求`);

    // ── 第二步：调领星 API ──────────────────────────────────────────────────
    console.log("\n[2/4] 调用 batchGetProductInfo 接口...");

    const client = new LingxingClient(cfg);
    const costMap = new Map<string, CostInfo>();
    let apiErrorCount = 0;

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

        // 写 RAW 层
        if (!DRY_RUN) {
          await saveRawPage(db, params, response);
        }

        const data = (response as { data?: unknown }).data;
        const items = Array.isArray(data) ? data : [];

        for (const item of items) {
          if (!item || typeof item !== "object") continue;
          const rec = item as Record<string, unknown>;
          const msku = String(rec.sku ?? "").trim();
          if (!msku) continue;

          costMap.set(msku, {
            purchaseCost: parseNumber(rec.cg_price),
            logisticsCost: extractUsTransportCost(rec.product_logistics_relation),
          });
        }

        console.log(`  ✓ ${label}: 返回 ${items.length} 条`);
      } catch (err) {
        console.error(`  ✗ ${label} 失败: ${String(err)}`);
        apiErrorCount++;
      }

      if (i < batches.length - 1) await sleep(DELAY_BATCH_MS);
    }

    const matched = costMap.size;
    const withPurchase = [...costMap.values()].filter((c) => c.purchaseCost !== null).length;
    const withLogistics = [...costMap.values()].filter((c) => c.logisticsCost !== null).length;

    console.log(`\n[3/4] API 结果汇总:`);
    console.log(`  有成本数据的 MSKU: ${matched}`);
    console.log(`  含采购成本(cg_price): ${withPurchase}`);
    console.log(`  含头程成本(US_cg_transport_costs): ${withLogistics}`);
    console.log(`  API 错误批次: ${apiErrorCount}`);

    if (matched === 0) {
      console.log("\n  ⚠️  API 未返回任何成本数据，请检查 MSKU 是否在领星本地库存中");
      return;
    }

    // ── 第三步：写入 dim_product_cost_config ───────────────────────────────
    console.log("\n[4/4] 写入 dim_product_cost_config...");

    let totalInserted = 0;
    let totalUpdated = 0;
    let totalSkipped = 0;

    for (const [msku, cost] of costMap.entries()) {
      // 没有任何成本数据则跳过
      if (cost.purchaseCost === null && cost.logisticsCost === null) {
        totalSkipped++;
        continue;
      }

      const identity = identityMap.get(msku);
      const platform = identity?.platform ?? "walmart";
      const store_id = identity?.store_id ?? "";
      const store_name = identity?.store_name ?? "";
      const item_id = identity?.item_id ?? "";

      if (DRY_RUN) {
        console.log(
          `  [DRY] ${msku} | 采购: ${cost.purchaseCost ?? "-"} | 头程: ${cost.logisticsCost ?? "-"} | item_id: ${item_id || "(未匹配)"}`,
        );
        totalInserted++; // dry-run 计数
        continue;
      }

      const [result] = await db.query<mysql.ResultSetHeader>(
        `INSERT INTO dim_product_cost_config
           (platform, store_id, store_name, item_id, msku,
            purchase_cost, logistics_cost,
            effective_date, source_system)
         VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'lingxing_api')
         ON DUPLICATE KEY UPDATE
           purchase_cost   = VALUES(purchase_cost),
           logistics_cost  = VALUES(logistics_cost),
           updated_at      = CURRENT_TIMESTAMP`,
        [
          platform, store_id, store_name, item_id, msku,
          cost.purchaseCost, cost.logisticsCost,
          EFFECTIVE_DATE,
        ],
      );

      const r = upsertCount(result.affectedRows);
      totalInserted += r.inserted;
      totalUpdated += r.updated;
    }

    // ── 结果 ────────────────────────────────────────────────────────────────
    console.log("\n" + "=".repeat(60));
    if (DRY_RUN) {
      console.log("DRY-RUN 预览完成（未写入）");
      console.log(`  待写入条数: ${totalInserted}`);
      console.log(`  无成本跳过: ${totalSkipped}`);
      console.log("\n加 --confirm-write 参数正式写入");
    } else {
      console.log("✅ 同步完成");
      console.log(`  新增: ${totalInserted}`);
      console.log(`  更新: ${totalUpdated}`);
      console.log(`  无成本跳过: ${totalSkipped}`);
      console.log(`  API 错误批次: ${apiErrorCount}`);
    }
    console.log("=".repeat(60));
  } finally {
    await db.end();
  }
}

run().catch((err) => {
  console.error("同步失败:", err);
  process.exit(1);
});
