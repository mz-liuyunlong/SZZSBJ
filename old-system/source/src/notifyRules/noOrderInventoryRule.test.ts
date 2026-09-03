/**
 * noOrderInventoryRule.test.ts - 不出单通报库存规则 单元测试
 *
 * 运行：npx ts-node src/notifyRules/noOrderInventoryRule.test.ts
 * 纯函数测试，不调用领星 API、不调用飞书接口、不连数据库。
 */

import * as assert from "assert";
import {
  toSafeQty,
  buildInventorySnapshot,
  shouldIncludeInNoOrderNotify,
  classifyNoOrderGroup,
} from "./noOrderInventoryRule";

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

/**
 * 模拟 noOrderNotify.classifyProducts 的过滤顺序（与脚本一致）：
 * 1) 总可售 <= 0 → 不通报（原规则）
 * 2) shouldIncludeInNoOrderNotify=false → 不通报（新规则）
 * 3) 其余 → 按原不出单判断（本函数返回 true 表示"进入原规则判定"）
 */
function passesInventoryGate(raw: Record<string, unknown>): boolean {
  const inv = buildInventorySnapshot(raw);
  if (inv.totalAvailableQty <= 0) return false;
  return shouldIncludeInNoOrderNotify(inv);
}

console.log("── toSafeQty 安全转换（禁止 NaN）──");

t("null/undefined/空串/非数字 → 0", () => {
  assert.strictEqual(toSafeQty(null), 0);
  assert.strictEqual(toSafeQty(undefined), 0);
  assert.strictEqual(toSafeQty(""), 0);
  assert.strictEqual(toSafeQty("  "), 0);
  assert.strictEqual(toSafeQty("abc"), 0);
  assert.strictEqual(toSafeQty(NaN), 0);
  assert.strictEqual(toSafeQty(Infinity), 0);
  assert.strictEqual(toSafeQty({}), 0);
});

t("正常数值与数字字符串", () => {
  assert.strictEqual(toSafeQty(5), 5);
  assert.strictEqual(toSafeQty("12"), 12);
  assert.strictEqual(toSafeQty("0"), 0);
});

t("任何输入都不产生 NaN", () => {
  for (const v of [null, undefined, "", "x", {}, [], NaN, "1a"]) {
    assert.ok(!Number.isNaN(toSafeQty(v)));
  }
});

console.log("── 需求用例矩阵（WFS / 非WFS → 是否进入通报）──");

t("WFS=0, 非WFS=0 → 不通报", () => {
  assert.strictEqual(passesInventoryGate({ wfs_available_quantity: 0, available_quantity: 0 }), false);
});

t("WFS=0, 非WFS=1 → 不通报", () => {
  assert.strictEqual(passesInventoryGate({ wfs_available_quantity: 0, available_quantity: 1 }), false);
});

t("WFS=0, 非WFS=2 → 按原规则通报", () => {
  assert.strictEqual(passesInventoryGate({ wfs_available_quantity: 0, available_quantity: 2 }), true);
});

t("WFS=1, 非WFS=0 → 按原规则通报", () => {
  assert.strictEqual(passesInventoryGate({ wfs_available_quantity: 1, available_quantity: 0 }), true);
});

t("WFS=20, 非WFS=0 → 按原规则通报", () => {
  assert.strictEqual(passesInventoryGate({ wfs_available_quantity: 20, available_quantity: 0 }), true);
});

t("WFS=null, 非WFS=1 → 不通报", () => {
  assert.strictEqual(passesInventoryGate({ wfs_available_quantity: null, available_quantity: 1 }), false);
});

t("WFS=undefined, 非WFS=2 → 按原规则通报", () => {
  assert.strictEqual(passesInventoryGate({ available_quantity: 2 }), true);
});

t("WFS=非数字, 非WFS=非数字 → 不通报", () => {
  assert.strictEqual(passesInventoryGate({ wfs_available_quantity: "abc", available_quantity: "xyz" }), false);
});

console.log("── buildInventorySnapshot 结构化字段 ──");

t("拆分字段与合计正确", () => {
  const inv = buildInventorySnapshot({ wfs_available_quantity: 3, available_quantity: "2" });
  assert.strictEqual(inv.wfsAvailableQty, 3);
  assert.strictEqual(inv.nonWfsAvailableQty, 2);
  assert.strictEqual(inv.totalAvailableQty, 5);
});

t("inbound/warehouse 仅在 API 返回时透传", () => {
  const withFields = buildInventorySnapshot({
    wfs_available_quantity: 0,
    available_quantity: 0,
    inbound_stock: "7",
    warehouse_stock: 4,
  });
  assert.strictEqual(withFields.inboundQty, 7);
  assert.strictEqual(withFields.warehouseQty, 4);

  const withoutFields = buildInventorySnapshot({ wfs_available_quantity: 0, available_quantity: 0 });
  assert.strictEqual(withoutFields.inboundQty, undefined);
  assert.strictEqual(withoutFields.warehouseQty, undefined);
});

console.log("── 近 3/5/7 天互斥分类（口径不变）──");

t("7 天无单 → 7（最高优先）", () => {
  assert.strictEqual(classifyNoOrderGroup({ orders7: 0, orders5: 0, orders3: 0 }), 7);
});

t("7 天有单、5 天无单 → 5", () => {
  assert.strictEqual(classifyNoOrderGroup({ orders7: 2, orders5: 0, orders3: 0 }), 5);
});

t("5 天有单、3 天无单 → 3", () => {
  assert.strictEqual(classifyNoOrderGroup({ orders7: 3, orders5: 1, orders3: 0 }), 3);
});

t("近 3 天有单 → null（不通报）", () => {
  assert.strictEqual(classifyNoOrderGroup({ orders7: 5, orders5: 3, orders3: 1 }), null);
});

t("互斥性：一个产品只落一个分组", () => {
  const groups = [
    classifyNoOrderGroup({ orders7: 0, orders5: 0, orders3: 0 }),
    classifyNoOrderGroup({ orders7: 1, orders5: 0, orders3: 0 }),
    classifyNoOrderGroup({ orders7: 1, orders5: 1, orders3: 0 }),
  ];
  assert.deepStrictEqual(groups, [7, 5, 3]);
});

console.log(`\n结果：通过 ${passed}，失败 ${failed}`);
if (failed > 0) process.exit(1);
