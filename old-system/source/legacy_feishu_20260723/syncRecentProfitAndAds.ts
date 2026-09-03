import currentReport from "../config/currentReportFieldMapping.json";
import { FeishuSheetWriter, SheetRow } from "./feishuSheetWriter";
import { TableOperationLogger } from "./tableOperationLogger";

const TASK_NAME = "同步近期利润与广告";
const TARGET_SHEET_NAME = "近期利润与广告";
const DETAIL_SHEET_NAME = "5月销售明细_复盘";
const DETAIL_SHEET_ID = currentReport.sheets[DETAIL_SHEET_NAME];
const LOG_SHEET_NAME = "表格操作日志";
const LEGACY_DETAIL_FORMULA_REF = "'5月销售明细'!";
const DETAIL_READ_START_ROW = 2;
const DETAIL_READ_BATCH_SIZE = 500;
const RECENT_CLEAR_RANGE = "A2:R10000";
const MAX_RECENT_DATA_ROWS = 9999;
const WRITE_BATCH_SIZE = 100;

interface RecentBaseItem {
  storeName: string;
  itemId: string;
  msku: string;
  sku: string;
  productName: string;
  owner: string;
}

function createRunId(): string {
  return `run_${new Date().toISOString().replace(/[-:.TZ]/g, "")}_${Math.random()
    .toString(36)
    .slice(2, 8)}`;
}

function unwrapCellValue(value: unknown): unknown {
  if (Array.isArray(value)) {
    return value.map((item) => normalizeText(item)).join("");
  }
  if (value && typeof value === "object") {
    const record = value as Record<string, unknown>;
    for (const key of ["text", "value", "formattedValue", "string", "number", "result"]) {
      if (record[key] !== undefined && record[key] !== null) {
        return unwrapCellValue(record[key]);
      }
    }
    return "";
  }
  return value;
}

function normalizeText(value: unknown): string {
  return String(unwrapCellValue(value) ?? "").trim();
}

function normalizeBaseText(value: unknown): string {
  const text = normalizeText(value);
  return text === "[object Object]" ? "" : text;
}

function parseDateText(value: unknown): string | null {
  const text = normalizeText(value);
  const match = /^(\d{4})-(\d{2})-(\d{2})/.exec(text);
  if (!match) {
    return null;
  }

  return `${match[1]}-${match[2]}-${match[3]}`;
}

function addDays(dateText: string, days: number): string {
  const [year, month, day] = dateText.split("-").map(Number);
  const date = new Date(Date.UTC(year, month - 1, day));
  date.setUTCDate(date.getUTCDate() + days);
  return date.toISOString().slice(0, 10);
}

function buildRecentDates(latestDate: string, dayCount: number): string[] {
  const dates: string[] = [];
  for (let offset = dayCount - 1; offset >= 0; offset -= 1) {
    dates.push(addDays(latestDate, -offset));
  }
  return dates;
}

function findLatestDate(rows: SheetRow[]): string {
  const dates = rows
    .flatMap((row) => row.map(parseDateText))
    .filter((date): date is string => Boolean(date));

  if (dates.length === 0) {
    throw new Error("5月销售明细 A列没有可识别日期");
  }

  dates.sort();
  return dates[dates.length - 1];
}

function buildSumifsFormula(valueColumn: string, dates: string[], rowNumber: number): string {
  const pieces = dates.map((date) => {
    return (
      `SUMIFS('${DETAIL_SHEET_NAME}'!${valueColumn}:${valueColumn},` +
      `'${DETAIL_SHEET_NAME}'!C:C,$B${rowNumber},` +
      `'${DETAIL_SHEET_NAME}'!B:B,$A${rowNumber}&"*",` +
      `'${DETAIL_SHEET_NAME}'!A:A,"${date}")`
    );
  });

  return `=IFERROR(${pieces.join("+")},0)`;
}

function buildFormulaRow(rowNumber: number, recent3Dates: string[], recent5Dates: string[]): SheetRow {
  return [
    {
      formula: buildSumifsFormula("K", recent3Dates, rowNumber),
      cell_styles: { number_format: "0.00" },
    },
    {
      formula: buildSumifsFormula("J", recent3Dates, rowNumber),
      cell_styles: { number_format: "0" },
    },
    {
      formula: buildSumifsFormula("L", recent3Dates, rowNumber),
      cell_styles: { number_format: "0.00" },
    },
    {
      formula: `=IFERROR(I${rowNumber}/G${rowNumber},0)`,
      cell_styles: { number_format: "0%" },
    },
    {
      formula: buildSumifsFormula("H", recent3Dates, rowNumber),
      cell_styles: { number_format: "0.00" },
    },
    {
      formula: `=IFERROR(K${rowNumber}/G${rowNumber},0)`,
      cell_styles: { number_format: "0%" },
    },
    {
      formula: buildSumifsFormula("K", recent5Dates, rowNumber),
      cell_styles: { number_format: "0.00" },
    },
    {
      formula: buildSumifsFormula("J", recent5Dates, rowNumber),
      cell_styles: { number_format: "0" },
    },
    {
      formula: buildSumifsFormula("L", recent5Dates, rowNumber),
      cell_styles: { number_format: "0.00" },
    },
    {
      formula: `=IFERROR(O${rowNumber}/M${rowNumber},0)`,
      cell_styles: { number_format: "0%" },
    },
    {
      formula: buildSumifsFormula("H", recent5Dates, rowNumber),
      cell_styles: { number_format: "0.00" },
    },
    {
      formula: `=IFERROR(Q${rowNumber}/M${rowNumber},0)`,
      cell_styles: { number_format: "0%" },
    },
  ];
}

function buildRecentReportRow(item: RecentBaseItem, rowNumber: number, recent3Dates: string[], recent5Dates: string[]): SheetRow {
  return [
    normalizeBaseText(item.storeName),
    normalizeBaseText(item.itemId),
    normalizeBaseText(item.msku),
    normalizeBaseText(item.sku),
    normalizeBaseText(item.productName),
    normalizeBaseText(item.owner),
    ...buildFormulaRow(rowNumber, recent3Dates, recent5Dates),
  ];
}

function collectFormulas(rows: SheetRow[]): string[] {
  return rows.flatMap((row) =>
    row.flatMap((cell) => {
      if (cell && typeof cell === "object" && "formula" in cell && typeof cell.formula === "string") {
        return [cell.formula];
      }
      return [];
    }),
  );
}

function assertNoLegacyDetailFormulaReference(rows: SheetRow[]): void {
  const formula = collectFormulas(rows).find((item) => item.includes(LEGACY_DETAIL_FORMULA_REF));
  if (formula) {
    throw new Error(`公式仍引用旧销售明细 Sheet：${formula}`);
  }
}

function chunkRows(rows: SheetRow[], size: number): SheetRow[][] {
  const chunks: SheetRow[][] = [];
  for (let index = 0; index < rows.length; index += size) {
    chunks.push(rows.slice(index, index + size));
  }
  return chunks;
}

function readDetailRows(writer: FeishuSheetWriter): SheetRow[] {
  const rows: SheetRow[] = [];

  const sheetRowCount = writer.getRowCount({
    spreadsheetToken: currentReport.spreadsheetToken,
    sheetId: DETAIL_SHEET_ID,
    sheetName: DETAIL_SHEET_NAME,
  });
  console.log(`${DETAIL_SHEET_NAME} 实际行数: ${sheetRowCount}`);

  for (let startRow = DETAIL_READ_START_ROW; startRow <= sheetRowCount; startRow += DETAIL_READ_BATCH_SIZE) {
    const endRow = Math.min(startRow + DETAIL_READ_BATCH_SIZE - 1, sheetRowCount);
    const range = `A${startRow}:G${endRow}`;
    const chunk = writer.readValues({
      spreadsheetToken: currentReport.spreadsheetToken,
      sheetId: DETAIL_SHEET_ID,
      range,
    });
    const validRows = chunk.filter((row) => normalizeText(row[0]) && normalizeText(row[1]) && normalizeText(row[2]));
    rows.push(...validRows);
    console.log(`读取 ${DETAIL_SHEET_NAME} ${range}: 有效数据 ${validRows.length} 行`);
    if (chunk.length < DETAIL_READ_BATCH_SIZE) break;
  }

  return rows;
}

function buildBaseItemsFromDetailRows(detailRows: SheetRow[]): RecentBaseItem[] {
  const map = new Map<string, RecentBaseItem>();

  for (const row of detailRows) {
    const storeName = normalizeText(row[1]); // 5月销售明细 B列
    const itemId = normalizeText(row[2]); // 5月销售明细 C列
    if (!storeName || !itemId) {
      continue;
    }

    const key = `${storeName}__${itemId}`;
    const existing = map.get(key);
    const incoming = {
      storeName,
      itemId,
      msku: normalizeText(row[3]), // D列
      sku: normalizeText(row[4]), // E列
      productName: normalizeText(row[5]), // F列
      owner: normalizeText(row[6]), // G列
    };

    map.set(key, existing ? {
      storeName: existing.storeName || incoming.storeName,
      itemId: existing.itemId || incoming.itemId,
      msku: existing.msku || incoming.msku,
      sku: existing.sku || incoming.sku,
      productName: existing.productName || incoming.productName,
      owner: existing.owner || incoming.owner,
    } : incoming);
  }

  return Array.from(map.values()).sort((a, b) => {
    const storeCompare = a.storeName.localeCompare(b.storeName, "zh-Hans-CN");
    if (storeCompare !== 0) {
      return storeCompare;
    }
    return a.itemId.localeCompare(b.itemId);
  });
}

function readCheckRows(writer: FeishuSheetWriter, lastRow: number): SheetRow[] {
  const checkEndRow = Math.min(lastRow, 6);
  if (checkEndRow < 2) {
    return [];
  }

  const values = writer.readValues({
    spreadsheetToken: currentReport.spreadsheetToken,
    sheetId: currentReport.sheets[TARGET_SHEET_NAME],
    range: `A2:R${checkEndRow}`,
  });

  return values.map((row) => [
    normalizeBaseText(row[0]),
    normalizeBaseText(row[1]),
    row[6] ?? "",
    row[7] ?? "",
    row[8] ?? "",
    row[12] ?? "",
    row[13] ?? "",
    row[14] ?? "",
  ]);
}

async function main(): Promise<void> {
  const startedAt = Date.now();
  const runId = createRunId();
  const confirmWrite = process.argv.includes("--confirm-write");
  const dryRun = !confirmWrite;
  const writer = new FeishuSheetWriter();
  const logger = new TableOperationLogger(writer, {
    spreadsheetToken: currentReport.spreadsheetToken,
    logSheetId: currentReport.sheets[LOG_SHEET_NAME],
    dryRun,
    confirmWrite,
  });

  let latestDate = "";
  let recent3Dates: string[] = [];
  let recent5Dates: string[] = [];
  let updatedRows = 0;
  let status = dryRun ? "dry-run" : "success";
  let errorMessage = "";
  let checkPassed = false;
  let logSuccess = false;

  console.log("同步近期利润与广告");
  console.log(`运行ID: ${runId}`);
  console.log(`写入模式: ${confirmWrite ? "confirm-write" : "dry-run"}`);
  console.log(`目标 Sheet: ${TARGET_SHEET_NAME} (${currentReport.sheets[TARGET_SHEET_NAME]})`);
  console.log(`数据源 Sheet: ${DETAIL_SHEET_NAME} (${DETAIL_SHEET_ID})`);
  console.log(`先从 ${DETAIL_SHEET_NAME} 重建 A:F，再写 G:R 公式`);
  console.log(`执行前清空范围: ${RECENT_CLEAR_RANGE}`);

  try {
    const detailRows = readDetailRows(writer);
    latestDate = findLatestDate(detailRows);
    recent3Dates = buildRecentDates(latestDate, 3);
    recent5Dates = buildRecentDates(latestDate, 5);
    const baseItems = buildBaseItemsFromDetailRows(detailRows);

    if (baseItems.length === 0) {
      throw new Error("5月销售明细 没有可用于重建近期利润与广告 A:F 的数据");
    }
    if (baseItems.length > MAX_RECENT_DATA_ROWS) {
      throw new Error(`重建行数 ${baseItems.length} 超过安全上限 ${MAX_RECENT_DATA_ROWS}，已停止写入`);
    }

    console.log(`最新日期=${latestDate}`);
    console.log(`近3天日期=${recent3Dates.join("/")}`);
    console.log(`近5天日期=${recent5Dates.join("/")}`);
    console.log(`5月销售明细有效行数=${detailRows.length}`);
    console.log(`按 店铺+商品ID 去重后基础清单行数=${baseItems.length}`);

    updatedRows = baseItems.length;
    const lastDataRow = updatedRows + 1;
    const reportRows = baseItems.map((item, index) => buildRecentReportRow(item, index + 2, recent3Dates, recent5Dates));
    assertNoLegacyDetailFormulaReference(reportRows);

    console.log(`更新行数=${updatedRows}`);
    console.log(`写入范围=A2:R${lastDataRow}`);
    console.log(`公式数据源检查=通过，未发现 ${LEGACY_DETAIL_FORMULA_REF}`);
    console.log("写入预览（前 3 行）:");
    console.log(JSON.stringify(reportRows.slice(0, 3), null, 2));

    writer.ensureRows({
      spreadsheetToken: currentReport.spreadsheetToken,
      sheetId: currentReport.sheets[TARGET_SHEET_NAME],
      sheetName: TARGET_SHEET_NAME,
      requiredEndRow: lastDataRow,
      dryRun,
      confirmWrite,
    });

    writer.clearRange({
      spreadsheetToken: currentReport.spreadsheetToken,
      sheetId: currentReport.sheets[TARGET_SHEET_NAME],
      sheetName: TARGET_SHEET_NAME,
      range: RECENT_CLEAR_RANGE,
      dryRun,
      confirmWrite,
    });

    let nextRow = 2;
    for (const batch of chunkRows(reportRows, WRITE_BATCH_SIZE)) {
      const endRow = nextRow + batch.length - 1;
      writer.writeCells({
        spreadsheetToken: currentReport.spreadsheetToken,
        sheetId: currentReport.sheets[TARGET_SHEET_NAME],
        sheetName: TARGET_SHEET_NAME,
        range: `A${nextRow}:R${endRow}`,
        rows: batch,
        dryRun,
        confirmWrite,
        allowOverwrite: true,
      });
      nextRow = endRow + 1;
    }

    const checkRows = readCheckRows(writer, lastDataRow);
    checkPassed = checkRows.length > 0;
    console.log("检查结果（前 5 行）:");
    console.log("店铺 | 商品ID | 近3天销售额 | 近3天销量 | 近3天广告费 | 近5天销售额 | 近5天销量 | 近5天广告费");
    checkRows.forEach((row) => {
      console.log(row.map((value) => normalizeText(value)).join(" | "));
    });
    console.log(`检查结果=${checkPassed ? "通过" : "失败"}`);
  } catch (error) {
    status = "failed";
    errorMessage = error instanceof Error ? error.message : String(error);
    console.log(`同步失败: ${errorMessage}`);
  } finally {
    const remark =
      `CODEX执行：同步近期利润与广告，最新日期=${latestDate || "N/A"}` +
      `，近3天=${recent3Dates.join("/") || "N/A"}` +
      `，近5天=${recent5Dates.join("/") || "N/A"}` +
      `，更新行数=${updatedRows}，检查结果=${checkPassed ? "通过" : "失败"}`;

    try {
      logger.append({
        executedAt: new Date().toISOString(),
        taskName: TASK_NAME,
        targetSheet: TARGET_SHEET_NAME,
        operationType: dryRun ? "dry-run" : "formula_update",
        dataSource: DETAIL_SHEET_NAME,
        dateRange: latestDate ? `${recent5Dates[0]}~${latestDate}` : "",
        fetchedCount: 0,
        writtenCount: 0,
        updatedCount: updatedRows,
        skippedCount: 0,
        failedCount: status === "failed" ? 1 : 0,
        status,
        errorMessage,
        durationSeconds: Number(((Date.now() - startedAt) / 1000).toFixed(3)),
        runId,
        environment: "local",
        remark: errorMessage ? `${remark}，失败原因=${errorMessage}` : remark,
      });
      logSuccess = true;
    } catch (logError) {
      console.log(`记录操作日志失败: ${logError instanceof Error ? logError.message : String(logError)}`);
    }

    console.log(`日志是否写入成功: ${logSuccess ? "是" : "否"}`);
  }
}

main().catch((error) => {
  console.log(`执行失败: ${error instanceof Error ? error.message : String(error)}`);
});
