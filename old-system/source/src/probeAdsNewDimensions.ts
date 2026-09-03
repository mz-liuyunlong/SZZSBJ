/**
 * probeAdsNewDimensions.ts —— 只读双探测（platform + page_type）
 *
 * 目的：为"新增两个广告维度 FACT 表"做地基验证。
 *   - 调 reportPlatformSpList（平台维度）+ queryPageTypeSPList（页面类型维度）
 *   - 每页响应写入 raw_lingxing_api（RAW 留痕，幂等 raw_hash）
 *   - 打印字段清单：字段名 / 样例值 / 类型 / 非空率
 *   - 重点判定：page_type 是否返回 advertiserId/campaignId/adGroupId/pageType/date（定唯一键）
 *
 * 只读：不建 FACT 表、不写 FACT、不改任何现有同步逻辑。
 * 用法：npx ts-node src/probeAdsNewDimensions.ts [--date=2026-06-25] [--advertiser=502543]
 */
import "dotenv/config";
import * as crypto from "crypto";
import * as mysql from "mysql2/promise";
import { loadConfig } from "./config";
import { LingxingClient } from "./lingxingClient";

const PLATFORM_PATH = "/basicOpen/multiplatform/ads/reportPlatformSpList";
const PAGETYPE_PATH = "/basicOpen/multiplatform/ads/queryPageTypeSPList";
const TIMEOUT_MS = 60000;

function getArg(name: string, dflt: string): string {
  const p = `--${name}=`;
  const a = process.argv.find((x) => x.startsWith(p));
  return a ? a.slice(p.length) : dflt;
}

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
       VALUES ('lingxing', ?, 'POST', ?, ?, ?, ?, ?, NOW(), ?, JSON_OBJECT('probe','ads_new_dimensions'))`,
      [apiPath, paramsJson, respJson, code, code === "0" ? 1 : 0, dataDate, rawHash],
    );
    return res.insertId ?? null;
  } catch (e) {
    console.warn(`  [RAW写入失败,忽略] ${e instanceof Error ? e.message : String(e)}`);
    return null;
  }
}

function analyze(items: Record<string, unknown>[]): void {
  const keys = new Set<string>();
  items.forEach((it) => Object.keys(it).forEach((k) => keys.add(k)));
  console.log(`  样本行数: ${items.length}，字段数: ${keys.size}`);
  console.log(`  ${"字段名".padEnd(28)} ${"类型".padEnd(8)} ${"非空".padEnd(7)} 样例值`);
  console.log(`  ${"-".repeat(70)}`);
  for (const k of [...keys].sort()) {
    let sample: unknown = null, nonNull = 0;
    for (const it of items) {
      const v = it[k];
      if (v !== null && v !== undefined && v !== "") { nonNull++; if (sample === null) sample = v; }
    }
    const type = sample === null ? "(全空)" : Array.isArray(sample) ? "array" : typeof sample;
    const sampleStr = sample === null ? "" : typeof sample === "object" ? JSON.stringify(sample) : String(sample);
    console.log(`  ${k.padEnd(28)} ${type.padEnd(8)} ${String(nonNull + "/" + items.length).padEnd(7)} ${sampleStr.slice(0, 60)}`);
  }
  // 维度字段判定（决定唯一键）
  const has = (names: string[]) => names.find((n) => [...keys].some((k) => k.toLowerCase() === n.toLowerCase()));
  console.log(`  ── 维度字段判定 ──`);
  console.log(`    advertiserId : ${has(["advertiserId", "advertiser_id"]) ?? "❌无"}`);
  console.log(`    campaignId   : ${has(["campaignId", "campaign_id"]) ?? "❌无"}`);
  console.log(`    adGroupId    : ${has(["adGroupId", "ad_group_id"]) ?? "❌无"}`);
  console.log(`    date/日期     : ${has(["date", "stat_date", "reportDate"]) ?? "❌无"}`);
  console.log(`    pageType/位置 : ${has(["pageType", "page_type", "placement", "placementType", "position", "adPlacement"]) ?? "❌无(需在字段清单里人工找)"}`);
  console.log(`    store_id     : ${has(["store_id", "storeId"]) ?? "❌无(需用 advertiserId 反查 dim_store_config)"}`);
}

async function probe(
  db: mysql.Connection, client: LingxingClient, label: string, path: string,
  params: Record<string, unknown>, dataDate: string,
): Promise<Record<string, unknown>[]> {
  console.log(`\n══════════ ${label}  ${path} ══════════`);
  console.log(`  请求参数: ${JSON.stringify(params).slice(0, 300)}`);
  try {
    const resp = await client.request<unknown>({ method: "POST", path, params, timeoutMs: TIMEOUT_MS });
    const rawId = await insertRaw(db, path, params, resp, dataDate);
    const total = (resp as { data?: { total?: unknown } })?.data?.total;
    console.log(`  ✓ 调用成功 | data.total=${total ?? "?"} | raw_lingxing_api.id=${rawId ?? "?"}`);
    const items = dataList(resp);
    if (items.length === 0) {
      console.log("  ⚠️ 返回 0 行。原始响应前 500 字符：");
      console.log("  " + JSON.stringify(resp).slice(0, 500));
      return [];
    }
    analyze(items);
    console.log(`  ── 首行完整 JSON（供人工核字段）──`);
    console.log("  " + JSON.stringify(items[0]).slice(0, 1200));
    return items;
  } catch (e) {
    console.error(`  ✗ ${label} 调用失败: ${e instanceof Error ? e.message : String(e)}`);
    return [];
  }
}

async function main(): Promise<void> {
  const dataDate = getArg("date", "2026-06-25");
  const advertiserId = getArg("advertiser", "502543"); // 默认 CN2502-悦斯（活跃、有广告）
  const startDate = dataDate, endDate = dataDate;
  const client = new LingxingClient(loadConfig());
  const db = await getDb();
  console.log(`探测日期=${dataDate}  advertiserId=${advertiserId}`);
  try {
    // 1) 平台维度
    const platItems = await probe(db, client, "① 平台维度 reportPlatformSpList", PLATFORM_PATH, {
      advertiserIds: [Number(advertiserId)],
      campaignType: ["sponsoredProducts-manual", "sponsoredProducts-auto"],
      startDate, endDate, pageNum: 1, pageSize: 50, paging: true,
    }, dataDate);

    // 从平台数据取真实 campaignId 给页面类型探测（页面类型上一版空 campaignIds 报"程序内部错误"）
    const campaignIds = [...new Set(platItems.map((r) => Number(r.campaignId)).filter((n) => Number.isFinite(n) && n > 0))].slice(0, 20);
    console.log(`\n  取到 ${campaignIds.length} 个 campaignId 供页面类型探测: ${campaignIds.slice(0, 5).join(",")}...`);

    // 2) 页面类型：一次跑多种参数组合，哪个通用哪个
    const adv = Number(advertiserId);
    const CT = ["sponsoredProducts-manual", "sponsoredProducts-auto"];
    const c1 = campaignIds[0];
    const variants: { label: string; params: Record<string, unknown> }[] = [
      { label: "V1 极简+campaignType", params: { advertiserIds: [adv], campaignType: CT, startDate, endDate } },
      { label: "V2 adDatePicker=区间,无startDate", params: { advertiserIds: [adv], campaignType: CT, adDatePicker: [startDate, endDate], day: 1, pageNum: 1, pageSize: 50 } },
      { label: "V3 全参+单campaign", params: { advertiserIds: [adv], campaignType: CT, startDate, endDate, adDatePicker: [startDate, endDate], day: 1, pageNum: 1, pageSize: 50, campaignIds: c1 ? [c1] : [] } },
      { label: "V4 宽日期区间", params: { advertiserIds: [adv], campaignType: CT, startDate: "2026-06-20", endDate: "2026-06-25", pageNum: 1, pageSize: 50 } },
      { label: "V5 campaignType仅manual", params: { advertiserIds: [adv], campaignType: ["sponsoredProducts-manual"], startDate, endDate, pageNum: 1, pageSize: 50 } },
    ];
    let ok = false;
    for (const v of variants) {
      const items = await probe(db, client, `② 页面类型 ${v.label}`, PAGETYPE_PATH, v.params, dataDate);
      if (items.length > 0) { console.log(`\n  ✅ 变体【${v.label}】成功返回数据，以此确定字段/唯一键。`); ok = true; break; }
    }
    if (!ok) console.log(`\n  ❌ 所有变体都失败（多为"程序内部错误"）→ 判断为领星该接口对本账号/站点有问题，需另议。`);
  } finally {
    await db.end();
  }
  console.log("\n探测完成（只写了 raw_lingxing_api，未建/写任何 FACT 表）。");
}

main().catch((e) => { console.error("探测失败:", e); process.exit(1); });
