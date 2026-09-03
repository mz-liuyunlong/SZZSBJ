import currentReport from "../config/currentReportFieldMapping.json";
import { execFileSync } from "child_process";
import { FeishuSheetWriter, SheetRow } from "./feishuSheetWriter";
import {
  STORES,
  applyFormulaColumns,
  generateDailyRowsForDate,
} from "./syncDailyBaseData";
import { TableOperationLogger } from "./tableOperationLogger";

const TARGET_SHEET_NAME = "5月销售明细_复盘";
const LOG_SHEET_NAME = "表格操作日志";
const TASK_NAME = "补充5月销售明细";
const WRITE_BATCH_SIZE = 200;
const READ_BATCH_SIZE = 500;
const LARK_CLI = "./scripts/lark-cli";
const SAFE_MIN_APPEND_ROW = 2;

function getArg(name: string, defaultValue = ""): string {
  const prefix = `--${name}=`;
  const arg = process.argv.find((item) => item.startsWith(prefix));
  return arg ? arg.slice(prefix.length) : defaultValue;
}

function getNumberArg(name: string, defaultValue = 0): number {
  const raw = getArg(name);
  if (!raw) {
    return defaultValue;
  }

  const parsed = Number.parseInt(raw, 10);
  if (!Number.isFinite(parsed) || parsed < 0) {
    throw new Error(`--${name} 必须是非负整数`);
  }

  return parsed;
}

function createRunId(): string {
  return `run_${new Date().toISOString().replace(/[-:.TZ]/g, "")}_${Math.random()
    .toString(36)
    .slice(2, 8)}`;
}

function normalizeKeyPart(value: unknown): string {
  return String(value ?? "").trim();
}

function buildUniqueKey(row: SheetRow): string {
  return [
    normalizeKeyPart(row[0]),
    normalizeKeyPart(row[1]),
    normalizeKeyPart(row[2]),
  ].join("|");
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

function readExistingKeys(): { keys: Set<string>; nextRow: number } {
  const keys = new Set<string>();
  let lastNonEmptyRow = 1;
  const rowCount = getSheetRowCount();

  for (let startRow = 1; startRow <= rowCount; startRow += READ_BATCH_SIZE) {
    const endRow = Math.min(startRow + READ_BATCH_SIZE - 1, rowCount);
    const rows = readValuesWithRowNumbers(`A${startRow}:V${endRow}`);

    rows.forEach(({ row, rowNumber }) => {
      if (row.some((value) => value !== null && String(value).trim() !== "")) {
        lastNonEmptyRow = Math.max(lastNonEmptyRow, rowNumber);
      }

      if (rowNumber === 1) {
        return;
      }

      const key = buildUniqueKey(row);
      if (key.split("|").every(Boolean)) {
        keys.add(key);
      }
    });
  }

  return {
    keys,
    nextRow: Math.max(lastNonEmptyRow + 1, SAFE_MIN_APPEND_ROW),
  };
}

function readValuesWithRowNumbers(range: string): Array<{ row: SheetRow; rowNumber: number }> {
  const output = execLarkCli([
    "sheets",
    "+cells-get",
    "--spreadsheet-token",
    currentReport.spreadsheetToken,
    "--sheet-id",
    currentReport.sheets[TARGET_SHEET_NAME],
    "--range",
    range,
    "--include",
    "value",
    "--format",
    "json",
  ]);

  const parsed = JSON.parse(output) as {
    ok?: boolean;
    data?: {
      ranges?: Array<{
        cells?: Array<Array<{ value?: string | number | boolean | null }>>;
        row_indices?: number[];
      }>;
    };
    error?: { message?: string };
  };

  if (!parsed.ok) {
    throw new Error(parsed.error?.message ?? "读取 5月销售明细 现有数据失败");
  }

  const dataRange = parsed.data?.ranges?.[0];
  const cells = dataRange?.cells ?? [];
  const rowIndices = dataRange?.row_indices ?? [];

  return cells.map((row, index) => ({
    row: row.map((cell) => (cell.value === undefined ? null : cell.value)),
    rowNumber: rowIndices[index] !== undefined ? rowIndices[index] : index + 1,
  }));
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

function chunkRows(rows: SheetRow[], size: number): SheetRow[][] {
  const chunks: SheetRow[][] = [];
  for (let index = 0; index < rows.length; index += size) {
    chunks.push(rows.slice(index, index + size));
  }
  return chunks;
}

function getSheetRowCount(): number {
  const output = execLarkCli([
    "sheets",
    "+sheet-info",
    "--spreadsheet-token",
    currentReport.spreadsheetToken,
    "--sheet-id",
    currentReport.sheets[TARGET_SHEET_NAME],
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
  if (requiredEndRow < currentRowCount) {
    console.log(`5月销售明细当前行数 ${currentRowCount}，无需扩展`);
    return;
  }

  const insertCount = requiredEndRow - currentRowCount + 1;
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
    currentReport.sheets[TARGET_SHEET_NAME],
    "--position",
    String(Math.max(currentRowCount - 1, 1)),
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
  const skipExistingWrittenRows = getNumberArg("skipExistingWrittenRows");
  const forcedAppendStartRow = getNumberArg("appendStartRow");
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
  let appendCount = 0;
  let duplicateSkippedCount = 0;
  let zeroActivitySkippedCount = 0;
  let failedCount = 0;
  let logSuccess = false;
  let status = "success";
  let errorMessage = "";
  let remark = "";
  const failedStores = new Set<string>();
  const nonBlockingErrors: string[] = [];

  console.log("补充5月销售明细");
  console.log(`运行ID: ${runId}`);
  console.log(`写入模式: ${confirmWrite ? "confirm-write" : "dry-run"}`);
  console.log(`补数范围: ${startDate}~${endDate}`);
  console.log("统计主键=Item ID");
  console.log("去重键=日期+店铺+商品ID");
  console.log(`目标 Sheet: ${TARGET_SHEET_NAME} (${currentReport.sheets[TARGET_SHEET_NAME]})`);

  try {
    const dates = getDateRange(startDate, endDate);
    const existing = readExistingKeys();
    let appendRows: SheetRow[] = [];
    const seenKeys = new Set(existing.keys);
    const appendStartRow = forcedAppendStartRow || existing.nextRow;

    console.log(`现有去重键数量: ${existing.keys.size}`);
    console.log(`追加起始行: ${appendStartRow}`);
    if (forcedAppendStartRow > 0) {
      console.log(`手动指定追加起始行: ${forcedAppendStartRow}`);
    }
    if (skipExistingWrittenRows > 0) {
      console.log(`续跑跳过已写入行数: ${skipExistingWrittenRows}`);
    }

    for (const date of dates) {
      console.log("");
      console.log(`开始生成日期: ${date}`);
      const generated = await generateDailyRowsForDate(date, writer);
      fetchedCount += generated.totals.fetchedCount;
      zeroActivitySkippedCount += generated.skippedCount;
      generated.failedStores.forEach((store) => failedStores.add(`${date}:${store}`));
      nonBlockingErrors.push(...generated.nonBlockingErrors.map((message) => `${date}:${message}`));

      for (const row of generated.rows) {
        const key = buildUniqueKey(row);
        if (seenKeys.has(key)) {
          duplicateSkippedCount += 1;
          continue;
        }

        seenKeys.add(key);
        appendRows.push(row);
      }
    }

    if (skipExistingWrittenRows > 0) {
      const resumeSkippedCount = Math.min(skipExistingWrittenRows, appendRows.length);
      appendRows = appendRows.slice(resumeSkippedCount);
      duplicateSkippedCount += resumeSkippedCount;
      console.log(`续跑实际跳过行数: ${resumeSkippedCount}`);
    }

    appendCount = appendRows.length;
    applyFormulaColumns(appendRows, appendStartRow);

    console.log("");
    console.log("补数汇总:");
    console.log(`数据范围: ${startDate}~${endDate}`);
    console.log(`店铺数: ${STORES.length}`);
    console.log(`抓取商品数: ${fetchedCount}`);
    console.log(`追加写入条数: ${appendCount}`);
    console.log(`重复跳过条数: ${duplicateSkippedCount}`);
    console.log(`零活跃过滤条数: ${zeroActivitySkippedCount}`);
    console.log(`失败店铺: ${failedStores.size > 0 ? Array.from(failedStores).join(", ") : "无"}`);
    console.log(`实际追加起始行: ${appendStartRow}`);
    console.log("写入预览（前 3 行）:");
    console.log(JSON.stringify(appendRows.slice(0, 3), null, 2));

    if (appendRows.length > 0) {
      ensureSheetRows(appendStartRow + appendRows.length - 1, dryRun, confirmWrite);

      let nextRow = appendStartRow;
      for (const batch of chunkRows(appendRows, WRITE_BATCH_SIZE)) {
        const endRow = nextRow + batch.length - 1;
        const range = `A${nextRow}:V${endRow}`;
        writer.writeCells({
          spreadsheetToken: currentReport.spreadsheetToken,
          sheetId: currentReport.sheets[TARGET_SHEET_NAME],
          sheetName: TARGET_SHEET_NAME,
          range,
          rows: batch,
          dryRun,
          confirmWrite,
          allowOverwrite: true,
        });
        nextRow = endRow + 1;
      }
    } else {
      console.log("无新增行，跳过写入 5月销售明细");
    }

    failedCount = failedStores.size;
    status = dryRun ? "dry-run" : failedStores.size > 0 ? "partial_success" : "success";
  } catch (error) {
    status = "failed";
    errorMessage = error instanceof Error ? error.message : String(error);
    failedCount = STORES.length;
    console.log(`补数失败: ${errorMessage}`);
  } finally {
    const failedStoreText = failedStores.size > 0 ? Array.from(failedStores).join("|") : "无";
    remark =
      `CODEX执行：修复统计主键为Item ID；补充5月销售明细，补数范围=${startDate}~${endDate}` +
      `，去重键=日期+店铺+商品ID，追加写入条数=${appendCount}` +
      `，重复跳过条数=${duplicateSkippedCount}，零活跃过滤条数=${zeroActivitySkippedCount}` +
      `，失败店铺=${failedStoreText}`;

    if (nonBlockingErrors.length > 0) {
      remark += `，非阻塞错误=${nonBlockingErrors.join("；")}`;
    }
    if (errorMessage) {
      remark += `，失败原因=${errorMessage}`;
    }

    try {
      logger.append({
        executedAt: new Date().toISOString(),
        taskName: TASK_NAME,
        targetSheet: TARGET_SHEET_NAME,
        operationType: dryRun ? "dry-run" : "append",
        dataSource: "Item ID daily data generator",
        dateRange: `${startDate}~${endDate}`,
        fetchedCount,
        writtenCount: appendCount,
        updatedCount: 0,
        skippedCount: duplicateSkippedCount + zeroActivitySkippedCount,
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
      console.log(`记录操作日志失败: ${logError instanceof Error ? logError.message : String(logError)}`);
    }

    console.log(`日志是否写入成功: ${logSuccess ? "是" : "否"}`);
    if (status === "failed") {
      process.exitCode = 1;
    }
  }
}

main().catch((error) => {
  console.log(`执行失败: ${error instanceof Error ? error.message : String(error)}`);
  process.exitCode = 1;
});
