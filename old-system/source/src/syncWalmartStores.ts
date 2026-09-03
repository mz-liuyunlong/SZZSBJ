/**
 * syncWalmartStores.ts  —— 店铺自动发现（每日 cron）
 *
 * 1) 领星「店铺列表」 getSellerList(platform 10008) → 全部沃尔玛店铺 store_id/store_name/is_sync/status
 * 2) 领星「广告主列表」advertiser/list            → 全部广告主 advertiserId/advertiserName/status
 * 3) 领星「广告商品报表」reportAdItemSpList 里的 mpSellerName == store_name，
 *    据此把 advertiserId 精确连到 store_id（名字对不上的问题靠这条解决）
 * 4) upsert 进 dim_store_config：
 *    - 新店：领星"启用+授权正常"→ is_active=1，否则 0
 *    - 老店：更新 store_name/advertiser_id/last_seen_at；领星停用/授权失败→强制 is_active=0；
 *            否则不覆盖人工 is_active（COALESCE 保护已有 advertiser_id 不被 null 冲掉）
 *
 * 只写 dim_store_config，不动其它同步。用法：npx ts-node src/syncWalmartStores.ts
 */
import "dotenv/config";
import * as mysql from "mysql2/promise";
import { loadConfig } from "./config";
import { LingxingClient } from "./lingxingClient";

const SELLER_LIST_PATH = "/pb/mp/shop/v2/getSellerList";
const ADVERTISER_LIST_PATH = "/basicOpen/adReport/advertiser/list";
const AD_ITEM_PATH = "/basicOpen/multiplatform/ads/reportAdItemSpList";
const WALMART_PLATFORM = 10008;
const TIMEOUT_MS = 60000;

interface StoreRow { store_id: string; store_name: string; is_sync: number; status: number; }
interface AdvRow { advertiserId: string; advertiserName: string; status: number; }

const norm = (v: unknown): string => String(v ?? "").trim();

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

function ymd(offsetDays: number): string {
  const d = new Date();
  d.setDate(d.getDate() + offsetDays);
  return d.toISOString().slice(0, 10);
}

async function fetchStores(client: LingxingClient): Promise<StoreRow[]> {
  const out: StoreRow[] = [];
  for (let offset = 0; offset < 4000; offset += 200) {
    const resp = await client.request<unknown>({
      method: "POST", path: SELLER_LIST_PATH,
      params: { offset, length: 200, platform_code: [WALMART_PLATFORM] },
      timeoutMs: TIMEOUT_MS,
    });
    const list = dataList(resp);
    for (const s of list) {
      out.push({ store_id: norm(s.store_id), store_name: norm(s.store_name), is_sync: Number(s.is_sync), status: Number(s.status) });
    }
    if (list.length < 200) break;
  }
  return out;
}

async function fetchAdvertisers(client: LingxingClient): Promise<AdvRow[]> {
  const out: AdvRow[] = [];
  for (let page = 1; page <= 30; page++) {
    const resp = await client.request<unknown>({
      method: "POST", path: ADVERTISER_LIST_PATH,
      params: { paging: true, limit: 200, page },
      timeoutMs: TIMEOUT_MS,
    });
    const list = dataList(resp);
    for (const a of list) {
      out.push({ advertiserId: norm(a.advertiserId), advertiserName: norm(a.advertiserName), status: Number(a.status) });
    }
    if (list.length < 200) break;
  }
  return out;
}

/**
 * 用广告报表的 mpSellerName 把 advertiserId 连到 store_name。
 * 对每个广告主拉近 30 天一页广告数据，取首条 mpSellerName。取不到就跳过（保留种子/已有值）。
 */
async function deriveStoreNameByAdvertiser(client: LingxingClient, ads: AdvRow[]): Promise<Map<string, string>> {
  const advToStoreName = new Map<string, string>();
  const startDate = ymd(-30);
  const endDate = ymd(0);
  for (const a of ads) {
    if (!a.advertiserId) continue;
    try {
      const resp = await client.request<unknown>({
        method: "POST", path: AD_ITEM_PATH,
        params: {
          advertiserIds: [a.advertiserId],
          campaignType: ["sponsoredProducts-manual", "sponsoredProducts-auto"],
          startDate, endDate, pageNum: 1, pageSize: 5, paging: true,
        },
        timeoutMs: TIMEOUT_MS,
      });
      const list = dataList(resp);
      const sellerName = list.map((r) => norm(r.mpSellerName)).find(Boolean);
      if (sellerName) advToStoreName.set(a.advertiserId, sellerName);
    } catch (e) {
      console.warn(`  广告主 ${a.advertiserId} 取 mpSellerName 失败（忽略）：${e instanceof Error ? e.message : String(e)}`);
    }
  }
  return advToStoreName;
}

async function main(): Promise<void> {
  const client = new LingxingClient(loadConfig());

  console.log("① 拉店铺列表 getSellerList ...");
  const stores = await fetchStores(client);
  console.log(`   店铺数: ${stores.length}`);

  console.log("② 拉广告主列表 advertiser/list ...");
  const ads = await fetchAdvertisers(client);
  console.log(`   广告主数: ${ads.length}`);

  console.log("③ 用广告报表 mpSellerName 自动连 advertiserId ↔ store_name ...");
  const advToStoreName = await deriveStoreNameByAdvertiser(client, ads);
  // storeName → {advertiserId, advertiserName}
  const nameToAdv = new Map<string, { id: string; name: string }>();
  for (const a of ads) {
    const sn = advToStoreName.get(a.advertiserId);
    if (sn) nameToAdv.set(sn, { id: a.advertiserId, name: a.advertiserName });
  }
  console.log(`   成功连上 ${nameToAdv.size} 个店↔广告主`);

  console.log("④ upsert dim_store_config ...");
  const db = await getDb();
  let ins = 0, upd = 0;
  try {
    for (const s of stores) {
      if (!s.store_id) continue;
      const lingActive = s.is_sync === 1 && s.status === 1 ? 1 : 0;
      const authStatus = s.status === 1 ? "normal" : "expired";
      const adv = nameToAdv.get(s.store_name);
      const [res] = await db.query<mysql.ResultSetHeader>(
        `INSERT INTO dim_store_config
           (platform, store_id, store_name, advertiser_id, advertiser_name, is_active, auth_status, first_seen_at, last_seen_at)
         VALUES ('walmart', ?, ?, ?, ?, ?, ?, NOW(), NOW())
         ON DUPLICATE KEY UPDATE
           store_name      = VALUES(store_name),
           advertiser_id   = COALESCE(VALUES(advertiser_id), advertiser_id),
           advertiser_name = COALESCE(VALUES(advertiser_name), advertiser_name),
           auth_status     = VALUES(auth_status),
           is_active       = IF(? = 1, is_active, 0),
           last_seen_at    = NOW()`,
        [s.store_id, s.store_name, adv?.id ?? null, adv?.name ?? null, lingActive, authStatus, lingActive],
      );
      // affectedRows: 1=insert, 2=update(值有变), 0=update(无变化)
      if (res.affectedRows === 1) ins++; else upd++;
      const advTxt = adv ? adv.id : "(无/保留原值)";
      console.log(`   ${s.store_name} | store_id=${s.store_id} | advertiser=${advTxt} | 领星active=${lingActive} | auth=${authStatus}`);
    }
    console.log(`\n完成：新增 ${ins}，更新 ${upd}，共处理 ${stores.length} 店。`);
    console.log("提示：is_active 只在领星停用/授权失败时被强制置 0；人工设过的 is_active 不会被覆盖。");
  } finally {
    await db.end();
  }
}

main().catch((e) => { console.error("syncWalmartStores 失败:", e); process.exit(1); });
