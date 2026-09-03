/**
 * syncSbSvAdsDaily.ts
 *
 * AI财务/广告系统 · SB品牌广告 + SV视频广告 每日商品级同步（一期第二条正式脚本）。
 *
 * 设计依据（需求方R1拍板 + 探针16/17/17b定型）：
 *   - 写入现有 fact_ads_product_daily（与SP手动/自动同表同展示；唯一键
 *     uq_fact_ads_product(stat_date,platform,advertiser_id,campaign_id,ad_group_id,item_id) 天然兼容，
 *     campaign_type 列存API原生 'sba'/'video' 实现分类；零改动现有表结构与现有同步脚本）。
 *   - 接口与参数（探针17b实锤）：
 *       SB: /basicOpen/multiplatform/ads/reportAdItemSbList  campaignType=["sba"]
 *       SV: /basicOpen/multiplatform/ads/reportAdItemSvList  campaignType=["video"]
 *       day=14（花费不随归因天数变，销售归因取14天与搜索词SOP一致）；
 *       paging 必须为布尔 true（文档示例字符串"1"经网关必400——教训）；窗口≤31天，按天调用。
 *   - 行处理与 syncLingxingDailyToDb 的 upsertFactAds 保持同口径：按天(startDate=endDate)拉取、
 *     无itemId行跳过、指标字段原样存（ctr等与现表既有口径一致）、RAW留痕。
 *
 * 写入范围（严格限定）：fact_ads_product_daily（INSERT..ON DUPLICATE，仅新增sba/video行）
 *   + raw_lingxing_api / sync_task_log（INSERT留痕）。不触碰SP行、不改任何现有文件/定时任务；
 *   本脚本不挂cron（挂cron需需求方单独批准）。
 *
 * 用法：
 *   npx ts-node src/syncSbSvAdsDaily.ts                      # 默认前天(T-2,与SP同步口径一致)
 *   npx ts-node src/syncSbSvAdsDaily.ts --date=2026-07-15
 *   npx ts-node src/syncSbSvAdsDaily.ts --startDate=2026-07-01 --endDate=2026-08-10   # 回填
 *   npx ts-node src/syncSbSvAdsDaily.ts --store=110687423514268160 --startDate=... --endDate=...
 */

import "dotenv/config";
import * as crypto from "crypto";
import * as mysql from "mysql2/promise";
import { loadConfig } from "./config";
import { LingxingClient } from "./lingxingClient";

const PATHS: Array<{ label: string; path: string; ct: string }> = [
  { label: "SB", path: "/basicOpen/multiplatform/ads/reportAdItemSbList", ct: "sba" },
  { label: "SV", path: "/basicOpen/multiplatform/ads/reportAdItemSvList", ct: "video" },
];
const TASK_NAME = "sbsv_ads_daily_sync";
const PAGE_SIZE = 200;
const MAX_PAGES = 25;
const ATTR_DAY = 14;
const DELAY_PAGE_MS = 400;
const DELAY_TYPE_MS = 800;
const DELAY_DAY_MS = 800;
const DELAY_STORE_MS = 2000;
const RETRY_MAX = 3;

function getArg(name: string, def = ""): string {
  const p = `--${name}=`;
  const a = process.argv.find((x) => x.startsWith(p));
  return a ? a.slice(p.length) : def;
}
function chinaDate(offsetDays = 0): string {
  const d = new Date();
  d.setUTCHours(d.getUTCHours() + 8);
  d.setUTCDate(d.getUTCDate() + offsetDays);
  return d.toISOString().slice(0, 10);
}
function addDays(dateStr: string, n: number): string {
  const d = new Date(dateStr + "T00:00:00Z");
  d.setUTCDate(d.getUTCDate() + n);
  return d.toISOString().slice(0, 10);
}
function toNum(v: unknown): number {
  if (typeof v === "number") return Number.isFinite(v) ? v : 0;
  const n = Number(String(v ?? "").replace(/,/g, "").replace("%", ""));
  return Number.isFinite(n) ? n : 0;
}
function toNumOrNull(v: unknown): number | null { return v == null || v === "" ? null : toNum(v); }
function toStr(v: unknown): string { return String(v ?? "").trim(); }
function sleep(ms: number): Promise<void> { return new Promise((r) => setTimeout(r, ms)); }
function extractList(data: unknown): Array<Record<string, unknown>> {
  if (Array.isArray(data)) return data as Array<Record<string, unknown>>;
  const d = data as { list?: unknown; data?: unknown } | null;
  if (Array.isArray(d?.list)) return d!.list as Array<Record<string, unknown>>;
  if (Array.isArray(d?.data)) return d!.data as Array<Record<string, unknown>>;
  return [];
}

async function saveRawPage(
  db: mysql.Connection, path: string, params: Record<string, unknown>, response: unknown, dataDate: string,
): Promise<void> {
  const rawJson = JSON.stringify(response);
  const rawHash = crypto.createHash("md5").update(rawJson).digest("hex").slice(0, 64);
  await db.query(
    `INSERT IGNORE INTO raw_lingxing_api
       (api_path, request_method, request_params_json, response_json, response_code, is_success, data_date, raw_hash)
     VALUES (?, 'POST', ?, ?, '0', 1, ?, ?)`,
    [path, JSON.stringify(params), rawJson, dataDate, rawHash],
  );
}

async function syncStoreDay(
  client: LingxingClient, db: mysql.Connection,
  store: { store_id: string; store_name: string; advertiser_id: string }, day: string,
): Promise<{ upserted: number; spendByType: Record<string, number> }> {
  let upserted = 0;
  const spendByType: Record<string, number> = {};
  for (const t of PATHS) {
    const rows: Array<Record<string, unknown>> = [];
    for (let pageNum = 1; pageNum <= MAX_PAGES; pageNum++) {
      const params = {
        advertiserIds: [store.advertiser_id],
        campaignType: [t.ct],
        day: ATTR_DAY,
        startDate: day,
        endDate: day,
        pageNum,
        pageSize: PAGE_SIZE,
        paging: true, // 必须布尔true（探针17/17b教训）
      };
      let resp: unknown = null;
      let lastErr: unknown = null;
      for (let attempt = 0; attempt < RETRY_MAX; attempt++) {
        try {
          resp = await client.request<unknown>({ method: "POST", path: t.path, params, timeoutMs: 60000 });
          lastErr = null;
          break;
        } catch (e) { lastErr = e; await sleep(2000 * (attempt + 1)); }
      }
      if (lastErr) throw lastErr;
      const data = (resp as { data?: unknown }).data;
      await saveRawPage(db, t.path, params, data, day);
      const list = extractList(data);
      if (list.length === 0) break;
      rows.push(...list);
      if (list.length < PAGE_SIZE) break;
      await sleep(DELAY_PAGE_MS);
    }

    let typeSpend = 0;
    for (const r of rows) {
      const itemId = toStr(r.itemId ?? r.adItemId);
      if (!itemId) continue; // 与SP同步同口径：无itemId不落
      const spend = toNum(r.adSpend);
      typeSpend += spend;
      await db.query(
        `INSERT INTO fact_ads_product_daily
           (stat_date, platform, store_id, store_name, advertiser_id,
            campaign_id, campaign_name, campaign_type, ad_group_id, ad_group_name,
            item_id, msku, impressions, clicks, ctr, ad_spend,
            orders, total_sales, acos, cpc, cvr, roas, source_system)
         VALUES (?, 'walmart', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'lingxing')
         ON DUPLICATE KEY UPDATE
           campaign_name=VALUES(campaign_name), campaign_type=VALUES(campaign_type),
           ad_group_name=VALUES(ad_group_name), msku=VALUES(msku),
           impressions=VALUES(impressions), clicks=VALUES(clicks), ctr=VALUES(ctr),
           ad_spend=VALUES(ad_spend), orders=VALUES(orders), total_sales=VALUES(total_sales),
           acos=VALUES(acos), cpc=VALUES(cpc), cvr=VALUES(cvr), roas=VALUES(roas)`,
        [day, store.store_id, toStr(r.mpSellerName) || store.store_name, toStr(r.advertiserId) || store.advertiser_id,
         toStr(r.campaignId), toStr(r.campaignName), toStr(r.campaignType) || t.ct,
         toStr(r.adGroupId), toStr(r.adGroupName),
         itemId, toStr(r.msku ?? ""),
         toNum(r.numAdsShown), toNum(r.numAdsClicks), toNumOrNull(r.ctr), spend,
         toNum(r.attributedOrders), toNum(r.attributedSales),
         toNumOrNull(r.acos), toNumOrNull(r.cpc), toNumOrNull(r.cvr), toNumOrNull(r.roas)],
      );
      upserted++;
    }
    spendByType[t.ct] = (spendByType[t.ct] ?? 0) + typeSpend;
    await sleep(DELAY_TYPE_MS);
  }
  return { upserted, spendByType };
}

async function main() {
  const storeFilter = getArg("store");
  const dateArg = getArg("date");
  const startDate = getArg("startDate") || dateArg || chinaDate(-2);
  const endDate = getArg("endDate") || dateArg || chinaDate(-2);

  console.log("═".repeat(60));
  console.log(`  SB/SV广告商品级同步  ${startDate} → ${endDate}${storeFilter ? `  store=${storeFilter}` : "  (全店铺)"}`);
  console.log("═".repeat(60));

  const db = await mysql.createConnection({
    host: process.env.DB_HOST ?? "127.0.0.1", port: Number(process.env.DB_PORT ?? 3306),
    user: process.env.DB_USER ?? "", password: process.env.DB_PASSWORD ?? "",
    database: process.env.DB_NAME ?? "walmart_ai_data",
  });
  const client = new LingxingClient(loadConfig());

  const [storeRows] = await db.execute(
    `SELECT store_id, store_name, advertiser_id FROM dim_store_config
      WHERE platform='walmart' AND COALESCE(advertiser_id,'')<>''${storeFilter ? " AND store_id=?" : ""}`,
    storeFilter ? [storeFilter] : [],
  );
  const stores = storeRows as Array<{ store_id: string; store_name: string; advertiser_id: string }>;
  console.log(`店铺数: ${stores.length}\n`);

  let totalUpserted = 0, errors = 0;
  const grand: Record<string, number> = {};

  for (const store of stores) {
    console.log(`──── ${store.store_name} (${store.store_id}) ────`);
    for (let d = startDate; d <= endDate; d = addDays(d, 1)) {
      try {
        const { upserted, spendByType } = await syncStoreDay(client, db, store, d);
        totalUpserted += upserted;
        for (const [k, v] of Object.entries(spendByType)) grand[k] = (grand[k] ?? 0) + v;
        const parts = Object.entries(spendByType).map(([k, v]) => `${k}=$${v.toFixed(2)}`).join(" ");
        if (upserted > 0) console.log(`  ${d}: upsert=${upserted}  ${parts}`);
      } catch (e) {
        errors++;
        console.log(`  ⚠️ ${d} 失败(跳过继续): ${e instanceof Error ? e.message : String(e)}`);
      }
      await sleep(DELAY_DAY_MS);
    }
    await sleep(DELAY_STORE_MS);
  }

  await db.query(
    `INSERT INTO sync_task_log
       (task_name, source_system, target_table, status, inserted_count, updated_count, failed_count, finished_at, error_message)
     VALUES (?, 'lingxing_api', 'fact_ads_product_daily', ?, ?, 0, ?, NOW(), ?)`,
    [TASK_NAME, errors > 0 ? "failed" : "success", totalUpserted, errors, errors > 0 ? `${errors}个店铺天失败` : null],
  );
  await db.end();
  const grandParts = Object.entries(grand).map(([k, v]) => `${k}=$${v.toFixed(2)}`).join("  ");
  console.log(`\n完成：upsert=${totalUpserted}  花费合计 ${grandParts || "(无)"}  错误=${errors}`);
}

main().catch((err) => { console.error("同步失败：", err); process.exit(1); });
