import { execFileSync } from "child_process";

export type CellValue = string | number | boolean | null;
export interface SheetCellPayload {
  value?: CellValue;
  formula?: string;
  cell_styles?: {
    number_format?: string;
  };
}
export type SheetCell = CellValue | SheetCellPayload;
export type SheetRow = SheetCell[];

export interface WriteCellsOptions {
  spreadsheetToken: string;
  sheetId: string;
  sheetName: string;
  range: string;
  rows: SheetRow[];
  dryRun: boolean;
  confirmWrite: boolean;
  allowOverwrite?: boolean;
}

export interface ReadCellsOptions {
  spreadsheetToken: string;
  sheetId: string;
  range: string;
}

export interface ClearRangeOptions {
  spreadsheetToken: string;
  sheetId: string;
  sheetName: string;
  range: string;
  dryRun: boolean;
  confirmWrite: boolean;
}

const LARK_CLI = "./scripts/lark-cli";
const AUTO_INSERT_ROW_COUNT = 500;

export class FeishuSheetWriter {
  getRowCount(options: { spreadsheetToken: string; sheetId: string; sheetName: string }): number {
    return getSheetRowCount(options.spreadsheetToken, options.sheetId, options.sheetName);
  }

  ensureRows(options: {
    spreadsheetToken: string;
    sheetId: string;
    sheetName: string;
    requiredEndRow: number;
    dryRun: boolean;
    confirmWrite: boolean;
  }): void {
    ensureSheetHasRows(options);
  }

  writeCells(options: WriteCellsOptions): void {
    validateWriteOptions(options);

    const rowCount = options.rows.length;
    const columnCount = Math.max(...options.rows.map((row) => row.length));

    console.log("飞书写入预检:");
    console.log(`目标 Sheet: ${options.sheetName} (${options.sheetId})`);
    console.log(`目标 Range: ${options.range}`);
    console.log(`行数: ${rowCount}`);
    console.log(`列数: ${columnCount}`);
    console.log(`模式: ${options.confirmWrite ? "confirm-write" : "dry-run"}`);

    if (options.dryRun || !options.confirmWrite) {
      console.log("dry-run: 不调用飞书写入接口");
      console.log(`预览前 ${Math.min(3, options.rows.length)} 行:`);
      console.log(JSON.stringify(options.rows.slice(0, 3), null, 2));
      return;
    }

    ensureSheetHasRows(options);

    const cells = options.rows.map((row) => row.map(toCellPayload));
    const args = [
      "sheets",
      "+cells-set",
      "--spreadsheet-token",
      options.spreadsheetToken,
      "--sheet-id",
      options.sheetId,
      "--range",
      options.range,
      "--cells",
      "-",
      `--allow-overwrite=${String(options.allowOverwrite ?? true)}`,
    ];

    const output = execLarkCli(args, JSON.stringify(cells)).trim();

    if (output) {
      console.log(output);
    }
  }

  readValues(options: ReadCellsOptions): CellValue[][] {
    const output = execLarkCli([
      "sheets",
      "+cells-get",
      "--spreadsheet-token",
      options.spreadsheetToken,
      "--sheet-id",
      options.sheetId,
      "--range",
      options.range,
      "--include",
      "value",
      "--format",
      "json",
    ]);
    const parsed = JSON.parse(output) as {
      ok?: boolean;
      data?: { ranges?: Array<{ cells?: Array<Array<{ value?: CellValue }>> }> };
      error?: { message?: string };
    };

    if (!parsed.ok) {
      throw new Error(parsed.error?.message ?? "Failed to read Feishu cells");
    }

    return (
      parsed.data?.ranges?.[0]?.cells?.map((row) =>
        row.map((cell) => (cell.value === undefined ? null : cell.value)),
      ) ?? []
    );
  }

  clearRange(options: ClearRangeOptions): void {
    validateClearOptions(options);

    console.log("飞书清理预检:");
    console.log(`目标 Sheet: ${options.sheetName} (${options.sheetId})`);
    console.log(`目标 Range: ${options.range}`);
    console.log(`清理范围: content only`);
    console.log(`模式: ${options.confirmWrite ? "confirm-write" : "dry-run"}`);

    if (options.dryRun || !options.confirmWrite) {
      console.log("dry-run: 不调用飞书清理接口");
      return;
    }

    const args = [
      "sheets",
      "+cells-clear",
      "--spreadsheet-token",
      options.spreadsheetToken,
      "--sheet-id",
      options.sheetId,
      "--range",
      options.range,
      "--scope",
      "content",
      "--yes",
    ];

    const output = execLarkCli(args).trim();

    if (output) {
      console.log(output);
    }
  }
}

function ensureSheetHasRows(options: {
  spreadsheetToken: string;
  sheetId: string;
  sheetName: string;
  requiredEndRow?: number;
  range?: string;
  dryRun: boolean;
  confirmWrite: boolean;
}): void {
  const requiredEndRow = options.requiredEndRow ?? (options.range ? getRangeEndRow(options.range) : null);
  if (!requiredEndRow) {
    console.log(`自动扩容检查: 无法从 Range ${options.range ?? ""} 解析结束行，跳过`);
    return;
  }

  const currentRowCount = getSheetRowCount(options.spreadsheetToken, options.sheetId, options.sheetName);
  if (requiredEndRow <= currentRowCount) {
    console.log(`自动扩容检查: 当前行数 ${currentRowCount}，目标结束行 ${requiredEndRow}，无需新增行`);
    return;
  }

  const missingRowCount = requiredEndRow - currentRowCount;
  const insertCount = Math.max(missingRowCount * 2, AUTO_INSERT_ROW_COUNT);
  console.log(
    `自动扩容检查: 当前行数 ${currentRowCount}，目标结束行 ${requiredEndRow}，缺少 ${missingRowCount} 行，自动新增 ${insertCount} 行`,
  );

  if (options.dryRun || !options.confirmWrite) {
    console.log("dry-run: 不调用飞书新增行接口");
    return;
  }

  const output = execLarkCli([
    "sheets",
    "+dim-insert",
    "--spreadsheet-token",
    options.spreadsheetToken,
    "--sheet-id",
    options.sheetId,
    "--position",
    String(Math.max(currentRowCount, 1)),
    "--count",
    String(insertCount),
    "--inherit-style",
    "before",
    "--format",
    "json",
  ]).trim();

  if (output) {
    console.log(output);
  }
}

function getSheetRowCount(spreadsheetToken: string, sheetId: string, sheetName: string): number {
  const output = execLarkCli([
    "sheets",
    "+sheet-info",
    "--spreadsheet-token",
    spreadsheetToken,
    "--sheet-id",
    sheetId,
    "--format",
    "json",
  ]);

  const parsed = JSON.parse(output) as {
    ok?: boolean;
    data?: { range?: string };
    error?: { message?: string };
  };

  if (!parsed.ok) {
    throw new Error(parsed.error?.message ?? `读取 ${sheetName} 行数失败`);
  }

  const range = parsed.data?.range ?? "";
  const match = /[A-Z]+1:[A-Z]+(\d+)/.exec(range);
  if (!match) {
    throw new Error(`无法解析 ${sheetName} 当前行数: ${range}`);
  }

  return Number(match[1]);
}

function getRangeEndRow(range: string): number | null {
  const normalizedRange = range.includes("!") ? range.split("!").pop() ?? range : range;
  const match = /[A-Z]+(\d+):[A-Z]+(\d+)$/.exec(normalizedRange);
  if (!match) {
    return null;
  }

  return Number(match[2]);
}

function normalizeCellValue(value: unknown): CellValue {
  if (value === undefined || value === null) {
    return "";
  }

  if (typeof value === "string" || typeof value === "number" || typeof value === "boolean") {
    return value;
  }

  if (Array.isArray(value)) {
    return value.map((item) => String(normalizeCellValue(item) ?? "")).join("");
  }

  if (typeof value === "object") {
    const record = value as Record<string, unknown>;
    for (const key of ["value", "text", "formattedValue", "string", "number", "result"]) {
      if (record[key] !== undefined && record[key] !== null) {
        return normalizeCellValue(record[key]);
      }
    }
  }

  return "";
}

function toCellPayload(value: SheetCell): SheetCellPayload {
  if (
    value !== null &&
    typeof value === "object" &&
    ("value" in value || "formula" in value || "cell_styles" in value)
  ) {
    const payload = value as SheetCellPayload;
    return {
      ...(payload.value !== undefined ? { value: normalizeCellValue(payload.value) } : {}),
      ...(payload.formula !== undefined ? { formula: payload.formula } : {}),
      ...(payload.cell_styles !== undefined ? { cell_styles: payload.cell_styles } : {}),
    };
  }

  return { value: normalizeCellValue(value) };
}

function validateWriteOptions(options: WriteCellsOptions): void {
  if (!options.confirmWrite && !options.dryRun) {
    throw new Error("Writes must be dry-run unless --confirm-write is provided");
  }

  if (!options.rows.length) {
    throw new Error("No rows to write");
  }

  if (!options.rows.every((row) => row.length > 0)) {
    throw new Error("Every written row must contain at least one column");
  }

  if (isWholeSheetRange(options.range)) {
    throw new Error("Refusing to write a whole sheet range");
  }

  if (isProtectedManualSheet(options.sheetName)) {
    throw new Error(`Refusing to write protected manual sheet: ${options.sheetName}`);
  }
}

function validateClearOptions(options: ClearRangeOptions): void {
  if (!options.confirmWrite && !options.dryRun) {
    throw new Error("Clears must be dry-run unless --confirm-write is provided");
  }

  if (isWholeSheetRange(options.range)) {
    throw new Error("Refusing to clear a whole sheet range");
  }

  if (isProtectedManualSheet(options.sheetName)) {
    throw new Error(`Refusing to clear protected manual sheet: ${options.sheetName}`);
  }
}

function isWholeSheetRange(range: string): boolean {
  return /^[A-Z]+:[A-Z]+$/.test(range) || /^\d+:\d+$/.test(range);
}

function isProtectedManualSheet(sheetName: string): boolean {
  return sheetName === "ItemID负责人";
}

function execLarkCli(args: string[], input?: string): string {
  try {
    return execFileSync(LARK_CLI, args, {
      cwd: process.cwd(),
      encoding: "utf8",
      input,
      maxBuffer: 20 * 1024 * 1024,
      stdio: input === undefined ? ["ignore", "pipe", "pipe"] : ["pipe", "pipe", "pipe"],
    });
  } catch (error) {
    const err = error as { stderr?: Buffer | string; message?: string };
    const stderr = Buffer.isBuffer(err.stderr) ? err.stderr.toString("utf8") : err.stderr;
    throw new Error(stderr || err.message || "lark-cli command failed");
  }
}
