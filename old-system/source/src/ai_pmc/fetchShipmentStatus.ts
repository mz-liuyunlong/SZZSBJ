/**
 * src/ai_pmc/fetchShipmentStatus.ts
 * Phase 7B — 拉取 WFS 货件当前状态（按 SKU 展开），用于发货流程细分提醒
 *
 * 只做 WFS（FBA 暂缓：本账号 FBA 量极小，且细分状态在另一个 MWS 接口）。
 * 接口：POST /cepf/warehouse/api/openApi/queryWFSCargoPage
 *
 * 状态映射（cargo_sync_status，已确认）：
 *   已申报 → 货件已建未发货（待确认发出）
 *   已发货 → 头程已出，等待海外到货
 *   入库中 → 海外仓入库中（在途，不提醒）
 *   已完成 → 海外到货（终态，不提醒）
 *   已取消 → 排除
 *
 * 只读、安全。
 */

process.env.TZ = 'Asia/Shanghai';

import { LingxingClient } from '../lingxingClient';
import { loadConfig } from '../config';
import { logger, errMsg } from './logger';

const WFS_CARGO_PATH = '/cepf/warehouse/api/openApi/queryWFSCargoPage';
const PAGE = 100;
const PAGE_INTERVAL_MS = 200;
const MAX_RETRY = 3;
const BACKOFF_MS = [1000, 2000, 4000];
const MAX_PAGES = 50;

/** WFS 货件按 SKU 展开后的一条记录 */
export interface WfsShipmentItem {
  itemId: string;       // = sku
  cargoCode: string;    // 货件号
  storeName: string;
  syncStatus: string;   // 已申报/已发货/入库中/已完成/已取消
  productName: string;
  createDate: string;   // cargo_create_date（已申报基准）
  awaitTime: string;    // to_await_time（已发货基准，epoch ms 字符串）
  receiveTime: string;  // to_receive_time
}

const sleep = (ms: number) => new Promise<void>((r) => setTimeout(r, ms));

function pickList(d: any): any[] {
  if (Array.isArray(d)) return d;
  if (Array.isArray(d?.list)) return d.list;
  if (Array.isArray(d?.data)) return d.data;
  if (Array.isArray(d?.records)) return d.records;
  if (Array.isArray(d?.data?.list)) return d.data.list;
  return [];
}

async function postWithRetry(client: LingxingClient, params: Record<string, unknown>, label: string): Promise<unknown | null> {
  for (let attempt = 0; attempt <= MAX_RETRY; attempt++) {
    try {
      const resp = await client.post(WFS_CARGO_PATH, params);
      return (resp.data as any)?.data ?? resp.data;
    } catch (e) {
      if (attempt < MAX_RETRY) {
        const wait = BACKOFF_MS[attempt] ?? 4000;
        logger.warn(`[fetchShipmentStatus] ${label} 第${attempt + 1}次失败，${wait}ms 后重试：${errMsg(e)}`);
        await sleep(wait);
      } else {
        logger.error(`[fetchShipmentStatus] ${label} 重试${MAX_RETRY}次仍失败，跳过`, e);
        return null;
      }
    }
  }
  return null;
}

/** 拉取所有 WFS 货件，按 cargo_good_list 的 SKU 展开（排除已取消） */
export async function fetchWfsShipmentItems(): Promise<WfsShipmentItem[]> {
  const client = new LingxingClient(loadConfig());
  const out: WfsShipmentItem[] = [];
  let offset = 0;

  logger.info('[fetchShipmentStatus] 开始拉取 WFS 货件');

  for (let page = 0; page < MAX_PAGES; page++) {
    const data = await postWithRetry(client, { offset, length: PAGE }, `offset=${offset}`);
    if (data === null) break;
    const cargos = pickList(data);
    if (cargos.length === 0) break;

    for (const c of cargos) {
      const syncStatus = String(c?.cargo_sync_status ?? '').trim();
      if (syncStatus === '已取消') continue;
      const goods: any[] = Array.isArray(c?.cargo_good_list) ? c.cargo_good_list : [];
      for (const g of goods) {
        const sku = String(g?.sku ?? '').trim();
        if (!sku) continue;
        out.push({
          itemId: sku,
          cargoCode: String(c?.cargo_code ?? '').trim(),
          storeName: String(c?.store_name ?? '').trim(),
          syncStatus,
          productName: String(g?.product_name ?? '').trim(),
          createDate: String(c?.cargo_create_date ?? '').trim(),
          awaitTime: String(c?.to_await_time ?? '').trim(),
          receiveTime: String(c?.to_receive_time ?? '').trim(),
        });
      }
    }

    if (cargos.length < PAGE) break;
    offset += PAGE;
    await sleep(PAGE_INTERVAL_MS);
  }

  logger.info(`[fetchShipmentStatus] 完成：WFS 货件明细 ${out.length} 条`);
  return out;
}
