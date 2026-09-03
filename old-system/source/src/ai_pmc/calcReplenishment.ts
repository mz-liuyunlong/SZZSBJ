/**
 * src/ai_pmc/calcReplenishment.ts
 * Phase 8 — 补货需求计算（纯逻辑，不依赖任何接口）
 *
 * 公式（按 FyeDgo 配置）：
 *   avgDaily   = MAX(近15天日均, 近30天日均)
 *   adjustedAvg= isQ4 ? avgDaily × q4_multiplier : avgDaily
 *   totalInventory = 国内 + (采购未到货|开关) + (在途|开关) + (海外|开关)
 *   targetInventory= adjustedAvg × safety_days
 *   suggestQty     = targetInventory - totalInventory
 *   needReplenish  = suggestQty >= min_suggest_qty
 */

import { ReplenishConfig } from './replenishConfig';
import { todayBJString } from './dateUtil';

/** 各 ItemID 的销量（窗口内总销量件数） */
export interface SalesByItem {
  qtyShort: number; // 近 salesDaysShort 天总销量
  qtyLong: number;  // 近 salesDaysLong 天总销量
  qtyYoy: number;   // 去年同期 yoyDays 天总销量
}

/** 各 ItemID 的 4 类库存 + 基础信息 */
export interface InventoryByItem {
  sku: string;
  productName: string;
  domestic: number;        // 国内仓
  purchasePending: number; // 采购未到货
  inTransit: number;       // 发往海外在途
  overseas: number;        // 海外在库
  ownerName: string;
  ownerOpenId: string;
}

export interface ReplenishTask {
  itemId: string;
  sku: string;
  productName: string;
  avgDaily15: number;
  avgDaily30: number;
  avgDaily: number;
  isQ4: boolean;
  adjustedAvg: number;
  yoyAvgDaily: number;
  yoyRatio: number;
  domestic: number;
  purchasePending: number;
  inTransit: number;
  overseas: number;
  totalInventory: number;
  targetInventory: number;
  suggestQty: number;
  needReplenish: boolean;
  ownerName: string;
  ownerOpenId: string;
  aiResult?: AiEvalResult;
}

export interface AiEvalResult {
  priority: string;            // 高/中/低
  adjustedSuggestQty: number;
  reason: string;
  analysis: string;
  aiSuccess: boolean;
}

function round1(n: number): number {
  return Math.round(n * 10) / 10;
}

/**
 * 计算补货需求，返回 needReplenish=true 的任务列表。
 * @param sales     ItemID → 销量
 * @param inventory ItemID → 库存
 * @param config    FyeDgo 配置
 * @param now       当前日期（默认今天，北京）
 */
export function calcReplenishment(
  sales: Map<string, SalesByItem>,
  inventory: Map<string, InventoryByItem>,
  config: ReplenishConfig,
  now: Date = new Date(),
): ReplenishTask[] {
  const month = Number(todayBJString(now).slice(5, 7));
  const isQ4 = config.q4Months.includes(month);
  const tasks: ReplenishTask[] = [];

  // 以库存表的 ItemID 全集为准（有库存信息才能算）
  for (const [itemId, inv] of inventory) {
    const s = sales.get(itemId) ?? { qtyShort: 0, qtyLong: 0, qtyYoy: 0 };
    const avgDaily15 = config.salesDaysShort > 0 ? s.qtyShort / config.salesDaysShort : 0;
    const avgDaily30 = config.salesDaysLong > 0 ? s.qtyLong / config.salesDaysLong : 0;
    const avgDaily = config.salesMethod.toUpperCase() === 'MAX'
      ? Math.max(avgDaily15, avgDaily30)
      : (avgDaily15 + avgDaily30) / 2;
    const adjustedAvg = isQ4 ? avgDaily * config.q4Multiplier : avgDaily;

    const yoyAvgDaily = config.yoyDays > 0 ? s.qtyYoy / config.yoyDays : 0;
    const yoyRatio = avgDaily30 > 0 ? round1(yoyAvgDaily / avgDaily30) : 0;

    const totalInventory =
      (config.includeDomestic ? inv.domestic : 0) +
      (config.includePurchasePending ? inv.purchasePending : 0) +
      (config.includeInTransit ? inv.inTransit : 0) +
      (config.includeOverseas ? inv.overseas : 0);

    const targetInventory = Math.round(adjustedAvg * config.safetyDays);
    const rawSuggestQty = Math.round(targetInventory - totalInventory);
    const needReplenish = rawSuggestQty >= config.minSuggestQty;

    if (!needReplenish) continue;

    // 单次补货量下限：触发后不低于 min_order_qty（默认100）
    const suggestQty = Math.max(rawSuggestQty, config.minOrderQty);

    tasks.push({
      itemId,
      sku: inv.sku,
      productName: inv.productName,
      avgDaily15: round1(avgDaily15),
      avgDaily30: round1(avgDaily30),
      avgDaily: round1(avgDaily),
      isQ4,
      adjustedAvg: round1(adjustedAvg),
      yoyAvgDaily: round1(yoyAvgDaily),
      yoyRatio,
      domestic: inv.domestic,
      purchasePending: inv.purchasePending,
      inTransit: inv.inTransit,
      overseas: inv.overseas,
      totalInventory,
      targetInventory,
      suggestQty,
      needReplenish,
      ownerName: inv.ownerName,
      ownerOpenId: inv.ownerOpenId,
    });
  }

  return tasks;
}

/** 数组分批 */
export function chunk<T>(arr: T[], size: number): T[][] {
  const out: T[][] = [];
  for (let i = 0; i < arr.length; i += Math.max(1, size)) out.push(arr.slice(i, i + Math.max(1, size)));
  return out;
}
