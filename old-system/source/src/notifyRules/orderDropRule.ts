/**
 * orderDropRule.ts - 订单异常下滑判定规则（纯函数模块）
 *
 * 需求定稿 2026-07-16（与需求方逐条确认）：
 *   粒度：店铺+ItemID；指标：订单量（saleStat v2 result_type=2）
 *   基线：近3个完整销售日平均；"当日"=16:25拉取的最新完整美国销售日
 *   分档触发（日均 → 条件）：
 *     <1（3天合计≤2）   不提醒（由既有"不出单通报"兜底）
 *     1~2.99            连续3天0单 → 通报（断单前3日均≥1）
 *     3~4.99            当日≤1单
 *     5~9.99            当日≤2单 或 降≥70%
 *     10~29.99          降≥50% 且 减少≥5单
 *     30~49.99          降≥35% 且 减少≥12单
 *     ≥50               降≥30% 且 减少≥18单
 *   无异常等级（需求方取消）；只报事实：数字+降幅+连续第N天
 *   恢复：当日≥近3日均70% → 状态关闭（不发恢复通知）；不报上涨
 *   剔除：CS测品、归档产品、断货（总可售=0）——由调用方过滤，本模块不管数据源
 *
 * 零外部IO，供 checkOrderDrop.ts / orderDropNotify.ts 与单测共用。
 */

import { toSafeQty } from "./noOrderInventoryRule";

export interface OrderDropInput {
  /** 近3个完整日订单数（旧→新，不含当日）。不足3天传实际长度，判定自动跳过 */
  baseline: number[];
  /** 当日（最新完整日）订单数 */
  current: number;
  /**
   * 含当日的连续0单天数（当日>0时应为0）。
   * 供低量档（日均1~2.99）"连续3天0单"判定；
   * zeroStreak>=3 时 baseline 必须传"断单前"的3个完整日（否则0会拉低基线）。
   */
  zeroStreak?: number;
}

export interface OrderDropDecision {
  alert: boolean;
  /** drop=下滑触发；zero_streak=低量档连续3天0单触发 */
  reason: "drop" | "zero_streak" | null;
  /** 基线日均（保留2位） */
  avg: number;
  /** 下降比例 0~1；基线不足或未触发时可为 null */
  dropPct: number | null;
  /** 命中档位（日志/调参观察用） */
  band: "lt1" | "1to3" | "3to5" | "5to10" | "10to30" | "30to50" | "ge50" | "insufficient";
}

function round2(n: number): number {
  return Math.round(n * 100) / 100;
}

export function evaluateOrderDrop(input: OrderDropInput): OrderDropDecision {
  const baseline = (input.baseline ?? []).map(toSafeQty);
  const current = toSafeQty(input.current);
  const zeroStreak = toSafeQty(input.zeroStreak ?? 0);

  // 基线数据不足3个完整日（新品/数据缺口）：不判定
  if (baseline.length < 3) {
    return { alert: false, reason: null, avg: 0, dropPct: null, band: "insufficient" };
  }

  const sum = baseline.reduce((s, v) => s + v, 0);
  const avg = sum / 3;
  const dropPct = avg > 0 ? Math.max(0, (avg - current) / avg) : null;
  const diff = avg - current;

  // 不报上涨/持平
  const base = { avg: round2(avg), dropPct: dropPct === null ? null : round2(dropPct) };

  // <1：不提醒（3天合计≤2；不出单通报兜底）
  if (avg < 1) {
    return { alert: false, reason: null, band: "lt1", ...base };
  }

  // 1~2.99：仅"连续3天0单"触发（baseline 此时应为断单前3日）
  if (avg < 3) {
    if (zeroStreak >= 3 && current === 0) {
      return { alert: true, reason: "zero_streak", band: "1to3", ...base, dropPct: 1 };
    }
    return { alert: false, reason: null, band: "1to3", ...base };
  }

  // 3~4.99：当日≤1单
  if (avg < 5) {
    return { alert: current <= 1, reason: current <= 1 ? "drop" : null, band: "3to5", ...base };
  }

  // 5~9.99：当日≤2单 或 降≥70%
  if (avg < 10) {
    const hit = current <= 2 || (dropPct !== null && dropPct >= 0.7);
    return { alert: hit, reason: hit ? "drop" : null, band: "5to10", ...base };
  }

  // 10~29.99：降≥50% 且 减少≥5单
  if (avg < 30) {
    const hit = dropPct !== null && dropPct >= 0.5 && diff >= 5;
    return { alert: hit, reason: hit ? "drop" : null, band: "10to30", ...base };
  }

  // 30~49.99：降≥35% 且 减少≥12单
  if (avg < 50) {
    const hit = dropPct !== null && dropPct >= 0.35 && diff >= 12;
    return { alert: hit, reason: hit ? "drop" : null, band: "30to50", ...base };
  }

  // ≥50：降≥30% 且 减少≥18单
  const hit = dropPct !== null && dropPct >= 0.3 && diff >= 18;
  return { alert: hit, reason: hit ? "drop" : null, band: "ge50", ...base };
}

/** 恢复判定：当日 ≥ 近3日均的70% → 关闭异常状态（不发恢复通知） */
export function isRecovered(baseline: number[], current: number): boolean {
  const b = (baseline ?? []).map(toSafeQty);
  if (b.length < 3) return false;
  const avg = b.reduce((s, v) => s + v, 0) / 3;
  if (avg <= 0) return true; // 基线归零无从谈恢复，直接关闭防僵尸状态
  return toSafeQty(current) >= 0.7 * avg;
}

/** 连续异常天数 → 展示文案（不是等级，是去重与持续跟踪的状态事实） */
export function streakLabel(consecutiveDays: number): string {
  const d = Math.max(1, Math.floor(toSafeQty(consecutiveDays)));
  return d === 1 ? "首次异常" : `连续第${d}天异常`;
}

// ── 通报文案 ─────────────────────────────────────────────────────────

export interface OrderDropItemInfo {
  itemId: string;
  storeName: string;
  msku: string;
  productName: string;
  baseline: number[];
  current: number;
  avg: number;
  dropPct: number | null;
  reason: "drop" | "zero_streak";
  consecutiveDays: number;
}

export function buildItemLine(no: number, p: OrderDropItemInfo): string {
  const head = `${no}. ItemID：${p.itemId} ｜ 店铺：${p.storeName} ｜ MSKU：${p.msku}${p.productName ? ` ${p.productName}` : ""}`;
  const baseTxt = p.baseline.join(" / ");
  const body = p.reason === "zero_streak"
    ? `   近3天订单：${baseTxt}（日均${p.avg}）→ 连续${p.consecutiveDays >= 3 ? p.consecutiveDays : 3}天 0 单`
    : `   近3天订单：${baseTxt}（日均${p.avg}）→ 当日：${p.current}　↓${p.dropPct !== null ? (p.dropPct * 100).toFixed(1) : "?"}%`;
  const streak = `   ${streakLabel(p.consecutiveDays)}`;
  return [head, body, streak].join("\n");
}

export function buildOwnerMessage(ownerName: string, dataDate: string, items: OrderDropItemInfo[]): string {
  const lines = [
    `【订单异常下滑提醒】`,
    `数据日期：${dataDate}`,
    `负责人：${ownerName || "未匹配"}`,
    `异常产品：${items.length}个`,
    ``,
  ];
  items.forEach((p, i) => {
    lines.push(buildItemLine(i + 1, p));
    if (i < items.length - 1) lines.push("");
  });
  return lines.join("\n");
}
