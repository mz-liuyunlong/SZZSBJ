/**
 * probeSampleOrderCostLeak.ts —— 只读探测：送样单「销售额剔除了、成本没剔除」的影响面量化
 *
 * 缘起（需求方 2026-08-21 报障，附「每日销售明细V2」YC00263 截图）：
 *   2026-08-14 该行 销量=0、销售额=0.00，但 剔除送样额=19.99、头程成本=0.82、采购成本=2.47、订单利润=-10.24。
 *   需求方原话：「订单剔除，所有成本都要剔除，不然真实订单的利润偏低」。
 *
 * 代码侧已定位（读代码得出，非推测，本探针用数据复核）：
 *   · src/salesDetailV2Routes.ts:139-142 —— 建行时就把成本按**含送样的 qty** 算死：
 *       wfs = wfs_unit * qty ; purchase_cost = pc_unit * qty / 6.6 ; first_leg = fl_unit * qty / 6.6
 *     :160-162 才把送样从 sales/qty 里减掉，**三项成本没有回头重算**。
 *   · src/orderProfitV2Routes.ts:102-108 同形态（SQL 里 SUM(unit * sales_qty) 含送样），
 *     :306-312 只把 netSales / qtyNet / commission 换成剔除后口径，**r.wfs / pc_cny / fl_cny 仍是含送样的**。
 *   · 佣金无此问题（:311 用 netSales 算，正确）；仓储费按日摊与销量无关；广告按剔除后销售额份额分摊。
 *   ⇒ 受影响的**只有三列：WFS配送费、采购成本、头程成本**。本探针只量化这三列。
 *
 * 本探针要回答的四件事：
 *   ① 影响面：多少行、多少品、多少店、多长时间区间
 *   ② 错记金额：被误计入订单利润的成本合计是多少
 *   ③ 修正后利润变化：合计变化、以及"从亏变不亏"的行有多少
 *   ④ 边界情况清点（这些直接决定方案怎么写，不清点就写代码必踩）
 *
 * 判定条件与线上**逐字一致**，不得自创：
 *   送样单 = raw_mp_order_discount 中 order_status <> 7 AND ABS(discount_amount) >= item_price_amount - 0.01
 *   汇率 6.6（EXCHANGE_RATE，两个路由文件同值）；CS 开头 MSKU 与人工名单 item 一律排除。
 *
 * 只读约束：全程只 SELECT，不 INSERT/UPDATE/DDL，不调任何外部 API，不改任何现有文件。
 * 时区加固：dateStrings:true（DATABASE_MAP 2026-08-02 教训：DATE 列 toISOString 会整体错一天）。
 *
 * 用法：
 *   npx ts-node src/probeSampleOrderCostLeak.ts
 *   npx ts-node src/probeSampleOrderCostLeak.ts --days=31 --top=25 --case=YC00263-1A
 */
import "dotenv/config";
import * as mysql from "mysql2/promise";

const EXCHANGE_RATE = 6.6;
const MANUAL_EXCLUDE_ITEMS = new Set<string>(["20090164596", "20706361834"]);

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
async function tableExists(db: mysql.Connection, name: string): Promise<boolean> {
  const [rows] = await db.query<mysql.RowDataPacket[]>(
    `SELECT COUNT(*) AS n FROM information_schema.TABLES
      WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = ?`, [name]);
  return Number(rows[0]?.n ?? 0) > 0;
}
const r2 = (v: number): number => Math.round(v * 100) / 100;
const money = (v: number): string => `$${v.toFixed(2)}`;
function pct(n: number, d: number): string { return d === 0 ? "—" : `${((n / d) * 100).toFixed(2)}%`; }

async function main(): Promise<void> {
  const days = Number(getArg("days", "31"));
  const top = Number(getArg("top", "25"));
  const caseMsku = getArg("case", "YC00263-1A");

  const db = await getDb();
  console.log("=".repeat(88));
  console.log("送样单成本未剔除 影响面量化（只读）");
  console.log(`  窗口=最近 ${days} 天 · 明细 Top ${top} · 对照样例 MSKU=${caseMsku}`);
  console.log("=".repeat(88));

  try {
    console.log("\n【步骤0】表结构自检");
    for (const t of ["fact_profit_daily", "raw_mp_order_discount"]) {
      const ok = await tableExists(db, t);
      console.log(`  ${t.padEnd(28)} ${ok ? "✅ 存在" : "❌ 不存在 —— 探测中止"}`);
      if (!ok) return;
    }

    // ── 步骤1：送样识别的可用区间（识别窗口决定修正只能覆盖多久）─────────────
    console.log("\n【步骤1】送样单识别的可用区间（折扣RAW 只有31天窗口，超窗的送样识别不了）");
    const [dr] = await db.query<mysql.RowDataPacket[]>(
      `SELECT MIN(purchase_date) d0, MAX(purchase_date) d1, COUNT(*) rows_all,
              SUM(order_status <> 7 AND ABS(discount_amount) >= item_price_amount - 0.01) sample_lines
         FROM raw_mp_order_discount`);
    const g = dr[0] ?? {};
    console.log(`  raw_mp_order_discount 覆盖 ${g.d0} ~ ${g.d1}  折扣行 ${g.rows_all}，其中判定为送样的行 ${g.sample_lines}`);
    if (!g.d1) { console.log("  ⚠️ 折扣RAW为空，无法探测。"); return; }
    const endDate = String(g.d1);

    const [pr] = await db.query<mysql.RowDataPacket[]>(
      `SELECT MIN(stat_date) d0, MAX(stat_date) d1 FROM fact_profit_daily WHERE platform='walmart'`);
    console.log(`  fact_profit_daily 覆盖 ${pr[0]?.d0} ~ ${pr[0]?.d1}`);
    console.log(`  ⇒ 修正只在两者交集内有效；交集之外的历史送样单**识别不出来，也就修不了**。`);

    // ── 步骤2：拉受影响行（口径与线上逐字一致）───────────────────────────────
    console.log("\n【步骤2】拉取受影响行（送样日 × 店 × MSKU）");
    const [raw] = await db.query<mysql.RowDataPacket[]>(
      `SELECT DATE_FORMAT(f.stat_date,'%Y-%m-%d') d, f.store_id, COALESCE(f.store_name,'') store_name,
              f.item_id, f.msku,
              CAST(JSON_UNQUOTE(JSON_EXTRACT(f.extra_json,'$.sales_qty')) AS DECIMAL(12,2)) qty,
              f.sales_amount sales,
              CAST(JSON_UNQUOTE(JSON_EXTRACT(f.extra_json,'$.wfs_fee_usd')) AS DECIMAL(12,4)) wfs_unit,
              CAST(JSON_UNQUOTE(JSON_EXTRACT(f.extra_json,'$.purchase_cost_cny')) AS DECIMAL(12,4)) pc_unit,
              CAST(JSON_UNQUOTE(JSON_EXTRACT(f.extra_json,'$.first_leg_cost_cny')) AS DECIMAL(12,4)) fl_unit,
              s.sqty, s.samt
         FROM fact_profit_daily f
         JOIN (
           SELECT purchase_date pd, store_id, msku, SUM(quantity) sqty, ROUND(SUM(item_price_amount),2) samt
             FROM raw_mp_order_discount
            WHERE order_status <> 7 AND ABS(discount_amount) >= item_price_amount - 0.01
              AND msku NOT LIKE 'CS%'
              AND purchase_date > DATE_SUB(?, INTERVAL ? DAY)
            GROUP BY pd, store_id, msku
         ) s ON s.pd = f.stat_date AND s.store_id = f.store_id AND s.msku = f.msku
        WHERE f.platform='walmart' AND f.msku NOT LIKE 'CS%'
        ORDER BY f.stat_date DESC, f.store_id, f.msku`, [endDate, days]);
    type R = { d: string; store_id: string; store_name: string; item_id: string; msku: string;
      qty: number; sales: number; wfs_unit: number; pc_unit: number; fl_unit: number; sqty: number; samt: number };
    const rows = (raw as unknown as R[]).filter((r) => !MANUAL_EXCLUDE_ITEMS.has(String(r.item_id)));
    console.log(`  受影响行数 = ${rows.length}（已排除 CS 测品与人工名单 item）`);
    if (rows.length === 0) { console.log("  ⚠️ 0 行。先排除样本问题，不要判成「无此问题」。"); return; }

    // ── 步骤3：影响面 ────────────────────────────────────────────────────────
    console.log("\n【步骤3】影响面");
    const [allCnt] = await db.query<mysql.RowDataPacket[]>(
      `SELECT COUNT(*) n FROM fact_profit_daily
        WHERE platform='walmart' AND msku NOT LIKE 'CS%' AND stat_date > DATE_SUB(?, INTERVAL ? DAY)`, [endDate, days]);
    const totalRows = Number(allCnt[0]?.n ?? 0);
    console.log(`  同窗口明细总行数        ${String(totalRows).padStart(8)}`);
    console.log(`  其中受影响行            ${String(rows.length).padStart(8)}  ${pct(rows.length, totalRows)}`);
    console.log(`  涉及 MSKU               ${String(new Set(rows.map((r) => r.msku)).size).padStart(8)}`);
    console.log(`  涉及 店铺               ${String(new Set(rows.map((r) => r.store_id)).size).padStart(8)}`);
    console.log(`  涉及 自然日             ${String(new Set(rows.map((r) => r.d)).size).padStart(8)}`);
    console.log(`  送样件数合计            ${String(rows.reduce((s, r) => s + Number(r.sqty), 0)).padStart(8)}`);
    console.log(`  送样金额合计（原价口径） ${money(rows.reduce((s, r) => s + Number(r.samt), 0)).padStart(8)}`);

    // ── 步骤4：错记成本 ──────────────────────────────────────────────────────
    console.log("\n【步骤4】被误计入订单利润的成本（= 送样件数 × 单件成本）");
    type Leak = R & { effQty: number; leakPc: number; leakFl: number; leakWfs: number; leakAll: number; qtyNet: number };
    const leaks: Leak[] = rows.map((r) => {
      const qty = Number(r.qty ?? 0), sqty = Number(r.sqty ?? 0);
      // 线上把销量截断为 max(0, qty - sqty)，故"应扣成本"的件数同样以实际可扣的为准，避免扣出负数
      const effQty = Math.min(sqty, qty);
      const qtyNet = Math.max(0, qty - sqty);
      const pcU = Number(r.pc_unit ?? 0), flU = Number(r.fl_unit ?? 0), wU = Number(r.wfs_unit ?? 0);
      const leakPc = pcU * effQty / EXCHANGE_RATE;
      const leakFl = flU * effQty / EXCHANGE_RATE;
      const leakWfs = wU * effQty;
      return { ...r, effQty, qtyNet, leakPc, leakFl, leakWfs, leakAll: leakPc + leakFl + leakWfs };
    });
    const sum = (f: (x: Leak) => number): number => leaks.reduce((s, x) => s + f(x), 0);
    console.log(`  采购成本 误记合计   ${money(sum((x) => x.leakPc)).padStart(12)}`);
    console.log(`  头程成本 误记合计   ${money(sum((x) => x.leakFl)).padStart(12)}`);
    console.log(`  WFS配送费 误记合计  ${money(sum((x) => x.leakWfs)).padStart(12)}`);
    console.log(`  ── 三项合计         ${money(sum((x) => x.leakAll)).padStart(12)}   ← 这就是订单利润被低估的总额`);
    console.log(`\n  按店铺拆分：`);
    const byStore = new Map<string, { n: number; amt: number }>();
    for (const x of leaks) {
      const k = x.store_name || x.store_id;
      const o = byStore.get(k) ?? { n: 0, amt: 0 };
      o.n++; o.amt += x.leakAll; byStore.set(k, o);
    }
    for (const [k, v] of [...byStore.entries()].sort((a, b) => b[1].amt - a[1].amt)) {
      console.log(`    ${k.padEnd(32)}${String(v.n).padStart(6)} 行   ${money(v.amt).padStart(12)}`);
    }
    console.log(`\n  误记金额最大的 ${top} 行：`);
    console.log(`    ${"日期".padEnd(12)}${"店铺".padEnd(24)}${"MSKU".padEnd(16)}${"销量".padStart(6)}${"送样".padStart(6)}${"净销量".padStart(8)}${"采购".padStart(9)}${"头程".padStart(9)}${"WFS".padStart(9)}${"合计".padStart(10)}`);
    for (const x of [...leaks].sort((a, b) => b.leakAll - a.leakAll).slice(0, top)) {
      console.log(`    ${x.d.padEnd(12)}${(x.store_name || x.store_id).slice(0, 22).padEnd(24)}${x.msku.slice(0, 14).padEnd(16)}` +
        `${String(Number(x.qty)).padStart(6)}${String(Number(x.sqty)).padStart(6)}${String(x.qtyNet).padStart(8)}` +
        `${money(x.leakPc).padStart(9)}${money(x.leakFl).padStart(9)}${money(x.leakWfs).padStart(9)}${money(x.leakAll).padStart(10)}`);
    }

    // ── 步骤5：边界情况清点（不清点就写代码必踩）──────────────────────────────
    console.log("\n【步骤5】边界情况清点");
    const caseA = leaks.filter((x) => x.qtyNet === 0);
    const caseB = leaks.filter((x) => Number(x.sqty) > Number(x.qty));
    const caseC = leaks.filter((x) => Number(x.pc_unit ?? 0) <= 0 || Number(x.fl_unit ?? 0) <= 0);
    console.log(`  A. 剔除后净销量=0 却仍有成本的行（截图那一类） ${String(caseA.length).padStart(6)}  ${pct(caseA.length, leaks.length)}  误记 ${money(caseA.reduce((s, x) => s + x.leakAll, 0))}`);
    console.log(`  B. 送样件数 > 当日销量（数据异常，线上被 max(0,) 截断） ${String(caseB.length).padStart(6)}  ${pct(caseB.length, leaks.length)}`);
    if (caseB.length) {
      console.log(`     ⚠️ 这类行「该扣多少件成本」没有唯一答案：按销量扣则送样成本扣不干净，按送样量扣则会扣出负成本。**需求方须拍板。**`);
      for (const x of caseB.slice(0, 10)) {
        console.log(`       ${x.d} ${(x.store_name || x.store_id).slice(0, 20)} ${x.msku}  销量=${Number(x.qty)} 送样=${Number(x.sqty)}`);
      }
    }
    console.log(`  C. 单件采购或头程成本缺失(<=0)的行             ${String(caseC.length).padStart(6)}  ${pct(caseC.length, leaks.length)}   ← 这类行本来就扣不全，修正影响有限`);
    // D. 折扣RAW有送样、但利润FACT当天没有对应行 → 线上 rows.get 未命中被静默丢弃
    const [orphan] = await db.query<mysql.RowDataPacket[]>(
      `SELECT COUNT(*) n FROM (
         SELECT s.pd, s.store_id, s.msku FROM (
           SELECT purchase_date pd, store_id, msku FROM raw_mp_order_discount
            WHERE order_status <> 7 AND ABS(discount_amount) >= item_price_amount - 0.01
              AND msku NOT LIKE 'CS%' AND purchase_date > DATE_SUB(?, INTERVAL ? DAY)
            GROUP BY pd, store_id, msku
         ) s LEFT JOIN fact_profit_daily f
             ON f.platform='walmart' AND f.stat_date = s.pd AND f.store_id = s.store_id AND f.msku = s.msku
         WHERE f.id IS NULL
       ) t`, [endDate, days]);
    console.log(`  D. 折扣RAW判为送样、但利润FACT当天无对应行     ${String(Number(orphan[0]?.n ?? 0)).padStart(6)}   ← 线上 rows.get 未命中被静默丢弃，这些送样目前既不剔销售额也不剔成本`);

    // ── 步骤6：对照样例（用需求方截图那条逐项核对）────────────────────────────
    console.log(`\n【步骤6】对照样例：MSKU=${caseMsku}（用来和需求方截图逐项核对）`);
    const cs = leaks.filter((x) => x.msku === caseMsku);
    if (cs.length === 0) console.log(`  该 MSKU 在窗口内无受影响行（可能不在窗口内，或未被判定为送样）。`);
    for (const x of cs) {
      console.log(`  ${x.d}  ${x.store_name || x.store_id}  ${x.msku}`);
      console.log(`     FACT原始:  销量=${Number(x.qty)}  销售额=${money(Number(x.sales))}`);
      console.log(`     送样    :  件数=${Number(x.sqty)}  金额=${money(Number(x.samt))}`);
      console.log(`     单件成本:  采购¥${Number(x.pc_unit).toFixed(2)}  头程¥${Number(x.fl_unit).toFixed(2)}  WFS$${Number(x.wfs_unit).toFixed(2)}`);
      console.log(`     现状(页面显示): 净销量=${x.qtyNet}  采购=${money(Number(x.pc_unit) * Number(x.qty) / EXCHANGE_RATE)}  头程=${money(Number(x.fl_unit) * Number(x.qty) / EXCHANGE_RATE)}  WFS=${money(Number(x.wfs_unit) * Number(x.qty))}   ← 按**含送样**的销量算`);
      console.log(`     修正后        : 净销量=${x.qtyNet}  采购=${money(Number(x.pc_unit) * x.qtyNet / EXCHANGE_RATE)}  头程=${money(Number(x.fl_unit) * x.qtyNet / EXCHANGE_RATE)}  WFS=${money(Number(x.wfs_unit) * x.qtyNet)}`);
      console.log(`     该行利润改善  : ${money(x.leakAll)}`);
    }

    // ── 步骤7：结论 ──────────────────────────────────────────────────────────
    console.log("\n【步骤7】结论");
    console.log(`  ① 受影响 ${rows.length} 行 / ${new Set(rows.map((r) => r.msku)).size} 个 MSKU / ${new Set(rows.map((r) => r.store_id)).size} 家店，占同窗口明细 ${pct(rows.length, totalRows)}。`);
    console.log(`  ② 订单利润被低估合计 ${money(sum((x) => x.leakAll))}（采购 ${money(sum((x) => x.leakPc))} + 头程 ${money(sum((x) => x.leakFl))} + WFS ${money(sum((x) => x.leakWfs))}）。`);
    console.log(`  ③ 截图那一类（净销量=0 仍背成本）共 ${caseA.length} 行，占受影响行 ${pct(caseA.length, leaks.length)}。`);
    console.log(`  ④ 修正只能覆盖折扣RAW的识别窗口；窗口之外的历史送样单识别不出来，也修不了。`);
    console.log(`  ⑤ 送样成本本身是真实发生的支出，修正后它从"订单利润"里移走 —— **移到哪里去，需求方须拍板**（本探针不替其决定）。`);
  } catch (e) {
    console.error(`✗ 探测异常: ${e instanceof Error ? e.message : String(e)}`);
    console.error("  按规矩：报错的查询不得用于支撑任何结论（API_MAP §6-1）。");
  } finally {
    await db.end().catch(() => undefined);
  }
}

main().catch((e: unknown) => { console.error("探测脚本异常:", e); process.exit(1); });
