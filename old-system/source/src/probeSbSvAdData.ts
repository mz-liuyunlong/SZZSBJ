/**
 * src/probeSbSvAdData.ts
 *
 * AI财务 · 探针17 —— SB/SV广告数据定型验证（按官方API文档精确构造参数；只读，零写库，零改动生产）。
 *
 * 文档定型参数（需求方提供的6页领星API文档，2026-08-06解析）：
 *   campaignType 枚举全集: sponsoredProducts-manual / sponsoredProducts-auto / sba(SB品牌) / video(SV视频)
 *   —— SB报告"必须且只能携带sba"，SV报告"必须且只能携带video"（探针16盲猜失败根因）。
 *   day = 归因天数，枚举 3/14/30；广告(AdItem)接口非必填默认14，活动(Campaign)接口必填。
 *   operationSourceType = 操作来源，"openapi调用必传gateway"（Campaign接口必填）。
 *   startDate/endDate 间隔不能超过31天。
 *   reportAdItemSvList 响应字段含 itemId/adItemId —— SV有商品级原生归属（SB待本探针实证）。
 *
 * 验证目标（CN2601，窗口1 2026-07-10~07-15）：
 *   ① SB(reportAdItemSbList, ["sba"]) 与 SV(reportAdItemSvList, ["video"]) 实际返回什么：
 *      行数/字段名/前2条原始JSON/itemId是否非空/按活动聚合adSpend。
 *   ② 发票核对：YC00019-SBV-5.11-TEST 窗口1真实花费$345.32——在SB还是SV里、金额占比多少。
 *   ③ 守恒验证：SP已知$6059.69，发票总额$6607.08，缺口$547.39——SB总+SV总 ≈ 缺口？
 *      （若≈100%，广告五分类的守恒等式2即完全闭环）
 *   ④ Campaign级接口(reportCampaignSbList/SvList, 带day+operationSourceType)各调1页对照总额。
 *   ⑤ day参数敏感性：对命中SBV活动，day=3/14/30各查一次——adSpend应不随归因天数变
 *      （花费点击即定，归因只影响出单/销售额），实证以定同步参数。
 *
 * 安全边界：只读 LingXing API + 只查 dim_store_config，零写库、零写RAW、零改动生产。
 * 运行（生产机，由部署工程师执行）：npx ts-node src/probeSbSvAdData.ts
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
  return `${anyE?.message ?? String(e)}${anyE?.data ? "  data=" + JSON.stringify(anyE.data).slice(0, 400) : ""}`;
}

async function fetchAll(
  client: LingxingClient, path: string, extra: Record<string, unknown>, advertiserId: string,
): Promise<Array<Record<string, unknown>>> {
  const rows: Array<Record<string, unknown>> = [];
  for (let pageNum = 1; pageNum <= 10; pageNum++) {
    const resp = await client.request<unknown>({
      method: "POST", path,
      params: { advertiserIds: [advertiserId], startDate: WINDOW.startDate, endDate: WINDOW.endDate,
                pageNum, pageSize: 200, paging: "1", ...extra },
      timeoutMs: 60000,
    });
    const list = extractList((resp as { data?: unknown }).data);
    if (list.length === 0) break;
    rows.push(...list);
    if (list.length < 200) break;
    await sleep(500);
  }
  return rows;
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
  console.log(`目标店铺: ${stores[0].store_name}  advertiser_id=${adv}  窗口: ${WINDOW.startDate}~${WINDOW.endDate}`);
  console.log(`基准: SP已知$${SP_KNOWN}，发票总额$${INVOICE_TOTAL}，缺口$${(INVOICE_TOTAL - SP_KNOWN).toFixed(2)}\n`);

  const client = new LingxingClient(loadConfig());
  let sbTotal = 0, svTotal = 0;

  // ① SB 广告级
  try {
    const rows = await fetchAll(client, "/basicOpen/multiplatform/ads/reportAdItemSbList", { campaignType: ["sba"], day: 14 }, adv);
    sbTotal = summarize("一、SB品牌广告 reportAdItemSbList campaignType=[sba] day=14", rows);
  } catch (e) { console.log(`一、SB广告级失败: ${errInfo(e)}`); }
  await sleep(1000);

  // ② SV 广告级
  try {
    const rows = await fetchAll(client, "/basicOpen/multiplatform/ads/reportAdItemSvList", { campaignType: ["video"], day: 14 }, adv);
    svTotal = summarize("二、SV视频广告 reportAdItemSvList campaignType=[video] day=14", rows);
  } catch (e) { console.log(`二、SV广告级失败: ${errInfo(e)}`); }
  await sleep(1000);

  // ③ Campaign级对照
  for (const [label, path, ct] of [
    ["三、SB活动级 reportCampaignSbList", "/basicOpen/multiplatform/ads/reportCampaignSbList", "sba"],
    ["四、SV活动级 reportCampaignSvList", "/basicOpen/multiplatform/ads/reportCampaignSvList", "video"],
  ] as const) {
    try {
      const rows = await fetchAll(client, path, { campaignType: [ct], day: 14, operationSourceType: "gateway" }, adv);
      summarize(`${label} campaignType=[${ct}] day=14 operationSourceType=gateway`, rows);
    } catch (e) { console.log(`${label}失败: ${errInfo(e)}`); }
    await sleep(1000);
  }

  // ⑤ day敏感性（对SV广告级，含SBV样本的那一路）
  console.log(`\n【五、day参数敏感性】（adSpend应不随归因天数变；attributedSales应随之变）`);
  for (const day of [3, 30]) {
    try {
      const rows = await fetchAll(client, "/basicOpen/multiplatform/ads/reportAdItemSvList", { campaignType: ["video"], day }, adv);
      const total = rows.reduce((a, r) => a + toNum(r.adSpend), 0);
      const sales = rows.reduce((a, r) => a + toNum(r.attributedSales), 0);
      console.log(`  day=${day}: 行数=${rows.length}  adSpend总=$${total.toFixed(2)}  attributedSales总=$${sales.toFixed(2)}`);
    } catch (e) { console.log(`  day=${day} 失败: ${errInfo(e)}`); }
    await sleep(800);
  }

  // 守恒
  console.log(`\n=== 守恒验证 ===`);
  console.log(`SP $${SP_KNOWN.toFixed(2)} + SB $${sbTotal.toFixed(2)} + SV $${svTotal.toFixed(2)} = $${(SP_KNOWN + sbTotal + svTotal).toFixed(2)}`);
  console.log(`对照发票总额 $${INVOICE_TOTAL.toFixed(2)}，覆盖率 ${(((SP_KNOWN + sbTotal + svTotal) / INVOICE_TOTAL) * 100).toFixed(1)}%（≈100%=广告守恒等式完全闭环）`);
  console.log("\n探针17结束。");
}

main().catch((err) => { console.error("探针17执行失败：", err); process.exit(1); });
