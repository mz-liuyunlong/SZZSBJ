/**
 * probeSampleOrderAnomalyDetail.ts —— 只读探测：送样单两类异常的原始行取证
 *
 * 缘起（需求方 2026-08-21 追问，probeSampleOrderCostLeak 跑出 B/D 两类后）：
 *   B 类：「YC00216-1A 销5送6，是总订单11（卖5+送6），还是总共只有5单、其中6个送样？」
 *   D 类：「D 类是什么情况，我没有明白」
 *   —— 这两个问题都**不能靠推理回答**，必须把原始订单行摆出来。本探针只做取证，不下未经数据支撑的结论。
 *
 * 链路事实（读代码得出，用于解释为什么两个数会打架）：
 *   · 销量 qty：saleStat → fact_sales_daily.sales_qty → syncOrderProfitDaily(:309 COALESCE(f.sales_qty,0))
 *               → fact_profit_daily.extra_json.sales_qty
 *   · 送样件数 sqty：raw_mp_order_discount 里 SUM(quantity)，判定条件
 *               order_status <> 7 AND ABS(discount_amount) >= item_price_amount - 0.01
 *   ⇒ 两个不同来源，谁也不保证对方的口径。
 *
 * ⚠️ 取证纪律：**`fact_sales_daily.order_count` 不得当订单数用。**
 *   syncLingxingDailyToDb.ts:452 写入的是 `qty, qty, amount` —— order_count 只是 qty 的拷贝。
 *   要数"几个订单"只能数 raw_mp_order_discount 的 DISTINCT platform_order_no。
 *
 * 日界事实（已核查，不是坑）：raw_mp_order_discount.purchase_date 是**美西日界**
 *   （syncMpOrderDiscount.ts:137 `pDate = laDate(pts)` 走 usPacific 模块），与 saleStat 族同源。
 *   建表注释写的"北京时区"是 2026-08-18 对齐修订后**未更新的过期注释**，已骗过代码侧一次。
 *   本探针仍打印 ±2 天邻日数据，用于**实测**排除日界错位，而不是靠注释下结论。
 *
 * 只读约束：全程只 SELECT，不 INSERT/UPDATE/DDL，不调外部 API，不改任何现有文件。
 * 时区加固：dateStrings:true。
 *
 * 用法：
 *   npx ts-node src/probeSampleOrderAnomalyDetail.ts
 *   npx ts-node src/probeSampleOrderAnomalyDetail.ts --days=31
 */
import "dotenv/config";
import * as mysql from "mysql2/promise";

const MANUAL_EXCLUDE_ITEMS = new Set<string>(["20090164596", "20706361834"]);
const SAMPLE_COND = "order_status <> 7 AND ABS(discount_amount) >= item_price_amount - 0.01";

function getArg(name: string, dflt: string): string {
  const p = `--${name}=`;
  const a = process.argv.find((x: string) => x.startsWith(p));
  return a ? a.slice(p.length) : dflt;
}
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
function shift(d: string, n: number): string {
  return new Date(Date.parse(`${d}T00:00:00Z`) + n * 86400000).toISOString().slice(0, 10);
}

async function main(): Promise<void> {
  const days = Number(getArg("days", "31"));
  const db = await getDb();
  console.log("=".repeat(92));
  console.log("送样单 B/D 两类异常 原始行取证（只读）");
  console.log(`  窗口=最近 ${days} 天`);
  console.log("=".repeat(92));

  try {
    const [dr] = await db.query<mysql.RowDataPacket[]>(
      `SELECT MAX(purchase_date) d1 FROM raw_mp_order_discount`);
    const endDate = String(dr[0]?.d1 ?? "");
    if (!endDate) { console.log("⚠️ 折扣RAW为空，无法探测。"); return; }
    console.log(`\n折扣RAW 最新日 = ${endDate}`);

    // ══ B 类：送样件数 > 当日销量 ═══════════════════════════════════════════
    console.log("\n" + "━".repeat(92));
    console.log("【B 类】送样件数 > 当日销量 —— 逐案原始行取证");
    console.log("━".repeat(92));
    const [bcases] = await db.query<mysql.RowDataPacket[]>(
      `SELECT DATE_FORMAT(f.stat_date,'%Y-%m-%d') d, f.store_id, COALESCE(f.store_name,'') store_name,
              f.item_id, f.msku,
              CAST(JSON_UNQUOTE(JSON_EXTRACT(f.extra_json,'$.sales_qty')) AS DECIMAL(12,2)) qty,
              f.sales_amount sales, s.sqty, s.samt, s.slines
         FROM fact_profit_daily f
         JOIN (
           SELECT purchase_date pd, store_id, msku, SUM(quantity) sqty,
                  ROUND(SUM(item_price_amount),2) samt, COUNT(*) slines
             FROM raw_mp_order_discount
            WHERE ${SAMPLE_COND} AND msku NOT LIKE 'CS%'
              AND purchase_date > DATE_SUB(?, INTERVAL ? DAY)
            GROUP BY pd, store_id, msku
         ) s ON s.pd = f.stat_date AND s.store_id = f.store_id AND s.msku = f.msku
        WHERE f.platform='walmart' AND f.msku NOT LIKE 'CS%'
          AND s.sqty > CAST(JSON_UNQUOTE(JSON_EXTRACT(f.extra_json,'$.sales_qty')) AS DECIMAL(12,2))
        ORDER BY f.stat_date`, [endDate, days]);
    const bs = (bcases as Array<Record<string, unknown>>).filter((r) => !MANUAL_EXCLUDE_ITEMS.has(String(r.item_id)));
    console.log(`\n检出 B 类案例 = ${bs.length} 条\n`);

    for (const c of bs) {
      const d = String(c.d), sid = String(c.store_id), msku = String(c.msku);
      console.log("─".repeat(92));
      console.log(`■ ${d}  ${c.store_name || sid}  ${msku}`);
      console.log(`  利润FACT: sales_qty=${Number(c.qty)}  sales_amount=$${Number(c.sales).toFixed(2)}`);
      console.log(`  折扣RAW : 判定送样 行数=${Number(c.slines)}  件数=${Number(c.sqty)}  金额=$${Number(c.samt).toFixed(2)}`);

      // ① 该日该品 折扣RAW 全部原始行（含非送样折扣行，用于看清全貌）
      const [lines] = await db.query<mysql.RowDataPacket[]>(
        `SELECT platform_order_no, order_item_no, order_status, quantity,
                item_price_amount, discount_amount,
                DATE_FORMAT(purchase_time,'%Y-%m-%d %H:%i:%s') ptime,
                DATE_FORMAT(purchase_date,'%Y-%m-%d') pdate,
                (${SAMPLE_COND}) is_sample
           FROM raw_mp_order_discount
          WHERE store_id=? AND msku=? AND purchase_date=?
          ORDER BY purchase_time, platform_order_no`, [sid, msku, d]);
      console.log(`\n  ① 该日该品「折扣RAW」全部原始行（共 ${(lines as unknown[]).length} 行，含非送样折扣行）：`);
      console.log(`     ${"平台订单号".padEnd(24)}${"明细号".padEnd(22)}${"状态".padStart(5)}${"件数".padStart(6)}${"商品金额".padStart(10)}${"折扣额".padStart(10)}${"送样?".padStart(7)}  订购时间(美西)`);
      for (const l of lines as Array<Record<string, unknown>>) {
        console.log(`     ${String(l.platform_order_no).padEnd(24)}${String(l.order_item_no).slice(0, 20).padEnd(22)}` +
          `${String(l.order_status).padStart(5)}${String(l.quantity).padStart(6)}` +
          `${Number(l.item_price_amount).toFixed(2).padStart(10)}${Number(l.discount_amount).toFixed(2).padStart(10)}` +
          `${(Number(l.is_sample) === 1 ? "是" : "否").padStart(7)}  ${l.ptime}`);
      }
      const orderNos = new Set((lines as Array<Record<string, unknown>>).map((l) => String(l.platform_order_no)));
      const smpNos = new Set((lines as Array<Record<string, unknown>>).filter((l) => Number(l.is_sample) === 1).map((l) => String(l.platform_order_no)));
      console.log(`\n     ⇒ 折扣RAW 里不同「平台订单号」= ${orderNos.size} 个，其中含送样行的订单 = ${smpNos.size} 个`);
      console.log(`        （注意：折扣RAW 只收录**有折扣**的订单行，不含全价单，故这不是当日总订单数）`);

      // ② 该日该品 两个销售 FACT 的对照
      const [fsd] = await db.query<mysql.RowDataPacket[]>(
        `SELECT sales_qty, order_count, sales_amount FROM fact_sales_daily
          WHERE platform='walmart' AND stat_date=? AND store_id=? AND msku=?`, [d, sid, msku]);
      const f0 = (fsd as Array<Record<string, unknown>>)[0];
      console.log(`\n  ② fact_sales_daily 当日：` + (f0
        ? `sales_qty=${Number(f0.sales_qty)}  sales_amount=$${Number(f0.sales_amount).toFixed(2)}  [order_count=${Number(f0.order_count)} —— 是 qty 的拷贝，不可当订单数]`
        : `无行`));

      // ③ 前后 2 天，看是不是日界错位（实测，不靠注释）
      console.log(`\n  ③ 邻日对照（±2 天，用于实测排除日界错位）：`);
      console.log(`     ${"日期".padEnd(12)}${"销量FACT".padStart(10)}${"销售额".padStart(12)}${"送样件".padStart(9)}${"送样金额".padStart(11)}`);
      for (let k = -2; k <= 2; k++) {
        const dd = shift(d, k);
        const [a] = await db.query<mysql.RowDataPacket[]>(
          `SELECT sales_qty q, sales_amount amt FROM fact_sales_daily
            WHERE platform='walmart' AND stat_date=? AND store_id=? AND msku=?`, [dd, sid, msku]);
        const [b] = await db.query<mysql.RowDataPacket[]>(
          `SELECT SUM(quantity) q, ROUND(SUM(item_price_amount),2) amt FROM raw_mp_order_discount
            WHERE ${SAMPLE_COND} AND store_id=? AND msku=? AND purchase_date=?`, [sid, msku, dd]);
        const x = (a as Array<Record<string, unknown>>)[0], y = (b as Array<Record<string, unknown>>)[0];
        const mark = k === 0 ? "  ← 本案" : "";
        console.log(`     ${dd.padEnd(12)}${(x ? String(Number(x.q)) : "-").padStart(10)}${(x ? `$${Number(x.amt).toFixed(2)}` : "-").padStart(12)}` +
          `${(y && y.q !== null ? String(Number(y.q)) : "-").padStart(9)}${(y && y.amt !== null ? `$${Number(y.amt).toFixed(2)}` : "-").padStart(11)}${mark}`);
      }
      console.log("");
    }

    // ══ D 类：折扣RAW判为送样、但利润FACT当天无行 ═════════════════════════
    console.log("\n" + "━".repeat(92));
    console.log("【D 类】折扣RAW判为送样、但 fact_profit_daily 当天无对应行 —— 逐条归因");
    console.log("━".repeat(92));
    const [dcases] = await db.query<mysql.RowDataPacket[]>(
      `SELECT s.pd d, s.store_id, s.msku, s.sqty, s.samt, s.slines
         FROM (
           SELECT purchase_date pd, store_id, msku, SUM(quantity) sqty,
                  ROUND(SUM(item_price_amount),2) samt, COUNT(*) slines
             FROM raw_mp_order_discount
            WHERE ${SAMPLE_COND} AND msku NOT LIKE 'CS%'
              AND purchase_date > DATE_SUB(?, INTERVAL ? DAY)
            GROUP BY pd, store_id, msku
         ) s
         LEFT JOIN fact_profit_daily f
                ON f.platform='walmart' AND f.stat_date = s.pd
               AND f.store_id = s.store_id AND f.msku = s.msku
        WHERE f.id IS NULL
        ORDER BY s.pd, s.store_id, s.msku`, [endDate, days]);
    const ds = dcases as Array<Record<string, unknown>>;
    console.log(`\n检出 D 类 = ${ds.length} 条\n`);
    console.log(`${"日期".padEnd(12)}${"店铺ID".padEnd(22)}${"MSKU".padEnd(18)}${"送样件".padStart(7)}${"金额".padStart(10)}  归因`);

    const reasonCnt = new Map<string, number>();
    for (const x of ds) {
      const d = String(x.d), sid = String(x.store_id), msku = String(x.msku);
      // 归因证据 1：当日 fact_sales_daily 有没有行
      const [fs] = await db.query<mysql.RowDataPacket[]>(
        `SELECT sales_qty q FROM fact_sales_daily
          WHERE platform='walmart' AND stat_date=? AND store_id=? AND msku=?`, [d, sid, msku]);
      const hasSales = (fs as unknown[]).length > 0;
      // 归因证据 2：该店该品在利润FACT 全窗口最近的有行日期
      const [near] = await db.query<mysql.RowDataPacket[]>(
        `SELECT DATE_FORMAT(MAX(stat_date),'%Y-%m-%d') dmax, COUNT(*) n FROM fact_profit_daily
          WHERE platform='walmart' AND store_id=? AND msku=?`, [sid, msku]);
      const n0 = Number((near as Array<Record<string, unknown>>)[0]?.n ?? 0);
      const dmax = (near as Array<Record<string, unknown>>)[0]?.dmax;
      // 归因证据 3：dim_product 有没有建档
      const [dp] = await db.query<mysql.RowDataPacket[]>(
        `SELECT COUNT(*) n FROM dim_product WHERE platform='walmart' AND store_id=? AND msku=?`, [sid, msku]);
      const inDim = Number((dp as Array<Record<string, unknown>>)[0]?.n ?? 0) > 0;
      // 归因证据 4：利润FACT 在 ±1 天有没有行（日界错位嫌疑）
      const [adj] = await db.query<mysql.RowDataPacket[]>(
        `SELECT DATE_FORMAT(stat_date,'%Y-%m-%d') d FROM fact_profit_daily
          WHERE platform='walmart' AND store_id=? AND msku=? AND stat_date IN (?, ?)`,
        [sid, msku, shift(d, -1), shift(d, 1)]);
      const adjDays = (adj as Array<Record<string, unknown>>).map((r) => String(r.d));

      let reason: string;
      if (!inDim) reason = "① MSKU 在 dim_product 未建档";
      else if (n0 === 0) reason = "② 该品在利润FACT 从未出现过";
      else if (adjDays.length > 0) reason = `③ 利润FACT 邻日有行(${adjDays.join(",")}) → 日界/归因错位嫌疑`;
      else if (!hasSales) reason = "④ 当日 fact_sales_daily 也无行 → 当天 saleStat 确实没这个品";
      else reason = "⑤ 当日有销售FACT、无利润FACT → 利润ETL 漏生成";
      reasonCnt.set(reason, (reasonCnt.get(reason) ?? 0) + 1);
      console.log(`${d.padEnd(12)}${sid.padEnd(22)}${msku.slice(0, 16).padEnd(18)}${String(Number(x.sqty)).padStart(7)}${`$${Number(x.samt).toFixed(2)}`.padStart(10)}  ${reason}` +
        (n0 > 0 ? `  [该品利润FACT共${n0}行,最近${dmax}]` : ""));
    }
    console.log(`\n归因汇总：`);
    for (const [k, v] of [...reasonCnt.entries()].sort((a, b) => b[1] - a[1])) {
      console.log(`  ${String(v).padStart(4)} 条   ${k}`);
    }

    console.log("\n【结论提示】");
    console.log("  · B 类要看的是：折扣RAW 的订单号个数 与 销量FACT 的关系，以及邻日是否有互补（日界错位的指纹）。");
    console.log("  · D 类归因若集中在 ③，说明是归因日错位；集中在 ④，说明 saleStat 当天本就没这个品，属正常；");
    console.log("    集中在 ①/② 说明是建档/映射问题；出现 ⑤ 才是利润ETL 的缺陷。");
    console.log("  · 本探针只取证，不替需求方选修法。");
  } catch (e) {
    console.error(`✗ 探测异常: ${e instanceof Error ? e.message : String(e)}`);
    console.error("  按规矩：报错的查询不得用于支撑任何结论（API_MAP §6-1）。");
  } finally {
    await db.end().catch(() => undefined);
  }
}

main().catch((e: unknown) => { console.error("探测脚本异常:", e); process.exit(1); });
