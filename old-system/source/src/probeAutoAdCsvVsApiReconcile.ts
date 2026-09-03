/**
 * src/probeAutoAdCsvVsApiReconcile.ts
 *
 * 单品现金利润模块 · 探针11 —— 自动广告"CSV路 vs API路"逐活动逐日对账（只读，零写库，零改动生产）。
 *
 * 背景：
 *   探针10已实锤：领星 reportAdItemSpList 加 campaignType=["sponsoredProducts-auto"] 能拿到
 *   自动广告的商品级真实花费（样本活动 YC00029-自动-5.03 与真实发票 $102.44 100%吻合）；
 *   窗口1(2026-07-10~07-15) API路自动广告总额=$1576.83。
 *   而现库里自动广告的另一路：fact_ads_keyword_daily source_type='walmart_auto_csv'
 *   （沃尔玛后台搜索词CSV人工导入，翁骏维护，17:25有监控cron），探针6同窗口只有约$176，
 *   仅API路的约11%。
 *
 *   需求方已定的方向："合计花费两路需要一致，详细数据以CSV为主"——即搜索词明细用CSV路，
 *   但两路合计必须对得上（需要对账校验）。要落地这个方向，必须先量化：现状两路差距到底
 *   差在哪——是CSV导入缺了天数？缺了活动？还是搜索词报告本身就不含全部花费（沃尔玛搜索词
 *   报告通常只列有点击/曝光的词，部分花费不归到任何词）？
 *
 * 本探针做的事（纯读取）：
 *   1) 查 dim_store_config 拿 CN2601 的 advertiser_id。
 *   2) API路窗口级：ITEM_PATH campaignType=["sponsoredProducts-auto"]，窗口1一次拉全，
 *      按 campaignId+campaignName 聚合 adSpend。
 *   3) API路逐日：同参数按天（07-10~07-15共6天）各调一次，得到逐日合计与逐活动逐日花费；
 *      并校验"逐日加总 ≈ 窗口级总额"（接口口径自洽性）。
 *   4) CSV路(DB)：fact_ads_keyword_daily WHERE source_type='walmart_auto_csv' 同窗口，
 *      按 campaign_name 聚合、按 stat_date 聚合；打印 campaign_id 样例（CSV来自沃尔玛后台，
 *      其campaign_id可能是沃尔玛编号体系，≠领星campaignId——探针7的教训，故对账按活动名）。
 *   5) 逐活动对账表：按"归一化活动名"匹配两路，打印 API$ / CSV$ / 差值 / CSV占比；
 *      列出仅API有、仅CSV有的活动清单。
 *   6) 逐日对账表：API日合计 vs CSV日合计（定位"缺天"问题）。
 *
 * 安全边界：只读 LingXing API + 只读 DB SELECT，零写库、零写RAW、零改动生产脚本、不建表。
 *
 * 运行（生产机，由部署工程师执行）：
 *   npx ts-node src/probeAutoAdCsvVsApiReconcile.ts
 *
 * 用法：把完整输出贴回来，重点看"五、逐活动对账表"和"六、逐日对账表"。
 */

import "dotenv/config";
import * as mysql from "mysql2/promise";
import { loadConfig } from "./config";
import { LingxingClient } from "./lingxingClient";

const ITEM_PATH = "/basicOpen/multiplatform/ads/reportAdItemSpList";
const WINDOW = { label: "窗口1", startDate: "2026-07-10", endDate: "2026-07-15" };
const DAYS = ["2026-07-10", "2026-07-11", "2026-07-12", "2026-07-13", "2026-07-14", "2026-07-15"];
const API_WINDOW_KNOWN_TOTAL = 1576.83; // 探针10：窗口级auto总额
const CSV_KNOWN_APPROX = 176;           // 探针6：同窗口walmart_auto_csv约值（本探针重新精确计算）

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
  const advertiserId = String(store.advertiser_id); // 上方已判空，此处显式收窄类型
  console.log(`目标店铺: store_id=${store.store_id} (${store.store_name})  advertiser_id=${advertiserId}\n`);
  console.log(`=== 一、目标窗口 ${WINDOW.label}: ${WINDOW.startDate} ~ ${WINDOW.endDate} ===`);
  console.log(`    已知基准: API路auto窗口总额=$${API_WINDOW_KNOWN_TOTAL}（探针10）；CSV路约$${CSV_KNOWN_APPROX}（探针6，本次重算精确值）\n`);

  const cfg = loadConfig();
  const client = new LingxingClient(cfg);

  // ── 二、API路窗口级 per-campaign ──
  console.log(`=== 二、API路窗口级（campaignType=["sponsoredProducts-auto"]，一次拉全窗口）===\n`);
  const winRows = await fetchAutoItemRows(client, advertiserId, WINDOW.startDate, WINDOW.endDate);
  const apiCampaign = new Map<string, { campaignId: string; campaignName: string; spend: number; rows: number }>();
  let apiWindowTotal = 0;
  for (const r of winRows) {
    const id = toStr(r.campaignId);
    const name = toStr(r.campaignName);
    const spend = toNum(r.adSpend);
    apiWindowTotal += spend;
    const key = normName(name) || id;
    if (!apiCampaign.has(key)) apiCampaign.set(key, { campaignId: id, campaignName: name, spend: 0, rows: 0 });
    const a = apiCampaign.get(key)!;
    a.spend += spend;
    a.rows += 1;
  }
  console.log(`窗口级返回 ${winRows.length} 行，去重 ${apiCampaign.size} 个活动，adSpend总和=$${apiWindowTotal.toFixed(2)}（对照探针10 $${API_WINDOW_KNOWN_TOTAL}）\n`);
  await sleep(1500);

  // ── 三、API路逐日 ──
  console.log(`=== 三、API路逐日调用（同参数按天）===\n`);
  const apiDaily = new Map<string, number>(); // date -> total
  const apiCampaignDaily = new Map<string, Map<string, number>>(); // nameKey -> date -> spend
  for (const d of DAYS) {
    const dayRows = await fetchAutoItemRows(client, advertiserId, d, d);
    let dayTotal = 0;
    for (const r of dayRows) {
      const spend = toNum(r.adSpend);
      dayTotal += spend;
      const key = normName(toStr(r.campaignName)) || toStr(r.campaignId);
      if (!apiCampaignDaily.has(key)) apiCampaignDaily.set(key, new Map());
      const m = apiCampaignDaily.get(key)!;
      m.set(d, (m.get(d) ?? 0) + spend);
    }
    apiDaily.set(d, dayTotal);
    console.log(`  ${d}: ${dayRows.length}行, adSpend合计=$${dayTotal.toFixed(2)}`);
    await sleep(800);
  }
  const apiDailySum = [...apiDaily.values()].reduce((a, b) => a + b, 0);
  console.log(`  逐日加总=$${apiDailySum.toFixed(2)}  vs 窗口级$${apiWindowTotal.toFixed(2)}  差=$${(apiDailySum - apiWindowTotal).toFixed(2)}（校验接口逐日/窗口口径自洽性）\n`);

  // ── 四、CSV路(DB) ──
  console.log(`=== 四、CSV路（fact_ads_keyword_daily source_type='walmart_auto_csv'）===\n`);
  const [csvCampRows] = await db.execute(
    `SELECT campaign_id, campaign_name, SUM(ad_spend) AS spend, COUNT(*) AS cnt,
            COUNT(DISTINCT stat_date) AS day_cnt
       FROM fact_ads_keyword_daily
      WHERE store_id = ? AND source_type = 'walmart_auto_csv' AND stat_date BETWEEN ? AND ?
      GROUP BY campaign_id, campaign_name
      ORDER BY spend DESC`,
    [store.store_id, WINDOW.startDate, WINDOW.endDate],
  );
  const csvCamps = csvCampRows as Array<{ campaign_id: string; campaign_name: string; spend: string | null; cnt: number; day_cnt: number }>;
  const csvCampaign = new Map<string, { campaignId: string; campaignName: string; spend: number; rows: number; days: number }>();
  let csvTotal = 0;
  for (const r of csvCamps) {
    const spend = toNum(r.spend);
    csvTotal += spend;
    const key = normName(toStr(r.campaign_name)) || toStr(r.campaign_id);
    if (!csvCampaign.has(key)) csvCampaign.set(key, { campaignId: toStr(r.campaign_id), campaignName: toStr(r.campaign_name), spend: 0, rows: 0, days: 0 });
    const c = csvCampaign.get(key)!;
    c.spend += spend;
    c.rows += r.cnt;
    c.days = Math.max(c.days, r.day_cnt);
  }
  console.log(`CSV路 ${csvCamps.length} 个(campaign_id,name)组合，归一名后 ${csvCampaign.size} 个活动，ad_spend总和=$${csvTotal.toFixed(2)}`);
  console.log(`campaign_id 样例（核实CSV用的是哪套ID体系，预期≠领星campaignId）:`);
  for (const r of csvCamps.slice(0, 5)) {
    console.log(`  campaign_id=${r.campaign_id || "(空)"}  name="${r.campaign_name || "(空)"}"  spend=$${toNum(r.spend).toFixed(2)}  行数=${r.cnt}  覆盖天数=${r.day_cnt}`);
  }

  const [csvDayRows] = await db.execute(
    `SELECT stat_date, SUM(ad_spend) AS spend, COUNT(*) AS cnt, COUNT(DISTINCT campaign_name) AS camp_cnt
       FROM fact_ads_keyword_daily
      WHERE store_id = ? AND source_type = 'walmart_auto_csv' AND stat_date BETWEEN ? AND ?
      GROUP BY stat_date ORDER BY stat_date`,
    [store.store_id, WINDOW.startDate, WINDOW.endDate],
  );
  const csvDays = csvDayRows as Array<{ stat_date: string | Date; spend: string | null; cnt: number; camp_cnt: number }>;
  const csvDaily = new Map<string, number>();
  for (const r of csvDays) {
    const d = typeof r.stat_date === "string" ? r.stat_date.slice(0, 10) : (r.stat_date as Date).toISOString().slice(0, 10);
    csvDaily.set(d, toNum(r.spend));
  }

  // 顺带查同窗口CSV路整体导入情况（是否近期才开始导、这店铺覆盖到哪天）
  const [csvRangeRows] = await db.execute(
    `SELECT MIN(stat_date) AS min_d, MAX(stat_date) AS max_d, COUNT(DISTINCT stat_date) AS day_cnt, COUNT(*) AS cnt
       FROM fact_ads_keyword_daily
      WHERE store_id = ? AND source_type = 'walmart_auto_csv'`,
    [store.store_id],
  );
  const rng = (csvRangeRows as Array<{ min_d: unknown; max_d: unknown; day_cnt: number; cnt: number }>)[0];
  console.log(`\nCSV路该店铺全历史覆盖: ${String(rng?.min_d ?? "-").slice(0, 15)} ~ ${String(rng?.max_d ?? "-").slice(0, 15)}，覆盖天数=${rng?.day_cnt ?? 0}，总行数=${rng?.cnt ?? 0}`);

  // ── 五、逐活动对账表 ──
  console.log(`\n=== 五、逐活动对账表（按归一化活动名匹配；API$为基准）===\n`);
  console.log("API$".padEnd(11) + "CSV$".padEnd(11) + "CSV占比".padEnd(9) + "活动名(API侧) | CSV匹配情况");
  const allKeys = new Set<string>([...apiCampaign.keys(), ...csvCampaign.keys()]);
  let matchedBoth = 0, onlyApi = 0, onlyCsv = 0;
  const sortedApi = [...apiCampaign.entries()].sort((a, b) => b[1].spend - a[1].spend);
  for (const [key, a] of sortedApi) {
    const c = csvCampaign.get(key);
    if (c) {
      matchedBoth++;
      const pct = a.spend > 0 ? ((c.spend / a.spend) * 100).toFixed(1) + "%" : "-";
      console.log(`$${a.spend.toFixed(2).padEnd(10)}$${c.spend.toFixed(2).padEnd(10)}${pct.padEnd(9)}${a.campaignName} | CSV覆盖${c.days}天/${DAYS.length}天`);
    } else {
      onlyApi++;
      console.log(`$${a.spend.toFixed(2).padEnd(10)}${"-".padEnd(11)}${"0%".padEnd(9)}${a.campaignName} | [CSV路完全没有此活动]`);
    }
  }
  for (const [key, c] of [...csvCampaign.entries()].sort((a, b) => b[1].spend - a[1].spend)) {
    if (!apiCampaign.has(key)) {
      onlyCsv++;
      console.log(`${"-".padEnd(11)}$${c.spend.toFixed(2).padEnd(10)}${"-".padEnd(9)}"${c.campaignName}" | [仅CSV路有，API路无——核对是否名称写法差异]`);
    }
  }
  console.log(`\n活动匹配统计: 两路都有=${matchedBoth}  仅API有=${onlyApi}  仅CSV有=${onlyCsv}  （API共${apiCampaign.size}，CSV共${csvCampaign.size}）`);
  console.log(`窗口合计: API=$${apiWindowTotal.toFixed(2)}  CSV=$${csvTotal.toFixed(2)}  CSV/API=${apiWindowTotal > 0 ? ((csvTotal / apiWindowTotal) * 100).toFixed(1) : "-"}%`);

  // ── 六、逐日对账表 ──
  console.log(`\n=== 六、逐日对账表 ===\n`);
  console.log("日期".padEnd(13) + "API$".padEnd(12) + "CSV$".padEnd(12) + "CSV占比");
  for (const d of DAYS) {
    const a = apiDaily.get(d) ?? 0;
    const c = csvDaily.get(d) ?? 0;
    const pct = a > 0 ? ((c / a) * 100).toFixed(1) + "%" : (c > 0 ? "API=0" : "-");
    console.log(d.padEnd(13) + ("$" + a.toFixed(2)).padEnd(12) + ("$" + c.toFixed(2)).padEnd(12) + pct);
  }

  console.log(`\n=== 七、结论判读提示（人工核对用）===`);
  console.log(`  ① 若"仅API有"的活动占大头 → CSV导入缺活动（沃尔玛后台导出范围/搜索词报告天生不全）；`);
  console.log(`  ② 若逐日表里CSV整天为0 → CSV导入缺天（对照17:25监控cron的滞后3天口径）；`);
  console.log(`  ③ 若同活动两路都有但CSV系统性偏低且比例稳定 → 搜索词报告天生不含全部花费（无词归属的花费进不了搜索词明细）；`);
  console.log(`     ③成立时，"两路合计一致"无法靠补导CSV实现，只能"合计以API为准+CSV做明细分析"，需回报需求方重新拍板。`);

  await db.end();
  console.log("\n探针11结束。");
}

main().catch((err) => {
  console.error("探针11执行失败：", err);
  process.exit(1);
});
