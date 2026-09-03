/**
 * orderDropRule.test.ts - 订单异常下滑规则单元测试
 * 运行：npx ts-node src/notifyRules/orderDropRule.test.ts
 * 纯函数测试，零外部调用。
 */

import * as assert from "assert";
import { evaluateOrderDrop, isRecovered, streakLabel, buildOwnerMessage } from "./orderDropRule";

let passed = 0;
let failed = 0;
function t(name: string, fn: () => void): void {
  try {
    fn();
    passed += 1;
    console.log(`  ✅ ${name}`);
  } catch (e) {
    failed += 1;
    console.error(`  ❌ ${name}: ${e instanceof Error ? e.message : String(e)}`);
  }
}

console.log("── 需求方原始示例 ──");

t("示例1：18/20/16 均18，当日6 → 触发（降66.7%）", () => {
  const d = evaluateOrderDrop({ baseline: [18, 20, 16], current: 6 });
  assert.strictEqual(d.alert, true);
  assert.strictEqual(d.band, "10to30");
  assert.strictEqual(d.dropPct, 0.67);
});

t("示例2：4/5/3 均4，当日1 → 触发", () => {
  const d = evaluateOrderDrop({ baseline: [4, 5, 3], current: 1 });
  assert.strictEqual(d.alert, true);
  assert.strictEqual(d.band, "3to5");
});

t("示例3：2/1/2 均1.67，当日0（首日）→ 不触发（低量档需连续3天）", () => {
  const d = evaluateOrderDrop({ baseline: [2, 1, 2], current: 0, zeroStreak: 1 });
  assert.strictEqual(d.alert, false);
  assert.strictEqual(d.band, "1to3");
});

console.log("── 低量档 1~2.99：连续3天0单 ──");

t("断单前基线 2/1/3（均2），连续3天0单 → 触发 zero_streak", () => {
  const d = evaluateOrderDrop({ baseline: [2, 1, 3], current: 0, zeroStreak: 3 });
  assert.strictEqual(d.alert, true);
  assert.strictEqual(d.reason, "zero_streak");
});

t("连续2天0单 → 未到3天不触发", () => {
  const d = evaluateOrderDrop({ baseline: [2, 1, 3], current: 0, zeroStreak: 2 });
  assert.strictEqual(d.alert, false);
});

t("日均<1（1/0/1）连续3天0单 → 仍不提醒（不出单通报兜底）", () => {
  const d = evaluateOrderDrop({ baseline: [1, 0, 1], current: 0, zeroStreak: 3 });
  assert.strictEqual(d.alert, false);
  assert.strictEqual(d.band, "lt1");
});

console.log("── 各档触发边界 ──");

t("3~4.99档：当日2单不触发，当日1单触发", () => {
  assert.strictEqual(evaluateOrderDrop({ baseline: [4, 4, 4], current: 2 }).alert, false);
  assert.strictEqual(evaluateOrderDrop({ baseline: [4, 4, 4], current: 1 }).alert, true);
});

t("5~9.99档真实边界：均9.9当日3（降69.7%）不触发；当日2触发", () => {
  // 整数订单下"降≥70%"必然伴随当日≤2，两个条件在实数据里重合——保留OR分支无害
  const d3 = evaluateOrderDrop({ baseline: [10, 10, 9.7] as number[], current: 3 });
  assert.strictEqual(d3.band, "5to10");
  assert.strictEqual(d3.alert, false);
  const d2 = evaluateOrderDrop({ baseline: [10, 10, 9.7] as number[], current: 2 });
  assert.strictEqual(d2.alert, true);
});

t("5~9.99档：当日2单直接触发", () => {
  assert.strictEqual(evaluateOrderDrop({ baseline: [6, 5, 7], current: 2 }).alert, true);
});

t("10~29.99档：降50%但只减4单（均8？不，均12→8）→ 不触发（差额不足5）", () => {
  // 均12，当日8：降33%不足50% → 不触发；构造精确用例：均10，当日5=降50%减5单→触发
  assert.strictEqual(evaluateOrderDrop({ baseline: [10, 10, 10], current: 5 }).alert, true);
  // 均10，当日6=降40% → 不触发
  assert.strictEqual(evaluateOrderDrop({ baseline: [10, 10, 10], current: 6 }).alert, false);
});

t("30~49.99档：均40当日25（降37.5%减15单）→ 触发", () => {
  const d = evaluateOrderDrop({ baseline: [42, 38, 40], current: 25 });
  assert.strictEqual(d.band, "30to50");
  assert.strictEqual(d.alert, true);
});

t("30~49.99档：均40当日30（降25%）→ 不触发", () => {
  assert.strictEqual(evaluateOrderDrop({ baseline: [40, 40, 40], current: 30 }).alert, false);
});

t("≥50档：均60当日40（降33%减20单）→ 触发", () => {
  const d = evaluateOrderDrop({ baseline: [58, 62, 60], current: 40 });
  assert.strictEqual(d.band, "ge50");
  assert.strictEqual(d.alert, true);
});

t("≥50档：均60当日45（降25%）→ 不触发", () => {
  assert.strictEqual(evaluateOrderDrop({ baseline: [60, 60, 60], current: 45 }).alert, false);
});

t("上涨/持平永不触发", () => {
  assert.strictEqual(evaluateOrderDrop({ baseline: [10, 10, 10], current: 15 }).alert, false);
  assert.strictEqual(evaluateOrderDrop({ baseline: [10, 10, 10], current: 10 }).alert, false);
});

t("基线不足3天（新品）→ 不判定", () => {
  const d = evaluateOrderDrop({ baseline: [8, 9], current: 0 });
  assert.strictEqual(d.alert, false);
  assert.strictEqual(d.band, "insufficient");
});

t("非法值安全：NaN/负数按0处理不炸", () => {
  const d = evaluateOrderDrop({ baseline: [NaN as number, 10, 20], current: Number("x") });
  assert.ok(typeof d.avg === "number" && !Number.isNaN(d.avg));
});

console.log("── 恢复判定与连续状态 ──");

t("恢复：当日≥均值70%关闭；未达不关闭", () => {
  assert.strictEqual(isRecovered([10, 10, 10], 7), true);
  assert.strictEqual(isRecovered([10, 10, 10], 6), false);
});

t("streakLabel：1天=首次异常，3天=连续第3天异常", () => {
  assert.strictEqual(streakLabel(1), "首次异常");
  assert.strictEqual(streakLabel(3), "连续第3天异常");
});

console.log("── 通报文案（无等级，仅事实）──");

t("按负责人汇总文案要素齐全，且不含等级词", () => {
  const msg = buildOwnerMessage("刘华媛", "2026-07-15", [
    { itemId: "19051502014", storeName: "CN2501", msku: "YC00019-1U", productName: "",
      baseline: [18, 20, 16], current: 6, avg: 18, dropPct: 0.667, reason: "drop", consecutiveDays: 2 },
    { itemId: "20115156254", storeName: "CN2601", msku: "JJ7619-1A", productName: "粉色浴巾",
      baseline: [2, 1, 3], current: 0, avg: 2, dropPct: 1, reason: "zero_streak", consecutiveDays: 3 },
  ]);
  assert.ok(msg.includes("数据日期：2026-07-15"));
  assert.ok(msg.includes("异常产品：2个"));
  assert.ok(msg.includes("18 / 20 / 16（日均18）→ 当日：6　↓66.7%"));
  assert.ok(msg.includes("连续第2天异常"));
  assert.ok(msg.includes("连续3天 0 单"));
  assert.ok(!msg.includes("一般异常") && !msg.includes("严重") && !msg.includes("断单异常"));
});

console.log(`\n结果：通过 ${passed}，失败 ${failed}`);
if (failed > 0) process.exit(1);
