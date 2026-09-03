/**
 * checkOrderDrop.ts - 订单异常下滑检测（16:25，拉数+判定+写事件）
 *
 * 链路：领星 saleStat(pageList, result_type=2 订单量, data_type=1 ItemID维度)
 *       + walmart/list（实时库存，断货剔除）
 *   → raw_lingxing_api（RAW-first）
 *   → fact_sales_orders_early（早鸟快照，绝不写 fact_sales_daily）
 *   → 判定（orderDropRule 分档）→ biz_event（event_type=order_drop，状态机）
 *
 * 口径（2026-07-16 定稿）：
 *   当日 = 中国今天-1（站点最新完整销售日假设，观察期用 --slot=2000 对照验证）
 *   基线 = 当日前3个完整日；低量档零单连击基线 = 断单前3日
 *   剔除：CS测品（全MSKU以CS开头）、归档、断货（实时总可售=0）、基线不足3天
 *   恢复：当日≥基线70% → biz_event 置 resolved
 *
 * 运行：
 *   npx ts-node src/checkOrderDrop.ts                     # dry-run 零写入
 *   npx ts-node src/checkOrderDrop.ts --confirm-write     # 写快照+事件
 *   npx ts-node src/checkOrderDrop.ts --confirm-write --slot=2000  # 观察期对照（只写快照不写事件）
 */

import "dotenv/config";
import * as crypto from "crypto";
import * as mysql from "mysql2/promise";
import { loadConfig } from "./config";
import { LingxingClient } from "./lingxingClient";
import { STORES } from "./syncDailyBaseData";
import { evaluateOrderDrop, isRecovered } from "./notifyRules/orderDropRule";
import { toSafeQty } from "./notifyRules/noOrderInventoryRule";

const SCRIPT_NAME = "checkOrderDrop";
const SALE_STAT_PATH = "/basicOpen/platformStatisticsV2/saleStat/pageList";
const WALMART_LIST_PATH = "/basicOpen/multiplatform/walmart/list";
const PLATFORM = "walmart";
const PAGE_LENGTH = 200;
const MAX_PAGES = 20;
const PAGE_DELAY_MS = 1100; // saleStat 令牌桶容量=1，必须限速
const TIMEOUT_MS = 120000;
const PULL_DAYS = 10; // 拉近10天，覆盖 当日+基线3日+零单连击回溯

const CONFIRM_WRITE = process.argv.includes("--confirm-write");
const SLOT = (process.argv.find((a) => a.startsWith("--slot="))?.slice(7) ?? "1625").trim();

function sleep(ms: number): Promise<void> { return new Promise((r) => setTimeout(r, ms)); }
function pad2(n: number): string { return String(n).padStart(2, "0"); }

function cstToday(): string {
  return new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Shanghai", year: "numeric", month: "2-digit", day: "2-digit" }).format(new Date());
}
function addDays(ymd: string, days: number): string {
  const [y, m, d] = ymd.split("-").map(Number);
  const dt = new Date(Date.UTC(y, m - 1, d));
  dt.setUTCDate(dt.getUTCDate() + days);
  return `${dt.getUTCFullYear()}-${pad2(dt.getUTCMonth() + 1)}-${pad2(dt.getUTCDate())}`;
}

function toArrayValues(value: unknown): string[] {
  if (Array.isArray(value)) return value.map((v) => String(v).trim()).filter(Boolean);
  const s = String(value ?? "").trim();
  if (!s) return [];
  try { const p = JSON.parse(s); if (Array.isArray(p)) return p.map((v) => String(v).trim()).filter(Boolean); } catch {}
  return [s];
}
function parseDateCollect(raw: unknown): Record<string, number> {
  if (!raw) return {};
  try {
    const obj = typeof raw === "string" ? JSON.parse(raw) : raw;
    if (obj && typeof obj === "object" && !Array.isArray(obj)) {
      const out: Record<string, number> = {};
      for (const [k, v] of Object.entries(obj as Record<string, unknown>)) out[k] = toSafeQty(v);
      return out;
    }
  } catch {}
  return {};
}
function extractListItems(data: unknown): unknown[] {
  if (Array.isArray(data)) return data;
  if (data && typeof data === "object") {
    const d = data as Record<string, unknown>;
    for (const key of ["list", "data", "rows", "records"]) if (Array.isArray(d[key])) return d[key] as unknown[];
  }
  return [];
}

async function insertRaw(db: mysql.Connection, apiPath: string, params: unknown, responseData: unknown, batchNo: string): Promise<number> {
  const requestJson = JSON.stringify(params);
  const responseJson = JSON.stringify(responseData);
  const rawHash = crypto.createHash("sha256").update(`${apiPath}|${requestJson}|${responseJson}`).digest("hex");
  const extraJson = JSON.stringify({ script: SCRIPT_NAME, batch_no: batchNo, slot: SLOT });
  await db.query(
    `INSERT IGNORE INTO raw_lingxing_api
       (source_system, api_path, request_method, request_params_json, response_json,
        response_code, is_success, error_message, data_date, raw_hash, extra_json)
     VALUES ('lingxing', ?, 'POST', CAST(? AS JSON), CAST(? AS JSON), '0', 1, NULL, CURDATE(), ?, CAST(? AS JSON))`,
    [apiPath, requestJson, responseJson, rawHash, extraJson],
  );
  const [rows] = await db.query<mysql.RowDataPacket[]>(
    `SELECT id FROM raw_lingxing_api WHERE api_path = ? AND data_date = CURDATE() AND raw_hash = ? ORDER BY id DESC LIMIT 1`,
    [apiPath, rawHash],
  );
  const rawId = Number(rows[0]?.id ?? 0);
  if (!rawId) throw new Error(`RAW insert/query failed for ${batchNo}`);
  return rawId;
}

interface ItemOrders {
  storeId: string;
  storeName: string;
  itemId: string;
  dc: Record<string, number>;
}

async function main(): Promise<void> {
  const today = cstToday();
  const dataDate = addDays(today, -1); // 当日 = 最新完整销售日（站点口径假设，观察期验证）
  const pullStart = addDays(today, -PULL_DAYS);
  const isControlSlot = SLOT !== "1625"; // 对照时点只写快照，不写事件

  console.log("=".repeat(60));
  console.log(`订单异常下滑检测 ${CONFIRM_WRITE ? "[confirm-write]" : "[dry-run 零写入]"} slot=${SLOT}${isControlSlot ? "（对照：只写快照）" : ""}`);
  console.log(`数据日期(当日)=${dataDate}，基线=${addDays(dataDate, -3)}~${addDays(dataDate, -1)}，拉取窗口=${pullStart}~${today}`);
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

  let alerts = 0;
  let recovered = 0;
  let skippedCs = 0;
  let skippedArchived = 0;
  let skippedNoStock = 0;
  let snapshotRows = 0;
  const sampleAlerts: string[] = [];

  try {
    // ── 1. 拉订单数据（saleStat，逐店铺分页）────────────────────
    const items: ItemOrders[] = [];
    for (const [si, store] of STORES.entries()) {
      if (si > 0) await sleep(PAGE_DELAY_MS);
      for (let page = 1; page <= MAX_PAGES; page++) {
        if (page > 1) await sleep(PAGE_DELAY_MS);
        const params = {
          start_date: pullStart, end_date: today,
          result_type: "2", date_unit: "4", data_type: "1",
          page, length: PAGE_LENGTH, sids: [store.storeId],
        };
        const resp = await client.request<unknown>({ method: "POST", path: SALE_STAT_PATH, params, timeoutMs: TIMEOUT_MS });
        if (CONFIRM_WRITE) await insertRaw(db, SALE_STAT_PATH, params, resp.data, `saleStat_${store.storeId}_p${page}`);
        const list = extractListItems(resp.data);
        for (const raw of list) {
          const r = raw as Record<string, unknown>;
          const ids = toArrayValues(r.platform_product_id);
          if (!ids.length) continue;
          const dc = parseDateCollect(r.date_collect);
          for (const id of ids) items.push({ storeId: store.storeId, storeName: store.storeName, itemId: id, dc });
        }
        if (list.length < PAGE_LENGTH) break;
      }
      console.log(`  店铺 ${store.storeName}: 累计 item 行 ${items.length}`);
    }

    // ── 2. 实时库存（断货剔除）────────────────────────────────
    const stockMap = new Map<string, number>(); // storeId|itemId → 总可售
    for (const [si, store] of STORES.entries()) {
      if (si > 0) await sleep(800);
      for (let page = 0; page < MAX_PAGES; page++) {
        const resp = await client.request<unknown>({
          method: "POST", path: WALMART_LIST_PATH,
          params: { store_ids: [store.storeId], status: [0], offset: page * PAGE_LENGTH, length: PAGE_LENGTH },
          timeoutMs: TIMEOUT_MS,
        });
        const list = extractListItems(resp.data);
        for (const raw of list) {
          const r = raw as Record<string, unknown>;
          const itemId = String(r.item_id ?? "").trim();
          if (!itemId) continue;
          stockMap.set(`${store.storeId}|${itemId}`, toSafeQty(r.wfs_available_quantity) + toSafeQty(r.available_quantity));
        }
        if (list.length < PAGE_LENGTH) break;
        await sleep(800);
      }
    }
    console.log(`  库存映射: ${stockMap.size} 个商品`);

    // ── 3. 维表：owner / CS / 归档 ────────────────────────────
    const [dimRows] = await db.query<mysql.RowDataPacket[]>(
      `SELECT store_id, item_id,
              MAX(NULLIF(owner,'')) AS owner,
              GROUP_CONCAT(DISTINCT msku) AS mskus,
              MAX(COALESCE(NULLIF(product_name,''), NULLIF(item_name,''), '')) AS pname,
              MIN(CASE WHEN COALESCE(product_management_status,'') = 'archived' THEN 1 ELSE 0 END) AS all_archived
       FROM dim_product WHERE platform = ? GROUP BY store_id, item_id`,
      [PLATFORM],
    );
    const dimMap = new Map<string, { owner: string; mskus: string[]; pname: string; archived: boolean }>();
    for (const r of dimRows) {
      dimMap.set(`${r.store_id}|${r.item_id}`, {
        owner: String(r.owner ?? ""),
        mskus: String(r.mskus ?? "").split(",").filter(Boolean),
        pname: String(r.pname ?? ""),
        archived: Number(r.all_archived) === 1,
      });
    }

    // ── 4. 快照写入 + 判定 ────────────────────────────────────
    // 昨日open事件（连续天数）
    const [prevEvents] = await db.query<mysql.RowDataPacket[]>(
      `SELECT source_key, extra_json FROM biz_event
       WHERE event_type = 'order_drop' AND status = 'open' AND event_date = ?`,
      [addDays(dataDate, -1)],
    );
    const prevStreak = new Map<string, number>();
    for (const r of prevEvents) {
      const ex = (typeof r.extra_json === "object" && r.extra_json) ? r.extra_json as Record<string, unknown> : {};
      prevStreak.set(String(r.source_key), toSafeQty(ex.consecutiveDays) || 1);
    }
    // 全部open事件（恢复关闭用）
    const [openEvents] = await db.query<mysql.RowDataPacket[]>(
      `SELECT event_id, source_key FROM biz_event WHERE event_type = 'order_drop' AND status = 'open'`,
    );

    const seen = new Set<string>();
    const alertedKeys = new Set<string>();

    for (const it of items) {
      const key = `${it.storeId}|${it.itemId}`;
      if (seen.has(key)) continue; // 同item多行（多msku聚合返回）去重
      seen.add(key);

      // 快照写入（近PULL_DAYS内 ≤dataDate 的每个日期）
      if (CONFIRM_WRITE) {
        for (let i = 0; i < PULL_DAYS; i++) {
          const d = addDays(dataDate, -i);
          const cnt = toSafeQty(it.dc[d]);
          await db.query(
            `INSERT INTO fact_sales_orders_early (stat_date, platform, store_id, item_id, order_count, pull_slot)
             VALUES (?,?,?,?,?,?)
             ON DUPLICATE KEY UPDATE order_count=VALUES(order_count), updated_at=NOW()`,
            [d, PLATFORM, it.storeId, it.itemId, cnt, SLOT],
          );
          snapshotRows += 1;
        }
      } else {
        snapshotRows += PULL_DAYS;
      }
      if (isControlSlot) continue; // 对照时点到此为止

      // 剔除项
      const dim = dimMap.get(key);
      if (dim?.archived) { skippedArchived += 1; continue; }
      if (dim && dim.mskus.length > 0 && dim.mskus.every((m) => m.toUpperCase().startsWith("CS"))) { skippedCs += 1; continue; }
      const stock = stockMap.get(key);
      if (stock !== undefined && stock <= 0) { skippedNoStock += 1; continue; }

      // 判定数据组装
      const day = (offset: number) => toSafeQty(it.dc[addDays(dataDate, -offset)]);
      const current = day(0);
      let zeroStreak = 0;
      for (let i = 0; i <= PULL_DAYS - 4; i++) { if (day(i) === 0) zeroStreak += 1; else break; }
      // 基线：零单连击≥3时取断单前3日，否则取当日前3日
      const baseStart = zeroStreak >= 3 ? zeroStreak : 1;
      const baseline = [day(baseStart + 2), day(baseStart + 1), day(baseStart)];

      const decision = evaluateOrderDrop({ baseline, current, zeroStreak });
      const sourceKey = `${it.storeId}:${it.itemId}`;

      if (decision.alert) {
        alertedKeys.add(sourceKey);
        const consecutiveDays = (prevStreak.get(sourceKey) ?? 0) + 1;
        const payload = {
          storeName: it.storeName, itemId: it.itemId,
          msku: dim?.mskus.join("/") ?? "", productName: dim?.pname ?? "",
          owner: dim?.owner ?? "", baseline, current,
          avg: decision.avg, dropPct: decision.dropPct, band: decision.band,
          reason: decision.reason, consecutiveDays, dataDate,
        };
        if (CONFIRM_WRITE) {
          await db.query(
            `INSERT IGNORE INTO biz_event
               (event_date, event_type, platform, store_id, store_name, item_id, msku, owner,
                title, reason, status, source_table, source_key, detected_by, extra_json)
             VALUES (?, 'order_drop', ?, ?, ?, ?, ?, ?, ?, ?, 'open', 'fact_sales_orders_early', ?, 'rule', CAST(? AS JSON))`,
            [dataDate, PLATFORM, it.storeId, it.storeName, it.itemId,
             dim?.mskus.join("/") ?? "", dim?.owner ?? "",
             decision.reason === "zero_streak" ? `订单异常：连续${zeroStreak}天0单` : `订单异常：日均${decision.avg}降至${current}`,
             `基线${baseline.join("/")} 当日${current} 降幅${decision.dropPct !== null ? (decision.dropPct * 100).toFixed(1) : "-"}%`,
             sourceKey, JSON.stringify(payload)],
          );
        }
        alerts += 1;
        if (sampleAlerts.length < 5) {
          sampleAlerts.push(`  ${it.storeName} ${it.itemId} 基线${baseline.join("/")} 当日${current} band=${decision.band} 连续${consecutiveDays}天`);
        }
      }
    }

    // ── 5. 恢复关闭 ───────────────────────────────────────────
    if (!isControlSlot) {
      for (const ev of openEvents) {
        const sk = String(ev.source_key);
        if (alertedKeys.has(sk)) continue; // 今天仍异常，保持open
        const [storeId, itemId] = sk.split(":");
        const it = items.find((x) => x.storeId === storeId && x.itemId === itemId);
        if (!it) continue; // 无数据不动
        const day = (offset: number) => toSafeQty(it.dc[addDays(dataDate, -offset)]);
        if (isRecovered([day(3), day(2), day(1)], day(0))) {
          if (CONFIRM_WRITE) {
            await db.query(
              `UPDATE biz_event SET status='resolved', resolved_at=NOW() WHERE event_id = ?`,
              [ev.event_id],
            );
          }
          recovered += 1;
        }
      }
    }

    console.log("\n" + "=".repeat(60));
    console.log(`商品数(去重): ${seen.size}，快照行: ${snapshotRows}${CONFIRM_WRITE ? "" : "（dry-run 未写）"}`);
    console.log(`异常触发: ${alerts}${isControlSlot ? "（对照时点不写事件）" : CONFIRM_WRITE ? "" : "（dry-run 未写）"}，恢复关闭: ${recovered}`);
    console.log(`剔除：CS ${skippedCs} / 归档 ${skippedArchived} / 断货 ${skippedNoStock}`);
    if (sampleAlerts.length) { console.log("异常样例:"); sampleAlerts.forEach((s) => console.log(s)); }
  } finally {
    await db.end().catch(() => {});
  }
}

main().catch((e) => {
  console.error(`${SCRIPT_NAME} 失败:`, e instanceof Error ? e.message : String(e));
  process.exit(1);
});
