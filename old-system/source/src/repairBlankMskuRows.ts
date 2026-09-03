/**
 * repairBlankMskuRows.ts — 空msku行存量清理（方案B，需求方2026-08-18拍板，批B-7）
 *
 * 背景：saleStat族历史空msku行188行/$6,888（05-01~08-09），源头已于08-13加固止血
 *   （syncLingxingDailyToDb msku兜底+拒写空串），本脚本清历史存量。
 * 规则（fact_sales_daily 与 fact_profit_daily 同规则处理，保族恒等）：
 *   ①双胞胎（同店同item同日存在非空msku行）→ 备份后删除（重复计数铁证42/45行金额全同）；
 *   ②孤行且 dim_product(店铺+item) 唯一反查命中 → UPDATE 补回 msku（sales表连带补sku）；
 *   ③孤行且反查无/歧义 → 备份后删除（需求方拍板：基本为悦斯已删档CS测品，忽略不计）。
 * 铁律合规：删除行先原样存入 <表名>_blankmsku_bak 备份表（显式例外拍板+留档审计）；
 *   dry-run默认零写入；输出受影响日期清单供 <REDACTED_FEISHU_SHEET_ID> 按日幂等重生成。
 * 用法：npx ts-node src/repairBlankMskuRows.ts [--confirm-write]
 */
import "dotenv/config";
import * as mysql from "mysql2/promise";

function getDb(): Promise<mysql.Connection> {
  return mysql.createConnection({
    host: process.env.DB_HOST ?? "127.0.0.1",
    port: Number(process.env.DB_PORT ?? 3306),
    user: process.env.DB_USER ?? "",
    password: process.env.DB_PASSWORD ?? "",
    database: process.env.DB_NAME ?? "walmart_ai_data",
  });
}

const TABLES: Array<{ name: string; dateCol: string; hasSku: boolean }> = [
  { name: "fact_sales_daily", dateCol: "stat_date", hasSku: true },
  { name: "fact_profit_daily", dateCol: "stat_date", hasSku: false },
];

async function main(): Promise<void> {
  const confirmWrite = process.argv.includes("--confirm-write");
  const db = await getDb();
  const summary: Record<string, unknown> = { dryRun: !confirmWrite };
  const affectedDates = new Set<string>();
  try {
    for (const t of TABLES) {
      const bak = `${t.name}_blankmsku_bak`;
      if (confirmWrite) {
        await db.execute(`CREATE TABLE IF NOT EXISTS ${bak} LIKE ${t.name}`);
      }
      const [rows] = await db.execute(
        `SELECT id, store_id, item_id, DATE_FORMAT(${t.dateCol},'%Y-%m-%d') d, sales_amount
         FROM ${t.name} WHERE platform='walmart' AND (msku IS NULL OR msku='')`);
      let twinDel = 0, twinSales = 0, recovered = 0, recoveredSales = 0, unresolvedDel = 0, unresolvedSales = 0, guardSkip = 0;
      for (const r of rows as Array<Record<string, unknown>>) {
        const id = Number(r.id), storeId = String(r.store_id), itemId = String(r.item_id), d = String(r.d);
        const sales = Number(r.sales_amount ?? 0);
        affectedDates.add(d);
        const [tw] = await db.execute(
          `SELECT COUNT(*) c FROM ${t.name}
           WHERE platform='walmart' AND store_id=? AND item_id=? AND ${t.dateCol}=? AND COALESCE(msku,'')<>''`,
          [storeId, itemId, d]);
        const isTwin = Number((tw as Array<Record<string, unknown>>)[0]?.c ?? 0) > 0;
        if (isTwin) {
          twinDel += 1; twinSales += sales;
          if (confirmWrite) {
            await db.execute(`INSERT INTO ${bak} SELECT * FROM ${t.name} WHERE id=?`, [id]);
            await db.execute(`DELETE FROM ${t.name} WHERE id=?`, [id]);
          }
          continue;
        }
        const [dp] = await db.execute(
          `SELECT COALESCE(MAX(NULLIF(TRIM(msku),'')),'') msku, COALESCE(MAX(NULLIF(TRIM(sku),'')),'') sku,
                  COUNT(DISTINCT NULLIF(TRIM(msku),'')) n
           FROM dim_product WHERE platform='walmart' AND store_id=? AND item_id=?`, [storeId, itemId]);
        const dpr = (dp as Array<Record<string, unknown>>)[0] ?? {};
        const msku = String(dpr.msku ?? ""), sku = String(dpr.sku ?? ""), n = Number(dpr.n ?? 0);
        if (n === 1 && msku) {
          // uq碰撞守卫：目标键已有行则按双胞胎处理
          const [col] = await db.execute(
            `SELECT COUNT(*) c FROM ${t.name}
             WHERE platform='walmart' AND store_id=? AND item_id=? AND ${t.dateCol}=? AND msku=?`,
            [storeId, itemId, d, msku]);
          if (Number((col as Array<Record<string, unknown>>)[0]?.c ?? 0) > 0) {
            guardSkip += 1; twinDel += 1; twinSales += sales;
            if (confirmWrite) {
              await db.execute(`INSERT INTO ${bak} SELECT * FROM ${t.name} WHERE id=?`, [id]);
              await db.execute(`DELETE FROM ${t.name} WHERE id=?`, [id]);
            }
            continue;
          }
          recovered += 1; recoveredSales += sales;
          if (confirmWrite) {
            if (t.hasSku && sku) await db.execute(`UPDATE ${t.name} SET msku=?, sku=? WHERE id=?`, [msku, sku, id]);
            else await db.execute(`UPDATE ${t.name} SET msku=? WHERE id=?`, [msku, id]);
          }
        } else {
          unresolvedDel += 1; unresolvedSales += sales;
          if (confirmWrite) {
            await db.execute(`INSERT INTO ${bak} SELECT * FROM ${t.name} WHERE id=?`, [id]);
            await db.execute(`DELETE FROM ${t.name} WHERE id=?`, [id]);
          }
        }
      }
      summary[t.name] = {
        blank_rows: (rows as unknown[]).length,
        twin_deleted: twinDel, twin_sales: Math.round(twinSales * 100) / 100,
        recovered, recovered_sales: Math.round(recoveredSales * 100) / 100,
        unresolved_deleted: unresolvedDel, unresolved_sales: Math.round(unresolvedSales * 100) / 100,
        uq_guard_as_twin: guardSkip,
      };
    }
    summary.affected_dates = Array.from(affectedDates).sort();
    summary.affected_date_cnt = affectedDates.size;
    summary.status = "success";
    console.log("SUMMARY_JSON=" + JSON.stringify(summary));
  } finally {
    await db.end();
  }
}
main().catch((e) => { console.error("FATAL:", e instanceof Error ? e.message : String(e)); process.exit(1); });
