import currentReport from "../config/currentReportFieldMapping.json";
import { FeishuSheetWriter, SheetRow } from "./feishuSheetWriter";
import { TableOperationLogger } from "./tableOperationLogger";

const TASK_NAME = "修复悦斯CS成本列";
const DETAIL_SHEET_NAME = "5月销售明细_复盘";
const LOG_SHEET_NAME = "表格操作日志";
const STORE_NAME_KEYWORD = "CN2502-悦斯电子";
const READ_START_ROW = 2;
const READ_BATCH_SIZE = 500;
const PURCHASE_COST = 200;
const LOGISTICS_COST = 1;
const WFS_FEE = 4;

interface MatchedRow {
  rowNumber: number;
  storeName: string;
  itemId: string;
  msku: string;
  currentWfsFee: unknown;
  currentPurchaseCost: unknown;
  currentLogisticsCost: unknown;
}

function createRunId(): string {
  return `run_${new Date().toISOString().replace(/[-:.TZ]/g, "")}_${Math.random()
    .toString(36)
    .slice(2, 8)}`;
}

function normalizeText(value: unknown): string {
  if (value === undefined || value === null) {
    return "";
  }
  if (typeof value === "object") {
    const record = value as Record<string, unknown>;
    for (const key of ["value", "text", "formattedValue", "string", "number", "result"]) {
      if (record[key] !== undefined && record[key] !== null) {
        return normalizeText(record[key]);
      }
    }
    return "";
  }
  return String(value).trim();
}

function isSameNumber(value: unknown, expected: number): boolean {
  return Number(normalizeText(value)) === expected;
}

function isTargetRow(row: SheetRow): boolean {
  const storeName = normalizeText(row[1]);
  const msku = normalizeText(row[3]).toUpperCase();
  return storeName.includes(STORE_NAME_KEYWORD) && msku.startsWith("CS");
}

function getRowCount(writer: FeishuSheetWriter): number {
  return writer.getRowCount({
    spreadsheetToken: currentReport.spreadsheetToken,
    sheetId: currentReport.sheets[DETAIL_SHEET_NAME],
    sheetName: DETAIL_SHEET_NAME,
  });
}

function readMatchedRows(writer: FeishuSheetWriter): MatchedRow[] {
  const rowCount = getRowCount(writer);
  const matchedRows: MatchedRow[] = [];

  for (let startRow = READ_START_ROW; startRow <= rowCount; startRow += READ_BATCH_SIZE) {
    const endRow = Math.min(startRow + READ_BATCH_SIZE - 1, rowCount);
    const rows = writer.readValues({
      spreadsheetToken: currentReport.spreadsheetToken,
      sheetId: currentReport.sheets[DETAIL_SHEET_NAME],
      range: `A${startRow}:V${endRow}`,
    });

    rows.forEach((row, index) => {
      if (!isTargetRow(row)) {
        return;
      }

      matchedRows.push({
        rowNumber: startRow + index,
        storeName: normalizeText(row[1]),
        itemId: normalizeText(row[2]),
        msku: normalizeText(row[3]),
        currentWfsFee: row[13],
        currentPurchaseCost: row[15],
        currentLogisticsCost: row[16],
      });
    });

    console.log(`读取 ${DETAIL_SHEET_NAME} A${startRow}:V${endRow}: 匹配悦斯CS ${matchedRows.length} 行（累计）`);
  }

  return matchedRows;
}

function needsUpdate(row: MatchedRow): boolean {
  return (
    !isSameNumber(row.currentWfsFee, WFS_FEE) ||
    !isSameNumber(row.currentPurchaseCost, PURCHASE_COST) ||
    !isSameNumber(row.currentLogisticsCost, LOGISTICS_COST)
  );
}

function groupConsecutiveRows(rows: MatchedRow[]): MatchedRow[][] {
  const groups: MatchedRow[][] = [];
  for (const row of rows) {
    const lastGroup = groups[groups.length - 1];
    const lastRow = lastGroup?.[lastGroup.length - 1];
    if (lastGroup && lastRow && row.rowNumber === lastRow.rowNumber + 1) {
      lastGroup.push(row);
    } else {
      groups.push([row]);
    }
  }
  return groups;
}

function writeUpdates(writer: FeishuSheetWriter, rows: MatchedRow[], dryRun: boolean, confirmWrite: boolean): void {
  for (const group of groupConsecutiveRows(rows)) {
    const startRow = group[0].rowNumber;
    const endRow = group[group.length - 1].rowNumber;

    writer.writeCells({
      spreadsheetToken: currentReport.spreadsheetToken,
      sheetId: currentReport.sheets[DETAIL_SHEET_NAME],
      sheetName: DETAIL_SHEET_NAME,
      range: `N${startRow}:N${endRow}`,
      rows: group.map(() => [WFS_FEE]),
      dryRun,
      confirmWrite,
      allowOverwrite: true,
    });

    writer.writeCells({
      spreadsheetToken: currentReport.spreadsheetToken,
      sheetId: currentReport.sheets[DETAIL_SHEET_NAME],
      sheetName: DETAIL_SHEET_NAME,
      range: `P${startRow}:Q${endRow}`,
      rows: group.map(() => [PURCHASE_COST, LOGISTICS_COST]),
      dryRun,
      confirmWrite,
      allowOverwrite: true,
    });
  }
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

  let matchedCount = 0;
  let updateCount = 0;
  let status = dryRun ? "dry-run" : "success";
  let errorMessage = "";
  let logSuccess = false;

  console.log(TASK_NAME);
  console.log(`运行ID: ${runId}`);
  console.log(`写入模式: ${confirmWrite ? "confirm-write" : "dry-run"}`);
  console.log(`目标 Sheet: ${DETAIL_SHEET_NAME} (${currentReport.sheets[DETAIL_SHEET_NAME]})`);
  console.log(`规则: 店铺包含 ${STORE_NAME_KEYWORD} 且 MSKU 以 CS 开头时，N=4，P=200，Q=1`);

  try {
    const matchedRows = readMatchedRows(writer);
    const rowsToUpdate = matchedRows.filter(needsUpdate);
    matchedCount = matchedRows.length;
    updateCount = rowsToUpdate.length;

    console.log("");
    console.log("修复预览:");
    console.log(`匹配悦斯CS行数: ${matchedCount}`);
    console.log(`需要更新行数: ${updateCount}`);
    console.table(
      rowsToUpdate.slice(0, 20).map((row) => ({
        行号: row.rowNumber,
        店铺: row.storeName,
        商品ID: row.itemId,
        MSKU: row.msku,
        当前WFS配送费: row.currentWfsFee,
        新WFS配送费: WFS_FEE,
        当前采购成本: row.currentPurchaseCost,
        新采购成本: PURCHASE_COST,
        当前头程成本: row.currentLogisticsCost,
        新头程成本: LOGISTICS_COST,
      })),
    );

    if (rowsToUpdate.length > 0) {
      writeUpdates(writer, rowsToUpdate, dryRun, confirmWrite);
    }
  } catch (error) {
    status = "failed";
    errorMessage = error instanceof Error ? error.message : String(error);
    console.log(`修复失败: ${errorMessage}`);
  } finally {
    try {
      logger.append({
        executedAt: new Date().toISOString(),
        taskName: TASK_NAME,
        targetSheet: DETAIL_SHEET_NAME,
        operationType: dryRun ? "dry-run" : "update_cost_columns",
        dataSource: DETAIL_SHEET_NAME,
        dateRange: "",
        fetchedCount: matchedCount,
        writtenCount: status === "failed" ? 0 : updateCount,
        updatedCount: status === "failed" ? 0 : updateCount,
        skippedCount: matchedCount - updateCount,
        failedCount: status === "failed" ? 1 : 0,
        status,
        errorMessage,
        durationSeconds: Number(((Date.now() - startedAt) / 1000).toFixed(3)),
        runId,
        environment: "local",
        remark:
          `CODEX执行：只更新悦斯CS成本列，Sheet=${DETAIL_SHEET_NAME}` +
          `，规则=店铺CN2502且MSKU以CS开头，N列WFS配送费=4，P列采购成本=200，Q列头程成本=1` +
          `，匹配行数=${matchedCount}，更新行数=${updateCount}` +
          (errorMessage ? `，失败原因=${errorMessage}` : ""),
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
