/**
 * reportV2Reconcile.ts — 订单利润 新旧Tab对账报告（批4d，2026-08-19）
 *
 * 只读生成近N个业务日的逐日对账表（默认7天），落盘 reports/v2_reconcile_<日期>.md 并打印。
 * 口径：
 *   Beta毛利(旧) = fact_profit_daily.gross_profit 合计（分全量/非CS两列，Beta页含CS）
 *   V2订单利润 = 非CS口径：净销售额 − 广告(权威表全类型) − WFS配送费 − 佣金 − 采购 − 头程 − 退款 − 仓储日摊
 *   恒等自检 = V2订单利润 −（旧毛利非CS − 折扣 − 退款 − 仓储 − 广告增量）≈ 0（佣金费率同参时成立）
 *   广告增量 = 权威表全类型(剔CS品) − 利润FACT旧口径ad_spend(非CS) ＝ SEM/SB/SV补进的部分
 * 用法：npx ts-node src/reportV2Reconcile.ts [--days=7]
 */
import "dotenv/config";
import * as fs from "fs";
import * as mysql from "mysql2/promise";

function getDb(): Promise<mysql.Connection> {
  return mysql.createConnection({
    host: process.env.DB_HOST ?? "127.0.0.1",
    port: Number(process.env.DB_PORT ?? 3306),
    user: process.env.DB_USER ?? "",
    password: process.env.DB_PASSWORD ?? "",
    database: process.env.DB_NAME ?? "walmart_ai_data",
    dateStrings: true,
  });
}
const r2 = (v: number): number => Math.round(v * 100) / 100;
const commissionRate = (storeName: string): number =>
  (storeName.includes("CN2501") || storeName.includes("CN2502")) ? 0.15 : 0.12;

async function main(): Promise<void> {
  const daysArg = process.argv.find((a) => a.startsWith("--days="));
  const days = Math.min(31, Math.max(1, Number(daysArg?.split("=")[1] ?? 7)));
  const db = await getDb();
  try {
    const [dRows] = await db.execute(
      `SELECT DISTINCT DATE_FORMAT(stat_date,'%Y-%m-%d') d FROM fact_profit_daily
       WHERE platform='walmart' ORDER BY d DESC LIMIT ${days}`);
    const dates = (dRows as Array<Record<string, unknown>>).map((r) => String(r.d)).reverse();
    const lines: string[] = [];
    lines.push(`# 订单利润 新旧Tab对账报告`);
    lines.push(``);
    lines.push(`> 生成口径：Beta=旧毛利(fact_profit_daily.gross_profit)；V2=非CS、含折扣/退款/仓储/权威表广告。`);
    lines.push(`> 领星三方对数：请需求方在领星「销量统计」对同日销售额抽查（saleStat同源应逐分一致）。`);
    lines.push(``);
    lines.push(`| 业务日 | 销售额全量 | 销售额非CS | 促销折扣 | 退款额 | 仓储日摊 | 广告旧口径 | 广告权威表 | 广告增量 | Beta毛利全量 | Beta毛利非CS | V2订单利润 | 恒等自检差 |`);
    lines.push(`|---|---|---|---|---|---|---|---|---|---|---|---|---|`);
    for (const d of dates) {
      const [b] = await db.execute(
        `SELECT ROUND(SUM(sales_amount),2) sales_all, ROUND(SUM(gross_profit),2) gp_all,
                ROUND(SUM(CASE WHEN msku NOT LIKE 'CS%' THEN sales_amount ELSE 0 END),2) sales_nc,
                ROUND(SUM(CASE WHEN msku NOT LIKE 'CS%' THEN gross_profit ELSE 0 END),2) gp_nc,
                ROUND(SUM(CASE WHEN msku NOT LIKE 'CS%' THEN ad_spend ELSE 0 END),2) ad_old,
                ROUND(SUM(CASE WHEN msku NOT LIKE 'CS%' THEN
                  CAST(JSON_UNQUOTE(JSON_EXTRACT(extra_json,'$.wfs_fee_usd')) AS DECIMAL(12,4))
                  * CAST(JSON_UNQUOTE(JSON_EXTRACT(extra_json,'$.sales_qty')) AS DECIMAL(12,2)) ELSE 0 END),2) wfs,
                ROUND(SUM(CASE WHEN msku NOT LIKE 'CS%' THEN
                  (CAST(JSON_UNQUOTE(JSON_EXTRACT(extra_json,'$.purchase_cost_cny')) AS DECIMAL(12,2))
                  + CAST(JSON_UNQUOTE(JSON_EXTRACT(extra_json,'$.first_leg_cost_cny')) AS DECIMAL(12,2)))
                  * CAST(JSON_UNQUOTE(JSON_EXTRACT(extra_json,'$.sales_qty')) AS DECIMAL(12,2)) ELSE 0 END)/6.6,2) leg,
                ROUND(SUM(CASE WHEN msku NOT LIKE 'CS%' AND (store_name LIKE '%CN2501%' OR store_name LIKE '%CN2502%')
                  THEN sales_amount*0.15 WHEN msku NOT LIKE 'CS%' THEN sales_amount*0.12 ELSE 0 END),2) comm
         FROM fact_profit_daily WHERE platform='walmart' AND stat_date=?`, [d]);
      const bb = (b as Array<Record<string, unknown>>)[0] ?? {};
      const [ad] = await db.execute(
        `SELECT ROUND(SUM(a.ad_spend),2) ad_new FROM fact_ads_product_daily a
         WHERE a.platform='walmart' AND a.stat_date=?
           AND NOT EXISTS (SELECT 1 FROM dim_product dp
             WHERE dp.platform='walmart' AND dp.store_id=a.store_id AND dp.item_id=a.item_id
             GROUP BY dp.store_id HAVING SUM(CASE WHEN dp.msku NOT LIKE 'CS%' THEN 1 ELSE 0 END)=0)`, [d]);
      const adNew = Number((ad as Array<Record<string, unknown>>)[0]?.ad_new ?? 0);
      const [pr] = await db.execute(
        `SELECT ROUND(SUM(discount_amount),2) v FROM fact_promo_discount_daily
         WHERE platform='walmart' AND discount_date=? AND msku NOT LIKE 'CS%'`, [d]);
      const disc = Number((pr as Array<Record<string, unknown>>)[0]?.v ?? 0);
      const [rf] = await db.execute(
        `SELECT ROUND(SUM(refund_amount),2) v FROM fact_refund_daily
         WHERE platform='walmart' AND refund_date=? AND msku NOT LIKE 'CS%'`, [d]);
      const refund = Number((rf as Array<Record<string, unknown>>)[0]?.v ?? 0);
      const [st] = await db.execute(
        `SELECT ROUND(SUM(storage_fee),2) v FROM fact_storage_fee_daily
         WHERE platform='walmart' AND fee_date=? AND sku NOT LIKE 'CS%'`, [d]);
      const storage = Number((st as Array<Record<string, unknown>>)[0]?.v ?? 0);
      const salesAll = Number(bb.sales_all ?? 0), salesNc = Number(bb.sales_nc ?? 0);
      const gpAll = Number(bb.gp_all ?? 0), gpNc = Number(bb.gp_nc ?? 0);
      const adOld = Number(bb.ad_old ?? 0), wfs = Number(bb.wfs ?? 0), leg = Number(bb.leg ?? 0), comm = Number(bb.comm ?? 0);
      const netSales = salesNc - disc;
      const v2Profit = r2(netSales - adNew - wfs - comm - leg - refund - storage);
      const adDelta = r2(adNew - adOld);
      const identityDiff = r2(v2Profit - (gpNc - disc - refund - storage - adDelta));
      lines.push(`| ${d} | ${salesAll} | ${salesNc} | ${disc} | ${refund} | ${storage} | ${adOld} | ${r2(adNew)} | ${adDelta} | ${gpAll} | ${gpNc} | ${v2Profit} | ${identityDiff} |`);
    }
    lines.push(``);
    lines.push(`说明：恒等自检差≈0（±数元内=佣金费率/舍入正常波动）说明V2公式与旧毛利可互推；`);
    lines.push(`广告增量列=SEM/SB/SV补进的费用（旧口径漏计部分）；仓储8/8后账期未出账时为0属待出账状态。`);
    const out = lines.join("\n");
    const dir = "reports";
    if (!fs.existsSync(dir)) fs.mkdirSync(dir, { recursive: true });
    const fname = `${dir}/v2_reconcile_${dates[dates.length - 1]?.replace(/-/g, "") ?? "latest"}.md`;
    fs.writeFileSync(fname, out, "utf-8");
    console.log(out);
    console.log(`\nREPORT_FILE=${fname}`);
  } finally {
    await db.end();
  }
}
main().catch((e) => { console.error("FATAL:", e instanceof Error ? e.message : String(e)); process.exit(1); });
