/**
 * syncSettlementMonthly.ts — 领星结算利润月度同步（AI财务 批11；定稿 v1.5 管道②核查线）
 *
 * 链路：领星 /basicOpen/multiplatform/profit/report/msku → raw_lingxing_api（RAW-first）
 *       → fact_settlement_msku_monthly（platform+store_id+msku+settlement_month 幂等）
 *
 * 口径（探针2/4/14b 实证）：
 *   - 参数（探针4实证）：{ offset, length, platformCodeS:["10008"], sids:<store_id>, startDate, endDate }；
 *     结算数据为**月粒度**（探针14b），按自然月窗口逐店铺拉取，settlement_month = 窗口所在月
 *   - list 行字段（探针实证的才落列）：salesNum / salesAmount / purchaseAmount / transportationAmount /
 *     currencyCode / storeId / storeName / msku / localSku。**其余字段名未实证，不猜**——
 *     整行原样存 extra_json（表注释本就要求全量留存），promotion/refund/commission 等列待字段实证后回填。
 *   - localSku 即本地 SKU，存于 extra_json（表无 sku 列），查询用 JSON_EXTRACT(extra_json,'$.localSku')
 *   - 首要用途（2026-08-13）：1~4 月已售数量 → 期初一刀口径2（全链路期初 = 切点前采购 − 早期已售）
 *   - 金额为 USD 原币（list 层），禁用 totalSum（定稿弃用清单）
 *
 * 规范：默认 dry-run 零写入；--confirm-write 才写库；RAW 失败页不写 FACT；不发飞书；隔离开发不碰既有脚本。
 *
 * 运行：
 *   npx ts-node src/syncSettlementMonthly.ts --from=2026-01 --to=2026-04            # dry-run
 *   npx ts-node src/syncSettlementMonthly.ts --from=2026-01 --to=2026-08 --confirm-write
 *   npx ts-node src/syncSettlementMonthly.ts --confirm-write                        # 缺省=当月+前2月(核查线日常)
 */

import "dotenv/config";
import * as crypto from "crypto";
import * as mysql from "mysql2/promise";
import { loadConfig } from "./config";
import { LingxingClient } from "./lingxingClient";

const SCRIPT_NAME = "syncSettlementMonthly";
const API_PATH = "/basicOpen/multiplatform/profit/report/msku";
const WALMART_PLATFORM_CODE = "10008";
const PAGE_SIZE = 200;
const MAX_PAGES = 30;
const REQ_DELAY_MS = 700;

const CONFIRM_WRITE = process.argv.includes("--confirm-write");

function getArg(name: string, def = ""): string {
  const p = `--${name}=`;
  const hit = process.argv.find((a) => a.startsWith(p));
  return hit ? hit.slice(p.length) : def;
}
function sleep(ms: number): Promise<void> { return new Promise((r) => setTimeout(r, ms)); }
function s(v: unknown): string { return String(v ?? "").trim(); }
function num(v: unknown): number { const x = Number(v); return Number.isFinite(x) ? x : 0; }
function r4(v: number): number { return Math.round(v * 10000) / 10000; }

function monthRange(): string[] {
  const nowCst = new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Shanghai", year: "numeric", month: "2-digit" })
    .format(new Date()).slice(0, 7);
  let from = getArg("from", ""), to = getArg("to", "") || nowCst;
  if (!from) {
    const [y, m] = to.split("-").map(Number);
    const d = new Date(Date.UTC(y, m - 3, 1));
    from = `${d.getUTCFullYear()}-${String(d.getUTCMonth() + 1).padStart(2, "0")}`;
  }
  if (!/^\d{4}-\d{2}$/.test(from) || !/^\d{4}-\d{2}$/.test(to)) throw new Error(`--from/--to 需为 yyyy-MM（收到 ${from}/${to}）`);
  const out: string[] = [];
  const [fy, fm] = from.split("-").map(Number);
  const [ty, tm] = to.split("-").map(Number);
  let cur = new Date(Date.UTC(fy, fm - 1, 1));
  const last = new Date(Date.UTC(ty, tm - 1, 1));
  while (cur <= last && out.length < 36) {
    out.push(`${cur.getUTCFullYear()}-${String(cur.getUTCMonth() + 1).padStart(2, "0")}`);
    cur = new Date(Date.UTC(cur.getUTCFullYear(), cur.getUTCMonth() + 1, 1));
  }
  return out;
}
function monthWindow(ym: string): { start: string; end: string } {
  const [y, m] = ym.split("-").map(Number);
  const lastDay = new Date(Date.UTC(y, m, 0)).getUTCDate();
  return { start: `${ym}-01`, end: `${ym}-${String(lastDay).padStart(2, "0")}` };
}

interface Row {
  storeId?: unknown; storeName?: unknown; msku?: unknown; localSku?: unknown; currencyCode?: unknown;
  salesNum?: unknown; salesAmount?: unknown; purchaseAmount?: unknown; transportationAmount?: unknown;
  [k: string]: unknown;
}

async function insertRaw(db: mysql.Connection, params: unknown, resp: unknown, tag: string): Promise<number> {
  const requestJson = JSON.stringify(params);
  const responseJson = JSON.stringify(resp);
  const rawHash = crypto.createHash("sha256").update(`${API_PATH}|${requestJson}|${responseJson}`).digest("hex");
  const extraJson = JSON.stringify({ script: SCRIPT_NAME, tag });
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
  if (!rawId) throw new Error(`RAW 写入/回查失败（${tag}），该页不写 FACT`);
  return rawId;
}

async function main(): Promise<void> {
  const months = monthRange();
  console.log("=".repeat(64));
  console.log(`结算利润月度同步 ${CONFIRM_WRITE ? "[confirm-write 写库]" : "[dry-run 零写入]"}`);
  console.log(`接口=${API_PATH} | 月份 ${months[0]} ~ ${months[months.length - 1]}（${months.length} 个月）| 每页=${PAGE_SIZE}`);
  console.log("列落地：salesNum/salesAmount/purchaseAmount/transportationAmount（实证字段）；整行存 extra_json");
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

  const [storeRows] = await db.query<mysql.RowDataPacket[]>(
    `SELECT store_id, store_name FROM dim_store_config WHERE platform='walmart'`);
  const stores = storeRows.map((r) => ({ id: s(r.store_id), name: s(r.store_name) })).filter((x) => x.id);
  console.log(`walmart 店铺 ${stores.length} 家（dim_store_config）`);

  const sum = {
    rows: 0, upserts: 0, noMsku: 0,
    byMonth: new Map<string, { rows: number; qty: number; amt: number }>(),
    fieldSeen: new Set<string>(),
  };

  try {
    for (const ym of months) {
      const w = monthWindow(ym);
      for (const st of stores) {
        let monthStoreRows = 0;
        for (let page = 1; page <= MAX_PAGES; page++) {
          const params: Record<string, unknown> = {
            offset: (page - 1) * PAGE_SIZE, length: PAGE_SIZE,
            platformCodeS: [WALMART_PLATFORM_CODE], sids: st.id,
            startDate: w.start, endDate: w.end,
          };
          const resp = await client.request<unknown>({ method: "POST", path: API_PATH, params, timeoutMs: 30000 });
          const data = (resp as { data?: { list?: Row[] } }).data;
          const list: Row[] = data?.list ?? [];
          if (page === 1 && list.length) Object.keys(list[0]).forEach((k) => sum.fieldSeen.add(k));
          if (!list.length) break;

          let rawId = 0;
          if (CONFIRM_WRITE) rawId = await insertRaw(db, { api: API_PATH, ...params }, resp, `${ym}|${st.id}|p${page}`);

          for (const row of list) {
            const msku = s(row.msku);
            if (!msku) { sum.noMsku += 1; continue; }
            sum.rows += 1; monthStoreRows += 1;
            const qty = Math.round(num(row.salesNum));
            const amt = r4(num(row.salesAmount));
            const acc = sum.byMonth.get(ym) ?? { rows: 0, qty: 0, amt: 0 };
            acc.rows += 1; acc.qty += qty; acc.amt = r4(acc.amt + amt);
            sum.byMonth.set(ym, acc);

            if (!CONFIRM_WRITE) continue;
            const hash = crypto.createHash("md5")
              .update(`${amt}|${qty}|${num(row.purchaseAmount)}|${num(row.transportationAmount)}`).digest("hex");
            await db.query(
              `INSERT INTO fact_settlement_msku_monthly
                 (platform, store_id, store_name, msku, settlement_month, currency_code,
                  sales_amount, sales_num, purchase_amount, transportation_amount,
                  extra_json, amount_hash, last_synced_at, source_raw_id)
               VALUES ('walmart',?,?,?,?,?,?,?,?,?,CAST(? AS JSON),?,NOW(),?)
               ON DUPLICATE KEY UPDATE
                 store_name=VALUES(store_name), currency_code=VALUES(currency_code),
                 sales_amount=VALUES(sales_amount), sales_num=VALUES(sales_num),
                 purchase_amount=VALUES(purchase_amount), transportation_amount=VALUES(transportation_amount),
                 extra_json=VALUES(extra_json), amount_hash=VALUES(amount_hash),
                 last_synced_at=NOW(), source_raw_id=VALUES(source_raw_id), updated_at=NOW()`,
              // store_id 用请求侧 sid（dim_store_config 正确 id）：API 返回的 row.storeId 是数字，
              // JSON 解析丢精度会把 …845056 损坏成 …845060，导致与 dim_store 永不相交（批12b 实锤）
              [st.id, s(row.storeName).slice(0, 128) || st.name, msku, ym,
               (s(row.currencyCode) || "USD").toUpperCase().slice(0, 8),
               amt, qty, r4(num(row.purchaseAmount)), r4(num(row.transportationAmount)),
               JSON.stringify(row), hash, rawId],
            );
            sum.upserts += 1;
          }
          if (list.length < PAGE_SIZE) break;
          await sleep(REQ_DELAY_MS);
        }
        if (monthStoreRows) console.log(`  ${ym} ${st.name}: ${monthStoreRows} 行`);
        await sleep(REQ_DELAY_MS);
      }
    }

    console.log("\n" + "=".repeat(64));
    console.log(`行 ${sum.rows}（upsert ${sum.upserts}，无msku跳过 ${sum.noMsku}）`);
    console.log("按结算月（行数 / 销量 / 销售额USD）：");
    for (const m of Array.from(sum.byMonth.keys()).sort()) {
      const a = sum.byMonth.get(m)!;
      console.log(`  ${m}   ${String(a.rows).padStart(5)} 行   ${String(a.qty).padStart(7)} 件   $${a.amt}`);
    }
    console.log(`\nlist 首行字段全名（供后续 promotion/refund 等列的字段实证）：\n  ${Array.from(sum.fieldSeen).sort().join(", ")}`);
    console.log(CONFIRM_WRITE ? "已写库。" : "dry-run 结束，未写入任何数据。");
  } finally {
    await db.end().catch(() => undefined);
  }
}

main().catch((e) => {
  console.error("同步失败:", e instanceof Error ? e.stack : String(e));
  process.exit(1);
});
