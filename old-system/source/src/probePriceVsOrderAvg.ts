/**
 * probePriceVsOrderAvg.ts —— 只读探测：挂牌价 `price` 与「订单均价」的一致性（conflict 率）
 *
 * 缘起（需求方 2026-08-21）：
 *   「价格调整的规则，需要增加一个辅助判断的规矩，就是订单售价是否一致」
 *   —— 即：快照差分判定「运营调价了」之后，用当日订单均价做**旁证**。
 *   本探针只回答一个问题：**这条旁证规矩到底站不站得住**。
 *
 * 口径定义（写死，避免事后扯皮）：
 *   · 挂牌价     = `raw_lingxing_walmart_listing.row_json.$.price`（§API_MAP 2.5-e 已定：调价一律以 price 为准，
 *                  不用 buy_box_price——那列时而是BuyBox价时而是挂牌价，列名与语义不符）
 *   · 订单均价   = `fact_sales_daily.sales_amount / sales_qty`
 *                  （sales_amount 来自 saleStat V2 result_type=3，sales_qty 来自 result_type=1，见 syncLingxingDailyToDb.ts:676）
 *   · 偏离度     = |订单均价 - 挂牌价| / 挂牌价
 *   · conflict   = 偏离度 > 阈值（默认 1%）
 *
 * 已知的**合理**偏离原因（必须先分离，否则 conflict 率没有意义）：
 *   ① 促销折扣 —— `fact_promo_discount_daily` 有当日折扣额，本探针单独分层
 *   ② 日界不同 —— fact_sales 是**美西日界**（saleStat 族，DATABASE_MAP 2026-08-18 定），
 *                 而 listing 快照 capture_date 是**拉取时刻的北京日期**。当天改价的，订单里必然混着改价前的成交。
 *   ③ 一天内多次快照且价不同 —— 本探针输出 price_min/price_max，不合并掉这个信号
 *
 * 只读约束：**全程只 SELECT，不 INSERT / UPDATE / DDL，不调任何外部 API**。
 * 时区加固：连接开 `dateStrings:true`。原因见 DATABASE_MAP 2026-08-02 教训——
 *   mysql2 把 DATE 列返回成 +08:00 零点的 JS Date，`toISOString().slice(0,10)` 会整体错一天（探针11因此误报过）。
 *
 * 用法：
 *   npx ts-node src/probePriceVsOrderAvg.ts
 *   npx ts-node src/probePriceVsOrderAvg.ts --days=30 --tol=0.01 --top=25
 *   npx ts-node src/probePriceVsOrderAvg.ts --store=<store_id>
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

async function columnsOf(db: mysql.Connection, name: string): Promise<string[]> {
  const [rows] = await db.query<mysql.RowDataPacket[]>(
    `SELECT COLUMN_NAME FROM information_schema.COLUMNS
      WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = ? ORDER BY ORDINAL_POSITION`, [name]);
  return rows.map((r) => String(r.COLUMN_NAME));
}

type Row = {
  d: string; store_id: string; item_id: string; msku: string;
  price_min: number | null; price_max: number | null;
  sales_qty: number | null; sales_amount: number | null;
  discount_amount: number | null; discount_qty: number | null;
};

function pct(n: number, d: number): string {
  return d === 0 ? "—" : `${((n / d) * 100).toFixed(2)}%`;
}

async function main(): Promise<void> {
  const days = Number(getArg("days", "30"));
  const tol = Number(getArg("tol", "0.01"));
  const top = Number(getArg("top", "25"));
  const storeFilter = getArg("store", "");

  const db = await getDb();
  console.log("=".repeat(80));
  console.log("挂牌价 price vs 订单均价 一致性探测（只读）");
  console.log(`  窗口=最近 ${days} 天 · conflict 阈值=${(tol * 100).toFixed(1)}% · 明细 Top ${top}` +
    (storeFilter ? ` · 限店铺=${storeFilter}` : " · 全店铺"));
  console.log("=".repeat(80));

  try {
    // ── 步骤 0：结构自检（铁律：禁止臆测字段，缺列就停，不猜）──────────────────
    console.log("\n【步骤0】表结构自检");
    const need: Record<string, string[]> = {
      raw_lingxing_walmart_listing: ["capture_date", "store_id", "item_id", "msku", "row_json"],
      fact_sales_daily: ["stat_date", "platform", "store_id", "item_id", "msku", "sales_qty", "sales_amount"],
    };
    let structOk = true;
    for (const [t, cols] of Object.entries(need)) {
      if (!(await tableExists(db, t))) {
        console.log(`  ${t.padEnd(32)} ❌ 表不存在 —— 探测中止`);
        structOk = false; continue;
      }
      const actual = await columnsOf(db, t);
      const miss = cols.filter((c) => !actual.includes(c));
      console.log(`  ${t.padEnd(32)} ${miss.length === 0 ? "✅ 所需列齐全" : `❌ 缺列: ${miss.join(",")}`}  (实际 ${actual.length} 列)`);
      if (miss.length) { console.log(`     实际列名：${actual.join(", ")}`); structOk = false; }
    }
    // 促销表允许缺失（V2批2 状态未定），缺了就降级为「不分层」，并把这件事说清楚
    const hasPromo = await tableExists(db, "fact_promo_discount_daily");
    console.log(`  fact_promo_discount_daily        ${hasPromo ? "✅ 存在，启用促销分层" : "⚠️ 不存在 → 本次不做促销分层（促销导致的偏离将混在 conflict 里，结论需打折看）"}`);
    if (!structOk) { console.log("\n✗ 结构自检未通过，按规矩不猜字段、不继续。"); return; }

    // ── 步骤 1：样本范围（先证明有样本，再谈比率）──────────────────────────────
    console.log("\n【步骤1】快照样本范围");
    const [rangeRows] = await db.query<mysql.RowDataPacket[]>(
      `SELECT MIN(capture_date) AS d0, MAX(capture_date) AS d1,
              COUNT(*) AS rows_all, COUNT(DISTINCT capture_date) AS days_all,
              COUNT(DISTINCT store_id) AS stores, COUNT(DISTINCT item_id) AS items
         FROM raw_lingxing_walmart_listing`);
    const rg = rangeRows[0] ?? {};
    console.log(`  capture_date 覆盖 ${rg.d0} ~ ${rg.d1}  共 ${rg.days_all} 天 / ${rg.rows_all} 行 / ${rg.stores} 店 / ${rg.items} item`);
    if (Number(rg.days_all ?? 0) === 0) { console.log("  ⚠️ 快照表为空，无法探测。"); return; }
    const endDate = String(rg.d1);

    // ── 步骤 2：主查询 ───────────────────────────────────────────────────────
    console.log("\n【步骤2】拉取「快照价 × 当日销售 × 当日促销」对照集");
    const promoSelect = hasPromo ? "p.discount_amount, p.discount_qty" : "NULL AS discount_amount, NULL AS discount_qty";
    const promoJoin = hasPromo
      ? `LEFT JOIN fact_promo_discount_daily p
             ON p.platform = 'walmart' AND p.discount_date = s.capture_date
            AND p.store_id = s.store_id AND p.msku = s.msku`
      : "";
    const sql =
      `SELECT s.capture_date AS d, s.store_id, s.item_id, s.msku,
              s.price_min, s.price_max,
              f.sales_qty, f.sales_amount,
              ${promoSelect}
         FROM (
           SELECT capture_date, store_id, item_id, msku,
                  MIN(CAST(NULLIF(JSON_UNQUOTE(JSON_EXTRACT(row_json,'$.price')),'null') AS DECIMAL(12,4))) AS price_min,
                  MAX(CAST(NULLIF(JSON_UNQUOTE(JSON_EXTRACT(row_json,'$.price')),'null') AS DECIMAL(12,4))) AS price_max
             FROM raw_lingxing_walmart_listing
            WHERE capture_date > DATE_SUB(?, INTERVAL ? DAY)
              ${storeFilter ? "AND store_id = ?" : ""}
            GROUP BY capture_date, store_id, item_id, msku
         ) s
         LEFT JOIN fact_sales_daily f
                ON f.platform = 'walmart' AND f.stat_date = s.capture_date
               AND f.store_id = s.store_id AND f.item_id = s.item_id AND f.msku = s.msku
         ${promoJoin}
        WHERE s.price_max IS NOT NULL AND s.price_max > 0
        ORDER BY s.store_id, s.item_id, s.msku, s.capture_date`;
    const args: unknown[] = storeFilter ? [endDate, days, storeFilter] : [endDate, days];
    const [raw] = await db.query<mysql.RowDataPacket[]>(sql, args);
    const rows = raw as unknown as Row[];
    console.log(`  对照集行数 = ${rows.length}（一行 = 一个 快照日×店×item×msku）`);
    if (rows.length === 0) { console.log("  ⚠️ 0 行。先排除样本问题（窗口内是否有快照/该店是否有数据），不要直接判成「口径不可用」。"); return; }

    // ── 步骤 3：可核性（需求方口径：无订单则「无订单可核」，不算异常）──────────
    console.log("\n【步骤3】可核性拆分");
    const withOrder = rows.filter((r) => Number(r.sales_qty ?? 0) > 0 && Number(r.sales_amount ?? 0) > 0);
    const noOrder = rows.length - withOrder.length;
    console.log(`  有订单可核        ${String(withOrder.length).padStart(7)}  ${pct(withOrder.length, rows.length)}`);
    console.log(`  无订单可核        ${String(noOrder).padStart(7)}  ${pct(noOrder, rows.length)}   ← 需求方定：照记事件、标注「无订单可核」、不提醒`);

    // ── 步骤 4：偏离度分布 ───────────────────────────────────────────────────
    console.log("\n【步骤4】偏离度分布  |订单均价 - 挂牌价| / 挂牌价");
    type Ev = Row & { unit: number; dev: number; hasPromo: boolean };
    const evs: Ev[] = withOrder.map((r) => {
      const unit = Number(r.sales_amount) / Number(r.sales_qty);
      const price = Number(r.price_max);
      return { ...r, unit, dev: Math.abs(unit - price) / price, hasPromo: Number(r.discount_amount ?? 0) > 0 };
    });
    const buckets: [string, (d: number) => boolean][] = [
      ["完全一致 (=0)", (d) => d === 0],
      ["≤1%", (d) => d > 0 && d <= 0.01],
      ["1%~5%", (d) => d > 0.01 && d <= 0.05],
      ["5%~10%", (d) => d > 0.05 && d <= 0.10],
      ["10%~30%", (d) => d > 0.10 && d <= 0.30],
      [">30%", (d) => d > 0.30],
    ];
    console.log(`  ${"区间".padEnd(16)}${"全部".padStart(10)}${"无促销".padStart(12)}${"有促销".padStart(12)}`);
    const noPromo = evs.filter((e) => !e.hasPromo);
    const yesPromo = evs.filter((e) => e.hasPromo);
    for (const [label, f] of buckets) {
      const a = evs.filter((e) => f(e.dev)).length;
      const b = noPromo.filter((e) => f(e.dev)).length;
      const c = yesPromo.filter((e) => f(e.dev)).length;
      console.log(`  ${label.padEnd(16)}${`${a} ${pct(a, evs.length)}`.padStart(10)}${`${b} ${pct(b, noPromo.length)}`.padStart(14)}${`${c} ${pct(c, yesPromo.length)}`.padStart(14)}`);
    }
    const conflictAll = evs.filter((e) => e.dev > tol).length;
    const conflictClean = noPromo.filter((e) => e.dev > tol).length;
    console.log(`\n  conflict 率（阈值 ${(tol * 100).toFixed(1)}%）：全部 ${pct(conflictAll, evs.length)}  ｜  剔除促销后 ${pct(conflictClean, noPromo.length)}`);
    if (!hasPromo) console.log("  ⚠️ 促销表不存在，上面「无促销」列实为「未知促销状态」，该数字偏高属预期。");

    // ── 步骤 5：一天内多次快照且价不同 ───────────────────────────────────────
    const intraday = rows.filter((r) => r.price_min !== null && r.price_max !== null && Number(r.price_min) !== Number(r.price_max));
    console.log(`\n【步骤5】同一天内快照价不一致的行 = ${intraday.length}  ${pct(intraday.length, rows.length)}`);
    console.log("  （>0 说明当天改过价；这类行的订单均价必然混着改价前后的成交，不应计入 conflict）");
    for (const r of intraday.slice(0, 5)) {
      console.log(`    ${r.d} ${r.store_id} ${r.item_id} ${r.msku}  ${r.price_min} → ${r.price_max}`);
    }

    // ── 步骤 6：调价日专项 —— 这才是「辅助判断」规矩的真正考题 ─────────────────
    console.log("\n【步骤6】调价日专项：挂牌价相对前一快照日发生变化的行，订单均价跟没跟上");
    const byKey = new Map<string, Row[]>();
    for (const r of rows) {
      const k = `${r.store_id}|${r.item_id}|${r.msku}`;
      const arr = byKey.get(k); if (arr) arr.push(r); else byKey.set(k, [r]);
    }
    type Chg = { key: string; d: string; from: number; to: number; unitPrev: number | null; unitCurr: number | null };
    const changes: Chg[] = [];
    for (const [k, arr] of byKey) {
      for (let i = 1; i < arr.length; i++) {
        const prev = arr[i - 1], cur = arr[i];
        const p0 = Number(prev.price_max), p1 = Number(cur.price_max);
        if (!isFinite(p0) || !isFinite(p1) || p0 === p1) continue;
        const uPrev = Number(prev.sales_qty ?? 0) > 0 ? Number(prev.sales_amount) / Number(prev.sales_qty) : null;
        const uCurr = Number(cur.sales_qty ?? 0) > 0 ? Number(cur.sales_amount) / Number(cur.sales_qty) : null;
        changes.push({ key: k, d: String(cur.d), from: p0, to: p1, unitPrev: uPrev, unitCurr: uCurr });
      }
    }
    console.log(`  窗口内检出调价事件 = ${changes.length} 条（覆盖 ${new Set(changes.map((c) => c.key)).size} 个 店×item×msku）`);
    const bothSides = changes.filter((c) => c.unitPrev !== null && c.unitCurr !== null);
    const followed = bothSides.filter((c) => {
      const dirPrice = Math.sign(c.to - c.from);
      const dirUnit = Math.sign((c.unitCurr as number) - (c.unitPrev as number));
      return dirPrice === dirUnit;
    });
    console.log(`  其中前后两天都有订单、可以做旁证的 = ${bothSides.length}  ${pct(bothSides.length, changes.length)}`);
    console.log(`  旁证方向一致（订单均价与挂牌价同向变动）= ${followed.length}  ${pct(followed.length, bothSides.length)}`);
    console.log("  ⇒ 这个「同向率」就是「订单售价是否一致」这条辅助规矩的可信度上限。");
    console.log(`\n  调价事件明细（前 ${top} 条）：`);
    console.log(`    ${"日期".padEnd(12)}${"店|item|msku".padEnd(46)}${"挂牌价".padStart(18)}${"订单均价 前→后".padStart(22)}`);
    for (const c of changes.slice(0, top)) {
      const u = `${c.unitPrev === null ? "无单" : c.unitPrev.toFixed(2)} → ${c.unitCurr === null ? "无单" : c.unitCurr.toFixed(2)}`;
      console.log(`    ${c.d.padEnd(12)}${c.key.padEnd(46)}${`${c.from.toFixed(2)} → ${c.to.toFixed(2)}`.padStart(18)}${u.padStart(22)}`);
    }

    // ── 步骤 7：conflict 明细 ────────────────────────────────────────────────
    console.log(`\n【步骤7】conflict 明细（无促销、偏离最大的前 ${top} 条）`);
    const worst = [...noPromo].sort((a, b) => b.dev - a.dev).slice(0, top);
    console.log(`    ${"日期".padEnd(12)}${"店|item|msku".padEnd(46)}${"挂牌价".padStart(10)}${"订单均价".padStart(12)}${"件数".padStart(7)}${"偏离".padStart(10)}`);
    for (const e of worst) {
      console.log(`    ${String(e.d).padEnd(12)}${`${e.store_id}|${e.item_id}|${e.msku}`.padEnd(46)}` +
        `${Number(e.price_max).toFixed(2).padStart(10)}${e.unit.toFixed(2).padStart(12)}${String(e.sales_qty).padStart(7)}${`${(e.dev * 100).toFixed(1)}%`.padStart(10)}`);
    }

    // ── 步骤 8：结论 ─────────────────────────────────────────────────────────
    console.log("\n【步骤8】结论（供需求方拍板）");
    console.log(`  ① 快照日中「无订单可核」占 ${pct(noOrder, rows.length)} —— 这部分只能记事件、不能核价。`);
    console.log(`  ② 有订单的行里，剔除促销后 conflict 率 = ${pct(conflictClean, noPromo.length)}（阈值 ${(tol * 100).toFixed(1)}%）。`);
    console.log(`  ③ 调价事件 ${changes.length} 条，可旁证 ${bothSides.length} 条，同向率 ${pct(followed.length, bothSides.length)}。`);
    console.log("  ④ 判读方法：同向率高 → 旁证规矩可用，作为「调价事件」的置信度加成；");
    console.log("     同向率低 → 说明订单均价受促销/多件/日界干扰太大，只能当参考，不能当判据。");
  } catch (e) {
    console.error(`✗ 探测异常: ${e instanceof Error ? e.message : String(e)}`);
    console.error("  按规矩：报错的查询不得用于支撑任何结论（API_MAP §6-1）。");
  } finally {
    await db.end().catch(() => undefined);
  }
}

main().catch((e: unknown) => { console.error("探测脚本异常:", e); process.exit(1); });
