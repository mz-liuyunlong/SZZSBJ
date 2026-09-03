/**
 * repairV2TimezoneAndStore.ts — V2数据链一次性修复（2026-08-18 整改批A）
 *
 * 修复两件事（探测已实证）：
 *   ① 店铺id精度损坏：退货链5个孤儿store_id共572行（…845060→…845056 等，末4位差≤16），
 *      normStore就近映射修复 RAW+FACT 的 store_id 提取列；row_json 接口原文一字不动（RAW留存铁律）。
 *   ② 折扣链日界切美西：purchase_time/purchase_date 由北京时间改为美西时间
 *      （从 row_json.order.global_purchase_time unix原值重算，IANA tz 自动DST），FACT按美西日重建。
 *   退货链日界零改动（售后接口已实证返回美西站点时间）。
 *
 * FACT重建方式（守"不清空数据表"铁律）：全量重算upsert + 精准DELETE不在新键集的残留行（逐行报告），
 *   不用 TRUNCATE/无条件DELETE。
 * 验收锚点：YC00097-1C 折扣应变为 08-10=115.96 / 08-11=28.99；fact_refund_daily item_unmapped 572→约0。
 * 用法：npx ts-node src/repairV2TimezoneAndStore.ts [--confirm-write]   # 默认dry-run零写入
 */
import "dotenv/config";
import * as mysql from "mysql2/promise";
import { laDateTime, laDate } from "./usPacific";
import { buildStoreNormalizer } from "./storeIdNorm";

function getDb(): Promise<mysql.Connection> {
  return mysql.createConnection({
    host: process.env.DB_HOST ?? "127.0.0.1",
    port: Number(process.env.DB_PORT ?? 3306),
    user: process.env.DB_USER ?? "",
    password: process.env.DB_PASSWORD ?? "",
    database: process.env.DB_NAME ?? "walmart_ai_data",
  });
}

async function main(): Promise<void> {
  const confirmWrite = process.argv.includes("--confirm-write");
  const db = await getDb();
  const S: Record<string, number | string> = { dryRun: String(!confirmWrite) };
  try {
    const norm = await buildStoreNormalizer(db);

    // ── ①a 退货RAW 店铺id修复 ──
    const [orph] = await db.execute(
      `SELECT DISTINCT store_id FROM raw_walmart_return_order
       WHERE store_id NOT IN (SELECT store_id FROM dim_store WHERE platform='walmart')`);
    const pairs: Array<[string, string]> = [];
    for (const r of orph as Array<Record<string, unknown>>) {
      const bad = String(r.store_id);
      const good = norm(bad);
      if (!good) { console.log(`WARN 无法映射: ${bad}（保留原值）`); continue; }
      pairs.push([bad, good]);
    }
    console.log("映射对: " + pairs.map(([b, g]) => `${b}→${g}`).join(" | "));
    let rawFixed = 0, factFixed = 0;
    for (const [bad, good] of pairs) {
      // FACT uq 碰撞守卫：目标键已存在则中止（探测预期=0）
      const [col] = await db.execute(
        `SELECT COUNT(*) c FROM fact_refund_daily a
         JOIN fact_refund_daily b ON b.platform=a.platform AND b.msku=a.msku AND b.refund_date=a.refund_date
         WHERE a.store_id=? AND b.store_id=?`, [bad, good]);
      if (Number((col as Array<Record<string, unknown>>)[0]?.c ?? 0) > 0) {
        throw new Error(`FACT键碰撞: ${bad}→${good}，中止`);
      }
      if (confirmWrite) {
        const [r1] = await db.execute(`UPDATE raw_walmart_return_order SET store_id=? WHERE store_id=?`, [good, bad]);
        const [r2] = await db.execute(`UPDATE fact_refund_daily SET store_id=? WHERE store_id=?`, [good, bad]);
        rawFixed += Number((r1 as unknown as { affectedRows?: number }).affectedRows ?? 0);
        factFixed += Number((r2 as unknown as { affectedRows?: number }).affectedRows ?? 0);
      } else {
        const [c1] = await db.execute(`SELECT COUNT(*) c FROM raw_walmart_return_order WHERE store_id=?`, [bad]);
        const [c2] = await db.execute(`SELECT COUNT(*) c FROM fact_refund_daily WHERE store_id=?`, [bad]);
        rawFixed += Number((c1 as Array<Record<string, unknown>>)[0]?.c ?? 0);
        factFixed += Number((c2 as Array<Record<string, unknown>>)[0]?.c ?? 0);
      }
    }
    S.refund_store_pairs = pairs.length; S.refund_raw_fixed = rawFixed; S.refund_fact_fixed = factFixed;

    // ── ①b 退货FACT item_id 回填（店铺修复后全量重算upsert；退货日界不变无残留键）──
    let refundItemFilled = 0, refundUnmapped = 0;
    const [ragg] = await db.execute(
      `SELECT store_id, msku, DATE_FORMAT(return_order_date,'%Y-%m-%d') d,
              COUNT(DISTINCT return_order_id) orders, SUM(quantity) qty, ROUND(SUM(line_total_amount),2) amt
       FROM raw_walmart_return_order
       WHERE return_type='REFUND' AND return_order_date IS NOT NULL
       GROUP BY store_id, msku, DATE_FORMAT(return_order_date,'%Y-%m-%d')`);
    for (const a of ragg as Array<Record<string, unknown>>) {
      const storeId = String(a.store_id), msku = String(a.msku);
      const [dp] = await db.execute(
        `SELECT item_id FROM dim_product WHERE platform='walmart' AND store_id=? AND msku=?
         ORDER BY (product_management_status='active') DESC, updated_at DESC LIMIT 1`, [storeId, msku]);
      const itemId = String((dp as Array<Record<string, unknown>>)[0]?.item_id ?? "");
      if (itemId) refundItemFilled += 1; else refundUnmapped += 1;
      if (confirmWrite) {
        await db.execute(
          `INSERT INTO fact_refund_daily
             (platform, store_id, item_id, msku, refund_date, refund_orders, refund_qty, refund_amount, source_system)
           VALUES ('walmart', ?, ?, ?, ?, ?, ?, ?, 'walmart_return_api')
           ON DUPLICATE KEY UPDATE item_id=VALUES(item_id), refund_orders=VALUES(refund_orders),
             refund_qty=VALUES(refund_qty), refund_amount=VALUES(refund_amount)`,
          [storeId, itemId, msku, String(a.d), Number(a.orders), Number(a.qty), Number(a.amt)]);
      }
    }
    S.refund_fact_groups = (ragg as unknown[]).length;
    S.refund_item_mapped = refundItemFilled; S.refund_item_unmapped = refundUnmapped;

    // ── ②a 折扣RAW 时区重算（unix原值→美西）＋店铺id防御性修复 ──
    const [prows] = await db.execute(
      `SELECT id, store_id, DATE_FORMAT(purchase_date,'%Y-%m-%d') pd,
              CAST(JSON_UNQUOTE(JSON_EXTRACT(row_json,'$.order.global_purchase_time')) AS UNSIGNED) pts
       FROM raw_mp_order_discount`);
    let tzFixed = 0, tzSame = 0, promoStoreFixed = 0, ptsMissing = 0;
    for (const r of prows as Array<Record<string, unknown>>) {
      const pts = Number(r.pts ?? 0);
      if (!pts) { ptsMissing += 1; continue; }
      const laDT = laDateTime(pts), laD = laDate(pts);
      const curD = String(r.pd ?? "").slice(0, 10); // SQL侧DATE_FORMAT直出，禁JS侧Date截断（批1教训）
      const good = norm(String(r.store_id));
      const needStore = good !== null && good !== String(r.store_id);
      if (needStore) promoStoreFixed += 1;
      if (laD !== curD || needStore) {
        tzFixed += 1;
        if (confirmWrite) {
          const vals: mysql.ExecuteValues = [laDT, laD, needStore ? good : String(r.store_id), Number(r.id)];
          await db.execute(`UPDATE raw_mp_order_discount SET purchase_time=?, purchase_date=?, store_id=? WHERE id=?`,
            vals);
        }
      } else {
        tzSame += 1;
        if (confirmWrite) {
          const vals: mysql.ExecuteValues = [laDT, Number(r.id)];
          await db.execute(`UPDATE raw_mp_order_discount SET purchase_time=? WHERE id=?`, vals);
        }
      }
    }
    S.promo_rows = (prows as unknown[]).length; S.promo_date_changed = tzFixed;
    S.promo_date_same = tzSame; S.promo_pts_missing = ptsMissing; S.promo_store_fixed = promoStoreFixed;

    // ── ②b 折扣FACT 按美西日全量重建（upsert新键集 + 精准DELETE残留键）──
    let promoFactUpserts = 0, promoMapped = 0, promoUnmapped = 0, promoStale = 0;
    if (confirmWrite || true) {
      const [pagg] = await db.execute(
        `SELECT store_id, msku, DATE_FORMAT(purchase_date,'%Y-%m-%d') d,
                COUNT(DISTINCT platform_order_no) orders, SUM(quantity) qty, ROUND(SUM(ABS(discount_amount)),2) amt
         FROM raw_mp_order_discount WHERE order_status <> 7 AND purchase_date IS NOT NULL
         GROUP BY store_id, msku, DATE_FORMAT(purchase_date,'%Y-%m-%d')`);
      const newKeys = new Set<string>();
      for (const a of pagg as Array<Record<string, unknown>>) {
        const storeId = String(a.store_id), msku = String(a.msku), d = String(a.d);
        newKeys.add(`${storeId}||${msku}||${d}`);
        const [dp] = await db.execute(
          `SELECT item_id FROM dim_product WHERE platform='walmart' AND store_id=? AND msku=?
           ORDER BY (product_management_status='active') DESC, updated_at DESC LIMIT 1`, [storeId, msku]);
        const itemId = String((dp as Array<Record<string, unknown>>)[0]?.item_id ?? "");
        if (itemId) promoMapped += 1; else promoUnmapped += 1;
        if (confirmWrite) {
          await db.execute(
            `INSERT INTO fact_promo_discount_daily
               (platform, store_id, item_id, msku, discount_date, discount_orders, discount_qty, discount_amount, source_system)
             VALUES ('walmart', ?, ?, ?, ?, ?, ?, ?, 'mp_order_api')
             ON DUPLICATE KEY UPDATE item_id=VALUES(item_id), discount_orders=VALUES(discount_orders),
               discount_qty=VALUES(discount_qty), discount_amount=VALUES(discount_amount)`,
            [storeId, itemId, msku, d, Number(a.orders), Number(a.qty), Number(a.amt)]);
        }
        promoFactUpserts += 1;
      }
      const [exist] = await db.execute(
        `SELECT id, store_id, msku, DATE_FORMAT(discount_date,'%Y-%m-%d') d FROM fact_promo_discount_daily`);
      for (const e of exist as Array<Record<string, unknown>>) {
        const k = `${e.store_id}||${e.msku}||${e.d}`;
        if (!newKeys.has(k)) {
          promoStale += 1;
          console.log(`残留键将删除: ${k}`);
          if (confirmWrite) {
            const vals: mysql.ExecuteValues = [Number(e.id)];
            await db.execute(`DELETE FROM fact_promo_discount_daily WHERE id=?`, vals);
          }
        }
      }
    }
    S.promo_fact_upserts = promoFactUpserts; S.promo_item_mapped = promoMapped;
    S.promo_item_unmapped = promoUnmapped; S.promo_fact_stale_deleted = promoStale;
    console.log("SUMMARY_JSON=" + JSON.stringify({ ...S, status: "success" }));
  } finally {
    await db.end();
  }
}
main().catch((e) => { console.error("FATAL:", e instanceof Error ? e.message : String(e)); process.exit(1); });
