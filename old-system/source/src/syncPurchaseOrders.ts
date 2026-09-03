/**
 * syncPurchaseOrders.ts - 领星采购单每日同步（批④ AI智能PMC，2026-07-21）
 *
 * 链路：purchaseOrderList → raw_lingxing_api（RAW-first，RAW失败不写下游）→
 *       fact_purchase_order / fact_purchase_order_item（UPSERT 覆盖状态与数量）
 * 口径：全量分页拉取（接口无增量参数实证前保守全量；单量小），关联键=SKU
 * 运行：npx ts-node src/syncPurchaseOrders.ts                # dry-run 零写入
 *       npx ts-node src/syncPurchaseOrders.ts --confirm-write
 * cron：40 7 * * *（复活卡采购触发 08:50 依赖本任务先行）
 */

import "dotenv/config";
import * as crypto from "crypto";
import * as mysql from "mysql2/promise";
import { loadConfig } from "./config";
import { LingxingClient } from "./lingxingClient";

const SCRIPT_NAME = "syncPurchaseOrders";
const API_PATH = "/erp/sc/routing/data/local_inventory/purchaseOrderList";
const PAGE_SIZE = 200;
const CONFIRM_WRITE = process.argv.includes("--confirm-write");

interface PoItem {
  sku?: unknown; msku?: unknown; product_name?: unknown;
  quantity_real?: unknown; quantity_entry?: unknown; quantity_receive?: unknown;
  expect_arrive_time?: unknown;
}
interface PoHead {
  order_sn?: unknown; status?: unknown; status_text?: unknown;
  status_shipped?: unknown; status_shipped_text?: unknown;
  ware_house_name?: unknown; order_time?: unknown; create_time?: unknown;
  auditor_time?: unknown; update_time?: unknown; item_list?: PoItem[];
}

function s(v: unknown): string { return String(v ?? "").trim(); }
function n(v: unknown): number { const x = Number(v); return Number.isFinite(x) ? Math.round(x) : 0; }

async function insertRaw(db: mysql.Connection, requestParams: unknown, responseData: unknown, batchNo: number): Promise<number> {
  const requestJson = JSON.stringify(requestParams);
  const responseJson = JSON.stringify(responseData);
  const rawHash = crypto.createHash("sha256").update(`${API_PATH}|${requestJson}|${responseJson}`).digest("hex");
  const extraJson = JSON.stringify({ script: SCRIPT_NAME, batch_no: batchNo });
  await db.query(
    `INSERT IGNORE INTO raw_lingxing_api
       (source_system, api_path, request_method, request_params_json, response_json,
        response_code, is_success, error_message, data_date, raw_hash, extra_json)
     VALUES ('lingxing', ?, 'POST', CAST(? AS JSON), CAST(? AS JSON), '0', 1, NULL, CURDATE(), ?, CAST(? AS JSON))`,
    [API_PATH, requestJson, responseJson, rawHash, extraJson],
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
  console.log("=".repeat(60));
  console.log(`采购单同步 ${CONFIRM_WRITE ? "[confirm-write]" : "[dry-run 零写入]"}`);
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
    script: SCRIPT_NAME, confirmWrite: CONFIRM_WRITE,
    pages: 0, orders: 0, itemRows: 0, headUpserts: 0, itemUpserts: 0,
    skuEmpty: 0, status: "success", error: "",
  };
  try {
    let offset = 0;
    for (let page = 1; page <= 50; page++) {
      const params = { offset, length: PAGE_SIZE };
      const resp = await client.post<unknown>(API_PATH, params);
      // 2026-07-21 实证：purchaseOrderList 列表在 $.data.data（RAW#38710/38711 验证，total=586）
      const outer = resp as { data?: { data?: PoHead[]; list?: PoHead[] }; list?: PoHead[] };
      const list: PoHead[] = (outer.data?.data ?? outer.data?.list ?? outer.list ?? []) as PoHead[];
      summary.pages += 1;
      console.log(`  第${page}页: ${list.length} 单`);
      let rawId = 0;
      if (CONFIRM_WRITE) rawId = await insertRaw(db, { api: API_PATH, ...params }, resp, page);
      for (const h of list) {
        summary.orders += 1;
        const orderSn = s(h.order_sn);
        if (!orderSn) continue;
        if (CONFIRM_WRITE) {
          await db.query(
            `INSERT INTO fact_purchase_order
               (order_sn, status, status_text, status_shipped, status_shipped_text,
                ware_house_name, order_time, create_time, auditor_time, update_time, source_raw_id)
             VALUES (?,?,?,?,?,?,?,?,?,?,?)
             ON DUPLICATE KEY UPDATE
               status=VALUES(status), status_text=VALUES(status_text),
               status_shipped=VALUES(status_shipped), status_shipped_text=VALUES(status_shipped_text),
               ware_house_name=VALUES(ware_house_name), order_time=VALUES(order_time),
               auditor_time=VALUES(auditor_time), update_time=VALUES(update_time),
               source_raw_id=VALUES(source_raw_id), updated_at=NOW()`,
            [orderSn, s(h.status), s(h.status_text), s(h.status_shipped), s(h.status_shipped_text),
             s(h.ware_house_name), s(h.order_time), s(h.create_time), s(h.auditor_time), s(h.update_time), rawId],
          );
          summary.headUpserts += 1;
        }
        for (const it of h.item_list ?? []) {
          summary.itemRows += 1;
          const sku = s(it.sku);
          if (!sku) { summary.skuEmpty += 1; continue; }
          if (CONFIRM_WRITE) {
            await db.query(
              `INSERT INTO fact_purchase_order_item
                 (order_sn, sku, msku, product_name, quantity_real, quantity_entry,
                  quantity_receive, expect_arrive_time, source_raw_id)
               VALUES (?,?,?,?,?,?,?,?,?)
               ON DUPLICATE KEY UPDATE
                 product_name=VALUES(product_name), quantity_real=VALUES(quantity_real),
                 quantity_entry=VALUES(quantity_entry), quantity_receive=VALUES(quantity_receive),
                 expect_arrive_time=VALUES(expect_arrive_time), source_raw_id=VALUES(source_raw_id),
                 updated_at=NOW()`,
              [orderSn, sku, s(it.msku), s(it.product_name).slice(0, 255),
               n(it.quantity_real), n(it.quantity_entry), n(it.quantity_receive),
               s(it.expect_arrive_time), rawId],
            );
            summary.itemUpserts += 1;
          }
        }
      }
      if (list.length < PAGE_SIZE) break;
      offset += PAGE_SIZE;
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
