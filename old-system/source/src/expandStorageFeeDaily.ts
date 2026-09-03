/**
 * expandStorageFeeDaily.ts — 仓储费日摊展开（订单利润V2·批2，2026-08-18；2026-08-19 分段升级）
 *
 * 数据流：
 *   步骤0  statement RAW(raw_lingxing_api) → fact_storage_weekly_charge（结算周实扣，店铺×7天周期间）
 *   步骤1  fact_wfs_storage_fee（账期14/28天）→ fact_storage_fee_daily（日粒度）
 *          分段模式：账期能被完整覆盖的结算周（每段7天、Σ周实扣与账期总额差≤$0.05）→ 按周实扣金额
 *          分段、段内均摊、末段吸收对账期总额的舍入差 → 任意结算周窗口可与店铺后台对账单精确对平。
 *          回退模式：周数据缺失/不守恒/账期非7天倍数 → 整期均摊（2026-08-18 原行为），SUMMARY 计数。
 *
 * 口径（需求方 2026-08-14/17 定稿·账单驱动式；2026-08-19 分段升级拍板）：
 *   - CSV导入新账期后运行本脚本 → 全量重展开 → 利润实时查询自动生效
 *   - 账期守恒不变量：逐期 |Σ日摊-账期额|<0.01、总额差<0.05（哨兵第⑦依赖，分段不破坏）
 *   - 仓储费列是"历史不回改"的显式例外：新账单导入仅动仓储费列，其余列不回改
 *   - 幂等：同(store,sku,fee_date)重复运行覆盖同值
 *   - store_id 取请求侧 sids[0] 原文正则提取；禁读响应行 storeId（JSON double 丢精度，探针实证）
 *   - 行级去重键 (sid,ps,pe,amount,reportKey)：防 RAW 同行多页重复留存（HK2615 实证）
 * 用法：
 *   npx ts-node src/expandStorageFeeDaily.ts                  # dry-run 零写入（周费提取与分段均只预览）
 *   npx ts-node src/expandStorageFeeDaily.ts --confirm-write  # 真写：upsert周费表 + 全量重展开日摊表
 */
import "dotenv/config";
import * as mysql from "mysql2/promise";

const STATEMENT_PATH = "/basicOpen/multiplatformFinance/walmart/bill/statement/list";

function getDb(): Promise<mysql.Connection> {
  return mysql.createConnection({
    host: process.env.DB_HOST ?? "127.0.0.1",
    port: Number(process.env.DB_PORT ?? 3306),
    user: process.env.DB_USER ?? "",
    password: process.env.DB_PASSWORD ?? "",
    database: process.env.DB_NAME ?? "walmart_ai_data",
  });
}
function addDays(date: string, n: number): string {
  return new Date(Date.parse(`${date}T00:00:00Z`) + n * 86400000).toISOString().slice(0, 10);
}
const r5 = (n: number): number => Math.round(n * 100000) / 100000;
const r2 = (n: number): number => Math.round(n * 100) / 100;

interface WeeklyCharge { sid: string; ps: string; pe: string; amount: number; txnRows: number; reportKey: string; reportDate: string }

/** 步骤0：statement RAW → 周实扣聚合（内存返回；confirmWrite 时同步 upsert fact_storage_weekly_charge） */
async function extractWeeklyCharges(db: mysql.Connection, confirmWrite: boolean): Promise<Map<string, WeeklyCharge>> {
  const seen = new Set<string>();                 // 行级去重 (sid|ps|pe|amount|reportKey)
  const agg = new Map<string, WeeklyCharge>();    // (sid|ps|pe) → 求和
  let pages = 0, lastId = 0, noSidPages = 0, parseFailPages = 0;
  for (;;) {
    // ⚠️ 必须 CAST(... AS CHAR) 取原文字符串：mysql2 对 JSON 类型列会自动 parse 成对象，
    // String(对象)='[object Object]' 会让下游解析静默归零（2026-08-19 部署 dry-run 闸门实测拦截）；
    // 且原文字符串才能对 sids 做正则提取，避免 JSON.parse 数字经 double 丢精度。
    const [rows] = await db.execute(
      `SELECT id, CAST(request_params_json AS CHAR) AS req_txt, CAST(response_json AS CHAR) AS resp_txt
       FROM raw_lingxing_api WHERE api_path = ? AND id > ? ORDER BY id LIMIT 100`,
      [STATEMENT_PATH, lastId]);
    const batch = rows as Array<{ id: number; req_txt: string; resp_txt: string }>;
    if (batch.length === 0) break;
    for (const page of batch) {
      lastId = page.id;
      pages += 1;
      // 请求侧 sids[0] 原文正则提取（兼容 "123"/123 两种形态）
      const m = /"sids"\s*:\s*\[\s*"?(\d+)"?/.exec(String(page.req_txt ?? ""));
      const sid = m ? m[1] : "";
      if (!sid) { noSidPages += 1; continue; }
      let list: Array<Record<string, unknown>> = [];
      try {
        const data = JSON.parse(String(page.resp_txt ?? "null")) as { list?: unknown } | null;
        if (Array.isArray(data?.list)) list = data!.list as Array<Record<string, unknown>>;
      } catch { parseFailPages += 1; continue; }
      for (const row of list) {
        if (String(row.transactionType ?? "") !== "Service Fee") continue;
        if (String(row.transactionDescription ?? "") !== "WFS StorageFee") continue;
        const ps = String(row.periodStartDate ?? "").slice(0, 10);
        const pe = String(row.periodEndDate ?? "").slice(0, 10);
        const amt = Number(row.amount);
        if (!/^\d{4}-\d{2}-\d{2}$/.test(ps) || !/^\d{4}-\d{2}-\d{2}$/.test(pe) || !Number.isFinite(amt)) continue;
        const reportKey = String(row.reportKey ?? "");
        const dedupKey = `${sid}|${ps}|${pe}|${amt}|${reportKey}`;
        if (seen.has(dedupKey)) continue;
        seen.add(dedupKey);
        const aggKey = `${sid}|${ps}|${pe}`;
        const cur = agg.get(aggKey);
        if (cur) { cur.amount = r2(cur.amount + Math.abs(amt)); cur.txnRows += 1; }
        else agg.set(aggKey, { sid, ps, pe, amount: r2(Math.abs(amt)), txnRows: 1, reportKey, reportDate: String(row.reportDate ?? "").slice(0, 10) });
      }
    }
  }
  if (confirmWrite) {
    for (const w of agg.values()) {
      await db.execute(
        `INSERT INTO fact_storage_weekly_charge
           (platform, store_id, period_start, period_end, amount, txn_rows, report_key, report_date)
         VALUES ('walmart', ?, ?, ?, ?, ?, ?, ?)
         ON DUPLICATE KEY UPDATE
           amount=VALUES(amount), txn_rows=VALUES(txn_rows), report_key=VALUES(report_key), report_date=VALUES(report_date)`,
        [w.sid, w.ps, w.pe, w.amount, w.txnRows, w.reportKey, w.reportDate || null]);
    }
  }
  console.log(`步骤0 周实扣提取：raw页 ${pages}｜周行 ${agg.size}｜无sid页 ${noSidPages}｜解析失败页 ${parseFailPages}｜write=${confirmWrite}`);
  if (pages > 0 && agg.size === 0) {
    console.warn("WARN: statement RAW 有页但提取到 0 条周实扣——解析链疑似失效，本次全部账期将回退整期均摊，请核查！");
  }
  return agg;
}

async function main(): Promise<void> {
  const confirmWrite = process.argv.includes("--confirm-write");
  const db = await getDb();
  let periods = 0, rowsExpanded = 0, badDays = 0, collisions = 0;
  let segmented = 0, fallbackUniform = 0;
  let feeTotalSrc = 0, feeTotalDaily = 0;
  try {
    const weekly = await extractWeeklyCharges(db, confirmWrite);

    const [rows] = await db.execute(
      `SELECT platform, store_id, sku, gtin, item_id,
              DATE_FORMAT(report_start,'%Y-%m-%d') rs, DATE_FORMAT(report_end,'%Y-%m-%d') re,
              days_in_period, final_storage_fee
       FROM fact_wfs_storage_fee ORDER BY report_start, store_id, sku`);
    const src = rows as Array<Record<string, unknown>>;
    console.log(`步骤1 源账期行 ${src.length} 条｜write=${confirmWrite}`);

    // 账期级分段方案缓存：同(store,rs,re)的所有SKU行共用同一套段权重
    const segPlanCache = new Map<string, number[] | null>(); // key=store|rs|re → 各段周实扣额(总和=各段原值),null=回退均摊
    const segPlanOf = (storeId: string, rs: string, re: string): number[] | null => {
      const key = `${storeId}|${rs}|${re}`;
      if (segPlanCache.has(key)) return segPlanCache.get(key)!;
      let plan: number[] | null = null;
      const spanDays = Math.round((Date.parse(re) - Date.parse(rs)) / 86400000) + 1;
      if (spanDays > 0 && spanDays % 7 === 0) {
        const segs = spanDays / 7;
        const amts: number[] = [];
        for (let k = 0; k < segs; k++) {
          const ps = addDays(rs, k * 7);
          const w = weekly.get(`${storeId}|${ps}|${addDays(ps, 6)}`);
          if (!w) { break; }
          amts.push(w.amount);
        }
        if (amts.length === segs) plan = amts; // 守恒校验在具体账期行级做（对店铺级周费 vs SKU行聚合额）
      }
      segPlanCache.set(key, plan);
      return plan;
    };
    // 店铺×账期的SKU行合计（分段守恒校验用：周实扣是店铺级，须对店铺级账期总额校验）
    const periodTotal = new Map<string, number>();
    for (const r of src) {
      const key = `${r.store_id}|${r.rs}|${r.re}`;
      periodTotal.set(key, r2((periodTotal.get(key) ?? 0) + Number(r.final_storage_fee)));
    }
    const planValid = new Map<string, boolean>(); // 店铺级守恒判定缓存
    const planValidOf = (storeId: string, rs: string, re: string): boolean => {
      const key = `${storeId}|${rs}|${re}`;
      if (planValid.has(key)) return planValid.get(key)!;
      const plan = segPlanOf(storeId, rs, re);
      let ok = false;
      if (plan) {
        const sumW = r2(plan.reduce((s, a) => s + a, 0));
        const tot = periodTotal.get(key) ?? 0;
        ok = Math.abs(sumW - tot) <= 0.05;
      }
      planValid.set(key, ok);
      return ok;
    };

    const seen = new Map<string, string>(); // (store|sku|date) → 账期，检测跨账期同日碰撞
    for (const r of src) {
      periods += 1;
      const rs = String(r.rs), re = String(r.re);
      const storeId = String(r.store_id);
      const fee = Number(r.final_storage_fee);
      feeTotalSrc += fee;
      let days = Math.round(Number(r.days_in_period));
      const spanDays = Math.round((Date.parse(re) - Date.parse(rs)) / 86400000) + 1;
      if (days <= 0 || spanDays <= 0) { badDays += 1; days = Math.max(spanDays, 1); }
      if (days !== spanDays && spanDays > 0) days = spanDays; // 以账期实际跨度为准，days_in_period仅参考

      // ── 分段权重：店铺级周实扣占比 → 应用到本SKU行金额；否则整期均摊 ──
      let segWeights: number[] | null = null; // 每段占账期的比例
      if (planValidOf(storeId, rs, re)) {
        const plan = segPlanOf(storeId, rs, re)!;
        const sumW = plan.reduce((s, a) => s + a, 0);
        if (sumW > 0) { segWeights = plan.map((a) => a / sumW); segmented += 1; }
      }
      if (!segWeights) fallbackUniform += 1;

      // 段金额（SKU行级）：前 n-1 段按权重取5位小数，末段=fee-Σ前段（吸收舍入，保证账期守恒）
      const nSegs = segWeights ? segWeights.length : 1;
      const segDays = days / nSegs; // 分段模式下必为7；均摊模式=days
      const segAmts: number[] = [];
      if (segWeights) {
        let accSeg = 0;
        for (let k = 0; k < nSegs - 1; k++) { const a = r5(fee * segWeights[k]); segAmts.push(a); accSeg = r5(accSeg + a); }
        segAmts.push(r5(fee - accSeg));
      } else {
        segAmts.push(fee);
      }

      let acc = 0;
      for (let k = 0; k < segAmts.length; k++) {
        const segFee = segAmts[k];
        const dCount = segWeights ? 7 : days;
        const perDay = Math.floor((segFee / dCount) * 100000) / 100000; // 5位小数向下取
        let accSegDaily = 0;
        for (let i = 0; i < dCount; i++) {
          const feeDate = addDays(rs, k * segDays + i);
          const isLastOfSeg = i === dCount - 1;
          const dailyFee = isLastOfSeg ? r5(segFee - accSegDaily) : perDay; // 段末日吸收舍入差
          accSegDaily = r5(accSegDaily + dailyFee);
          acc = r5(acc + dailyFee);
          const key = `${storeId}|${r.sku}|${feeDate}`;
          const prev = seen.get(key);
          if (prev && prev !== `${rs}~${re}`) collisions += 1;
          seen.set(key, `${rs}~${re}`);
          if (confirmWrite) {
            await db.execute(
              `INSERT INTO fact_storage_fee_daily
                 (platform, store_id, sku, gtin, item_id, fee_date, storage_fee, report_start, report_end, days_in_period)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON DUPLICATE KEY UPDATE
                 gtin=VALUES(gtin), item_id=VALUES(item_id), storage_fee=VALUES(storage_fee),
                 report_start=VALUES(report_start), report_end=VALUES(report_end), days_in_period=VALUES(days_in_period)`,
              [String(r.platform), storeId, String(r.sku), String(r.gtin), String(r.item_id),
               feeDate, dailyFee, rs, re, days]);
          }
          rowsExpanded += 1;
          feeTotalDaily += dailyFee;
        }
      }
      if (Math.abs(acc - fee) >= 0.01) {
        throw new Error(`账期守恒失败: ${storeId}/${r.sku} ${rs}~${re} Σ日摊=${acc} vs 账期=${fee}`);
      }
    }
    feeTotalSrc = r2(feeTotalSrc);
    feeTotalDaily = r2(feeTotalDaily);
    console.log("SUMMARY_JSON=" + JSON.stringify({
      dryRun: !confirmWrite, periods, rows_expanded: rowsExpanded,
      fee_total_src: feeTotalSrc, fee_total_daily: feeTotalDaily,
      segmented_rows: segmented, fallback_uniform_rows: fallbackUniform,
      weekly_charge_rows: weekly.size,
      bad_days_rows: badDays, cross_period_collisions: collisions, status: "success",
    }));
    if (Math.abs(feeTotalSrc - feeTotalDaily) >= 0.05) {
      throw new Error(`总额守恒失败: 源=${feeTotalSrc} vs 日摊合计=${feeTotalDaily}`);
    }
  } finally {
    await db.end();
  }
}
main().catch((e) => { console.error("FATAL:", e instanceof Error ? e.message : String(e)); process.exit(1); });
