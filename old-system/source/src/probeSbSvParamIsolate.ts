/**
 * src/probeSbSvParamIsolate.ts
 *
 * AI财务 · 探针17b —— SB/SV请求信封单变量隔离（只读，零写库，零改动生产）。
 *
 * 背景：
 *   探针16实证：reportAdItemSbList 用 {paging:true, pageSize:50, campaignType:[...]} 信封能返回200
 *   （枚举错误仅0行）；探针17按文档示例改为 {paging:"1", pageSize:200, campaignType:["sba"], day:14}
 *   反而全线400"参数有误"（无字段提示）——枚举值sba/video大概率没错，错在信封改动。
 *   嫌疑（按概率）：①paging应传布尔true（文档示例"1"是直连API写法，网关封装可能校验布尔）；
 *   ②pageSize=200超SB/SV上限（文档示例仅20）；③day字段本身。
 *
 * 本探针（CN2601，窗口1 2026-07-10~07-15）：
 *   第一步 逐变体隔离（对 reportAdItemSbList["sba"] 与 reportAdItemSvList["video"] 各试）：
 *     V1 paging:true + pageSize:50（探针16已证可用的信封+新枚举）
 *     V2 = V1 + day:14
 *     V3 = V1 但 pageSize:200
 *     V4 = V1 但 paging:"1"
 *     V5 = V2 + operationSourceType:"gateway"
 *   首个成功的变体即"可用信封"，并同时定位坏字段。
 *   第二步 用可用信封全量拉取并汇总：行数/字段名/前2条JSON/itemId非空比/按活动聚合adSpend/
 *     SBV样本YC00019对发票$345.32占比；SP$6059.69+SB+SV对发票$6607.08守恒。
 *   第三步 活动级接口（reportCampaignSbList/SvList）用可用信封+day+operationSourceType各拉1页对照。
 *   第四步 day敏感性（3/30）：adSpend不应变、attributedSales应变。
 *
 * 安全边界：只读 LingXing API + 只查 dim_store_config，零写库零改生产。
 * 运行：npx ts-node src/probeSbSvParamIsolate.ts
 */

import "dotenv/config";
import * as mysql from "mysql2/promise";
import { loadConfig } from "./config";
import { LingxingClient } from "./lingxingClient";

const WINDOW = { startDate: "2026-07-10", endDate: "2026-07-15" };
const SBV_SAMPLE = { nameHint: "YC00019", real: 345.32 };
const SP_KNOWN = 6059.69;
const INVOICE_TOTAL = 6607.08;

function toNum(v: unknown): number { const n = Number(v); return Number.isFinite(n) ? n : 0; }
function toStr(v: unknown): string { return String(v ?? "").trim(); }
function sleep(ms: number): Promise<void> { return new Promise((r) => setTimeout(r, ms)); }
function extractList(data: unknown): Array<Record<string, unknown>> {
  if (Array.isArray(data)) return data as Array<Record<string, unknown>>;
  const d = data as { list?: unknown; data?: unknown } | null;
  if (Array.isArray(d?.list)) return d!.list as Array<Record<string, unknown>>;
  if (Array.isArray(d?.data)) return d!.data as Array<Record<string, unknown>>;
  return [];
}
function errInfo(e: unknown): string {
  const anyE = e as { message?: string; data?: unknown };
  return `${anyE?.message ?? String(e)}${anyE?.data ? "  data=" + JSON.stringify(anyE.data).slice(0, 300) : ""}`;
}

async function callOnce(
  client: LingxingClient, path: string, body: Record<string, unknown>,
): Promise<{ ok: boolean; rows: Array<Record<string, unknown>>; err?: string }> {
  try {
    const resp = await client.request<unknown>({ method: "POST", path, params: body, timeoutMs: 60000 });
    return { ok: true, rows: extractList((resp as { data?: unknown }).data) };
  } catch (e) {
    return { ok: false, rows: [], err: errInfo(e) };
  }
}

function summarize(label: string, rows: Array<Record<string, unknown>>): number {
  console.log(`\n【${label}】共 ${rows.length} 行`);
  if (rows.length === 0) return 0;
  const keys = new Set<string>();
  for (const r of rows.slice(0, 50)) for (const k of Object.keys(r)) keys.add(k);
  console.log(`字段名: ${[...keys].sort().join(", ")}`);
  console.log(`前2条原始JSON:`);
  for (const r of rows.slice(0, 2)) console.log(JSON.stringify(r));
  const itemNonEmpty = rows.filter((r) => toStr(r.itemId ?? r.adItemId)).length;
  console.log(`itemId/adItemId 非空行: ${itemNonEmpty}/${rows.length}`);
  const camp = new Map<string, number>();
  let total = 0;
  for (const r of rows) {
    const s = toNum(r.adSpend);
    total += s;
    const n = toStr(r.campaignName) || toStr(r.campaignId) || "(无名)";
    camp.set(n, (camp.get(n) ?? 0) + s);
  }
  console.log(`adSpend总和 = $${total.toFixed(2)}；按活动聚合:`);
  for (const [n, s] of [...camp.entries()].sort((a, b) => b[1] - a[1])) {
    const mark = n.includes(SBV_SAMPLE.nameHint) ? `  ← SBV样本（发票$${SBV_SAMPLE.real}，占比${((s / SBV_SAMPLE.real) * 100).toFixed(1)}%）` : "";
    console.log(`  $${s.toFixed(2).padEnd(10)} ${n}${mark}`);
  }
  return total;
}

async function main() {
  const db = await mysql.createConnection({
    host: process.env.DB_HOST ?? "127.0.0.1", port: Number(process.env.DB_PORT ?? 3306),
    user: process.env.DB_USER ?? "", password: process.env.DB_PASSWORD ?? "",
    database: process.env.DB_NAME ?? "walmart_ai_data",
  });
  const [storeRows] = await db.execute(
    `SELECT store_id, store_name, advertiser_id FROM dim_store_config WHERE platform='walmart' AND store_name LIKE '%瑞盈龙盛%'`,
  );
  await db.end();
  const stores = storeRows as Array<{ store_id: string; store_name: string; advertiser_id: string | null }>;
  if (stores.length === 0 || !stores[0].advertiser_id) { console.log("没匹配到店铺，终止。"); return; }
  const adv = String(stores[0].advertiser_id);
  console.log(`目标店铺: ${stores[0].store_name}  advertiser_id=${adv}  窗口: ${WINDOW.startDate}~${WINDOW.endDate}\n`);

  const client = new LingxingClient(loadConfig());
  const base = { advertiserIds: [adv], startDate: WINDOW.startDate, endDate: WINDOW.endDate, pageNum: 1 };

  const TARGETS: Array<{ label: string; path: string; ct: string }> = [
    { label: "SB", path: "/basicOpen/multiplatform/ads/reportAdItemSbList", ct: "sba" },
    { label: "SV", path: "/basicOpen/multiplatform/ads/reportAdItemSvList", ct: "video" },
  ];

  const working: Record<string, Record<string, unknown> | null> = {};
  console.log(`=== 一、信封单变量隔离 ===`);
  for (const t of TARGETS) {
    console.log(`\n────── ${t.label} ${t.path} campaignType=["${t.ct}"] ──────`);
    const variants: Array<{ name: string; body: Record<string, unknown> }> = [
      { name: "V1 paging:true pageSize:50", body: { ...base, paging: true, pageSize: 50, campaignType: [t.ct] } },
      { name: "V2 =V1+day:14", body: { ...base, paging: true, pageSize: 50, campaignType: [t.ct], day: 14 } },
      { name: "V3 =V1但pageSize:200", body: { ...base, paging: true, pageSize: 200, campaignType: [t.ct] } },
      { name: "V4 =V1但paging:'1'", body: { ...base, paging: "1", pageSize: 50, campaignType: [t.ct] } },
      { name: "V5 =V2+operationSourceType:gateway", body: { ...base, paging: true, pageSize: 50, campaignType: [t.ct], day: 14, operationSourceType: "gateway" } },
    ];
    working[t.label] = null;
    for (const v of variants) {
      const r = await callOnce(client, t.path, v.body);
      console.log(`  [${v.name}] ${r.ok ? `成功，${r.rows.length}行` : `失败: ${r.err}`}`);
      if (r.ok && working[t.label] === null) working[t.label] = v.body;
      await sleep(600);
    }
  }

  // ── 二、可用信封全量拉取 ──
  console.log(`\n=== 二、可用信封全量拉取与汇总 ===`);
  let sbTotal = 0, svTotal = 0;
  for (const t of TARGETS) {
    const env = working[t.label];
    if (!env) { console.log(`\n【${t.label}】无可用信封，跳过（把第一节失败详情贴回分析）`); continue; }
    const all: Array<Record<string, unknown>> = [];
    for (let pageNum = 1; pageNum <= 20; pageNum++) {
      const r = await callOnce(client, t.path, { ...env, pageNum });
      if (!r.ok || r.rows.length === 0) break;
      all.push(...r.rows);
      if (r.rows.length < Number(env.pageSize ?? 50)) break;
      await sleep(500);
    }
    const total = summarize(`${t.label} 全量（信封=${JSON.stringify({ paging: env.paging, pageSize: env.pageSize, day: env.day ?? "(未传,默认14)" })}）`, all);
    if (t.label === "SB") sbTotal = total; else svTotal = total;
    await sleep(800);
  }

  // ── 三、活动级对照 ──
  console.log(`\n=== 三、活动级接口对照（day+operationSourceType 必填）===`);
  for (const [label, path, ct] of [
    ["SB活动级", "/basicOpen/multiplatform/ads/reportCampaignSbList", "sba"],
    ["SV活动级", "/basicOpen/multiplatform/ads/reportCampaignSvList", "video"],
  ] as const) {
    const r = await callOnce(client, path, { ...base, paging: true, pageSize: 50, campaignType: [ct], day: 14, operationSourceType: "gateway" });
    if (r.ok) {
      const total = r.rows.reduce((a, x) => a + toNum(x.adSpend), 0);
      console.log(`  ${label}: 成功 ${r.rows.length}行 adSpend合计=$${total.toFixed(2)}`);
      for (const x of r.rows.slice(0, 2)) console.log(`    样例: ${JSON.stringify(x).slice(0, 400)}`);
    } else {
      console.log(`  ${label}: 失败 ${r.err}`);
    }
    await sleep(800);
  }

  // ── 四、day敏感性 ──
  console.log(`\n=== 四、day敏感性（可用信封+day=3/30；adSpend应不变，attributedSales应变）===`);
  const envSv = working["SV"];
  if (envSv) {
    for (const day of [3, 30]) {
      const r = await callOnce(client, "/basicOpen/multiplatform/ads/reportAdItemSvList", { ...envSv, day, pageNum: 1 });
      if (r.ok) {
        const spend = r.rows.reduce((a, x) => a + toNum(x.adSpend), 0);
        const sales = r.rows.reduce((a, x) => a + toNum(x.attributedSales), 0);
        console.log(`  day=${day}: ${r.rows.length}行 adSpend=$${spend.toFixed(2)} attributedSales=$${sales.toFixed(2)}`);
      } else console.log(`  day=${day}: 失败 ${r.err}`);
      await sleep(600);
    }
  } else console.log(`  SV无可用信封，跳过`);

  console.log(`\n=== 守恒验证 ===`);
  console.log(`SP $${SP_KNOWN.toFixed(2)} + SB $${sbTotal.toFixed(2)} + SV $${svTotal.toFixed(2)} = $${(SP_KNOWN + sbTotal + svTotal).toFixed(2)}`);
  console.log(`对照发票总额 $${INVOICE_TOTAL.toFixed(2)}，覆盖率 ${(((SP_KNOWN + sbTotal + svTotal) / INVOICE_TOTAL) * 100).toFixed(1)}%`);
  console.log("\n探针17b结束。");
}

main().catch((err) => { console.error("探针17b执行失败：", err); process.exit(1); });
