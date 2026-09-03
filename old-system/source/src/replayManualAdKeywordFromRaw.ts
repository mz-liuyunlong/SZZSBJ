/**
 * replayManualAdKeywordFromRaw.ts — 手动广告关键词历史重放（2026-07-15）
 *
 * 背景：fact_ads_keyword_daily 旧唯一键不含 campaign/ad_group，同关键词跨 campaign 互相
 * 覆盖（TASK_CHANGE_LOG 2026-07-15 广告数据排查）。唯一键修复（ALTER）后，用本表 RAW 留存
 * （raw_lingxing_api）重放历史，正确值覆盖脏行、原被覆盖行各归各位。**不调用领星 API**。
 *
 * 用法：
 *   npx ts-node src/replayManualAdKeywordFromRaw.ts --start=2026-05-01 --end=2026-07-12          # dry-run
 *   npx ts-node src/replayManualAdKeywordFromRaw.ts --start=2026-07-10 --end=2026-07-10 --execute
 *
 * 前置：必须在新唯一键（含 campaign_id/ad_group_id）生效后执行，否则重放会重现覆盖。
 * 映射逻辑与 syncManualAdKeywordDaily.ts 逐字段一致（numAdsShown/numAdsClicks/adSpend/
 * attributedOrders/attributedSales/keywordBid/keywordId）。
 * store 归属：RAW 行无店铺信息，按页面请求参数 advertiserIds[0] → fact 表既有
 * advertiser_id→store_id/store_name 映射还原（只读自举，无需配置）。
 */

import "dotenv/config";
import * as mysql from "mysql2/promise";

const ITEM_PATH = "/basicOpen/multiplatform/ads/reportAdItemSpList";
const KEYWORD_PATH = "/basicOpen/multiplatform/ads/reportKeywordSpList";
const BATCH = 500;

type Row = Record<string, unknown>;

function getArg(name: string, def = ""): string {
  const p = process.argv.find((a) => a.startsWith(`--${name}=`));
  return p ? p.slice(name.length + 3) : def;
}

function toNum(v: unknown): number {
  const n = Number(v);
  return Number.isFinite(n) ? n : 0;
}

function toStr(v: unknown): string {
  return v === null || v === undefined ? "" : String(v).trim();
}

function extractArray(data: unknown): Row[] {
  if (!data || typeof data !== "object") return [];
  const d = data as Record<string, unknown>;
  for (const k of ["rows", "list", "records", "data"]) {
    const v = d[k];
    if (Array.isArray(v)) return v as Row[];
    if (v && typeof v === "object") {
      const inner = (v as Record<string, unknown>);
      for (const k2 of ["rows", "list", "records"]) {
        if (Array.isArray(inner[k2])) return inner[k2] as Row[];
      }
    }
  }
  return [];
}

function getDb(): Promise<mysql.Connection> {
  return mysql.createConnection({
    host:     process.env.DB_HOST     ?? "127.0.0.1",
    port:     Number(process.env.DB_PORT ?? 3306),
    user:     process.env.DB_USER     ?? "",
    password: process.env.DB_PASSWORD ?? "",
    database: process.env.DB_NAME     ?? "walmart_ai_data",
  });
}

interface RawPage { id: number; api_path: string; params: Record<string, unknown>; rows: Row[]; }

/** JSON 列类型自适应：mysql2 对 JSON 型列自动返回对象，LONGTEXT 返回字符串（v4 修复静默吞页问题） */
function jsonVal(v: unknown): unknown {
  if (v === null || v === undefined) return null;
  if (typeof v === "object") return v;
  try { return JSON.parse(String(v)); } catch { return null; }
}

async function loadPages(db: mysql.Connection, apiPath: string, dataDate: string): Promise<RawPage[]> {
  // 两步取数：先轻量取 id（避免带大JSON列的 ORDER BY 触发 Out of sort memory），
  // 再按 id 分批取大字段，JS 侧按 id 保序。
  // DATE() 兜底：兼容 data_date 为 datetime 型（等值比较只命中零点的问题）
  const [idRows] = await db.query<mysql.RowDataPacket[]>(
    `SELECT id FROM raw_lingxing_api WHERE api_path = ? AND DATE(data_date) = ? ORDER BY id`,
    [apiPath, dataDate],
  );
  const ids = idRows.map((r) => Number(r.id));
  const pages: RawPage[] = [];
  const FETCH_BATCH = 10;
  let parseFailures = 0;
  for (let i = 0; i < ids.length; i += FETCH_BATCH) {
    const chunk = ids.slice(i, i + FETCH_BATCH);
    const [rows] = await db.query<mysql.RowDataPacket[]>(
      `SELECT id, api_path, request_params_json, response_json FROM raw_lingxing_api
       WHERE id IN (?)`,
      [chunk],
    );
    for (const r of rows) {
      const params = jsonVal(r.request_params_json);
      const resp = jsonVal(r.response_json);
      if (!params || !resp) {
        parseFailures++;
        continue;
      }
      pages.push({
        id: Number(r.id), api_path: String(r.api_path),
        params: params as Record<string, unknown>, rows: extractArray(resp),
      });
    }
  }
  pages.sort((a, b) => a.id - b.id);
  if (parseFailures > 0) console.log(`  ⚠️ ${apiPath} @ ${dataDate}: ${parseFailures} 页JSON解析失败被跳过`);
  return pages;
}

function pageAdvertiser(p: RawPage): string {
  const ids = p.params.advertiserIds;
  if (Array.isArray(ids) && ids.length > 0) return toStr(ids[0]);
  return "";
}

async function main(): Promise<void> {
  const start = getArg("start");
  const end = getArg("end", start);
  const execute = process.argv.includes("--execute");
  if (!/^\d{4}-\d{2}-\d{2}$/.test(start) || !/^\d{4}-\d{2}-\d{2}$/.test(end) || start > end) {
    console.error("用法: --start=YYYY-MM-DD [--end=YYYY-MM-DD] [--execute]（默认dry-run）");
    process.exit(1);
  }
  const db = await getDb();
  try {
    // advertiser → store 映射（从 fact 既有 manual_kw 行自举）
    const [mapRows] = await db.query<mysql.RowDataPacket[]>(
      `SELECT advertiser_id, MAX(store_id) store_id, MAX(store_name) store_name
       FROM fact_ads_keyword_daily
       WHERE source_type='manual_kw' AND COALESCE(advertiser_id,'') <> ''
       GROUP BY advertiser_id`,
    );
    const storeMap = new Map<string, { store_id: string; store_name: string }>();
    for (const r of mapRows) {
      storeMap.set(String(r.advertiser_id), { store_id: String(r.store_id), store_name: String(r.store_name ?? "") });
    }
    console.log(`advertiser→store 映射: ${storeMap.size} 个`);

    // 本地无关的纯字符串日期步进（修复：toISOString 在 +0800 时区把起始日拨回一天）
    const fmtDay = (d: Date) =>
      `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
    const days: string[] = [];
    for (let d = new Date(`${start}T12:00:00`); ; d.setDate(d.getDate() + 1)) {
      const s = fmtDay(d);
      if (s > end) break;
      days.push(s);
    }

    let grandRows = 0, grandAffected = 0, missingStore = 0, missingItem = 0;
    let zeroSkipped = 0; // v5：全零行跳过计数
    for (const day of days) {
      const itemPages = await loadPages(db, ITEM_PATH, day);
      const kwPages = await loadPages(db, KEYWORD_PATH, day);
      if (kwPages.length === 0) {
        // 诊断：该 api_path 在库中的实际覆盖，便于定位是日期问题还是路径问题
        const [diag] = await db.query<mysql.RowDataPacket[]>(
          `SELECT COUNT(*) AS n, MIN(DATE(data_date)) AS mn, MAX(DATE(data_date)) AS mx
           FROM raw_lingxing_api WHERE api_path = ?`,
          [KEYWORD_PATH],
        );
        console.log(`${day} 无RAW关键词页，跳过（诊断：api_path总页数=${diag[0]?.n} 覆盖=${diag[0]?.mn}~${diag[0]?.mx}）`);
        continue;
      }
      // campaign+adGroup → item 映射（与同步脚本一致：首见优先）
      const itemMap = new Map<string, { item_id: string; msku: string }>();
      for (const p of itemPages) {
        for (const r of p.rows) {
          const cid = toStr(r.campaignId), gid = toStr(r.adGroupId);
          const itemId = toStr(r.itemId ?? r.platformProductId ?? r.productId);
          const msku = toStr(r.msku ?? r.sku ?? "");
          if (cid && itemId) {
            const k = `${cid}|${gid}`;
            if (!itemMap.has(k)) itemMap.set(k, { item_id: itemId, msku });
          }
        }
      }
      // 关键词行组装
      const out: unknown[][] = [];
      for (const p of kwPages) {
        const advFromPage = pageAdvertiser(p);
        for (const r of p.rows) {
          const keyword = toStr(r.keywordName ?? r.keyword ?? r.targetingText ?? "");
          if (!keyword) continue;
          // v5：全零行不入FACT（与同步v2一致；暂停实体持续零回传=无效数据）
          if (toNum(r.numAdsShown) === 0 && toNum(r.numAdsClicks) === 0
              && toNum(r.adSpend) === 0 && toNum(r.attributedOrders) === 0
              && toNum(r.attributedSales) === 0) { zeroSkipped++; continue; }
          const cid = toStr(r.campaignId), gid = toStr(r.adGroupId);
          const info = itemMap.get(`${cid}|${gid}`) ?? { item_id: "", msku: "" };
          const adv = toStr(r.advertiserId) || advFromPage;
          const st = storeMap.get(adv);
          if (!st) { missingStore++; continue; }
          if (!info.item_id) missingItem++;
          out.push([
            day, "walmart", st.store_id, toStr(r.mpSellerName) || st.store_name, adv,
            cid, toStr(r.campaignName), toStr(r.campaignType ?? "sponsoredProducts"), gid, toStr(r.adGroupName),
            info.item_id, info.msku, keyword, keyword.toLowerCase().trim(),
            toStr(r.matchType ?? "broad"), toStr(r.targetingType ?? "manual"),
            toNum(r.numAdsShown), toNum(r.numAdsClicks), toNum(r.ctr) / 100, toNum(r.adSpend),
            toNum(r.attributedOrders), toNum(r.cvr) / 100, toNum(r.attributedSales), toNum(r.acos) / 100,
            toNum(r.cpc), toNum(r.cvr) / 100, toNum(r.roas),
            r.keywordBid != null ? toNum(r.keywordBid) : null,
            "manual_kw", "lingxing_raw_replay",
            JSON.stringify({ keywordId: toStr(r.keywordId ?? r.key), replay_raw_id: p.id }),
          ]);
        }
      }
      grandRows += out.length;
      if (!execute) {
        console.log(`${day} [dry-run] RAW关键词页=${kwPages.length} 可重放行=${out.length}`);
        continue;
      }
      let affected = 0;
      for (let i = 0; i < out.length; i += BATCH) {
        const chunk = out.slice(i, i + BATCH);
        const [res] = await db.query<mysql.ResultSetHeader>(
          `INSERT INTO fact_ads_keyword_daily
             (stat_date, platform, store_id, store_name, advertiser_id,
              campaign_id, campaign_name, campaign_type, ad_group_id, ad_group_name,
              item_id, msku, keyword, normalized_keyword, match_type, keyword_type,
              impressions, clicks, ctr, ad_spend, orders, conversion_rate,
              total_sales, acos, cpc, cvr, roas, keyword_bid, source_type, source_system, extra_json)
           VALUES ?
           ON DUPLICATE KEY UPDATE
             impressions = VALUES(impressions), clicks = VALUES(clicks), ctr = VALUES(ctr),
             ad_spend = VALUES(ad_spend), orders = VALUES(orders),
             conversion_rate = VALUES(conversion_rate), total_sales = VALUES(total_sales),
             acos = VALUES(acos), cpc = VALUES(cpc), cvr = VALUES(cvr), roas = VALUES(roas),
             keyword_bid = VALUES(keyword_bid), extra_json = VALUES(extra_json),
             source_system = VALUES(source_system)`,
          [chunk],
        );
        affected += res.affectedRows;
      }
      grandAffected += affected;
      console.log(`${day} 重放行=${out.length} affectedRows=${affected}`);
    }
    console.log("SUMMARY_JSON=" + JSON.stringify({
      start, end, execute, totalRows: grandRows, totalAffected: grandAffected,
      missingStoreRows: missingStore, missingItemRows: missingItem, zeroSkipped,
      status: "success",
    }));
  } finally {
    await db.end().catch(() => undefined);
  }
}

main().catch((e) => {
  console.error("FATAL:", e instanceof Error ? e.message : String(e));
  process.exit(1);
});
