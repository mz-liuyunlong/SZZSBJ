/**
 * syncLocalInventory.ts - 本地仓库存每日快照（批④v3，2026-07-21）
 * 链路：inventoryDetails → raw_lingxing_api（RAW-first）→ fact_local_inventory_daily
 * 口径：实时库存打"拉取当日"标签（沿用 fact_inventory_daily 口径修复教训）；按 SKU 聚合
 * 字段：可用库存候选侦测（沿用 Phase 7a fetchLocalInventory 的候选序）
 * 运行：--confirm-write 生产写入，默认 dry-run
 * cron：45 7 * * *（PMC 采购中口径依赖）
 */

import "dotenv/config";
import * as crypto from "crypto";
import * as mysql from "mysql2/promise";
import { loadConfig } from "./config";
import { LingxingClient } from "./lingxingClient";

const SCRIPT_NAME = "syncLocalInventory";
const API_PATH = "/erp/sc/routing/data/local_inventory/inventoryDetails";
// 2026-08-03 核对领星：inventoryDetails 会返回已删除/幽灵仓(如 wid 26724/28030/27159)的历史残留，
// 本地仓库只应统计"仓库列表"里的有效仓(is_delete=0)。动态取，接口失败时兜底=惠州16168/深圳27645。
const WAREHOUSE_API = "/erp/sc/data/local_inventory/warehouse";
const FALLBACK_WIDS = [16168, 27645];
const PAGE_SIZE = 200;
const CONFIRM_WRITE = process.argv.includes("--confirm-write");
const STOCK_FIELDS = [
  "product_valid_num", "valid_num", "validNum",
  "available_num", "available", "good_num", "quantity", "stock_num", "total_num",
];

function s(v: unknown): string { return String(v ?? "").trim(); }

function pickList(data: unknown): Record<string, unknown>[] {
  const d = data as { list?: unknown; data?: unknown; records?: unknown };
  if (Array.isArray(data)) return data as Record<string, unknown>[];
  if (Array.isArray(d?.list)) return d.list as Record<string, unknown>[];
  if (Array.isArray(d?.data)) return d.data as Record<string, unknown>[];
  if (Array.isArray(d?.records)) return d.records as Record<string, unknown>[];
  return [];
}

function pickQty(row: Record<string, unknown>): number {
  for (const f of STOCK_FIELDS) {
    if (row[f] !== undefined && row[f] !== null && row[f] !== "") {
      const n = Number(row[f]);
      if (Number.isFinite(n)) return Math.round(n);
    }
  }
  return 0;
}

function cstToday(): string {
  return new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Shanghai" }).format(new Date());
}

async function insertRaw(db: mysql.Connection, requestParams: unknown, responseData: unknown, batchNo: number): Promise<number> {
  const requestJson = JSON.stringify(requestParams);
  const responseJson = JSON.stringify(responseData);
  const rawHash = crypto.createHash("sha256").update(`${API_PATH}|${requestJson}|${responseJson}`).digest("hex");
  await db.query(
    `INSERT IGNORE INTO raw_lingxing_api
       (source_system, api_path, request_method, request_params_json, response_json,
        response_code, is_success, error_message, data_date, raw_hash, extra_json)
     VALUES ('lingxing', ?, 'POST', CAST(? AS JSON), CAST(? AS JSON), '0', 1, NULL, CURDATE(), ?, CAST(? AS JSON))`,
    [API_PATH, requestJson, responseJson, rawHash, JSON.stringify({ script: SCRIPT_NAME, batch_no: batchNo })],
  );
  const [rows] = await db.query<mysql.RowDataPacket[]>(
    `SELECT id FROM raw_lingxing_api WHERE api_path = ? AND data_date = CURDATE() AND raw_hash = ? ORDER BY id DESC LIMIT 1`,
    [API_PATH, rawHash],
  );
  const rawId = Number(rows[0]?.id ?? 0);
  if (!rawId) throw new Error(`RAW insert/query failed for batch ${batchNo}`);
  return rawId;
}

async function main(): Promise<void> {
  const today = cstToday();
  console.log("=".repeat(60));
  console.log(`本地仓库存快照 ${CONFIRM_WRITE ? "[confirm-write]" : "[dry-run 零写入]"} snapshot_date=${today}`);
  console.log("=".repeat(60));
  const client = new LingxingClient(loadConfig());
  const db = await mysql.createConnection({
    host: process.env.DB_HOST ?? "127.0.0.1",
    port: Number(process.env.DB_PORT ?? 3306),
    user: process.env.DB_USER ?? "",
    password: process.env.DB_PASSWORD ?? "",
    database: process.env.DB_NAME ?? "walmart_ai_data",
    dateStrings: true,
  });
  const summary = {
    script: SCRIPT_NAME, confirmWrite: CONFIRM_WRITE, snapshotDate: today,
    pages: 0, rows: 0, skuAgg: 0, upserts: 0, status: "success", error: "",
  };
  try {
    // 有效本地仓 wid（只统计仓库列表里 is_delete=0 的仓，剔除幽灵仓）
    const validWids = new Set<number>();
    try {
      const whResp = await client.post<unknown>(WAREHOUSE_API, {});
      const whList = pickList((whResp as { data?: unknown }).data ?? whResp);
      for (const w of whList) {
        const wid = Number(w.wid);
        if (Number.isFinite(wid) && Number(w.is_delete ?? 0) === 0) validWids.add(wid);
      }
    } catch (e) { console.log(`  仓库列表获取失败,用兜底 wid: ${e instanceof Error ? e.message : String(e)}`); }
    if (validWids.size === 0) for (const w of FALLBACK_WIDS) validWids.add(w);
    console.log(`  有效本地仓 wid: [${[...validWids].join(",")}]`);
    const skuQty = new Map<string, number>();
    let offset = 0;
    let lastRawId = 0;
    for (let page = 1; page <= 200; page++) {
      const params = { offset, length: PAGE_SIZE };
      const resp = await client.post<unknown>(API_PATH, params);
      const outer = resp as { data?: unknown };
      const list = pickList(outer.data ?? resp);
      summary.pages += 1;
      if (page === 1 && list.length) {
        console.log(`  首行字段快照: ${Object.keys(list[0]).slice(0, 20).join(",")}`);
      }
      if (CONFIRM_WRITE) lastRawId = await insertRaw(db, { api: API_PATH, ...params }, resp, page);
      for (const row of list) {
        summary.rows += 1;
        if (!validWids.has(Number(row.wid))) continue; // 只算有效本地仓(惠州/深圳)，剔除已删除/幽灵仓
        const sku = s(row.sku ?? row.SKU ?? row.local_sku);
        if (!sku) continue;
        skuQty.set(sku, (skuQty.get(sku) ?? 0) + pickQty(row));
      }
      if (list.length < PAGE_SIZE) break;
      offset += PAGE_SIZE;
    }
    summary.skuAgg = skuQty.size;
    console.log(`  SKU 聚合数: ${skuQty.size}`);
    if (CONFIRM_WRITE) {
      for (const [sku, qty] of skuQty) {
        await db.query(
          `INSERT INTO fact_local_inventory_daily (snapshot_date, sku, qty, source_raw_id)
           VALUES (?, ?, ?, ?)
           ON DUPLICATE KEY UPDATE qty = VALUES(qty), source_raw_id = VALUES(source_raw_id), updated_at = NOW()`,
          [today, sku, qty, lastRawId],
        );
        summary.upserts += 1;
      }
    }
  } catch (e) {
    summary.status = "failed";
    summary.error = e instanceof Error ? e.message : String(e);
    process.exitCode = 1;
  } finally {
    console.log("SUMMARY_JSON=" + JSON.stringify(summary));
    await db.end().catch(() => {});
  }
}

main().catch((e) => {
  console.error(`${SCRIPT_NAME} 失败:`, e instanceof Error ? e.message : String(e));
  process.exit(1);
});
