/**
 * src/probeAutoCsvCoverageAndRatio.ts
 *
 * 单品现金利润模块 · 探针12 —— 自动广告CSV路"日期覆盖异常"与"66.7%比例稳定性"核查
 * （只读，零写库，零改动生产）。
 *
 * 背景（探针11结论，需求方指示再探一轮后拍板）：
 *   窗口1(2026-07-10~07-15) CSV路(source_type='walmart_auto_csv')只在07-14落了一天数据
 *   $176.14，其余5天全为$0；但该店铺CSV全历史覆盖显示 07-11~07-31 有18个覆盖天——
 *   说明日期覆盖有异常（导入缺天？还是导入时stat_date打的日期跟报表实际日期有偏差？）。
 *   另外07-14当天 CSV=$176.14 vs API当天=$264.15 = 66.7%，疑似"搜索词报告天生不含
 *   全部花费"的天花板，但只有一天样本，需要看其他覆盖天这个比例是否稳定。
 *
 * 本探针做的事：
 *   一、CSV路全景（CN2601）：按 stat_date 逐日列出 spend/行数/活动数/导入时间(created_at
 *       min~max)/source_task_id 去重值——看18个覆盖天具体是哪些天、每天是哪批导入写的、
 *       stat_date 与导入时间的关系（如果每批导入只写一个stat_date，且间隔数天，就是
 *       "多天报表被压到单天"或"隔几天导一次、每次只导一天"）。
 *   二、样例行 extra_json 原文（2条）：看CSV原始行里有没有报表日期范围字段，判断 stat_date
 *       是取自CSV内容还是导入时人工填的。
 *   三、全店铺 auto_csv 覆盖概览：按 store_id 汇总 min/max stat_date、覆盖天数、行数——
 *       看日期覆盖问题是CN2601独有还是所有店铺共性。
 *   四、逐覆盖日比率：对该店铺每个有CSV数据的 stat_date（上限20天），实时调
 *       reportAdItemSpList(campaignType=["sponsoredProducts-auto"]) 取当日API合计，
 *       算 CSV/API 比率，输出比率表+均值±波动——验证66.7%是否稳定。
 *   五、最佳覆盖日逐活动对比：取CSV花费最高的一天，per-campaign 对比 CSV$ vs API$（前15），
 *       看比例在活动层面是均匀衰减还是集中缺失。
 *
 * 安全边界：只读 LingXing API + 只读 DB SELECT，零写库、零写RAW、零改动生产脚本、不建表。
 *
 * 运行（生产机，由部署工程师执行）：
 *   npx ts-node src/probeAutoCsvCoverageAndRatio.ts
 *
 * 用法：把完整输出贴回来，重点看"一、CSV路全景"和"四、逐覆盖日比率"。
 */

import "dotenv/config";
import * as mysql from "mysql2/promise";
import { loadConfig } from "./config";
import { LingxingClient } from "./lingxingClient";

const ITEM_PATH = "/basicOpen/multiplatform/ads/reportAdItemSpList";
const MAX_RATIO_DAYS = 20;

function toNum(v: unknown): number {
  const n = Number(v);
  return Number.isFinite(n) ? n : 0;
}
function toStr(v: unknown): string {
  return String(v ?? "").trim();
}
function normName(s: string): string {
  return s.toLowerCase().replace(/\s+/g, "");
}
function toDateStr(v: unknown): string {
  if (typeof v === "string") return v.slice(0, 10);
  if (v instanceof Date) {
    const d = new Date(v.getTime() - v.getTimezoneOffset() * 60000);
    return d.toISOString().slice(0, 10);
  }
  return String(v ?? "").slice(0, 10);
}
function sleep(ms: number): Promise<void> {
  return new Promise((r) => setTimeout(r, ms));
}

async function fetchAutoItemRows(
  client: LingxingClient,
  advertiserId: string,
  startDate: string,
  endDate: string,
): Promise<Array<Record<string, unknown>>> {
  const allRows: Array<Record<string, unknown>> = [];
  const PAGE_SIZE = 200;
  const MAX_PAGES = 25;
  for (let pageNum = 1; pageNum <= MAX_PAGES; pageNum++) {
    const resp = await client.request<unknown>({
      method: "POST",
      path: ITEM_PATH,
      params: {
        advertiserIds: [advertiserId],
        campaignType: ["sponsoredProducts-auto"],
        startDate,
        endDate,
        pageNum,
        pageSize: PAGE_SIZE,
        paging: true,
      },
      timeoutMs: 60000,
    });
    const data = (resp as unknown as { data?: unknown }).data;
    const list: Array<Record<string, unknown>> = Array.isArray(data)
      ? (data as Array<Record<string, unknown>>)
      : Array.isArray((data as { list?: unknown })?.list)
      ? ((data as { list: Array<Record<string, unknown>> }).list)
      : Array.isArray((data as { data?: unknown })?.data)
      ? ((data as { data: Array<Record<string, unknown>> }).data)
      : [];
    if (list.length === 0) break;
    allRows.push(...list);
    if (list.length < PAGE_SIZE) break;
    await sleep(400);
  }
  return allRows;
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
    `SELECT store_id, store_name, advertiser_id FROM dim_store_config WHERE platform = 'walmart' AND store_name LIKE '%瑞盈龙盛%'`,
  );
  const stores = storeRows as Array<{ store_id: string; store_name: string; advertiser_id: string | null }>;
  if (stores.length === 0 || !stores[0].advertiser_id) {
    console.log("没匹配到 CN2601-瑞盈龙盛 店铺或缺 advertiser_id，终止。");
    await db.end();
    return;
  }
  const store = stores[0];
  const advertiserId = String(store.advertiser_id);
  console.log(`目标店铺: store_id=${store.store_id} (${store.store_name})  advertiser_id=${advertiserId}\n`);

  // ── 一、CSV路全景 ──
  console.log(`=== 一、CSV路全景（该店铺 walmart_auto_csv 按 stat_date 逐日）===\n`);
  const [dayRows] = await db.execute(
    `SELECT stat_date, SUM(ad_spend) AS spend, COUNT(*) AS cnt,
            COUNT(DISTINCT campaign_name) AS camp_cnt,
            MIN(created_at) AS created_min, MAX(created_at) AS created_max,
            GROUP_CONCAT(DISTINCT source_task_id) AS task_ids
       FROM fact_ads_keyword_daily
      WHERE store_id = ? AND source_type = 'walmart_auto_csv'
      GROUP BY stat_date ORDER BY stat_date`,
    [store.store_id],
  );
  const days = dayRows as Array<{
    stat_date: unknown; spend: string | null; cnt: number; camp_cnt: number;
    created_min: unknown; created_max: unknown; task_ids: string | null;
  }>;
  console.log("stat_date".padEnd(13) + "spend$".padEnd(10) + "行数".padEnd(7) + "活动数".padEnd(8) + "导入时间(created_at min~max)".padEnd(44) + "source_task_id");
  for (const r of days) {
    const taskIds = toStr(r.task_ids);
    console.log(
      toDateStr(r.stat_date).padEnd(13) + toNum(r.spend).toFixed(2).padEnd(10) +
      String(r.cnt).padEnd(7) + String(r.camp_cnt).padEnd(8) +
      (String(r.created_min ?? "-").slice(0, 19) + " ~ " + String(r.created_max ?? "-").slice(0, 19)).padEnd(44) +
      (taskIds.length > 60 ? taskIds.slice(0, 60) + "..." : taskIds || "(空)"),
    );
  }
  console.log(`\n共 ${days.length} 个覆盖天。`);

  // ── 二、样例行 extra_json ──
  console.log(`\n=== 二、样例行原始字段（2条，看CSV原始行里的日期信息与stat_date来源）===\n`);
  const [sampleRows] = await db.execute(
    `SELECT stat_date, campaign_name, keyword, ad_spend, created_at, source_task_id, source_raw_id, extra_json
       FROM fact_ads_keyword_daily
      WHERE store_id = ? AND source_type = 'walmart_auto_csv'
      ORDER BY ad_spend DESC LIMIT 2`,
    [store.store_id],
  );
  for (const r of sampleRows as Array<Record<string, unknown>>) {
    console.log(JSON.stringify({ ...r, extra_json: (() => { try { return JSON.parse(String(r.extra_json ?? "null")); } catch { return String(r.extra_json ?? ""); } })() }, null, 2));
  }

  // ── 三、全店铺覆盖概览 ──
  console.log(`\n=== 三、全店铺 walmart_auto_csv 覆盖概览（是否CN2601独有问题）===\n`);
  const [storeCov] = await db.execute(
    `SELECT f.store_id, MAX(f.store_name) AS store_name,
            MIN(f.stat_date) AS min_d, MAX(f.stat_date) AS max_d,
            COUNT(DISTINCT f.stat_date) AS day_cnt, COUNT(*) AS cnt, SUM(f.ad_spend) AS spend
       FROM fact_ads_keyword_daily f
      WHERE f.source_type = 'walmart_auto_csv'
      GROUP BY f.store_id ORDER BY spend DESC`,
  );
  console.log("store_id".padEnd(22) + "覆盖".padEnd(24) + "天数".padEnd(6) + "行数".padEnd(8) + "spend$".padEnd(11) + "店铺名");
  for (const r of storeCov as Array<Record<string, unknown>>) {
    console.log(
      toStr(r.store_id).padEnd(22) + (toDateStr(r.min_d) + "~" + toDateStr(r.max_d)).padEnd(24) +
      String(r.day_cnt).padEnd(6) + String(r.cnt).padEnd(8) + toNum(r.spend).toFixed(2).padEnd(11) + toStr(r.store_name),
    );
  }

  // ── 四、逐覆盖日 CSV vs API 比率 ──
  const covDates = days.map((r) => toDateStr(r.stat_date)).filter(Boolean);
  const ratioDates = covDates.slice(0, MAX_RATIO_DAYS);
  if (covDates.length > MAX_RATIO_DAYS) {
    console.log(`\n[注意] 覆盖天共${covDates.length}个，仅对前${MAX_RATIO_DAYS}个做API比率核对（限速考虑）。`);
  }
  console.log(`\n=== 四、逐覆盖日比率（CSV日合计 vs API当日auto合计，实时调用${ratioDates.length}天）===\n`);
  const cfg = loadConfig();
  const client = new LingxingClient(cfg);
  const csvDayMap = new Map<string, number>();
  for (const r of days) csvDayMap.set(toDateStr(r.stat_date), toNum(r.spend));

  const ratios: number[] = [];
  console.log("日期".padEnd(13) + "CSV$".padEnd(11) + "API$".padEnd(11) + "CSV/API");
  const apiDayCampaignCache = new Map<string, Map<string, { name: string; spend: number }>>();
  for (const d of ratioDates) {
    const rows = await fetchAutoItemRows(client, advertiserId, d, d);
    let apiTotal = 0;
    const campMap = new Map<string, { name: string; spend: number }>();
    for (const r of rows) {
      const spend = toNum(r.adSpend);
      apiTotal += spend;
      const key = normName(toStr(r.campaignName)) || toStr(r.campaignId);
      if (!campMap.has(key)) campMap.set(key, { name: toStr(r.campaignName), spend: 0 });
      campMap.get(key)!.spend += spend;
    }
    apiDayCampaignCache.set(d, campMap);
    const csv = csvDayMap.get(d) ?? 0;
    const ratio = apiTotal > 0 ? (csv / apiTotal) * 100 : NaN;
    if (Number.isFinite(ratio)) ratios.push(ratio);
    console.log(d.padEnd(13) + ("$" + csv.toFixed(2)).padEnd(11) + ("$" + apiTotal.toFixed(2)).padEnd(11) + (Number.isFinite(ratio) ? ratio.toFixed(1) + "%" : "API=0"));
    await sleep(800);
  }
  if (ratios.length > 0) {
    const avg = ratios.reduce((a, b) => a + b, 0) / ratios.length;
    const min = Math.min(...ratios);
    const max = Math.max(...ratios);
    console.log(`\n比率统计: 均值=${avg.toFixed(1)}%  最小=${min.toFixed(1)}%  最大=${max.toFixed(1)}%  样本天数=${ratios.length}`);
    console.log(`判读: 若比率集中在一个窄带（如60~75%）→ "搜索词报告天生不全"为主，天花板≈均值；`);
    console.log(`      若比率大起大落 → 各天导入完整性不一，先解决导入质量再谈口径。`);
  }

  // ── 五、最佳覆盖日逐活动对比 ──
  let bestDay = "";
  let bestSpend = 0;
  for (const [d, s] of csvDayMap.entries()) {
    if (ratioDates.includes(d) && s > bestSpend) { bestSpend = s; bestDay = d; }
  }
  if (bestDay) {
    console.log(`\n=== 五、最佳覆盖日 ${bestDay}（CSV花费最高天）逐活动对比（API$降序前15）===\n`);
    const [csvCampRows] = await db.execute(
      `SELECT campaign_name, SUM(ad_spend) AS spend
         FROM fact_ads_keyword_daily
        WHERE store_id = ? AND source_type = 'walmart_auto_csv' AND stat_date = ?
        GROUP BY campaign_name`,
      [store.store_id, bestDay],
    );
    const csvCampMap = new Map<string, number>();
    for (const r of csvCampRows as Array<{ campaign_name: string; spend: string | null }>) {
      csvCampMap.set(normName(toStr(r.campaign_name)), toNum(r.spend));
    }
    const apiCamps = apiDayCampaignCache.get(bestDay) ?? new Map();
    const sorted = [...apiCamps.entries()].sort((a, b) => b[1].spend - a[1].spend).slice(0, 15);
    console.log("API$".padEnd(10) + "CSV$".padEnd(10) + "CSV占比".padEnd(9) + "活动名");
    for (const [key, a] of sorted) {
      const c = csvCampMap.get(key) ?? 0;
      const pct = a.spend > 0 ? ((c / a.spend) * 100).toFixed(1) + "%" : "-";
      console.log(("$" + a.spend.toFixed(2)).padEnd(10) + ("$" + c.toFixed(2)).padEnd(10) + pct.padEnd(9) + a.name);
    }
  }

  await db.end();
  console.log("\n探针12结束。");
}

main().catch((err) => {
  console.error("探针12执行失败：", err);
  process.exit(1);
});
