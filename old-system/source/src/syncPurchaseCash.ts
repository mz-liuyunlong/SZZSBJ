/**
 * syncPurchaseCash.ts — 采购单现金支出线同步（AI财务 批8）
 *
 * 链路：领星 purchaseOrderList → raw_lingxing_api（RAW-first）→
 *       fact_purchase_cash（头：现金支出）+ fact_purchase_cash_item（明细：真实单价/金额）
 *
 * 口径（定稿 v1.4 + 探针1b 实锤，2026-08-13）：
 *   - 现金支出 = total_price（货款 amount_total + 运费 shipping_price + 其他 other_fee）
 *   - 记账日 = 下单日 order_time；**order_time 为空串（707 单中 5 单，多为"待下单"）退 create_time**，
 *     date_source 标记来源，不猜不丢
 *   - 复核收口：review_close_at = 记账日的次月末；**已过收口日的单不再刷新（冻结）**，
 *     但库里没有的老单首次仍会插入（历史完整性）
 *   - item.msku 是**数组**（可空）：唯一值逗号连接落库；item 按 (order_sn, sku, msku) 聚合
 *     （同 SKU 多计划行合并，数量金额相加，单价=金额÷数量），保证唯一键幂等
 *   - 守恒自检：|goods_amount − Σitem.amount| > ¥0.5 记为不符并列出（fee_part_type 分摊差异观察用，不拦截）
 *   - 币种：purchase_currency 实测 CNY；出现非 CNY 时计数告警，不折算不猜
 *   - 解包：resp.data.data（2026-07-21 RAW#38710/38711 + 探针1b 双重实证；探针1 多剥一层的教训）
 *
 * 规范：默认 dry-run 零写入；--confirm-write 才写库；RAW 写入失败的页不写 FACT；
 *       不发送任何飞书消息；不改动既有 syncPurchaseOrders.ts 及其表（隔离开发）。
 *
 * 运行：
 *   npx ts-node src/syncPurchaseCash.ts                    # dry-run
 *   npx ts-node src/syncPurchaseCash.ts --pages=2
 *   npx ts-node src/syncPurchaseCash.ts --confirm-write
 */

import "dotenv/config";
import * as crypto from "crypto";
import * as mysql from "mysql2/promise";
import { loadConfig } from "./config";
import { LingxingClient } from "./lingxingClient";

const SCRIPT_NAME = "syncPurchaseCash";
const API_PATH = "/erp/sc/routing/data/local_inventory/purchaseOrderList";
const PAGE_SIZE = 200;
const MAX_PAGES_DEFAULT = 10;
const PAGE_DELAY_MS = 800;

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
function toDate(v: unknown): string | null {
  const m = s(v).match(/^(\d{4}-\d{2}-\d{2})/);
  return m ? m[1] : null;
}
function toDateTime(v: unknown): string | null {
  const t = s(v);
  if (/^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$/.test(t)) return t;
  return /^\d{4}-\d{2}-\d{2}$/.test(t) ? `${t} 00:00:00` : null;
}
function todayCst(): string {
  return new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Shanghai", year: "numeric", month: "2-digit", day: "2-digit" }).format(new Date());
}
/** 记账日次月末（复核收口日）：2026-08-05 → 2026-09-30 */
function reviewCloseOf(cashDate: string): string {
  const [y, m] = cashDate.split("-").map(Number);
  const d = new Date(Date.UTC(y, m + 1, 0)); // 下月第0天=下月末
  return `${d.getUTCFullYear()}-${String(d.getUTCMonth() + 1).padStart(2, "0")}-${String(d.getUTCDate()).padStart(2, "0")}`;
}
/** item.msku 数组 → 唯一值逗号连接（实测可为空数组） */
function mskuStr(v: unknown): string {
  if (Array.isArray(v)) return Array.from(new Set(v.map((x) => s(x)).filter(Boolean))).join(",").slice(0, 128);
  return s(v).slice(0, 128);
}

interface PoItem {
  sku?: unknown; msku?: unknown; product_name?: unknown; sid?: unknown;
  price?: unknown; amount?: unknown; quantity_real?: unknown;
}
interface PoHead {
  order_sn?: unknown; status_text?: unknown; pay_status_text?: unknown;
  order_time?: unknown; create_time?: unknown;
  purchase_currency?: unknown; amount_total?: unknown; shipping_price?: unknown;
  other_fee?: unknown; total_price?: unknown;
  supplier_name?: unknown; opt_realname?: unknown; quantity_total?: unknown;
  item_list?: PoItem[];
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
  const maxPages = Number(getArg("pages", String(MAX_PAGES_DEFAULT))) || MAX_PAGES_DEFAULT;
  const today = todayCst();

  console.log("=".repeat(64));
  console.log(`采购现金线同步 ${CONFIRM_WRITE ? "[confirm-write 写库]" : "[dry-run 零写入]"}`);
  console.log(`接口=${API_PATH} | 每页=${PAGE_SIZE} | 最多${maxPages}页 | 今日(CST)=${today}`);
  console.log("口径：现金支出=total_price(货款+运费+其他)，记账日=order_time(空退create_time)，次月末收口冻结");
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
    pages: 0, orders: 0, headUpserts: 0, itemUpserts: 0, frozenSkipped: 0,
    dateFromCreate: 0, noDate: [] as string[], nonCny: [] as string[],
    conservationBad: [] as string[],
    byMonth: new Map<string, { n: number; cash: number }>(),
    byStatus: new Map<string, number>(),
  };

  try {
    for (let page = 1; page <= maxPages; page++) {
      const params = { offset: (page - 1) * PAGE_SIZE, length: PAGE_SIZE };
      const resp = await client.post<unknown>(API_PATH, params);
      const outer = resp as { data?: { data?: PoHead[]; list?: PoHead[] } };
      const list: PoHead[] = (outer.data?.data ?? outer.data?.list ?? []) as PoHead[];
      sum.pages += 1;
      console.log(`  第${page}页: ${list.length} 单`);
      if (!list.length) break;

      let rawId = 0;
      if (CONFIRM_WRITE) rawId = await insertRaw(db, { api: API_PATH, ...params }, resp, page);

      // 本页冻结判定：已存在且 review_close_at < 今天 → 跳过刷新（首插不受限）
      const sns = list.map((h) => s(h.order_sn)).filter(Boolean);
      const frozen = new Set<string>();
      if (sns.length) {
        const [ex] = await db.query<mysql.RowDataPacket[]>(
          `SELECT order_sn FROM fact_purchase_cash
            WHERE order_sn IN (${sns.map(() => "?").join(",")})
              AND review_close_at IS NOT NULL AND review_close_at < ?`, [...sns, today]);
        for (const r of ex) frozen.add(s(r.order_sn));
      }

      for (const h of list) {
        const orderSn = s(h.order_sn);
        if (!orderSn) continue;
        sum.orders += 1;

        const statusText = s(h.status_text);
        sum.byStatus.set(statusText, (sum.byStatus.get(statusText) ?? 0) + 1);

        const cur = (s(h.purchase_currency) || "CNY").toUpperCase();
        if (cur !== "CNY" && sum.nonCny.length < 20) sum.nonCny.push(`${orderSn}(${cur})`);

        const orderDate = toDate(h.order_time);
        const cashDate = orderDate ?? toDate(h.create_time);
        if (!cashDate) { sum.noDate.push(orderSn); continue; }
        const dateSource = orderDate ? "order_time" : "create_time";
        if (dateSource === "create_time") sum.dateFromCreate += 1;

        const goods = r4(num(h.amount_total));
        const ship = r4(num(h.shipping_price));
        const other = r4(num(h.other_fee));
        const total = r4(num(h.total_price));
        const reviewClose = reviewCloseOf(cashDate);

        // 明细按 (sku, msku) 聚合（同SKU多计划行合并，保证唯一键幂等）
        const agg = new Map<string, { sku: string; msku: string; name: string; sid: string; qty: number; amt: number }>();
        for (const it of h.item_list ?? []) {
          const sku = s(it.sku);
          if (!sku) continue;
          const mk = mskuStr(it.msku);
          const k = `${sku}||${mk}`;
          const a = agg.get(k) ?? { sku, msku: mk, name: s(it.product_name).slice(0, 255), sid: s(it.sid), qty: 0, amt: 0 };
          a.qty += Math.round(num(it.quantity_real));
          a.amt = r4(a.amt + num(it.amount));
          if (!a.sid) a.sid = s(it.sid);
          agg.set(k, a);
        }
        const itemsSum = r4(Array.from(agg.values()).reduce((x, y) => x + y.amt, 0));
        if (Math.abs(goods - itemsSum) > 0.5 && sum.conservationBad.length < 20) {
          sum.conservationBad.push(`${orderSn}: 货款${goods} vs Σ明细${itemsSum}（差${r4(goods - itemsSum)}）`);
        }

        const m = cashDate.slice(0, 7);
        const acc = sum.byMonth.get(m) ?? { n: 0, cash: 0 };
        acc.n += 1; acc.cash = r4(acc.cash + total);
        sum.byMonth.set(m, acc);

        if (!CONFIRM_WRITE) continue;
        if (frozen.has(orderSn)) { sum.frozenSkipped += 1; continue; }

        const amountHash = crypto.createHash("md5").update(`${total}|${goods}|${ship}|${other}|${cashDate}`).digest("hex");
        await db.query(
          `INSERT INTO fact_purchase_cash
             (order_sn, order_time, create_time, date_source, status_text, amount_total,
              goods_amount, shipping_amount, other_amount, supplier_name, creator,
              quantity_total, pay_status_text, currency_code, review_close_at, amount_hash, source_raw_id)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
           ON DUPLICATE KEY UPDATE
             order_time=VALUES(order_time), create_time=VALUES(create_time), date_source=VALUES(date_source),
             status_text=VALUES(status_text), amount_total=VALUES(amount_total),
             goods_amount=VALUES(goods_amount), shipping_amount=VALUES(shipping_amount),
             other_amount=VALUES(other_amount), supplier_name=VALUES(supplier_name), creator=VALUES(creator),
             quantity_total=VALUES(quantity_total), pay_status_text=VALUES(pay_status_text),
             currency_code=VALUES(currency_code), review_close_at=VALUES(review_close_at),
             amount_hash=VALUES(amount_hash), source_raw_id=VALUES(source_raw_id), updated_at=NOW()`,
          [orderSn, cashDate, toDateTime(h.create_time), dateSource, statusText, total,
           goods, ship, other, s(h.supplier_name).slice(0, 128), s(h.opt_realname).slice(0, 64),
           Math.round(num(h.quantity_total)), s(h.pay_status_text).slice(0, 32), cur, reviewClose, amountHash, rawId],
        );
        sum.headUpserts += 1;

        for (const a of agg.values()) {
          await db.query(
            `INSERT INTO fact_purchase_cash_item
               (order_sn, sku, msku, product_name, sid, quantity, unit_price, amount, source_raw_id)
             VALUES (?,?,?,?,?,?,?,?,?)
             ON DUPLICATE KEY UPDATE
               product_name=VALUES(product_name), sid=VALUES(sid), quantity=VALUES(quantity),
               unit_price=VALUES(unit_price), amount=VALUES(amount),
               source_raw_id=VALUES(source_raw_id), updated_at=NOW()`,
            [orderSn, a.sku, a.msku, a.name, a.sid, a.qty,
             a.qty > 0 ? r4(a.amt / a.qty) : 0, a.amt, rawId],
          );
          sum.itemUpserts += 1;
        }
      }

      if (list.length < PAGE_SIZE) break;
      await sleep(PAGE_DELAY_MS);
    }

    console.log("\n" + "=".repeat(64));
    console.log(`采购单 ${sum.orders} 张（头 upsert ${sum.headUpserts}，冻结跳过 ${sum.frozenSkipped}）｜明细 upsert ${sum.itemUpserts}`);
    console.log(`记账日来源：create_time 兜底 ${sum.dateFromCreate} 张`);
    console.log("\n按记账月现金支出（全部状态；页面口径另按基准日 2026-02-01 过滤）：");
    for (const m of Array.from(sum.byMonth.keys()).sort()) {
      const a = sum.byMonth.get(m)!;
      console.log(`  ${m}   ${String(a.n).padStart(4)} 单   ¥${a.cash}`);
    }
    console.log("\n状态分布：");
    for (const [k, v] of Array.from(sum.byStatus.entries()).sort((a, b) => b[1] - a[1])) {
      console.log(`  ${k || "(空)"}: ${v}`);
    }
    if (sum.noDate.length) console.log(`⚠️ 无记账日(order_time与create_time都空) ${sum.noDate.length} 张: ${sum.noDate.slice(0, 10).join(", ")}`);
    if (sum.nonCny.length) console.log(`⚠️ 非人民币采购单（未折算，需人工定口径）: ${sum.nonCny.join(", ")}`);
    if (sum.conservationBad.length) {
      console.log(`⚠️ 货款 vs Σ明细不符（差>¥0.5，观察项不拦截，多为费用分摊设置）: ${sum.conservationBad.length} 张`);
      for (const b of sum.conservationBad.slice(0, 10)) console.log("   " + b);
    } else {
      console.log("✅ 守恒自检：全部订单 货款 = Σ明细金额");
    }
    console.log(CONFIRM_WRITE ? "已写库。" : "dry-run 结束，未写入任何数据。");
  } finally {
    await db.end().catch(() => undefined);
  }
}

main().catch((e) => {
  console.error("同步失败:", e instanceof Error ? e.stack : String(e));
  process.exit(1);
});
