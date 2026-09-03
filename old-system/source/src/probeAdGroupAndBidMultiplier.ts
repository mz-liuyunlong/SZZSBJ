/**
 * probeAdGroupAndBidMultiplier.ts —— 只读探测：广告组接口 + 竞价加倍（页面类型/平台）
 *
 * 【探测前已按 API_MAP 规矩第 0 条通读台账，本次新增探测均不在已探清单内】
 *
 * 目的（需求方 2026-08-21 提出的两个问题）：
 *   ① 有没有独立的「广告组」查询接口 —— 关键词接口只返回**有关键词的**广告组，
 *      自动投放组、刚建还没加词的组拿不到，会让「广告组增减」漏记。
 *   ② 「竞价加倍」的数据能不能抓 —— Walmart Connect 的竞价加倍分两类：
 *        · Placement（页面类型）Bid Multiplier：Buy Box / Search Carousel / Item Page
 *        · Platform Bid Multiplier：Desktop / App / Mobile
 *      对应领星的「页面类型」与「平台」两族接口。
 *      旁证：sql/009 定义的 fact_ads_platform_daily 有 `bid DECIMAL(18,4) COMMENT '当前竞价($)'`
 *      且粒度是 广告组×投放平台 —— 形态与平台竞价加倍吻合（该表在生产从未创建，是空壳）。
 *
 * 路径来源与可信度（**必须如实标注，不得当成已确认事实**）：
 *   - 已实证可用：queryCampaignSpList、reportKeywordSpList、reportKeywordSvList
 *   - 已实证失败：queryPageTypeSPList（2026-07-02，领星服务端"程序内部错误"，8 种参数组合全败，
 *                 见 reports/lingxing_page_type_api_probe.md）。距今约 50 天，**本次重试一次**，
 *                 且这次先用 queryCampaignSpList 拿到真实 campaignIds 再带上（上次失败原因之一疑为缺 campaignIds）。
 *   - **推断路径（未见正文文档，仅由 docs/lingxing/_sidebar.md 的文件名推得）**：
 *       queryGroupSpList        ← walmart-GroupSpList_9.md
 *       reportAdGroupSbList     ← walmart-reportAdGroupSbList_15.md
 *       queryAdGroupSvList      ← walmart-AdGroupSvList_1.md
 *       reportPlatformSbList / reportPlatformSvList / reportPageTypeSbList / reportPageTypeSvList
 *     推断规则：文件名 `walmart-<接口名>_<序号>.md`，文件名带 report 前缀者为 report 系、不带者为 query 系。
 *     **这是推断。跑不通＝路径推错，属正常结果，如实记录后向需求方索取对应 apidoc 页面，不做多轮试错。**
 *
 * 只读约束：只调查询类接口；不建表、不写任何 FACT/DIM/BIZ；每次响应写 raw_lingxing_api 留痕。
 * 限流：queryCampaignSpList 令牌桶容量=1，全部调用间隔 SLEEP_MS（默认 2500ms）。
 * 纪律：业务 code≠0 一律如实打印原始响应，**不改参数重试、不换路径硬试**。
 *
 * 用法：
 *   npx ts-node src/probeAdGroupAndBidMultiplier.ts
 *   npx ts-node src/probeAdGroupAndBidMultiplier.ts --advertiser=571910 --start=2026-08-01 --end=2026-08-18 --sleep=4000
 */
import "dotenv/config";
import * as crypto from "crypto";
import * as mysql from "mysql2/promise";
import { loadConfig } from "./config";
import { LingxingClient } from "./lingxingClient";

const BASE = "/basicOpen/multiplatform/ads/";
const TIMEOUT_MS = 60000;

interface Target {
  label: string;
  path: string;
  campaignType: string[];
  /** true = 路径由 sidebar 文件名推断，未见正文文档 */
  inferred: boolean;
  /** 是否需要带 campaignIds（页面类型接口上次疑因缺此参数失败） */
  needCampaignIds?: boolean;
}

const TARGETS: Target[] = [
  // ① 广告组
  { label: "①-SP 广告组", path: BASE + "queryGroupSpList", campaignType: ["sponsoredProducts-manual", "sponsoredProducts-auto"], inferred: true },
  { label: "①-SB 广告组", path: BASE + "reportAdGroupSbList", campaignType: ["sba"], inferred: true },
  { label: "①-SV 广告组", path: BASE + "queryAdGroupSvList", campaignType: ["video"], inferred: true },
  // ② 竞价加倍 · 页面类型（Placement Bid Multiplier）
  { label: "②-SP 页面类型（2026-07-02 曾失败，本次重试）", path: BASE + "queryPageTypeSPList", campaignType: ["sponsoredProducts-manual", "sponsoredProducts-auto"], inferred: false, needCampaignIds: true },
  { label: "②-SB 页面类型", path: BASE + "reportPageTypeSbList", campaignType: ["sba"], inferred: true, needCampaignIds: true },
  { label: "②-SV 页面类型", path: BASE + "reportPageTypeSvList", campaignType: ["video"], inferred: true, needCampaignIds: true },
  // ③ 竞价加倍 · 平台（Platform Bid Multiplier）
  { label: "③-SP 平台", path: BASE + "reportPlatformSpList", campaignType: ["sponsoredProducts-manual", "sponsoredProducts-auto"], inferred: false },
  { label: "③-SB 平台", path: BASE + "reportPlatformSbList", campaignType: ["sba"], inferred: true },
  { label: "③-SV 平台", path: BASE + "reportPlatformSvList", campaignType: ["video"], inferred: true },
];

/** 竞价加倍/出价类关注字段（宽口径，命名未知，靠模糊匹配兜底） */
const BID_HINTS = ["bid", "multiplier", "modifier", "adjust", "percent", "ratio", "boost"];

function getArg(name: string, dflt: string): string {
  const p = `--${name}=`;
  const a = process.argv.find((x: string) => x.startsWith(p));
  return a ? a.slice(p.length) : dflt;
}
const sleep = (ms: number): Promise<void> => new Promise((r) => setTimeout(r, ms));
const isEmpty = (v: unknown): boolean =>
  v === null || v === undefined || v === "" || (Array.isArray(v) && v.length === 0);

function getDb(): Promise<mysql.Connection> {
  return mysql.createConnection({
    host: process.env.DB_HOST ?? "127.0.0.1",
    port: Number(process.env.DB_PORT ?? 3306),
    user: process.env.DB_USER ?? "",
    password: process.env.DB_PASSWORD ?? "",
    database: process.env.DB_NAME ?? "walmart_ai_data",
  });
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
       VALUES ('lingxing', ?, 'POST', ?, ?, ?, ?, ?, NOW(), ?, JSON_OBJECT('probe','adgroup_bid_multiplier'))`,
      [apiPath, paramsJson, respJson, code, code === "0" ? 1 : 0, dataDate, rawHash],
    );
    return res.insertId ?? null;
  } catch (e) {
    console.warn(`  [RAW写入失败,忽略] ${e instanceof Error ? e.message : String(e)}`);
    return null;
  }
}

function report(rows: Record<string, unknown>[]): void {
  const keys: string[] = [...new Set(rows.flatMap((o: Record<string, unknown>) => Object.keys(o)))].sort();
  console.log(`  样本行数=${rows.length}  字段数=${keys.length}`);
  console.log(`  全部字段名: ${keys.join(", ")}`);

  const hits = keys.filter((k: string) => BID_HINTS.some((h: string) => k.toLowerCase().includes(h)));
  console.log(`  ── 出价/加倍类字段命中（模糊匹配 ${BID_HINTS.join("/")}）──`);
  if (hits.length === 0) {
    console.log("    ❌ 无命中 ⇒ 该接口不含出价或竞价加倍字段");
  } else {
    for (const f of hits) {
      const n = rows.filter((o: Record<string, unknown>) => !isEmpty(o[f])).length;
      const s = rows.find((o: Record<string, unknown>) => !isEmpty(o[f]));
      const mark = n === 0 ? "❌ 全空" : n === rows.length ? "✅ 全有值" : "⚠️ 部分有值";
      console.log(`    ${f.padEnd(24)} ${mark.padEnd(12)} ${n}/${rows.length}  样例=${s ? JSON.stringify(s[f]) : ""}`);
      const m = new Map<string, number>();
      for (const r of rows) m.set(isEmpty(r[f]) ? "(空)" : String(r[f]), (m.get(isEmpty(r[f]) ? "(空)" : String(r[f])) ?? 0) + 1);
      console.log(`      分布: ${[...m.entries()].sort((a, b) => b[1] - a[1]).slice(0, 8).map(([k, n2]) => `${k}=${n2}`).join("  ")}`);
    }
  }
  // 维度键（决定唯一键怎么定）
  const dim = ["campaignId", "adGroupId", "adGroupName", "adGroupStatus", "pageType", "placement", "platform", "adPlatform", "campaignType", "targetingType", "entityCreateAt"];
  console.log(`  ── 维度/状态字段 ──`);
  for (const f of dim) {
    if (!keys.includes(f)) continue;
    const n = rows.filter((o: Record<string, unknown>) => !isEmpty(o[f])).length;
    const s = rows.find((o: Record<string, unknown>) => !isEmpty(o[f]));
    console.log(`    ${f.padEnd(20)} ${n}/${rows.length}  样例=${s ? JSON.stringify(s[f]) : ""}`);
  }
  console.log(`  ── 首行完整 JSON ──`);
  console.log("  " + JSON.stringify(rows[0]).slice(0, 1400));
}

async function main(): Promise<void> {
  const advertiserId = Number(getArg("advertiser", "571910")); // CN2601，SP/SV 都有数据
  const startDate = getArg("start", "2026-08-01");
  const endDate = getArg("end", "2026-08-18");
  const sleepMs = Number(getArg("sleep", "2500"));

  const client = new LingxingClient(loadConfig());
  const db = await getDb();

  console.log("═".repeat(80));
  console.log("广告组接口 + 竞价加倍（页面类型/平台）只读探测");
  console.log(`  advertiserId=${advertiserId}  区间=${startDate}~${endDate}  间隔=${sleepMs}ms`);
  console.log("  ⚠️ 9 个目标中 7 个路径为 sidebar 文件名**推断**，跑不通属正常结果");
  console.log("═".repeat(80));

  const summary: string[] = [];

  // 先拿真实 campaignIds（页面类型接口需要）
  let campaignIds: number[] = [];
  try {
    const r = await client.request<unknown>({
      method: "POST", path: BASE + "queryCampaignSpList", timeoutMs: TIMEOUT_MS,
      params: {
        advertiserIds: [advertiserId],
        campaignType: ["sponsoredProducts-manual", "sponsoredProducts-auto"],
        day: 14, startDate, endDate, operationSourceType: "gateway",
        pageNum: 1, pageSize: 50, paging: true,
      },
    });
    const list = (r as { data?: { list?: unknown } })?.data?.list;
    if (Array.isArray(list)) {
      campaignIds = [...new Set((list as Record<string, unknown>[])
        .map((o) => Number(o.campaignId)).filter((n) => Number.isFinite(n) && n > 0))].slice(0, 20);
    }
    console.log(`\n预备：取到 ${campaignIds.length} 个真实 campaignId（供页面类型接口使用）: ${campaignIds.slice(0, 5).join(",")}…`);
  } catch (e) {
    console.warn(`预备步骤失败（不影响后续，页面类型将不带 campaignIds）: ${e instanceof Error ? e.message : String(e)}`);
  }
  await sleep(sleepMs);

  for (const t of TARGETS) {
    console.log(`\n══════════ ${t.label}${t.inferred ? "  【路径为推断】" : ""}\n           ${t.path} ══════════`);
    const params: Record<string, unknown> = {
      advertiserIds: [advertiserId],
      campaignType: t.campaignType,
      startDate, endDate, day: 14,
      pageNum: 1, pageSize: 200, paging: true,
      operationSourceType: "gateway",
    };
    if (t.needCampaignIds && campaignIds.length > 0) params.campaignIds = campaignIds;
    console.log(`  请求参数: ${JSON.stringify(params)}`);

    try {
      const resp = await client.request<unknown>({ method: "POST", path: t.path, params, timeoutMs: TIMEOUT_MS });
      const rawId = await insertRaw(db, t.path, params, resp, endDate);
      const code = (resp as { code?: unknown })?.code;
      const msg = (resp as { message?: unknown })?.message;
      const total = (resp as { data?: { total?: unknown } })?.data?.total;
      console.log(`  业务 code=${String(code)} | message=${String(msg ?? "")} | data.total=${total ?? "?"} | raw_id=${rawId ?? "?"}`);

      if (String(code) !== "0") {
        console.log("  ✗ 业务失败，原始响应前 600 字符（**不改参数重试、不换路径硬试**）：");
        console.log("  " + JSON.stringify(resp).slice(0, 600));
        summary.push(`${t.label.padEnd(34)} ✗ code=${String(code)} ${String(msg ?? "")}`);
        continue;
      }
      const d = (resp as { data?: { list?: unknown } })?.data;
      const rows: Record<string, unknown>[] = Array.isArray(d?.list) ? (d?.list as Record<string, unknown>[]) : [];
      if (rows.length === 0) {
        console.log("  ⚠️ code=0 但 0 行。注意：**0 行 ≠ 接口不可用**（API_MAP §6-2），先排除本账号无该类数据。");
        console.log("  " + JSON.stringify(resp).slice(0, 500));
        summary.push(`${t.label.padEnd(34)} ⚠ code=0 但 0 行（接口通、无数据）`);
        continue;
      }
      report(rows);
      const keys = [...new Set(rows.flatMap((o) => Object.keys(o)))];
      const bidHit = keys.filter((k) => BID_HINTS.some((h) => k.toLowerCase().includes(h)));
      summary.push(`${t.label.padEnd(34)} ✅ ${rows.length} 行 | 出价类字段: ${bidHit.length ? bidHit.join(",") : "无"}`);
    } catch (e) {
      console.error(`  ✗ 调用异常: ${e instanceof Error ? e.message : String(e)}`);
      summary.push(`${t.label.padEnd(34)} ✗ 异常（多为路径不存在，说明推断错误）`);
    } finally {
      await sleep(sleepMs);
    }
  }

  console.log("\n" + "═".repeat(80));
  console.log("汇总");
  console.log("═".repeat(80));
  summary.forEach((x: string) => console.log("  " + x));
  console.log("\n  说明：本脚本只取事实。哪些接口该接入、竞价加倍怎么落表，由代码侧与需求方讨论后另定。");
  await db.end().catch(() => undefined);
}

main().catch((e: unknown) => { console.error("探测脚本异常:", e); process.exit(1); });
