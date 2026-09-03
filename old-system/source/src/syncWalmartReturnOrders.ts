/**
 * syncWalmartReturnOrders.ts — Walmart售后订单同步（订单利润V2·退货数据链，2026-08-14 批1）
 *
 * 数据流：领星 /basicOpen/openapi/multiplatform/walmart/returnOrder/list（dateType=1 售后时间）
 *   → raw_walmart_return_order（uq return_order_id+msku 幂等upsert，原样留存）
 *   → fact_refund_daily（店铺×MSKU×日聚合重算，窗口内upsert；item_id经dim_product映射）
 *
 * 口径（需求方2026-08-14定稿）：按售后申请日(returnOrderDate)记当日——接口返回美西站点时间(2026-08-18实证)，
 *   DATE()即美西日界，符合全局时间规则；退款额=lineTotalAmount(含税净额)；
 *   store_id 经 storeIdNorm 修复领星数字精度损坏(2026-08-18实证:5店铺572行末4位损坏)；row_json原文不动。
 *   仅 returnType=REFUND 计入FACT（REPLACEMENT/PREORDER 留RAW不进利润）；INITIATED/COMPLETED 均计。
 *
 * cron（批4挂载）：每日 07:50 --confirm-write（默认窗口=近7天，覆盖状态滞后更新）
 * 用法：
 *   npx ts-node src/syncWalmartReturnOrders.ts                          # dry-run 近7天，零写入
 *   npx ts-node src/syncWalmartReturnOrders.ts --confirm-write          # 真写 近7天
 *   npx ts-node src/syncWalmartReturnOrders.ts --start=2026-06-16 --end=2026-08-14 --confirm-write  # 历史回补
 * 限速：令牌桶=1，页间隔1500ms，pageSize=100。
 */
import "dotenv/config";
import * as mysql from "mysql2/promise";
import { loadConfig } from "./config";
import { LingxingClient } from "./lingxingClient";
import { buildStoreNormalizer } from "./storeIdNorm";

const API_PATH = "/basicOpen/openapi/multiplatform/walmart/returnOrder/list";
const PAGE_SIZE = 100;
const MAX_PAGES = 200;
const sleep = (ms: number): Promise<void> => new Promise((r) => setTimeout(r, ms));

function getDb(): Promise<mysql.Connection> {
  return mysql.createConnection({
    host: process.env.DB_HOST ?? "127.0.0.1",
    port: Number(process.env.DB_PORT ?? 3306),
    user: process.env.DB_USER ?? "",
    password: process.env.DB_PASSWORD ?? "",
    database: process.env.DB_NAME ?? "walmart_ai_data",
  });
}
function getArg(name: string): string {
  const p = `--${name}=`;
  const f = process.argv.slice(2).find((a) => a.startsWith(p));
  return f ? f.slice(p.length).trim() : "";
}
function chinaDate(offsetDays: number): string {
  return new Date(Date.now() + 8 * 3600 * 1000 + offsetDays * 86400 * 1000).toISOString().slice(0, 10);
}

interface ReturnItem {
  msku?: unknown; quantityDisplay?: unknown; lineTotalAmount?: unknown; status?: unknown;
  currentRefundStatus?: unknown; returnReason?: unknown; returnDescription?: unknown; [k: string]: unknown;
}
interface ReturnOrder {
  returnOrderId?: unknown; customerOrderId?: unknown; storeId?: unknown; returnType?: unknown;
  returnOrderDate?: unknown; purchaseTimeLocale?: unknown; items?: ReturnItem[]; [k: string]: unknown;
}

async function main(): Promise<void> {
  const confirmWrite = process.argv.includes("--confirm-write");
  const startDate = getArg("start") || chinaDate(-7);
  const endDate = getArg("end") || chinaDate(0);
  const captureBatch = endDate.slice(0, 7);
  const cfg = loadConfig();
  const client = new LingxingClient(cfg);
  const db = await getDb();
  const normStore = await buildStoreNormalizer(db);
  let storeNormFixed = 0, storeNormMiss = 0;
  let apiCalls = 0, fetched = 0, rawUpserts = 0, factUpserts = 0, skippedNonRefund = 0, mappedItem = 0, unmapped = 0;
  try {
    console.log(`窗口 ${startDate}~${endDate}（售后时间）｜write=${confirmWrite}`);
    const orders: ReturnOrder[] = [];
    for (let page = 1; page <= MAX_PAGES; page++) {
      const resp = await client.request<{ list?: ReturnOrder[]; total?: number }>({
        method: "POST", path: API_PATH,
        params: { startDate, endDate, dateType: 1, pageNum: page, pageSize: PAGE_SIZE },
        timeoutMs: 30000,
      });
      apiCalls += 1;
      const d = resp?.data as { list?: ReturnOrder[]; total?: number } | undefined;
      const list = d?.list ?? [];
      orders.push(...list);
      if (page === 1) console.log(`接口 total=${d?.total ?? "?"}`);
      if (list.length < PAGE_SIZE) break;
      await sleep(1500);
    }
    fetched = orders.length;
    console.log(`拉取售后单 ${fetched} 条`);

    // ── RAW upsert ──
    for (const o of orders) {
      const rid = String(o.returnOrderId ?? "").trim();
      const rawStoreId = String(o.storeId ?? "");
      const _n = normStore(rawStoreId);
      if (_n && _n !== rawStoreId) storeNormFixed += 1;
      if (!_n && rawStoreId) storeNormMiss += 1;
      const normedStoreId = _n ?? rawStoreId;
      if (!rid) continue;
      for (const it of (o.items ?? [])) {
        const msku = String(it.msku ?? "").trim();
        if (!msku) continue;
        if (confirmWrite) {
          const [res] = await db.execute(
            `INSERT INTO raw_walmart_return_order
               (return_order_id, msku, customer_order_id, purchase_order_id, store_id,
                return_type, item_status, refund_status, return_order_date, purchase_time,
                quantity, line_total_amount, return_reason, return_description, row_json, capture_batch)
             VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
             ON DUPLICATE KEY UPDATE
               item_status=VALUES(item_status), refund_status=VALUES(refund_status),
               quantity=VALUES(quantity), line_total_amount=VALUES(line_total_amount),
               return_reason=VALUES(return_reason), return_description=VALUES(return_description),
               row_json=VALUES(row_json), capture_batch=VALUES(capture_batch)`,
            [rid, msku, String(o.customerOrderId ?? ""), String((it as Record<string, unknown>).purchaseOrderId ?? ""),
             normedStoreId, String(o.returnType ?? ""), String(it.status ?? ""),
             String(it.currentRefundStatus ?? ""), String(o.returnOrderDate ?? "") || null,
             String(o.purchaseTimeLocale ?? "") || null, Math.round(Number(it.quantityDisplay ?? 0)),
             Number(it.lineTotalAmount ?? 0), String(it.returnReason ?? "").slice(0, 64),
             String(it.returnDescription ?? "").slice(0, 255),
             JSON.stringify({ header: { ...o, items: undefined }, item: it }), captureBatch]);
          if ((res as mysql.ResultSetHeader).affectedRows > 0) rawUpserts += 1;
        } else { rawUpserts += 1; }
      }
    }

    // ── FACT 窗口重算（从RAW聚合，仅 returnType=REFUND）──
    const [aggRows] = await db.execute(
      `SELECT store_id, msku, DATE_FORMAT(return_order_date, '%Y-%m-%d') d,
              COUNT(DISTINCT return_order_id) orders, SUM(quantity) qty, ROUND(SUM(line_total_amount),2) amt
       FROM raw_walmart_return_order
       WHERE return_type='REFUND' AND return_order_date IS NOT NULL
         AND DATE(return_order_date) BETWEEN ? AND ?
       GROUP BY store_id, msku, DATE_FORMAT(return_order_date, '%Y-%m-%d')`, [startDate, endDate]);
    const aggs = aggRows as Array<Record<string, unknown>>;
    const nonRefundCheck = orders.filter((o) => String(o.returnType) !== "REFUND").length;
    skippedNonRefund = nonRefundCheck;
    for (const a of aggs) {
      const storeId = String(a.store_id), msku = String(a.msku);
      const [dp] = await db.execute(
        `SELECT item_id FROM dim_product
         WHERE platform='walmart' AND store_id=? AND msku=?
         ORDER BY (product_management_status='active') DESC, updated_at DESC LIMIT 1`, [storeId, msku]);
      const itemId = String((dp as Array<Record<string, unknown>>)[0]?.item_id ?? "");
      if (itemId) mappedItem += 1; else unmapped += 1;
      if (confirmWrite) {
        await db.execute(
          `INSERT INTO fact_refund_daily
             (platform, store_id, item_id, msku, refund_date, refund_orders, refund_qty, refund_amount, source_system)
           VALUES ('walmart', ?, ?, ?, ?, ?, ?, ?, 'walmart_return_api')
           ON DUPLICATE KEY UPDATE
             item_id=VALUES(item_id), refund_orders=VALUES(refund_orders),
             refund_qty=VALUES(refund_qty), refund_amount=VALUES(refund_amount)`,
          [storeId, itemId, msku, String(a.d).slice(0, 10), Number(a.orders), Number(a.qty), Number(a.amt)]);
      }
      factUpserts += 1;
    }
  } finally { await db.end().catch(() => undefined); }
  console.log("SUMMARY_JSON=" + JSON.stringify({
    startDate, endDate, dryRun: !confirmWrite, apiCalls, fetched,
    raw_upserts: rawUpserts, fact_upserts: factUpserts, non_refund_orders: skippedNonRefund,
    item_mapped: mappedItem, item_unmapped: unmapped,
      store_norm_fixed: storeNormFixed, store_norm_miss: storeNormMiss, status: "success",
  }));
}

main().catch((e) => { console.error("FATAL:", e instanceof Error ? e.message : String(e)); process.exit(1); });
