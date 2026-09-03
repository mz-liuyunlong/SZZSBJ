/**
 * src/ai_pmc/fetchInventory.ts
 * Phase 8 — 合并 4 类库存（按 ItemID/商品ID，与销量 platform_product_id 对齐），FBA 不做
 *
 *   国内仓        ← inventoryDetails（fetchLocalStockMap，按 SKU）
 *   采购未到货    ← purchaseOrderList（应入库−已入库，>0，按 SKU）
 *   WFS 海外在库  ← 「当日数据」表 T 列 wfs_available_quantity（按 ItemID，多店铺求和）
 *   品名/负责人   ← 「当日数据」表 F/G 列
 *   SKU→ItemID 映射 ← 「当日数据」表 C(商品ID)/E(SKU) 同行
 *
 * 输出：Map<itemId, InventoryByItem>
 */

process.env.TZ = 'Asia/Shanghai';

import * as fs from 'fs';
import * as path from 'path';
import { FeishuSheetWriter } from '../feishuSheetWriter';
import { InventoryByItem } from './calcReplenishment';
import { fetchLocalStockMap } from './fetchLocalInventory';
import { fetchPurchaseOrders } from './fetchLingxing';
import { FALLBACK_NAME, FALLBACK_OPEN_ID } from './readOwners';
import { logger } from './logger';

const DAILY_TOKEN = '<REDACTED_FEISHU_SPREADSHEET_TOKEN>';
const DAILY_SHEET_ID = '<REDACTED_FEISHU_SHEET_ID>'; // 当日数据
const DAILY_RANGE = 'A2:V5000';
// 列：C商品ID=2, E SKU=4, F品名=5, G负责人=6, T WFS可售库存=19
const COL = { ITEM_ID: 2, SKU: 4, NAME: 5, OWNER: 6, WFS: 19 };

function loadOpenIds(): Record<string, string> {
  try { return JSON.parse(fs.readFileSync(path.resolve(process.cwd(), 'config/ownerOpenIds.json'), 'utf-8')); }
  catch { return {}; }
}

/** 采购未到货：各 SKU 的（应入库−已入库）求和，仅取 >0 的明细 */
async function fetchPurchasePending(): Promise<Map<string, number>> {
  const map = new Map<string, number>();
  try {
    const orders = await fetchPurchaseOrders(undefined, 500);
    for (const o of orders) for (const it of o.item_list) {
      const sku = String(it.sku ?? '').trim();
      if (!sku) continue;
      const pending = (it.quantity_real ?? 0) - (it.quantity_entry ?? 0);
      if (pending > 0) map.set(sku, (map.get(sku) ?? 0) + pending);
    }
  } catch (e) { logger.error('[fetchInventory] 采购未到货读取失败，按 0 处理', e); }
  return map;
}

export async function fetchInventory(writer: FeishuSheetWriter): Promise<Map<string, InventoryByItem>> {
  const openIds = loadOpenIds();
  const result = new Map<string, InventoryByItem>();
  const skuToItemId = new Map<string, string>();

  // 1. 当日数据：WFS 库存 + 品名/负责人（以 ItemID 为键，WFS 多店铺求和）
  let rows: (string | number | boolean | null)[][] = [];
  try {
    rows = writer.readValues({ spreadsheetToken: DAILY_TOKEN, sheetId: DAILY_SHEET_ID, range: DAILY_RANGE });
  } catch (e) {
    logger.error('[fetchInventory] 读取「当日数据」失败，库存合并中止', e);
    return result;
  }
  for (const row of rows) {
    const itemId = String(row[COL.ITEM_ID] ?? '').trim();
    if (!itemId) continue;
    const sku = String(row[COL.SKU] ?? '').trim();
    const name = String(row[COL.NAME] ?? '').trim();
    const owner = String(row[COL.OWNER] ?? '').trim();
    const wfs = Number(row[COL.WFS]);
    if (sku) skuToItemId.set(sku, itemId);
    const cur = result.get(itemId) ?? {
      sku, productName: name, domestic: 0, purchasePending: 0, inTransit: 0, overseas: 0,
      ownerName: owner || FALLBACK_NAME, ownerOpenId: openIds[owner] ?? FALLBACK_OPEN_ID,
    };
    if (sku && !cur.sku) cur.sku = sku;
    if (name && !cur.productName) cur.productName = name;
    if (owner && (cur.ownerName === FALLBACK_NAME)) { cur.ownerName = owner; cur.ownerOpenId = openIds[owner] ?? FALLBACK_OPEN_ID; }
    cur.overseas += Number.isFinite(wfs) ? Math.max(0, wfs) : 0; // WFS 海外在库（多店铺累加）
    result.set(itemId, cur);
  }

  // 2. 国内仓（按 SKU → 经 skuToItemId 并入 ItemID）
  const domesticMap = await fetchLocalStockMap();
  let domMatched = 0;
  for (const [sku, qty] of domesticMap) {
    const itemId = skuToItemId.get(sku);
    if (!itemId) continue;
    const cur = result.get(itemId);
    if (cur) { cur.domestic += Math.max(0, qty); domMatched++; }
  }

  // 3. 采购未到货
  const pendingMap = await fetchPurchasePending();
  let penMatched = 0;
  for (const [sku, qty] of pendingMap) {
    const itemId = skuToItemId.get(sku);
    if (!itemId) continue;
    const cur = result.get(itemId);
    if (cur) { cur.purchasePending += Math.max(0, qty); penMatched++; }
  }

  logger.info(`[fetchInventory] 合并完成：${result.size} 个 ItemID（国内匹配${domMatched}/采购未到货匹配${penMatched}）`);
  return result;
}
