/**
 * pmcRule.test.ts - PMC 补货建议单元测试
 * 运行：npx ts-node src/notifyRules/pmcRule.test.ts
 */
import * as assert from "assert";
import { replenishSuggestion, riskLevel } from "./pmcRule";

let passed = 0;
let failed = 0;
function t(name: string, fn: () => void): void {
  try { fn(); passed += 1; console.log(`  ✅ ${name}`); }
  catch (e) { failed += 1; console.error(`  ❌ ${name}: ${e instanceof Error ? e.message : String(e)}`); }
}

t("70天目标：日销3.1 库存18 → 建议补 199（ceil(217-18)）", () => {
  const r = replenishSuggestion({ stock: 18, inbound: 0, purchased: 0, daily7: 3.1, isClearance: false });
  assert.strictEqual(r.qty, Math.ceil(3.1 * 70 - 18));
  assert.ok(r.label.includes("建议补") && r.label.includes("70天目标"));
  assert.strictEqual(r.daysToSell, 6);
});

t("断货有销量 → 立即补", () => {
  const r = replenishSuggestion({ stock: 0, inbound: 0, purchased: 0, daily7: 1.4, isClearance: false });
  assert.strictEqual(r.qty, 98);
  assert.ok(r.label.startsWith("立即补 98 件"));
});

t("在途+采购覆盖 → 暂不需补并给覆盖天数", () => {
  const r = replenishSuggestion({ stock: 96, inbound: 40, purchased: 200, daily7: 4.2, isClearance: false });
  assert.strictEqual(r.qty, 0);
  assert.ok(r.label.includes("暂不需补") && r.label.includes(`${Math.round(336 / 4.2)} 天`));
});

t("清货期无任何建议；日销0无建议", () => {
  assert.strictEqual(replenishSuggestion({ stock: 213, inbound: 0, purchased: 0, daily7: 0.9, isClearance: true }).label, "");
  assert.strictEqual(replenishSuggestion({ stock: 50, inbound: 0, purchased: 0, daily7: 0, isClearance: false }).label, "");
});

t("targetDays 参数可调（45天）", () => {
  const r = replenishSuggestion({ stock: 10, inbound: 0, purchased: 0, daily7: 2, isClearance: false, targetDays: 45 });
  assert.strictEqual(r.qty, 80);
});

t("风险分层：已断货/≤7天/≤14天/积压/健康/清货中/无动销", () => {
  assert.strictEqual(riskLevel(0, 1.4, false), "已断货");
  assert.strictEqual(riskLevel(18, 3.1, false), "≤7天");
  assert.strictEqual(riskLevel(40, 3.1, false), "≤14天");
  assert.strictEqual(riskLevel(400, 1, false), "积压");
  assert.strictEqual(riskLevel(96, 4.2, false), "健康");
  assert.strictEqual(riskLevel(213, 0.9, true), "清货中");
  assert.strictEqual(riskLevel(50, 0, false), "无动销");
});

console.log(`\n结果: ${passed} 通过, ${failed} 失败`);
if (failed > 0) process.exit(1);
