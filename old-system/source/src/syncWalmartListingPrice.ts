/**
 * syncWalmartListingPrice.ts — Walmart 在线商品 Buy Box 价格同步（2026-07-16）
 *
 * 数据流：领星 POST /basicOpen/multiplatform/walmart/list（status=[0] 仅 PUBLISHED 在线商品）
 *          → raw_lingxing_walmart_listing（RAW 原样留存，capture_date 快照）
 *          → dim_product.buy_box_price（按 store_id+item_id+msku 匹配更新）
 * 响应结构（2026-07-16 生产探针实测）：{code,message,data:[...]}——data 直接是数组、无 total，
 * 翻页以"返回条数<页长"为终止条件。
 *
 * 用途：新品月业绩目标——无成交新品的单价兜底（需求方定稿：取 buy_box_price）。
 * 限速：接口令牌桶容量=1，每页间隔 1200ms；分页 length=200。
 * 铁律：外部数据必先入RAW；DIM 只更新 buy_box_price 两列，不碰人工字段。
 *
 * 用法：
 *   npx ts-node src/syncWalmartListingPrice.ts            # dry-run：拉取+统计，零写入
 *   npx ts-node src/syncWalmartListingPrice.ts --confirm-write
 * cron 建议：每日 05:20（在 16:45 方案B链与早高峰通知链之外）。
 */

import "dotenv/config";
import * as mysql from "mysql2/promise";
import { loadConfig } from "./config";
import { LingxingClient } from "./lingxingClient";
import { laToday } from "./usPacific";

const PAGE_LEN = 200;
const PAGE_INTERVAL_MS = 1200; // 令牌桶容量1，稳妥限速
const API_PATH = "/basicOpen/multiplatform/walmart/list";

interface ListingRow {
  item_id?: unknown; msku?: unknown; store_id?: unknown; store_name?: unknown;
  price?: unknown; buy_box_price?: unknown; listing_start_time?: unknown;
  [k: string]: unknown;
}

function getDb(): Promise<mysql.Connection> {
  return mysql.createConnection({
    host:     process.env.DB_HOST     ?? "127.0.0.1",
    port:     Number(process.env.DB_PORT ?? 3306),
    user:     process.env.DB_USER     ?? "",
    password: process.env.DB_PASSWORD ?? "",
    database: process.env.DB_NAME     ?? "walmart_ai_data",
  });
}

function getClient(): LingxingClient {
  // 密钥/地址统一读环境变量（loadConfig 内部校验必填项）
  return new LingxingClient(loadConfig());
}

function sleep(ms: number): Promise<void> {
  return new Promise((r) => setTimeout(r, ms));
}

function todayShanghai(): string {
  const now = new Date(Date.now() + 8 * 3600 * 1000);
  return now.toISOString().slice(0, 10);
}

/**
 * 2026-08-21 新增：快照观测日（美西日界）。
 * 为什么要这一列：上面的 todayShanghai() 返回**北京日**，而 fact_sales_daily / fact_profit_daily
 *   全系统业务日界是**美西**（usPacific.ts，2026-08-18 立规）。两者天生错位一天——
 *   代码侧在两轮价格探针里就是拿北京日 JOIN 美西日跑出来的，"同向率13.43%"很可能被这个错位污染。
 * 为什么不直接改 capture_date：原列已有 37 天历史、且有唯一键与既有读取依赖它，改原列会破坏历史。
 *   故**只加列不改列**：capture_date 原样保留，新链路（调价差分）一律用 capture_date_la。
 * 本 cron 挂北京 05:20，= UTC 前一日 21:20 = 美西前一日 13:20(PST)/14:20(PDT)，恒为前一天；
 *   但这里不做减一天的推算，直接取美西当前日，DST 与手工跑时段都由 usPacific 兜住。
 */
function todayLosAngeles(): string {
  return laToday(0);
}

function numOrNull(v: unknown): number | null {
  const n = Number(String(v ?? "").replace(/,/g, ""));
  return Number.isFinite(n) && n > 0 ? Math.round(n * 100) / 100 : null;
}

async function main(): Promise<void> {
  const confirmWrite = process.argv.includes("--confirm-write");
  const captureDate = todayShanghai();
  const captureDateLa = todayLosAngeles(); // 2026-08-21 新增：美西日界，供调价差分使用
  const client = getClient();
  const db = await getDb();

  let fetched = 0;
  let badRows = 0;
  let rawUpserted = 0;
  let dimUpdated = 0;
  let dimMissed = 0;
  let priceNull = 0;
  try {
    const all: ListingRow[] = [];
    let offset = 0;
    let pages = 0;
    for (;;) {
      const resp = await client.request<ListingRow[]>({
        method: "POST", path: API_PATH,
        params: { offset, length: PAGE_LEN, status: [0] }, // 0=PUBLISHED（在线商品口径）
        timeoutMs: 30000,
      });
      const list = Array.isArray(resp?.data) ? resp.data : [];
      all.push(...list);
      fetched += list.length;
      pages += 1;
      if (list.length < PAGE_LEN) break; // 无 total 字段，短页即末页
      if (pages > 500) throw new Error("翻页超过500页保险丝触发，疑似接口异常");
      offset += PAGE_LEN;
      await sleep(PAGE_INTERVAL_MS);
    }
    console.log(`拉取完成 pages=${pages} fetched=${fetched}`);

    for (const r of all) {
      const storeId = String(r.store_id ?? "").trim();
      const itemId = String(r.item_id ?? "").trim();
      const msku = String(r.msku ?? "").trim();
      if (!itemId) { badRows++; continue; }
      const bb = numOrNull(r.buy_box_price) ?? numOrNull(r.price); // BuyBox缺失时用挂牌价兜底
      if (bb === null) priceNull++;

      if (confirmWrite) {
        const [res1] = await db.execute(
          `INSERT INTO raw_lingxing_walmart_listing (capture_date, capture_date_la, store_id, item_id, msku, row_json)
           VALUES (?, ?, ?, ?, ?, ?)
           ON DUPLICATE KEY UPDATE capture_date_la = VALUES(capture_date_la), row_json = VALUES(row_json)`,
          [captureDate, captureDateLa, storeId, itemId, msku, JSON.stringify(r)],
        );
        rawUpserted += (res1 as mysql.ResultSetHeader).affectedRows > 0 ? 1 : 0;
        if (bb !== null) {
          const [res2] = await db.execute(
            `UPDATE dim_product
                SET buy_box_price = ?, buy_box_price_updated_at = NOW()
              WHERE platform = 'walmart' AND item_id = ?
                AND (msku = ? OR ? = '')
                ${storeId ? "AND store_id = ?" : ""}`,
            storeId ? [bb, itemId, msku, msku, storeId] : [bb, itemId, msku, msku],
          );
          const n = (res2 as mysql.ResultSetHeader).affectedRows;
          if (n > 0) dimUpdated += n; else dimMissed++;
        }
      }
    }

    console.log("SUMMARY_JSON=" + JSON.stringify({
      captureDate, captureDateLa, dryRun: !confirmWrite, fetched, badRows, priceNull,
      rawUpserted, dimUpdated, dimMissed,
      status: "success",
    }));
  } finally {
    await db.end().catch(() => undefined);
  }
}

main().catch((e) => {
  console.error("FATAL:", e instanceof Error ? e.message : String(e));
  process.exit(1);
});
