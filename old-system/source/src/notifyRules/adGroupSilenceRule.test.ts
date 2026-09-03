/**
 * adGroupSilenceRule.test.ts - 广告组静默规则单元测试
 * 运行：npx ts-node src/notifyRules/adGroupSilenceRule.test.ts
 * 纯函数测试，零外部调用。
 */

import * as assert from "assert";
import { evaluateAdGroupSilence, hadActivityBefore, buildAdGroupSilentText, buildAdGroupNoSpendText, AdGroupDayStat } from "./adGroupSilenceRule";

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

/** 构造连续日期序列（7月1日起） */
function days(specs: Array<[number, number]>): AdGroupDayStat[] {
  return specs.map(([spend, impr], i) => ({
    statDate: `2026-07-${String(i + 1).padStart(2, "0")}`,
    adSpend: spend,
    impressions: impr,
  }));
}

console.log("── R5 连续5天 0花费且0曝光 ──");

t("刚好连续5天静默 → silentAlert", () => {
  const d = evaluateAdGroupSilence(days([[5, 100], [0, 0], [0, 0], [0, 0], [0, 0], [0, 0]]));
  assert.strictEqual(d.silentDays, 5);
  assert.strictEqual(d.silentAlert, true);
  assert.strictEqual(d.silentStreakStart, "2026-07-02");
});

t("连续4天静默 → 不提醒", () => {
  const d = evaluateAdGroupSilence(days([[5, 100], [0, 0], [0, 0], [0, 0], [0, 0]]));
  assert.strictEqual(d.silentDays, 4);
  assert.strictEqual(d.silentAlert, false);
});

t("中间有曝光打断 → 从最新重新计数", () => {
  // 最后3天静默，第4天前有曝光
  const d = evaluateAdGroupSilence(days([[0, 0], [0, 0], [0, 50], [0, 0], [0, 0], [0, 0]]));
  assert.strictEqual(d.silentDays, 3);
  assert.strictEqual(d.silentAlert, false);
});

t("最新一天有花费 → 静默为0", () => {
  const d = evaluateAdGroupSilence(days([[0, 0], [0, 0], [0, 0], [0, 0], [0, 0], [3, 10]]));
  assert.strictEqual(d.silentDays, 0);
  assert.strictEqual(d.silentStreakStart, null);
});

console.log("── R6 连续7天 0花费 ──");

t("连续7天0花费（有曝光）→ noSpendAlert，且不触发R5", () => {
  const d = evaluateAdGroupSilence(days([[2, 10], [0, 30], [0, 30], [0, 30], [0, 30], [0, 30], [0, 30], [0, 30]]));
  assert.strictEqual(d.noSpendDays, 7);
  assert.strictEqual(d.noSpendAlert, true);
  assert.strictEqual(d.silentAlert, false);
  assert.strictEqual(d.noSpendStreakStart, "2026-07-02");
});

t("连续6天0花费 → 不提醒", () => {
  const d = evaluateAdGroupSilence(days([[2, 10], [0, 30], [0, 0], [0, 30], [0, 0], [0, 30], [0, 30]]));
  assert.strictEqual(d.noSpendDays, 6);
  assert.strictEqual(d.noSpendAlert, false);
});

t("7天全静默 → R5与R6同时触发", () => {
  const d = evaluateAdGroupSilence(days([[0, 0], [0, 0], [0, 0], [0, 0], [0, 0], [0, 0], [0, 0]]));
  assert.strictEqual(d.silentAlert, true);
  assert.strictEqual(d.noSpendAlert, true);
});

t("阈值可配置", () => {
  const d = evaluateAdGroupSilence(days([[0, 0], [0, 0], [0, 0]]), { silentThreshold: 3, noSpendThreshold: 3 });
  assert.strictEqual(d.silentAlert, true);
  assert.strictEqual(d.noSpendAlert, true);
});

t("空序列/非数字安全（禁止NaN）", () => {
  const d1 = evaluateAdGroupSilence([]);
  assert.deepStrictEqual([d1.silentDays, d1.noSpendDays, d1.silentAlert, d1.noSpendAlert], [0, 0, false, false]);
  const d2 = evaluateAdGroupSilence([{ statDate: "2026-07-01", adSpend: NaN, impressions: Number("x") }]);
  assert.strictEqual(d2.silentDays, 1); // NaN→0，按静默计
});

console.log("── 新鲜度上限（防首跑积压，2026-07-15 生产230条校准）──");

t("静默11天（阈值5+宽限5=10）→ 陈旧不报", () => {
  const d = evaluateAdGroupSilence(days([[5, 100], ...Array(11).fill([0, 0]) as Array<[number, number]>]));
  assert.strictEqual(d.silentDays, 11);
  assert.strictEqual(d.silentAlert, false);
});

t("静默10天（=上限）→ 仍报", () => {
  const d = evaluateAdGroupSilence(days([[5, 100], ...Array(10).fill([0, 0]) as Array<[number, number]>]));
  assert.strictEqual(d.silentAlert, true);
});

t("宽限可配置：grace=0 时仅报恰好跨线段", () => {
  const d6 = evaluateAdGroupSilence(days([[5, 100], ...Array(6).fill([0, 0]) as Array<[number, number]>]), { freshGrace: 0 });
  assert.strictEqual(d6.silentAlert, false); // 6>5+0
  const d5 = evaluateAdGroupSilence(days([[5, 100], ...Array(5).fill([0, 0]) as Array<[number, number]>]), { freshGrace: 0 });
  assert.strictEqual(d5.silentAlert, true);
});

console.log("── 曾活跃锚点（防历史死组轰炸）──");

t("活跃紧邻窗口：活跃在段前8天以上（窗口7）→ 不算活跃转静默", () => {
  // 前10天全0中仅第1天活跃，然后5天静默：活跃距段首>7天
  const series = days([[9, 90], ...Array(9).fill([0, 0]) as Array<[number, number]>]);
  const d = evaluateAdGroupSilence(series);
  // 整段10天静默? 注意第1天有活跃→静默段=后9天，超上限不报；此处直接测 hadActivityBefore 窗口
  assert.strictEqual(hadActivityBefore(series, "2026-07-09", 7), false);
  assert.strictEqual(hadActivityBefore(series, "2026-07-09", 0), true); // 不限窗口时算
  assert.ok(d.silentDays >= 5);
});

t("活跃转静默 → 锚点命中", () => {
  const series = days([[5, 100], [3, 80], [0, 0], [0, 0], [0, 0], [0, 0], [0, 0]]);
  const d = evaluateAdGroupSilence(series);
  assert.strictEqual(d.silentAlert, true);
  assert.strictEqual(hadActivityBefore(series, d.silentStreakStart), true);
});

t("历史死组（全程0）→ 锚点不命中，不提醒", () => {
  const series = days([[0, 0], [0, 0], [0, 0], [0, 0], [0, 0], [0, 0], [0, 0]]);
  const d = evaluateAdGroupSilence(series);
  assert.strictEqual(d.silentAlert, true); // 规则本身命中
  assert.strictEqual(hadActivityBefore(series, d.silentStreakStart), false); // 但锚点过滤
});

t("streakStart为null → 锚点false", () => {
  assert.strictEqual(hadActivityBefore(days([[1, 1]]), null), false);
});

console.log("── 文案 ──");

t("静默文案要素齐全", () => {
  const text = buildAdGroupSilentText({
    storeName: "CN2501", campaignName: "SP-主推", adGroupName: "AG-核心词", msku: "JJ8021-1A",
    productName: "牛油刀套装", owner: "张三", dataThrough: "2026-07-12", silentDays: 5,
  });
  assert.ok(text.includes("连续 5 天 0花费且0曝光"));
  assert.ok(text.includes("SP-主推"));
  assert.ok(text.includes("AG-核心词"));
  assert.ok(text.includes("数据截至：2026-07-12"));
});

t("零花费文案要素齐全", () => {
  const text = buildAdGroupNoSpendText({
    storeName: "CN2501", campaignName: "SP-主推", adGroupName: "AG-核心词", msku: "JJ8021-1A",
    productName: "牛油刀套装", owner: "张三", dataThrough: "2026-07-12", noSpendDays: 7,
  });
  assert.ok(text.includes("连续 7 天广告花费为 0"));
  assert.ok(text.includes("出价/预算"));
});

console.log(`\n结果：通过 ${passed}，失败 ${failed}`);
if (failed > 0) process.exit(1);
