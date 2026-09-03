/**
 * reminderCards.test.ts - 提醒卡片构建单元测试
 * 运行：npx ts-node src/notifyRules/reminderCards.test.ts
 * 纯函数测试，零外部调用。
 */

import * as assert from "assert";
import { buildRuleSignalCard, buildUnmatchedOwnerCard, buildOrderDropCard, buildOpsInactionCard, buildClearanceApprovalCard, buildClearanceTailCard, buildClearanceArchiveCard, buildClearanceReviveCard, levelBadge, RuleSignalItem, UnmatchedOwnerItem, OrderDropCardItem, OpsInactionCardItem, ClearanceApprovalItem } from "./reminderCards";

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

function sig(p: Partial<RuleSignalItem>): RuleSignalItem {
  return {
    owner: "曾洁茹", storeName: "HK2612-张李华", itemId: "20598811962", msku: "YC00081-1A",
    ruleLevel: "warn", ruleName: "断货风险", triggerReason: "可售<3天", suggestedAction: "尽快补货",
    isNew: false, ...p,
  };
}

console.log("── levelBadge ──");
t("high/严重→🔴, warn→🟡, info→🔵, 其他→▫️", () => {
  assert.strictEqual(levelBadge("high"), "🔴");
  assert.strictEqual(levelBadge("严重"), "🔴");
  assert.strictEqual(levelBadge("warn"), "🟡");
  assert.strictEqual(levelBadge("info"), "🔵");
  assert.strictEqual(levelBadge(""), "▫️");
});

console.log("── 低利润产品提醒卡片（原规则信号） ──");
t("标题=专属名称+日期，橙色头", () => {
  const b = buildRuleSignalCard("2026-07-18", [sig({})], { perOwnerLimit: 10, pageUrl: "http://x" });
  assert.strictEqual(b.title, "📉 低利润产品提醒 ｜ 2026-07-18");
  const header = b.card.header as { template: string; title: { content: string } };
  assert.strictEqual(header.template, "orange");
  assert.strictEqual(header.title.content, b.title);
});

t("测试前缀生效", () => {
  const b = buildRuleSignalCard("2026-07-18", [sig({})], { perOwnerLimit: 10, pageUrl: "http://x", testPrefix: true });
  assert.ok(b.title.startsWith("【测试】📉"));
});

t("按负责人分组：两人各成分区，未分配兜底命名", () => {
  const b = buildRuleSignalCard("2026-07-18", [sig({}), sig({ owner: "林翔", msku: "A1" }), sig({ owner: "", msku: "A2" })],
    { perOwnerLimit: 10, pageUrl: "http://x" });
  const divs = (b.card.elements as { tag: string; text?: { content: string } }[])
    .filter((e) => e.tag === "div").map((e) => e.text!.content);
  assert.ok(divs.some((c) => c.includes("👤 曾洁茹")));
  assert.ok(divs.some((c) => c.includes("👤 林翔")));
  assert.ok(divs.some((c) => c.includes("（未分配负责人）")));
  assert.ok(b.fallbackText.includes("负责人：林翔（1 条）"));
});

t("perOwnerLimit 折叠：3条限2 → 另有1条", () => {
  const b = buildRuleSignalCard("2026-07-18", [sig({ msku: "A" }), sig({ msku: "B" }), sig({ msku: "C" })],
    { perOwnerLimit: 2, pageUrl: "http://x" });
  assert.ok(b.fallbackText.includes("另有 1 条未展开"));
  const divs = (b.card.elements as { tag: string; text?: { content: string } }[])
    .filter((e) => e.tag === "div").map((e) => e.text!.content);
  assert.ok(divs.some((c) => c.includes("另有 1 条未展开")));
  assert.ok(!divs.some((c) => c.includes("MSKU C")));
});

t("新触发带🆕；汇总行含条数/人数/产品数", () => {
  const b = buildRuleSignalCard("2026-07-18", [sig({ isNew: true }), sig({ owner: "林翔", itemId: "X", msku: "M2" })],
    { perOwnerLimit: 10, pageUrl: "http://x" });
  const divs = (b.card.elements as { tag: string; text?: { content: string } }[])
    .filter((e) => e.tag === "div").map((e) => e.text!.content);
  assert.ok(divs.some((c) => c.includes("🆕")));
  assert.ok(divs[0].includes("**本次信号** 2 条"));
  assert.ok(divs[0].includes("**涉及负责人** 2 人"));
  assert.ok(divs[0].includes("**涉及产品** 2 个"));
});

t("含页面按钮与去重说明note", () => {
  const b = buildRuleSignalCard("2026-07-18", [sig({})], { perOwnerLimit: 10, pageUrl: "http://page" });
  const els = b.card.elements as { tag: string; actions?: { url: string }[] }[];
  const action = els.find((e) => e.tag === "action");
  assert.ok(action && action.actions![0].url === "http://page");
  assert.ok(els.some((e) => e.tag === "note"));
});

console.log("── 待认领产品卡片 ──");
t("标题=专属名称+日期，紫色头，按店铺分组连续编号", () => {
  const items: UnmatchedOwnerItem[] = [
    { storeName: "CN2601-瑞盈龙盛", itemId: "1", msku: "YC1" },
    { storeName: "CN2601-瑞盈龙盛", itemId: "2", msku: "YC2" },
    { storeName: "HK2612-张李华", itemId: "3", msku: "YC3" },
  ];
  const b = buildUnmatchedOwnerCard("2026-07-18", 1024, items, { detailLimit: 50, pageUrl: "http://x" });
  assert.strictEqual(b.title, "🙋 待认领产品日报 ｜ 2026-07-18");
  const header = b.card.header as { template: string };
  assert.strictEqual(header.template, "purple");
  const divs = (b.card.elements as { tag: string; text?: { content: string } }[])
    .filter((e) => e.tag === "div").map((e) => e.text!.content);
  assert.ok(divs[0].includes("**active 商品** 1024 个"));
  assert.ok(divs.some((c) => c.includes("🏪 CN2601-瑞盈龙盛") && c.includes("1. YC1") && c.includes("2. YC2")));
  assert.ok(divs.some((c) => c.includes("🏪 HK2612-张李华") && c.includes("3. YC3")));
});

t("detailLimit 折叠尾注", () => {
  const items: UnmatchedOwnerItem[] = Array.from({ length: 5 }, (_, i) => ({ storeName: "S", itemId: String(i), msku: `M${i}` }));
  const b = buildUnmatchedOwnerCard("2026-07-18", 100, items, { detailLimit: 3, pageUrl: "http://x" });
  assert.ok(b.fallbackText.includes("其余 2 个请到产品管理页面查看"));
});

t("零缺失→绿色全认领卡", () => {
  const b = buildUnmatchedOwnerCard("2026-07-18", 1024, [], { detailLimit: 50, pageUrl: "http://x" });
  const header = b.card.header as { template: string };
  assert.strictEqual(header.template, "green");
  assert.ok(b.fallbackText.includes("全部已维护负责人"));
});

t("测试前缀生效（待认领）", () => {
  const b = buildUnmatchedOwnerCard("2026-07-18", 10, [], { detailLimit: 50, pageUrl: "http://x", testPrefix: true });
  assert.ok(b.title.startsWith("【测试】🙋"));
});

console.log("── 订单异常下滑卡片 ──");
function od(p: Partial<OrderDropCardItem>): OrderDropCardItem {
  return {
    owner: "刘华媛", storeName: "CN2601-瑞盈龙盛", itemId: "19900769352", msku: "YC00001-1A",
    productName: "", detail: "近3天订单 18 / 20 / 16（日均18）→ 当日 6　↓66.7%", streak: "连续第1天异常", ...p,
  };
}

t("标题=专属名称+日期，红色头", () => {
  const b = buildOrderDropCard("2026-07-17", [od({})], {});
  assert.strictEqual(b.title, "🔻 订单异常下滑提醒 ｜ 2026-07-17");
  const header = b.card.header as { template: string };
  assert.strictEqual(header.template, "red");
});

t("测试前缀生效（订单下滑）", () => {
  const b = buildOrderDropCard("2026-07-17", [od({})], { testPrefix: true });
  assert.ok(b.title.startsWith("【测试】🔻"));
});

t("按负责人分区，未匹配兜底命名，汇总行含个数/人数", () => {
  const b = buildOrderDropCard("2026-07-17", [od({}), od({ owner: "林翔", msku: "B1" }), od({ owner: "", msku: "B2" })], {});
  const divs = (b.card.elements as { tag: string; text?: { content: string } }[])
    .filter((e) => e.tag === "div").map((e) => e.text!.content);
  assert.ok(divs[0].includes("**异常产品** 3 个"));
  assert.ok(divs[0].includes("**涉及负责人** 3 人"));
  assert.ok(divs.some((c) => c.includes("👤 刘华媛")));
  assert.ok(divs.some((c) => c.includes("👤 林翔")));
  assert.ok(divs.some((c) => c.includes("（未匹配负责人）")));
  assert.ok(b.fallbackText.includes("负责人：林翔（1 个异常）"));
});

t("明细含 detail/streak 与口径note", () => {
  const b = buildOrderDropCard("2026-07-17", [od({ streak: "连续第2天异常" })], {});
  const divs = (b.card.elements as { tag: string; text?: { content: string } }[])
    .filter((e) => e.tag === "div").map((e) => e.text!.content);
  assert.ok(divs.some((c) => c.includes("↓66.7%") && c.includes("连续第2天异常")));
  const els = b.card.elements as { tag: string }[];
  assert.ok(els.some((e) => e.tag === "note"));
  assert.ok(b.fallbackText.includes("ItemID：19900769352"));
});

console.log("── 无运营动作卡片 ──");
function oi(p: Partial<OpsInactionCardItem>): OpsInactionCardItem {
  return {
    owner: "江梓博", storeName: "CN2601-瑞盈龙盛(刘云龙)", itemId: "19983613590", mskus: "YC00053-1B",
    poolReason: "5天不出单", ruleHit: "连续5个日志日无动作", lastActionDate: "2026-07-10", ...p,
  };
}

t("标题=专属名称+日期+备注，橙色头（与低利润统一）", () => {
  const b = buildOpsInactionCard("2026-07-20", [oi({})], { titleNote: "（总览留档）" });
  assert.strictEqual(b.title, "⚠️ 无运营动作产品提醒 ｜ 2026-07-20（总览留档）");
  const header = b.card.header as { template: string };
  assert.strictEqual(header.template, "orange");
});

t("测试前缀+负责人分区+未分配兜底+解除数", () => {
  const b = buildOpsInactionCard("2026-07-20", [oi({}), oi({ owner: "", mskus: "X1" })],
    { resolvedToday: 3, testPrefix: true });
  assert.ok(b.title.startsWith("【测试】⚠️"));
  const divs = (b.card.elements as { tag: string; text?: { content: string } }[])
    .filter((e) => e.tag === "div").map((e) => e.text!.content);
  assert.ok(divs[0].includes("今日自动解除 3 个"));
  assert.ok(divs.some((c) => c.includes("👤 江梓博")));
  assert.ok(divs.some((c) => c.includes("（未分配负责人）")));
});

t("行含店铺/最近动作，note含解除规则，降级文本含ItemID", () => {
  const b = buildOpsInactionCard("2026-07-20", [oi({})], {});
  const divs = (b.card.elements as { tag: string; text?: { content: string } }[])
    .filter((e) => e.tag === "div").map((e) => e.text!.content);
  assert.ok(divs.some((c) => c.includes("CN2601-瑞盈龙盛(刘云龙)") && c.includes("最近动作：07-10")));
  const els = b.card.elements as { tag: string }[];
  assert.ok(els.some((e) => e.tag === "note"));
  assert.ok(b.fallbackText.includes("ItemID 19983613590"));
});

console.log("── 清货申请审批卡 ──");
function ca(p: Partial<ClearanceApprovalItem>): ClearanceApprovalItem {
  return {
    id: 7, storeName: "CN2601-瑞盈龙盛", itemId: "19952124946", mskus: "YC00094-1A",
    sku: "YC00094", owner: "刘华媛", applicant: "刘华媛",
    sales30: 3, stock: 86, inbound: 0, turnoverDays: 860, ...p,
  };
}

t("标题含待审批数，琥珀头，每申请带同意/驳回按钮", () => {
  const b = buildClearanceApprovalCard("2026-07-21", [ca({}), ca({ id: 8, mskus: "JJ2027-1B" })], {});
  assert.ok(b.title.includes("（2 项待审批）"));
  const header = b.card.header as { template: string };
  assert.strictEqual(header.template, "amber");
  const actions = (b.card.elements as { tag: string; actions?: { text: { content: string }; value: Record<string, unknown> }[] }[])
    .filter((e) => e.tag === "action");
  assert.strictEqual(actions.length, 2);
  assert.strictEqual(actions[0].actions![0].text.content, "同意清货");
  assert.strictEqual(actions[0].actions![1].text.content, "驳回");
  assert.deepStrictEqual(actions[0].actions![0].value, { biz: "clearance_approval", id: 7, choice: "approve" });
  assert.deepStrictEqual(actions[1].actions![1].value, { biz: "clearance_approval", id: 8, choice: "reject" });
});

t("testMode：标题带测试前缀且按钮 value 带 test=1", () => {
  const b = buildClearanceApprovalCard("2026-07-21", [ca({})], { testMode: true });
  assert.ok(b.title.startsWith("【测试】🧹"));
  const actions = (b.card.elements as { tag: string; actions?: { value: Record<string, unknown> }[] }[])
    .filter((e) => e.tag === "action");
  assert.strictEqual(actions[0].actions![0].value.test, 1);
});

t("分区含关键指标；周转 null 显示—；降级文本说明无法按钮审批", () => {
  const b = buildClearanceApprovalCard("2026-07-21", [ca({ turnoverDays: null, sales30: 0 })], {});
  const divs = (b.card.elements as { tag: string; text?: { content: string } }[])
    .filter((e) => e.tag === "div").map((e) => e.text!.content);
  assert.ok(divs.some((c) => c.includes("近30天销量 0") && c.includes("周转 —") && c.includes("申请人 刘华媛")));
  assert.ok(b.fallbackText.includes("无法按钮审批"));
});

console.log("── 清货三张自动卡 ──");
t("清尾卡：turquoise头/逐品继续清货与转稳定期按钮/含预计结束", () => {
  const b = buildClearanceTailCard("2026-07-24", "刘华媛",
    [{ id: 11, storeName: "CN2601-瑞盈龙盛", itemId: "19955150859", mskus: "YC00026-1R", stock: 40, daily7: 0.9, daysToClear: 44, expectEnd: "2026-08-31" }], {});
  const header = b.card.header as { template: string };
  assert.strictEqual(header.template, "turquoise");
  assert.ok(b.title.includes("清货收尾确认"));
  const actions = (b.card.elements as { tag: string; actions?: { text: { content: string }; value: Record<string, unknown> }[] }[]).filter((e) => e.tag === "action");
  assert.strictEqual(actions[0].actions![0].text.content, "继续清货");
  assert.deepStrictEqual(actions[0].actions![1].value, { biz: "clearance_card", id: 11, choice: "stable" });
  const divs = (b.card.elements as { tag: string; text?: { content: string } }[]).filter((e) => e.tag === "div").map((e) => e.text!.content);
  assert.ok(divs.some((c) => c.includes("约 44 天清完") && c.includes("预计结束 2026-08-31")));
});

t("归档卡：green头/确认归档+暂不归档/含清零天数与拦截说明", () => {
  const b = buildClearanceArchiveCard({ id: 22, storeName: "CN2602-添详商贸", itemId: "20044316591", mskus: "YC00004-1A", zeroDays: 9 }, { testMode: true });
  assert.ok(b.title.startsWith("【测试】📦"));
  const header = b.card.header as { template: string };
  assert.strictEqual(header.template, "green");
  const actions = (b.card.elements as { tag: string; actions?: { value: Record<string, unknown> }[] }[]).filter((e) => e.tag === "action");
  assert.strictEqual(actions[0].actions![0].value.choice, "archive");
  assert.strictEqual(actions[0].actions![1].value.test, 1);
  const divs = (b.card.elements as { tag: string; text?: { content: string } }[]).filter((e) => e.tag === "div").map((e) => e.text!.content);
  assert.ok(divs.some((c) => c.includes("9 天")));
});

t("复活卡：violet头/转上升期+转稳定期/含货件号与数量", () => {
  const b = buildClearanceReviveCard({ id: 33, storeName: "HK2612-张李华", itemId: "20598811962", mskus: "YC00081-1A", shipmentId: "9371138WFA", shipmentQty: 32 }, {});
  const header = b.card.header as { template: string };
  assert.strictEqual(header.template, "violet");
  const actions = (b.card.elements as { tag: string; actions?: { value: Record<string, unknown> }[] }[]).filter((e) => e.tag === "action");
  assert.strictEqual(actions[0].actions![0].value.choice, "rising");
  assert.strictEqual(actions[0].actions![1].value.choice, "stable");
  const divs = (b.card.elements as { tag: string; text?: { content: string } }[]).filter((e) => e.tag === "div").map((e) => e.text!.content);
  assert.ok(divs.some((c) => c.includes("9371138WFA") && c.includes("32 件")));
});

console.log(`\n结果: ${passed} 通过, ${failed} 失败`);
if (failed > 0) process.exit(1);
