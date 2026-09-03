/**
 * src/probeAdCampaignTypeEnum.ts
 *
 * 单品现金利润模块 · 探针10 —— 探针9已实锤：方案1（原样吃进reportAdItemSpList的adSpend字段）
 * 解决不了自动广告缺口。证据：
 *   ① 现有参数 campaignType=["sponsoredProducts-manual"] 下，ITEM_PATH 返回的773行里，
 *      目标自动活动 campaignId=5032288（"YC00029-自动-5.03"）一行都没有；
 *   ② ITEM_PATH.adSpend 全量求和 $4482.86，与 KEYWORD_PATH 同窗口 manual_kw 总额分毫不差
 *      （探针6数据$4482.86）——两接口在该筛选下覆盖同一批花费，吃进去=重复计数，无增量；
 *   ③ 返回行含 campaignAndTargetingType="sponsoredProducts+manual" 字段，暗示存在 auto 枚举。
 *
 * 真正根因假设：同步脚本 baseParams 里 campaignType=["sponsoredProducts-manual"] 这个筛选
 * 把自动投放(auto-targeting)型活动整个排除在请求范围外了——修法方向应是放宽/补充该参数的
 * 枚举值，而不是换字段。但正确的枚举值写法未知，本探针逐个试出来。
 *
 * 本探针做的事（纯读取，不落库、不写RAW、不改脚本、不改表）：
 *   对窗口1（2026-07-10~07-15），用5种 campaignType 参数变体分别实时调用 ITEM_PATH
 *   （/basicOpen/multiplatform/ads/reportAdItemSpList），每种变体统计：
 *     - 返回总行数、adSpend总和、按 campaignAndTargetingType 分组的行数+花费
 *     - 目标活动 campaignId=5032288 是否出现、出现的话逐行打印原始JSON并求和 adSpend，
 *       与真实发票该活动 $102.44、现DB仅有的 $10.67 对比
 *   变体清单：
 *     A. 完全不传 campaignType 字段（看接口默认是否返回全部类型）
 *     B. campaignType=["sponsoredProducts-auto"]（按现有枚举命名习惯猜测auto写法）
 *     C. campaignType=["sponsoredProducts-manual","sponsoredProducts-auto"]（手动+自动并列）
 *     D. campaignType=["sponsoredProducts"]（只给产品线不给投放方式）
 *     E. campaignType=[]（空数组，看是否等价于不筛选）
 *   某变体报错不中断，记录错误后继续下一个；末尾输出五变体汇总对照表。
 *
 * 判定标准（写死在输出里）：
 *   哪个变体能让 campaignId=5032288 出现、且该活动 adSpend 加总 ≈ $102.44（±5%），
 *   哪个变体就是同步脚本 campaignType 参数的正确修法；如果所有变体都出现不了，
 *   说明该接口体系拿不到自动广告数据，修法只能另找数据源（如沃尔玛后台CSV口径扩容）。
 *
 * 安全边界：只读 LingXing API（与生产同步脚本同一只读接口）+ 只读 DB SELECT，
 *   零写库、零写RAW、零改动生产脚本、不建表、不改表。
 *
 * 运行（生产机，由部署工程师执行）：
 *   npx ts-node src/probeAdCampaignTypeEnum.ts
 *
 * 用法：把完整输出贴回来，重点看末尾"三、五变体汇总对照表"。
 */

import "dotenv/config";
import * as mysql from "mysql2/promise";
import { loadConfig } from "./config";
import { LingxingClient } from "./lingxingClient";

const ITEM_PATH = "/basicOpen/multiplatform/ads/reportAdItemSpList";
const WINDOW = { label: "窗口1", startDate: "2026-07-10", endDate: "2026-07-15" };

const TARGET_CAMPAIGN_ID = "5032288";           // "YC00029-自动-5.03"
const TARGET_REAL_AMOUNT = 102.44;              // 真实发票该活动窗口1花费
const DB_KNOWN_SPEND = 10.67;                   // 现 fact_ads_keyword_daily 仅有的花费
const MANUAL_BASELINE_TOTAL = 4482.86;          // 探针9：manual筛选下ITEM_PATH全量adSpend总和
const INVOICE_TOTAL = 6607.08;                  // 窗口1真实发票总额（含SBV等其他类型$345.32+）

interface Variant {
  key: string;
  desc: string;
  campaignType: string[] | undefined; // undefined = 不传该字段
}
const VARIANTS: Variant[] = [
  { key: "A", desc: "不传campaignType字段", campaignType: undefined },
  { key: "B", desc: 'campaignType=["sponsoredProducts-auto"]', campaignType: ["sponsoredProducts-auto"] },
  { key: "C", desc: 'campaignType=["sponsoredProducts-manual","sponsoredProducts-auto"]', campaignType: ["sponsoredProducts-manual", "sponsoredProducts-auto"] },
  { key: "D", desc: 'campaignType=["sponsoredProducts"]', campaignType: ["sponsoredProducts"] },
  { key: "E", desc: "campaignType=[]（空数组）", campaignType: [] },
];

interface VariantResult {
  key: string;
  desc: string;
  ok: boolean;
  error: string;
  rows: number;
  totalSpend: number;
  targetRows: number;
  targetSpend: number;
  typeBreakdown: Map<string, { rows: number; spend: number }>;
  distinctCampaigns: number;
}

function toNum(v: unknown): number {
  const n = Number(v);
  return Number.isFinite(n) ? n : 0;
}
function toStr(v: unknown): string {
  return String(v ?? "").trim();
}
function sleep(ms: number): Promise<void> {
  return new Promise((r) => setTimeout(r, ms));
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
  console.log(`目标店铺: store_id=${store.store_id} (${store.store_name})  advertiser_id=${store.advertiser_id}\n`);
  console.log(`=== 一、目标窗口 ${WINDOW.label}: ${WINDOW.startDate} ~ ${WINDOW.endDate} ===`);
  console.log(`    判定基准: campaignId=${TARGET_CAMPAIGN_ID}("YC00029-自动-5.03") 真实发票=$${TARGET_REAL_AMOUNT}；`);
  console.log(`    现DB仅有=$${DB_KNOWN_SPEND}；manual筛选下ITEM_PATH全量=$${MANUAL_BASELINE_TOTAL}；发票总额=$${INVOICE_TOTAL}\n`);

  const cfg = loadConfig();
  const client = new LingxingClient(cfg);

  const results: VariantResult[] = [];

  console.log(`=== 二、逐变体实时调用 ${ITEM_PATH} ===`);
  for (const v of VARIANTS) {
    console.log(`\n────── 变体${v.key}: ${v.desc} ──────`);
    const res: VariantResult = {
      key: v.key, desc: v.desc, ok: false, error: "", rows: 0, totalSpend: 0,
      targetRows: 0, targetSpend: 0, typeBreakdown: new Map(), distinctCampaigns: 0,
    };
    try {
      const allRows: Array<Record<string, unknown>> = [];
      const PAGE_SIZE = 200;
      const MAX_PAGES = 25;
      for (let pageNum = 1; pageNum <= MAX_PAGES; pageNum++) {
        const params: Record<string, unknown> = {
          advertiserIds: [store.advertiser_id],
          startDate: WINDOW.startDate,
          endDate: WINDOW.endDate,
          pageNum,
          pageSize: PAGE_SIZE,
          paging: true,
        };
        if (v.campaignType !== undefined) params.campaignType = v.campaignType;
        const resp = await client.request<unknown>({ method: "POST", path: ITEM_PATH, params, timeoutMs: 60000 });
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

      res.ok = true;
      res.rows = allRows.length;
      const campaignSet = new Set<string>();
      for (const r of allRows) {
        const spend = toNum(r.adSpend);
        res.totalSpend += spend;
        campaignSet.add(toStr(r.campaignId));
        const t = toStr(r.campaignAndTargetingType) || toStr(r.campaignType) || "(空)";
        if (!res.typeBreakdown.has(t)) res.typeBreakdown.set(t, { rows: 0, spend: 0 });
        const b = res.typeBreakdown.get(t)!;
        b.rows += 1;
        b.spend += spend;
      }
      res.distinctCampaigns = campaignSet.size;

      console.log(`  返回行数=${res.rows}  去重活动数=${res.distinctCampaigns}  adSpend总和=$${res.totalSpend.toFixed(2)}`);
      console.log(`  按 campaignAndTargetingType 分组:`);
      for (const [t, b] of [...res.typeBreakdown.entries()].sort((a, b2) => b2[1].spend - a[1].spend)) {
        console.log(`    ${t.padEnd(32)} 行数=${String(b.rows).padEnd(6)} spend=$${b.spend.toFixed(2)}`);
      }

      // 目标活动严格按 campaignId 匹配（探针9教训：不做名称包含兜底，避免捞到同名前缀的手动活动）
      const targetRows = allRows.filter((r) => toStr(r.campaignId) === TARGET_CAMPAIGN_ID);
      res.targetRows = targetRows.length;
      res.targetSpend = targetRows.reduce((a, r) => a + toNum(r.adSpend), 0);
      if (targetRows.length === 0) {
        console.log(`  目标活动 campaignId=${TARGET_CAMPAIGN_ID}: [未出现]`);
      } else {
        console.log(`  目标活动 campaignId=${TARGET_CAMPAIGN_ID}: 出现${targetRows.length}行, adSpend合计=$${res.targetSpend.toFixed(2)} (真实发票$${TARGET_REAL_AMOUNT}, 占比${((res.targetSpend / TARGET_REAL_AMOUNT) * 100).toFixed(1)}%)`);
        console.log(`  逐行原始JSON:`);
        for (const r of targetRows) console.log(JSON.stringify(r, null, 2));
      }
    } catch (err) {
      res.error = err instanceof Error ? err.message : String(err);
      console.log(`  [变体${v.key}请求失败] ${res.error}`);
    }
    results.push(res);
    await sleep(2000);
  }

  console.log(`\n=== 三、五变体汇总对照表 ===\n`);
  console.log(
    "变体".padEnd(4) + "行数".padEnd(8) + "活动数".padEnd(8) + "adSpend总和".padEnd(14) +
    "目标活动行数".padEnd(12) + "目标活动$".padEnd(12) + "对$102.44占比".padEnd(14) + "说明",
  );
  for (const r of results) {
    if (!r.ok) {
      console.log(`${r.key.padEnd(4)}[请求失败: ${r.error.slice(0, 60)}] ${r.desc}`);
      continue;
    }
    const pct = r.targetRows > 0 ? ((r.targetSpend / TARGET_REAL_AMOUNT) * 100).toFixed(1) + "%" : "-";
    console.log(
      r.key.padEnd(4) + String(r.rows).padEnd(8) + String(r.distinctCampaigns).padEnd(8) +
      ("$" + r.totalSpend.toFixed(2)).padEnd(14) + String(r.targetRows).padEnd(12) +
      ("$" + r.targetSpend.toFixed(2)).padEnd(12) + pct.padEnd(14) + r.desc,
    );
  }
  console.log(`\n判定：目标活动出现且金额≈$${TARGET_REAL_AMOUNT}（±5%）的变体 = 同步脚本campaignType参数的正确修法；`);
  console.log(`      全部变体都不出现 = 该接口体系拿不到自动广告花费，需另找数据源，不能改脚本硬凑。`);

  await db.end();
  console.log("\n探针10结束。");
}

main().catch((err) => {
  console.error("探针10执行失败：", err);
  process.exit(1);
});
