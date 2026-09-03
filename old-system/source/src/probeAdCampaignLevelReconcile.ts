/**
 * src/probeAdCampaignLevelReconcile.ts
 *
 * 单品现金利润模块 · 探针7 —— 探针6发现 fact_ads_keyword_daily 跟真实发票对不上（窗口1只有
 * 真实值的70.5%，窗口2只有85.1%，窗口3反而多到172.6%），本探针往下深挖差异是"整体口径偏差"
 * 还是"部分广告类型完全没同步"（只读，零写库，零改动生产）。
 *
 * 背景（探针6原始结论，来自CN2601-瑞盈龙盛真实生产数据）：
 *   窗口1(07-10~07-15) 真实发票$6607.08，fact_ads_keyword_daily合计$4659.00（70.5%）
 *   窗口2(07-16~07-22) 真实发票$6977.20，fact_ads_keyword_daily合计$5936.77（85.1%）
 *   窗口3(07-22~07-23) 真实发票 $846.32，fact_ads_keyword_daily合计$1460.40（172.6%）
 *   fact_ads_keyword_daily 两路来源：source_type=manual_kw(经领星API同步) + walmart_auto_csv(人工CSV导入)。
 *   一个怀疑：这3张真实发票里出现了"YC00019-SBV-5.11-TEST"这个广告活动（SBV=Sponsored Brand
 *   Video，一种跟"手动关键词广告(sponsoredProducts-manual)"完全不同的广告产品类型），窗口1里这一个
 *   活动就占了$345.32，窗口2占$372.60——如果 fact_ads_keyword_daily 的同步逻辑只覆盖
 *   manual关键词广告+CSV导入的自动广告，没覆盖SBV这类广告，就能部分解释窗口1/2为什么系统性偏低。
 *   窗口3反而偏高172.6%，怀疑是CSV导入口径的统计日期跟发票账期边界没对齐，或者有重复计入。
 *
 * 本探针做的事（比探针6更细）：
 *   1) 逐个真实广告活动核对：从3张真实Walmart Connect发票里人工摘取18条真实
 *      (campaign_id, 真实发票金额, 所属窗口) 样本（覆盖自动/手动/精准/广泛/词组/AI筛选词/SBV
 *      多种类型），逐条去 fact_ads_keyword_daily 按 campaign_id + 日期窗口查 SUM(ad_spend)，
 *      跟真实发票金额逐条对比——能揪出"这个活动到底有没有同步/同步得准不准"。
 *   2) 每个窗口整体按 campaign_type + source_type 分组打印 SUM(ad_spend) 和涉及活动数，
 *      直接看有没有 SBV/Sponsored Brand 这类广告类型完全缺席。
 *
 * 安全边界：只读 DB SELECT，零写库、零改动生产、不建表。
 *
 * 运行（生产机，由部署工程师执行）：
 *   npx ts-node src/probeAdCampaignLevelReconcile.ts
 *
 * 用法：把完整输出贴回来，重点看①逐活动核对表里有没有"[缺失]"标记的活动，
 *      ②按campaign_type分组的列表里有没有SBV相关类型。
 */

import "dotenv/config";
import * as mysql from "mysql2/promise";

// 3张真实发票里人工摘取的样本（campaign_id, 真实发票金额, 广告活动名, 所属窗口标签）
const SAMPLE_CAMPAIGNS: Array<{ campaignId: string; realAmount: number; name: string; window: string }> = [
  // 窗口1: 2026-07-10 ~ 2026-07-15 (发票78430539, 总额$6607.08)
  { campaignId: "9879914",  realAmount: 15.16,  name: "YC00032-自动4.07",        window: "w1" },
  { campaignId: "9879926",  realAmount: 20.89,  name: "YC00032-词组4.07",        window: "w1" },
  { campaignId: "9914192",  realAmount: 121.57, name: "YC00017-精准-4.20-M",     window: "w1" },
  { campaignId: "9958450",  realAmount: 102.44, name: "YC00029-自动-5.03",       window: "w1" },
  { campaignId: "9982173",  realAmount: 345.32, name: "YC00019-SBV-5.11-TEST",   window: "w1" },
  { campaignId: "9986262",  realAmount: 67.65,  name: "JJ4035-手动-KY-5.12",     window: "w1" },
  // 窗口2: 2026-07-16 ~ 2026-07-22 (发票78597070, 总额$6977.20)
  { campaignId: "9879914",  realAmount: 25.38,  name: "YC00032-自动4.07",        window: "w2" },
  { campaignId: "9914192",  realAmount: 119.01, name: "YC00017-精准-4.20-M",     window: "w2" },
  { campaignId: "9958450",  realAmount: 83.89,  name: "YC00029-自动-5.03",       window: "w2" },
  { campaignId: "9982173",  realAmount: 372.60, name: "YC00019-SBV-5.11-TEST",   window: "w2" },
  { campaignId: "9986262",  realAmount: 89.53,  name: "JJ4035-手动-KY-5.12",     window: "w2" },
  { campaignId: "11100743", realAmount: 100.15, name: "YC00108-自动-ky-6/22",    window: "w2" },
  // 窗口3: 2026-07-22 ~ 2026-07-23 (发票78597073, 总额$846.32)
  { campaignId: "11260844", realAmount: 8.21,   name: "JJ2080-AI筛选词-JZB-7.22", window: "w3" },
  { campaignId: "11131147", realAmount: 25.98,  name: "YC00029-广泛-拓-6.26",    window: "w3" },
  { campaignId: "11260778", realAmount: 0.46,   name: "JJ2080-自动出单词-JZB-7.22", window: "w3" },
  { campaignId: "11249024", realAmount: 6.20,   name: "JJ5024-AI筛选词-JZB-7.21", window: "w3" },
  { campaignId: "11253331", realAmount: 6.27,   name: "JJ5102-自动(重开)-YJ-0722", window: "w3" },
  { campaignId: "11253955", realAmount: 3.01,   name: "YC00027-自动-ZMS-0722",   window: "w3" },
];

const WINDOWS: Record<string, { label: string; startDate: string; endDate: string }> = {
  w1: { label: "窗口1", startDate: "2026-07-10", endDate: "2026-07-15" },
  w2: { label: "窗口2", startDate: "2026-07-16", endDate: "2026-07-22" },
  w3: { label: "窗口3", startDate: "2026-07-22", endDate: "2026-07-23" },
};

function toNum(v: unknown): number {
  const n = Number(v);
  return Number.isFinite(n) ? n : 0;
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
    `SELECT store_id, store_name FROM dim_store_config WHERE platform = 'walmart' AND store_name LIKE '%瑞盈龙盛%'`,
  );
  const stores = storeRows as Array<{ store_id: string; store_name: string }>;
  if (stores.length === 0) {
    console.log("没匹配到 CN2601-瑞盈龙盛 店铺，终止。");
    await db.end();
    return;
  }
  const storeId = stores[0].store_id;
  console.log(`目标店铺: store_id=${storeId} (${stores[0].store_name})\n`);

  console.log("=== 一、逐广告活动核对（campaign_id级别，直接对真实发票金额）===\n");
  console.log(
    "campaign_id".padEnd(12) + "窗口".padEnd(6) + "真实发票$".padEnd(11) +
    "fact_ads_keyword_daily$".padEnd(25) + "差值".padEnd(10) + "占比".padEnd(8) + "活动名/覆盖情况",
  );
  let missingCount = 0;
  for (const c of SAMPLE_CAMPAIGNS) {
    const w = WINDOWS[c.window];
    const [rows] = await db.execute(
      `SELECT SUM(ad_spend) AS spend, COUNT(*) AS cnt,
              GROUP_CONCAT(DISTINCT campaign_type) AS ctypes,
              GROUP_CONCAT(DISTINCT source_type) AS stypes
         FROM fact_ads_keyword_daily
        WHERE store_id = ? AND campaign_id = ? AND stat_date BETWEEN ? AND ?`,
      [storeId, c.campaignId, w.startDate, w.endDate],
    );
    const r = (rows as Array<{ spend: string | null; cnt: number; ctypes: string | null; stypes: string | null }>)[0];
    const factSpend = toNum(r?.spend);
    const cnt = r?.cnt ?? 0;
    const diff = factSpend - c.realAmount;
    const pct = c.realAmount > 0 ? ((factSpend / c.realAmount) * 100).toFixed(0) + "%" : "-";
    const tag = cnt === 0 ? "[缺失·完全没同步]" : `type=${r?.ctypes ?? "-"} src=${r?.stypes ?? "-"} 行数=${cnt}`;
    if (cnt === 0) missingCount++;
    console.log(
      c.campaignId.padEnd(12) + w.label.padEnd(6) + c.realAmount.toFixed(2).padEnd(11) +
      factSpend.toFixed(2).padEnd(25) + diff.toFixed(2).padEnd(10) + pct.padEnd(8) + `${c.name} ${tag}`,
    );
  }
  console.log(`\n样本共${SAMPLE_CAMPAIGNS.length}条，完全缺失(0行)的有${missingCount}条。`);

  console.log("\n\n=== 二、每个窗口按 campaign_type + source_type 分组总览（看SBV等类型是否缺席）===");
  for (const key of Object.keys(WINDOWS)) {
    const w = WINDOWS[key];
    console.log(`\n--- ${w.label} ${w.startDate}~${w.endDate} ---`);
    const [rows] = await db.execute(
      `SELECT campaign_type, source_type, SUM(ad_spend) AS spend, COUNT(DISTINCT campaign_id) AS campaign_cnt
         FROM fact_ads_keyword_daily
        WHERE store_id = ? AND stat_date BETWEEN ? AND ?
        GROUP BY campaign_type, source_type
        ORDER BY spend DESC`,
      [storeId, w.startDate, w.endDate],
    );
    const typed = rows as Array<{ campaign_type: string; source_type: string; spend: string | null; campaign_cnt: number }>;
    if (typed.length === 0) {
      console.log("  [无数据]");
    }
    for (const r of typed) {
      console.log(`  campaign_type=${r.campaign_type ?? "(空)"}  source_type=${r.source_type}  spend=${toNum(r.spend).toFixed(2)}  活动数=${r.campaign_cnt}`);
    }
  }

  await db.end();
  console.log("\n探针7结束。");
}

main().catch((err) => {
  console.error("探针7执行失败：", err);
  process.exit(1);
});
