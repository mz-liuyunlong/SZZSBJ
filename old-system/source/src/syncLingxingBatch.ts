/**
 * syncLingxingBatch.ts — 领星批次明细同步（AI财务 批9）
 *
 * 链路：领星 getBatchDetailList → raw_lingxing_api（RAW-first）→ fact_lingxing_batch（wid+batch_no 幂等）
 *
 * 口径（探针1d 实锤，2026-08-13）：
 *   - 路径 /erp/sc/routing/data/local_inventory/getBatchDetailList，解包 resp.data.data
 *   - stock_price = purchase_price + price(其他) + head_stock_price（样例恒等已实证）；
 *     stock_cost = stock_price × balance_num（样例 27.1851×24=652.44 分毫不差）
 *   - 恒等式作为逐行自检：偏差 > ¥0.02 计数并抽样打印（不拦截，供判读接口口径是否变化）
 *   - 用途：①期初一刀（2026-05-01 前入库批次的 SKU 加权平均 stock_price）②当前存货价值 ③成本追溯
 *
 * 规范：默认 dry-run 零写入；--confirm-write 才写库；RAW 失败页不写 FACT；不发飞书；不碰既有表。
 *
 * 运行：
 *   npx ts-node src/syncLingxingBatch.ts                 # dry-run（统计+期初预演）
 *   npx ts-node src/syncLingxingBatch.ts --confirm-write
 */

import "dotenv/config";
import * as crypto from "crypto";
import * as mysql from "mysql2/promise";
import { loadConfig } from "./config";
import { LingxingClient } from "./lingxingClient";

const SCRIPT_NAME = "syncLingxingBatch";
const API_PATH = "/erp/sc/routing/data/local_inventory/getBatchDetailList";
const PAGE_SIZE = 200;
const MAX_PAGES = 100;
const PAGE_DELAY_MS = 800;
const CUTOFF = "2026-05-01"; // 期初一刀切点（需求方 2026-08-13 拍板）

const CONFIRM_WRITE = process.argv.includes("--confirm-write");

function s(v: unknown): string { return String(v ?? "").trim(); }
function num(v: unknown): number { const x = Number(v); return Number.isFinite(x) ? x : 0; }
function r4(v: number): number { return Math.round(v * 10000) / 10000; }
function toDateTime(v: unknown): string | null {
  const t = s(v);
  if (/^\d{4}-\d{2}-\d{2} \d{2}:\d{2}(:\d{2})?$/.test(t)) return t.length === 16 ? `${t}:00` : t;
  return /^\d{4}-\d{2}-\d{2}$/.test(t) ? `${t} 00:00:00` : null;
}
function sleep(ms: number): Promise<void> { return new Promise((r) => setTimeout(r, ms)); }

interface BatchRow {
  wid?: unknown; wh_name?: unknown; batch_no?: unknown; order_sn?: unknown;
  type?: unknown; type_name?: unknown; product_id?: unknown; product_name?: unknown;
  sku?: unknown; msku?: unknown; store_id?: unknown;
  total?: unknown; balance_num?: unknown; transit_balance_num?: unknown;
  good_num?: unknown; bad_num?: unknown;
  purchase_price?: unknown; price?: unknown; head_stock_price?: unknown;
  stock_price?: unknown; stock_cost?: unknown; amount?: unknown;
  head_stock_cost?: unknown; fee?: unknown;
  purchase_in_time?: unknown; batch_time?: unknown; inventory_age?: unknown;
  update_time?: unknown; source_batch_no?: unknown; purchase_order_sns?: unknown; supplier_names?: unknown;
}

async function insertRaw(db: mysql.Connection, params: unknown, resp: unknown, batchNo: number): Promise<number> {
  const requestJson = JSON.stringify(params);
  const responseJson = JSON.stringify(resp);
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
    `SELECT id FROM raw_lingxing_api WHERE api_path=? AND data_date=CURDATE() AND raw_hash=? ORDER BY id DESC LIMIT 1`,
    [API_PATH, rawHash],
  );
  const rawId = Number(rows[0]?.id ?? 0);
  if (!rawId) throw new Error(`RAW 写入/回查失败（第${batchNo}页），本页不写 FACT`);
  return rawId;
}

async function main(): Promise<void> {
  console.log("=".repeat(64));
  console.log(`领星批次明细同步 ${CONFIRM_WRITE ? "[confirm-write 写库]" : "[dry-run 零写入]"}`);
  console.log(`接口=${API_PATH} | 每页=${PAGE_SIZE} | 期初切点=${CUTOFF}`);
  console.log("=".repeat(64));

  const client = new LingxingClient(loadConfig());
  const db = await mysql.createConnection({
    host: process.env.DB_HOST ?? "127.0.0.1",
    port: Number(process.env.DB_PORT ?? 3306),
    user: process.env.DB_USER ?? "",
    password: process.env.DB_PASSWORD ?? "",
    database: process.env.DB_NAME ?? "walmart_ai_data",
    dateStrings: true,
  });

  const sum = {
    pages: 0, rows: 0, upserts: 0, identityBad: 0,
    minIn: "", maxIn: "",
    skus: new Set<string>(),
    preCut: { batches: 0, skus: new Set<string>(), qty: 0, cost: 0 },
    balancePos: { batches: 0, qty: 0, cost: 0 },
    byWh: new Map<string, { n: number; qty: number }>(),
    // 期初预演：切点前入库批次 按 SKU 加权（Σ单价×入库量 ÷ Σ入库量，用 total 权重）
    opening: new Map<string, { qty: number; amt: number }>(),
  };

  try {
    for (let page = 1; page <= MAX_PAGES; page++) {
      const params = { offset: (page - 1) * PAGE_SIZE, length: PAGE_SIZE };
      const resp = await client.post<unknown>(API_PATH, params);
      const outer = resp as { data?: { data?: BatchRow[]; list?: BatchRow[] } };
      const list: BatchRow[] = (outer.data?.data ?? outer.data?.list ?? []) as BatchRow[];
      sum.pages += 1;
      console.log(`  第${page}页: ${list.length} 批`);
      if (!list.length) break;

      let rawId = 0;
      if (CONFIRM_WRITE) rawId = await insertRaw(db, { api: API_PATH, ...params }, resp, page);

      for (const b of list) {
        const batchNo = s(b.batch_no);
        const sku = s(b.sku);
        if (!batchNo || !sku) continue;
        sum.rows += 1;
        sum.skus.add(sku);

        const pp = num(b.purchase_price), op = num(b.price), hp = num(b.head_stock_price);
        const sp = num(b.stock_price), sc = num(b.stock_cost);
        const bal = Math.round(num(b.balance_num));
        const total = Math.round(num(b.total));
        if (Math.abs(r4(pp + op + hp) - sp) > 0.02 || Math.abs(r4(sp * bal) - sc) > 0.05) {
          sum.identityBad += 1;
          if (sum.identityBad <= 8) {
            console.log(`  ⚠️ 恒等不符 ${batchNo}/${sku}: ${pp}+${op}+${hp}=${r4(pp + op + hp)} vs stock_price ${sp}; ×${bal}=${r4(sp * bal)} vs stock_cost ${sc}`);
          }
        }

        const inTime = toDateTime(b.purchase_in_time);
        const inDate = inTime ? inTime.slice(0, 10) : "";
        if (inDate) {
          if (!sum.minIn || inDate < sum.minIn) sum.minIn = inDate;
          if (!sum.maxIn || inDate > sum.maxIn) sum.maxIn = inDate;
        }
        if (inDate && inDate < CUTOFF) {
          sum.preCut.batches += 1; sum.preCut.skus.add(sku);
          sum.preCut.qty += bal; sum.preCut.cost = r4(sum.preCut.cost + sc);
          const o = sum.opening.get(sku) ?? { qty: 0, amt: 0 };
          o.qty += total; o.amt = r4(o.amt + sp * total);
          sum.opening.set(sku, o);
        }
        if (bal > 0) {
          sum.balancePos.batches += 1; sum.balancePos.qty += bal;
          sum.balancePos.cost = r4(sum.balancePos.cost + sc);
        }
        const wh = s(b.wh_name) || "(空)";
        const w = sum.byWh.get(wh) ?? { n: 0, qty: 0 };
        w.n += 1; w.qty += bal; sum.byWh.set(wh, w);

        if (!CONFIRM_WRITE) continue;
        await db.query(
          `INSERT INTO fact_lingxing_batch
             (wid, wh_name, batch_no, order_sn, type, type_name, product_id, product_name, sku, msku, store_id,
              total, balance_num, transit_balance_num, good_num, bad_num,
              purchase_price, other_price, head_stock_price, stock_price, stock_cost, amount, head_stock_cost, fee,
              purchase_in_time, batch_time, inventory_age, lx_update_time,
              source_batch_json, purchase_sns_json, supplier_names, source_raw_id)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,CAST(? AS JSON),CAST(? AS JSON),?,?)
           ON DUPLICATE KEY UPDATE
             wh_name=VALUES(wh_name), order_sn=VALUES(order_sn), type=VALUES(type), type_name=VALUES(type_name),
             product_id=VALUES(product_id), product_name=VALUES(product_name), sku=VALUES(sku), msku=VALUES(msku),
             store_id=VALUES(store_id), total=VALUES(total), balance_num=VALUES(balance_num),
             transit_balance_num=VALUES(transit_balance_num), good_num=VALUES(good_num), bad_num=VALUES(bad_num),
             purchase_price=VALUES(purchase_price), other_price=VALUES(other_price),
             head_stock_price=VALUES(head_stock_price), stock_price=VALUES(stock_price),
             stock_cost=VALUES(stock_cost), amount=VALUES(amount), head_stock_cost=VALUES(head_stock_cost),
             fee=VALUES(fee), purchase_in_time=VALUES(purchase_in_time), batch_time=VALUES(batch_time),
             inventory_age=VALUES(inventory_age), lx_update_time=VALUES(lx_update_time),
             source_batch_json=VALUES(source_batch_json), purchase_sns_json=VALUES(purchase_sns_json),
             supplier_names=VALUES(supplier_names), source_raw_id=VALUES(source_raw_id), updated_at=NOW()`,
          [Math.round(num(b.wid)), s(b.wh_name).slice(0, 64), batchNo, s(b.order_sn), Math.round(num(b.type)),
           s(b.type_name).slice(0, 32), s(b.product_id), s(b.product_name).slice(0, 255), sku, s(b.msku).slice(0, 128),
           s(b.store_id), total, bal, Math.round(num(b.transit_balance_num)),
           Math.round(num(b.good_num)), Math.round(num(b.bad_num)),
           pp, op, hp, sp, sc, num(b.amount), num(b.head_stock_cost), num(b.fee),
           inTime, toDateTime(b.batch_time), Math.round(num(b.inventory_age)), toDateTime(b.update_time),
           JSON.stringify(b.source_batch_no ?? []), JSON.stringify(b.purchase_order_sns ?? []),
           Array.isArray(b.supplier_names) ? b.supplier_names.map((x) => s(x)).join(",").slice(0, 255) : s(b.supplier_names).slice(0, 255),
           rawId],
        );
        sum.upserts += 1;
      }
      if (list.length < PAGE_SIZE) break;
      await sleep(PAGE_DELAY_MS);
    }

    console.log("\n" + "=".repeat(64));
    console.log(`批次 ${sum.rows} 条（upsert ${sum.upserts}）｜SKU ${sum.skus.size} 个｜入库时间 ${sum.minIn || "-"} ~ ${sum.maxIn || "-"}`);
    console.log(`恒等自检不符 ${sum.identityBad} 条${sum.identityBad ? "（口径可能变化，需判读）" : "（全部通过）"}`);
    console.log(`当前结存>0：${sum.balancePos.batches} 批 / ${sum.balancePos.qty} 件 / 结存成本 ¥${sum.balancePos.cost}`);
    console.log(`\n【期初预演】切点(${CUTOFF})前入库批次：${sum.preCut.batches} 批 / SKU ${sum.preCut.skus.size} 个 / 现结存 ${sum.preCut.qty} 件 / 结存成本 ¥${sum.preCut.cost}`);
    console.log("仓库分布（批次数/结存件数）：");
    for (const [k, v] of Array.from(sum.byWh.entries()).sort((a, b) => b[1].qty - a[1].qty)) {
      console.log(`  ${k}: ${v.n} 批 / ${v.qty} 件`);
    }
    const ops = Array.from(sum.opening.entries())
      .map(([sku, o]) => ({ sku, qty: o.qty, unit: o.qty > 0 ? r4(o.amt / o.qty) : 0 }))
      .sort((a, b) => b.qty - a.qty);
    console.log(`\n【期初单价一刀·草案】切点前入库批次按入库量加权平均 stock_price（前 20 个 SKU）：`);
    for (const o of ops.slice(0, 20)) console.log(`  ${o.sku}: 加权单价 ¥${o.unit}（切点前入库 ${o.qty} 件）`);
    console.log(`（共 ${ops.length} 个 SKU 可从批次取到期初单价；完整清单待落库后 SQL 导出给财务复核）`);
    console.log(CONFIRM_WRITE ? "已写库。" : "dry-run 结束，未写入任何数据。");
  } finally {
    await db.end().catch(() => undefined);
  }
}

main().catch((e) => {
  console.error("同步失败:", e instanceof Error ? e.stack : String(e));
  process.exit(1);
});
