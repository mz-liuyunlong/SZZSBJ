/**
 * src/probeAdLiveVsInvoiceCompare.ts
 *
 * 单品现金利润模块 · 探针8 —— 探针7发现：18个样本活动全部"完全没同步"，包括普通自动/手动广告
 * （不只是SBV）。用户已确认"SBV目前没有做广告数据，这个没错"——SBV缺席是预期内的，不是bug。
 * 但普通sponsoredProducts广告也全部对不上campaign_id，就不正常了：探针6/7都证明
 * fact_ads_keyword_daily 这个店铺这几个窗口里确实有数据（窗口1 manual_kw就有207个活动、
 * $4482.86），只是我探针7里用发票上印的那个数字（如"YC00032-自动4.07(9879914)"里的9879914）
 * 去匹配 campaign_id 字段，一个都没对上——很可能这串数字在Walmart Connect发票上是别的ID
 * （比如ad_group_id、或Walmart自己的一个跟领星campaignId不同源的编号），不是拿去跟领星
 * campaign_id字段比的正确钥匙。
 *
 * 用户指示："这个数据去领星看看对比一下"——不要再猜ID怎么映射，直接把领星广告接口现在
 * 实时返回的原始数据摆出来，人工用广告活动名称（而不是ID数字）去跟发票核对，看真实花费
 * 金额对不对得上。
 *
 * 本探针做的事：
 *   1) 查 dim_store_config 拿 CN2601 的 advertiser_id（syncManualAdKeywordDaily.ts 同款用法）。
 *   2) 对窗口1（2026-07-10~07-15，真实发票$6607.08）直接实时调用领星广告接口
 *      /basicOpen/multiplatform/ads/reportKeywordSpList（跟生产同步脚本用的是同一个只读接口，
 *      不落库、不写RAW，纯读取），按 campaignId+campaignName 汇总 adSpend，全量打印排序，
 *      供人工用活动名称去对真实发票逐行核对（发票上的活动名称都是"YC00032-自动4.07"这种）。
 *   3) 顺手在 fact_ads_keyword_daily 里按 campaign_name 关键字（而不是探针7用的campaign_id）
 *      查一遍探针7同样那几个样本活动名，看名称匹配下是否真的有数据、金额是否接近发票。
 *
 * 安全边界：只读 LingXing API（跟生产同步脚本同一只读接口）+ 只读 DB SELECT，零写库、
 *   零改动生产、不建表、不写RAW。
 *
 * 运行（生产机，由部署工程师执行）：
 *   npx ts-node src/probeAdLiveVsInvoiceCompare.ts
 *
 * 用法：把完整输出贴回来。重点看"二、领星实时接口返回"里有没有出现"YC00032""JJ4035"这些
 *      样本活动名称前缀，以及它们的adSpend跟发票上的金额差多少。
 */

import "dotenv/config";
import * as mysql from "mysql2/promise";
import { loadConfig } from "./config";
import { LingxingClient } from "./lingxingClient";

const KEYWORD_PATH = "/basicOpen/multiplatform/ads/reportKeywordSpList";
const WINDOW = { label: "窗口1", startDate: "2026-07-10", endDate: "2026-07-15", realInvoiceTotal: 6607.08, invoiceNo: "78430539" };

// 探针7里用过的样本活动名称前缀（人工从真实发票摘取），本探针改用"名称"去核对，不再用ID
const SAMPLE_NAME_PREFIXES = [
  "YC00032-自动4.07", "YC00032-词组4.07", "YC00017-精准-4.20-M",
  "YC00029-自动-5.03", "YC00019-SBV-5.11-TEST", "JJ4035-手动-KY-5.12",
];

function toNum(v: unknown): number {
  const n = Number(v);
  return Number.isFinite(n) ? n : 0;
}
function toStr(v: unknown): string {
  return String(v ?? "").trim();
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
  if (stores.length === 0) {
    console.log("没匹配到 CN2601-瑞盈龙盛 店铺，终止。");
    await db.end();
    return;
  }
  const store = stores[0];
  console.log(`目标店铺: store_id=${store.store_id} (${store.store_name})  advertiser_id=${store.advertiser_id ?? "(空)"}\n`);

  if (!store.advertiser_id) {
    console.log("dim_store_config 里这个店铺没有 advertiser_id，无法调用广告接口，终止。");
    await db.end();
    return;
  }

  console.log(`=== 一、目标窗口 ${WINDOW.label}: ${WINDOW.startDate} ~ ${WINDOW.endDate} (对照发票 ${WINDOW.invoiceNo}, 真实总额 $${WINDOW.realInvoiceTotal}) ===\n`);

  console.log(`=== 二、领星广告接口实时返回（${KEYWORD_PATH}，campaignType=sponsoredProducts-manual）===\n`);
  const cfg = loadConfig();
  const client = new LingxingClient(cfg);

  const campaignAgg = new Map<string, { campaignId: string; campaignName: string; campaignType: string; spend: number; rows: number }>();
  let pageNum = 1;
  let totalRows = 0;
  const PAGE_SIZE = 200;
  const MAX_PAGES = 20;
  for (; pageNum <= MAX_PAGES; pageNum++) {
    const resp = await client.request<unknown>({
      method: "POST",
      path: KEYWORD_PATH,
      params: {
        advertiserIds: [store.advertiser_id],
        campaignType: ["sponsoredProducts-manual"],
        startDate: WINDOW.startDate,
        endDate: WINDOW.endDate,
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
    totalRows += list.length;
    for (const r of list) {
      const campaignId = toStr(r.campaignId);
      const campaignName = toStr(r.campaignName);
      const campaignType = toStr(r.campaignType);
      const spend = toNum(r.adSpend);
      const key = campaignId || campaignName;
      if (!campaignAgg.has(key)) {
        campaignAgg.set(key, { campaignId, campaignName, campaignType, spend: 0, rows: 0 });
      }
      const agg = campaignAgg.get(key)!;
      agg.spend += spend;
      agg.rows += 1;
    }
    if (list.length < PAGE_SIZE) break;
    await new Promise((r) => setTimeout(r, 400));
  }
  console.log(`实时接口共取回 ${totalRows} 条关键词行，去重后 ${campaignAgg.size} 个广告活动。\n`);

  const sortedCampaigns = [...campaignAgg.values()].sort((a, b) => b.spend - a.spend);
  console.log("按adSpend降序，全部广告活动（campaignId | campaignType | spend | 关键词行数 | 活动名）：");
  for (const c of sortedCampaigns) {
    console.log(`  ${c.campaignId.padEnd(14)} ${c.campaignType.padEnd(24)} $${c.spend.toFixed(2).padEnd(10)} 行数=${String(c.rows).padEnd(5)} ${c.campaignName}`);
  }
  const liveTotalSpend = sortedCampaigns.reduce((a, c) => a + c.spend, 0);
  console.log(`\n实时接口 adSpend 总和 = $${liveTotalSpend.toFixed(2)}（对照真实发票 $${WINDOW.realInvoiceTotal}，占比 ${((liveTotalSpend / WINDOW.realInvoiceTotal) * 100).toFixed(1)}%）`);

  console.log(`\n=== 三、样本活动名称匹配检查（在上面实时结果里搜索发票里出现过的活动名前缀）===`);
  for (const prefix of SAMPLE_NAME_PREFIXES) {
    const hits = sortedCampaigns.filter((c) => c.campaignName.includes(prefix.split("-")[0]) || c.campaignName.startsWith(prefix.slice(0, 6)));
    if (hits.length === 0) {
      console.log(`  "${prefix}" → [实时接口里完全没找到匹配的活动名]`);
    } else {
      for (const h of hits) {
        console.log(`  "${prefix}" → 疑似匹配: campaignId=${h.campaignId} campaignName="${h.campaignName}" spend=$${h.spend.toFixed(2)}`);
      }
    }
  }

  console.log(`\n=== 四、fact_ads_keyword_daily 按活动名称（非ID）核对同一批样本 ===`);
  for (const prefix of SAMPLE_NAME_PREFIXES) {
    const [rows] = await db.execute(
      `SELECT campaign_id, campaign_name, SUM(ad_spend) AS spend, COUNT(*) AS cnt
         FROM fact_ads_keyword_daily
        WHERE store_id = ? AND stat_date BETWEEN ? AND ? AND campaign_name LIKE ?
        GROUP BY campaign_id, campaign_name`,
      [store.store_id, WINDOW.startDate, WINDOW.endDate, `%${prefix.split("-")[0]}%`],
    );
    const typed = rows as Array<{ campaign_id: string; campaign_name: string; spend: string | null; cnt: number }>;
    if (typed.length === 0) {
      console.log(`  "${prefix}" → [DB里按名称模糊查也没有]`);
    } else {
      for (const r of typed) {
        console.log(`  "${prefix}" → DB命中: campaign_id=${r.campaign_id} campaign_name="${r.campaign_name}" spend=${toNum(r.spend).toFixed(2)} 行数=${r.cnt}`);
      }
    }
  }

  await db.end();
  console.log("\n探针8结束。");
}

main().catch((err) => {
  console.error("探针8执行失败：", err);
  process.exit(1);
});
