/**
 * wfsArrivalRule.test.ts - WFS到货提醒规则单元测试
 * 运行：npx ts-node src/notifyRules/wfsArrivalRule.test.ts
 * 纯函数测试，零外部调用。
 */

import * as assert from "assert";
import {
  parseEpochToCstDateTime,
  parseApiDateTime,
  detectShipmentTransitions,
  detectStockFirstAvailable,
  evaluateNoAds,
  buildClosedText,
  buildEscalationText,
  WFS_STATUS,
} from "./wfsArrivalRule";

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

console.log("── parseEpochToCstDateTime（probe实测：epoch毫秒字符串 / \"0\"）──");

t("epoch毫秒字符串 → 上海datetime", () => {
  // 1784036344637 = 2026-07-14T13:39:04.637Z = 上海 2026-07-14 21:39:04
  assert.strictEqual(parseEpochToCstDateTime("1784036344637"), "2026-07-14 21:39:04");
});

t('"0" / 空 / null → null（未到达状态）', () => {
  assert.strictEqual(parseEpochToCstDateTime("0"), null);
  assert.strictEqual(parseEpochToCstDateTime(""), null);
  assert.strictEqual(parseEpochToCstDateTime(null), null);
  assert.strictEqual(parseEpochToCstDateTime(undefined), null);
});

t("epoch秒(10位)兼容", () => {
  assert.strictEqual(parseEpochToCstDateTime("1784036344"), "2026-07-14 21:39:04");
});

t("datetime字符串透传；垃圾值 → null", () => {
  assert.strictEqual(parseEpochToCstDateTime("2026-07-13 01:44:08"), "2026-07-13 01:44:08");
  assert.strictEqual(parseEpochToCstDateTime("abc"), null);
  assert.strictEqual(parseEpochToCstDateTime("12345"), null);
});

t("parseApiDateTime 校验透传", () => {
  assert.strictEqual(parseApiDateTime("2026-07-14 21:39:04"), "2026-07-14 21:39:04");
  assert.strictEqual(parseApiDateTime("2026-07-14"), null);
  assert.strictEqual(parseApiDateTime(null), null);
});

console.log("── R1 状态跃迁 ──");

t("1→2 触发 receiving", () => {
  assert.deepStrictEqual(detectShipmentTransitions(WFS_STATUS.AWAITING, WFS_STATUS.RECEIVING), ["receiving"]);
});

t("2→3 触发 closed", () => {
  assert.deepStrictEqual(detectShipmentTransitions(WFS_STATUS.RECEIVING, WFS_STATUS.CLOSED), ["closed"]);
});

t("首见即2 → receiving；首见即3 → 只报closed", () => {
  assert.deepStrictEqual(detectShipmentTransitions(null, WFS_STATUS.RECEIVING), ["receiving"]);
  assert.deepStrictEqual(detectShipmentTransitions(null, WFS_STATUS.CLOSED), ["closed"]);
});

t("状态不变/回退/取消 → 无事件", () => {
  assert.deepStrictEqual(detectShipmentTransitions(2, 2), []);
  assert.deepStrictEqual(detectShipmentTransitions(3, 3), []);
  assert.deepStrictEqual(detectShipmentTransitions(3, 2), []);
  assert.deepStrictEqual(detectShipmentTransitions(1, WFS_STATUS.CANCELLED), []);
  assert.deepStrictEqual(detectShipmentTransitions(null, WFS_STATUS.AWAITING), []);
});

console.log("── R2 库存 0→非0 ──");

t("0→3 触发；0→0 不触发；5→8 不触发", () => {
  assert.strictEqual(detectStockFirstAvailable(0, 3), true);
  assert.strictEqual(detectStockFirstAvailable(0, 0), false);
  assert.strictEqual(detectStockFirstAvailable(5, 8), false);
});

t("上一快照无行(null)且当前>0 → 触发", () => {
  assert.strictEqual(detectStockFirstAvailable(null, 2), true);
  assert.strictEqual(detectStockFirstAvailable(null, 0), false);
});

console.log("── R3/R4 无广告判定（锚点=可售日，T-2护栏）──");

const base = { sellableDate: "2026-07-10", adSpendSum: 0, impressionsSum: 0, alreadyEscalated: false };

t("数据未覆盖可售日 → 不提醒不升级（护栏）", () => {
  const d = evaluateNoAds({ ...base, latestAdDataDate: "2026-07-09" });
  assert.deepStrictEqual([d.remind, d.escalate, d.resolved], [false, false, false]);
});

t("覆盖1天无广告 → 日常提醒，不升级", () => {
  const d = evaluateNoAds({ ...base, latestAdDataDate: "2026-07-10" });
  assert.strictEqual(d.remind, true);
  assert.strictEqual(d.escalate, false);
  assert.strictEqual(d.noAdsDays, 1);
});

t("覆盖2天无广告 → 提醒，不升级", () => {
  const d = evaluateNoAds({ ...base, latestAdDataDate: "2026-07-11" });
  assert.deepStrictEqual([d.remind, d.escalate, d.noAdsDays], [true, false, 2]);
});

t("第3个数据日仍无广告 → 提醒+升级（R4）", () => {
  const d = evaluateNoAds({ ...base, latestAdDataDate: "2026-07-12" });
  assert.deepStrictEqual([d.remind, d.escalate, d.noAdsDays], [true, true, 3]);
});

t("已升级过 → 不重复升级，日常提醒继续", () => {
  const d = evaluateNoAds({ ...base, latestAdDataDate: "2026-07-13", alreadyEscalated: true });
  assert.deepStrictEqual([d.remind, d.escalate, d.noAdsDays], [true, false, 4]);
});

t("严格口径：已创建广告(有报表行)但0投放 → 日常提醒继续、不升级不扣绩效", () => {
  const d = evaluateNoAds({ ...base, latestAdDataDate: "2026-07-12", adRowCount: 6 });
  assert.deepStrictEqual([d.remind, d.escalate, d.noAdsDays], [true, false, 3]);
});

t("严格口径：未创建广告(无报表行)满3天 → 升级扣绩效", () => {
  const d = evaluateNoAds({ ...base, latestAdDataDate: "2026-07-12", adRowCount: 0 });
  assert.strictEqual(d.escalate, true);
});

t("出现广告花费或曝光 → resolved，全部停止", () => {
  const d1 = evaluateNoAds({ ...base, latestAdDataDate: "2026-07-12", adSpendSum: 0.5 });
  const d2 = evaluateNoAds({ ...base, latestAdDataDate: "2026-07-12", impressionsSum: 10 });
  assert.deepStrictEqual([d1.resolved, d1.remind, d1.escalate], [true, false, false]);
  assert.deepStrictEqual([d2.resolved, d2.remind, d2.escalate], [true, false, false]);
});

t("超过提醒上限 → 停止日常提醒，升级仍可发（若未发过）", () => {
  const d = evaluateNoAds({ ...base, latestAdDataDate: "2026-08-15", maxRemindDays: 30 });
  assert.strictEqual(d.remind, false);
  assert.strictEqual(d.escalate, true);
});

t("非法可售日 → 全否（配置异常防御）", () => {
  const d = evaluateNoAds({ ...base, sellableDate: "bad", latestAdDataDate: "2026-07-12" });
  assert.deepStrictEqual([d.remind, d.escalate, d.resolved], [false, false, false]);
});

console.log("── 文案 ──");

t("接收完成文案含差异标记", () => {
  const text = buildClosedText({
    storeName: "CN2501-掌上便捷", cargoCode: "9500168WFA", inboundOrderId: "WMS-1", eventTime: "2026-07-14 10:00:00",
    goods: [
      { msku: "JJ8021-1A", productName: "牛油刀套装", declareNum: 100, receivedNum: 98, damagedQty: 1, owner: "张三" },
      { msku: "JJ8022-1A", productName: "测试品", declareNum: 50, receivedNum: 50, damagedQty: 0, owner: "李四" },
    ],
  });
  assert.ok(text.includes("接收完成"));
  assert.ok(text.includes("100/98/1 ⚠️差异"));
  assert.ok(text.includes("50/50/0 负责人：李四"));
});

t("升级文案含绩效口径与要素", () => {
  const text = buildEscalationText({
    storeName: "CN2501", msku: "JJ8021-1A", productName: "牛油刀套装", owner: "张三",
    sellableDate: "2026-07-10", noAdsDays: 3, dataThrough: "2026-07-12",
  });
  assert.ok(text.includes("绩效考核口径"));
  assert.ok(text.includes("满 3 天"));
  assert.ok(text.includes("负责人：张三"));
  assert.ok(text.includes("数据截至：2026-07-12"));
});

console.log(`\n结果：通过 ${passed}，失败 ${failed}`);
if (failed > 0) process.exit(1);
