/**
 * src/probeFactAdsProductDailyAudit.ts
 *
 * 单品现金利润模块 · 探针13 —— fact_ads_product_daily（商品广告事实表）完整性审计
 * （纯只读DB SELECT，不调任何API，零写库，零改动生产）。
 *
 * 背景（重大发现）：
 *   syncLingxingDailyToDb.ts 第4步每天调 reportAdItemSpList、参数已是
 *   ["sponsoredProducts-manual","sponsoredProducts-auto"]，按天按ItemID写 fact_ads_product_daily
 *   ——即探针10验证的"正确修法"在这条管道早已在跑。若数据完整且准确，keyword表的V3改造
 *   根本不需要做，AI财务模块直接读本表。
 *
 * 待验证三件事：
 *   ① 金额准不准：CN2601 窗口1(2026-07-10~07-15) 本表SUM(ad_spend) 应≈$6059.69
 *      （探针10实时API基准：manual $4482.86 + auto $1576.83）；目标自动活动
 *      campaignId=5032288("YC00029-自动-5.03") 窗口1应≈$102.44（真实发票值）。
 *   ② 自动广告从哪天开始有：若auto参数是7月中途才加的，早期自动广告缺失。
 *      用两个信号判断：a) 5032288 在本表的最早stat_date与逐日金额；
 *      b) CN2601 七月逐日总额曲线（auto加入当天总额会跳升~35%）。
 *   ③ 覆盖完整性：各店铺 min/max stat_date、七月缺天清单。
 *
 * 运行（生产机，由部署工程师执行）：
 *   npx ts-node src/probeFactAdsProductDailyAudit.ts
 *
 * 用法：把完整输出贴回来，重点看"二、窗口1三方对照"和"三、七月逐日"。
 */

import "dotenv/config";
import * as mysql from "mysql2/promise";

const W1 = { startDate: "2026-07-10", endDate: "2026-07-15" };
const API_BENCH = { total: 6059.69, manual: 4482.86, auto: 1576.83 };
const TARGET_CAMPAIGN_ID = "5032288";
const TARGET_REAL = 102.44;

function toNum(v: unknown): number {
  const n = Number(v);
  return Number.isFinite(n) ? n : 0;
}
function toDateStr(v: unknown): string {
  if (typeof v === "string") return v.slice(0, 10);
  if (v instanceof Date) {
    const d = new Date(v.getTime() - v.getTimezoneOffset() * 60000);
    return d.toISOString().slice(0, 10);
  }
  return String(v ?? "").slice(0, 10);
}

async function main() {
  const db = await mysql.createConnection({
    host: process.env.DB_HOST ?? "127.0.0.1",
    port: Number(process.env.DB_PORT ?? 3306),
    user: process.env.DB_USER ?? "",
    password: process.env.DB_PASSWORD ?? "",
    database: process.env.DB_NAME ?? "walmart_ai_data",
  });

  const [storeRows] = await db.execute(
    `SELECT store_id, store_name FROM dim_store_config WHERE platform='walmart' AND store_name LIKE '%瑞盈龙盛%'`,
  );
  const stores = storeRows as Array<{ store_id: string; store_name: string }>;
  if (stores.length === 0) { console.log("没匹配到店铺，终止。"); await db.end(); return; }
  const storeId = stores[0].store_id;
  console.log(`目标店铺: store_id=${storeId} (${stores[0].store_name})\n`);

  // 一、全店铺覆盖概览
  console.log("=== 一、fact_ads_product_daily 全店铺覆盖概览 ===\n");
  const [cov] = await db.execute(
    `SELECT store_id, MAX(store_name) AS store_name, MIN(stat_date) AS min_d, MAX(stat_date) AS max_d,
            COUNT(DISTINCT stat_date) AS day_cnt, COUNT(*) AS cnt, ROUND(SUM(ad_spend),2) AS spend
       FROM fact_ads_product_daily WHERE platform='walmart'
      GROUP BY store_id ORDER BY spend DESC`,
  );
  console.log("store_id".padEnd(22) + "覆盖".padEnd(25) + "天数".padEnd(6) + "行数".padEnd(9) + "spend$".padEnd(12) + "店铺名");
  for (const r of cov as Array<Record<string, unknown>>) {
    console.log(
      String(r.store_id).padEnd(22) + (toDateStr(r.min_d) + "~" + toDateStr(r.max_d)).padEnd(25) +
      String(r.day_cnt).padEnd(6) + String(r.cnt).padEnd(9) + String(r.spend).padEnd(12) + String(r.store_name),
    );
  }

  // 二、窗口1三方对照
  console.log(`\n=== 二、CN2601 窗口1(${W1.startDate}~${W1.endDate}) 对照探针10 API基准 ===\n`);
  const [w1rows] = await db.execute(
    `SELECT ROUND(SUM(ad_spend),2) AS spend, COUNT(*) AS cnt, COUNT(DISTINCT campaign_id) AS camp_cnt
       FROM fact_ads_product_daily WHERE store_id=? AND stat_date BETWEEN ? AND ?`,
    [storeId, W1.startDate, W1.endDate],
  );
  const w1 = (w1rows as Array<Record<string, unknown>>)[0];
  const w1spend = toNum(w1?.spend);
  console.log(`本表窗口1合计: $${w1spend.toFixed(2)}  行数=${w1?.cnt}  活动数=${w1?.camp_cnt}`);
  console.log(`API基准: 总$${API_BENCH.total}（manual $${API_BENCH.manual} + auto $${API_BENCH.auto}）  占比=${((w1spend / API_BENCH.total) * 100).toFixed(1)}%`);
  console.log(`[判读] ≈100%=手动+自动都全；≈74%(=4482.86/6059.69)=只有手动、auto缺；其他值=部分缺失`);

  const [tgt] = await db.execute(
    `SELECT DATE_FORMAT(stat_date,'%Y-%m-%d') AS d, ROUND(SUM(ad_spend),2) AS spend, COUNT(*) AS cnt
       FROM fact_ads_product_daily WHERE store_id=? AND campaign_id=? AND stat_date BETWEEN ? AND ?
      GROUP BY stat_date ORDER BY stat_date`,
    [storeId, TARGET_CAMPAIGN_ID, W1.startDate, W1.endDate],
  );
  const tgtRows = tgt as Array<{ d: string; spend: string; cnt: number }>;
  const tgtSum = tgtRows.reduce((a, r) => a + toNum(r.spend), 0);
  console.log(`\n目标自动活动 campaignId=${TARGET_CAMPAIGN_ID}("YC00029-自动-5.03") 窗口1:`);
  if (tgtRows.length === 0) console.log("  [本表窗口1完全没有此活动 → auto当时未入库]");
  for (const r of tgtRows) console.log(`  ${r.d}  $${toNum(r.spend).toFixed(2)}  行数=${r.cnt}`);
  console.log(`  合计=$${tgtSum.toFixed(2)}（真实发票$${TARGET_REAL}，占比${((tgtSum / TARGET_REAL) * 100).toFixed(1)}%）`);

  // 三、该自动活动全历史 + CN2601七月逐日
  console.log(`\n=== 三、auto入库起点定位 ===\n`);
  const [tgtHist] = await db.execute(
    `SELECT MIN(stat_date) AS min_d, MAX(stat_date) AS max_d, COUNT(DISTINCT stat_date) AS day_cnt, ROUND(SUM(ad_spend),2) AS spend
       FROM fact_ads_product_daily WHERE store_id=? AND campaign_id=?`,
    [storeId, TARGET_CAMPAIGN_ID],
  );
  const th = (tgtHist as Array<Record<string, unknown>>)[0];
  console.log(`campaignId=${TARGET_CAMPAIGN_ID} 在本表全历史: ${toDateStr(th?.min_d)} ~ ${toDateStr(th?.max_d)}，覆盖${th?.day_cnt}天，累计$${th?.spend}`);
  console.log(`→ 最早日期即"auto参数生效日"（若晚于7-01，之前的自动广告需回填）\n`);

  console.log(`CN2601 七月至今逐日（总额跳升~35%的那天=auto加入日；接近$0或缺行的天=当天同步缺失）:`);
  const [jul] = await db.execute(
    `SELECT DATE_FORMAT(stat_date,'%Y-%m-%d') AS d, ROUND(SUM(ad_spend),2) AS spend, COUNT(*) AS cnt,
            COUNT(DISTINCT campaign_id) AS camp_cnt,
            ROUND(SUM(CASE WHEN campaign_id=? THEN ad_spend ELSE 0 END),2) AS tgt_spend
       FROM fact_ads_product_daily WHERE store_id=? AND stat_date >= '2026-07-01'
      GROUP BY stat_date ORDER BY stat_date`,
    [TARGET_CAMPAIGN_ID, storeId],
  );
  console.log("日期".padEnd(13) + "总spend$".padEnd(11) + "行数".padEnd(7) + "活动数".padEnd(8) + "5032288$");
  for (const r of jul as Array<{ d: string; spend: string; cnt: number; camp_cnt: number; tgt_spend: string }>) {
    console.log(r.d.padEnd(13) + toNum(r.spend).toFixed(2).padEnd(11) + String(r.cnt).padEnd(7) + String(r.camp_cnt).padEnd(8) + toNum(r.tgt_spend).toFixed(2));
  }

  // 四、七月缺天清单（全店铺）
  console.log(`\n=== 四、七月缺天清单（各店铺 2026-07-01~2026-07-31 无任何行的天）===\n`);
  for (const s of cov as Array<Record<string, unknown>>) {
    const sid = String(s.store_id);
    const [dRows] = await db.execute(
      `SELECT DISTINCT DATE_FORMAT(stat_date,'%Y-%m-%d') AS d FROM fact_ads_product_daily
        WHERE store_id=? AND stat_date BETWEEN '2026-07-01' AND '2026-07-31'`,
      [sid],
    );
    const have = new Set((dRows as Array<{ d: string }>).map((r) => r.d));
    const missing: string[] = [];
    for (let day = 1; day <= 31; day++) {
      const d = `2026-07-${String(day).padStart(2, "0")}`;
      if (!have.has(d)) missing.push(d.slice(8));
    }
    console.log(`${String(s.store_name).padEnd(30)} 七月缺天: ${missing.length === 0 ? "无（31天全覆盖）" : missing.join(",") + "日"}`);
  }

  await db.end();
  console.log("\n探针13结束。");
}

main().catch((err) => {
  console.error("探针13执行失败：", err);
  process.exit(1);
});
