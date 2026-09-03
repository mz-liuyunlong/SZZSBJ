import { execFileSync } from "child_process";
import currentReport from "../config/currentReportFieldMapping.json";
import { FeishuSheetWriter } from "./feishuSheetWriter";
import { TableOperationLogger } from "./tableOperationLogger";

type Cell = {
  formula?: string;
  cell_styles?: {
    number_format?: string;
  };
};

const LARK_CLI = "./scripts/lark-cli";
const SPREADSHEET_TOKEN = currentReport.spreadsheetToken;
const LOG_SHEET_NAME = "表格操作日志";
const BATCH_SIZE = 25;
const READ_BATCH_SIZE = 500;
const LARK_CLI_TIMEOUT_MS = 120000;
const TASK_NAME = "补写公式列";
const REMARK =
  "CODEX执行：补写毛利润/毛利率/广告占比公式；当日数据和5月销售明细_复盘已同步；毛利润公式已逐项容错；百分比格式为整数，无小数点";

const TARGETS = [
  {
    sheetName: "当日数据",
    sheetId: currentReport.sheets["当日数据"],
    maxRows: 300,
  },
  {
    sheetName: "5月销售明细_复盘",
    sheetId: currentReport.sheets["5月销售明细_复盘"],
    maxRows: 12000,
  },
];

function createRunId(): string {
  return `run_${new Date().toISOString().replace(/[-:.TZ]/g, "")}_${Math.random()
    .toString(36)
    .slice(2, 8)}`;
}

function execLarkCli(args: string[], input?: string): string {
  try {
    return execFileSync(LARK_CLI, args, {
      cwd: process.cwd(),
      encoding: "utf8",
      input,
      maxBuffer: 50 * 1024 * 1024,
      timeout: LARK_CLI_TIMEOUT_MS,
      stdio: input === undefined ? ["ignore", "pipe", "pipe"] : ["pipe", "pipe", "pipe"],
    });
  } catch (error) {
    const err = error as { stderr?: Buffer | string; message?: string };
    const stderr = Buffer.isBuffer(err.stderr) ? err.stderr.toString("utf8") : err.stderr;
    throw new Error(stderr || err.message || "lark-cli command failed");
  }
}

function getArgValue(name: string): string | undefined {
  const prefix = `--${name}=`;
  const found = process.argv.slice(2).find((arg) => arg.startsWith(prefix));
  return found?.slice(prefix.length);
}

function getStartRow(): number {
  const raw = getArgValue("start-row");
  if (!raw) {
    return 2;
  }

  const parsed = Number.parseInt(raw, 10);
  if (!Number.isFinite(parsed) || parsed < 2) {
    throw new Error("--start-row 必须是大于等于 2 的数字");
  }

  return parsed;
}

function readLastDataRow(sheetId: string, maxRows: number): number {
  let lastRow = 1;

  for (let startRow = 1; startRow <= maxRows; startRow += READ_BATCH_SIZE) {
    const endRow = Math.min(startRow + READ_BATCH_SIZE - 1, maxRows);
    const output = execLarkCli([
      "sheets",
      "+cells-get",
      "--spreadsheet-token",
      SPREADSHEET_TOKEN,
      "--sheet-id",
      sheetId,
      "--range",
      `A${startRow}:A${endRow}`,
      "--include",
      "value",
      "--format",
      "json",
    ]);

    const parsed = JSON.parse(output) as {
      ok?: boolean;
      data?: { ranges?: Array<{ cells?: Array<Array<{ value?: unknown }>>; row_indices?: number[] }> };
      error?: { message?: string };
    };

    if (!parsed.ok) {
      throw new Error(parsed.error?.message ?? "读取 A 列失败");
    }

    const range = parsed.data?.ranges?.[0];
    const cells = range?.cells ?? [];
    const rowIndices = range?.row_indices ?? [];

    cells.forEach((row, index) => {
      const value = row[0]?.value;
      const rowNumber = rowIndices[index] ?? startRow + index;
      if (value !== undefined && String(value).trim() !== "") {
        lastRow = rowNumber;
      }
    });
  }

  return lastRow;
}

function grossProfitFormula(row: number): string {
  return (
    `=IFERROR(K${row},0)-IFERROR(L${row},0)` +
    `-IFERROR(N${row}*J${row},0)` +
    `-IFERROR(K${row}*O${row},0)` +
    `-IFERROR((P${row}+Q${row})*J${row}/R${row},0)`
  );
}

function profitFormulaCellsForRows(startRow: number, endRow: number): Cell[][] {
  const rows: Cell[][] = [];

  for (let row = startRow; row <= endRow; row += 1) {
    rows.push([
      {
        formula: grossProfitFormula(row),
        cell_styles: { number_format: "0.00" },
      },
      {
        formula: `=IFERROR(H${row}/K${row},0)`,
        cell_styles: { number_format: "0%" },
      },
    ]);
  }

  return rows;
}

function adRatioFormulaCellsForRows(startRow: number, endRow: number): Cell[][] {
  const rows: Cell[][] = [];

  for (let row = startRow; row <= endRow; row += 1) {
    rows.push([
      {
        formula: `=IFERROR(L${row}/K${row},0)`,
        cell_styles: { number_format: "0%" },
      },
    ]);
  }

  return rows;
}

function percentStyleCells(rowCount: number): Cell[][] {
  return Array.from({ length: rowCount }, () => [{ cell_styles: { number_format: "0%" } }]);
}

function writeCells(sheetId: string, range: string, cells: Cell[][], confirmWrite: boolean): void {
  console.log(`写入预检: ${range}, 行数=${cells.length}, 模式=${confirmWrite ? "confirm-write" : "dry-run"}`);
  if (!confirmWrite) {
    console.log("dry-run: 不调用飞书写入接口");
    console.log(JSON.stringify(cells.slice(0, 2), null, 2));
    return;
  }

  const output = execLarkCli(
    [
      "sheets",
      "+cells-set",
      "--spreadsheet-token",
      SPREADSHEET_TOKEN,
      "--sheet-id",
      sheetId,
      "--range",
      range,
      "--cells",
      "-",
      "--allow-overwrite=true",
      "--format",
      "json",
    ],
    JSON.stringify(cells),
  ).trim();

  if (output) {
    console.log(output);
  }
}

function writeFormulaBatches(
  sheetName: string,
  sheetId: string,
  lastRow: number,
  startAtRow: number,
  confirmWrite: boolean,
): number {
  if (lastRow < 2) {
    console.log(`${sheetName}: 没有数据行，跳过`);
    return 0;
  }

  if (startAtRow > lastRow) {
    console.log(`${sheetName}: 起始行 ${startAtRow} 大于最后一行 ${lastRow}，跳过`);
    return 0;
  }

  let writtenRows = 0;
  for (let startRow = startAtRow; startRow <= lastRow; startRow += BATCH_SIZE) {
    const endRow = Math.min(startRow + BATCH_SIZE - 1, lastRow);
    const profitFormulaRange = `H${startRow}:I${endRow}`;
    const adRatioFormulaRange = `M${startRow}:M${endRow}`;
    const styleRange = `O${startRow}:O${endRow}`;
    const rowCount = endRow - startRow + 1;

    console.log(`${sheetName}: 写入毛利润/毛利率公式 ${profitFormulaRange}`);
    writeCells(sheetId, profitFormulaRange, profitFormulaCellsForRows(startRow, endRow), confirmWrite);

    console.log(`${sheetName}: 写入广告占比公式 ${adRatioFormulaRange}`);
    writeCells(sheetId, adRatioFormulaRange, adRatioFormulaCellsForRows(startRow, endRow), confirmWrite);

    console.log(`${sheetName}: 设置佣金率格式 ${styleRange}`);
    writeCells(sheetId, styleRange, percentStyleCells(rowCount), confirmWrite);

    writtenRows += rowCount;
  }

  return writtenRows;
}

async function main(): Promise<void> {
  const startedAt = Date.now();
  const runId = createRunId();
  let totalRows = 0;
  let logSuccess = false;
  let status = "success";
  let errorMessage = "";
  const onlySheet = getArgValue("only-sheet");
  const startAtRow = getStartRow();
  const targets = onlySheet ? TARGETS.filter((target) => target.sheetName === onlySheet) : TARGETS;
  const confirmWrite = process.argv.includes("--confirm-write");
  const dryRun = !confirmWrite;

  if (onlySheet && targets.length === 0) {
    throw new Error(`未知 sheet: ${onlySheet}`);
  }

  console.log("补写公式列");
  console.log(`运行ID: ${runId}`);
  console.log(`写入模式: ${confirmWrite ? "confirm-write" : "dry-run"}`);
  console.log("只写 H/I/M 公式和 H/I/M/O 数字格式，不修改 J/K/L/N/O/P/Q/R 的值");
  console.log(`执行范围: ${onlySheet ?? "当日数据,5月销售明细_复盘"}，起始行: ${startAtRow}`);

  try {
    for (const target of targets) {
      const lastRow = readLastDataRow(target.sheetId, target.maxRows);
      console.log(`${target.sheetName}: 最后一行 ${lastRow}`);
      totalRows += writeFormulaBatches(target.sheetName, target.sheetId, lastRow, startAtRow, confirmWrite);
    }
  } catch (error) {
    status = "failed";
    errorMessage = error instanceof Error ? error.message : String(error);
    console.log(`公式写入失败: ${errorMessage}`);
  } finally {
    const writer = new FeishuSheetWriter();
    const logger = new TableOperationLogger(writer, {
      spreadsheetToken: SPREADSHEET_TOKEN,
      logSheetId: currentReport.sheets[LOG_SHEET_NAME],
      dryRun,
      confirmWrite,
    });

    try {
      logger.append({
        executedAt: new Date().toISOString(),
        taskName: TASK_NAME,
        targetSheet: onlySheet ?? "当日数据,5月销售明细_复盘",
        operationType: "formula",
        dataSource: "lark-cli",
        dateRange: "all data rows",
        fetchedCount: 0,
        writtenCount: totalRows,
        updatedCount: totalRows,
        skippedCount: 0,
        failedCount: status === "success" ? 0 : 1,
        status: dryRun && status === "success" ? "dry-run" : status,
        errorMessage,
        durationSeconds: Number(((Date.now() - startedAt) / 1000).toFixed(3)),
        runId,
        environment: "local",
        remark: status === "success" ? REMARK : `${REMARK}；失败原因：${errorMessage}`,
      });
      logSuccess = true;
    } catch (logError) {
      console.log(`记录操作日志失败: ${logError instanceof Error ? logError.message : String(logError)}`);
    }

    console.log(`日志是否写入成功: ${logSuccess ? "是" : "否"}`);
  }

  if (status !== "success") {
    throw new Error(errorMessage);
  }
}

main().catch((error) => {
  console.log(`执行失败: ${error instanceof Error ? error.message : String(error)}`);
});
