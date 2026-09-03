/**
 * adGroupSilenceRule.ts - 广告组静默提醒规则（纯函数模块）
 *
 * 需求（2026-07-15 需求方追加，归入广告通报）：
 *   R5：广告组连续 5 个数据日 花费=0 且 曝光=0 → 提醒
 *   R6：广告组连续 7 个数据日 花费=0（曝光可>0）→ 提醒
 *
 * 数据说明：fact_ads_product_daily 为报表型数据，某广告组某日无行时按 0 处理
 * （调用方必须先把缺失日补 0 后再传入）；广告组"存在"锚点 = 近30个数据日内出现过行。
 * 连续天数从最新数据日往回数，中断即停。
 */

import { toSafeQty } from "./noOrderInventoryRule";

export interface AdGroupDayStat {
  /** YYYY-MM-DD，调用方保证升序且连续（缺失日已补0） */
  statDate: string;
  adSpend: number;
  impressions: number;
}

export interface AdGroupSilenceDecision {
  /** 自最新数据日起连续 花费=0且曝光=0 的天数 */
  silentDays: number;
  /** 自最新数据日起连续 花费=0 的天数 */
  noSpendDays: number;
  /** R5：silentDays >= silentThreshold(默认5) */
  silentAlert: boolean;
  /** R6：noSpendDays >= noSpendThreshold(默认7) */
  noSpendAlert: boolean;
  /** 静默连续段起始日（幂等 biz_key 用；无静默为 null） */
  silentStreakStart: string | null;
  /** 零花费连续段起始日 */
  noSpendStreakStart: string | null;
}

export function evaluateAdGroupSilence(
  days: AdGroupDayStat[],
  opts?: {
    silentThreshold?: number;
    noSpendThreshold?: number;
    /**
     * 新鲜度上限（2026-07-15 生产校准：首跑dry-run候选230条，全是存量陈旧静默段）。
     * 只报"刚跨过阈值"的段：连续天数 > 阈值+freshGrace 视为陈旧不报。默认5。
     */
    freshGrace?: number;
  },
): AdGroupSilenceDecision {
  const silentThreshold = opts?.silentThreshold ?? 5;
  const noSpendThreshold = opts?.noSpendThreshold ?? 7;
  const freshGrace = opts?.freshGrace ?? 5;

  let silentDays = 0;
  let noSpendDays = 0;
  let silentStreakStart: string | null = null;
  let noSpendStreakStart: string | null = null;
  let silentBroken = false;
  let noSpendBroken = false;

  // 从最新往回数连续段
  for (let i = days.length - 1; i >= 0; i--) {
    const d = days[i];
    const spend = toSafeQty(d.adSpend);
    const impr = toSafeQty(d.impressions);

    if (!noSpendBroken) {
      if (spend === 0) {
        noSpendDays += 1;
        noSpendStreakStart = d.statDate;
      } else {
        noSpendBroken = true;
      }
    }
    if (!silentBroken) {
      if (spend === 0 && impr === 0) {
        silentDays += 1;
        silentStreakStart = d.statDate;
      } else {
        silentBroken = true;
      }
    }
    if (silentBroken && noSpendBroken) break;
  }

  return {
    silentDays,
    noSpendDays,
    silentAlert: silentDays >= silentThreshold && silentDays <= silentThreshold + freshGrace,
    noSpendAlert: noSpendDays >= noSpendThreshold && noSpendDays <= noSpendThreshold + freshGrace,
    silentStreakStart: silentDays > 0 ? silentStreakStart : null,
    noSpendStreakStart: noSpendDays > 0 ? noSpendStreakStart : null,
  };
}

/**
 * "曾活跃"锚点（2026-07-15 生产数据校准）：
 * 生产报表约77%的行常年0花费0曝光（历史死组），字面规则会日产2400+提醒。
 * 因此只对"由活跃转静默"的广告组提醒：静默/零花费连续段开始之前，
 * 序列内存在至少一天 花费>0 或 曝光>0。
 */
export function hadActivityBefore(
  days: AdGroupDayStat[],
  streakStart: string | null,
  /**
   * 活跃紧邻窗口（2026-07-15 收紧）：活跃必须出现在静默段开始前 withinDays 个数据日内，
   * 默认7——30天前偶有一次曝光的不算"活跃转静默"。0 表示不限窗口（旧行为）。
   */
  withinDays = 7,
): boolean {
  if (!streakStart) return false;
  // 序列升序：先收集段前的日期，再检查末尾 withinDays 个
  const before: AdGroupDayStat[] = [];
  for (const d of days) {
    if (d.statDate >= streakStart) break;
    before.push(d);
  }
  const window = withinDays > 0 ? before.slice(-withinDays) : before;
  for (const d of window) {
    if (toSafeQty(d.adSpend) > 0 || toSafeQty(d.impressions) > 0) return true;
  }
  return false;
}

// ── 文案 ─────────────────────────────────────────────────────────────

export interface AdGroupAlertInfo {
  storeName: string;
  campaignName: string;
  adGroupName: string;
  msku: string;         // 关联商品（item级，可为多个MSKU的代表或空）
  productName: string;
  owner: string;
  dataThrough: string;
}

export function buildAdGroupSilentText(p: AdGroupAlertInfo & { silentDays: number }): string {
  return [
    `【广告组静默提醒】连续 ${p.silentDays} 天 0花费且0曝光`,
    `店铺：${p.storeName}`,
    `广告活动：${p.campaignName} / 广告组：${p.adGroupName}`,
    `商品：${p.msku} ${p.productName}`,
    `负责人：${p.owner || "未匹配"}，数据截至：${p.dataThrough}`,
    `广告组疑似停投/预算耗尽/被拒审，请检查投放状态`,
  ].join("\n");
}

export function buildAdGroupNoSpendText(p: AdGroupAlertInfo & { noSpendDays: number }): string {
  return [
    `【广告组零花费提醒】连续 ${p.noSpendDays} 天广告花费为 0`,
    `店铺：${p.storeName}`,
    `广告活动：${p.campaignName} / 广告组：${p.adGroupName}`,
    `商品：${p.msku} ${p.productName}`,
    `负责人：${p.owner || "未匹配"}，数据截至：${p.dataThrough}`,
    `有曝光但持续无花费或完全无消耗，请检查出价/预算设置`,
  ].join("\n");
}
