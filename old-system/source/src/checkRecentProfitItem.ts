import { execFileSync } from "child_process";
import currentReport from "../config/currentReportFieldMapping.json";
import { loadConfig } from "./config";
import { FeishuSheetWriter, SheetRow } from "./feishuSheetWriter";
import { LingxingClient } from "./lingxingClient";
import { STORES } from "./syncDailyBaseData";

const RECENT_SHEET_NAME = "近期利润与广告";
const DETAIL_SHEET_NAME = "5月销售明细_复盘";
const DEFAULT_STORE_NAME = "CN2601-瑞盈龙盛(刘云龙）";
const DEFAULT_ITEM_ID = "19952908300";
const READ_BATCH_SIZE = 500;
const LARK_CLI = "./scripts/lark-cli";
const SALE_STAT_PATH = "/basicOpen/platformStatisticsV2/saleStat/pageList";
const WALMART_SP_AD_PATH = "/basicOpen/multiplatform/ads/reportAdItemSpList";
const TIMEOUT_MS = 120000;
const SHEETS = currentReport.sheets as Record<string, string>;

function getArg(name: string, defaultValue = ""): string {
  const prefix = `--${name}=`;
  const arg = process.argv.find((item) => item.startsWith(prefix));
  return arg ? arg.slice(prefix.length) : defaultValue;
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

function toNumber(value: unknown): number {
  const text = normalizeText(value).replace(/,/g, "");
  const parsed = Number(text);
  return Number.isFinite(parsed) ? parsed : 0;
}

function toArrayValues(value: unknown): string[] {
  if (Array.isArray(value)) {
    return value.map(normalizeText).filter(Boolean);
  }
  if (typeof value === "string") {
    const text = value.trim();
    if (!text) {
      return [];
    }
    try {
      const parsed = JSON.parse(text);
      if (Array.isArray(parsed)) {
        return parsed.map(normalizeText).filter(Boolean);
      }
    } catch {
      // Some API fields are plain strings.
    }
    return [text];
  }
  const text = normalizeText(value);
  return text ? [text] : [];
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

function getItemIds(): string[] {
  const itemIds = getArg("item-ids");
  if (itemIds) {
    return itemIds.split(",").map((item) => item.trim()).filter(Boolean);
  }
  return [getArg("item-id", DEFAULT_ITEM_ID)];
}

function getSheetRowCount(writer: FeishuSheetWriter, sheetName: string): number {
  return writer.getRowCount({
    spreadsheetToken: currentReport.spreadsheetToken,
    sheetId: SHEETS[sheetName],
    sheetName,
  });
}

function readValuesInBatches(writer: FeishuSheetWriter, sheetName: string, rangeColumns: string): SheetRow[] {
  const rows: SheetRow[] = [];
  const rowCount = getSheetRowCount(writer, sheetName);
  for (let startRow = 2; startRow <= rowCount; startRow += READ_BATCH_SIZE) {
    const endRow = Math.min(startRow + READ_BATCH_SIZE - 1, rowCount);
    const chunk = writer.readValues({
      spreadsheetToken: currentReport.spreadsheetToken,
      sheetId: SHEETS[sheetName],
      range: `${rangeColumns.split(":")[0]}${startRow}:${rangeColumns.split(":")[1]}${endRow}`,
    });
    rows.push(...chunk);
  }
  return rows;
}

function findLatestDate(detailRows: SheetRow[]): string {
  const dates = detailRows.map((row) => normalizeText(row[0]).slice(0, 10)).filter((date) => /^\d{4}-\d{2}-\d{2}$/.test(date));
  dates.sort();
  if (dates.length === 0) {
    throw new Error("销售明细没有可识别日期");
  }
  return dates[dates.length - 1];
}

function getRecentSheetRowsWithFormula(): Array<{
  rowNumber: number;
  values: unknown[];
  formulas: string[];
}> {
  const output = execFileSync(
    LARK_CLI,
    [
      "sheets",
      "+cells-get",
      "--spreadsheet-token",
      currentReport.spreadsheetToken,
      "--sheet-id",
      SHEETS[RECENT_SHEET_NAME],
      "--range",
      "A2:R1000",
      "--include",
      "value,formula",
      "--format",
      "json",
    ],
    { cwd: process.cwd(), encoding: "utf8", maxBuffer: 80 * 1024 * 1024 },
  );
  const parsed = JSON.parse(output) as {
    ok?: boolean;
    data?: { ranges?: Array<{ cells?: Array<Array<{ value?: unknown; formula?: string }>>; row_indices?: number[] }> };
    error?: { message?: string };
  };
  if (!parsed.ok) {
    throw new Error(parsed.error?.message ?? "读取近期利润与广告失败");
  }
  const range = parsed.data?.ranges?.[0];
  const cells = range?.cells ?? [];
  const rowIndices = range?.row_indices ?? [];
  return cells.map((row, index) => ({
    rowNumber: rowIndices[index] ?? index + 2,
    values: row.map((cell) => cell.value ?? ""),
    formulas: row.map((cell) => cell.formula ?? "").filter(Boolean),
  }));
}

function sumDetailRows(detailRows: SheetRow[], storeName: string, itemId: string, dates: string[]): {
  salesQty: number;
  salesAmount: number;
  adCost: number;
} {
  const dateSet = new Set(dates);
  return detailRows.reduce(
    (sum, row) => {
      const date = normalizeText(row[0]).slice(0, 10);
      const rowStore = normalizeText(row[1]);
      const rowItemId = normalizeText(row[2]);
      if (dateSet.has(date) && rowStore.startsWith(storeName) && rowItemId === itemId) {
        sum.salesQty += toNumber(row[9]);
        sum.salesAmount += toNumber(row[10]);
        sum.adCost += toNumber(row[11]);
      }
      return sum;
    },
    { salesQty: 0, salesAmount: 0, adCost: 0 },
  );
}

function extractDataArray(data: unknown): unknown[] {
  if (Array.isArray(data)) return data;
  if (data && typeof data === "object") {
    const value = data as { data?: unknown; list?: unknown };
    if (Array.isArray(value.data)) return value.data;
    if (Array.isArray(value.list)) return value.list;
    if (value.data && typeof value.data === "object") {
      const nested = value.data as { list?: unknown; rows?: unknown; records?: unknown };
      if (Array.isArray(nested.list)) return nested.list;
      if (Array.isArray(nested.rows)) return nested.rows;
      if (Array.isArray(nested.records)) return nested.records;
    }
  }
  return [];
}

async function fetchSaleMetric(options: {
  client: LingxingClient;
  storeId: string;
  itemId: string;
  startDate: string;
  endDate: string;
  resultType: "1" | "3";
}): Promise<number> {
  let total = 0;
  for (let page = 1; page <= 10; page += 1) {
    const response = await options.client.request<unknown>({
      method: "POST",
      path: SALE_STAT_PATH,
      params: {
        start_date: options.startDate,
        end_date: options.endDate,
        result_type: options.resultType,
        date_unit: "4",
        data_type: "1",
        page,
        length: 200,
        sids: [options.storeId],
      },
      timeoutMs: TIMEOUT_MS,
    });
    const rows = extractDataArray(response.data);
    for (const row of rows) {
      if (row && typeof row === "object") {
        const record = row as Record<string, unknown>;
        if (toArrayValues(record.platform_product_id).includes(options.itemId)) {
          total += toNumber(record.volumeTotal);
        }
      }
    }
    if (rows.length < 200) {
      break;
    }
  }
  return Number(total.toFixed(2));
}

async function fetchAdCost(options: {
  client: LingxingClient;
  advertiserId: string;
  itemId: string;
  date: string;
}): Promise<number> {
  let total = 0;
  for (let pageNum = 1; pageNum <= 20; pageNum += 1) {
    const response = await options.client.request<unknown>({
      method: "POST",
      path: WALMART_SP_AD_PATH,
      params: {
        advertiserIds: [options.advertiserId],
        campaignType: ["sponsoredProducts-manual", "sponsoredProducts-auto"],
        startDate: options.date,
        endDate: options.date,
        pageNum,
        pageSize: 200,
        paging: true,
      },
      timeoutMs: TIMEOUT_MS,
    });
    const rows = extractDataArray(response.data);
    for (const row of rows) {
      if (row && typeof row === "object") {
        const record = row as Record<string, unknown>;
        if (normalizeText(record.itemId ?? record.item_id) === options.itemId) {
          total += toNumber(record.adSpend);
        }
      }
    }
    if (rows.length < 200) {
      break;
    }
  }
  return Number(total.toFixed(2));
}

async function compareEachDate(options: {
  client: LingxingClient;
  store: typeof STORES[number];
  storeName: string;
  itemId: string;
  dates: string[];
  detailRows: SheetRow[];
}): Promise<void> {
  console.log("逐日明细核对:");
  console.log("日期 | 明细销量 | ERP销量 | 明细销售额 | ERP销售额 | 明细广告费 | ERP广告费");
  for (const date of options.dates) {
    const detail = sumDetailRows(options.detailRows, options.storeName, options.itemId, [date]);
    const erpQty = await fetchSaleMetric({
      client: options.client,
      storeId: options.store.storeId,
      itemId: options.itemId,
      startDate: date,
      endDate: date,
      resultType: "1",
    });
    const erpAmount = await fetchSaleMetric({
      client: options.client,
      storeId: options.store.storeId,
      itemId: options.itemId,
      startDate: date,
      endDate: date,
      resultType: "3",
    });
    const erpAdCost = options.store.advertiserId
      ? await fetchAdCost({
          client: options.client,
          advertiserId: options.store.advertiserId,
          itemId: options.itemId,
          date,
        })
      : 0;
    console.log(
      `${date} | ${detail.salesQty} | ${erpQty} | ${Number(detail.salesAmount.toFixed(2))} | ${erpAmount} | ` +
        `${Number(detail.adCost.toFixed(2))} | ${erpAdCost}`,
    );
  }
}

function findRecentRow(
  recentRows: Array<{ rowNumber: number; values: unknown[]; formulas: string[] }>,
  itemId: string,
  storeName?: string,
): { rowNumber: number; values: unknown[]; formulas: string[] } {
  const row = recentRows.find((item) => {
    const sameItem = normalizeText(item.values[1]) === itemId;
    const sameStore = storeName ? normalizeText(item.values[0]) === storeName : true;
    return sameItem && sameStore;
  }) ?? recentRows.find((item) => normalizeText(item.values[1]) === itemId);
  if (!row) {
    throw new Error(`近期利润与广告未找到 ${storeName ? `${storeName} / ` : ""}${itemId}`);
  }
  return row;
}

function inferStoreName(
  recentRows: Array<{ rowNumber: number; values: unknown[]; formulas: string[] }>,
  detailRows: SheetRow[],
  itemId: string,
): string {
  const recentRow = recentRows.find((item) => normalizeText(item.values[1]) === itemId);
  if (recentRow) {
    return normalizeText(recentRow.values[0]);
  }
  const detailRow = detailRows.find((row) => normalizeText(row[2]) === itemId);
  if (detailRow) {
    return normalizeText(detailRow[1]);
  }
  throw new Error(`无法从近期利润与广告或销售明细推断店铺：${itemId}`);
}

async function main(): Promise<void> {
  const explicitStoreName = getArg("store");
  const itemIds = getItemIds();
  const dayCount = Number(getArg("days", "7"));
  const writer = new FeishuSheetWriter();
  const detailRows = readValuesInBatches(writer, DETAIL_SHEET_NAME, "A:L");
  const latestDate = findLatestDate(detailRows);
  const recentDates = buildRecentDates(latestDate, dayCount);
  const recentRows = getRecentSheetRowsWithFormula();
  const client = new LingxingClient(loadConfig());

  console.log("近期利润与广告单品核对");
  console.log(`最新日期: ${latestDate}`);
  console.log(`近${dayCount}天: ${recentDates.join("/")}`);

  for (const itemId of itemIds) {
    const storeName = explicitStoreName || inferStoreName(recentRows, detailRows, itemId);
    const recentRow = (() => {
      try {
        return findRecentRow(recentRows, itemId, storeName);
      } catch {
        return null;
      }
    })();
    const detail = sumDetailRows(detailRows, storeName, itemId, recentDates);
    const store = STORES.find((item) => item.storeName === storeName);
    if (!store) {
      throw new Error(`未找到店铺配置：${storeName}`);
    }

    console.log("");
    console.log(`店铺: ${storeName}`);
    console.log(`商品ID: ${itemId}`);
    console.log(`近期利润与广告行号: ${recentRow?.rowNumber ?? "未定位"}`);
    console.log(`公式单元格数量: ${recentRow?.formulas.length ?? "未读取"}`);
    console.log(
      `销售明细近${dayCount}天汇总: 销量=${detail.salesQty}, 销售额=${Number(detail.salesAmount.toFixed(2))}, ` +
        `广告费=${Number(detail.adCost.toFixed(2))}`,
    );
    console.log("公式示例:");
    console.log(recentRow?.formulas.slice(0, 3).join("\n") || "未读取到公式");
    await compareEachDate({
      client,
      store,
      storeName,
      itemId,
      dates: recentDates,
      detailRows,
    });
  }
}

main().catch((error) => {
  console.log(`核对失败: ${error instanceof Error ? error.message : String(error)}`);
  process.exitCode = 1;
});
