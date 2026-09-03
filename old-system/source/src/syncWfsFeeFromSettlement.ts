/**
 * syncWfsFeeFromSettlement.ts — WFS配送费自动化（结算利润订单口径，2026-07-17 定稿）
 *
 * 数据流：领星 POST /basicOpen/multiplatform/profit/report/order（walmart/销售/USD/结算日期近60天）
 *   → raw_lingxing_settlement_order（RAW 原样留存，uk uniqueId+rowIndex upsert）
 *   → dim_product_wfs_fee_auto（店铺+msku级自动费率，v2 键位 uk_store_msku）
 *
 * 口径 v2（2026-07-17 缺陷修复，需求方实证 20176060394 串数据后定稿）：
 *   键位 = 店铺+msku——跨店同名 msku 是不同产品，必须隔离（缺陷一修复）
 *   店铺ID取值（v2.1）：结算行 storeId 为18位数字，超出 JS Number 安全精度，JSON.parse 已损尾数
 *     （RAW 留存的也是损值，实证 199/331 命中）→ 改用 storeName 精确映射 dim_store_config.store_id，
 *     storeId 字符串仅作无名兜底；unmappedStores 计数回报
 *   配对折算 = 物流费挂在 salesNum=0 的独立费用行上，按平台单号把费用行与销售行配对：
 *     单件费率 = |该单物流费合计| ÷ 该单销售件数合计（件数=0 的费用单剔除并计数，缺陷二修复）
 *   自动WFS费 = 配对后单件费率【众数】（并列取结算日期较新的值）
 *   样本保护：窗口总件数 < 10 或 无有效费率订单 → fee=NULL（利润链回退人工值）
 *   频率：每月一跑（cron 每月25日）；--from-raw 从 RAW 重算不调 API（修复重算/回测用）
 *   CS测品（msku LIKE 'CS%'）不参与：利润链对CS有固定值覆盖
 *
 * 消费侧（本脚本不改）：syncOrderProfitDaily COALESCE(auto.fee, 人工store, 人工item, 0)
 * 用法：
 *   npx ts-node src/syncWfsFeeFromSettlement.ts                  # dry-run 全量试算，零写入
 *   npx ts-node src/syncWfsFeeFromSettlement.ts --msku=YC00018-1A  # 单msku试算
 *   npx ts-node src/syncWfsFeeFromSettlement.ts --confirm-write
 *   npx ts-node src/syncWfsFeeFromSettlement.ts --from-raw [--confirm-write]  # 复用RAW重算，不调API
 * 限速：令牌桶容量=1，请求间隔1200ms；450 msku 约10~15分钟（--from-raw 秒级）。
 */

import "dotenv/config";
import * as mysql from "mysql2/promise";
import { loadConfig } from "./config";
import { LingxingClient } from "./lingxingClient";

const API_PATH = "/basicOpen/multiplatform/profit/report/order";
const PAGE_LEN = 200;
const REQ_INTERVAL_MS = 1200;
const WINDOW_DAYS = 60;
const MIN_UNITS = 10;        // 窗口销量阈值（需求方拍板：10件）
const SETTLE_LAG_DAYS = 2;   // 结算 T+2

interface OrderRow {
  msku?: unknown; salesNum?: unknown; platformLogisticsAmount?: unknown;
  settlementDate?: unknown; uniqueId?: unknown; rowIndex?: unknown;
  transactionTypeS?: unknown; transactionTypes?: unknown;
  storeId?: unknown; storeName?: unknown; platformOrderNo?: unknown;
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

function toNum(v: unknown): number {
  const n = Number(String(v ?? "").replace(/,/g, ""));
  return Number.isFinite(n) ? n : 0;
}

function shanghaiDate(offsetDays = 0): string {
  const d = new Date(Date.now() + 8 * 3600 * 1000);
  d.setUTCDate(d.getUTCDate() + offsetDays);
  return d.toISOString().slice(0, 10);
}

function sleep(ms: number): Promise<void> {
  return new Promise((r) => setTimeout(r, ms));
}

function getArg(name: string): string {
  const prefix = `--${name}=`;
  const arg = process.argv.find((a) => a.startsWith(prefix));
  return arg ? arg.slice(prefix.length) : "";
}

/** 按平台单号配对折算单件费率（v2：费用行 salesNum=0，件数取同单销售行合计） */
function orderUnitFees(rows: OrderRow[]): { samples: Array<{ fee: number; date: string }>; units: number; skippedNoQty: number } {
  const byOrder = new Map<string, { qty: number; fee: number; latest: string }>();
  let units = 0;
  for (const r of rows) {
    const orderNo = String(r.platformOrderNo ?? "").trim() || `__row_${String(r.uniqueId ?? "")}_${String(r.rowIndex ?? "")}`;
    const cur = byOrder.get(orderNo) ?? { qty: 0, fee: 0, latest: "" };
    cur.qty += toNum(r.salesNum);
    cur.fee += toNum(r.platformLogisticsAmount);
    const d = String(r.settlementDate ?? "");
    if (d > cur.latest) cur.latest = d;
    byOrder.set(orderNo, cur);
    units += toNum(r.salesNum);
  }
  const samples: Array<{ fee: number; date: string }> = [];
  let skippedNoQty = 0;
  for (const o of byOrder.values()) {
    if (Math.abs(o.fee) <= 0) continue;
    if (o.qty < 1) { skippedNoQty += 1; continue; } // 费用单窗口内无件数可配对，剔除
    samples.push({ fee: Math.round(Math.abs(o.fee) / o.qty * 100) / 100, date: o.latest });
  }
  return { samples, units, skippedNoQty };
}

/** 众数（并列取 settlementDate 较新者） */
function feeMode(samples: Array<{ fee: number; date: string }>): { fee: number; count: number } | null {
  if (samples.length === 0) return null;
  const agg = new Map<number, { count: number; latest: string }>();
  for (const s of samples) {
    const cur = agg.get(s.fee) ?? { count: 0, latest: "" };
    cur.count += 1;
    if (s.date > cur.latest) cur.latest = s.date;
    agg.set(s.fee, cur);
  }
  let best: { fee: number; count: number; latest: string } | null = null;
  for (const [fee, v] of agg) {
    if (!best || v.count > best.count || (v.count === best.count && v.latest > best.latest)) {
      best = { fee, count: v.count, latest: v.latest };
    }
  }
  return best ? { fee: best.fee, count: best.count } : null;
}

async function main(): Promise<void> {
  const confirmWrite = process.argv.includes("--confirm-write");
  const fromRaw = process.argv.includes("--from-raw");
  const onlyMsku = getArg("msku").trim();
  const endDate = shanghaiDate(-SETTLE_LAG_DAYS);
  const startDate = shanghaiDate(-SETTLE_LAG_DAYS - WINDOW_DAYS + 1);
  const captureBatch = endDate.slice(0, 7);
  const client = new LingxingClient(loadConfig());
  const db = await getDb();

  let apiCalls = 0;
  let rawUpserts = 0;
  let withFee = 0;
  let lowSample = 0;
  let noFeeRows = 0;
  const unmappedStores = new Set<string>();
  const preview: Array<Record<string, unknown>> = [];
  try {
    let mskus: string[];
    if (onlyMsku) {
      mskus = [onlyMsku];
    } else {
      const [rows] = await db.execute(
        `SELECT DISTINCT msku FROM dim_product
         WHERE platform = 'walmart' AND COALESCE(NULLIF(msku,''),'') <> ''
           AND msku NOT LIKE 'CS%'
           AND COALESCE(NULLIF(product_management_status,''),'active') NOT IN ('inactive','archived')
         ORDER BY msku`,
      );
      mskus = (rows as Array<{ msku: string }>).map((r) => String(r.msku));
    }
    // v2.1：店铺名→精确store_id映射（结算行storeId数值超JS安全精度不可信）
    const [storeRows] = await db.execute(
      `SELECT store_id, store_name FROM dim_store_config WHERE platform = 'walmart'`,
    );
    const storeIdByName = new Map<string, string>();
    for (const s of storeRows as Array<{ store_id: string; store_name: string }>) {
      storeIdByName.set(String(s.store_name).trim(), String(s.store_id));
    }
    console.log(`窗口 ${startDate}~${endDate}（结算日期）｜待处理 msku=${mskus.length}｜write=${confirmWrite}｜fromRaw=${fromRaw}｜店铺映射=${storeIdByName.size}`);

    for (const [idx, msku] of mskus.entries()) {
      // 取该 msku 窗口内全部销售结算行：默认走API（短页终止；接口 total 不可靠）；--from-raw 复用RAW
      const rows: OrderRow[] = [];
      if (fromRaw) {
        const [rawRows] = await db.execute(
          `SELECT row_json FROM raw_lingxing_settlement_order WHERE msku_query = ?`,
          [msku],
        );
        for (const rr of rawRows as Array<{ row_json: unknown }>) {
          const r = (typeof rr.row_json === "string" ? JSON.parse(rr.row_json) : rr.row_json) as OrderRow;
          const d = String(r.settlementDate ?? "").slice(0, 10);
          if (String(r.msku ?? "").trim() === msku && d >= startDate && d <= endDate) rows.push(r);
        }
      } else {
        let offset = 0;
        for (;;) {
          const resp = await client.request<{ list?: OrderRow[] }>({
            method: "POST", path: API_PATH,
            params: {
              offset, length: PAGE_LEN,
              platformCodeS: ["10008"], transactionTypeS: [0],
              currencyCode: "USD", searchDateType: "2",
              startDate, endDate,
              searchField: "msku", searchValue: msku,
            },
            timeoutMs: 30000,
          });
          apiCalls += 1;
          const list = resp?.data?.list ?? [];
          // 搜索可能模糊命中，精确过滤本 msku
          rows.push(...list.filter((r) => String(r.msku ?? "").trim() === msku));
          if (list.length < PAGE_LEN) break;
          offset += PAGE_LEN;
          await sleep(REQ_INTERVAL_MS);
        }
      }

      // RAW 留痕（--from-raw 时来源即RAW，不重写）
      if (confirmWrite && !fromRaw) {
        for (const r of rows) {
          const [res] = await db.execute(
            `INSERT INTO raw_lingxing_settlement_order
               (capture_batch, msku_query, unique_id, row_index, row_json)
             VALUES (?, ?, ?, ?, ?)
             ON DUPLICATE KEY UPDATE row_json = VALUES(row_json), capture_batch = VALUES(capture_batch)`,
            [captureBatch, msku, String(r.uniqueId ?? ""), String(r.rowIndex ?? ""), JSON.stringify(r)],
          );
          if ((res as mysql.ResultSetHeader).affectedRows > 0) rawUpserts += 1;
        }
      }

      // v2：按店铺分组（缺陷一修复：跨店同名msku必须隔离）
      // v2.1：storeName→精确store_id映射；storeId数值已损精度仅兜底
      const byStore = new Map<string, OrderRow[]>();
      for (const r of rows) {
        const sname = String(r.storeName ?? "").trim();
        const mapped = storeIdByName.get(sname);
        if (!mapped && sname) unmappedStores.add(sname);
        const sid = mapped ?? String(r.storeId ?? "").trim();
        const arr = byStore.get(sid) ?? [];
        arr.push(r);
        byStore.set(sid, arr);
      }

      // 窗口内无结算行的旧(店铺,msku)自动值先置NULL（回退人工），窗口对齐本次
      if (confirmWrite) {
        await db.execute(
          `UPDATE dim_product_wfs_fee_auto
              SET fee = NULL, sample_units = 0, fee_orders = 0, skipped_no_qty = 0,
                  mode_count = 0, window_start = ?, window_end = ?
            WHERE platform = 'walmart' AND msku = ?`,
          [startDate, endDate, msku],
        );
      }

      for (const [storeId, storeRows] of byStore) {
        // v2：按平台单号配对折算（缺陷二修复：费用行salesNum=0，件数取同单销售行）
        const { samples, units, skippedNoQty } = orderUnitFees(storeRows);
        const mode = feeMode(samples);
        let fee: number | null = null;
        if (units < MIN_UNITS) lowSample += 1;
        else if (!mode) noFeeRows += 1;
        else { fee = mode.fee; withFee += 1; }

        if (confirmWrite) {
          await db.execute(
            `INSERT INTO dim_product_wfs_fee_auto
               (platform, store_id, msku, fee, sample_units, fee_orders, skipped_no_qty, mode_count, window_start, window_end)
             VALUES ('walmart', ?, ?, ?, ?, ?, ?, ?, ?, ?)
             ON DUPLICATE KEY UPDATE
               fee = VALUES(fee), sample_units = VALUES(sample_units), fee_orders = VALUES(fee_orders),
               skipped_no_qty = VALUES(skipped_no_qty), mode_count = VALUES(mode_count),
               window_start = VALUES(window_start), window_end = VALUES(window_end)`,
            [storeId, msku, fee, units, samples.length, skippedNoQty, mode?.count ?? 0, startDate, endDate],
          );
        }
        if (preview.length < 10) {
          preview.push({ storeId, msku, units, feeOrders: samples.length, skippedNoQty, fee, modeCount: mode?.count ?? 0 });
        }
      }
      if ((idx + 1) % 50 === 0) console.log(`  进度 ${idx + 1}/${mskus.length}`);
      if (!fromRaw) await sleep(REQ_INTERVAL_MS);
    }

    console.log("PREVIEW=" + JSON.stringify(preview, null, 2));
    console.log("SUMMARY_JSON=" + JSON.stringify({
      startDate, endDate, captureBatch, dryRun: !confirmWrite,
      mskus: onlyMsku ? 1 : undefined, apiCalls, rawUpserts,
      withFee, lowSample, noFeeRows,
      unmappedStores: [...unmappedStores],
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
