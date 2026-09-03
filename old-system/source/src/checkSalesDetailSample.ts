import { execFileSync } from "child_process";
import currentReport from "../config/currentReportFieldMapping.json";
import { loadConfig } from "./config";
import { FeishuSheetWriter } from "./feishuSheetWriter";
import { LingxingClient } from "./lingxingClient";
import { STORES, StoreConfig } from "./syncDailyBaseData";

type FieldKey = "salesQty" | "salesAmount" | "adCost" | "grossProfit" | "grossMargin";

interface SalesDetailRow {
  sheetRowNumber: number;
  date: string;
  storeName: string;
  itemId: string;
  msku: string;
  sku: string;
  values: unknown[];
}

interface MetricMaps {
  salesQtyMap: Map<string, number>;
  salesAmountMap: Map<string, number>;
  adCostMap: Map<string, number>;
}

interface CheckResult {
  date: string;
  storeName: string;
  itemId: string;
  fieldName: string;
  sheetValue: string;
  apiValue: string;
  passed: boolean;
  diff: number;
}

const LARK_CLI = "./scripts/lark-cli";
const TARGET_SHEET_NAME = "5月销售明细_复盘";
const READ_START_ROW = 2;
// READ_END_ROW 在运行时通过 getRowCount() 动态获取
const READ_BATCH_SIZE = 500;
const DEFAULT_START_DATE = "2026-05-01";
const DEFAULT_END_DATE = "2026-06-03";
const SAMPLE_DATE_COUNT = 10;
const SAMPLE_ITEM_COUNT = 20;
const CHECKS_PER_ITEM = 2;
const SALE_STAT_PATH = "/basicOpen/platformStatisticsV2/saleStat/pageList";
const WALMART_SP_AD_PATH = "/basicOpen/multiplatform/ads/reportAdItemSpList";
const PRODUCT_COST_PATH = "/erp/sc/routing/data/local_inventory/batchGetProductInfo";
const SALE_STAT_PAGE_LENGTH = 200;
const SALE_STAT_MAX_PAGES = 10;
const AD_PAGE_LENGTH = 200;
const AD_MAX_PAGES = 20;
const PRODUCT_COST_BATCH_SIZE = 50;
const TIMEOUT_MS = 120000;
const MAX_RETRIES = 3;
const AMOUNT_TOLERANCE = 0.01;

// 抽查排除的店铺（测款店铺，成本结构特殊，不参与利润抽查）
const EXCLUDE_STORE_NAMES = ["CN2502-悦斯电子(陈文胜）"];

const FIELD_OPTIONS: Array<{ key: FieldKey; name: string }> = [
  { key: "salesQty", name: "今日销量 J列" },
  { key: "salesAmount", name: "今日销售额 K列" },
  { key: "adCost", name: "广告花费 L列" },
  { key: "grossProfit", name: "毛利润 H列" },
  { key: "grossMargin", name: "毛利率 I列" },
];

function getArg(name: string, defaultValue = ""): string {
  const prefix = `--${name}=`;
  const arg = process.argv.find((item) => item.startsWith(prefix));
  return arg ? arg.slice(prefix.length) : defaultValue;
}

const DATE_ARG = getArg("date");
const START_DATE = getArg("startDate", DATE_ARG || DEFAULT_START_DATE);
const END_DATE = getArg("endDate", DATE_ARG || DEFAULT_END_DATE);

function execLarkCli(args: string[]): string {
  try {
    return execFileSync(LARK_CLI, args, {
      cwd: process.cwd(),
      encoding: "utf8",
      maxBuffer: 80 * 1024 * 1024,
      stdio: ["ignore", "pipe", "pipe"],
    });
  } catch (error) {
    const err = error as { stderr?: Buffer | string; message?: string };
    const stderr = Buffer.isBuffer(err.stderr) ? err.stderr.toString("utf8") : err.stderr;
    throw new Error(stderr || err.message || "lark-cli command failed");
  }
}

function readSalesDetailRange(a1Range: string): SalesDetailRow[] {
  const output = execLarkCli([
    "sheets",
    "+cells-get",
    "--spreadsheet-token",
    currentReport.spreadsheetToken,
    "--sheet-id",
    currentReport.sheets[TARGET_SHEET_NAME],
    "--range",
    a1Range,
    "--include",
    "value",
    "--format",
    "json",
  ]);

  const parsed = JSON.parse(output) as {
    ok?: boolean;
    data?: {
      ranges?: Array<{
        cells?: Array<Array<{ value?: unknown }>>;
        row_indices?: number[];
      }>;
    };
    error?: { message?: string };
  };

  if (!parsed.ok) {
    throw new Error(parsed.error?.message ?? "读取 5月销售明细 失败");
  }

  const parsedRange = parsed.data?.ranges?.[0];
  const cells = parsedRange?.cells ?? [];
  const rowIndices = parsedRange?.row_indices ?? [];

  return cells
    .map((row, index) => {
      const values = row.map((cell) => cell.value ?? "");
      return {
        sheetRowNumber: rowIndices[index] ?? index + 2,
        date: normalizeText(values[0]),
        storeName: normalizeText(values[1]),
        itemId: normalizeText(values[2]),
        msku: normalizeText(values[3]),
        sku: normalizeText(values[4]),
        values,
      };
    })
    .filter((row) => row.date >= START_DATE && row.date <= END_DATE && row.storeName && row.itemId && !EXCLUDE_STORE_NAMES.includes(row.storeName));
}

function readSalesDetailRows(): SalesDetailRow[] {
  const rows: SalesDetailRow[] = [];

  const writer = new FeishuSheetWriter();
  const sheetRowCount = writer.getRowCount({
    spreadsheetToken: currentReport.spreadsheetToken,
    sheetId: currentReport.sheets[TARGET_SHEET_NAME],
    sheetName: TARGET_SHEET_NAME,
  });
  console.log(`${TARGET_SHEET_NAME} 实际行数: ${sheetRowCount}`);

  for (let startRow = READ_START_ROW; startRow <= sheetRowCount; startRow += READ_BATCH_SIZE) {
    const endRow = Math.min(startRow + READ_BATCH_SIZE - 1, sheetRowCount);
    const range = `A${startRow}:V${endRow}`;
    const rawRows = readSalesDetailRange(range);
    rows.push(...rawRows);
    console.log(`读取范围 ${range}: 有效数据 ${rawRows.length} 行`);
    if (endRow >= sheetRowCount) break;
  }

  return rows;
}

function normalizeText(value: unknown): string {
  return String(value ?? "").trim();
}

function toNumber(value: unknown): number {
  const text = normalizeText(value).replace(/,/g, "");
  if (!text) {
    return 0;
  }
  if (text.endsWith("%")) {
    const percent = Number(text.slice(0, -1));
    return Number.isFinite(percent) ? percent / 100 : 0;
  }

  const num = Number(text);
  return Number.isFinite(num) ? num : 0;
}

function roundTo(value: number, digits: number): number {
  const factor = 10 ** digits;
  return Math.round((value + Number.EPSILON) * factor) / factor;
}

function shuffle<T>(items: T[]): T[] {
  const result = [...items];
  for (let index = result.length - 1; index > 0; index -= 1) {
    const randomIndex = Math.floor(Math.random() * (index + 1));
    [result[index], result[randomIndex]] = [result[randomIndex], result[index]];
  }
  return result;
}

function pickRandom<T>(items: T[], count: number): T[] {
  return shuffle(items).slice(0, count);
}

function sampleRows(rows: SalesDetailRow[]): { selectedDates: string[]; selectedRows: SalesDetailRow[] } {
  const availableDates = Array.from(new Set(rows.map((row) => row.date))).sort();
  if (availableDates.length === 0) {
    throw new Error("可抽查日期不足，当前日期范围没有有效数据");
  }

  const selectedDateCount = Math.min(SAMPLE_DATE_COUNT, availableDates.length);
  const selectedDates = pickRandom(availableDates, selectedDateCount).sort();
  const rowsInSelectedDates = rows.filter((row) => selectedDates.includes(row.date));
  const uniqueByItemId = new Map<string, SalesDetailRow>();

  for (const row of shuffle(rowsInSelectedDates)) {
    if (!uniqueByItemId.has(row.itemId)) {
      uniqueByItemId.set(row.itemId, row);
    }
  }

  const uniqueRows = Array.from(uniqueByItemId.values());
  if (uniqueRows.length < SAMPLE_ITEM_COUNT) {
    throw new Error(`可抽查 ITEM ID 不足 ${SAMPLE_ITEM_COUNT} 个，当前只有 ${uniqueRows.length} 个`);
  }

  return {
    selectedDates,
    selectedRows: pickRandom(uniqueRows, SAMPLE_ITEM_COUNT),
  };
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
      // API sometimes returns plain strings.
    }

    return [text];
  }

  const normalized = normalizeText(value);
  return normalized ? [normalized] : [];
}

function extractDataArray(data: unknown): unknown[] {
  if (Array.isArray(data)) {
    return data;
  }

  if (data && typeof data === "object") {
    const value = data as { data?: unknown; list?: unknown; rows?: unknown; records?: unknown };
    if (Array.isArray(value.data)) {
      return value.data;
    }
    if (Array.isArray(value.list)) {
      return value.list;
    }
    if (Array.isArray(value.rows)) {
      return value.rows;
    }
    if (Array.isArray(value.records)) {
      return value.records;
    }
  }

  return [];
}

function extractAdItems(data: unknown): unknown[] {
  if (data && typeof data === "object") {
    const value = data as { list?: unknown; data?: unknown };
    if (Array.isArray(value.list)) {
      return value.list;
    }
    if (value.data && typeof value.data === "object") {
      const nested = value.data as { list?: unknown };
      if (Array.isArray(nested.list)) {
        return nested.list;
      }
    }
  }

  return extractDataArray(data);
}

function extractAdTotal(data: unknown): number {
  if (data && typeof data === "object") {
    const value = data as { total?: unknown; data?: unknown };
    const directTotal = Number(value.total);
    if (Number.isFinite(directTotal) && directTotal > 0) {
      return directTotal;
    }

    if (value.data && typeof value.data === "object") {
      const nested = value.data as { total?: unknown };
      const nestedTotal = Number(nested.total);
      if (Number.isFinite(nestedTotal) && nestedTotal > 0) {
        return nestedTotal;
      }
    }
  }

  return 0;
}

async function sleep(ms: number): Promise<void> {
  await new Promise((resolve) => setTimeout(resolve, ms));
}

async function withRetry<T>(label: string, task: () => Promise<T>): Promise<T> {
  let lastError: unknown;

  for (let attempt = 1; attempt <= MAX_RETRIES; attempt += 1) {
    try {
      return await task();
    } catch (error) {
      lastError = error;
      console.log(`${label} 失败: attempt=${attempt}/${MAX_RETRIES}, 原因=${getErrorMessage(error)}`);
      if (attempt < MAX_RETRIES) {
        await sleep(1000 * attempt);
      }
    }
  }

  throw lastError instanceof Error ? lastError : new Error(String(lastError));
}

async function fetchSaleStatMap(
  client: LingxingClient,
  store: StoreConfig,
  dataDate: string,
  resultType: "1" | "3",
): Promise<Map<string, number>> {
  const metricMap = new Map<string, number>();

  for (let page = 1; page <= SALE_STAT_MAX_PAGES; page += 1) {
    const response = await withRetry(`${store.storeName} ${dataDate} 销售统计 result_type=${resultType} page=${page}`, () =>
      client.request<unknown>({
        method: "POST",
        path: SALE_STAT_PATH,
        params: {
          start_date: dataDate,
          end_date: dataDate,
          result_type: resultType,
          date_unit: "4",
          data_type: "1",
          page,
          length: SALE_STAT_PAGE_LENGTH,
          sids: [store.storeId],
        },
        timeoutMs: TIMEOUT_MS,
      }),
    );

    const pageItems = extractDataArray(response.data);
    for (const item of pageItems) {
      if (!item || typeof item !== "object") {
        continue;
      }
      const record = item as Record<string, unknown>;
      const metric = toNumber(record.volumeTotal);
      for (const itemId of toArrayValues(record.platform_product_id)) {
        metricMap.set(itemId, (metricMap.get(itemId) ?? 0) + metric);
      }
    }

    if (pageItems.length < SALE_STAT_PAGE_LENGTH) {
      break;
    }
  }

  return metricMap;
}

async function fetchAdCostMap(client: LingxingClient, store: StoreConfig, dataDate: string): Promise<Map<string, number>> {
  const metricMap = new Map<string, number>();
  if (!store.advertiserId) {
    return metricMap;
  }

  let fetchedCount = 0;
  for (let pageNum = 1; pageNum <= AD_MAX_PAGES; pageNum += 1) {
    const response = await withRetry(`${store.storeName} ${dataDate} Walmart SP广告 pageNum=${pageNum}`, () =>
      client.request<unknown>({
        method: "POST",
        path: WALMART_SP_AD_PATH,
        params: {
          advertiserIds: [store.advertiserId],
          campaignType: ["sponsoredProducts-manual", "sponsoredProducts-auto"],
          startDate: dataDate,
          endDate: dataDate,
          pageNum,
          pageSize: AD_PAGE_LENGTH,
          paging: true,
        },
        timeoutMs: TIMEOUT_MS,
      }),
    );

    const pageItems = extractAdItems(response.data);
    fetchedCount += pageItems.length;
    for (const item of pageItems) {
      if (!item || typeof item !== "object") {
        continue;
      }
      const record = item as Record<string, unknown>;
      const itemId = normalizeText(record.itemId);
      const adSpend = toNumber(record.adSpend);
      if (itemId) {
        metricMap.set(itemId, (metricMap.get(itemId) ?? 0) + adSpend);
      }
    }

    const total = extractAdTotal(response.data);
    if (pageItems.length < AD_PAGE_LENGTH || (total > 0 && fetchedCount >= total)) {
      break;
    }
  }

  return metricMap;
}

function chunkArray<T>(items: T[], size: number): T[][] {
  const chunks: T[][] = [];
  for (let index = 0; index < items.length; index += size) {
    chunks.push(items.slice(index, index + size));
  }
  return chunks;
}

function extractUsTransportCost(value: unknown): unknown {
  if (Array.isArray(value)) {
    for (const item of value) {
      if (item && typeof item === "object" && "US_cg_transport_costs" in item) {
        return (item as Record<string, unknown>).US_cg_transport_costs;
      }
    }
  }

  if (value && typeof value === "object" && "US_cg_transport_costs" in value) {
    return (value as Record<string, unknown>).US_cg_transport_costs;
  }

  return "";
}

async function fetchProductCostMap(client: LingxingClient, rows: SalesDetailRow[]): Promise<Map<string, { purchaseCost: number; logisticsCost: number }>> {
  const skus = Array.from(new Set(rows.map((row) => row.sku).filter(Boolean)));
  const costMap = new Map<string, { purchaseCost: number; logisticsCost: number }>();

  for (const [index, batch] of chunkArray(skus, PRODUCT_COST_BATCH_SIZE).entries()) {
    const response = await withRetry(`产品成本抽查批次 ${index + 1}`, () =>
      client.request<unknown>({
        method: "POST",
        path: PRODUCT_COST_PATH,
        params: { skus: batch },
        timeoutMs: TIMEOUT_MS,
      }),
    );

    for (const item of extractDataArray(response.data)) {
      if (!item || typeof item !== "object") {
        continue;
      }
      const record = item as Record<string, unknown>;
      const sku = normalizeText(record.sku);
      if (!sku) {
        continue;
      }
      costMap.set(sku, {
        purchaseCost: toNumber(record.cg_price),
        logisticsCost: toNumber(extractUsTransportCost(record.product_logistics_relation)),
      });
    }
  }

  return costMap;
}

function findStore(storeName: string): StoreConfig {
  const store = STORES.find((item) => storeName === item.storeName || storeName.startsWith(item.storeName));
  if (!store) {
    throw new Error(`无法根据店铺名匹配 store_id: ${storeName}`);
  }
  return store;
}

async function fetchMetricMapsForSamples(client: LingxingClient, rows: SalesDetailRow[]): Promise<Map<string, MetricMaps>> {
  const groups = new Map<string, { date: string; store: StoreConfig }>();

  for (const row of rows) {
    const store = findStore(row.storeName);
    groups.set(`${row.date}__${store.storeId}`, { date: row.date, store });
  }

  const result = new Map<string, MetricMaps>();
  for (const [key, group] of groups.entries()) {
    console.log(`重新调用 API: 日期=${group.date}, 店铺=${group.store.storeName}, 统计主键=Item ID`);
    const salesQtyMap = await fetchSaleStatMap(client, group.store, group.date, "1");
    const salesAmountMap = await fetchSaleStatMap(client, group.store, group.date, "3");
    const adCostMap = await fetchAdCostMap(client, group.store, group.date);
    result.set(key, { salesQtyMap, salesAmountMap, adCostMap });
  }

  return result;
}

function getMetricMaps(metricMapsByGroup: Map<string, MetricMaps>, row: SalesDetailRow): MetricMaps {
  const store = findStore(row.storeName);
  const maps = metricMapsByGroup.get(`${row.date}__${store.storeId}`);
  if (!maps) {
    throw new Error(`缺少 API 指标缓存: ${row.date} ${row.storeName}`);
  }
  return maps;
}

function calculateExpectedValues(
  row: SalesDetailRow,
  metrics: MetricMaps,
  productCostMap: Map<string, { purchaseCost: number; logisticsCost: number }>,
): Record<FieldKey, number> {
  const itemId = row.itemId;
  const salesQty = metrics.salesQtyMap.get(itemId) ?? 0;
  const salesAmount = metrics.salesAmountMap.get(itemId) ?? 0;
  const adCost = metrics.adCostMap.get(itemId) ?? 0;
  const productCost = productCostMap.get(row.sku);
  const wfsFee = toNumber(row.values[13]);
  const commissionRate = toNumber(row.values[14]);
  const purchaseCost = productCost?.purchaseCost ?? toNumber(row.values[15]);
  const logisticsCost = productCost?.logisticsCost ?? toNumber(row.values[16]);
  const exchangeRate = toNumber(row.values[17]) || 6.7;
  const grossProfit = salesAmount - adCost - wfsFee * salesQty - salesAmount * commissionRate - ((purchaseCost + logisticsCost) * salesQty) / exchangeRate;
  const grossMargin = salesAmount === 0 ? 0 : grossProfit / salesAmount;

  return {
    salesQty,
    salesAmount,
    adCost,
    grossProfit,
    grossMargin,
  };
}

function getSheetValue(row: SalesDetailRow, field: FieldKey): number {
  const indexByField: Record<FieldKey, number> = {
    grossProfit: 7,
    grossMargin: 8,
    salesQty: 9,
    salesAmount: 10,
    adCost: 11,
  };

  return toNumber(row.values[indexByField[field]]);
}

function normalizeComparable(field: FieldKey, value: number): number {
  if (field === "grossMargin") {
    return roundTo(value, 2);
  }
  if (field === "grossProfit" || field === "salesAmount" || field === "adCost") {
    return roundTo(value, 2);
  }
  return roundTo(value, 6);
}

function formatValue(field: FieldKey, value: number): string {
  if (field === "grossMargin") {
    return `${Math.round(value * 100)}%`;
  }
  if (field === "salesQty") {
    return String(roundTo(value, 6));
  }
  return roundTo(value, 2).toFixed(2);
}

function compareValue(field: FieldKey, sheetRawValue: number, apiRawValue: number): { sheetValue: number; apiValue: number; diff: number; passed: boolean } {
  const sheetValue = normalizeComparable(field, sheetRawValue);
  const apiValue = normalizeComparable(field, apiRawValue);
  const diff = roundTo(sheetValue - apiValue, field === "grossMargin" ? 4 : 6);

  if (field === "grossMargin") {
    return {
      sheetValue,
      apiValue,
      diff,
      passed: Math.abs(diff) < 0.0001,
    };
  }

  return {
    sheetValue,
    apiValue,
    diff,
    passed: Math.abs(diff) <= AMOUNT_TOLERANCE,
  };
}

function getErrorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

async function main(): Promise<void> {
  console.log("5月销售明细数据抽查校验");
  console.log(`检查范围: ${START_DATE}~${END_DATE}`);
  console.log("统计主键=Item ID");
  console.log("只读模式: 不修改飞书表格");

  const rows = readSalesDetailRows();
  console.log(`读取有效数据行数: ${rows.length}`);

  const { selectedDates, selectedRows } = sampleRows(rows);
  console.log(`抽查日期: ${selectedDates.join(", ")}`);
  console.log(`抽查 ITEM ID 数: ${selectedRows.length}`);

  const config = loadConfig();
  config.timeoutMs = TIMEOUT_MS;
  const client = new LingxingClient(config);
  const metricMapsByGroup = await fetchMetricMapsForSamples(client, selectedRows);
  const productCostMap = await fetchProductCostMap(client, selectedRows);
  const results: CheckResult[] = [];

  for (const row of selectedRows) {
    const fields = pickRandom(FIELD_OPTIONS, CHECKS_PER_ITEM);
    const metrics = getMetricMaps(metricMapsByGroup, row);
    const expectedValues = calculateExpectedValues(row, metrics, productCostMap);

    for (const field of fields) {
      const sheetRawValue = getSheetValue(row, field.key);
      const apiRawValue = expectedValues[field.key];
      const comparison = compareValue(field.key, sheetRawValue, apiRawValue);

      results.push({
        date: row.date,
        storeName: row.storeName,
        itemId: row.itemId,
        fieldName: field.name,
        sheetValue: formatValue(field.key, comparison.sheetValue),
        apiValue: formatValue(field.key, comparison.apiValue),
        passed: comparison.passed,
        diff: comparison.diff,
      });
    }
  }

  const passedCount = results.filter((result) => result.passed).length;
  const failedResults = results.filter((result) => !result.passed);

  console.log("");
  console.log("抽查明细:");
  console.table(
    results.map((result) => ({
      日期: result.date,
      店铺: result.storeName,
      ITEM_ID: result.itemId,
      检查字段: result.fieldName,
      表格值: result.sheetValue,
      API值: result.apiValue,
      是否一致: result.passed ? "是" : "否",
      差异值: result.diff,
    })),
  );

  console.log("");
  console.log("抽查汇总:");
  console.log(`抽查日期数: ${selectedDates.length}`);
  console.log(`抽查 ITEM ID 数: ${selectedRows.length}`);
  console.log(`检查项总数: ${results.length}`);
  console.log(`通过数: ${passedCount}`);
  console.log(`失败数: ${failedResults.length}`);

  if (failedResults.length > 0) {
    console.log("失败明细:");
    console.table(
      failedResults.map((result) => ({
        日期: result.date,
        店铺: result.storeName,
        ITEM_ID: result.itemId,
        检查字段: result.fieldName,
        表格值: result.sheetValue,
        API值: result.apiValue,
        差异值: result.diff,
      })),
    );
  } else {
    console.log("失败明细: 无");
  }
}

main().catch((error) => {
  console.log(`抽查失败: ${getErrorMessage(error)}`);
  process.exitCode = 1;
});
