/**
 * src/ai_pmc/replenishConfig.ts
 * Phase 8 — 读取补货规则配置（FyeDgo，A列=字段名，B列=值）
 *
 * 读取失败/缺字段时回退默认值并记日志（不中断）。
 */

process.env.TZ = 'Asia/Shanghai';

import { FeishuSheetWriter } from '../feishuSheetWriter';
import { PMC_SPREADSHEET_TOKEN } from './config';
import { logger } from './logger';

export const REPLENISH_SHEET_ID = '<REDACTED_FEISHU_SHEET_ID>';

export interface ReplenishConfig {
  salesDaysShort: number;     // 15
  salesDaysLong: number;      // 30
  salesMethod: string;        // MAX
  safetyDays: number;         // 50
  q4Months: number[];         // [10,11,12]
  q4Multiplier: number;       // 2.0
  yoyDays: number;            // 30
  includeDomestic: boolean;
  includePurchasePending: boolean;
  includeInTransit: boolean;
  includeOverseas: boolean;
  minSuggestQty: number;      // 50（触发阈值）
  minOrderQty: number;        // 100（单次补货量下限）
  aiEvaluate: string;         // 启用/停用
  aiBatchSize: number;        // 20
  aiTimeoutMs: number;        // 30000
  notifyDay: string;          // 周日
  isActive: string;           // 启用/停用
}

const DEFAULTS: ReplenishConfig = {
  salesDaysShort: 15,
  salesDaysLong: 30,
  salesMethod: 'MAX',
  safetyDays: 50,
  q4Months: [10, 11, 12],
  q4Multiplier: 2.0,
  yoyDays: 30,
  includeDomestic: true,
  includePurchasePending: true,
  includeInTransit: true,
  includeOverseas: true,
  minSuggestQty: 50,
  minOrderQty: 100,
  aiEvaluate: '启用',
  aiBatchSize: 20,
  aiTimeoutMs: 30000,
  notifyDay: '周日',
  isActive: '启用',
};

function toBool(v: string, dft: boolean): boolean {
  const s = v.trim().toUpperCase();
  if (['TRUE', '1', '是', '启用', 'Y', 'YES'].includes(s)) return true;
  if (['FALSE', '0', '否', '停用', 'N', 'NO'].includes(s)) return false;
  return dft;
}
function toNum(v: string, dft: number): number {
  const n = Number(v.trim());
  return Number.isFinite(n) ? n : dft;
}
function toMonths(v: string, dft: number[]): number[] {
  const arr = v.split(/[,，、\s]+/).map((x) => Number(x.trim())).filter((n) => Number.isFinite(n) && n >= 1 && n <= 12);
  return arr.length ? arr : dft;
}

/** 读取 FyeDgo 配置；offline/失败回退默认值。 */
export function loadReplenishConfig(writer?: FeishuSheetWriter): ReplenishConfig {
  if (!writer) return { ...DEFAULTS };
  try {
    const rows = writer.readValues({ spreadsheetToken: PMC_SPREADSHEET_TOKEN, sheetId: REPLENISH_SHEET_ID, range: 'A1:B60' });
    const kv = new Map<string, string>();
    for (const row of rows) {
      const k = String(row[0] ?? '').trim();
      const v = String(row[1] ?? '').trim();
      if (k) kv.set(k, v);
    }
    const g = (k: string) => kv.get(k) ?? '';
    const cfg: ReplenishConfig = {
      salesDaysShort: toNum(g('sales_days_short'), DEFAULTS.salesDaysShort),
      salesDaysLong: toNum(g('sales_days_long'), DEFAULTS.salesDaysLong),
      salesMethod: g('sales_method') || DEFAULTS.salesMethod,
      safetyDays: toNum(g('safety_days'), DEFAULTS.safetyDays),
      q4Months: toMonths(g('q4_months'), DEFAULTS.q4Months),
      q4Multiplier: toNum(g('q4_multiplier'), DEFAULTS.q4Multiplier),
      yoyDays: toNum(g('yoy_days'), DEFAULTS.yoyDays),
      includeDomestic: toBool(g('include_domestic'), DEFAULTS.includeDomestic),
      includePurchasePending: toBool(g('include_purchase_pending'), DEFAULTS.includePurchasePending),
      includeInTransit: toBool(g('include_in_transit'), DEFAULTS.includeInTransit),
      includeOverseas: toBool(g('include_overseas'), DEFAULTS.includeOverseas),
      minSuggestQty: toNum(g('min_suggest_qty'), DEFAULTS.minSuggestQty),
      minOrderQty: toNum(g('min_order_qty'), DEFAULTS.minOrderQty),
      aiEvaluate: g('ai_evaluate') || DEFAULTS.aiEvaluate,
      aiBatchSize: toNum(g('ai_batch_size'), DEFAULTS.aiBatchSize),
      aiTimeoutMs: toNum(g('ai_timeout_ms'), DEFAULTS.aiTimeoutMs),
      notifyDay: g('notify_day') || DEFAULTS.notifyDay,
      isActive: g('is_active') || DEFAULTS.isActive,
    };
    logger.info(`[replenishConfig] 已从 FyeDgo 读取（is_active=${cfg.isActive}, ai_evaluate=${cfg.aiEvaluate}, safety_days=${cfg.safetyDays}）`);
    return cfg;
  } catch (e) {
    logger.warn(`[replenishConfig] 读取失败，使用默认值：${e instanceof Error ? e.message : String(e)}`);
    return { ...DEFAULTS };
  }
}
