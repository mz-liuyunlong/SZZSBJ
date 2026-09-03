import "dotenv/config";
import { execFileSync } from "child_process";
import currentReport from "../config/currentReportFieldMapping.json";
import { FeishuSheetWriter } from "./feishuSheetWriter";
import { TableOperationLogger } from "./tableOperationLogger";

interface StepResult {
  name: string;
  success: boolean;
  output: string;
  errorMessage: string;
}

const TASK_NAME = "每日自动化";
const LOG_SHEET_NAME = "表格操作日志";
const TIME_ZONE = "Asia/Shanghai";
const MAX_OUTPUT_BUFFER = 120 * 1024 * 1024;

function createRunId(): string {
  return `run_${new Date().toISOString().replace(/[-:.TZ]/g, "")}_${Math.random()
    .toString(36)
    .slice(2, 8)}`;
}

function getChinaDateText(date = new Date()): string {
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: TIME_ZONE,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).formatToParts(date);

  const year = parts.find((part) => part.type === "year")?.value;
  const month = parts.find((part) => part.type === "month")?.value;
  const day = parts.find((part) => part.type === "day")?.value;

  if (!year || !month || !day) {
    throw new Error("无法计算中国日期");
  }

  return `${year}-${month}-${day}`;
}

function addDays(dateText: string, days: number): string {
  const [year, month, day] = dateText.split("-").map(Number);
  const date = new Date(Date.UTC(year, month - 1, day));
  date.setUTCDate(date.getUTCDate() + days);
  return date.toISOString().slice(0, 10);
}

function getErrorMessage(error: unknown): string {
  if (error instanceof Error) {
    return error.message;
  }
  return String(error);
}

function runNpmScript(scriptName: string, args: string[]): StepResult {
  const printableCommand = ["npm", "run", scriptName, ...(args.length > 0 ? ["--", ...args] : [])].join(" ");
  console.log("");
  console.log(`开始执行: ${printableCommand}`);

  try {
    const output = execFileSync("npm", ["run", scriptName, ...(args.length > 0 ? ["--", ...args] : [])], {
      cwd: process.cwd(),
      encoding: "utf8",
      maxBuffer: MAX_OUTPUT_BUFFER,
      stdio: ["ignore", "pipe", "pipe"],
    });
    console.log(output);
    console.log(`执行成功: ${scriptName}`);
    return { name: scriptName, success: true, output, errorMessage: "" };
  } catch (error) {
    const err = error as { stdout?: Buffer | string; stderr?: Buffer | string; message?: string };
    const stdout = Buffer.isBuffer(err.stdout) ? err.stdout.toString("utf8") : err.stdout ?? "";
    const stderr = Buffer.isBuffer(err.stderr) ? err.stderr.toString("utf8") : err.stderr ?? "";
    const output = `${stdout}${stderr}`;
    const errorMessage = stderr || err.message || getErrorMessage(error);
    if (output) {
      console.log(output);
    }
    console.log(`执行失败: ${scriptName}`);
    console.log(`失败原因: ${errorMessage}`);
    return { name: scriptName, success: false, output, errorMessage };
  }
}

function parseFailureCount(output: string): number | null {
  const match = /失败数:\s*(\d+)/.exec(output);
  return match ? Number(match[1]) : null;
}

function parseNewItemCount(output: string): number {
  const match = /新增 ITEM ID 数:\s*(\d+)/.exec(output) ?? /待新增商品ID数:\s*(\d+)/.exec(output);
  return match ? Number(match[1]) : 0;
}

function parseNumberByLabel(output: string, label: string): number {
  const escaped = label.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const match = new RegExp(`${escaped}\\s*[:：=]\\s*(\\d+)`).exec(output);
  return match ? Number(match[1]) : 0;
}

function parseDailyWrittenCount(dailyOutput: string, backfillOutput: string): number {
  return (
    parseNumberByLabel(dailyOutput, "写入条数") ||
    parseNumberByLabel(dailyOutput, "行数") ||
    parseNumberByLabel(backfillOutput, "追加写入条数")
  );
}

function isAiEnabled(): boolean {
  return String(process.env.ENABLE_AI_DIAGNOSIS ?? "").trim().toLowerCase() === "true";
}

function buildArgs(baseArgs: string[], confirmWrite: boolean): string[] {
  return confirmWrite ? [...baseArgs, "--confirm-write"] : baseArgs;
}

function buildDailyArgs(dataDate: string, confirmWrite: boolean): string[] {
  return buildArgs([`--date=${dataDate}`], confirmWrite);
}

function buildBackfillArgs(dataDate: string, confirmWrite: boolean): string[] {
  return buildArgs([`--startDate=${dataDate}`, `--endDate=${dataDate}`], confirmWrite);
}

function buildAiArgs(dataDate: string, confirmWrite: boolean): string[] {
  return buildArgs([`--date=${dataDate}`], confirmWrite);
}

function buildOperationLogBaseArgs(dataDate: string, confirmWrite: boolean): string[] {
  return buildArgs([`--date=${dataDate}`], confirmWrite);
}

function buildCheckArgs(dataDate: string): string[] {
  return [`--date=${dataDate}`];
}

function buildNoDateWriteArgs(confirmWrite: boolean): string[] {
  return buildArgs([], confirmWrite);
}

function assertStepSuccess(result: StepResult): void {
  if (!result.success) {
    throw new Error(`${result.name} 失败：${result.errorMessage}`);
  }
}

function runDailyAndBackfill(dataDate: string, confirmWrite: boolean): { daily: StepResult; backfill: StepResult } {
  const daily = runNpmScript("sync:daily-all", buildDailyArgs(dataDate, confirmWrite));
  assertStepSuccess(daily);

  const backfill = runNpmScript("backfill:sales-detail", buildBackfillArgs(dataDate, confirmWrite));
  assertStepSuccess(backfill);

  return { daily, backfill };
}

function runCheckWithOneRetry(dataDate: string, confirmWrite: boolean): {
  check: StepResult;
  retried: boolean;
  dailyRetry?: StepResult;
  backfillRetry?: StepResult;
} {
  const firstCheck = runNpmScript("check:sales-detail-sample", buildCheckArgs(dataDate));
  assertStepSuccess(firstCheck);
  const firstFailureCount = parseFailureCount(firstCheck.output);

  if (firstFailureCount === null) {
    throw new Error("抽查输出中没有找到失败数");
  }
  if (firstFailureCount === 0) {
    return { check: firstCheck, retried: false };
  }

  console.log(`抽查失败数=${firstFailureCount}，自动重跑 当日数据 和 销售明细 一次`);
  const retry = runDailyAndBackfill(dataDate, confirmWrite);
  const secondCheck = runNpmScript("check:sales-detail-sample", buildCheckArgs(dataDate));
  assertStepSuccess(secondCheck);
  const secondFailureCount = parseFailureCount(secondCheck.output);

  if (secondFailureCount === null) {
    throw new Error("重跑后抽查输出中没有找到失败数");
  }
  if (secondFailureCount > 0) {
    throw new Error(`重跑后抽查仍失败，失败数=${secondFailureCount}`);
  }

  return {
    check: secondCheck,
    retried: true,
    dailyRetry: retry.daily,
    backfillRetry: retry.backfill,
  };
}

async function main(): Promise<void> {
  const startedAt = Date.now();
  const runId = createRunId();
  const confirmWrite = process.argv.includes("--confirm-write");
  const explicitDryRun = process.argv.includes("--dry-run");
  const skipAi = process.argv.includes("--skip-ai");
  const coreOnly = process.argv.includes("--core-only"); // 只跑步骤1-4，跳过5(recent-profit-ads)和6(operation-log-base)
  const dryRun = !confirmWrite;

  if (confirmWrite && explicitDryRun) {
    throw new Error("--dry-run 和 --confirm-write 不能同时使用");
  }

  const chinaDate = getChinaDateText();
  const dataDate = addDays(chinaDate, -2);
  const writer = new FeishuSheetWriter();
  const logger = new TableOperationLogger(writer, {
    spreadsheetToken: currentReport.spreadsheetToken,
    logSheetId: currentReport.sheets[LOG_SHEET_NAME],
    dryRun,
    confirmWrite,
  });

  let dailyStatus = "未执行";
  let salesDetailStatus = "未执行";
  let missingItemStatus = "未执行";
  let checkStatus = "未执行";
  let recentStatus = "未执行";
  let operationLogBaseStatus = "未执行";
  let aiStatus = skipAi ? "已拆分独立任务" : "未启用";
  let checkStarted = false;
  let newItemCount = 0;
  let totalSkuCount = 0;
  let levelACount = 0;
  let levelBCount = 0;
  let levelCCount = 0;
  let levelDCount = 0;
  let triggerAiCount = 0;
  let aiSuccessCount = 0;
  let aiFailureCount = 0;
  let dailyLogWriteCount = 0;
  let status = dryRun ? "dry-run" : "success";
  let errorMessage = "";
  let logSuccess = false;
  const nonBlockingErrors: string[] = [];
  const aiEnabled = isAiEnabled();

  console.log("每日自动化");
  console.log(`运行ID: ${runId}`);
  console.log(`写入模式: ${confirmWrite ? "confirm-write" : "dry-run"}`);
  console.log(`中国日期: ${chinaDate}`);
  console.log(`执行数据日期: ${dataDate}`);
  console.log(`销售明细Sheet=<REDACTED_FEISHU_SHEET_ID>`);
  console.log(`AI开关=${aiEnabled}`);

  try {
    const firstRun = runDailyAndBackfill(dataDate, confirmWrite);
    dailyStatus = firstRun.daily.success ? "成功" : "失败";
    salesDetailStatus = firstRun.backfill.success ? "成功" : "失败";
    totalSkuCount = parseDailyWrittenCount(firstRun.daily.output, firstRun.backfill.output);

    const missingItems = runNpmScript("sync:missing-item-owners", buildNoDateWriteArgs(confirmWrite));
    assertStepSuccess(missingItems);
    missingItemStatus = "成功";
    newItemCount = parseNewItemCount(missingItems.output);

    checkStarted = true;
    try {
      const checkResult = runCheckWithOneRetry(dataDate, confirmWrite);
      checkStatus = checkResult.check.success ? "通过" : "失败";
      if (checkResult.retried) {
        dailyStatus = checkResult.dailyRetry?.success ? "成功" : "失败";
        salesDetailStatus = checkResult.backfillRetry?.success ? "成功" : "失败";
        if (checkResult.dailyRetry && checkResult.backfillRetry) {
          totalSkuCount = parseDailyWrittenCount(checkResult.dailyRetry.output, checkResult.backfillRetry.output);
        }
      }
    } catch (error) {
      checkStatus = "失败";
      const checkErrorMessage = getErrorMessage(error);
      nonBlockingErrors.push(`抽查失败：${checkErrorMessage}`);
      console.log(`抽查失败但继续执行后续流程: ${checkErrorMessage}`);
    }

    if (!coreOnly) {
      // ── 2026-07-23 批2：飞书退役，sync:recent-profit-ads（写真飞书在线表）已下线归档至 legacy_feishu_20260723/，
      // npm script 已摘除，不再触发。旧调用保留备查（勿恢复；恢复会重新写飞书在线表）：
      // const recent = runNpmScript("sync:recent-profit-ads", buildNoDateWriteArgs(confirmWrite));
      // assertStepSuccess(recent);
      recentStatus = "已下线归档(2026-07-23 批2)";

      // ── 任务H-1C：运营日志基础行退役飞书链路 ───────────────────────────────
      // 基础行生成已迁至独立 20:50 cron: build:operation-log-base（MySQL 链路，写 biz_product_operation_log）。
      // 旧 sync:daily-operation-log-base（写飞书 <REDACTED_FEISHU_SHEET_ID>）不再由本编排器触发，避免与独立 cron 双跑。
      // 手动全量重生成请直接执行: npm run build:operation-log-base -- --confirm-write
      operationLogBaseStatus = "已迁移MySQL独立cron(build:operation-log-base)";

      // ── 任务H-1C：停用 AI 写飞书自动入口 ───────────────────────────────────
      // ai:daily(aiDailyDiagnosis.ts) 会写飞书 <REDACTED_FEISHU_SHEET_ID>「AI诊断记录」，按指示停用自动入口。
      // aiDailyDiagnosis.ts 内部逻辑未改；后续 1E 改为系统规则写 MySQL 供前端只读。
      aiStatus = "已停用(任务H-1C)";

      // 旧步骤保留备查（已停用，勿直接恢复；恢复会重新写飞书 <REDACTED_FEISHU_SHEET_ID>）：
      // const operationLogBase = runNpmScript("sync:daily-operation-log-base", buildOperationLogBaseArgs(dataDate, confirmWrite));
      // assertStepSuccess(operationLogBase);
      // operationLogBaseStatus = "成功";
      // dailyLogWriteCount = parseNumberByLabel(operationLogBase.output, "新增每日运营跟进日志行数");
      // levelACount = parseNumberByLabel(operationLogBase.output, "A级数量");
      // levelBCount = parseNumberByLabel(operationLogBase.output, "B级数量");
      // levelCCount = parseNumberByLabel(operationLogBase.output, "C级数量");
      // levelDCount = parseNumberByLabel(operationLogBase.output, "D级数量");
      // if (aiEnabled && !skipAi) {
      //   const ai = runNpmScript("ai:daily", buildAiArgs(dataDate, confirmWrite));
      //   assertStepSuccess(ai);
      //   aiStatus = "成功";
      //   totalSkuCount = parseNumberByLabel(ai.output, "总SKU数") || totalSkuCount;
      //   levelACount = parseNumberByLabel(ai.output, "A级数量");
      //   levelBCount = parseNumberByLabel(ai.output, "B级数量");
      //   levelCCount = parseNumberByLabel(ai.output, "C级数量");
      //   levelDCount = parseNumberByLabel(ai.output, "D级数量");
      //   triggerAiCount = parseNumberByLabel(ai.output, "触发AI数量");
      //   aiSuccessCount = parseNumberByLabel(ai.output, "AI成功数");
      //   aiFailureCount = parseNumberByLabel(ai.output, "AI失败数");
      //   dailyLogWriteCount = parseNumberByLabel(ai.output, "写入每日运营跟进日志数量");
      // }
    }
  } catch (error) {
    status = "failed";
    errorMessage = getErrorMessage(error);
    if (checkStarted && checkStatus === "未执行") {
      checkStatus = "失败";
    }
    console.log(`每日自动化失败: ${errorMessage}`);
  } finally {
    const durationSeconds = Number(((Date.now() - startedAt) / 1000).toFixed(3));
    if (status !== "failed" && nonBlockingErrors.length > 0) {
      status = "failed";
      errorMessage = nonBlockingErrors.join("；");
    } else if (status === "failed" && nonBlockingErrors.length > 0) {
      errorMessage = [errorMessage, ...nonBlockingErrors].filter(Boolean).join("；");
    }
    const remark =
      `CODEX执行：每日自动化流程` +
      `，数据日期=${dataDate}` +
      `，销售明细Sheet=<REDACTED_FEISHU_SHEET_ID>` +
      `，AI开关=${aiEnabled}` +
      `，总SKU数=${totalSkuCount}` +
      `，A级数量=${levelACount}` +
      `，B级数量=${levelBCount}` +
      `，C级数量=${levelCCount}` +
      `，D级数量=${levelDCount}` +
      `，触发AI数量=${triggerAiCount}` +
      `，AI成功=${aiSuccessCount}` +
      `，AI失败=${aiFailureCount}` +
      `，写入每日运营跟进日志=${dailyLogWriteCount}` +
      `，当日数据=${dailyStatus}` +
      `，销售明细=${salesDetailStatus}` +
      `，新增ItemID=${newItemCount}` +
      `，抽查=${checkStatus}` +
      `，每日运营跟进日志基础字段=${operationLogBaseStatus}` +
      `，AI诊断=${aiStatus}` +
      `，近期利润与广告=${recentStatus}`;

    try {
      logger.append({
        executedAt: new Date().toISOString(),
        taskName: TASK_NAME,
        targetSheet: "全流程",
        operationType: dryRun ? "dry-run" : "daily_automation",
        dataSource: "local npm scripts",
        dateRange: dataDate,
        fetchedCount: 0,
        writtenCount: 0,
        updatedCount: 0,
        skippedCount: 0,
        failedCount: status === "failed" ? 1 : aiFailureCount,
        status,
        errorMessage,
        durationSeconds,
        runId,
        environment: "local",
        remark: errorMessage ? `${remark}，失败原因=${errorMessage}` : remark,
      });
      logSuccess = true;
    } catch (logError) {
      console.log(`写入每日自动化总日志失败: ${getErrorMessage(logError)}`);
    }

    console.log("");
    console.log("每日自动化汇总:");
    console.log(`执行日期=${dataDate}`);
    console.log(`当日数据=${dailyStatus}`);
    console.log(`销售明细=${salesDetailStatus}`);
    console.log(`新增ItemID=${newItemCount}`);
    console.log(`抽查=${checkStatus}`);
    console.log(`每日运营跟进日志基础字段=${operationLogBaseStatus}`);
    console.log(`AI诊断=${aiStatus}`);
    console.log(`总SKU数=${totalSkuCount}`);
    console.log(`A级数量=${levelACount}`);
    console.log(`B级数量=${levelBCount}`);
    console.log(`C级数量=${levelCCount}`);
    console.log(`D级数量=${levelDCount}`);
    console.log(`触发AI数量=${triggerAiCount}`);
    console.log(`AI成功数=${aiSuccessCount}`);
    console.log(`AI失败数=${aiFailureCount}`);
    console.log(`写入每日运营跟进日志数量=${dailyLogWriteCount}`);
    console.log(`近期利润与广告=${recentStatus}`);
    console.log(`总状态=${status}`);
    console.log(`总日志是否写入成功=${logSuccess ? "是" : "否"}`);

    if (status === "failed") {
      process.exitCode = 1;
    }
  }
}

main().catch((error) => {
  console.log(`执行失败: ${getErrorMessage(error)}`);
  process.exitCode = 1;
});
