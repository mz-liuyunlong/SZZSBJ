/**
 * probeAdsBidBudgetStrategy.ts —— 只读探测：广告出价 / 预算 / 竞价策略 / 分时策略
 *
 * 背景（需求方 2026-08-21 提问）：
 *   ① 所有广告类型的 BID 能不能拿到  ② 广告预算能不能拿到  ③ SEM 竞价策略变化能不能拿到
 * 需求方已提供三份领星 apidoc 存档，逐字核对后确认下列字段在文档中存在，本脚本负责**实测是否真有值**：
 *   - queryCampaignSpList : dailyBudget / totalBudget / budgetType / rollover
 *                           biddingStrategy{strategy(DYNAMIC|FIXED|TROAS), troas, biddingStrategyStatus}
 *                           appliedTemplate[]{taskType(BID_ADJUSTMENT|STATUS_CONTROL|BUDGET_AD…), taskStatus,
 *                                             effectiveTime{begin,end}, benchmarkType, curBenchmarkVal, timezone}
 *                           isApplyTime / benchmarkVal / campaignStatus / targetingType
 *   - reportKeywordSbList : keywordBid / keywordId / keywordStatus / matchType / adGroupStatus / appliedTemplate
 *   - reportKeywordSvList : 同上
 *
 * 本次要用实测回答的三个判定（**文档写了不等于有值**）：
 *   A. queryCampaignSpList 的请求 campaignType 只在文档示例里出现 SP manual/auto，
 *      但响应 campaignType 枚举含 sba/video、且带大量「仅SV视频广告」字段
 *      → 传 ["sba"] / ["video"] 到底能不能返回数据？能，则**一个接口拿全三类活动的预算与策略**。
 *   B. dailyBudget/totalBudget/biddingStrategy 在本账号本店铺是否真有非空值（非文档示例值）。
 *   C. SB/SV 的 keywordBid 是否真有值（SP 的 keyword_bid 已入库、覆盖 52.39%）。
 *
 * 只读约束（照 probeAdsNewDimensions.ts 先例 + CODE_DEPLOY_SOP）：
 *   - 只调 query 系与 report 系只读接口；**不建表、不写任何 FACT/DIM、不改任何现有同步逻辑、不动定时任务**
 *   - 每页响应写 raw_lingxing_api 留痕（RAW 层留存原始响应＝铁律，非"写业务库"）
 *   - 限流：queryCampaignSpList 文档标注**令牌桶容量=1**，故所有调用间隔 SLEEP_MS，默认 2500ms
 *   - 失败即如实打印 code/message 与原始响应片段，**绝不改写参数去凑一个"成功"**
 *     （前车之鉴：reports/lingxing_page_type_api_probe.md —— 同族 queryPageTypeSPList 在 2026-07-02
 *       被领星服务端以"程序内部错误"拒绝，8 种参数组合全败，最终结论是服务端问题而非参数问题）
 *
 * 用法：
 *   npx ts-node src/probeAdsBidBudgetStrategy.ts
 *   npx ts-node src/probeAdsBidBudgetStrategy.ts --start=2026-08-01 --end=2026-08-18 --advertiser=502543
 *   npx ts-node src/probeAdsBidBudgetStrategy.ts --sleep=4000        # 撞限流时加大间隔
 */
import "dotenv/config";
import * as crypto from "crypto";
import * as mysql from "mysql2/promise";
import { loadConfig } from "./config";
import { LingxingClient } from "./lingxingClient";

const P_CAMPAIGN_SP = "/basicOpen/multiplatform/ads/queryCampaignSpList";
const P_KEYWORD_SB = "/basicOpen/multiplatform/ads/reportKeywordSbList";
const P_KEYWORD_SV = "/basicOpen/multiplatform/ads/reportKeywordSvList";
const TIMEOUT_MS = 60000;

function getArg(name: string, dflt: string): string {
  const p = `--${name}=`;
  const a = process.argv.find((x) => x.startsWith(p));
  return a ? a.slice(p.length) : dflt;
}
const sleep = (ms: number): Promise<void> => new Promise((r) => setTimeout(r, ms));

function getDb(): Promise<mysql.Connection> {
  return mysql.createConnection({
    host: process.env.DB_HOST ?? "127.0.0.1",
    port: Number(process.env.DB_PORT ?? 3306),
    user: process.env.DB_USER ?? "",
    password: process.env.DB_PASSWORD ?? "",
    database: process.env.DB_NAME ?? "walmart_ai_data",
  });
}

function dataList(resp: unknown): Record<string, unknown>[] {
  const d = (resp as { data?: unknown })?.data;
  if (Array.isArray(d)) return d as Record<string, unknown>[];
  const list = (d as { list?: unknown })?.list;
  return Array.isArray(list) ? (list as Record<string, unknown>[]) : [];
}

async function insertRaw(
  db: mysql.Connection, apiPath: string, params: unknown, resp: unknown, dataDate: string,
): Promise<number | null> {
  try {
    const paramsJson = JSON.stringify(params);
    const respJson = JSON.stringify(resp);
    const rawHash = crypto.createHash("sha256").update(paramsJson + respJson).digest("hex");
    const code = String((resp as { code?: unknown })?.code ?? "");
    const [res] = await db.query<mysql.ResultSetHeader>(
      `INSERT INTO raw_lingxing_api
         (source_system, api_path, request_method, request_params_json, response_json,
          response_code, is_success, data_date, pulled_at, raw_hash, extra_json)
       VALUES ('lingxing', ?, 'POST', ?, ?, ?, ?, ?, NOW(), ?, JSON_OBJECT('probe','ads_bid_budget_strategy'))`,
      [apiPath, paramsJson, respJson, code, code === "0" ? 1 : 0, dataDate, rawHash],
    );
    return res.insertId ?? null;
  } catch (e) {
    console.warn(`  [RAW写入失败,忽略] ${e instanceof Error ? e.message : String(e)}`);
    return null;
  }
}

/** 字段清单：名 / 类型 / 非空率 / 样例（对象与数组打 JSON，便于看嵌套结构） */
function analyze(items: Record<string, unknown>[]): void {
  const keys = new Set<string>();
  items.forEach((it) => Object.keys(it).forEach((k) => keys.add(k)));
  console.log(`  样本行数: ${items.length}，字段数: ${keys.size}`);
  console.log(`  ${"字段名".padEnd(30)} ${"类型".padEnd(8)} ${"非空".padEnd(9)} 样例值`);
  console.log(`  ${"-".repeat(76)}`);
  for (const k of [...keys].sort()) {
    let sample: unknown = null, nonNull = 0;
    for (const it of items) {
      const v = it[k];
      const empty = v === null || v === undefined || v === "" ||
        (Array.isArray(v) && v.length === 0) ||
        (typeof v === "object" && v !== null && !Array.isArray(v) && Object.keys(v).length === 0);
      if (!empty) { nonNull++; if (sample === null) sample = v; }
    }
    const type = sample === null ? "(全空)" : Array.isArray(sample) ? "array" : typeof sample;
    const s = sample === null ? "" : typeof sample === "object" ? JSON.stringify(sample) : String(sample);
    console.log(`  ${k.padEnd(30)} ${type.padEnd(8)} ${(nonNull + "/" + items.length).padEnd(9)} ${s.slice(0, 70)}`);
  }
}

/** 针对本次三个问题的定向判定：这些字段"文档有"到底等不等于"实测有值" */
function verdict(label: string, items: Record<string, unknown>[], fields: string[]): void {
  console.log(`  ── ${label} 定向判定（文档有 ≠ 实测有值）──`);
  if (items.length === 0) { console.log("    (无数据行，无法判定)"); return; }
  for (const f of fields) {
    let nonNull = 0; let sample: unknown = null;
    for (const it of items) {
      const v = it[f];
      const empty = v === null || v === undefined || v === "" ||
        (Array.isArray(v) && v.length === 0) ||
        (typeof v === "object" && v !== null && !Array.isArray(v) && Object.keys(v).length === 0);
      if (!empty) { nonNull++; if (sample === null) sample = v; }
    }
    const mark = nonNull === 0 ? "❌ 全空" : nonNull === items.length ? "✅ 全有值" : "⚠️ 部分有值";
    const s = sample === null ? "" : typeof sample === "object" ? JSON.stringify(sample) : String(sample);
    console.log(`    ${f.padEnd(24)} ${mark.padEnd(12)} ${nonNull}/${items.length}  样例=${s.slice(0, 80)}`);
  }
  // 取值分布（策略类字段最关心分布，全是同一个值＝无区分度，如自动广告CSV的 Current Bidding Strategy 实测全 Fixed）
  const dist = (f: string, pick: (v: unknown) => string): void => {
    const c = new Map<string, number>();
    for (const it of items) { const key = pick(it[f]); c.set(key, (c.get(key) ?? 0) + 1); }
    const top = [...c.entries()].sort((a, b) => b[1] - a[1]).slice(0, 8);
    console.log(`    分布 ${f}: ${top.map(([k, n]) => `${k}=${n}`).join("  ")}`);
  };
  if (items.some((i) => "biddingStrategy" in i)) {
    dist("biddingStrategy", (v) => {
      const o = v as { strategy?: unknown } | null;
      return o && typeof o === "object" ? String(o.strategy ?? "(无strategy键)") : String(v ?? "(空)");
    });
  }
  if (items.some((i) => "budgetType" in i)) dist("budgetType", (v) => String(v ?? "(空)"));
  if (items.some((i) => "campaignStatus" in i)) dist("campaignStatus", (v) => String(v ?? "(空)"));
  if (items.some((i) => "targetingType" in i)) dist("targetingType", (v) => String(v ?? "(空)"));
  if (items.some((i) => "matchType" in i)) dist("matchType", (v) => String(v ?? "(空)"));
  if (items.some((i) => "isApplyTime" in i)) dist("isApplyTime", (v) => String(v ?? "(空)"));
}

async function probe(
  db: mysql.Connection, client: LingxingClient, label: string, path: string,
  params: Record<string, unknown>, dataDate: string, sleepMs: number,
): Promise<Record<string, unknown>[]> {
  console.log(`\n══════════ ${label}\n           ${path} ══════════`);
  console.log(`  请求参数: ${JSON.stringify(params)}`);
  try {
    const resp = await client.request<unknown>({ method: "POST", path, params, timeoutMs: TIMEOUT_MS });
    const rawId = await insertRaw(db, path, params, resp, dataDate);
    const code = (resp as { code?: unknown })?.code;
    const msg = (resp as { message?: unknown; msg?: unknown })?.message ?? (resp as { msg?: unknown })?.msg;
    const total = (resp as { data?: { total?: unknown } })?.data?.total;
    console.log(`  业务 code=${String(code)} | message=${String(msg ?? "")} | data.total=${total ?? "?"} | raw_id=${rawId ?? "?"}`);
    if (String(code) !== "0") {
      console.log(`  ✗ 业务失败。原始响应前 800 字符（**不改参数重试，如实记录**）：`);
      console.log("  " + JSON.stringify(resp).slice(0, 800));
      return [];
    }
    const items = dataList(resp);
    if (items.length === 0) {
      console.log("  ⚠️ code=0 但返回 0 行。原始响应前 800 字符：");
      console.log("  " + JSON.stringify(resp).slice(0, 800));
      return [];
    }
    analyze(items);
    console.log(`  ── 首行完整 JSON（供人工核嵌套结构）──`);
    console.log("  " + JSON.stringify(items[0]).slice(0, 1500));
    return items;
  } catch (e) {
    console.error(`  ✗ ${label} 调用异常: ${e instanceof Error ? e.message : String(e)}`);
    return [];
  } finally {
    await sleep(sleepMs); // 令牌桶容量=1，务必限速
  }
}

async function main(): Promise<void> {
  const startDate = getArg("start", "2026-08-01");
  const endDate = getArg("end", "2026-08-18");   // 文档：间隔不得超过 31 天
  const advertiserId = Number(getArg("advertiser", "502543")); // 默认 CN2502-悦斯电子（历史探针同一样本）
  const sleepMs = Number(getArg("sleep", "2500"));
  const day = Number(getArg("day", "14"));       // 归因天数，枚举 3/14/30

  const client = new LingxingClient(loadConfig());
  const db = await getDb();
  console.log("═".repeat(80));
  console.log(`广告 出价/预算/竞价策略 只读探测`);
  console.log(`  日期区间=${startDate} ~ ${endDate}  advertiserId=${advertiserId}  归因天数=${day}  调用间隔=${sleepMs}ms`);
  console.log(`  只读：不建表、不写 FACT/DIM，仅 raw_lingxing_api 留痕`);
  console.log("═".repeat(80));

  const CAMPAIGN_FIELDS = [
    "dailyBudget", "totalBudget", "budgetType", "rollover",
    "biddingStrategy", "isApplyTime", "appliedTemplate", "benchmarkVal",
    "campaignStatus", "targetingType", "campaignType", "startDate", "endDate", "entityCreateAt",
  ];
  const KEYWORD_FIELDS = [
    "keywordBid", "keywordId", "keywordName", "keywordStatus", "matchType",
    "adGroupStatus", "campaignStatus", "appliedTemplate", "isApplyTime", "benchmarkVal",
  ];

  const campaignBase = {
    advertiserIds: [advertiserId],
    day, startDate, endDate,
    operationSourceType: "gateway",   // 文档：openapi 调用必传 gateway
    pageNum: 1, pageSize: 200, paging: true,
  };

  try {
    // ── A. 活动级预算 + 竞价策略：分三次，分别测 SP / SB / SV 能否走同一个接口 ──
    const spCamp = await probe(db, client, "①-A SP活动（预算+竞价策略）campaignType=[SP手动,SP自动]",
      P_CAMPAIGN_SP, { ...campaignBase, campaignType: ["sponsoredProducts-manual", "sponsoredProducts-auto"] },
      endDate, sleepMs);
    verdict("SP活动", spCamp, CAMPAIGN_FIELDS);

    const sbCamp = await probe(db, client, "①-B SB活动（测同一接口能否返回SB）campaignType=[sba]",
      P_CAMPAIGN_SP, { ...campaignBase, campaignType: ["sba"] }, endDate, sleepMs);
    verdict("SB活动", sbCamp, CAMPAIGN_FIELDS);

    const svCamp = await probe(db, client, "①-C SV活动（测同一接口能否返回SV）campaignType=[video]",
      P_CAMPAIGN_SP, { ...campaignBase, campaignType: ["video"] }, endDate, sleepMs);
    verdict("SV活动", svCamp, CAMPAIGN_FIELDS);

    // ── B. SB / SV 关键词出价 ──
    const kwBase = { advertiserIds: [advertiserId], startDate, endDate, day, pageNum: 1, pageSize: 200, paging: true };
    const sbKw = await probe(db, client, "② SB关键词出价 reportKeywordSbList",
      P_KEYWORD_SB, { ...kwBase, campaignType: ["sba"] }, endDate, sleepMs);
    verdict("SB关键词", sbKw, KEYWORD_FIELDS);

    const svKw = await probe(db, client, "③ SV关键词出价 reportKeywordSvList",
      P_KEYWORD_SV, { ...kwBase, campaignType: ["video"] }, endDate, sleepMs);
    verdict("SV关键词", svKw, KEYWORD_FIELDS);

    // ── 汇总（只陈述事实，不下"该怎么做"的结论）──
    console.log("\n" + "═".repeat(80));
    console.log("汇总（行数为本次样本，非全量）");
    console.log("═".repeat(80));
    const line = (k: string, n: number, note: string): void =>
      console.log(`  ${k.padEnd(34)} ${String(n).padStart(5)} 行   ${note}`);
    line("queryCampaignSpList [SP手动+自动]", spCamp.length, "预算/竞价策略/分时策略");
    line("queryCampaignSpList [sba]", sbCamp.length, "0行=该接口不覆盖SB活动");
    line("queryCampaignSpList [video]", svCamp.length, "0行=该接口不覆盖SV活动");
    line("reportKeywordSbList [sba]", sbKw.length, "SB关键词出价");
    line("reportKeywordSvList [video]", svKw.length, "SV关键词出价");
    console.log("\n  注：本脚本只取事实。字段是否够用、要不要建表落库、快照频率如何定，由代码侧另行讨论后出方案。");
  } finally {
    await db.end().catch(() => undefined);
  }
}

main().catch((e) => { console.error("探测脚本异常:", e); process.exit(1); });
