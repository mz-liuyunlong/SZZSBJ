/**
 * src/ai_pmc/fetchShipments.ts
 * Phase 7a — 发货动作 SKU 集合（按 SKU + 时间关联）
 *
 * 目的：拉取 FBA 发货计划 + WFS 货件，得出"近 N 天有发货动作的 SKU 集合"。
 * 用途：checkStatus 判断"货到仓但还没安排发货"时，若该 SKU 在此集合内
 *      → 说明已创建发货单/货件，已进入发货流程，不再提醒仓库发货。
 *
 * 只读、安全。状态码细分（打包/装箱/头程…）留待 Phase 7b。
 *
 * 接口（用户已确认）：
 *   FBA 发货计划：POST /erp/sc/data/fba_report/shipmentPlanLists
 *   WFS 货件：    POST /cepf/warehouse/api/openApi/queryWFSCargoPage
 */

process.env.TZ = 'Asia/Shanghai';

import { LingxingClient } from '../lingxingClient';
import { loadConfig } from '../config';
import { daysSince } from './dateUtil';
import { logger, errMsg } from './logger';

const FBA_PLAN_PATH = '/erp/sc/data/fba_report/shipmentPlanLists';
const WFS_CARGO_PATH = '/cepf/warehouse/api/openApi/queryWFSCargoPage';
const PAGE_SIZE = 100;
const PAGE_INTERVAL_MS = 200;
const MAX_RETRY = 3;
const BACKOFF_MS = [1000, 2000, 4000];
const MAX_PAGES = 50; // 安全上限，防异常死循环

/** 默认：近 60 天内有发货动作即视为"已安排发货" */
export const DEFAULT_SHIPMENT_WINDOW_DAYS = 60;

export interface ShipmentSkuResult {
  skus: Set<string>; // 近 N 天有发货动作的 SKU
  fbaCount: number;
  wfsCount: number;
}

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

async function postWithRetry(client: LingxingClient, path: string, params: Record<string, unknown>, label: string): Promise<unknown | null> {
  for (let attempt = 0; attempt <= MAX_RETRY; attempt++) {
    try {
      const resp = await client.post(path, params);
      return (resp.data as any)?.data ?? resp.data;
    } catch (e) {
      if (attempt < MAX_RETRY) {
        const wait = BACKOFF_MS[attempt] ?? 4000;
        logger.warn(`[fetchShipments] ${label} 第${attempt + 1}次失败，${wait}ms 后重试：${errMsg(e)}`);
        await sleep(wait);
      } else {
        logger.error(`[fetchShipments] ${label} 重试${MAX_RETRY}次仍失败，跳过`, e);
        return null;
      }
    }
  }
  return null;
}

/** 拉 FBA 发货计划，收集近 windowDays 天创建的计划里的 SKU */
async function collectFbaSkus(client: LingxingClient, windowDays: number, out: Set<string>): Promise<number> {
  let added = 0;
  let offset = 0;
  for (let page = 0; page < MAX_PAGES; page++) {
    const data = await postWithRetry(client, FBA_PLAN_PATH, { offset, length: PAGE_SIZE }, `FBA offset=${offset}`);
    if (data === null) break;
    const plans = pickList(data);
    if (plans.length === 0) break;

    for (const plan of plans) {
      const items: any[] = Array.isArray(plan?.list) ? plan.list : [plan];
      for (const it of items) {
        const created = it?.create_time ?? plan?.create_time;
        const d = daysSince(created);
        // 近 windowDays 天内创建的发货计划才算"本批次已安排发货"
        if (d !== null && d <= windowDays) {
          const sku = String(it?.sku ?? '').trim();
          if (sku) { if (!out.has(sku)) added++; out.add(sku); }
        }
      }
    }
    if (plans.length < PAGE_SIZE) break;
    offset += PAGE_SIZE;
    await sleep(PAGE_INTERVAL_MS);
  }
  return added;
}

/** 拉 WFS 货件，收集近 windowDays 天创建、且非取消状态的货件里的 SKU */
async function collectWfsSkus(client: LingxingClient, windowDays: number, out: Set<string>): Promise<number> {
  let added = 0;
  let offset = 0;
  for (let page = 0; page < MAX_PAGES; page++) {
    const data = await postWithRetry(client, WFS_CARGO_PATH, { offset, length: PAGE_SIZE }, `WFS offset=${offset}`);
    if (data === null) break;
    const cargos = pickList(data);
    if (cargos.length === 0) break;

    for (const cargo of cargos) {
      const status = String(cargo?.cargo_status ?? '').toUpperCase();
      if (status === 'CANCELLED') continue; // 已取消的货件不算已发货
      const created = cargo?.cargo_create_date;
      const d = daysSince(created);
      if (d !== null && d > windowDays) continue;
      const goods: any[] = Array.isArray(cargo?.cargo_good_list) ? cargo.cargo_good_list : [];
      for (const g of goods) {
        const sku = String(g?.sku ?? '').trim();
        if (sku) { if (!out.has(sku)) added++; out.add(sku); }
      }
    }
    if (cargos.length < PAGE_SIZE) break;
    offset += PAGE_SIZE;
    await sleep(PAGE_INTERVAL_MS);
  }
  return added;
}

/**
 * 返回近 windowDays 天有发货动作（FBA 发货计划 或 WFS 货件）的 SKU 集合。
 * 任一数据源失败只记日志、不影响另一个；整体失败返回空集合（调用方据此降级）。
 */
export async function fetchShipmentSkus(windowDays = DEFAULT_SHIPMENT_WINDOW_DAYS): Promise<ShipmentSkuResult> {
  const client = new LingxingClient(loadConfig());
  const skus = new Set<string>();
  logger.info(`[fetchShipments] 开始拉取发货动作 SKU（近 ${windowDays} 天）`);

  let fbaCount = 0;
  let wfsCount = 0;
  try { fbaCount = await collectFbaSkus(client, windowDays, skus); }
  catch (e) { logger.error('[fetchShipments] FBA 拉取异常', e); }
  try { wfsCount = await collectWfsSkus(client, windowDays, skus); }
  catch (e) { logger.error('[fetchShipments] WFS 拉取异常', e); }

  logger.info(`[fetchShipments] 完成：发货动作 SKU 共 ${skus.size} 个（FBA 新增${fbaCount} / WFS 新增${wfsCount}）`);
  return { skus, fbaCount, wfsCount };
}
