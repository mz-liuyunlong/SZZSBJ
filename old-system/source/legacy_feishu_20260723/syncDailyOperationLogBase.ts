import currentReport from "../config/currentReportFieldMapping.json";
import { FeishuSheetWriter, SheetRow } from "./feishuSheetWriter";
import { TableOperationLogger } from "./tableOperationLogger";

type ProductLevel = "A" | "B" | "C" | "D" | "";

interface DailyOperationItem {
  date: string;
  storeName: string;
  itemId: string;
  msku: string;
  owner: string;
  grossMargin: number;
  adRatio: number;
  wfsAvailableQty: number;
}

interface HeaderMap {
  date: number;
  store: number;
  itemId: number;
  msku: number;
  owner: number;
  productLevel: number;
}

interface ExistingLogRow {
  rowNumber: number;
  date: string;
  storeName: string;
  itemId: string;
  msku: string;
  owner: string;
  productLevel: ProductLevel;
}

interface RecentMetric {
  grossMargin: number;
  adRatio: number;
}

interface DailyStock {
  wfsAvailableQty: number;
  grossMargin: number;
  adRatio: number;
}

interface ColumnUpdate {
  rowNumber: number;
  columnIndex: number;
  value: string;
}

const TASK_NAME = "每日运营跟进日志基础字段同步";
const DAILY_DATA_SHEET_NAME = "当日数据";
const RECENT_PROFIT_SHEET_NAME = "近期利润与广告";
const DAILY_LOG_SHEET_NAME = "每日运营跟进日志";
const LOG_SHEET_NAME = "表格操作日志";
const TIME_ZONE = "Asia/Shanghai";
const READ_START_ROW = 2;
const READ_BATCH_SIZE = 500;
const DAILY_LOG_READ_RANGE = "A1:Z5000"; // 初始默认值，运行时会动态扩展
const RECENT_READ_END_ROW = 50000; // 近期利润与广告行数可能超过12000
const DAILY_DATA_READ_END_ROW = 3000; // 当日数据每日重写，行数固定可控
const WRITE_BATCH_SIZE = 200;
const DAILY_LOG_HEADERS = ["日期", "店铺", "商品ID", "MSKU", "负责人", "产品等级", "产品数据问题", "解决意见", "运营日志"];

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

function isEntirelyOutsideSheetBoundsError(error: unknown): boolean {
  const message = error instanceof Error ? error.message : String(error);
  return message.includes("entirely outside sheet bounds");
}

function normalizeHeader(value: unknown): string {
  return normalizeText(value).replace(/\s+/g, "").toLowerCase();
}

function normalizeProductLevel(value: unknown): ProductLevel {
  const text = normalizeText(value).toUpperCase();
  return text === "A" || text === "B" || text === "C" || text === "D" ? text : "";
}

function toNumber(value: unknown): number {
  if (typeof value === "number") {
    return Number.isFinite(value) ? value : 0;
  }
  const text = normalizeText(value);
  if (!text) {
    return 0;
  }
  const isPercent = text.endsWith("%");
  const parsed = Number(text.replace(/,/g, "").replace("%", ""));
  if (!Number.isFinite(parsed)) {
    return 0;
  }
  return isPercent ? parsed / 100 : parsed;
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

function getDataDate(): string {
  return getArg("date") || addDays(getChinaDateText(), -2);
}

function findHeaderIndex(headers: SheetRow, candidates: string[]): number {
  const normalizedCandidates = candidates.map(normalizeHeader);
  return headers.findIndex((header) => normalizedCandidates.includes(normalizeHeader(header)));
}

function requireHeader(headers: SheetRow, candidates: string[], label: string): number {
  const index = findHeaderIndex(headers, candidates);
  if (index < 0) {
    throw new Error(`${DAILY_LOG_SHEET_NAME} 缺少表头：${label}`);
  }
  return index;
}

function buildHeaderMap(headers: SheetRow): HeaderMap {
  return {
    date: requireHeader(headers, ["日期"], "日期"),
    store: requireHeader(headers, ["店铺"], "店铺"),
    itemId: requireHeader(headers, ["商品ID", "ItemID", "ITEMID", "ITEM ID"], "商品ID"),
    msku: requireHeader(headers, ["MSKU"], "MSKU"),
    owner: requireHeader(headers, ["负责人"], "负责人"),
    productLevel: requireHeader(headers, ["产品等级"], "产品等级"),
  };
}

function buildUniqueKey(date: string, storeName: string, itemId: string): string {
  return `${date}|${storeName}|${itemId}`;
}

function buildItemKey(storeName: string, itemId: string): string {
  return `${storeName}|${itemId}`;
}

function columnName(index: number): string {
  let n = index + 1;
  let name = "";
  while (n > 0) {
    const remainder = (n - 1) % 26;
    name = String.fromCharCode(65 + remainder) + name;
    n = Math.floor((n - 1) / 26);
  }
  return name;
}

function chunkRows<T>(rows: T[], size: number): T[][] {
  const chunks: T[][] = [];
  for (let index = 0; index < rows.length; index += size) {
    chunks.push(rows.slice(index, index + size));
  }
  return chunks;
}

function readDailyOperationItems(writer: FeishuSheetWriter, dataDate: string): DailyOperationItem[] {
  const items: DailyOperationItem[] = [];
  const seen = new Set<string>();
  const sheetRowCount = writer.getRowCount({
    spreadsheetToken: currentReport.spreadsheetToken,
    sheetId: currentReport.sheets[DAILY_DATA_SHEET_NAME],
    sheetName: DAILY_DATA_SHEET_NAME,
  });
  const endLimit = Math.min(DAILY_DATA_READ_END_ROW, sheetRowCount);

  for (let startRow = READ_START_ROW; startRow <= endLimit; startRow += READ_BATCH_SIZE) {
    const endRow = Math.min(startRow + READ_BATCH_SIZE - 1, endLimit);
    const range = `A${startRow}:T${endRow}`;
    const rows = writer.readValues({
      spreadsheetToken: currentReport.spreadsheetToken,
      sheetId: currentReport.sheets[DAILY_DATA_SHEET_NAME],
      range,
    });
    let validCount = 0;
    let zeroStockSkippedCount = 0;

    for (const row of rows) {
      const date = normalizeText(row[0]);
      const storeName = normalizeText(row[1]);
      const itemId = normalizeText(row[2]);
      if (date !== dataDate || !storeName || !itemId) {
        continue;
      }

      const key = buildUniqueKey(date, storeName, itemId);
      if (seen.has(key)) {
        continue;
      }
      const wfsAvailableQty = toNumber(row[19]);
      if (wfsAvailableQty === 0) {
        zeroStockSkippedCount += 1;
        continue;
      }
      seen.add(key);
      validCount += 1;
      items.push({
        date,
        storeName,
        itemId,
        msku: normalizeText(row[3]),
        owner: normalizeText(row[6]),
        grossMargin: toNumber(row[8]),
        adRatio: toNumber(row[12]),
        wfsAvailableQty,
      });
    }

    console.log(
      `读取 ${DAILY_DATA_SHEET_NAME} ${range}: ${dataDate} 有效行 ${validCount}，库存为0跳过 ${zeroStockSkippedCount}`,
    );
  }

  return items;
}

function readExistingLogRows(writer: FeishuSheetWriter): {
  headers: SheetRow;
  headerMap: HeaderMap;
  rows: ExistingLogRow[];
  lastDataRow: number;
  emptyRowNumbers: number[];
} {
  // 动态获取实际行数
  const sheetRowCount = writer.getRowCount({
    spreadsheetToken: currentReport.spreadsheetToken,
    sheetId: currentReport.sheets[DAILY_LOG_SHEET_NAME],
    sheetName: DAILY_LOG_SHEET_NAME,
  });
  const endLimit = Math.min(5000, sheetRowCount);

  // 单独读取表头行，避免大范围一次性读取触发 has_more 分页被截断
  const headerRows = writer.readValues({
    spreadsheetToken: currentReport.spreadsheetToken,
    sheetId: currentReport.sheets[DAILY_LOG_SHEET_NAME],
    range: "A1:Z1",
  });
  if (headerRows.length === 0) {
    throw new Error(`${DAILY_LOG_SHEET_NAME} 没有表头`);
  }

  const headers = headerRows[0];
  const headerMap = buildHeaderMap(headers);
  const existingRows: ExistingLogRow[] = [];
  const emptyRowNumbers: number[] = [];
  let lastDataRow = 1;

  // 分批读取数据行，避免超大范围被截断（has_more 问题）
  for (let startRow = 2; startRow <= endLimit; startRow += READ_BATCH_SIZE) {
    const endRow = Math.min(startRow + READ_BATCH_SIZE - 1, endLimit);
    const range = `A${startRow}:Z${endRow}`;
    let batchRows: SheetRow[];
    try {
      batchRows = writer.readValues({
        spreadsheetToken: currentReport.spreadsheetToken,
        sheetId: currentReport.sheets[DAILY_LOG_SHEET_NAME],
        range,
      });
    } catch (error) {
      if (isEntirelyOutsideSheetBoundsError(error)) {
        console.log(`读取 ${DAILY_LOG_SHEET_NAME} ${range}: 已超出当前 Sheet 行数，停止读取后续批次`);
        break;
      }
      throw error;
    }
    batchRows.forEach((row, batchIndex) => {
      const rowNumber = startRow + batchIndex;
      const hasValue = row.some((value) => normalizeText(value));
      if (hasValue) {
        lastDataRow = rowNumber;
      } else {
        emptyRowNumbers.push(rowNumber);
      }

      const date = normalizeText(row[headerMap.date]);
      const storeName = normalizeText(row[headerMap.store]);
      const itemId = normalizeText(row[headerMap.itemId]);
      if (!date || !storeName || !itemId) {
        return;
      }

      existingRows.push({
        rowNumber,
        date,
        storeName,
        itemId,
        msku: normalizeText(row[headerMap.msku]),
        owner: normalizeText(row[headerMap.owner]),
        productLevel: normalizeProductLevel(row[headerMap.productLevel]),
      });
    });
  }

  return { headers, headerMap, rows: existingRows, lastDataRow, emptyRowNumbers };
}

function ensureDailyLogHeaders(writer: FeishuSheetWriter, dryRun: boolean, confirmWrite: boolean): void {
  const rows = writer.readValues({
    spreadsheetToken: currentReport.spreadsheetToken,
    sheetId: currentReport.sheets[DAILY_LOG_SHEET_NAME],
    range: "A1:I1",
  });
  const headerRow = rows[0] ?? [];
  const hasHeader = DAILY_LOG_HEADERS.slice(0, 6).every((header, index) => normalizeHeader(headerRow[index]) === normalizeHeader(header));

  if (hasHeader) {
    console.log("每日运营跟进日志表头检查: 已存在");
    return;
  }

  const hasAnyHeaderValue = headerRow.some((value) => normalizeText(value));
  if (hasAnyHeaderValue) {
    throw new Error(`${DAILY_LOG_SHEET_NAME} 表头不完整或不匹配，请确认 A1:F1 为：${DAILY_LOG_HEADERS.slice(0, 6).join("、")}`);
  }

  console.log("每日运营跟进日志表头检查: 空白表，准备写入标准表头");
  writer.writeCells({
    spreadsheetToken: currentReport.spreadsheetToken,
    sheetId: currentReport.sheets[DAILY_LOG_SHEET_NAME],
    sheetName: DAILY_LOG_SHEET_NAME,
    range: "A1:I1",
    rows: [DAILY_LOG_HEADERS],
    dryRun,
    confirmWrite,
    allowOverwrite: false,
  });
}

function buildNewLogRow(headers: SheetRow, headerMap: HeaderMap, item: DailyOperationItem, productLevel: ProductLevel): SheetRow {
  const row = new Array(headers.length).fill("");
  row[headerMap.date] = item.date;
  row[headerMap.store] = item.storeName;
  row[headerMap.itemId] = item.itemId;
  row[headerMap.msku] = item.msku;
  row[headerMap.owner] = item.owner;
  row[headerMap.productLevel] = productLevel;
  return row;
}

function buildSingleCellUpdateRange(columnIndex: number, rowNumber: number): string {
  const column = columnName(columnIndex);
  return `${column}${rowNumber}:${column}${rowNumber}`;
}

function evaluateProductLevel(metric?: RecentMetric | { grossMargin: number; adRatio: number }): ProductLevel {
  if (!metric) {
    return "";
  }

  const grossMargin = metric.grossMargin;
  const adRatio = metric.adRatio;
  if (grossMargin >= 0.2 && adRatio < 0.18) {
    return "A";
  }
  if (grossMargin >= 0.15) {
    return "B";
  }
  if (grossMargin >= 0.08) {
    return "C";
  }
  return "D";
}

function readRecentMetricMap(writer: FeishuSheetWriter): Map<string, RecentMetric> {
  const map = new Map<string, RecentMetric>();
  const sheetRowCount = writer.getRowCount({
    spreadsheetToken: currentReport.spreadsheetToken,
    sheetId: currentReport.sheets[RECENT_PROFIT_SHEET_NAME],
    sheetName: RECENT_PROFIT_SHEET_NAME,
  });
  const endLimit = Math.min(RECENT_READ_END_ROW, sheetRowCount);

  for (let startRow = READ_START_ROW; startRow <= endLimit; startRow += READ_BATCH_SIZE) {
    const endRow = Math.min(startRow + READ_BATCH_SIZE - 1, endLimit);
    const range = `A${startRow}:R${endRow}`;
    const rows = writer.readValues({
      spreadsheetToken: currentReport.spreadsheetToken,
      sheetId: currentReport.sheets[RECENT_PROFIT_SHEET_NAME],
      range,
    });
    let validCount = 0;

    for (const row of rows) {
      const storeName = normalizeText(row[0]);
      const itemId = normalizeText(row[1]);
      if (!storeName || !itemId) {
        continue;
      }
      validCount += 1;
      map.set(buildItemKey(storeName, itemId), {
        adRatio: toNumber(row[15]),
        grossMargin: toNumber(row[17]),
      });
    }

    console.log(`读取 ${RECENT_PROFIT_SHEET_NAME} ${range}: 有效商品 ${validCount}`);
  }

  return map;
}

function readDailyStockMap(writer: FeishuSheetWriter, dataDate: string): Map<string, DailyStock> {
  const map = new Map<string, DailyStock>();
  const sheetRowCount = writer.getRowCount({
    spreadsheetToken: currentReport.spreadsheetToken,
    sheetId: currentReport.sheets[DAILY_DATA_SHEET_NAME],
    sheetName: DAILY_DATA_SHEET_NAME,
  });
  const endLimit = Math.min(DAILY_DATA_READ_END_ROW, sheetRowCount);

  for (let startRow = READ_START_ROW; startRow <= endLimit; startRow += READ_BATCH_SIZE) {
    const endRow = Math.min(startRow + READ_BATCH_SIZE - 1, endLimit);
    const range = `A${startRow}:T${endRow}`;
    const rows = writer.readValues({
      spreadsheetToken: currentReport.spreadsheetToken,
      sheetId: currentReport.sheets[DAILY_DATA_SHEET_NAME],
      range,
    });
    let validCount = 0;

    for (const row of rows) {
      const date = normalizeText(row[0]);
      const storeName = normalizeText(row[1]);
      const itemId = normalizeText(row[2]);
      if (date !== dataDate || !storeName || !itemId) {
        continue;
      }
      validCount += 1;
      map.set(buildItemKey(storeName, itemId), {
        wfsAvailableQty: toNumber(row[19]),
        grossMargin: toNumber(row[8]),
        adRatio: toNumber(row[12]),
      });
    }

    console.log(`读取 ${DAILY_DATA_SHEET_NAME} ${range}: ${dataDate} 有效库存行 ${validCount}`);
  }

  return map;
}

function writeColumnUpdates(
  writer: FeishuSheetWriter,
  updates: ColumnUpdate[],
  dryRun: boolean,
  confirmWrite: boolean,
): void {
  const sorted = [...updates].sort((a, b) => a.columnIndex - b.columnIndex || a.rowNumber - b.rowNumber);
  let index = 0;

  while (index < sorted.length) {
    const start = sorted[index];
    const rows: SheetRow[] = [[start.value]];
    let endRow = start.rowNumber;
    index += 1;

    while (
      index < sorted.length &&
      sorted[index].columnIndex === start.columnIndex &&
      sorted[index].rowNumber === endRow + 1
    ) {
      rows.push([sorted[index].value]);
      endRow = sorted[index].rowNumber;
      index += 1;
    }

    const column = columnName(start.columnIndex);
    writer.writeCells({
      spreadsheetToken: currentReport.spreadsheetToken,
      sheetId: currentReport.sheets[DAILY_LOG_SHEET_NAME],
      sheetName: DAILY_LOG_SHEET_NAME,
      range: `${column}${start.rowNumber}:${column}${endRow}`,
      rows,
      dryRun,
      confirmWrite,
      allowOverwrite: true,
    });
  }
}

function hasAnyValue(row: SheetRow | undefined): boolean {
  return Boolean(row?.some((value) => normalizeText(value)));
}

function findEmptyBlockStart(
  writer: FeishuSheetWriter,
  startRow: number,
  rowCount: number,
  endColumn: string,
): number {
  if (rowCount <= 0) {
    return startRow;
  }

  const sheetRowCount = writer.getRowCount({
    spreadsheetToken: currentReport.spreadsheetToken,
    sheetId: currentReport.sheets[DAILY_LOG_SHEET_NAME],
    sheetName: DAILY_LOG_SHEET_NAME,
  });

  let candidate = Math.max(startRow, 2);
  while (candidate <= sheetRowCount) {
    const probeEndRow = Math.min(candidate + rowCount + 199, sheetRowCount);
    const rows = writer.readValues({
      spreadsheetToken: currentReport.spreadsheetToken,
      sheetId: currentReport.sheets[DAILY_LOG_SHEET_NAME],
      range: `A${candidate}:${endColumn}${probeEndRow}`,
    });

    let emptyRun = 0;
    for (let offset = 0; offset <= probeEndRow - candidate; offset += 1) {
      const rowNumber = candidate + offset;
      if (hasAnyValue(rows[offset])) {
        emptyRun = 0;
        continue;
      }

      emptyRun += 1;
      if (emptyRun >= rowCount) {
        return rowNumber - rowCount + 1;
      }
    }

    candidate = probeEndRow + 1;
  }

  // 搜完整个 sheet 仍有空行在末尾，直接追加到末尾而非跳过空行
  return sheetRowCount + 1;
}

function findAppendRow(writer: FeishuSheetWriter, lastDataRow: number): number {
  // 直接在 lastDataRow+1 追加，不做连续空行检测（lastDataRow 之后均为空）
  return lastDataRow + 1;
}

function isAlreadyHasDataError(error: unknown): boolean {
  const message = error instanceof Error ? error.message : String(error);
  return message.includes("already has data");
}

function writeNewRowsSafely(
  writer: FeishuSheetWriter,
  rows: SheetRow[],
  startRow: number,
  endColumn: string,
  dryRun: boolean,
  confirmWrite: boolean,
): number {
  let candidateStartRow = startRow;

  for (let attempt = 0; attempt < 50; attempt += 1) {
    candidateStartRow = findEmptyBlockStart(writer, candidateStartRow, rows.length, endColumn);
    const endRow = candidateStartRow + rows.length - 1;

    try {
      writer.writeCells({
        spreadsheetToken: currentReport.spreadsheetToken,
        sheetId: currentReport.sheets[DAILY_LOG_SHEET_NAME],
        sheetName: DAILY_LOG_SHEET_NAME,
        range: `A${candidateStartRow}:${endColumn}${endRow}`,
        rows,
        dryRun,
        confirmWrite,
        allowOverwrite: false,
      });
      return endRow + 1;
    } catch (error) {
      if (!isAlreadyHasDataError(error) || dryRun || !confirmWrite) {
        throw error;
      }
      console.log(`每日运营日志目标区域已有数据，继续查找下一块空位: A${endRow + 1}:${endColumn}${endRow + rows.length}`);
      candidateStartRow = endRow + 1;
    }
  }

  throw new Error("写入每日运营跟进日志失败：连续查找 50 次仍遇到已有数据区域");
}

async function main(): Promise<void> {
  const startedAt = Date.now();
  const runId = createRunId();
  const confirmWrite = process.argv.includes("--confirm-write");
  const explicitDryRun = process.argv.includes("--dry-run");
  const dryRun = !confirmWrite;
  if (confirmWrite && explicitDryRun) {
    throw new Error("--dry-run 和 --confirm-write 不能同时使用");
  }

  const dataDate = getDataDate();
  const writer = new FeishuSheetWriter();
  const logger = new TableOperationLogger(writer, {
    spreadsheetToken: currentReport.spreadsheetToken,
    logSheetId: currentReport.sheets[LOG_SHEET_NAME],
    dryRun,
    confirmWrite,
  });

  let fetchedCount = 0;
  let insertedCount = 0;
  let updatedCount = 0;
  let skippedCount = 0;
  let levelACount = 0;
  let levelBCount = 0;
  let levelCCount = 0;
  let levelDCount = 0;
  let zeroStockCount = 0;
  let status = dryRun ? "dry-run" : "success";
  let errorMessage = "";
  let logSuccess = false;

  console.log("每日运营跟进日志基础字段同步");
  console.log(`运行ID: ${runId}`);
  console.log(`写入模式: ${confirmWrite ? "confirm-write" : "dry-run"}`);
  console.log(`数据日期: ${dataDate}`);
  console.log(`来源 Sheet: ${DAILY_DATA_SHEET_NAME} (${currentReport.sheets[DAILY_DATA_SHEET_NAME]})`);
  console.log(`目标 Sheet: ${DAILY_LOG_SHEET_NAME} (${currentReport.sheets[DAILY_LOG_SHEET_NAME]})`);
  console.log("只写字段: 日期、店铺、商品ID、MSKU、负责人、产品等级");
  console.log("不写字段: 产品数据问题、解决意见、运营日志");

  try {
    ensureDailyLogHeaders(writer, dryRun, confirmWrite);
    const dailyItems = readDailyOperationItems(writer, dataDate);
    const recentMetricMap = readRecentMetricMap(writer);
    const dailyStockMap = readDailyStockMap(writer, dataDate);
    const existing = readExistingLogRows(writer);
    const existingByKey = new Map<string, ExistingLogRow>();
    for (const row of existing.rows) {
      existingByKey.set(buildUniqueKey(row.date, row.storeName, row.itemId), row);
    }

    fetchedCount = dailyItems.length;
    zeroStockCount = dailyStockMap.size - dailyItems.length;
    console.log(`当日数据匹配行数: ${fetchedCount}`);
    console.log(`近期利润与广告可评级商品数: ${recentMetricMap.size}`);
    console.log(`当日数据可识别库存商品数: ${dailyStockMap.size}`);
    console.log(`每日运营跟进日志现有有效行数: ${existing.rows.length}`);
    console.log(`每日运营跟进日志可回填空行数: ${existing.emptyRowNumbers.length}`);

    let nextAppendRow = existing.lastDataRow + 1;
    const reusableEmptyRows = [...existing.emptyRowNumbers].filter(
      (rowNumber) => rowNumber > 1 && rowNumber <= existing.lastDataRow,
    );
    const newRows: SheetRow[] = [];
    const columnUpdates: ColumnUpdate[] = [];
    for (const item of dailyItems) {
      const key = buildUniqueKey(item.date, item.storeName, item.itemId);
      const itemKey = buildItemKey(item.storeName, item.itemId);
      const existingRow = existingByKey.get(key);
      const productLevel =
        evaluateProductLevel(recentMetricMap.get(itemKey)) ||
        evaluateProductLevel({ grossMargin: item.grossMargin, adRatio: item.adRatio });
      const stock = dailyStockMap.get(itemKey);
      if (stock && stock.wfsAvailableQty === 0) {
        zeroStockCount += 1;
      }
      if (productLevel === "A") {
        levelACount += 1;
      } else if (productLevel === "B") {
        levelBCount += 1;
      } else if (productLevel === "C") {
        levelCCount += 1;
      } else if (productLevel === "D") {
        levelDCount += 1;
      }

      if (!existingRow) {
        const newRow = buildNewLogRow(existing.headers, existing.headerMap, item, productLevel);
        const reusableRowNumber = reusableEmptyRows.shift();
        if (reusableRowNumber) {
          const endColumn = columnName(existing.headers.length - 1);
          writer.writeCells({
            spreadsheetToken: currentReport.spreadsheetToken,
            sheetId: currentReport.sheets[DAILY_LOG_SHEET_NAME],
            sheetName: DAILY_LOG_SHEET_NAME,
            range: `A${reusableRowNumber}:${endColumn}${reusableRowNumber}`,
            rows: [newRow],
            dryRun,
            confirmWrite,
            allowOverwrite: true,
          });
        } else {
          newRows.push(newRow);
        }
        insertedCount += 1;
        continue;
      }

      const updates: Array<{ index: number; value: string }> = [];
      if (!existingRow.msku && item.msku) {
        updates.push({ index: existing.headerMap.msku, value: item.msku });
      }
      if (!existingRow.owner && item.owner) {
        updates.push({ index: existing.headerMap.owner, value: item.owner });
      }
      if (productLevel && existingRow.productLevel !== productLevel) {
        updates.push({ index: existing.headerMap.productLevel, value: productLevel });
      }

      if (updates.length === 0) {
        skippedCount += 1;
        continue;
      }

      for (const update of updates) {
        columnUpdates.push({ rowNumber: existingRow.rowNumber, columnIndex: update.index, value: update.value });
      }
      updatedCount += 1;
    }

    writeColumnUpdates(writer, columnUpdates, dryRun, confirmWrite);

    const endColumn = columnName(existing.headers.length - 1);
    // 直接从 lastDataRow+1 顺序追加，避免 findEmptyBlockStart 在边界产生空行
    let appendRow = existing.lastDataRow + 1;
    for (const batch of chunkRows(newRows, WRITE_BATCH_SIZE)) {
      const endRow = appendRow + batch.length - 1;
      writer.writeCells({
        spreadsheetToken: currentReport.spreadsheetToken,
        sheetId: currentReport.sheets[DAILY_LOG_SHEET_NAME],
        sheetName: DAILY_LOG_SHEET_NAME,
        range: `A${appendRow}:${endColumn}${endRow}`,
        rows: batch,
        dryRun,
        confirmWrite,
        allowOverwrite: false,
      });
      appendRow = endRow + 1;
    }

    console.log("");
    console.log("基础字段同步汇总:");
    console.log(`读取当日数据条数: ${fetchedCount}`);
    console.log(`新增每日运营跟进日志行数: ${insertedCount}`);
    console.log(`更新已有日志行数: ${updatedCount}`);
    console.log(`跳过已有完整日志行数: ${skippedCount}`);
    console.log(`A级数量: ${levelACount}`);
    console.log(`B级数量: ${levelBCount}`);
    console.log(`C级数量: ${levelCCount}`);
    console.log(`D级数量: ${levelDCount}`);
    console.log(`当日库存为0数量: ${zeroStockCount}`);
  } catch (error) {
    status = "failed";
    errorMessage = error instanceof Error ? error.message : String(error);
    console.log(`基础字段同步失败: ${errorMessage}`);
  } finally {
    try {
      logger.append({
        executedAt: new Date().toISOString(),
        taskName: TASK_NAME,
        targetSheet: DAILY_LOG_SHEET_NAME,
        operationType: dryRun ? "dry-run" : "base_fields",
        dataSource: DAILY_DATA_SHEET_NAME,
        dateRange: dataDate,
        fetchedCount,
        writtenCount: insertedCount,
        updatedCount,
        skippedCount,
        failedCount: status === "failed" ? 1 : 0,
        status,
        errorMessage,
        durationSeconds: Number(((Date.now() - startedAt) / 1000).toFixed(3)),
        runId,
        environment: "local",
        remark:
          `CODEX执行：每日运营跟进日志基础字段同步，数据日期=${dataDate}` +
          `，只写字段=日期/店铺/商品ID/MSKU/负责人/产品等级` +
          `，不处理AI，不写产品数据问题/解决意见/运营日志` +
          `，来源=当日数据` +
          `，读取当日数据=${fetchedCount}` +
          `，新增=${insertedCount}` +
          `，更新=${updatedCount}` +
          `，跳过=${skippedCount}` +
          `，A级=${levelACount}` +
          `，B级=${levelBCount}` +
          `，C级=${levelCCount}` +
          `，D级=${levelDCount}` +
          `，当日库存为0=${zeroStockCount}` +
          `，评级规则=近5天毛利率和广告占比` +
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
