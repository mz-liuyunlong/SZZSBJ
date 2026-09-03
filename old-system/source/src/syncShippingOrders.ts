/**
 * syncShippingOrders.ts — 平台仓发货单 + 头程分摊明细同步（AI财务 批7b，v2）
 *
 * 链路：领星 queryShippingListPage → raw_lingxing_api（RAW-first）→
 *       fact_shipping_order（分币种真实费用 + 守恒哨兵）+ fact_shipping_first_let（领星成品分摊值）
 *
 * ── v2 相对 v1 的修正（全部来自只读核查实证，2026-08-13）──────────────────────
 * 1) **币种按物流行混用**，不是整单一个币种。实测 SP202604070010001 有 13 条 CNY 行 + 1 条 USD 行；
 *    v1 取"最后一行币种"当整单币种并跨币种直接相加 → 整单费用列存错。
 *    v2 按行分别读 transportation_currency / other_currency，分币种累计到
 *    freight_cny / freight_usd / other_cny / other_usd 四列。
 *    验证：该单美元费用合计 244.05+161.00=405.05，×6.8367 = 2769.20 = alloc_sum 分毫不差。
 * 2) **折算汇率取领星 my_rate 的「上一个月」值**（fact_lingxing_fx_rate）。
 *    依据（2026-08-13 实测反推）：4 月发货单 SP202604070010001 隐含汇率 6.8367 ≈ 2026-03 my_rate 6.8348；
 *    5 月发货单（8 张）隐含 6.8495~6.8572 ≈ 2026-04 my_rate 6.8500。用当月汇率折算会整体偏 1.1%。
 *    缺该月则退同月 rate_org，再缺则不折算、alloc_diff 置 NULL 并列出缺失月份。
 * 3) **cash_date = COALESCE(实际发货日, 发货日)**：接口对多数已发货单不返回 actual_delivery_time
 *    （RAW 实锤 332 已发货中 253 为空），但 delivery_time 全量有值。cash_date 同时是
 *    头程现金记账日（需求方拍板：实际发货日）与成本归集锚日。
 * 4) 守恒哨兵改为 alloc_sum vs (运费 + 其他费用) 的 CNY 等值；实测该口径下越界由 24 张降至 4 张。
 *    **已作废单不参与哨兵**（SP202607100010003 运费 8239.70 但明细 0 行，属正常业务状态）。
 * 5) 补 logistics_provider_id / logistics_channel_id，用于区分
 *    「WFS-FedEx（运费由沃尔玛直扣，领星只录贴标费，运费=0 属正常）」与「海运卡派（运费=0 才是漏录）」。
 * 6) 只取实际费用；expected_transportation_cost / expected_other_cost 全程禁用（实测预估值恒为 0）。
 *
 * 规范：默认 dry-run 零写入；--confirm-write 才写库；RAW 写入失败的批次不写 FACT；
 *       不发送任何飞书消息；不改动任何既有表结构（新列由 sql/057 守卫式补齐）。
 *
 * 运行：
 *   npx ts-node src/syncShippingOrders.ts                  # dry-run
 *   npx ts-node src/syncShippingOrders.ts --pages=3
 *   npx ts-node src/syncShippingOrders.ts --confirm-write
 */

import "dotenv/config";
import * as crypto from "crypto";
import * as mysql from "mysql2/promise";
import { loadConfig } from "./config";
import { LingxingClient } from "./lingxingClient";

const SCRIPT_NAME = "syncShippingOrders";
const API_PATH = "/cepf/warehouse/api/openApi/queryShippingListPage";
const PLATFORM = "walmart";
const PAGE_LENGTH = 50;
const MAX_PAGES_DEFAULT = 40;
const PAGE_DELAY_MS = 900;
const VOID_STATUS = "已作废";

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
/** yyyy-MM 的上一个月（领星摊费用用上月汇率，实测反推） */
function prevMonth(ym: string): string {
  const m = ym.match(/^(\d{4})-(\d{2})$/);
  if (!m) return ym;
  const y = Number(m[1]), mo = Number(m[2]);
  const d = new Date(Date.UTC(y, mo - 2, 1));
  return `${d.getUTCFullYear()}-${String(d.getUTCMonth() + 1).padStart(2, "0")}`;
}
function toDateTime(v: unknown): string | null {
  const t = s(v);
  if (/^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$/.test(t)) return t;
  return /^\d{4}-\d{2}-\d{2}$/.test(t) ? `${t} 00:00:00` : null;
}

interface FirstLet {
  msku?: unknown; sku?: unknown; gtin?: unknown; delivery_num?: unknown; value_source?: unknown;
  purchase_price?: unknown; price?: unknown; aux_stock_price?: unknown;
  per_tax?: unknown; head_stock_price?: unknown; per_first_let_cost?: unknown; wfs_stock_price?: unknown;
}
interface Goods { msku?: unknown; sku?: unknown; shipments_num?: unknown; cargo_code?: unknown; store_id?: unknown }
interface Logi {
  transportation_cost?: unknown; transportation_currency?: unknown;
  other_cost?: unknown; other_currency?: unknown;
}
interface ShipHead {
  shipping_code?: unknown; shipping_status?: unknown; head_fee_type?: unknown;
  warehouse_id?: unknown; logistics_code?: unknown; creator?: unknown; gmt_create?: unknown;
  logistics_provider_id?: unknown; logistics_channel_id?: unknown;
  delivery_time?: unknown; actual_delivery_time?: unknown; sail_time?: unknown;
  expected_arrival_time?: unknown; arrival_time?: unknown;
  shipping_logistics?: Logi[]; shipping_goods?: Goods[]; shipping_first_lets?: FirstLet[];
}

function unwrapRecords(resp: unknown): ShipHead[] {
  const r = resp as Record<string, unknown> | undefined;
  const d1 = r?.data as Record<string, unknown> | undefined;
  const d2 = d1?.data as Record<string, unknown> | undefined;
  for (const v of [d2?.records, d2?.list, d1?.records, d1?.list, d1?.data]) {
    if (Array.isArray(v)) return v as ShipHead[];
  }
  return [];
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

/** 领星汇率表：month -> {my, org}；USD→CNY */
async function loadFxRates(db: mysql.Connection): Promise<Map<string, { my: number; org: number }>> {
  const out = new Map<string, { my: number; org: number }>();
  try {
    const [rows] = await db.query<mysql.RowDataPacket[]>(
      `SELECT rate_month, my_rate, rate_org FROM fact_lingxing_fx_rate WHERE currency_code='USD'`);
    for (const r of rows) out.set(s(r.rate_month), { my: num(r.my_rate), org: num(r.rate_org) });
  } catch { /* 表不存在时留空，后续 alloc_diff 置 NULL 并计数 */ }
  return out;
}

async function loadItemIdMap(db: mysql.Connection, pairs: Array<{ store: string; msku: string }>): Promise<Map<string, string>> {
  const out = new Map<string, string>();
  const stores = Array.from(new Set(pairs.map((p) => p.store).filter(Boolean)));
  const mskus = Array.from(new Set(pairs.map((p) => p.msku).filter(Boolean)));
  if (!stores.length || !mskus.length) return out;
  const [rows] = await db.query<mysql.RowDataPacket[]>(
    `SELECT store_id, msku, item_id FROM dim_product
      WHERE platform=? AND store_id IN (${stores.map(() => "?").join(",")})
        AND msku IN (${mskus.map(() => "?").join(",")})
      GROUP BY store_id, msku, item_id`,
    [PLATFORM, ...stores, ...mskus],
  );
  const acc = new Map<string, Set<string>>();
  for (const r of rows) {
    const k = `${s(r.store_id)}||${s(r.msku)}`;
    if (!acc.has(k)) acc.set(k, new Set());
    acc.get(k)!.add(s(r.item_id));
  }
  for (const [k, v] of acc.entries()) if (v.size === 1) out.set(k, Array.from(v)[0]);
  return out;
}

async function main(): Promise<void> {
  const maxPages = Number(getArg("pages", String(MAX_PAGES_DEFAULT))) || MAX_PAGES_DEFAULT;
  const sids = getArg("sids", "");

  console.log("=".repeat(64));
  console.log(`平台仓发货单同步 v2 ${CONFIRM_WRITE ? "[confirm-write 写库]" : "[dry-run 零写入]"}`);
  console.log(`接口=${API_PATH} | 每页=${PAGE_LENGTH} | 最多${maxPages}页 | sids=${sids || "(全部)"}`);
  console.log("费用口径：只取实际费用，按物流行分币种累计；美元折算用领星【上一个月】my_rate（缺则退官方汇率）");
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

  const fx = await loadFxRates(db);
  console.log(`领星汇率(USD)：已加载 ${fx.size} 个月`);

  const sum = {
    pages: 0, orders: 0, headUpserts: 0, letRows: 0, letUpserts: 0,
    matched: 0, ambiguous: 0, unmatched: 0, voided: 0,
    usdOrders: 0, noRateMonths: new Set<string>(), noCashDate: [] as string[],
    breach: [] as string[], cnyTotal: 0, usdTotal: 0, allocTotal: 0,
  };

  try {
    for (let page = 1; page <= maxPages; page++) {
      const params: Record<string, unknown> = { offset: (page - 1) * PAGE_LENGTH, length: PAGE_LENGTH };
      if (sids) params.sids = sids;
      const resp = await client.post<unknown>(API_PATH, params);
      const list = unwrapRecords(resp);
      sum.pages += 1;
      console.log(`  第${page}页: ${list.length} 单`);
      if (!list.length) break;

      let rawId = 0;
      if (CONFIRM_WRITE) rawId = await insertRaw(db, { api: API_PATH, ...params }, resp, page);

      const pairs: Array<{ store: string; msku: string }> = [];
      for (const h of list) for (const g of h.shipping_goods ?? []) pairs.push({ store: s(g.store_id), msku: s(g.msku) });
      const itemIdMap = CONFIRM_WRITE ? await loadItemIdMap(db, pairs) : new Map<string, string>();

      for (const h of list) {
        const code = s(h.shipping_code);
        if (!code) continue;
        sum.orders += 1;
        const status = s(h.shipping_status);
        const isVoid = status === VOID_STATUS;
        if (isVoid) sum.voided += 1;

        // ① 分币种累计（只取实际费用；expected_* 禁用）
        let fCny = 0, fUsd = 0, oCny = 0, oUsd = 0;
        for (const l of h.shipping_logistics ?? []) {
          const tc = num(l.transportation_cost), oc = num(l.other_cost);
          const tcur = (s(l.transportation_currency) || "CNY").toUpperCase();
          const ocur = (s(l.other_currency) || "CNY").toUpperCase();
          if (tcur === "USD") fUsd += tc; else fCny += tc;
          if (ocur === "USD") oUsd += oc; else oCny += oc;
        }
        fCny = r4(fCny); fUsd = r4(fUsd); oCny = r4(oCny); oUsd = r4(oUsd);
        if (fUsd + oUsd > 0) sum.usdOrders += 1;

        // ② 归集/记账锚日
        const cashDate = toDate(h.actual_delivery_time) ?? toDate(h.delivery_time);
        if (!cashDate) sum.noCashDate.push(code);

        // ③ 折算汇率：取【上一个月】的领星 my_rate（实测领星即按此折算），缺则退同月 rate_org
        const fxMonth = cashDate ? prevMonth(cashDate.slice(0, 7)) : "";
        const fxRow = fx.get(fxMonth);
        const rate = fxRow ? (fxRow.my > 0 ? fxRow.my : fxRow.org) : 0;
        if (fUsd + oUsd > 0 && rate <= 0) sum.noRateMonths.add(fxMonth || "(无日期)");

        const usdSum = r4(fUsd + oUsd);
        const cnySum = r4(fCny + oCny);
        const canConvert = usdSum === 0 || rate > 0;
        const freightCnyEq = usdSum === 0 ? fCny : r4(fCny + fUsd * rate);
        const otherCnyEq = usdSum === 0 ? oCny : r4(oCny + oUsd * rate);

        // ④ 货件反查索引
        const idx = new Map<string, Array<{ cargo: string; store: string; sku: string }>>();
        for (const g of h.shipping_goods ?? []) {
          const k = `${s(g.msku)}||${Math.round(num(g.shipments_num))}`;
          if (!idx.has(k)) idx.set(k, []);
          idx.get(k)!.push({ cargo: s(g.cargo_code), store: s(g.store_id), sku: s(g.sku) });
        }

        const lets = h.shipping_first_lets ?? [];
        let allocSum = 0, unmatchedRows = 0;
        interface LetRow {
          store: string; cargo: string; msku: string; sku: string; gtin: string; itemId: string;
          qty: number; src: string; pp: number; op: number; aux: number; tax: number;
          hsp: number; pfl: number; wsp: number; status: string;
        }
        const rows: LetRow[] = [];

        for (const fl of lets) {
          const msku = s(fl.msku);
          const qty = Math.round(num(fl.delivery_num));
          const pfl = num(fl.per_first_let_cost);
          allocSum += pfl * qty;
          sum.letRows += 1;

          const hits = idx.get(`${msku}||${qty}`) ?? [];
          const cargos = Array.from(new Set(hits.map((x) => x.cargo)));
          let mstatus = "unmatched", cargo = "", store = "", skuG = "";
          if (cargos.length === 1) {
            mstatus = "matched"; cargo = cargos[0]; store = hits[0].store; skuG = hits[0].sku; sum.matched += 1;
          } else if (cargos.length > 1) {
            mstatus = "ambiguous"; unmatchedRows += 1; sum.ambiguous += 1;
          } else {
            unmatchedRows += 1; sum.unmatched += 1;
          }

          rows.push({
            store, cargo, msku, sku: s(fl.sku) || skuG, gtin: s(fl.gtin),
            itemId: itemIdMap.get(`${store}||${msku}`) ?? "",
            qty, src: s(fl.value_source),
            pp: num(fl.purchase_price), op: num(fl.price), aux: num(fl.aux_stock_price),
            tax: num(fl.per_tax), hsp: num(fl.head_stock_price), pfl, wsp: num(fl.wfs_stock_price),
            status: mstatus,
          });
        }
        allocSum = r4(allocSum);

        // ⑤ 守恒哨兵：作废单不参与；无法折算的记 NULL
        const feeCnyEq = r4(freightCnyEq + otherCnyEq);
        const diff = canConvert ? r4(allocSum - feeCnyEq) : null;
        const impliedRate = cnySum === 0 && usdSum > 0 ? r4(allocSum / usdSum) : null;
        if (!isVoid && canConvert && feeCnyEq > 0) {
          // 阈值：人民币单 1%；含美元费用的单 2%——领星同月内取汇率时点不统一（实测同为5月单，
          // 部分按上月 6.85、部分按当月 6.78 折算，噪音 ±1.2%），成本取领星成品值不受影响，
          // 哨兵只拦真正的错账（>2%）。
          const tol = Math.max(1.0, feeCnyEq * (usdSum > 0 ? 0.02 : 0.01));
          if (Math.abs(diff as number) > tol) {
            sum.breach.push(`${code}[${status}]: 分摊Σ${allocSum} vs 费用CNY等值${feeCnyEq}（CNY ${cnySum} + USD ${usdSum}×${rate}），差${diff}，阈值±${r4(tol)}`);
          }
        }
        sum.cnyTotal = r4(sum.cnyTotal + cnySum);
        sum.usdTotal = r4(sum.usdTotal + usdSum);
        sum.allocTotal = r4(sum.allocTotal + allocSum);

        if (!CONFIRM_WRITE) continue;

        await db.query(
          `INSERT INTO fact_shipping_order
             (platform, shipping_code, shipping_status, head_fee_type, warehouse_id, logistics_code,
              logistics_provider_id, logistics_channel_id, creator,
              gmt_create, delivery_time, actual_delivery_time, cash_date, sail_time, expected_arrival_time, arrival_time,
              transportation_cost, freight_cny, freight_usd, other_cost, other_cny, other_usd, currency_code,
              alloc_sum, alloc_diff, implied_rate, first_let_rows, unmatched_rows, source_raw_id)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
           ON DUPLICATE KEY UPDATE
             shipping_status=VALUES(shipping_status), head_fee_type=VALUES(head_fee_type),
             warehouse_id=VALUES(warehouse_id), logistics_code=VALUES(logistics_code),
             logistics_provider_id=VALUES(logistics_provider_id), logistics_channel_id=VALUES(logistics_channel_id),
             creator=VALUES(creator), gmt_create=VALUES(gmt_create), delivery_time=VALUES(delivery_time),
             actual_delivery_time=VALUES(actual_delivery_time), cash_date=VALUES(cash_date),
             sail_time=VALUES(sail_time), expected_arrival_time=VALUES(expected_arrival_time),
             arrival_time=VALUES(arrival_time),
             transportation_cost=VALUES(transportation_cost), freight_cny=VALUES(freight_cny),
             freight_usd=VALUES(freight_usd), other_cost=VALUES(other_cost),
             other_cny=VALUES(other_cny), other_usd=VALUES(other_usd), currency_code=VALUES(currency_code),
             alloc_sum=VALUES(alloc_sum), alloc_diff=VALUES(alloc_diff), implied_rate=VALUES(implied_rate),
             first_let_rows=VALUES(first_let_rows), unmatched_rows=VALUES(unmatched_rows),
             source_raw_id=VALUES(source_raw_id), updated_at=NOW()`,
          [PLATFORM, code, status, s(h.head_fee_type), s(h.warehouse_id), s(h.logistics_code),
           s(h.logistics_provider_id), s(h.logistics_channel_id), s(h.creator),
           toDateTime(h.gmt_create), toDate(h.delivery_time), toDate(h.actual_delivery_time), cashDate,
           toDate(h.sail_time), toDate(h.expected_arrival_time), toDate(h.arrival_time),
           freightCnyEq, fCny, fUsd, otherCnyEq, oCny, oUsd, usdSum > 0 && cnySum === 0 ? "USD" : "CNY",
           allocSum, diff, impliedRate, lets.length, unmatchedRows, rawId],
        );
        sum.headUpserts += 1;

        for (const r of rows) {
          await db.query(
            `INSERT INTO fact_shipping_first_let
               (platform, shipping_code, store_id, cargo_code, msku, sku, gtin, item_id, delivery_num,
                value_source, purchase_price, outbound_price, aux_stock_price, per_tax, head_stock_price,
                per_first_let_cost, wfs_stock_price, currency_code, match_status,
                actual_delivery_time, cash_date, source_raw_id)
             VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
             ON DUPLICATE KEY UPDATE
               store_id=VALUES(store_id), sku=VALUES(sku), gtin=VALUES(gtin),
               item_id=IF(VALUES(item_id)='', item_id, VALUES(item_id)),
               value_source=VALUES(value_source), purchase_price=VALUES(purchase_price),
               outbound_price=VALUES(outbound_price), aux_stock_price=VALUES(aux_stock_price),
               per_tax=VALUES(per_tax), head_stock_price=VALUES(head_stock_price),
               per_first_let_cost=VALUES(per_first_let_cost), wfs_stock_price=VALUES(wfs_stock_price),
               currency_code=VALUES(currency_code), match_status=VALUES(match_status),
               actual_delivery_time=VALUES(actual_delivery_time), cash_date=VALUES(cash_date),
               source_raw_id=VALUES(source_raw_id), updated_at=NOW()`,
            [PLATFORM, code, r.store, r.cargo, r.msku, r.sku, r.gtin, r.itemId, r.qty, r.src,
             r.pp, r.op, r.aux, r.tax, r.hsp, r.pfl, r.wsp, "CNY", r.status,
             toDate(h.actual_delivery_time), cashDate, rawId],
          );
          sum.letUpserts += 1;
        }
      }

      if (list.length < PAGE_LENGTH) break;
      await sleep(PAGE_DELAY_MS);
    }

    console.log("\n" + "=".repeat(64));
    console.log(`发货单 ${sum.orders} 张（其中已作废 ${sum.voided}，头 upsert ${sum.headUpserts}）`);
    console.log(`头程明细行 ${sum.letRows}（upsert ${sum.letUpserts}）`);
    console.log(`货件反查：唯一命中 ${sum.matched} / 多命中歧义 ${sum.ambiguous} / 无命中 ${sum.unmatched}`);
    console.log(`费用合计：人民币 ¥${sum.cnyTotal} ＋ 美元 $${sum.usdTotal}（含美元费用的单 ${sum.usdOrders} 张）`);
    console.log(`按品分摊回加总 ¥${sum.allocTotal}`);
    if (sum.noCashDate.length) {
      console.log(`⚠️ 无归集锚日(实际发货日与发货日都缺) ${sum.noCashDate.length} 张: ${sum.noCashDate.slice(0, 10).join(", ")}${sum.noCashDate.length > 10 ? " …" : ""}`);
    }
    if (sum.noRateMonths.size) {
      console.log(`⚠️ 缺汇率月份（按上月口径查 fact_lingxing_fx_rate 无该月）：${Array.from(sum.noRateMonths).join(", ")} → 这些单 alloc_diff 置 NULL，请先补跑 syncLingxingFxRate`);
    }
    if (sum.breach.length) {
      console.log(`⚠️ 守恒哨兵越界 ${sum.breach.length} 张（阈值 CNY单1% / 含美元单2%，下限¥1，已排除作废单）:`);
      for (const b of sum.breach.slice(0, 20)) console.log("   " + b);
    } else {
      console.log("✅ 守恒哨兵：全部在阈值内（作废单已排除）");
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
