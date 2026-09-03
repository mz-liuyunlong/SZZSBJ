/**
 * syncWfsShipments.ts - WFS货件同步（R1：到仓/接收完成事件生成）
 *
 * 链路：领星 queryWFSCargoPage → raw_lingxing_api（RAW-first）→
 *       fact_wfs_shipment / fact_wfs_shipment_item（UPSERT）→
 *       event_arrival_notify（状态跃迁事件，INSERT IGNORE 幂等）
 *
 * 格式口径（2026-07-14 probe 实测）：to_*_time = epoch毫秒字符串/"0"；数量=字符串数字。
 * 规范：默认 dry-run 零写入；--confirm-write 才写库；RAW 写入失败的批次不得写 FACT/EVENT；
 *       DATETIME 解析失败置 NULL 并计数告警（2026-07-11 dateStrings 规约）；
 *       本脚本不发送任何飞书消息（发送职责在 arrivalNotify.ts）。
 *
 * 运行：
 *   npx ts-node src/syncWfsShipments.ts                    # dry-run
 *   npx ts-node src/syncWfsShipments.ts --confirm-write    # 写库
 *   npx ts-node src/syncWfsShipments.ts --confirm-write --days=90   # 首跑全量窗
 */

import "dotenv/config";
import * as crypto from "crypto";
import * as mysql from "mysql2/promise";
import { loadConfig } from "./config";
import { LingxingClient } from "./lingxingClient";
import {
  parseEpochToCstDateTime,
  parseApiDateTime,
  detectShipmentTransitions,
  ShipmentEventPayload,
} from "./notifyRules/wfsArrivalRule";
import { toSafeQty } from "./notifyRules/noOrderInventoryRule";

const SCRIPT_NAME = "syncWfsShipments";
const API_PATH = "/cepf/warehouse/api/openApi/queryWFSCargoPage";
const PLATFORM = "walmart";
const PAGE_LENGTH = 200;
const MAX_PAGES = 50;
const PAGE_DELAY_MS = 1100;
const TIMEOUT_MS = 120000;

const CONFIRM_WRITE = process.argv.includes("--confirm-write");

function getArg(name: string, defaultValue = ""): string {
  const prefix = `--${name}=`;
  const hit = process.argv.find((a) => a.startsWith(prefix));
  return hit ? hit.slice(prefix.length) : defaultValue;
}

function sleep(ms: number): Promise<void> {
  return new Promise((r) => setTimeout(r, ms));
}

function todayCst(): string {
  return new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Shanghai", year: "numeric", month: "2-digit", day: "2-digit" }).format(new Date());
}

function fmtDate(d: Date): string {
  return d.toISOString().slice(0, 10);
}

interface ShipmentRow {
  shipmentId: string;
  storeId: string;
  storeName: string;
  cargoCode: string;
  inboundOrderId: string;
  status: number;
  statusName: string;
  cargoStatus: string;
  cargoSyncStatus: string;
  logisticsCode: string;
  cargoCreateDate: string | null;
  toPendingTime: string | null;
  toAwaitTime: string | null;
  toReceiveTime: string | null;
  toClosedTime: string | null;
  toCancelledTime: string | null;
  cargoUpdateDate: string | null;
  systemUpdateDate: string | null;
  goods: Array<{ msku: string; sku: string; gtin: string; productName: string; declareNum: number; shipmentsNum: number; receivedNum: number; damagedQty: number }>;
}

let dateParseFailures = 0;

function parseTime(v: unknown): string | null {
  const s = String(v ?? "").trim();
  if (!s || s === "0") return null;
  const parsed = parseEpochToCstDateTime(v);
  if (parsed === null) dateParseFailures += 1;
  return parsed;
}

function parseRecord(raw: Record<string, unknown>): ShipmentRow | null {
  const shipmentId = String(raw.id ?? "").trim();
  const storeId = String(raw.store_id ?? "").trim();
  if (!shipmentId || !storeId) return null;
  const status = Number(raw.status);
  if (!Number.isInteger(status) || status < 0 || status > 4) return null;

  const goodsRaw = Array.isArray(raw.cargo_good_list) ? raw.cargo_good_list : [];
  const goods = goodsRaw.map((g) => {
    const gr = g as Record<string, unknown>;
    return {
      msku: String(gr.msku ?? "").trim(),
      sku: String(gr.sku ?? "").trim(),
      gtin: String(gr.gtin ?? "").trim(),
      productName: String(gr.product_name ?? "").trim(),
      declareNum: toSafeQty(gr.declare_num),
      shipmentsNum: toSafeQty(gr.shipments_num),
      receivedNum: toSafeQty(gr.received_num),
      damagedQty: toSafeQty(gr.dameged_qty), // API 拼写即 dameged_qty
    };
  }).filter((g) => g.msku);

  return {
    shipmentId,
    storeId,
    storeName: String(raw.store_name ?? "").trim(),
    cargoCode: String(raw.cargo_code ?? "").trim(),
    inboundOrderId: String(raw.in_bound_order_id ?? "").trim(),
    status,
    statusName: String(raw.status_name ?? "").trim(),
    cargoStatus: String(raw.cargo_status ?? "").trim(),
    cargoSyncStatus: String(raw.cargo_sync_status ?? "").trim(),
    logisticsCode: String(raw.logistics_code ?? "").trim(),
    cargoCreateDate: parseApiDateTime(raw.cargo_create_date),
    toPendingTime: parseTime(raw.to_pending_time),
    toAwaitTime: parseTime(raw.to_await_time),
    toReceiveTime: parseTime(raw.to_receive_time),
    toClosedTime: parseTime(raw.to_closed_time),
    toCancelledTime: parseTime(raw.to_cancelled_time),
    cargoUpdateDate: parseApiDateTime(raw.update_date),
    systemUpdateDate: parseApiDateTime(raw.system_update_date),
    goods,
  };
}

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

/** 负责人映射：store_id+msku 唯一命中才取，多命中/无命中返回 ""（禁止猜测） */
async function loadOwnerMap(db: mysql.Connection, pairs: Array<{ storeId: string; msku: string }>): Promise<Map<string, string>> {
  const map = new Map<string, string>();
  if (!pairs.length) return map;
  const uniq = [...new Map(pairs.map((p) => [`${p.storeId}|${p.msku}`, p])).values()];
  for (const p of uniq) {
    const [rows] = await db.query<mysql.RowDataPacket[]>(
      `SELECT DISTINCT COALESCE(owner,'') AS owner FROM dim_product
       WHERE platform = ? AND store_id = ? AND msku = ?`,
      [PLATFORM, p.storeId, p.msku],
    );
    const owners = rows.map((r) => String(r.owner)).filter(Boolean);
    map.set(`${p.storeId}|${p.msku}`, owners.length === 1 ? owners[0] : "");
  }
  return map;
}

async function main(): Promise<void> {
  const days = Number(getArg("days", "7")) || 7;
  const endDate = new Date();
  const startDate = new Date(endDate.getTime() - days * 24 * 3600 * 1000);

  console.log("=".repeat(60));
  console.log(`WFS货件同步 ${CONFIRM_WRITE ? "[confirm-write]" : "[dry-run 零写入]"}`);
  console.log(`创建时间窗: ${fmtDate(startDate)} ~ ${fmtDate(endDate)}（${days}天）`);
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

  let fetched = 0;
  let headUpserts = 0;
  let itemUpserts = 0;
  let eventReceiving = 0;
  let eventClosed = 0;
  let skippedInvalid = 0;

  try {
    for (let page = 0; page < MAX_PAGES; page++) {
      if (page > 0) await sleep(PAGE_DELAY_MS);
      const params = {
        start_time: fmtDate(startDate),
        end_time: fmtDate(endDate),
        offset: page * PAGE_LENGTH,
        length: PAGE_LENGTH,
      };
      const resp = await client.request<{ total?: unknown; records?: unknown[] }>({
        method: "POST", path: API_PATH, params, timeoutMs: TIMEOUT_MS,
      });
      const records = Array.isArray(resp.data?.records) ? resp.data!.records! : [];
      fetched += records.length;
      console.log(`第 ${page + 1} 页: ${records.length} 条`);

      let rawId = 0;
      if (CONFIRM_WRITE) {
        rawId = await insertRaw(db, params, resp.data, page + 1); // RAW-first：失败则本批不写下游
      }

      const rows = records
        .map((r) => parseRecord(r as Record<string, unknown>))
        .filter((r): r is ShipmentRow => {
          if (!r) skippedInvalid += 1;
          return r !== null;
        });

      // 旧状态批量读取
      const prevStatusMap = new Map<string, number>();
      if (rows.length) {
        const keys = rows.map((r) => r.shipmentId);
        const [prevRows] = await db.query<mysql.RowDataPacket[]>(
          `SELECT store_id, shipment_id, status FROM fact_wfs_shipment
           WHERE platform = ? AND shipment_id IN (${keys.map(() => "?").join(",")})`,
          [PLATFORM, ...keys],
        );
        for (const pr of prevRows) prevStatusMap.set(`${pr.store_id}|${pr.shipment_id}`, Number(pr.status));
      }

      const ownerMap = await loadOwnerMap(
        db,
        rows.flatMap((r) => r.goods.map((g) => ({ storeId: r.storeId, msku: g.msku }))),
      );

      for (const row of rows) {
        const prev = prevStatusMap.get(`${row.storeId}|${row.shipmentId}`) ?? null;
        const transitions = detectShipmentTransitions(prev, row.status);

        if (CONFIRM_WRITE) {
          await db.query(
            `INSERT INTO fact_wfs_shipment
               (platform, store_id, store_name, shipment_id, cargo_code, inbound_order_id,
                status, status_name, cargo_status, cargo_sync_status, logistics_code,
                cargo_create_date, to_pending_time, to_await_time, to_receive_time,
                to_closed_time, to_cancelled_time, cargo_update_date, system_update_date, source_raw_id)
             VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
             ON DUPLICATE KEY UPDATE
               store_name=VALUES(store_name), cargo_code=VALUES(cargo_code),
               inbound_order_id=VALUES(inbound_order_id), status=VALUES(status),
               status_name=VALUES(status_name), cargo_status=VALUES(cargo_status),
               cargo_sync_status=VALUES(cargo_sync_status), logistics_code=VALUES(logistics_code),
               cargo_create_date=VALUES(cargo_create_date), to_pending_time=VALUES(to_pending_time),
               to_await_time=VALUES(to_await_time), to_receive_time=VALUES(to_receive_time),
               to_closed_time=VALUES(to_closed_time), to_cancelled_time=VALUES(to_cancelled_time),
               cargo_update_date=VALUES(cargo_update_date), system_update_date=VALUES(system_update_date),
               source_raw_id=VALUES(source_raw_id), updated_at=NOW()`,
            [PLATFORM, row.storeId, row.storeName, row.shipmentId, row.cargoCode, row.inboundOrderId,
             row.status, row.statusName, row.cargoStatus, row.cargoSyncStatus, row.logisticsCode,
             row.cargoCreateDate, row.toPendingTime, row.toAwaitTime, row.toReceiveTime,
             row.toClosedTime, row.toCancelledTime, row.cargoUpdateDate, row.systemUpdateDate, rawId],
          );
          for (const g of row.goods) {
            await db.query(
              `INSERT INTO fact_wfs_shipment_item
                 (platform, store_id, shipment_id, msku, sku, gtin, product_name,
                  declare_num, shipments_num, received_num, damaged_qty, source_raw_id)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
               ON DUPLICATE KEY UPDATE
                 sku=VALUES(sku), gtin=VALUES(gtin), product_name=VALUES(product_name),
                 declare_num=VALUES(declare_num), shipments_num=VALUES(shipments_num),
                 received_num=VALUES(received_num), damaged_qty=VALUES(damaged_qty),
                 source_raw_id=VALUES(source_raw_id), updated_at=NOW()`,
              [PLATFORM, row.storeId, row.shipmentId, g.msku, g.sku, g.gtin, g.productName,
               g.declareNum, g.shipmentsNum, g.receivedNum, g.damagedQty, rawId],
            );
            itemUpserts += 1;
          }
        }
        headUpserts += 1;

        for (const tr of transitions) {
          const eventType = tr === "receiving" ? "wfs_shipment_receiving" : "wfs_shipment_closed";
          const transitionTime = tr === "receiving" ? row.toReceiveTime : row.toClosedTime;
          // 事件业务日期 = 货件实际跃迁日（修复：不再用运行日，保证回填的历史事件可按日期识别/跳过）
          const eventDate = transitionTime ? transitionTime.slice(0, 10) : todayCst();
          const payload: ShipmentEventPayload = {
            storeName: row.storeName,
            cargoCode: row.cargoCode,
            inboundOrderId: row.inboundOrderId,
            eventTime: transitionTime,
            goods: row.goods.map((g) => ({
              msku: g.msku, productName: g.productName, declareNum: g.declareNum,
              receivedNum: g.receivedNum, damagedQty: g.damagedQty,
              owner: ownerMap.get(`${row.storeId}|${g.msku}`) ?? "",
            })),
          };
          const owners = [...new Set(payload.goods.map((g) => g.owner).filter(Boolean))];
          if (CONFIRM_WRITE) {
            await db.query(
              `INSERT IGNORE INTO event_arrival_notify
                 (event_type, biz_key, event_date, platform, store_id, shipment_id, owner, payload_json)
               VALUES (?,?,?,?,?,?,?,CAST(? AS JSON))`,
              [eventType, row.shipmentId, eventDate, PLATFORM, row.storeId, row.shipmentId,
               owners.length === 1 ? owners[0] : "", JSON.stringify(payload)],
            );
          }
          if (tr === "receiving") eventReceiving += 1; else eventClosed += 1;
        }
      }

      if (records.length < PAGE_LENGTH) break;
    }

    console.log("\n" + "=".repeat(60));
    console.log(`货件拉取: ${fetched}（无效跳过 ${skippedInvalid}）`);
    console.log(`货件头 upsert: ${headUpserts}，明细 upsert: ${itemUpserts}${CONFIRM_WRITE ? "" : "（dry-run 未写）"}`);
    console.log(`事件生成: 开始接收 ${eventReceiving}，接收完成 ${eventClosed}${CONFIRM_WRITE ? "" : "（dry-run 未写）"}`);
    console.log(`日期解析失败计数: ${dateParseFailures}${dateParseFailures > 0 ? " ⚠️ 请检查API格式变化" : ""}`);
  } finally {
    await db.end().catch(() => {});
  }
}

main().catch((e) => {
  console.error(`${SCRIPT_NAME} 失败:`, e instanceof Error ? e.message : String(e));
  process.exit(1);
});
