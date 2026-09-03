import "dotenv/config";
import * as crypto from "crypto";
import * as mysql from "mysql2/promise";
import { loadConfig } from "./config";
import { LingxingClient, getResponseMessage } from "./lingxingClient";

// ============================================================================
// syncMpOrdersChannelDaily.ts — 领星订单接口 → WFS/非WFS 销量渠道分拆（2026-07-23）
// 链路：/pb/mp/order/v2/list（按订购日逐日拉取，原始响应入 raw_lingxing_api 留存）
//       → 按 (订购日, store_id, msku) 聚合 → UPSERT fact_mp_sales_channel_daily。
// 口径：delivery_type 3=平台发货(WFS) / 2=自发货 / 1=混合中转；排除 status=7 取消单、
//       is_delete=1 删除单；item_id 经 dim_product(platform,store_id,msku) 反查
//       （订单接口 product_no 实测为空串，msku 为可靠关联键——2026-07-23 探测实证）。
// 幂等：默认滚动窗口 T-7 ~ T-1 每日重拉，UPSERT 覆盖 + 当日消失键归零（取消单回收）。
// 用法：npx ts-node src/syncMpOrdersChannelDaily.ts [--start=YYYY-MM-DD] [--end=YYYY-MM-DD] [--execute]
//       默认 dry-run（不写 RAW 不写 FACT，只打印统计）；--execute 才落库。
// 本脚本为独立新增文件，不改动任何既有同步链路与定时任务。
// 2026-07-24 扩展（附件3同接口）：每日额外拉取亚马逊(10001)/希音(10021/27/28)/TEMU(10022/24)/
//   TikTok(10011)订单，按 product_no(平台商品ID) 聚合销量 → fact_channel_clearance_sales_daily
//   （供清货中心其他渠道行"本月已清/7日日销"读取；台账按 platform_ref=ASIN/SKC 匹配）。
//   沃尔玛WFS聚合路径与既有UPSERT/表完全不动；渠道路径独立 try/catch，失败只记日志不影响WFS主链路。
// ============================================================================

const API_PATH = "/pb/mp/order/v2/list";
const WALMART_PLATFORM_CODE = 10008;
// 2026-07-24 清货已清渠道（附件3同接口，扩 platform_code）：亚马逊/希音按本地SKU销量
// → fact_channel_clearance_sales_daily（独立事实表，不改动WFS主链路/沃尔玛聚合）。
// 2026-07-24：按 product_no(平台商品ID：亚马逊=ASIN/希音=SKC/TEMU/TikTok=平台商品ID) 聚合。
const CLEARANCE_CHANNELS: Array<{ platform: string; codes: number[] }> = [
  { platform: "amazon", codes: [10001] },
  { platform: "shein", codes: [10021, 10027, 10028] },
  { platform: "temu", codes: [10022, 10024] },
  { platform: "tiktok", codes: [10011] },
];
const PAGE_SIZE = 500;
const PAGE_SLEEP_MS = 1000;
const REQUEST_TIMEOUT_MS = 180000;

interface MpOrderItem {
  msku?: string;
  local_sku?: string; // 参考：本地SKU(=公司SKU)
  product_no?: string; // 2026-07-24 清货已清聚合键：平台商品ID（亚马逊ASIN/希音SKC/TEMU/TikTok商品ID）
  quantity?: number | string;
  is_delete?: number | string;
}

interface MpOrder {
  store_id?: string | number;
  store_name?: string;
  delivery_type?: number | string;
  status?: number | string;
  is_delete?: number | string;
  item_info?: MpOrderItem[];
}

interface OrderListData {
  total?: number | string;
  list?: MpOrder[];
}

interface ChannelAgg {
  storeId: string;
  storeName: string;
  msku: string;
  wfsQty: number;
  nonWfsQty: number;
  mixedQty: number;
  wfsOrders: number;
  nonWfsOrders: number;
}

interface DaySummary {
  day: string;
  pages: number;
  orders: number;
  cancelled: number;
  deleted: number;
  aggRows: number;
  zeroedRows: number;
  unmatchedMsku: number;
  ambiguousMsku: number;
  rawId: number;
  error?: string;
}

function md5(input: string): string {
  return crypto.createHash("md5").update(input).digest("hex");
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

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

/** 北京时间今天 YYYY-MM-DD */
function bjTodayStr(): string {
  return new Date(Date.now() + 8 * 3600 * 1000).toISOString().slice(0, 10);
}

function addDays(dateStr: string, n: number): string {
  const d = new Date(`${dateStr}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() + n);
  return d.toISOString().slice(0, 10);
}

/** 北京时间 dateStr 00:00:00 的秒级时间戳 */
function bjEpochSec(dateStr: string): number {
  return Math.floor(Date.parse(`${dateStr}T00:00:00+08:00`) / 1000);
}

function isValidDate(s: string): boolean {
  return /^\d{4}-\d{2}-\d{2}$/.test(s) && !Number.isNaN(Date.parse(`${s}T00:00:00Z`));
}

// ── RAW 层写入（与 syncLingxingDailyToDb.ts 同款模式：INSERT IGNORE + raw_hash 去重）──
async function insertRaw(
  db: mysql.Connection,
  dataDate: string,
  page: number,
  requestParams: unknown,
  responseBody: unknown,
  purpose: string = "wfs_channel_sales",
): Promise<number> {
  const bodyStr = JSON.stringify(responseBody);
  const hash = md5(`${API_PATH}|${dataDate}|p${page}|${bodyStr}`);
  const extraJson = JSON.stringify({ page, purpose });
  try {
    const [result] = await db.query<mysql.ResultSetHeader>(
      `INSERT IGNORE INTO raw_lingxing_api
         (source_system, api_path, request_method, request_params_json, data_date,
          response_json, is_success, raw_hash, extra_json, pulled_at)
       VALUES ('lingxing', ?, 'POST', ?, ?, ?, 1, ?, ?, NOW())`,
      [API_PATH, JSON.stringify(requestParams), dataDate, bodyStr, hash, extraJson],
    );
    return result.insertId || 0;
  } catch (e) {
    console.warn(`  ⚠️  insertRaw 写入失败 (${dataDate} p${page}): ${e instanceof Error ? e.message : String(e)}`);
    return 0;
  }
}

// ── 拉取某一订购日的全部订单（分页；单页失败重试1次）─────────────────────────
async function fetchDayPages(
  client: LingxingClient,
  day: string,
  platformCodes: number[] = [WALMART_PLATFORM_CODE],
): Promise<{ orders: MpOrder[]; pages: Array<{ page: number; params: unknown; body: unknown }> }> {
  const startTime = bjEpochSec(day) - 1; // 双开区间：覆盖 day 00:00:00 起
  const endTime = bjEpochSec(addDays(day, 1)); // 双开区间：覆盖至 day 23:59:59
  const orders: MpOrder[] = [];
  const pages: Array<{ page: number; params: unknown; body: unknown }> = [];
  let offset = 0;
  let pageNo = 0;
  for (;;) {
    const params = {
      offset,
      length: PAGE_SIZE,
      date_type: "global_purchase_time",
      start_time: startTime,
      end_time: endTime,
      platform_code: platformCodes,
    };
    let resp: { code?: string | number; data?: OrderListData } | null = null;
    let lastErr = "";
    for (let attempt = 1; attempt <= 2; attempt++) {
      try {
        resp = await client.request<OrderListData>({
          method: "POST",
          path: API_PATH,
          params,
          timeoutMs: REQUEST_TIMEOUT_MS,
        });
        if (Number(resp.code ?? -1) === 0) break;
        lastErr = `code=${String(resp.code)} msg=${getResponseMessage(resp)}`;
        resp = null;
      } catch (e) {
        lastErr = e instanceof Error ? e.message : String(e);
        resp = null;
      }
      if (attempt < 2) await sleep(2000);
    }
    if (!resp) throw new Error(`第${pageNo + 1}页拉取失败（已重试1次）: ${lastErr}`);
    pageNo += 1;
    const list = Array.isArray(resp.data?.list) ? (resp.data?.list as MpOrder[]) : [];
    pages.push({ page: pageNo, params, body: resp });
    orders.push(...list);
    const total = Number(resp.data?.total ?? 0);
    console.log(`  ${day} 第${pageNo}页 offset=${offset} 本页=${list.length} 累计=${orders.length}/${total}`);
    if (list.length < PAGE_SIZE || orders.length >= total) break;
    offset += PAGE_SIZE;
    await sleep(PAGE_SLEEP_MS);
  }
  return { orders, pages };
}

// ── 聚合一天订单 → (store_id|msku) 渠道分拆 ────────────────────────────────
function aggregateOrders(orders: MpOrder[]): {
  agg: Map<string, ChannelAgg>;
  cancelled: number;
  deleted: number;
} {
  const agg = new Map<string, ChannelAgg>();
  let cancelled = 0;
  let deleted = 0;
  for (const order of orders) {
    if (Number(order.is_delete ?? 0) === 1) {
      deleted += 1;
      continue;
    }
    if (Number(order.status ?? 0) === 7) {
      cancelled += 1;
      continue;
    }
    const storeId = String(order.store_id ?? "").trim();
    const storeName = String(order.store_name ?? "").trim();
    const deliveryType = Number(order.delivery_type ?? 0);
    if (!storeId) continue;
    const items = Array.isArray(order.item_info) ? order.item_info : [];
    const orderMskus = new Set<string>();
    for (const item of items) {
      if (Number(item.is_delete ?? 0) === 1) continue;
      const msku = String(item.msku ?? "").trim();
      const qty = Number(item.quantity ?? 0);
      if (!msku || !Number.isFinite(qty) || qty <= 0) continue;
      const key = `${storeId}|${msku}`;
      if (!agg.has(key)) {
        agg.set(key, {
          storeId, storeName, msku,
          wfsQty: 0, nonWfsQty: 0, mixedQty: 0, wfsOrders: 0, nonWfsOrders: 0,
        });
      }
      const rec = agg.get(key)!;
      if (deliveryType === 3) rec.wfsQty += qty;
      else if (deliveryType === 2) rec.nonWfsQty += qty;
      else rec.mixedQty += qty;
      if (!orderMskus.has(key)) {
        if (deliveryType === 3) rec.wfsOrders += 1;
        else if (deliveryType === 2) rec.nonWfsOrders += 1;
        orderMskus.add(key);
      }
    }
  }
  return { agg, cancelled, deleted };
}

// ── item_id 反查：dim_product(platform,store_id,msku) ─────────────────────────
async function resolveItemIds(
  db: mysql.Connection,
  aggList: ChannelAgg[],
): Promise<{ itemIdByKey: Map<string, string>; unmatched: number; ambiguous: number }> {
  const itemIdByKey = new Map<string, string>();
  let unmatched = 0;
  let ambiguous = 0;
  if (aggList.length === 0) return { itemIdByKey, unmatched, ambiguous };
  const storeIds = [...new Set(aggList.map((a) => a.storeId))];
  const mskus = [...new Set(aggList.map((a) => a.msku))];
  const [rows] = await db.query<mysql.RowDataPacket[]>(
    `SELECT store_id, msku, item_id FROM dim_product
     WHERE platform = 'walmart'
       AND store_id IN (${storeIds.map(() => "?").join(",")})
       AND msku IN (${mskus.map(() => "?").join(",")})`,
    [...storeIds, ...mskus],
  );
  for (const r of rows) {
    const key = `${String(r.store_id)}|${String(r.msku)}`;
    const itemId = String(r.item_id ?? "");
    if (itemIdByKey.has(key) && itemIdByKey.get(key) !== itemId) {
      ambiguous += 1; // 同店同msku多item_id：保留首个，计数告警
      continue;
    }
    itemIdByKey.set(key, itemId);
  }
  for (const a of aggList) {
    if (!itemIdByKey.has(`${a.storeId}|${a.msku}`)) unmatched += 1;
  }
  return { itemIdByKey, unmatched, ambiguous };
}

// ── 处理一天：拉取 → RAW → 聚合 → 反查 → 归零消失键 → UPSERT ─────────────────
async function processDay(
  db: mysql.Connection,
  client: LingxingClient,
  day: string,
  execute: boolean,
): Promise<DaySummary> {
  const { orders, pages } = await fetchDayPages(client, day);
  let rawId = 0;
  if (execute) {
    for (const p of pages) {
      const id = await insertRaw(db, day, p.page, p.params, p.body);
      if (id > 0) rawId = id;
    }
  }
  const { agg, cancelled, deleted } = aggregateOrders(orders);
  const aggList = [...agg.values()];
  const { itemIdByKey, unmatched, ambiguous } = await resolveItemIds(db, aggList);
  if (unmatched > 0) {
    console.warn(`  ⚠️  ${day} 有 ${unmatched} 个 (store,msku) 在 dim_product 未命中，item_id 置空串入库（不吞错，供后续排查）`);
  }

  // 当日已存在但本次聚合消失的键（订单被取消/删除）→ 归零（不删行、不清表）
  let zeroedRows = 0;
  if (execute) {
    const [existRows] = await db.query<mysql.RowDataPacket[]>(
      `SELECT store_id, msku FROM fact_mp_sales_channel_daily
       WHERE platform = 'walmart' AND stat_date = ?`,
      [day],
    );
    const currentKeys = new Set(aggList.map((a) => `${a.storeId}|${a.msku}`));
    const zeroTargets = existRows
      .map((r) => ({ storeId: String(r.store_id), msku: String(r.msku) }))
      .filter((r) => !currentKeys.has(`${r.storeId}|${r.msku}`));
    zeroedRows = zeroTargets.length;

    const allRows = [
      ...aggList.map((a) => ({
        storeId: a.storeId, storeName: a.storeName, msku: a.msku,
        itemId: itemIdByKey.get(`${a.storeId}|${a.msku}`) ?? "",
        wfs: a.wfsQty, nonWfs: a.nonWfsQty, mixed: a.mixedQty,
        wfsCnt: a.wfsOrders, nonWfsCnt: a.nonWfsOrders,
      })),
      ...zeroTargets.map((z) => ({
        storeId: z.storeId, storeName: "", msku: z.msku, itemId: "",
        wfs: 0, nonWfs: 0, mixed: 0, wfsCnt: 0, nonWfsCnt: 0,
      })),
    ];
    const CHUNK = 200;
    for (let i = 0; i < allRows.length; i += CHUNK) {
      const chunk = allRows.slice(i, i + CHUNK);
      const placeholders = chunk.map(() => "(?, 'walmart', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)").join(",");
      const values: Array<string | number | null> = [];
      for (const r of chunk) {
        values.push(day, r.storeId, r.storeName, r.itemId, r.msku,
          r.wfs, r.nonWfs, r.mixed, r.wfsCnt, r.nonWfsCnt, rawId > 0 ? rawId : null);
      }
      await db.query(
        `INSERT INTO fact_mp_sales_channel_daily
           (stat_date, platform, store_id, store_name, item_id, msku,
            wfs_sales_qty, non_wfs_sales_qty, mixed_sales_qty, wfs_order_cnt, non_wfs_order_cnt, source_raw_id)
         VALUES ${placeholders}
         ON DUPLICATE KEY UPDATE
           store_name = IF(VALUES(store_name) = '', store_name, VALUES(store_name)),
           item_id = IF(VALUES(item_id) = '', item_id, VALUES(item_id)),
           wfs_sales_qty = VALUES(wfs_sales_qty),
           non_wfs_sales_qty = VALUES(non_wfs_sales_qty),
           mixed_sales_qty = VALUES(mixed_sales_qty),
           wfs_order_cnt = VALUES(wfs_order_cnt),
           non_wfs_order_cnt = VALUES(non_wfs_order_cnt),
           source_raw_id = COALESCE(VALUES(source_raw_id), source_raw_id)`,
        values,
      );
    }
  }
  return {
    day,
    pages: pages.length,
    orders: orders.length,
    cancelled,
    deleted,
    aggRows: aggList.length,
    zeroedRows,
    unmatchedMsku: unmatched,
    ambiguousMsku: ambiguous,
    rawId,
  };
}

// ── 清货已清：按 product_no(平台商品ID) 聚合一天订单（排除取消/删除单，跨店铺汇总）──
// 需求方拍板：亚马逊按ASIN识别（同ASIN多店铺汇总，同SKU不同ASIN只算该ASIN）；其他平台同理按平台商品ID。
function aggregateByRef(orders: MpOrder[]): Map<string, { qty: number; orderCnt: number; localSku: string }> {
  const agg = new Map<string, { qty: number; orderCnt: number; localSku: string }>();
  for (const order of orders) {
    if (Number(order.is_delete ?? 0) === 1) continue;
    if (Number(order.status ?? 0) === 7) continue;
    const items = Array.isArray(order.item_info) ? order.item_info : [];
    const orderRefs = new Set<string>();
    for (const item of items) {
      if (Number(item.is_delete ?? 0) === 1) continue;
      const ref = String(item.product_no ?? "").trim();
      const qty = Number(item.quantity ?? 0);
      if (!ref || !Number.isFinite(qty) || qty <= 0) continue;
      const localSku = String(item.local_sku ?? "").trim();
      if (!agg.has(ref)) agg.set(ref, { qty: 0, orderCnt: 0, localSku });
      const rec = agg.get(ref)!;
      rec.qty += qty;
      if (!rec.localSku && localSku) rec.localSku = localSku;
      if (!orderRefs.has(ref)) { rec.orderCnt += 1; orderRefs.add(ref); }
    }
  }
  return agg;
}

// ── 处理一天某清货渠道：拉取 → RAW → 按product_no聚合 → 归零消失键 → UPSERT 独立事实表 ──
// 独立于沃尔玛WFS链路：写入 fact_channel_clearance_sales_daily(stat_date,platform,platform_ref)。
async function processChannelClearanceDay(
  db: mysql.Connection,
  client: LingxingClient,
  day: string,
  platform: string,
  codes: number[],
  execute: boolean,
): Promise<{ platform: string; orders: number; refs: number; zeroed: number }> {
  const { orders, pages } = await fetchDayPages(client, day, codes);
  let rawId = 0;
  if (execute) {
    for (const p of pages) {
      const id = await insertRaw(db, day, p.page, p.params, p.body, `channel_clearance_${platform}`);
      if (id > 0) rawId = id;
    }
  }
  const agg = aggregateByRef(orders);
  const aggList = [...agg.entries()].map(([ref, v]) => ({ ref, qty: v.qty, orderCnt: v.orderCnt, localSku: v.localSku }));
  let zeroed = 0;
  if (execute) {
    const [existRows] = await db.query<mysql.RowDataPacket[]>(
      `SELECT platform_ref FROM fact_channel_clearance_sales_daily
       WHERE platform = ? AND stat_date = ?`,
      [platform, day],
    );
    const currentRefs = new Set(aggList.map((a) => a.ref));
    const zeroTargets = existRows
      .map((r) => String(r.platform_ref))
      .filter((s) => !currentRefs.has(s));
    zeroed = zeroTargets.length;
    const allRows = [
      ...aggList.map((a) => ({ ref: a.ref, localSku: a.localSku, qty: a.qty, cnt: a.orderCnt })),
      ...zeroTargets.map((s) => ({ ref: s, localSku: "", qty: 0, cnt: 0 })),
    ];
    const CHUNK = 200;
    for (let i = 0; i < allRows.length; i += CHUNK) {
      const chunk = allRows.slice(i, i + CHUNK);
      const placeholders = chunk.map(() => "(?, ?, ?, ?, ?, ?, ?)").join(",");
      const values: Array<string | number | null> = [];
      for (const r of chunk) {
        values.push(day, platform, r.ref, r.localSku, r.qty, r.cnt, rawId > 0 ? rawId : null);
      }
      await db.query(
        `INSERT INTO fact_channel_clearance_sales_daily
           (stat_date, platform, platform_ref, local_sku, sales_qty, order_cnt, source_raw_id)
         VALUES ${placeholders}
         ON DUPLICATE KEY UPDATE
           local_sku = IF(VALUES(local_sku) = '', local_sku, VALUES(local_sku)),
           sales_qty = VALUES(sales_qty),
           order_cnt = VALUES(order_cnt),
           source_raw_id = COALESCE(VALUES(source_raw_id), source_raw_id)`,
        values,
      );
    }
  }
  return { platform, orders: orders.length, refs: aggList.length, zeroed };
}

async function main(): Promise<void> {
  const args = process.argv.slice(2);
  const execute = args.includes("--execute");
  const startArg = args.find((a) => a.startsWith("--start="))?.slice(8) ?? "";
  const endArg = args.find((a) => a.startsWith("--end="))?.slice(6) ?? "";
  const today = bjTodayStr();
  const end = endArg || addDays(today, -1);
  const start = startArg || addDays(today, -7);
  if (!isValidDate(start) || !isValidDate(end) || start > end) {
    console.error(`参数非法：--start=${start} --end=${end}（要求 YYYY-MM-DD 且 start<=end）`);
    process.exit(2);
  }
  if (end >= today) {
    console.error(`--end=${end} 不得晚于昨天（今天订购数据未完结）`);
    process.exit(2);
  }
  console.log(`═══ WFS销量渠道同步 ${start} ~ ${end}（${execute ? "EXECUTE 落库" : "DRY-RUN 只读"}）═══`);

  const db = await getDb();
  const client = new LingxingClient(loadConfig());
  const summaries: DaySummary[] = [];
  let failed = 0;
  try {
    for (let day = start; day <= end; day = addDays(day, 1)) {
      try {
        const s = await processDay(db, client, day, execute);
        summaries.push(s);
        console.log(
          `  ✓ ${day} 单=${s.orders} 取消=${s.cancelled} 删除=${s.deleted} 聚合行=${s.aggRows}` +
          ` 归零=${s.zeroedRows} msku未命中=${s.unmatchedMsku} 歧义=${s.ambiguousMsku}`,
        );
      } catch (e) {
        failed += 1;
        const msg = e instanceof Error ? e.message : String(e);
        summaries.push({
          day, pages: 0, orders: 0, cancelled: 0, deleted: 0,
          aggRows: 0, zeroedRows: 0, unmatchedMsku: 0, ambiguousMsku: 0, rawId: 0, error: msg,
        });
        console.error(`  ✗ ${day} 失败：${msg}（继续后续日期）`);
      }
      // 2026-07-24 清货已清：亚马逊/希音/TEMU/TikTok 按平台商品ID销量 → 独立事实表（失败只记日志，不影响WFS主链路）
      try {
        const parts: string[] = [];
        for (const ch of CLEARANCE_CHANNELS) {
          const s = await processChannelClearanceDay(db, client, day, ch.platform, ch.codes, execute);
          parts.push(`${ch.platform}(单=${s.orders} ref=${s.refs} 归零=${s.zeroed})`);
        }
        console.log(`    ↳ 清货已清 ${day} ${parts.join(" ")}`);
      } catch (e) {
        console.error(`    ✗ ${day} 清货已清渠道失败：${e instanceof Error ? e.message : String(e)}（不影响WFS主链路）`);
      }
      await sleep(PAGE_SLEEP_MS);
    }
  } finally {
    await db.end();
  }

  const totals = summaries.reduce(
    (acc, s) => ({
      orders: acc.orders + s.orders,
      cancelled: acc.cancelled + s.cancelled,
      aggRows: acc.aggRows + s.aggRows,
      unmatched: acc.unmatched + s.unmatchedMsku,
    }),
    { orders: 0, cancelled: 0, aggRows: 0, unmatched: 0 },
  );
  console.log(`SUMMARY_JSON ${JSON.stringify({
    mode: execute ? "execute" : "dry-run",
    window: { start, end },
    days: summaries.length,
    daysFailed: failed,
    orders: totals.orders,
    cancelled: totals.cancelled,
    aggRows: totals.aggRows,
    unmatchedMsku: totals.unmatched,
  })}`);
  if (failed > 0) process.exit(1);
}

main().catch((e) => {
  console.error(`FATAL: ${e instanceof Error ? e.stack || e.message : String(e)}`);
  process.exit(1);
});
