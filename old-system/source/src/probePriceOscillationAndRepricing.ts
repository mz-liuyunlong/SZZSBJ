/**
 * probePriceOscillationAndRepricing.ts —— 只读探测（第二轮）：价格对倒成因 + 需求方判据的落地量测
 *
 * 缘起：第一轮 probePriceVsOrderAvg.ts 跑出三个数——无订单可核 89.38%、有订单时 price 与成交价吻合 87.42%、
 *       但调价事件同向率只有 13.43%。明细里看到两个形状：
 *         模式A 高频对倒：JJ8006-1U 16.99↔14.99 几乎逐日翻转，成交均价恒定 14.99
 *         模式B 跳离谱值：YC00124-1A 挂 53.99、同日成交 8 件均价 12.99
 *       推测 `price` 在「促销价」与「原价」之间摆（促销价 API 不下发，见 API_MAP §2.5-d）。**本探针验证这个推测。**
 *
 * 需求方 2026-08-21 定案的判据（本探针的步骤5就是给这套判据算账）：
 *   · price 变更 且 当日成交价与新价一致  → 判定为「调价」，写系统运营日志
 *   · 不一致（异常）                      → 不猜，提醒运营在**人工运营日志**写实际情况
 *   · AI 分析时权重：人工运营日志 > 系统运营日志
 *   · 跑一段时间确认方案后再考虑撤掉人工环节
 *   ⇒ 因此本探针必须回答：**这套判据下每天能自动判几条、要提醒几条**。太多运营被烦死，太少系统等于没用。
 *
 * 第一轮留下的两个局限，本探针专门补上：
 *   ① 上轮「同日多快照价不一致=0」是空检查（一天只抓一次快照，min 必然=max），证明不了任何事 → 本轮改为跨日行为画像
 *   ② 上轮 374 条「不同向」没拆开「均价纹丝不动」与「均价反向」→ 本轮步骤4 拆
 *
 * 口径与第一轮完全一致（不许换口径，否则两轮结论不可比）：
 *   挂牌价 = raw_lingxing_walmart_listing.row_json.$.price ；订单均价 = fact_sales_daily.sales_amount / sales_qty
 *
 * 只读约束：全程只 SELECT，不 INSERT/UPDATE/DDL，不调任何外部 API。
 * 时区加固：dateStrings:true（DATABASE_MAP 2026-08-02 教训：mysql2 的 DATE 列 toISOString 会整体错一天）。
 * 日界提示：fact_sales 是美西日界，capture_date 是北京日期 → 步骤5 同时算 T+0 与 T+1，用来量化这个偏移的影响。
 *
 * 用法：
 *   npx ts-node src/probePriceOscillationAndRepricing.ts
 *   npx ts-node src/probePriceOscillationAndRepricing.ts --days=30 --tol=0.01 --top=20
 */
import "dotenv/config";
import * as mysql from "mysql2/promise";

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

type Row = {
  d: string; store_id: string; item_id: string; msku: string;
  price: number; sales_qty: number | null; sales_amount: number | null;
};
type Day = { d: string; price: number; unit: number | null; qty: number };

function pct(n: number, d: number): string { return d === 0 ? "—" : `${((n / d) * 100).toFixed(2)}%`; }
function r2(n: number): number { return Math.round(n * 100) / 100; }
function dayDiff(a: string, b: string): number {
  return Math.round((Date.parse(`${b}T00:00:00Z`) - Date.parse(`${a}T00:00:00Z`)) / 86400000);
}
function histo(vals: number[], edges: number[], labels: string[]): void {
  const total = vals.length;
  for (let i = 0; i < labels.length; i++) {
    const lo = edges[i], hi = edges[i + 1];
    const n = vals.filter((v) => v >= lo && (hi === undefined || v < hi)).length;
    console.log(`    ${labels[i].padEnd(18)}${String(n).padStart(7)}  ${pct(n, total)}`);
  }
}

async function main(): Promise<void> {
  const days = Number(getArg("days", "30"));
  const tol = Number(getArg("tol", "0.01"));
  const top = Number(getArg("top", "20"));

  const db = await getDb();
  console.log("=".repeat(84));
  console.log("价格对倒成因 + 需求方判据落地量测（只读 · 第二轮）");
  console.log(`  窗口=最近 ${days} 天 · 一致性阈值=${(tol * 100).toFixed(1)}% · 明细 Top ${top}`);
  console.log("=".repeat(84));

  try {
    console.log("\n【步骤0】表结构自检");
    for (const t of ["raw_lingxing_walmart_listing", "fact_sales_daily"]) {
      const ok = await tableExists(db, t);
      console.log(`  ${t.padEnd(32)} ${ok ? "✅ 存在" : "❌ 不存在 —— 探测中止"}`);
      if (!ok) return;
    }

    const [rangeRows] = await db.query<mysql.RowDataPacket[]>(
      `SELECT MAX(capture_date) AS d1 FROM raw_lingxing_walmart_listing`);
    const endDate = String(rangeRows[0]?.d1 ?? "");
    if (!endDate) { console.log("  ⚠️ 快照表为空，无法探测。"); return; }
    console.log(`  快照最新日 = ${endDate}`);

    console.log("\n【步骤1】拉取对照集（口径与第一轮完全一致）");
    const [raw] = await db.query<mysql.RowDataPacket[]>(
      `SELECT s.capture_date AS d, s.store_id, s.item_id, s.msku, s.price,
              f.sales_qty, f.sales_amount
         FROM (
           SELECT capture_date, store_id, item_id, msku,
                  MAX(CAST(NULLIF(JSON_UNQUOTE(JSON_EXTRACT(row_json,'$.price')),'null') AS DECIMAL(12,4))) AS price
             FROM raw_lingxing_walmart_listing
            WHERE capture_date > DATE_SUB(?, INTERVAL ? DAY)
            GROUP BY capture_date, store_id, item_id, msku
         ) s
         LEFT JOIN fact_sales_daily f
                ON f.platform='walmart' AND f.stat_date = s.capture_date
               AND f.store_id = s.store_id AND f.item_id = s.item_id AND f.msku = s.msku
        WHERE s.price IS NOT NULL AND s.price > 0
        ORDER BY s.store_id, s.item_id, s.msku, s.capture_date`, [endDate, days]);
    const rows = raw as unknown as Row[];
    console.log(`  对照集行数 = ${rows.length}`);
    if (rows.length === 0) { console.log("  ⚠️ 0 行。先排除样本问题，不要判成口径不可用。"); return; }

    const byKey = new Map<string, Day[]>();
    for (const r of rows) {
      const k = `${r.store_id}|${r.item_id}|${r.msku}`;
      const qty = Number(r.sales_qty ?? 0);
      const amt = Number(r.sales_amount ?? 0);
      const day: Day = { d: String(r.d), price: Number(r.price), qty, unit: qty > 0 && amt > 0 ? amt / qty : null };
      const a = byKey.get(k); if (a) a.push(day); else byKey.set(k, [day]);
    }
    console.log(`  覆盖 店×item×msku = ${byKey.size}`);

    // ── 步骤2：价格行为画像（模式A 到底占多少）────────────────────────────────
    console.log("\n【步骤2】按 item 的价格行为画像（跨日，非同日）");
    type Prof = { key: string; snapDays: number; distinct: number; changes: number; flips: number; pmin: number; pmax: number; ratio: number };
    const profs: Prof[] = [];
    for (const [key, arr] of byKey) {
      const prices = arr.map((x) => r2(x.price));
      const distinct = new Set(prices).size;
      let changes = 0, flips = 0, lastDir = 0;
      for (let i = 1; i < prices.length; i++) {
        if (prices[i] === prices[i - 1]) continue;
        changes++;
        const dir = Math.sign(prices[i] - prices[i - 1]);
        if (lastDir !== 0 && dir !== lastDir) flips++;
        lastDir = dir;
      }
      const pmin = Math.min(...prices), pmax = Math.max(...prices);
      profs.push({ key, snapDays: arr.length, distinct, changes, flips, pmin, pmax, ratio: pmin > 0 ? pmax / pmin : 0 });
    }
    const changed = profs.filter((p) => p.changes > 0);
    console.log(`  窗口内 price 从未变过的 item = ${profs.length - changed.length}  ${pct(profs.length - changed.length, profs.length)}`);
    console.log(`  窗口内 price 变过的 item   = ${changed.length}  ${pct(changed.length, profs.length)}`);
    console.log(`\n  变价 item 的「不同价格值个数」分布：`);
    histo(changed.map((p) => p.distinct), [2, 3, 4, 6, 11, Infinity], ["2 个值（对倒嫌疑）", "3 个值", "4~5 个值", "6~10 个值", ">10 个值"]);
    console.log(`\n  变价 item 的「方向翻转次数」分布（翻转=涨跌方向反转，模式A 的直接指标）：`);
    histo(changed.map((p) => p.flips), [0, 1, 3, 6, 11, Infinity], ["0 次（单向调价）", "1~2 次", "3~5 次", "6~10 次", ">10 次"]);
    const oscillating = changed.filter((p) => p.flips >= 3);
    console.log(`\n  ⇒ 翻转≥3 次的「对倒型」item = ${oscillating.length}  占变价 item 的 ${pct(oscillating.length, changed.length)}`);
    console.log(`\n  最高价/最低价 比值分布（模式B 的直接指标）：`);
    histo(changed.map((p) => p.ratio), [1, 1.2, 1.5, 2, 3, Infinity], ["<1.2 倍", "1.2~1.5 倍", "1.5~2 倍", "2~3 倍", "≥3 倍（离谱）"]);
    console.log(`\n  翻转最多的 ${top} 个 item：`);
    console.log(`    ${"店|item|msku".padEnd(46)}${"快照天".padStart(7)}${"值数".padStart(6)}${"变更".padStart(6)}${"翻转".padStart(6)}${"价格区间".padStart(18)}`);
    for (const p of [...changed].sort((a, b) => b.flips - a.flips).slice(0, top)) {
      console.log(`    ${p.key.padEnd(46)}${String(p.snapDays).padStart(7)}${String(p.distinct).padStart(6)}${String(p.changes).padStart(6)}${String(p.flips).padStart(6)}${`${p.pmin.toFixed(2)}~${p.pmax.toFixed(2)}`.padStart(18)}`);
    }

    // ── 步骤3：成交均价是不是恒等于 price 最小值 ───────────────────────────────
    console.log("\n【步骤3】验证推测：「成交均价恒等于该 item 的 price 最小值」");
    console.log("  （若成立 ⇒ price 在 促销价/原价 之间摆，实际一直按低价卖；这决定 price 能不能单独当售价用）");
    let nearMin = 0, nearMax = 0, between = 0, outside = 0, evaluable = 0;
    const sampleRows: string[] = [];
    for (const p of changed) {
      const arr = byKey.get(p.key) ?? [];
      const units = arr.filter((x) => x.unit !== null).map((x) => r2(x.unit as number));
      if (units.length === 0) continue;
      evaluable++;
      const med = units.slice().sort((a, b) => a - b)[Math.floor(units.length / 2)];
      const dMin = Math.abs(med - p.pmin) / p.pmin;
      const dMax = Math.abs(med - p.pmax) / p.pmax;
      if (dMin <= tol) { nearMin++; if (sampleRows.length < top) sampleRows.push(`    ${p.key.padEnd(46)} 价区间 ${p.pmin.toFixed(2)}~${p.pmax.toFixed(2)}  成交中位 ${med.toFixed(2)}  → 贴最低价`); }
      else if (dMax <= tol) nearMax++;
      else if (med > p.pmin && med < p.pmax) between++;
      else outside++;
    }
    console.log(`  可评估 item（变过价且有成交）= ${evaluable}`);
    console.log(`    成交中位价 ≈ 最低挂牌价   ${String(nearMin).padStart(6)}  ${pct(nearMin, evaluable)}   ← 支持「按促销价卖、price 在摆」`);
    console.log(`    成交中位价 ≈ 最高挂牌价   ${String(nearMax).padStart(6)}  ${pct(nearMax, evaluable)}`);
    console.log(`    落在两者之间             ${String(between).padStart(6)}  ${pct(between, evaluable)}   ← 真调价的正常形状`);
    console.log(`    落在区间之外             ${String(outside).padStart(6)}  ${pct(outside, evaluable)}   ← 需单独看`);
    if (sampleRows.length) { console.log(`\n  「贴最低价」样例：`); sampleRows.forEach((x) => console.log(x)); }

    // ── 步骤4：把第一轮的「不同向」拆开 ────────────────────────────────────────
    console.log("\n【步骤4】第一轮 374 条「不同向」的拆解（补上轮缺口）");
    let evUnmoved = 0, evSame = 0, evOpposite = 0, evBoth = 0;
    for (const [, arr] of byKey) {
      for (let i = 1; i < arr.length; i++) {
        const a = arr[i - 1], b = arr[i];
        if (r2(a.price) === r2(b.price)) continue;
        if (a.unit === null || b.unit === null) continue;
        evBoth++;
        const dp = Math.sign(r2(b.price) - r2(a.price));
        const du = Math.sign(r2(b.unit) - r2(a.unit));
        if (du === 0) evUnmoved++; else if (du === dp) evSame++; else evOpposite++;
      }
    }
    console.log(`  前后两天都有订单的调价事件 = ${evBoth}`);
    console.log(`    成交均价同向变动   ${String(evSame).padStart(6)}  ${pct(evSame, evBoth)}`);
    console.log(`    成交均价纹丝不动   ${String(evUnmoved).padStart(6)}  ${pct(evUnmoved, evBoth)}   ← 模式A 的指纹`);
    console.log(`    成交均价反向变动   ${String(evOpposite).padStart(6)}  ${pct(evOpposite, evBoth)}   ← 真异常，需人工看`);

    // ── 步骤5：★需求方判据的落地量测 ─────────────────────────────────────────
    console.log("\n【步骤5】★ 需求方判据落地量测：price 变更 + 成交价与新价一致 = 调价");
    type Cls = { key: string; d: string; from: number; to: number; unit: number | null; unitNext: number | null; cls: string; dev: number | null };
    const evs: Cls[] = [];
    for (const [key, arr] of byKey) {
      for (let i = 1; i < arr.length; i++) {
        const a = arr[i - 1], b = arr[i];
        const p0 = r2(a.price), p1 = r2(b.price);
        if (p0 === p1) continue;
        const nxt = arr[i + 1];
        const unitNext = nxt && dayDiff(b.d, nxt.d) === 1 ? nxt.unit : null;
        let cls: string, dev: number | null = null;
        if (b.unit === null) cls = "无订单可核";
        else { dev = Math.abs(b.unit - p1) / p1; cls = dev <= tol ? "判定为调价" : "异常·需提醒人工"; }
        evs.push({ key, d: b.d, from: p0, to: p1, unit: b.unit, unitNext, cls, dev });
      }
    }
    const nDays = new Set(rows.map((r) => r.d)).size;
    const cntBy = (c: string) => evs.filter((e) => e.cls === c).length;
    console.log(`  窗口内 price 变更事件总数 = ${evs.length}（覆盖 ${new Set(evs.map((e) => e.key)).size} 个 item，快照天数 ${nDays}）`);
    console.log(`  ${"分类".padEnd(20)}${"条数".padStart(8)}${"占比".padStart(10)}${"日均".padStart(10)}`);
    for (const c of ["判定为调价", "异常·需提醒人工", "无订单可核"]) {
      const n = cntBy(c);
      console.log(`  ${c.padEnd(20)}${String(n).padStart(8)}${pct(n, evs.length).padStart(10)}${(n / nDays).toFixed(1).padStart(10)}`);
    }
    console.log(`\n  ⇒ 按此判据，系统每天自动判定「调价」约 ${(cntBy("判定为调价") / nDays).toFixed(1)} 条，`);
    console.log(`     每天需要提醒运营手写人工日志约 ${(cntBy("异常·需提醒人工") / nDays).toFixed(1)} 条。`);
    console.log(`     ——「需提醒」这个日均数就是运营的额外负担，需求方按这个数决定阈值松紧。`);

    console.log(`\n  日界敏感性：把「当日」放宽为「当日或次日成交价与新价一致」后：`);
    const relaxed = evs.filter((e) => {
      const okToday = e.unit !== null && Math.abs(e.unit - e.to) / e.to <= tol;
      const okNext = e.unitNext !== null && Math.abs(e.unitNext - e.to) / e.to <= tol;
      return okToday || okNext;
    }).length;
    console.log(`    判定为调价 ${cntBy("判定为调价")} → ${relaxed} 条（日均 ${(relaxed / nDays).toFixed(1)}）`);
    console.log(`    （fact_sales 是美西日界、capture_date 是北京日期，差额即为日界错位带来的漏判）`);

    console.log(`\n  「异常·需提醒人工」的偏离档位分布：`);
    const abn = evs.filter((e) => e.cls === "异常·需提醒人工" && e.dev !== null);
    histo(abn.map((e) => e.dev as number), [0.01, 0.05, 0.1, 0.3, 0.5, Infinity], ["1%~5%", "5%~10%", "10%~30%", "30%~50%", ">50%（离谱）"]);

    console.log(`\n  「判定为调价」样例（前 ${top} 条，这些就是会自动写进系统运营日志的）：`);
    console.log(`    ${"日期".padEnd(12)}${"店|item|msku".padEnd(46)}${"挂牌价 旧→新".padStart(18)}${"当日成交均价".padStart(14)}`);
    for (const e of evs.filter((x) => x.cls === "判定为调价").slice(0, top)) {
      console.log(`    ${e.d.padEnd(12)}${e.key.padEnd(46)}${`${e.from.toFixed(2)} → ${e.to.toFixed(2)}`.padStart(18)}${(e.unit as number).toFixed(2).padStart(14)}`);
    }
    console.log(`\n  「异常·需提醒人工」样例（偏离最大的前 ${top} 条）：`);
    console.log(`    ${"日期".padEnd(12)}${"店|item|msku".padEnd(46)}${"挂牌价 旧→新".padStart(18)}${"当日成交均价".padStart(14)}${"偏离".padStart(9)}`);
    for (const e of [...abn].sort((a, b) => (b.dev as number) - (a.dev as number)).slice(0, top)) {
      console.log(`    ${e.d.padEnd(12)}${e.key.padEnd(46)}${`${e.from.toFixed(2)} → ${e.to.toFixed(2)}`.padStart(18)}${(e.unit as number).toFixed(2).padStart(14)}${`${((e.dev as number) * 100).toFixed(1)}%`.padStart(9)}`);
    }

    console.log("\n【步骤6】结论（供需求方拍板）");
    console.log(`  ① 对倒型 item（翻转≥3次）占变价 item 的 ${pct(oscillating.length, changed.length)}。`);
    console.log(`  ② 成交中位价贴最低挂牌价的 item 占可评估的 ${pct(nearMin, evaluable)} —— 越高越说明 price 在促销价/原价之间摆。`);
    console.log(`  ③ 需求方判据下：日均自动判定 ${(cntBy("判定为调价") / nDays).toFixed(1)} 条，日均提醒人工 ${(cntBy("异常·需提醒人工") / nDays).toFixed(1)} 条，日均无订单可核 ${(cntBy("无订单可核") / nDays).toFixed(1)} 条。`);
    console.log(`  ④ 放宽到 T+1 后自动判定升至日均 ${(relaxed / nDays).toFixed(1)} 条 —— 差额即日界错位的代价。`);
  } catch (e) {
    console.error(`✗ 探测异常: ${e instanceof Error ? e.message : String(e)}`);
    console.error("  按规矩：报错的查询不得用于支撑任何结论（API_MAP §6-1）。");
  } finally {
    await db.end().catch(() => undefined);
  }
}

main().catch((e: unknown) => { console.error("探测脚本异常:", e); process.exit(1); });
