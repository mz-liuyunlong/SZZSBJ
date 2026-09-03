/**
 * syncMpOrderDiscount.ts — 促销折扣同步（订单利润V2·批2，2026-08-18）
 *
 * 数据流：领星 POST /pb/mp/order/v2/list（platform_code=10008 Walmart）
 *   → raw_mp_order_discount（仅折扣≠0商品行，uq platform_order_no+order_item_no 幂等upsert）
 *   → fact_promo_discount_daily（店铺×MSKU×日聚合重算，排除 order_status=7 取消单）
 *   → raw_mp_order_item        （**2026-08-21 新增·全量商品行**，同一次响应，原本被 disc===0 丢弃的全价单不再丢）
 *   → fact_sales_fast_daily    （**2026-08-21 新增**·店铺×MSKU×日 的快速销量/销售额）
 *
 * 2026-08-21 新增部分的由来（需求方逐条拍板，勿擅改）：
 *   · 调价核对**不能用均价**——一天内多笔不同价会被平均掉，调价当天均价既不等于旧价也不等于新价。
 *     只能用订单级成交价，而全库唯一的销售侧订单价字段 item_price_amount 此前只存了折扣行（实测全价行 0 条）。
 *   · 每日销售明细V2 要 T-1：**不动 backfillDailyChain / profit ETL 任何调度**，改由本脚本现算兜底；
 *     权威链路跑到那天后以权威为准，数值波动（取消单/付款失败）需求方已确认可接受。
 *   · 为何不把全价单塞进 raw_mp_order_discount：本文件下方 fact_promo_discount_daily 重算段**没有折扣过滤**，
 *     靠"表里都是折扣行"这个隐含前提；塞入后 discount_orders/discount_qty 会被污染（实测 19:653 ⇒ 订单数膨胀约35倍）。
 *     故两表并存，**raw_mp_order_discount 与其下游逻辑一个字节不动**。
 *
 * 口径（2026-08-18需求方立规·美西日界）：折扣归因=订购日(global_purchase_time)按美西时间
 *   America/Los_Angeles 换算（自动DST，与saleStat族日界同源，禁北京日界——实证YC00097-1C错位教训）；
 *   折扣单独列不改销售额原值；FACT存折扣绝对额(正值)。折扣历史仅能回补31天（接口窗限制）。
 *   store_id 经 storeIdNorm 修复领星数字精度损坏（防御性，同AI财务normStore口径）。
 *
 * 模式：
 *   默认(日拉/cron批4)：date_type=update_time 近2天窗（覆盖迟同步订单），FACT重算窗=本批订单订购日 min~max
 *   回补：--start=YYYY-MM-DD --end=YYYY-MM-DD → date_type=global_purchase_time（≤31天，超窗报错退出）
 * 用法：
 *   npx ts-node src/syncMpOrderDiscount.ts                                        # dry-run 日拉模式
 *   npx ts-node src/syncMpOrderDiscount.ts --confirm-write                        # 真写 日拉模式
 *   npx ts-node src/syncMpOrderDiscount.ts --start=2026-07-18 --end=2026-08-17 --confirm-write  # 31天回补
 * 限速：页间隔1200ms（令牌桶10，从宽），pageSize=200。
 */
import "dotenv/config";
import * as mysql from "mysql2/promise";
import { loadConfig } from "./config";
import { LingxingClient } from "./lingxingClient";
import { laDateTime, laDate, laDayBounds, laToday } from "./usPacific";
import { buildStoreNormalizer } from "./storeIdNorm";

const API_PATH = "/pb/mp/order/v2/list";
const PLATFORM_WALMART = "10008";
const PAGE_SIZE = 200;
const MAX_PAGES = 300;
const STATUS_CANCELLED = 7;
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
/** 金额字符串鲁棒解析：接口金额带币种符号(如 "US$-22.99")，仅保留数字/点/负号 */
function parseAmount(v: unknown): number {
  if (typeof v === "number") return Number.isFinite(v) ? v : 0;
  const s = String(v ?? "").replace(/[^0-9.-]/g, "");
  const n = parseFloat(s);
  return Number.isFinite(n) ? n : 0;
}
// 时区换算统一走 ./usPacific（美西日界，IANA tz 自动DST）

interface OrderItem {
  order_item_no?: unknown; msku?: unknown; quantity?: unknown; discount_amount?: unknown;
  item_price_amount?: unknown; platform_order_no?: unknown; [k: string]: unknown;
}
interface MpOrder {
  store_id?: unknown; global_order_no?: unknown; reference_no?: unknown; status?: unknown;
  amount_currency?: unknown; global_purchase_time?: unknown; item_info?: OrderItem[];
  platform_info?: unknown; [k: string]: unknown;
}

async function main(): Promise<void> {
  const confirmWrite = process.argv.includes("--confirm-write");
  const startArg = getArg("start");
  const endArg = getArg("end");
  const backfill = Boolean(startArg && endArg);
  if ((startArg && !endArg) || (!startArg && endArg)) {
    throw new Error("回补模式需同时提供 --start 与 --end");
  }
  if (backfill) {
    const span = (Date.parse(endArg) - Date.parse(startArg)) / 86400000 + 1;
    if (!(span >= 1 && span <= 31)) throw new Error(`回补窗必须1~31天，当前=${span}天（接口订购时间窗限制）`);
  }
  const cfg = loadConfig();
  const client = new LingxingClient(cfg);
  const db = await getDb();
  const normStore = await buildStoreNormalizer(db);
  let storeNormFixed = 0, storeNormMiss = 0;
  let apiCalls = 0, fetched = 0, discountRows = 0, rawUpserts = 0, factUpserts = 0;
  let cancelledRows = 0, mappedItem = 0, unmapped = 0;
  // 2026-08-21 新增：全量商品行 / 快速销量表 的计数与窗口（与折扣侧完全分开，互不影响）
  let itemRows = 0, itemUpserts = 0, fastUpserts = 0;
  let minIDate = "", maxIDate = "";
  try {
    // ── 拉取窗口 ──
    let dateType: string, startTs: number, endTs: number, windowDesc: string;
    if (backfill) {
      dateType = "global_purchase_time";
      startTs = laDayBounds(startArg).startTs - 1; // 双开区间外扩1秒
      endTs = laDayBounds(endArg).endTs + 1;
      windowDesc = `${startArg}~${endArg}（订购时间回补·美西日界）`;
    } else {
      dateType = "update_time";
      endTs = Math.floor(Date.now() / 1000) + 60;
      startTs = endTs - 2 * 86400;
      windowDesc = "近2天（更新时间日拉）";
    }
    console.log(`窗口 ${windowDesc}｜write=${confirmWrite}`);
    const captureBatch = new Date().toISOString().slice(0, 7);

    const orders: MpOrder[] = [];
    for (let page = 0; page < MAX_PAGES; page++) {
      const resp = await client.request<{ list?: MpOrder[]; total?: unknown }>({
        method: "POST", path: API_PATH,
        params: {
          offset: page * PAGE_SIZE, length: PAGE_SIZE, date_type: dateType,
          start_time: startTs, end_time: endTs, platform_code: [PLATFORM_WALMART],
        },
        timeoutMs: 30000,
      });
      apiCalls += 1;
      const d = resp?.data as { list?: MpOrder[]; total?: unknown } | undefined;
      const list = d?.list ?? [];
      orders.push(...list);
      if (page === 0) console.log(`接口 total=${d?.total ?? "?"}`);
      if (list.length < PAGE_SIZE) break;
      await sleep(1200);
    }
    fetched = orders.length;
    console.log(`拉取订单 ${fetched} 条`);

    // ── RAW upsert（仅折扣≠0商品行；取消单也留RAW带status，FACT侧排除）──
    let minPDate = "", maxPDate = "";
    for (const o of orders) {
      const rawStoreId = String(o.store_id ?? "");
      const normed = normStore(rawStoreId);
      if (normed && normed !== rawStoreId) storeNormFixed += 1;
      if (!normed && rawStoreId) storeNormMiss += 1;
      const storeId = normed ?? rawStoreId;
      const status = Math.round(Number(o.status ?? 0));
      const pts = Math.round(Number(o.global_purchase_time ?? 0));
      if (!pts) continue;
      const pDate = laDate(pts);
      const currency = String(o.amount_currency ?? "");
      for (const it of o.item_info ?? []) {
        const disc = parseAmount(it.discount_amount);
        const pon = String(it.platform_order_no ?? o.reference_no ?? "").trim();
        const oin = String(it.order_item_no ?? "").trim();

        // ── 2026-08-21 新增：全量商品行入 raw_mp_order_item（含全价单）────────────────
        // 位置在 disc===0 的 continue **之前**——原来正是这一句把每天约 653 行全价单丢掉了。
        // 本段与下面的折扣侧完全独立：写另一张表、另一套计数、另一个重算窗，折扣链路行为不变。
        if (pon && oin) {
          itemRows += 1;
          if (!minIDate || pDate < minIDate) minIDate = pDate;
          if (!maxIDate || pDate > maxIDate) maxIDate = pDate;
          if (confirmWrite) {
            await db.execute(
              `INSERT INTO raw_mp_order_item
                 (platform_order_no, order_item_no, global_order_no, store_id, msku, purchase_time, purchase_date,
                  order_status, quantity, item_price_amount, discount_amount, currency, row_json, capture_batch)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON DUPLICATE KEY UPDATE
                 order_status=VALUES(order_status), quantity=VALUES(quantity),
                 item_price_amount=VALUES(item_price_amount), discount_amount=VALUES(discount_amount),
                 store_id=VALUES(store_id), msku=VALUES(msku),
                 purchase_time=VALUES(purchase_time), purchase_date=VALUES(purchase_date),
                 row_json=VALUES(row_json)`,
              [pon, oin, String(o.global_order_no ?? ""), storeId, String(it.msku ?? "").trim(),
               laDateTime(pts), pDate, status, Math.round(Number(it.quantity ?? 0)),
               parseAmount(it.item_price_amount), disc, currency,
               JSON.stringify({ order: { store_id: storeId, status, global_purchase_time: pts, amount_currency: currency }, item: it }),
               captureBatch]);
            itemUpserts += 1;
          }
        }
        // ── 以下为原折扣侧逻辑，一字未改 ────────────────────────────────────────────
        if (disc === 0) continue;
        discountRows += 1;
        if (status === STATUS_CANCELLED) cancelledRows += 1;
        if (!pon || !oin) continue;
        if (!minPDate || pDate < minPDate) minPDate = pDate;
        if (!maxPDate || pDate > maxPDate) maxPDate = pDate;
        if (confirmWrite) {
          await db.execute(
            `INSERT INTO raw_mp_order_discount
               (platform_order_no, order_item_no, global_order_no, store_id, msku, purchase_time, purchase_date,
                order_status, quantity, item_price_amount, discount_amount, currency, row_json, capture_batch)
             VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
             ON DUPLICATE KEY UPDATE
               order_status=VALUES(order_status), quantity=VALUES(quantity),
               item_price_amount=VALUES(item_price_amount), discount_amount=VALUES(discount_amount),
               row_json=VALUES(row_json)`,
            [pon, oin, String(o.global_order_no ?? ""), storeId, String(it.msku ?? "").trim(),
             laDateTime(pts), pDate, status, Math.round(Number(it.quantity ?? 0)),
             parseAmount(it.item_price_amount), disc, currency,
             JSON.stringify({ order: { store_id: storeId, status, global_purchase_time: pts, amount_currency: currency }, item: it }),
             captureBatch]);
          rawUpserts += 1;
        }
      }
    }
    console.log(`折扣商品行 ${discountRows} 条（含取消单 ${cancelledRows} 行，FACT侧排除）`);

    // ── FACT 窗口重算（重算窗=回补窗 or 本批订购日跨度）──
    const factStart = backfill ? startArg : minPDate;
    const factEnd = backfill ? endArg : maxPDate;
    if (factStart && factEnd) {
      const [aggRows] = await db.execute(
        `SELECT store_id, msku, DATE_FORMAT(purchase_date, '%Y-%m-%d') d,
                COUNT(DISTINCT platform_order_no) orders, SUM(quantity) qty, ROUND(SUM(ABS(discount_amount)),2) amt
         FROM raw_mp_order_discount
         WHERE order_status <> ${STATUS_CANCELLED} AND purchase_date BETWEEN ? AND ?
         GROUP BY store_id, msku, DATE_FORMAT(purchase_date, '%Y-%m-%d')`, [factStart, factEnd]);
      for (const a of aggRows as Array<Record<string, unknown>>) {
        const storeId = String(a.store_id), msku = String(a.msku);
        const [dp] = await db.execute(
          `SELECT item_id FROM dim_product
           WHERE platform='walmart' AND store_id=? AND msku=?
           ORDER BY (product_management_status='active') DESC, updated_at DESC LIMIT 1`, [storeId, msku]);
        const itemId = String((dp as Array<Record<string, unknown>>)[0]?.item_id ?? "");
        if (itemId) mappedItem += 1; else unmapped += 1;
        if (confirmWrite) {
          await db.execute(
            `INSERT INTO fact_promo_discount_daily
               (platform, store_id, item_id, msku, discount_date, discount_orders, discount_qty, discount_amount, source_system)
             VALUES ('walmart', ?, ?, ?, ?, ?, ?, ?, 'mp_order_api')
             ON DUPLICATE KEY UPDATE
               item_id=VALUES(item_id), discount_orders=VALUES(discount_orders),
               discount_qty=VALUES(discount_qty), discount_amount=VALUES(discount_amount)`,
            [storeId, itemId, msku, String(a.d), Number(a.orders), Number(a.qty), Number(a.amt)]);
        }
        factUpserts += 1;
      }
    }
    // ── 2026-08-21 新增：fact_sales_fast_daily 重算（T-1 快速销量/销售额）────────────
    //    口径：排除 order_status=7 取消单（与折扣侧 FACT 完全一致）；日界=purchase_date（美西）。
    //    重算窗与折扣侧分开用 minIDate/maxIDate，因为全量行的日期跨度可能比折扣行更宽。
    // ⚠️ 日拉模式必须硬性收窄到「最近 2 个美西日」，不能用本批订单的订购日跨度(minIDate~maxIDate)。
    //   原因：日拉走 date_type=update_time 近2天窗，只保证「最近2天有更新的订单」被拉到；
    //   更早日期里"下单后再没变动过"的订单根本不在本批，按 minIDate 聚合等于把**残缺值**写进 FACT。
    //   2026-08-21 首次上线实测（本缺陷的实证）：
    //     08-14 写成 $18.99 / 真实 $17008.43（-99.89%）；08-15 $17.98 / $16085.82；08-18 $130.43 / $10665.58。
    //   为什么「最近2天」是安全的：cron 挂北京 08:05 = 美西前一日 17:05，48h 更新窗恰好覆盖
    //   laToday(-1) 00:00 起至今（约 41 小时）与 laToday(0) 全程；laToday(-2) 起点在 65 小时前，**不保证**。
    //   更早日期只能由回补模式写——回补走 date_type=global_purchase_time 全量拉，天然完整。
    const fastStart = backfill ? startArg : laToday(-1);
    const fastEnd = backfill ? endArg : laToday(0);
    if (fastStart && fastEnd) {
      const [fastRows] = await db.execute(
        `SELECT store_id, msku, DATE_FORMAT(purchase_date, '%Y-%m-%d') d,
                COUNT(DISTINCT platform_order_no) order_cnt,
                SUM(quantity) qty, ROUND(SUM(item_price_amount), 2) amt
           FROM raw_mp_order_item
          WHERE order_status <> ${STATUS_CANCELLED} AND purchase_date BETWEEN ? AND ?
          GROUP BY store_id, msku, DATE_FORMAT(purchase_date, '%Y-%m-%d')`, [fastStart, fastEnd]);
      for (const a of fastRows as Array<Record<string, unknown>>) {
        const storeId2 = String(a.store_id), msku2 = String(a.msku);
        // item_id 映射口径与 fact_promo_discount_daily 完全一致；未映射写空串，**不写 NULL**
        // （唯一键内 NULL 不去重 —— 2026-08-15 Schema 审计已立此规）
        const [dp2] = await db.execute(
          `SELECT item_id FROM dim_product
            WHERE platform='walmart' AND store_id=? AND msku=?
            ORDER BY (product_management_status='active') DESC, updated_at DESC LIMIT 1`, [storeId2, msku2]);
        const itemId2 = String((dp2 as Array<Record<string, unknown>>)[0]?.item_id ?? "");
        if (confirmWrite) {
          await db.execute(
            `INSERT INTO fact_sales_fast_daily
               (platform, store_id, item_id, msku, stat_date, sales_qty, sales_amount, order_cnt, source_system)
             VALUES ('walmart', ?, ?, ?, ?, ?, ?, ?, 'mp_order_api')
             ON DUPLICATE KEY UPDATE
               item_id=VALUES(item_id), sales_qty=VALUES(sales_qty),
               sales_amount=VALUES(sales_amount), order_cnt=VALUES(order_cnt)`,
            [storeId2, itemId2, msku2, String(a.d), Number(a.qty), Number(a.amt), Number(a.order_cnt)]);
        }
        fastUpserts += 1;
      }
    }

    // ── 2026-08-21 新增：口径观测（只打印、不阻塞、不写库）──────────────────────────
    //    目的：订单聚合 与 saleStat(fact_sales_daily) 的差异率。需求方已确认「重算导致的波动可接受」，
    //    故本段**不作为闸门**；留它是为了万一差异不是几个百分点而是三成——那不是波动，是口径错了。
    if (fastStart && fastEnd) {
      const [cmp] = await db.execute(
        `SELECT d,
                ROUND(SUM(fast_amt), 2) fast_amt, SUM(fast_qty) fast_qty,
                ROUND(SUM(auth_amt), 2) auth_amt, SUM(auth_qty) auth_qty
           FROM (
             SELECT DATE_FORMAT(stat_date, '%Y-%m-%d') d, sales_amount fast_amt, sales_qty fast_qty,
                    0 auth_amt, 0 auth_qty
               FROM fact_sales_fast_daily WHERE stat_date BETWEEN ? AND ?
             UNION ALL
             SELECT DATE_FORMAT(stat_date, '%Y-%m-%d'), 0, 0, sales_amount, sales_qty
               FROM fact_sales_daily WHERE platform='walmart' AND stat_date BETWEEN ? AND ?
           ) t GROUP BY d ORDER BY d`, [fastStart, fastEnd, fastStart, fastEnd]);
      console.log("口径观测 订单聚合(fast) vs saleStat(auth)：");
      console.log(`  ${"日期".padEnd(12)}${"fast金额".padStart(12)}${"auth金额".padStart(12)}${"金额差异".padStart(10)}`
        + `${"fast件".padStart(9)}${"auth件".padStart(9)}${"件数差异".padStart(10)}`);
      for (const r of cmp as Array<Record<string, unknown>>) {
        const fa = Number(r.fast_amt ?? 0), aa = Number(r.auth_amt ?? 0);
        const fq = Number(r.fast_qty ?? 0), aq = Number(r.auth_qty ?? 0);
        const pa = aa === 0 ? "auth无数据" : `${(((fa - aa) / aa) * 100).toFixed(2)}%`;
        const pq = aq === 0 ? "auth无数据" : `${(((fq - aq) / aq) * 100).toFixed(2)}%`;
        console.log(`  ${String(r.d).padEnd(12)}${fa.toFixed(2).padStart(12)}${aa.toFixed(2).padStart(12)}${pa.padStart(10)}`
          + `${String(fq).padStart(9)}${String(aq).padStart(9)}${pq.padStart(10)}`);
      }
      console.log("  说明：auth 为 0 的日期＝权威链路尚未覆盖（正是 fast 表要兜底的那几天），不是异常。");
    }

    console.log(`全量商品行 ${itemRows} 条（其中折扣行 ${discountRows} 条）；fast 聚合 ${fastUpserts} 行`);
    console.log("SUMMARY_JSON=" + JSON.stringify({
      mode: backfill ? "backfill" : "daily", window: windowDesc, dryRun: !confirmWrite,
      apiCalls, fetched, discount_rows: discountRows, cancelled_rows: cancelledRows,
      raw_upserts: rawUpserts, fact_upserts: factUpserts,
      item_rows: itemRows, item_upserts: itemUpserts, fast_upserts: fastUpserts,
      item_window: fastStart && fastEnd ? `${fastStart}~${fastEnd}` : "",
      item_pdate_span: minIDate && maxIDate ? `${minIDate}~${maxIDate}` : "", // 本批订单的订购日跨度（仅供观察，**不再**用作 fast 重算窗）
      item_mapped: mappedItem, item_unmapped: unmapped,
      store_norm_fixed: storeNormFixed, store_norm_miss: storeNormMiss, status: "success",
    }));
  } finally {
    await db.end();
  }
}
main().catch((e) => { console.error("FATAL:", e instanceof Error ? e.message : String(e)); process.exit(1); });
