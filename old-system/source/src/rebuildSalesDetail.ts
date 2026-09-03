import currentReport from "../config/currentReportFieldMapping.json";
import { execFileSync } from "child_process";
import { FeishuSheetWriter, SheetRow } from "./feishuSheetWriter";
import {
  STORES,
  applyFormulaColumns,
  generateDailyRowsForDate,
} from "./syncDailyBaseData";
import { TableOperationLogger } from "./tableOperationLogger";

const TARGET_SHEET_NAME = getArg("targetSheetName", "5月销售明细_复盘");
const TARGET_SHEET_ID = getArg("targetSheetId", (currentReport.sheets as Record<string, string>)[TARGET_SHEET_NAME]);
const LOG_SHEET_NAME = "表格操作日志";
const TASK_NAME = "5月销售明细全量重跑覆盖";
const WRITE_BATCH_SIZE = 200;
const CLEAR_RANGE = "A2:V12000";
const MAX_REBUILD_ROWS = 11999;
const LARK_CLI = "./scripts/lark-cli";

function getArg(name: string, defaultValue = ""): string {
  const prefix = `--${name}=`;
  const arg = process.argv.find((item) => item.startsWith(prefix));
  return arg ? arg.slice(prefix.length) : defaultValue;
}

function createRunId(): string {
  return `run_${new Date().toISOString().replace(/[-:.TZ]/g, "")}_${Math.random()
    .toString(36)
    .slice(2, 8)}`;
}

function parseDate(value: string): Date {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value);
  if (!match) {
    throw new Error(`日期格式必须是 YYYY-MM-DD: ${value}`);
  }

  return new Date(Date.UTC(Number(match[1]), Number(match[2]) - 1, Number(match[3])));
}

function formatDate(date: Date): string {
  return date.toISOString().slice(0, 10);
}

function getDateRange(startDate: string, endDate: string): string[] {
  const start = parseDate(startDate);
  const end = parseDate(endDate);
  if (start.getTime() > end.getTime()) {
    throw new Error("--startDate 不能晚于 --endDate");
  }

  const dates: string[] = [];
  for (const cursor = new Date(start); cursor.getTime() <= end.getTime(); cursor.setUTCDate(cursor.getUTCDate() + 1)) {
    dates.push(formatDate(cursor));
  }
  return dates;
}

function getErrorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

function chunkRows(rows: SheetRow[], size: number): SheetRow[][] {
  const chunks: SheetRow[][] = [];
  for (let index = 0; index < rows.length; index += size) {
    chunks.push(rows.slice(index, index + size));
  }
  return chunks;
}

function summarizeNonBlockingErrors(errors: string[]): string {
  if (errors.length === 0) {
    return "";
  }

  const advertiserIdEmptyCount = errors.filter((message) => message.includes("advertiserId为空")).length;
  const otherErrors = errors.filter((message) => !message.includes("advertiserId为空"));
  const parts: string[] = [];

  if (advertiserIdEmptyCount > 0) {
    parts.push(`advertiserId为空广告费填0次数=${advertiserIdEmptyCount}`);
  }
  if (otherErrors.length > 0) {
    parts.push(`其他非阻塞错误=${otherErrors.slice(0, 10).join("；")}`);
    if (otherErrors.length > 10) {
      parts.push(`其他非阻塞错误剩余=${otherErrors.length - 10}`);
    }
  }

  return parts.join("，");
}

function getWriteRange(rowCount: number): string {
  if (rowCount <= 0) {
    return "A2:V2";
  }

  return `A2:V${rowCount + 1}`;
}

function execLarkCli(args: string[]): string {
  try {
    return execFileSync(LARK_CLI, args, {
      cwd: process.cwd(),
      encoding: "utf8",
      maxBuffer: 50 * 1024 * 1024,
      stdio: ["ignore", "pipe", "pipe"],
    });
  } catch (error) {
    const err = error as { stderr?: Buffer | string; message?: string };
    const stderr = Buffer.isBuffer(err.stderr) ? err.stderr.toString("utf8") : err.stderr;
    throw new Error(stderr || err.message || "lark-cli command failed");
  }
}

function getSheetRowCount(): number {
  const output = execLarkCli([
    "sheets",
    "+sheet-info",
    "--spreadsheet-token",
    currentReport.spreadsheetToken,
    "--sheet-id",
    TARGET_SHEET_ID,
    "--format",
    "json",
  ]);

  const parsed = JSON.parse(output) as {
    ok?: boolean;
    data?: { range?: string };
    error?: { message?: string };
  };

  if (!parsed.ok) {
    throw new Error(parsed.error?.message ?? "读取 5月销售明细 行数失败");
  }

  const match = /[A-Z]+1:[A-Z]+(\d+)/.exec(parsed.data?.range ?? "");
  if (!match) {
    throw new Error(`无法解析 5月销售明细 range: ${parsed.data?.range ?? ""}`);
  }

  return Number(match[1]);
}

function ensureSheetRows(requiredEndRow: number, dryRun: boolean, confirmWrite: boolean): void {
  const currentRowCount = getSheetRowCount();
  if (requiredEndRow <= currentRowCount) {
    console.log(`5月销售明细当前行数 ${currentRowCount}，无需扩展`);
    return;
  }

  const insertCount = requiredEndRow - currentRowCount;
  console.log(`5月销售明细当前行数 ${currentRowCount}，需要插入空白行 ${insertCount}`);

  if (dryRun || !confirmWrite) {
    console.log("dry-run: 不插入空白行");
    return;
  }

  const output = execLarkCli([
    "sheets",
    "+dim-insert",
    "--spreadsheet-token",
    currentReport.spreadsheetToken,
    "--sheet-id",
    TARGET_SHEET_ID,
    "--position",
    String(currentRowCount),
    "--count",
    String(insertCount),
    "--inherit-style",
    "none",
    "--format",
    "json",
  ]).trim();

  if (output) {
    console.log(output);
  }
}

async function main(): Promise<void> {
  const startedAt = Date.now();
  const runId = createRunId();
  const startDate = getArg("startDate");
  const endDate = getArg("endDate");
  const confirmWrite = process.argv.includes("--confirm-write");
  const dryRun = !confirmWrite;

  if (!startDate || !endDate) {
    throw new Error("必须传入 --startDate=YYYY-MM-DD 和 --endDate=YYYY-MM-DD");
  }

  const writer = new FeishuSheetWriter();
  const logger = new TableOperationLogger(writer, {
    spreadsheetToken: currentReport.spreadsheetToken,
    logSheetId: currentReport.sheets[LOG_SHEET_NAME],
    dryRun,
    confirmWrite,
  });

  let fetchedCount = 0;
  let writtenCount = 0;
  let skippedCount = 0;
  let failedCount = 0;
  let status = dryRun ? "dry-run" : "success";
  let errorMessage = "";
  let clearSuccess = false;
  let writeSuccess = false;
  let logSuccess = false;
  const failedStores = new Set<string>();
  const nonBlockingErrors: string[] = [];
  const allRows: SheetRow[] = [];

  console.log("5月销售明细全量重跑覆盖");
  console.log(`运行ID: ${runId}`);
  console.log(`写入模式: ${confirmWrite ? "confirm-write" : "dry-run"}`);
  console.log(`日期范围: ${startDate}~${endDate}`);
  console.log("统计主键=Item ID");
  console.log(`店铺数: ${STORES.length}`);
  console.log(`目标 Sheet: ${TARGET_SHEET_NAME} (${TARGET_SHEET_ID})`);
  console.log(`清空范围: ${CLEAR_RANGE}`);

  try {
    const dates = getDateRange(startDate, endDate);
    for (const date of dates) {
      console.log("");
      console.log(`开始生成日期: ${date}`);
      const generated = await generateDailyRowsForDate(date, writer);
      fetchedCount += generated.totals.fetchedCount;
      skippedCount += generated.skippedCount;
      generated.failedStores.forEach((storeName) => failedStores.add(`${date}:${storeName}`));
      nonBlockingErrors.push(...generated.nonBlockingErrors.map((message) => `${date}:${message}`));
      allRows.push(...generated.rows);

      console.log(
        `日期 ${date} 完成: 抓取商品=${generated.totals.fetchedCount}, 写入候选=${generated.rows.length}, 零活跃过滤=${generated.skippedCount}`,
      );
    }

    if (allRows.length === 0) {
      throw new Error("API 抓取完成但没有可写入数据，已停止清空和写入。");
    }
    if (allRows.length > MAX_REBUILD_ROWS) {
      throw new Error(`生成数据 ${allRows.length} 行，超过 ${CLEAR_RANGE} 可容纳的 ${MAX_REBUILD_ROWS} 行，已停止清空和写入。`);
    }

    writtenCount = allRows.length;
    failedCount = failedStores.size;
    status = dryRun ? "dry-run" : failedStores.size > 0 ? "partial_success" : "success";
    applyFormulaColumns(allRows, 2);
    const writeRange = getWriteRange(allRows.length);

    console.log("");
    console.log("重建汇总:");
    console.log(`日期范围: ${startDate}~${endDate}`);
    console.log("统计主键=Item ID");
    console.log(`店铺数: ${STORES.length}`);
    console.log(`抓取商品数: ${fetchedCount}`);
    console.log(`最终写入条数: ${writtenCount}`);
    console.log(`零活跃过滤条数: ${skippedCount}`);
    console.log(`失败店铺: ${failedStores.size > 0 ? Array.from(failedStores).join(", ") : "无"}`);
    console.log(`清空范围: ${CLEAR_RANGE}`);
    console.log(`写入范围: ${writeRange}`);
    console.log("写入预览（前 3 行）:");
    console.log(JSON.stringify(allRows.slice(0, 3), null, 2));

    ensureSheetRows(12000, dryRun, confirmWrite);

    if (confirmWrite) {
      writer.clearRange({
        spreadsheetToken: currentReport.spreadsheetToken,
        sheetId: TARGET_SHEET_ID,
        sheetName: TARGET_SHEET_NAME,
        range: CLEAR_RANGE,
        dryRun,
        confirmWrite,
      });
      clearSuccess = true;
      console.log("是否清空成功: 是");

      let nextRow = 2;
      for (const batch of chunkRows(allRows, WRITE_BATCH_SIZE)) {
        const endRow = nextRow + batch.length - 1;
        writer.writeCells({
          spreadsheetToken: currentReport.spreadsheetToken,
          sheetId: TARGET_SHEET_ID,
          sheetName: TARGET_SHEET_NAME,
          range: `A${nextRow}:V${endRow}`,
          rows: batch,
          dryRun,
          confirmWrite,
          allowOverwrite: true,
        });
        nextRow = endRow + 1;
      }
      writeSuccess = true;
    } else {
      writer.writeCells({
        spreadsheetToken: currentReport.spreadsheetToken,
        sheetId: TARGET_SHEET_ID,
        sheetName: TARGET_SHEET_NAME,
        range: writeRange,
        rows: allRows,
        dryRun,
        confirmWrite,
        allowOverwrite: true,
      });
      writeSuccess = true;
    }

    console.log(`是否写入成功: ${writeSuccess ? "是" : "否"}`);
  } catch (error) {
    status = "failed";
    errorMessage = getErrorMessage(error);
    failedCount = failedCount || STORES.length;
    console.log(`重建失败: ${errorMessage}`);
    console.log(`是否清空成功: ${clearSuccess ? "是" : "否"}`);
    console.log(`是否写入成功: ${writeSuccess ? "是" : "否"}`);
  } finally {
    const failedStoreText = failedStores.size > 0 ? Array.from(failedStores).join("|") : "无";
    let remark =
      `CODEX执行：5月销售明细全量重跑覆盖，统计主键=Item ID，日期范围=${startDate}~${endDate}` +
      `，清空范围=${CLEAR_RANGE}，写入条数=${writtenCount}` +
      `，零活跃过滤条数=${skippedCount}，失败店铺=${failedStoreText}`;

    const summarizedErrors = summarizeNonBlockingErrors(nonBlockingErrors);
    if (summarizedErrors) {
      remark += `，非阻塞错误=${summarizedErrors}`;
    }
    if (errorMessage) {
      remark += `，失败原因=${errorMessage}`;
    }

    try {
      logger.append({
        executedAt: new Date().toISOString(),
        taskName: TASK_NAME,
        targetSheet: TARGET_SHEET_NAME,
        operationType: dryRun ? "dry-run" : "replace_rebuild",
        dataSource: "Lingxing Walmart APIs",
        dateRange: `${startDate}~${endDate}`,
        fetchedCount,
        writtenCount,
        updatedCount: 0,
        skippedCount,
        failedCount,
        status,
        errorMessage,
        durationSeconds: Number(((Date.now() - startedAt) / 1000).toFixed(3)),
        runId,
        environment: "local",
        remark,
      });
      logSuccess = true;
    } catch (logError) {
      console.log(`记录操作日志失败: ${getErrorMessage(logError)}`);
    }

    console.log(`日志是否写入成功: ${logSuccess ? "是" : "否"}`);
  }
}

main().catch((error) => {
  console.log(`执行失败: ${getErrorMessage(error)}`);
});
