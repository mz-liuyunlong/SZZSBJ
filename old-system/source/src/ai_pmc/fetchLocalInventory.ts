/**
 * src/ai_pmc/fetchLocalInventory.ts
 * Phase 7a — 本地仓库库存（按 SKU 是否还有库存判断是否已发货）
 *
 * 逻辑：货到仓后，若该 SKU 在本地仓库当前库存 > 0 → 货还压在仓库没发走，应提醒发货；
 *      库存 ≤ 0 → 已发走/被发货单扣减 → 不提醒。
 *
 * 接口（用户已确认）：查询仓库库存明细
 *   POST /erp/sc/routing/data/local_inventory/inventoryDetails
 *
 * 只读、安全。首次运行打印字段快照，便于确认"可用库存"字段名。
 */

process.env.TZ = 'Asia/Shanghai';

import { LingxingClient } from '../lingxingClient';
import { loadConfig } from '../config';
import { logger, errMsg } from './logger';

const INVENTORY_PATH = '/erp/sc/routing/data/local_inventory/inventoryDetails';
const PAGE_SIZE = 200;
const PAGE_INTERVAL_MS = 200;
const MAX_RETRY = 3;
const BACKOFF_MS = [1000, 2000, 4000];
const MAX_PAGES = 200; // 安全上限

/** 可用库存候选字段（按优先级），命中第一个有值的 */
const STOCK_FIELDS = [
  'product_valid_num', 'valid_num', 'validNum',
  'available_num', 'available', 'good_num', 'quantity', 'stock_num', 'total_num',
];

const sleep = (ms: number) => new Promise<void>((r) => setTimeout(r, ms));

function pickList(data: unknown): any[] {
  const d = data as any;
  if (Array.isArray(d)) return d;
  if (Array.isArray(d?.list)) return d.list;
  if (Array.isArray(d?.data)) return d.data;
  if (Array.isArray(d?.records)) return d.records;
  if (Array.isArray(d?.rows)) return d.rows;
  if (Array.isArray(d?.data?.list)) return d.data.list;
  return [];
}

function pickStock(row: any): number {
  for (const f of STOCK_FIELDS) {
    if (row[f] !== undefined && row[f] !== null && row[f] !== '') {
      const n = Number(row[f]);
      if (Number.isFinite(n)) return n;
    }
  }
  return 0;
}

async function postWithRetry(client: LingxingClient, params: Record<string, unknown>, label: string): Promise<unknown | null> {
  for (let attempt = 0; attempt <= MAX_RETRY; attempt++) {
    try {
      const resp = await client.post(INVENTORY_PATH, params);
      return (resp.data as any)?.data ?? resp.data;
    } catch (e) {
      if (attempt < MAX_RETRY) {
        const wait = BACKOFF_MS[attempt] ?? 4000;
        logger.warn(`[fetchLocalInventory] ${label} 第${attempt + 1}次失败，${wait}ms 后重试：${errMsg(e)}`);
        await sleep(wait);
      } else {
        logger.error(`[fetchLocalInventory] ${label} 重试${MAX_RETRY}次仍失败`, e);
        return null;
      }
    }
  }
  return null;
}

export interface LocalStockResult {
  /** 当前本地仓库存 > 0 的 SKU 集合；null 表示拉取失败（调用方应降级，不据此过滤） */
  inStockSkus: Set<string> | null;
  rowCount: number;
}

/**
 * 返回本地仓库存 > 0 的 SKU 集合。
 * 任一页彻底失败即整体降级返回 null（调用方据此不应用"无库存即跳过"过滤，避免误杀）。
 */
export async function fetchLocalStockSkus(): Promise<LocalStockResult> {
  const client = new LingxingClient(loadConfig());
  const inStock = new Set<string>();
  let rowCount = 0;
  let offset = 0;
  let firstPageSnapshotDone = false;

  logger.info('[fetchLocalInventory] 开始拉取本地仓库存明细');

  for (let page = 0; page < MAX_PAGES; page++) {
    const data = await postWithRetry(client, { offset, length: PAGE_SIZE }, `offset=${offset}`);
    if (data === null) {
      logger.error('[fetchLocalInventory] 拉取失败，整体降级（本次不应用库存过滤）');
      return { inStockSkus: null, rowCount };
    }
    const rows = pickList(data);
    if (rows.length === 0) break;

    // 首页字段快照，便于确认"可用库存"字段名
    if (!firstPageSnapshotDone && rows.length > 0) {
      firstPageSnapshotDone = true;
      const sample = rows.slice(0, 2).map((r: any) => {
        const stockKeys = Object.keys(r).filter((k) => /num|qty|quantity|stock|valid|available/i.test(k));
        return { sku: r.sku ?? r.msku, stockFields: Object.fromEntries(stockKeys.map((k) => [k, r[k]])) };
      });
      logger.info(`[fetchLocalInventory] 字段快照: ${JSON.stringify(sample)}`);
    }

    for (const r of rows) {
      rowCount++;
      const sku = String(r?.sku ?? '').trim();
      if (!sku) continue;
      if (pickStock(r) > 0) inStock.add(sku);
    }

    if (rows.length < PAGE_SIZE) break;
    offset += PAGE_SIZE;
    await sleep(PAGE_INTERVAL_MS);
  }

  logger.info(`[fetchLocalInventory] 完成：有库存 SKU ${inStock.size} 个（明细行 ${rowCount}）`);
  return { inStockSkus: inStock, rowCount };
}

/**
 * Phase 8：返回各 SKU 的国内仓当前可用库存数量 Map<sku, qty>。
 * 拉取失败返回空 Map（调用方据此把国内库存当 0 处理）。
 */
export async function fetchLocalStockMap(): Promise<Map<string, number>> {
  const client = new LingxingClient(loadConfig());
  const map = new Map<string, number>();
  let offset = 0;
  for (let page = 0; page < MAX_PAGES; page++) {
    const data = await postWithRetry(client, { offset, length: PAGE_SIZE }, `qtyMap offset=${offset}`);
    if (data === null) break;
    const rows = pickList(data);
    if (rows.length === 0) break;
    for (const r of rows) {
      const sku = String(r?.sku ?? '').trim();
      if (!sku) continue;
      map.set(sku, (map.get(sku) ?? 0) + Math.max(0, pickStock(r)));
    }
    if (rows.length < PAGE_SIZE) break;
    offset += PAGE_SIZE;
    await sleep(PAGE_INTERVAL_MS);
  }
  logger.info(`[fetchLocalInventory] 国内库存数量 Map：${map.size} 个 SKU`);
  return map;
}
