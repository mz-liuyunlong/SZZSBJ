import { FeishuSheetWriter, SheetRow } from "./feishuSheetWriter";

export interface OperationLogEntry {
  executedAt: string;
  taskName: string;
  targetSheet: string;
  operationType: string;
  dataSource: string;
  dateRange: string;
  fetchedCount: number;
  writtenCount: number;
  updatedCount: number;
  skippedCount: number;
  failedCount: number;
  status: string;
  errorMessage: string;
  durationSeconds: number;
  runId: string;
  environment: string;
  remark: string;
}

export interface OperationLoggerOptions {
  spreadsheetToken: string;
  logSheetId: string;
  dryRun: boolean;
  confirmWrite: boolean;
}

const LOG_SHEET_NAME = "表格操作日志";
const LOG_COLUMNS = 17;
const MAX_APPEND_ATTEMPTS = 500;

export class TableOperationLogger {
  constructor(
    private readonly writer: FeishuSheetWriter,
    private readonly options: OperationLoggerOptions,
  ) {}

  append(entry: OperationLogEntry): void {
    // 2026-07-18 飞书副本链路退役：表格操作日志默认静默跳过（此前每日被lark-cli写入门禁拦截产生假报错）。
    // 如需恢复：环境变量设 FEISHU_TABLE_LOG_ENABLED=1（且需同时放行lark-cli写门禁才能真正写入）。
    if (process.env.FEISHU_TABLE_LOG_ENABLED !== "1") {
      console.log(`表格操作日志已停用，跳过记录（runId=${entry.runId}, status=${entry.status}）`);
      return;
    }
    const row = toLogRow(entry);
    const nextRowNumber = this.options.confirmWrite
      ? this.findNextLogRowNumber()
      : 2;
    let targetRowNumber = nextRowNumber;
    let range = `A${targetRowNumber}:Q${targetRowNumber}`;

    console.log("准备记录表格操作日志:");
    console.log(`运行ID: ${entry.runId}`);
    console.log(`执行状态: ${entry.status}`);
    console.log(`日志 Range: ${range}`);

    for (let attempt = 0; attempt < MAX_APPEND_ATTEMPTS; attempt += 1) {
      try {
        this.writer.writeCells({
          spreadsheetToken: this.options.spreadsheetToken,
          sheetId: this.options.logSheetId,
          sheetName: LOG_SHEET_NAME,
          range,
          rows: [row],
          dryRun: this.options.dryRun,
          confirmWrite: this.options.confirmWrite,
          allowOverwrite: false,
        });
        return;
      } catch (error) {
        const message = error instanceof Error ? error.message : String(error);
        if (!message.includes("already has data") || this.options.dryRun || !this.options.confirmWrite) {
          throw error;
        }
        targetRowNumber += 1;
        range = `A${targetRowNumber}:Q${targetRowNumber}`;
        console.log(`日志目标行已有数据，尝试下一行: ${range}`);
      }
    }

    throw new Error(`写入操作日志失败：连续 ${MAX_APPEND_ATTEMPTS} 行都有数据`);
  }

  private findNextLogRowNumber(): number {
    const rows = this.writer.readValues({
      spreadsheetToken: this.options.spreadsheetToken,
      sheetId: this.options.logSheetId,
      range: "A1:A10000",
    });
    const lastNonEmptyIndex = rows.reduce((lastIndex, row, index) => {
      return row.some((value) => value !== null && String(value).trim() !== "")
        ? index
        : lastIndex;
    }, -1);

    return Math.max(lastNonEmptyIndex + 2, 2);
  }
}

function toLogRow(entry: OperationLogEntry): SheetRow {
  return [
    entry.executedAt,
    entry.taskName,
    entry.targetSheet,
    entry.operationType,
    entry.dataSource,
    entry.dateRange,
    entry.fetchedCount,
    entry.writtenCount,
    entry.updatedCount,
    entry.skippedCount,
    entry.failedCount,
    entry.status,
    entry.errorMessage,
    entry.durationSeconds,
    entry.runId,
    entry.environment,
    entry.remark,
  ];
}
