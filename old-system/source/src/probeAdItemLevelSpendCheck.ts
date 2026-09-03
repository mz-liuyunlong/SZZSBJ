/**
 * src/probeAdItemLevelSpendCheck.ts
 *
 * 单品现金利润模块 · 探针9 —— 验证"改造同步脚本，吃进reportAdItemSpList自己的花费字段"
 * 这个修法能不能真的补全"自动"广告活动的真实花费缺口（只读，零写库，零改动生产）。
 *
 * 背景（探针8结论）：
 *   手动/关键词型广告活动（精准/词组/手动/AI筛选词）在 fact_ads_keyword_daily 里的数据，
 *   按活动名核对，跟真实Walmart Connect发票金额分毫不差；但"自动"(auto-targeting)型广告
 *   活动严重少算——样本"YC00029-自动-5.03"（campaignId=5032288），真实发票窗口1(07-10~07-15)
 *   金额$102.44，fact_ads_keyword_daily(经KEYWORD_PATH同步)只有$10.67，仅10.4%。
 *
 *   生产同步脚本 syncManualAdKeywordDaily.ts 目前实际调用了两个领星接口：
 *     ITEM_PATH    = /basicOpen/multiplatform/ads/reportAdItemSpList   （商品维度）
 *     KEYWORD_PATH = /basicOpen/multiplatform/ads/reportKeywordSpList （关键词维度）
 *   但 ITEM_PATH 拉回来的数据，脚本只用来建立 campaignId+adGroupId → {item_id, msku} 的映射表
 *  （campaignItemMap），从未读取/落库过 ITEM_PATH 自己返回的花费字段——花费金额全部来自
 *   KEYWORD_PATH 的 adSpend 字段。两个接口用的 baseParams 完全一样：
 *     { advertiserIds: [advertiser_id], campaignType: ["sponsoredProducts-manual"], startDate, endDate }
 *
 *   用户的问题："要不要改同步脚本，把reportAdItemSpList自己的花费字段也吃进去，把自动广告的
 *   真实花费补全"——这是目前看起来最根本的修法，但要动生产定时任务，需要先验证：
 *     ① reportAdItemSpList 这个接口本身，对"YC00029-自动-5.03"这个活动，到底有没有返回一个
 *        花费字段？字段名叫什么？
 *     ② 如果有，按这个活动加总，是否真的能对上/接近真实发票的$102.44（而不是KEYWORD_PATH的
 *        $10.67）？
 *     ③ 顺带看看返回的行本身是不是"商品维度"粒度（一行=一个item_id），如果要落到
 *        fact_ads_keyword_daily 现有的"keyword维度"唯一键上，这笔花费怎么摊，会不会需要动
 *        表结构/唯一键，而不只是脚本逻辑。
 *
 * 本探针做的事（纯读取，不落库、不写RAW、不改脚本、不改表）：
 *   1) 查 dim_store_config 拿 CN2601 的 advertiser_id（跟生产同步脚本同款用法）。
 *   2) 对窗口1（2026-07-10~07-15，真实发票$102.44口径来自"YC00029-自动-5.03"这一个活动）
 *      直接实时调用 reportAdItemSpList，用跟生产同步脚本完全相同的 baseParams
 *      （campaignType仍为["sponsoredProducts-manual"]，不额外放宽，先验证现有筛选条件下
 *      这个活动到底有没有被该接口覆盖）。
 *   3) 打印该接口返回的原始JSON前2条完整行（不做任何字段猜测过滤），供人工直接看到所有真实
 *      字段名——尤其是有没有花费/金额相关字段。
 *   4) 按 campaignId+campaignName 聚合，对几个候选花费字段名（adSpend/spend/cost/adCost/
 *      itemSpend/totalSpend/spendAmount等）分别求和打印，明确指出该接口里"花费"字段到底叫
 *      什么、有没有。
 *   5) 重点摘出 campaignId=5032288 / campaignName包含"YC00029"的行，完整打印每一行原始JSON，
 *      并计算候选花费字段对这一个活动的加总，跟真实发票$102.44、跟KEYWORD_PATH已知的$10.67
 *      三方对比。
 *   6) 打印该接口返回数据的粒度说明（是否item_id唯一、有没有keyword/adGroup字段），供人工
 *      判断"如果真要落库，会不会撞现有唯一键"这个结构性问题。
 *
 * 安全边界：只读 LingXing API（跟生产同步脚本同一只读接口 reportAdItemSpList）+ 只读 DB
 *   SELECT，零写库、零写RAW、零改动生产脚本、不建表、不改表。
 *
 * 运行（生产机，由部署工程师执行）：
 *   npx ts-node src/probeAdItemLevelSpendCheck.ts
 *
 * 用法：把完整输出贴回来。重点看"三、候选花费字段求和"和"四、YC00029-自动-5.03 逐行原始数据"。
 */

import "dotenv/config";
import * as mysql from "mysql2/promise";
import { loadConfig } from "./config";
import { LingxingClient } from "./lingxingClient";

const ITEM_PATH = "/basicOpen/multiplatform/ads/reportAdItemSpList";
const WINDOW = {
  label: "窗口1",
  startDate: "2026-07-10",
  endDate: "2026-07-15",
  realInvoiceTotal: 6607.08,
  invoiceNo: "78430539",
};
// 探针8已确认的问题活动
const TARGET_CAMPAIGN_ID = "5032288";
const TARGET_NAME_HINT = "YC00029";
const TARGET_REAL_AMOUNT = 102.44; // 真实发票口径，"YC00029-自动-5.03"这一个活动在窗口1的真实花费
const KEYWORD_PATH_KNOWN_SPEND = 10.67; // 探针8已查得：KEYWORD_PATH/fact_ads_keyword_daily 目前对这个活动只算出的花费

// 候选花费字段名（不确定 reportAdItemSpList 实际用哪个，全部尝试求和，哪个字段有非零值一目了然）
const SPEND_FIELD_CANDIDATES = [
  "adSpend", "spend", "cost", "adCost", "itemSpend", "totalSpend",
  "spendAmount", "amount", "adAmount", "spendMoney", "totalCost", "adFee",
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

  console.log(`=== 一、目标窗口 ${WINDOW.label}: ${WINDOW.startDate} ~ ${WINDOW.endDate} ===`);
  console.log(`    对照：campaignId=${TARGET_CAMPAIGN_ID}（"YC00029-自动-5.03"），真实发票该活动花费=$${TARGET_REAL_AMOUNT}`);
  console.log(`    对照：KEYWORD_PATH（现生产同步脚本用的接口）已知只算出=$${KEYWORD_PATH_KNOWN_SPEND}\n`);

  const cfg = loadConfig();
  const client = new LingxingClient(cfg);

  const baseParams = {
    advertiserIds: [store.advertiser_id],
    campaignType: ["sponsoredProducts-manual"], // 跟生产同步脚本baseParams完全一致，不额外放宽
    startDate: WINDOW.startDate,
    endDate: WINDOW.endDate,
  };

  console.log(`=== 二、实时调用 ${ITEM_PATH}（商品维度接口，跟同步脚本ITEM_PATH完全同款参数）===\n`);

  const allRows: Array<Record<string, unknown>> = [];
  let pageNum = 1;
  const PAGE_SIZE = 200;
  const MAX_PAGES = 30;
  for (; pageNum <= MAX_PAGES; pageNum++) {
    const resp = await client.request<unknown>({
      method: "POST",
      path: ITEM_PATH,
      params: { ...baseParams, pageNum, pageSize: PAGE_SIZE, paging: true },
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
    await new Promise((r) => setTimeout(r, 400));
  }
  console.log(`共取回 ${allRows.length} 条商品维度行。\n`);

  if (allRows.length === 0) {
    console.log("[异常] 该接口在此窗口/参数下一条数据都没返回，无法继续分析，请把这一情况直接贴回。");
    await db.end();
    return;
  }

  console.log("--- 原始JSON样例（前2条，逐字段打印，不做任何过滤，用于人工识别花费字段名） ---");
  for (const r of allRows.slice(0, 2)) {
    console.log(JSON.stringify(r, null, 2));
  }

  console.log("\n--- 该接口返回行的全部字段名（去重，来自前50条样本） ---");
  const allKeys = new Set<string>();
  for (const r of allRows.slice(0, 50)) {
    for (const k of Object.keys(r)) allKeys.add(k);
  }
  console.log([...allKeys].sort().join(", "));

  console.log(`\n=== 三、候选花费字段求和（对全部${allRows.length}行，逐个候选字段名求和，看哪个非零） ===\n`);
  for (const field of SPEND_FIELD_CANDIDATES) {
    const sum = allRows.reduce((acc, r) => acc + toNum(r[field]), 0);
    const nonZeroCount = allRows.filter((r) => toNum(r[field]) !== 0).length;
    console.log(`  ${field.padEnd(16)} 全量求和=${sum.toFixed(2).padEnd(12)} 非零行数=${nonZeroCount}/${allRows.length}`);
  }

  console.log(`\n=== 四、"YC00029-自动-5.03"（campaignId=${TARGET_CAMPAIGN_ID}）逐行原始数据核对 ===\n`);
  const targetRows = allRows.filter(
    (r) => toStr(r.campaignId) === TARGET_CAMPAIGN_ID || toStr(r.campaignName).includes(TARGET_NAME_HINT),
  );
  console.log(`匹配到 ${targetRows.length} 行（按campaignId=${TARGET_CAMPAIGN_ID} 或 campaignName包含"${TARGET_NAME_HINT}"）：\n`);
  for (const r of targetRows) {
    console.log(JSON.stringify(r, null, 2));
  }

  if (targetRows.length > 0) {
    console.log(`\n--- 该活动候选花费字段求和对比 ---`);
    console.log(`  真实发票口径（人工核对，基准）      : $${TARGET_REAL_AMOUNT.toFixed(2)}`);
    console.log(`  KEYWORD_PATH（现生产脚本用的接口）  : $${KEYWORD_PATH_KNOWN_SPEND.toFixed(2)}  (${((KEYWORD_PATH_KNOWN_SPEND / TARGET_REAL_AMOUNT) * 100).toFixed(1)}%)`);
    for (const field of SPEND_FIELD_CANDIDATES) {
      const sum = targetRows.reduce((acc, r) => acc + toNum(r[field]), 0);
      if (sum !== 0) {
        console.log(`  ITEM_PATH.${field.padEnd(14)} : $${sum.toFixed(2)}  (${((sum / TARGET_REAL_AMOUNT) * 100).toFixed(1)}%)  ← 候选修法字段`);
      }
    }
  } else {
    console.log("[重要] reportAdItemSpList 在当前筛选条件（campaignType=['sponsoredProducts-manual']）下，");
    console.log("       完全没有返回这个活动的任何一行——说明问题可能不在'脚本没吃这个字段'，而在于");
    console.log("       这个接口/这个筛选条件下这个活动本身就没有商品维度数据可拿，需要人工确认是否要");
    console.log("       放宽 campaignType 筛选条件（比如加上其他枚举值）后重测，而不能直接下结论说");
    console.log("       '改脚本吃这个字段就能解决'。");
  }

  console.log(`\n=== 五、返回粒度说明（判断落库要不要动 fact_ads_keyword_daily 唯一键结构）===`);
  console.log(`  样例行是否含 keyword 相关字段: ${[...allKeys].filter((k) => /keyword|target/i.test(k)).join(", ") || "(无)"}`);
  console.log(`  样例行是否含 adGroup 相关字段: ${[...allKeys].filter((k) => /adGroup/i.test(k)).join(", ") || "(无)"}`);
  console.log(`  样例行是否含 item/product 相关字段: ${[...allKeys].filter((k) => /item|product/i.test(k)).join(", ") || "(无)"}`);
  const uniqueItemIds = new Set(allRows.map((r) => toStr(r.itemId ?? r.platformProductId ?? r.productId)));
  console.log(`  全量${allRows.length}行里 item_id 去重后 ${uniqueItemIds.size} 个（如果行数≈item_id数，说明是'一活动一行'或'一item一行'粒度，不含keyword细分）`);

  await db.end();
  console.log("\n探针9结束。");
}

main().catch((err) => {
  console.error("探针9执行失败：", err);
  process.exit(1);
});
