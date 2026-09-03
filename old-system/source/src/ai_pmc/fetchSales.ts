/**
 * src/ai_pmc/fetchSales.ts
 * Phase 8 — 直接调领星销量统计接口（与「当日数据」抓取同一套调用方式）
 *
 * 接口：POST /basicOpen/platformStatisticsV2/saleStat/pageList
 * 参数（复用现有口径）：start_date/end_date, result_type="1"(销量),
 *        date_unit="4", data_type="1", page(1基), length, sids:[storeId]
 * 取值：volumeTotal，按 platform_product_id（商品ID=ItemID）聚合。
 * 店铺：复用 syncDailyBaseData 的 STORES（6 个沃尔玛店铺）。
 *
 * 输出：Map<itemId, { qtyShort, qtyLong, qtyYoy }>
 * 数据日期口径：美国时间当天减 2 天（与当日数据一致）。
 */

process.env.TZ = 'Asia/Shanghai';

import { LingxingClient } from '../lingxingClient';
import { loadConfig } from '../config';
import { STORES } from '../syncDailyBaseData';
import { SalesByItem } from './calcReplenishment';
import { todayBJDateMs, formatBJ } from './dateUtil';
import { logger, errMsg } from './logger';

const SALE_STAT_PATH = '/basicOpen/platformStatisticsV2/saleStat/pageList';
const PAGE_LENGTH = 200;
const MAX_PAGES = 50;
const PAGE_INTERVAL_MS = 200;
const MAX_RETRY = 3;
const BACKOFF_MS = [1000, 2000, 4000];
const DAY = 86400000;

const sleep = (ms: number) => new Promise<void>((r) => setTimeout(r, ms));

function ymd(ms: number): string {
  return formatBJ(new Date(ms), false).slice(0, 10);
}
function toNum(v: unknown): number {
  const n = Number(v);
  return Number.isFinite(n) ? n : 0;
}
function toIds(v: unknown): string[] {
  if (Array.isArray(v)) return v.map((x) => String(x).trim()).filter(Boolean);
  const s = String(v ?? '').trim();
  return s ? [s] : [];
}
function listOf(data: any): any[] {
  if (Array.isArray(data)) return data;
  for (const k of ['list', 'records', 'rows']) if (Array.isArray(data?.[k])) return data[k];
  if (Array.isArray(data?.data?.list)) return data.data.list;
  return [];
}

async function postRetry(client: LingxingClient, params: Record<string, unknown>, label: string): Promise<unknown | null> {
  for (let a = 0; a <= MAX_RETRY; a++) {
    try {
      const resp = await client.request<unknown>({ method: 'POST', path: SALE_STAT_PATH, params, timeoutMs: 120000 });
      return (resp as any)?.data ?? resp;
    } catch (e) {
      if (a < MAX_RETRY) { logger.warn(`[fetchSales] ${label} 第${a + 1}次失败，重试：${errMsg(e)}`); await sleep(BACKOFF_MS[a] ?? 4000); }
      else { logger.error(`[fetchSales] ${label} 重试${MAX_RETRY}次仍失败，跳过`, e); return null; }
    }
  }
  return null;
}

/** 取某时间窗内、所有店铺按 ItemID 的销量合计 */
async function fetchWindowSum(client: LingxingClient, startStr: string, endStr: string): Promise<Map<string, number>> {
  const sum = new Map<string, number>();
  for (const store of STORES) {
    for (let page = 1; page <= MAX_PAGES; page++) {
      const data = await postRetry(client, {
        start_date: startStr, end_date: endStr, result_type: '1', date_unit: '4', data_type: '1',
        page, length: PAGE_LENGTH, sids: [store.storeId],
      }, `${store.storeName} ${startStr}~${endStr} p${page}`);
      if (data === null) break;
      const items = listOf(data);
      for (const it of items) {
        const qty = toNum((it as any)?.volumeTotal);
        for (const id of toIds((it as any)?.platform_product_id)) sum.set(id, (sum.get(id) ?? 0) + qty);
      }
      if (items.length < PAGE_LENGTH) break;
      await sleep(PAGE_INTERVAL_MS);
    }
  }
  return sum;
}

/** 拉取销量：近 daysShort / daysLong / 去年同期 yoyDays 天，按 ItemID 汇总 */
export async function fetchSales(daysShort: number, daysLong: number, yoyDays: number): Promise<Map<string, SalesByItem>> {
  const client = new LingxingClient(loadConfig());
  const anchorMs = todayBJDateMs() - 2 * DAY; // 数据日期 = 美国时间当天减2天（近似）
  const end = ymd(anchorMs);

  logger.info(`[fetchSales] 锚点日期=${end}，窗口 ${daysShort}/${daysLong}/去年${yoyDays}天，店铺${STORES.length}个`);

  const shortSum = await fetchWindowSum(client, ymd(anchorMs - (daysShort - 1) * DAY), end);
  logger.info(`[fetchSales] 近${daysShort}天窗口完成，${shortSum.size} 个ItemID`);
  const longSum  = await fetchWindowSum(client, ymd(anchorMs - (daysLong - 1) * DAY), end);
  logger.info(`[fetchSales] 近${daysLong}天窗口完成，${longSum.size} 个ItemID`);
  const yoyEndMs = anchorMs - 365 * DAY;
  const yoySum   = await fetchWindowSum(client, ymd(yoyEndMs - (yoyDays - 1) * DAY), ymd(yoyEndMs));
  logger.info(`[fetchSales] 去年同期窗口完成，${yoySum.size} 个ItemID`);

  const map = new Map<string, SalesByItem>();
  const ensure = (id: string) => { let v = map.get(id); if (!v) { v = { qtyShort: 0, qtyLong: 0, qtyYoy: 0 }; map.set(id, v); } return v; };
  for (const [id, q] of shortSum) ensure(id).qtyShort = q;
  for (const [id, q] of longSum)  ensure(id).qtyLong = q;
  for (const [id, q] of yoySum)   ensure(id).qtyYoy = q;

  logger.info(`[fetchSales] 完成：覆盖 ${map.size} 个 ItemID（近${daysShort}天店铺合计SKU ${shortSum.size}）`);
  return map;
}
