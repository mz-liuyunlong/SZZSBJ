/**
 * autoAdImportCheck.test.ts - 自动广告搜索词导入检查 单元测试
 *
 * 运行：npx ts-node src/notifyRules/autoAdImportCheck.test.ts
 * 飞书表格读取与发送模块全部 Mock（deps 注入），不调用任何真实接口。
 */

import * as assert from "assert";
import {
  getTargetDateCST,
  parseDateCell,
  findDateColumnIndex,
  evaluateImportStatus,
  buildMissingAlertText,
  runAutoAdImportCheck,
  formatDateTimeCST,
} from "./autoAdImportCheck";

let passed = 0;
let failed = 0;

function t(name: string, fn: () => void | Promise<void>): Promise<void> {
  return Promise.resolve()
    .then(fn)
    .then(() => {
      passed += 1;
      console.log(`  ✅ ${name}`);
    })
    .catch((e) => {
      failed += 1;
      console.error(`  ❌ ${name}: ${e instanceof Error ? e.message : String(e)}`);
    });
}

/** Mock 发送模块：只记录，不发送 */
function mockSender(): { calls: string[]; sendAlert: (text: string) => Promise<void> } {
  const calls: string[] = [];
  return { calls, sendAlert: async (text: string) => { calls.push(text); } };
}

async function main(): Promise<void> {
  console.log("── getTargetDateCST（Asia/Shanghai，不依赖系统时区）──");

  await t("2026-07-13（上海）→ targetDate=2026-07-10", () => {
    // 2026-07-13T08:00:00Z = 上海 2026-07-13 16:00
    assert.strictEqual(getTargetDateCST(new Date("2026-07-13T08:00:00Z"), 3), "2026-07-10");
  });

  await t("UTC 与上海跨日边界：2026-07-13T17:00Z（上海已是 07-14）→ 2026-07-11", () => {
    assert.strictEqual(getTargetDateCST(new Date("2026-07-13T17:00:00Z"), 3), "2026-07-11");
  });

  await t("跨月：2026-07-02（上海）→ 2026-06-29", () => {
    assert.strictEqual(getTargetDateCST(new Date("2026-07-02T04:00:00Z"), 3), "2026-06-29");
  });

  await t("lagDays 可配置：lagDays=2 → 2026-07-11", () => {
    assert.strictEqual(getTargetDateCST(new Date("2026-07-13T08:00:00Z"), 2), "2026-07-11");
  });

  console.log("── parseDateCell ──");

  await t("标准日期", () => {
    assert.strictEqual(parseDateCell("2026-07-10"), "2026-07-10");
  });

  await t("日期列包含时间 → 正确解析", () => {
    assert.strictEqual(parseDateCell("2026-07-10 08:30:00"), "2026-07-10");
  });

  await t("斜杠与个位数月份日", () => {
    assert.strictEqual(parseDateCell("2026/7/9"), "2026-07-09");
  });

  await t("非法日历日期 → null", () => {
    assert.strictEqual(parseDateCell("2026-13-40"), null);
    assert.strictEqual(parseDateCell("2026-02-30"), null);
  });

  await t("非日期文本/空值 → null", () => {
    assert.strictEqual(parseDateCell("abc"), null);
    assert.strictEqual(parseDateCell(""), null);
    assert.strictEqual(parseDateCell(null), null);
    assert.strictEqual(parseDateCell(undefined), null);
  });

  console.log("── findDateColumnIndex（header / positional 双模式）──");

  await t("表头命中 → header 模式", () => {
    const r = findDateColumnIndex(["店铺", "MSKU", "x", "广告时间段"], ["广告时间段", "时间段"], 2);
    assert.deepStrictEqual(r, { index: 3, mode: "header" });
  });

  await t("表头未命中 → positional 模式，第 3 列（0-based=2）", () => {
    const r = findDateColumnIndex(["col_1", "col_2", "col_3", "col_4"], ["广告时间段", "时间段"], 2);
    assert.deepStrictEqual(r, { index: 2, mode: "positional" });
  });

  console.log("── evaluateImportStatus（标准日期比较，禁止模糊包含）──");

  await t("最新日期 2026-07-11 > target 2026-07-10 → 不通报(ok)", () => {
    const r = evaluateImportStatus(["2026-07-09", "2026-07-11"], "2026-07-10");
    assert.strictEqual(r.status, "ok");
    assert.strictEqual(r.latestDate, "2026-07-11");
  });

  await t("最新日期 = target 2026-07-10 → 不通报(ok)", () => {
    const r = evaluateImportStatus(["2026-07-08", "2026-07-10"], "2026-07-10");
    assert.strictEqual(r.status, "ok");
  });

  await t("最新日期 2026-07-09 < target 2026-07-10 → 通报(missing)", () => {
    const r = evaluateImportStatus(["2026-07-08", "2026-07-09"], "2026-07-10");
    assert.strictEqual(r.status, "missing");
    assert.strictEqual(r.latestDate, "2026-07-09");
  });

  await t("模糊包含不作数：'x2026-07-10y备注' 仍按提取出的标准日期判定", () => {
    const r = evaluateImportStatus(["导入批次2026-07-10全量"], "2026-07-10");
    assert.strictEqual(r.status, "ok");
    assert.strictEqual(r.latestDate, "2026-07-10");
  });

  await t("日期值全部非法 → config_error，不判缺失", () => {
    const r = evaluateImportStatus(["abc", "2026-99-99", "N/A"], "2026-07-10");
    assert.strictEqual(r.status, "config_error");
    assert.strictEqual(r.invalidCount, 3);
  });

  await t("日期列为空 → config_error", () => {
    const r = evaluateImportStatus(["", null, undefined], "2026-07-10");
    assert.strictEqual(r.status, "config_error");
  });

  await t("部分非法部分有效 → 用有效值判定，非法只计数", () => {
    const r = evaluateImportStatus(["abc", "2026-07-11"], "2026-07-10");
    assert.strictEqual(r.status, "ok");
    assert.strictEqual(r.invalidCount, 1);
  });

  console.log("── 通报文案 ──");

  await t("文案为固定四行且不含违禁表述", () => {
    const text = buildMissingAlertText({
      targetDate: "2026-07-10",
      checkTime: "2026-07-13 16:10",
      latestDate: "2026-07-09",
    });
    assert.strictEqual(
      text,
      "悦斯自动广告搜索词聚合分析数据缺失\n" +
        "应导入数据日期：2026-07-10\n" +
        "任务检查时间：2026-07-13 16:10\n" +
        "表内最新成功数据日期：2026-07-09",
    );
    assert.ok(!text.includes("今日" + "数据尚未导入"));
    assert.ok(!text.includes("2026-07-13\n"), "应导入日期不得是检查当天");
  });

  console.log("── runAutoAdImportCheck 编排（Mock 表格读取 + Mock 发送）──");

  const NOW = new Date("2026-07-13T08:10:00Z"); // 上海 2026-07-13 16:10

  await t("2026-07-13 运行 → targetDate=2026-07-10", async () => {
    const s = mockSender();
    const out = await runAutoAdImportCheck({
      readDateCells: async () => ["2026-07-10"],
      sendAlert: s.sendAlert,
      now: NOW,
    });
    assert.strictEqual(out.targetDate, "2026-07-10");
  });

  await t("最新 2026-07-11 → 不通报，发送模块零调用", async () => {
    const s = mockSender();
    const out = await runAutoAdImportCheck({
      readDateCells: async () => ["2026-07-09 12:00", "2026-07-11 08:00"],
      sendAlert: s.sendAlert,
      now: NOW,
    });
    assert.strictEqual(out.status, "ok");
    assert.strictEqual(s.calls.length, 0);
  });

  await t("最新 2026-07-10 → 不通报", async () => {
    const s = mockSender();
    const out = await runAutoAdImportCheck({
      readDateCells: async () => ["2026-07-10"],
      sendAlert: s.sendAlert,
      now: NOW,
    });
    assert.strictEqual(out.status, "ok");
    assert.strictEqual(s.calls.length, 0);
  });

  await t("最新 2026-07-09 → 通报一次，文案含四要素与 @ 行", async () => {
    const s = mockSender();
    const out = await runAutoAdImportCheck({
      readDateCells: async () => ["2026-07-08", "2026-07-09"],
      sendAlert: s.sendAlert,
      now: NOW,
      mentionLine: '<at user_id="<REDACTED_FEISHU_OPEN_ID>">江梓博</at>',
    });
    assert.strictEqual(out.status, "missing");
    assert.strictEqual(s.calls.length, 1);
    const text = s.calls[0];
    assert.ok(text.includes("悦斯自动广告搜索词聚合分析数据缺失"));
    assert.ok(text.includes("应导入数据日期：2026-07-10"));
    assert.ok(text.includes(`任务检查时间：${formatDateTimeCST(NOW)}`));
    assert.ok(text.includes("表内最新成功数据日期：2026-07-09"));
    assert.ok(text.includes("江梓博"));
    assert.ok(!text.includes("今日" + "数据尚未导入"));
  });

  await t("日期值非法 → config_error 且发送模块零调用", async () => {
    const s = mockSender();
    const out = await runAutoAdImportCheck({
      readDateCells: async () => ["abc", "###"],
      sendAlert: s.sendAlert,
      now: NOW,
    });
    assert.strictEqual(out.status, "config_error");
    assert.strictEqual(s.calls.length, 0);
    assert.ok(out.configErrorReason);
  });

  console.log(`\n结果：通过 ${passed}，失败 ${failed}`);
  if (failed > 0) process.exit(1);
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
