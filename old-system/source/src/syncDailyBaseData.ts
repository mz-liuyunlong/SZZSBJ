import currentReport from "../config/currentReportFieldMapping.json";
import { loadConfig } from "./config";
import { FeishuSheetWriter, SheetRow } from "./feishuSheetWriter";
import { LingxingClient } from "./lingxingClient";
import { TableOperationLogger } from "./tableOperationLogger";

const TASK_NAME = "当日数据所有店铺同步";
const TARGET_SHEET_NAME = "当日数据";
const OWNER_SHEET_NAME = "ItemID负责人";
const LOG_SHEET_NAME = "表格操作日志";

function getArg(name: string, defaultValue = ""): string {
  const prefix = `--${name}=`;
  const arg = process.argv.find((item) => item.startsWith(prefix));
  return arg ? arg.slice(prefix.length) : defaultValue;
}

const DEFAULT_DATA_DATE = getArg("date", "2026-06-02");
const WALMART_LIST_PATH = "/basicOpen/multiplatform/walmart/list";
const PRODUCT_COST_PATH = "/erp/sc/routing/data/local_inventory/batchGetProductInfo";
const SALE_STAT_PATH = "/basicOpen/platformStatisticsV2/saleStat/pageList";
const WALMART_SP_AD_PATH = "/basicOpen/multiplatform/ads/reportAdItemSpList";
const PAGE_LENGTH = 20;
const WALMART_LIST_MAX_PAGES = 100;
const SALE_STAT_PAGE_LENGTH = 200;
const SALE_STAT_MAX_PAGES = 10;
const PRODUCT_COST_BATCH_SIZE = 50;
const AD_PAGE_LENGTH = 200;
const AD_MAX_PAGES = 20;
const TIMEOUT_MS = 120000;
const MAX_RETRIES = 3;
const BASE_CLEAR_END_ROW = 2000;
const OWNER_READ_RANGE = "A1:U3000";
const EXCHANGE_RATE = 6.7;
const YUESI_CS_PURCHASE_COST = 200;
const YUESI_CS_LOGISTICS_COST = 1;
const YUESI_CS_WFS_FEE = 4;
const ENABLE_ZERO_ACTIVITY_FILTER =
  currentReport.filterRules?.zeroActivityItemFilter?.enabled === true;

export interface StoreConfig {
  storeId: string;
  storeName: string;
  advertiserId?: string;
}

interface WalmartListItem {
  item_id?: string | number;
  msku?: string;
  local_sku?: string;
  local_name?: string;
  store_name?: string;
  wfs_available_quantity?: string | number;
}

interface FetchResult {
  items: WalmartListItem[];
  pageCount: number;
}

interface ItemOwnerInfo {
  owner: string;
  wfsFee: string | number;
}

interface ProductCostInfo {
  purchaseCost: string | number;
  logisticsCost: string | number;
}

interface ProductCostFetchResult {
  costMap: Map<string, ProductCostInfo>;
  batchCount: number;
  errorMessages: string[];
}

interface SaleStatFetchResult {
  metricMap: Map<string, number>;
  fetchedCount: number;
  errorMessage: string;
}

interface AdCostFetchResult {
  metricMap: Map<string, number>;
  fetchedCount: number;
  totalCost: number;
  errorMessage: string;
}

export interface StoreSyncResult {
  store: StoreConfig;
  rawRows: SheetRow[];
  pageCount: number;
  fetchedCount: number;
  salesQtyFetchedCount: number;
  salesAmountFetchedCount: number;
  adFetchedCount: number;
  adTotalCost: number;
  productCostBatchCount: number;
  matchedOwnerCount: number;
  matchedWfsFeeCount: number;
  matchedSalesQtyCount: number;
  matchedSalesAmountCount: number;
  matchedPurchaseCostCount: number;
  matchedLogisticsCostCount: number;
  matchedAdCostCount: number;
  errors: string[];
  failed: boolean;
}

interface EnrichStats {
  matchedSalesQtyCount: number;
  matchedSalesAmountCount: number;
  matchedPurchaseCostCount: number;
  matchedLogisticsCostCount: number;
  matchedAdCostCount: number;
}

export const STORES: StoreConfig[] = [
  {
    storeId: "110687423514268160",
    storeName: "CN2601-瑞盈龙盛(刘云龙）",
    advertiserId: "571910",
  },
  {
    storeId: "110687427724845056",
    storeName: "CN2501-掌上便捷(陈佳聪）",
    advertiserId: "497124",
  },
  {
    storeId: "110687428693128704",
    storeName: "CN2502-悦斯电子(陈文胜）",
    advertiserId: "502543",
  },
  {
    storeId: "110689966555011584",
    storeName: "CN2602-添详商贸(邓添祥)",
    advertiserId: "574861",
  },
  {
    storeId: "110704863834580480",
    storeName: "CN2603-四颗洋葱(林翔）",
  },
  {
    storeId: "110704872940532224",
    storeName: "HK2612-张李华(賽藝境）",
  },
];

function createRunId(): string {
  return `run_${new Date().toISOString().replace(/[-:.TZ]/g, "")}_${Math.random()
    .toString(36)
    .slice(2, 8)}`;
}

function toNumber(value: unknown): number {
  const num = Number(value);
  return Number.isFinite(num) ? num : 0;
}

function normalizeLookupKey(value: unknown): string {
  return String(value ?? "").trim();
}

function normalizeHeader(value: unknown): string {
  return String(value ?? "").trim().replace(/\s+/g, "").toLowerCase();
}

function parseOptionalNumber(value: unknown): string | number {
  const text = String(value ?? "").trim();
  if (!text) {
    return "";
  }

  const num = Number(text);
  return Number.isFinite(num) ? num : text;
}

function toArrayValues(value: unknown): string[] {
  if (Array.isArray(value)) {
    return value.map(normalizeLookupKey).filter(Boolean);
  }

  if (typeof value === "string") {
    const text = value.trim();
    if (!text) {
      return [];
    }

    try {
      const parsed = JSON.parse(text);
      if (Array.isArray(parsed)) {
        return parsed.map(normalizeLookupKey).filter(Boolean);
      }
    } catch {
      // Some API fields are plain strings instead of JSON arrays.
    }

    return [text];
  }

  const normalized = normalizeLookupKey(value);
  return normalized ? [normalized] : [];
}

function chunkArray<T>(items: T[], size: number): T[][] {
  const chunks: T[][] = [];
  for (let index = 0; index < items.length; index += size) {
    chunks.push(items.slice(index, index + size));
  }
  return chunks;
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

function getErrorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

function findHeaderIndex(headers: SheetRow, names: string[]): number {
  const normalizedNames = names.map(normalizeHeader);
  return headers.findIndex((header) => normalizedNames.includes(normalizeHeader(header)));
}

function buildItemOwnerMap(rows: SheetRow[]): Map<string, ItemOwnerInfo> {
  if (rows.length === 0) {
    return new Map();
  }

  const headers = rows[0];
  const itemIdIndex = findHeaderIndex(headers, ["商品ID", "ITEMID", "ItemID"]);
  const ownerIndex = findHeaderIndex(headers, ["负责人"]);
  const wfsFeeIndex = findHeaderIndex(headers, ["WFS费用", "WFS配送费", "WFS配送费（$）"]);

  if (itemIdIndex < 0) {
    throw new Error("ItemID负责人 缺少 商品ID/ITEMID/ItemID 表头");
  }
  if (ownerIndex < 0) {
    throw new Error("ItemID负责人 缺少 负责人 表头");
  }
  if (wfsFeeIndex < 0) {
    throw new Error("ItemID负责人 缺少 WFS费用/WFS配送费/WFS配送费（$） 表头");
  }

  const map = new Map<string, ItemOwnerInfo>();
  for (const row of rows.slice(1)) {
    const itemId = normalizeLookupKey(row[itemIdIndex]);
    if (!itemId) {
      continue;
    }

    map.set(itemId, {
      owner: String(row[ownerIndex] ?? "").trim(),
      wfsFee: parseOptionalNumber(row[wfsFeeIndex]),
    });
  }

  return map;
}

function readItemOwnerMap(writer: FeishuSheetWriter): Map<string, ItemOwnerInfo> {
  console.log("读取 ItemID负责人 维护表:");
  console.log(`目标 Sheet: ${OWNER_SHEET_NAME} (${currentReport.sheets[OWNER_SHEET_NAME]})`);
  console.log(`读取 Range: ${OWNER_READ_RANGE}`);

  const rows = writer.readValues({
    spreadsheetToken: currentReport.spreadsheetToken,
    sheetId: currentReport.sheets[OWNER_SHEET_NAME],
    range: OWNER_READ_RANGE,
  });
  const map = buildItemOwnerMap(rows);

  console.log(`维护表有效 ItemID 数: ${map.size}`);
  return map;
}

function getCommissionRate(storeName: string): number {
  if (storeName.includes("CN2501-掌上便捷") || storeName.includes("CN2502-悦斯电子")) {
    return 0.15;
  }

  return 0.12;
}

function isYuesiCsItem(storeName: unknown, msku: unknown): boolean {
  return normalizeLookupKey(storeName).includes("CN2502-悦斯电子") && normalizeLookupKey(msku).toUpperCase().startsWith("CS");
}

function buildRows(
  store: StoreConfig,
  dataDate: string,
  items: WalmartListItem[],
  itemOwnerMap: Map<string, ItemOwnerInfo>,
): { rows: SheetRow[]; matchedOwnerCount: number; matchedWfsFeeCount: number } {
  let matchedOwnerCount = 0;
  let matchedWfsFeeCount = 0;

  const rows = items.map((item) => {
    const row = new Array(22).fill("");
    const itemId = normalizeLookupKey(item.item_id);
    const ownerInfo = itemOwnerMap.get(itemId);

    row[0] = dataDate; // A 日期
    row[1] = store.storeName; // B 店铺
    row[2] = item.item_id ?? ""; // C 商品ID
    row[3] = item.msku ?? ""; // D MSKU
    row[4] = item.local_sku ?? ""; // E SKU
    row[5] = item.local_name || item.local_sku || ""; // F 品名
    row[6] = ownerInfo?.owner || ""; // G 负责人
    row[13] = ownerInfo?.wfsFee ?? ""; // N WFS配送费（$）
    if (isYuesiCsItem(store.storeName, row[3])) {
      row[13] = YUESI_CS_WFS_FEE;
    }
    row[14] = {
      value: getCommissionRate(store.storeName),
      cell_styles: { number_format: "0%" },
    }; // O 店铺佣金率
    row[17] = EXCHANGE_RATE; // R 汇率
    row[19] = toNumber(item.wfs_available_quantity); // T WFS可售库存

    if (row[6] !== "") {
      matchedOwnerCount += 1;
    }
    if (row[13] !== "") {
      matchedWfsFeeCount += 1;
    }

    return row;
  });

  return {
    rows,
    matchedOwnerCount,
    matchedWfsFeeCount,
  };
}

export function applyFormulaColumns(rows: SheetRow[], startSheetRow = 2): void {
  rows.forEach((row, index) => {
    const sheetRowNumber = startSheetRow + index;
    row[7] = {
      formula:
        `=IFERROR(K${sheetRowNumber},0)-IFERROR(L${sheetRowNumber},0)` +
        `-IFERROR(N${sheetRowNumber}*J${sheetRowNumber},0)` +
        `-IFERROR(K${sheetRowNumber}*O${sheetRowNumber},0)` +
        `-IFERROR((P${sheetRowNumber}+Q${sheetRowNumber})*J${sheetRowNumber}/R${sheetRowNumber},0)`,
      cell_styles: { number_format: "0.00" },
    }; // H 毛利润（$）
    row[8] = {
      formula: `=IFERROR(H${sheetRowNumber}/K${sheetRowNumber},0)`,
      cell_styles: { number_format: "0%" },
    }; // I 毛利率
    row[12] = {
      formula: `=IFERROR(L${sheetRowNumber}/K${sheetRowNumber},0)`,
      cell_styles: { number_format: "0%" },
    }; // M 广告占比
  });
}

function shouldIncludeDailyItem(row: SheetRow): boolean {
  const salesQty = toNumber(row[9]); // J 今日销量
  const adCost = toNumber(row[11]); // L 广告花费
  const wfsQty = toNumber(row[19]); // T WFS可售库存

  return !(salesQty === 0 && wfsQty === 0 && adCost === 0);
}

function getWriteRange(rowCount: number): string {
  if (rowCount <= 0) {
    return "A2:V2";
  }

  return `A2:V${rowCount + 1}`;
}

function getClearRange(rowCount: number): string {
  const endRow = Math.max(BASE_CLEAR_END_ROW, rowCount + 1);
  return `A2:V${endRow}`;
}

function validateClearRange(range: string): void {
  const match = /^A2:V(\d+)$/.exec(range);
  if (!match) {
    throw new Error(`清理范围不符合安全要求：${range}`);
  }

  const endRow = Number(match[1]);
  if (!Number.isFinite(endRow) || endRow < BASE_CLEAR_END_ROW) {
    throw new Error(`清理范围结束行不符合安全要求：${range}`);
  }
}

function extractItems(data: unknown): WalmartListItem[] {
  if (Array.isArray(data)) {
    return data as WalmartListItem[];
  }

  if (data && typeof data === "object") {
    const value = data as { list?: unknown; rows?: unknown; records?: unknown; data?: unknown };
    if (Array.isArray(value.list)) {
      return value.list as WalmartListItem[];
    }
    if (Array.isArray(value.rows)) {
      return value.rows as WalmartListItem[];
    }
    if (Array.isArray(value.records)) {
      return value.records as WalmartListItem[];
    }
    if (Array.isArray(value.data)) {
      return value.data as WalmartListItem[];
    }
  }

  return [];
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
      console.log(`${label} 失败: attempt=${attempt}/${MAX_RETRIES}, 原因: ${getErrorMessage(error)}`);

      if (attempt < MAX_RETRIES) {
        await sleep(1000 * attempt);
      }
    }
  }

  throw lastError instanceof Error ? lastError : new Error(String(lastError));
}

async function fetchPageWithRetry(
  client: LingxingClient,
  store: StoreConfig,
  offset: number,
): Promise<WalmartListItem[]> {
  return withRetry(`${store.storeName} Walmart商品分页 offset=${offset}`, async () => {
    console.log(`${store.storeName}: 抓取分页 offset=${offset}, length=${PAGE_LENGTH}`);
    const response = await client.request<unknown>({
      method: "POST",
      path: WALMART_LIST_PATH,
      params: {
        offset,
        length: PAGE_LENGTH,
        store_ids: [store.storeId],
        status: [0],
      },
      timeoutMs: TIMEOUT_MS,
    });

    return extractItems(response.data);
  });
}

async function fetchStoreItems(client: LingxingClient, store: StoreConfig): Promise<FetchResult> {
  const items: WalmartListItem[] = [];
  let pageCount = 0;

  for (let page = 0; page < WALMART_LIST_MAX_PAGES; page += 1) {
    const offset = page * PAGE_LENGTH;
    const pageItems = await fetchPageWithRetry(client, store, offset);
    pageCount += 1;
    items.push(...pageItems);

    if (pageItems.length < PAGE_LENGTH) {
      break;
    }
  }

  return { items, pageCount };
}

async function fetchProductCosts(client: LingxingClient, rows: SheetRow[]): Promise<ProductCostFetchResult> {
  const skus = Array.from(new Set(rows.map((row) => normalizeLookupKey(row[4])).filter(Boolean)));
  const costMap = new Map<string, ProductCostInfo>();
  const errorMessages: string[] = [];
  const batches = chunkArray(skus, PRODUCT_COST_BATCH_SIZE);

  for (const [index, batch] of batches.entries()) {
    try {
      const response = await withRetry(`产品成本批次 ${index + 1}/${batches.length}`, async () => {
        return client.request<unknown>({
          method: "POST",
          path: PRODUCT_COST_PATH,
          params: { skus: batch },
          timeoutMs: TIMEOUT_MS,
        });
      });

      for (const item of extractDataArray(response.data)) {
        if (!item || typeof item !== "object") {
          continue;
        }

        const record = item as Record<string, unknown>;
        const sku = normalizeLookupKey(record.sku);
        if (!sku) {
          continue;
        }

        costMap.set(sku, {
          purchaseCost: parseOptionalNumber(record.cg_price),
          logisticsCost: parseOptionalNumber(extractUsTransportCost(record.product_logistics_relation)),
        });
      }
    } catch (error) {
      errorMessages.push(`产品成本批次 ${index + 1} 失败：${getErrorMessage(error)}`);
    }
  }

  return {
    costMap,
    batchCount: batches.length,
    errorMessages,
  };
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

async function fetchSaleStatMap(
  client: LingxingClient,
  store: StoreConfig,
  dataDate: string,
  resultType: "1" | "3",
): Promise<SaleStatFetchResult> {
  const metricMap = new Map<string, number>();
  let fetchedCount = 0;

  try {
    for (let page = 1; page <= SALE_STAT_MAX_PAGES; page += 1) {
      const response = await withRetry(`${store.storeName} 销售统计 result_type=${resultType} page=${page}`, async () => {
        return client.request<unknown>({
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
        });
      });

      const pageItems = extractDataArray(response.data);
      fetchedCount += pageItems.length;
      mergeSaleStatItems(metricMap, pageItems);

      if (pageItems.length < SALE_STAT_PAGE_LENGTH) {
        break;
      }
    }

    return { metricMap, fetchedCount, errorMessage: "" };
  } catch (error) {
    return { metricMap: new Map(), fetchedCount, errorMessage: getErrorMessage(error) };
  }
}

function mergeSaleStatItems(metricMap: Map<string, number>, items: unknown[]): void {
  for (const item of items) {
    if (!item || typeof item !== "object") {
      continue;
    }

    const record = item as Record<string, unknown>;
    const metric = toNumber(record.volumeTotal);
    const keys = toArrayValues(record.platform_product_id);

    for (const key of keys) {
      metricMap.set(key, (metricMap.get(key) ?? 0) + metric);
    }
  }
}

async function fetchAdCostMap(
  client: LingxingClient,
  store: StoreConfig,
  dataDate: string,
): Promise<AdCostFetchResult> {
  const metricMap = new Map<string, number>();
  let fetchedCount = 0;
  let totalCost = 0;

  if (!store.advertiserId) {
    return { metricMap, fetchedCount, totalCost, errorMessage: "advertiserId为空，广告花费填0" };
  }

  try {
    for (let pageNum = 1; pageNum <= AD_MAX_PAGES; pageNum += 1) {
      const response = await withRetry(`${store.storeName} Walmart SP广告 pageNum=${pageNum}`, async () => {
        return client.request<unknown>({
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
        });
      });

      const pageItems = extractAdItems(response.data);
      fetchedCount += pageItems.length;
      totalCost += mergeAdCostItems(metricMap, pageItems);

      const total = extractAdTotal(response.data);
      if (pageItems.length < AD_PAGE_LENGTH || (total > 0 && fetchedCount >= total)) {
        break;
      }
    }

    return { metricMap, fetchedCount, totalCost, errorMessage: "" };
  } catch (error) {
    return {
      metricMap: new Map(),
      fetchedCount,
      totalCost,
      errorMessage: `Walmart SP广告接口失败，广告花费暂填0。原因：${getErrorMessage(error)}`,
    };
  }
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

function mergeAdCostItems(metricMap: Map<string, number>, items: unknown[]): number {
  let totalCost = 0;

  for (const item of items) {
    if (!item || typeof item !== "object") {
      continue;
    }

    const record = item as Record<string, unknown>;
    const itemId = normalizeLookupKey(record.itemId);
    const cost = toNumber(record.adSpend);

    totalCost += cost;

    if (itemId) {
      metricMap.set(itemId, (metricMap.get(itemId) ?? 0) + cost);
    }
  }

  return totalCost;
}

function enrichRows(
  rows: SheetRow[],
  salesQtyMap: Map<string, number>,
  salesAmountMap: Map<string, number>,
  adCostMap: Map<string, number>,
  costMap: Map<string, ProductCostInfo>,
): EnrichStats {
  const stats: EnrichStats = {
    matchedSalesQtyCount: 0,
    matchedSalesAmountCount: 0,
    matchedPurchaseCostCount: 0,
    matchedLogisticsCostCount: 0,
    matchedAdCostCount: 0,
  };

  for (const row of rows) {
    const itemId = normalizeLookupKey(row[2]);
    const sku = normalizeLookupKey(row[4]);

    const salesQty = findMetricByItemId(salesQtyMap, itemId);
    row[9] = salesQty.matched ? salesQty.value : 0; // J 今日销量
    if (salesQty.matched) {
      stats.matchedSalesQtyCount += 1;
    }

    const salesAmount = findMetricByItemId(salesAmountMap, itemId);
    row[10] = salesAmount.matched ? salesAmount.value : 0; // K 今日销售额（$）
    if (salesAmount.matched) {
      stats.matchedSalesAmountCount += 1;
    }

    const adCost = findMetricByItemId(adCostMap, itemId);
    row[11] = adCost.matched ? adCost.value : 0; // L 广告花费（$）
    if (adCost.matched && adCost.value > 0) {
      stats.matchedAdCostCount += 1;
    }

    const productCost = costMap.get(sku);
    row[15] = productCost?.purchaseCost ?? ""; // P 采购成本(￥)
    row[16] = productCost?.logisticsCost ?? ""; // Q 头程成本(￥)
    if (isYuesiCsItem(row[1], row[3])) {
      row[15] = YUESI_CS_PURCHASE_COST;
      row[16] = YUESI_CS_LOGISTICS_COST;
    }

    if (row[15] !== "") {
      stats.matchedPurchaseCostCount += 1;
    }
    if (row[16] !== "") {
      stats.matchedLogisticsCostCount += 1;
    }
  }

  return stats;
}

function findMetricByItemId(metricMap: Map<string, number>, itemId: string): { matched: boolean; value: number } {
  if (itemId && metricMap.has(itemId)) {
    return { matched: true, value: metricMap.get(itemId) ?? 0 };
  }
  return { matched: false, value: 0 };
}

async function syncStore(
  client: LingxingClient,
  store: StoreConfig,
  dataDate: string,
  itemOwnerMap: Map<string, ItemOwnerInfo>,
): Promise<StoreSyncResult> {
  const result: StoreSyncResult = {
    store,
    rawRows: [],
    pageCount: 0,
    fetchedCount: 0,
    salesQtyFetchedCount: 0,
    salesAmountFetchedCount: 0,
    adFetchedCount: 0,
    adTotalCost: 0,
    productCostBatchCount: 0,
    matchedOwnerCount: 0,
    matchedWfsFeeCount: 0,
    matchedSalesQtyCount: 0,
    matchedSalesAmountCount: 0,
    matchedPurchaseCostCount: 0,
    matchedLogisticsCostCount: 0,
    matchedAdCostCount: 0,
    errors: [],
    failed: false,
  };

  console.log("");
  console.log(`开始处理店铺: ${store.storeName}`);
  console.log(`store_id: ${store.storeId}`);
  console.log(`advertiserId: ${store.advertiserId ?? "空，广告花费填0"}`);

  try {
    const fetchResult = await fetchStoreItems(client, store);
    result.pageCount = fetchResult.pageCount;
    result.fetchedCount = fetchResult.items.length;

    const buildResult = buildRows(store, dataDate, fetchResult.items, itemOwnerMap);
    result.rawRows = buildResult.rows;
    result.matchedOwnerCount = buildResult.matchedOwnerCount;
    result.matchedWfsFeeCount = buildResult.matchedWfsFeeCount;

    const productCostResult = await fetchProductCosts(client, result.rawRows);
    result.productCostBatchCount = productCostResult.batchCount;
    result.errors.push(...productCostResult.errorMessages);

    const salesQtyResult = await fetchSaleStatMap(client, store, dataDate, "1");
    result.salesQtyFetchedCount = salesQtyResult.fetchedCount;
    if (salesQtyResult.errorMessage) {
      result.errors.push(`销量接口失败，今日销量暂填0。原因：${salesQtyResult.errorMessage}`);
    }

    const salesAmountResult = await fetchSaleStatMap(client, store, dataDate, "3");
    result.salesAmountFetchedCount = salesAmountResult.fetchedCount;
    if (salesAmountResult.errorMessage) {
      result.errors.push(`销售额接口失败，今日销售额暂填0。原因：${salesAmountResult.errorMessage}`);
    }

    const adCostResult = await fetchAdCostMap(client, store, dataDate);
    result.adFetchedCount = adCostResult.fetchedCount;
    result.adTotalCost = adCostResult.totalCost;
    if (adCostResult.errorMessage) {
      result.errors.push(adCostResult.errorMessage);
    }

    const enrichStats = enrichRows(
      result.rawRows,
      salesQtyResult.metricMap,
      salesAmountResult.metricMap,
      adCostResult.metricMap,
      productCostResult.costMap,
    );
    result.matchedSalesQtyCount = enrichStats.matchedSalesQtyCount;
    result.matchedSalesAmountCount = enrichStats.matchedSalesAmountCount;
    result.matchedPurchaseCostCount = enrichStats.matchedPurchaseCostCount;
    result.matchedLogisticsCostCount = enrichStats.matchedLogisticsCostCount;
    result.matchedAdCostCount = enrichStats.matchedAdCostCount;

    console.log(`${store.storeName}: Walmart商品抓取页数=${result.pageCount}, 条数=${result.fetchedCount}`);
    console.log(`${store.storeName}: 销量抓取=${result.salesQtyFetchedCount}, 匹配=${result.matchedSalesQtyCount}`);
    console.log(`${store.storeName}: 销售额抓取=${result.salesAmountFetchedCount}, 匹配=${result.matchedSalesAmountCount}`);
    console.log(
      `${store.storeName}: 广告记录=${result.adFetchedCount}, 匹配广告花费=${result.matchedAdCostCount}, 广告总花费=${Number(result.adTotalCost.toFixed(2))}`,
    );
    console.log(
      `${store.storeName}: 产品成本批次=${result.productCostBatchCount}, 匹配采购成本=${result.matchedPurchaseCostCount}, 匹配头程成本=${result.matchedLogisticsCostCount}`,
    );
  } catch (error) {
    result.failed = true;
    result.errors.push(getErrorMessage(error));
    console.log(`${store.storeName}: 店铺同步失败，不影响其他店铺。原因: ${getErrorMessage(error)}`);
  }

  return result;
}

function sumResults(results: StoreSyncResult[]) {
  return results.reduce(
    (totals, result) => {
      totals.fetchedCount += result.fetchedCount;
      totals.pageCount += result.pageCount;
      totals.salesQtyFetchedCount += result.salesQtyFetchedCount;
      totals.salesAmountFetchedCount += result.salesAmountFetchedCount;
      totals.adFetchedCount += result.adFetchedCount;
      totals.adTotalCost += result.adTotalCost;
      totals.productCostBatchCount += result.productCostBatchCount;
      totals.matchedOwnerCount += result.matchedOwnerCount;
      totals.matchedWfsFeeCount += result.matchedWfsFeeCount;
      totals.matchedSalesQtyCount += result.matchedSalesQtyCount;
      totals.matchedSalesAmountCount += result.matchedSalesAmountCount;
      totals.matchedPurchaseCostCount += result.matchedPurchaseCostCount;
      totals.matchedLogisticsCostCount += result.matchedLogisticsCostCount;
      totals.matchedAdCostCount += result.matchedAdCostCount;
      return totals;
    },
    {
      fetchedCount: 0,
      pageCount: 0,
      salesQtyFetchedCount: 0,
      salesAmountFetchedCount: 0,
      adFetchedCount: 0,
      adTotalCost: 0,
      productCostBatchCount: 0,
      matchedOwnerCount: 0,
      matchedWfsFeeCount: 0,
      matchedSalesQtyCount: 0,
      matchedSalesAmountCount: 0,
      matchedPurchaseCostCount: 0,
      matchedLogisticsCostCount: 0,
      matchedAdCostCount: 0,
    },
  );
}

function buildRemark(options: {
  dataDate: string;
  storeCount: number;
  fetchedCount: number;
  writtenCount: number;
  skippedCount: number;
  failedStores: string[];
  adRecordCount: number;
  adTotalCost: number;
  errors: string[];
}): string {
  const parts = [
    "CODEX执行：当日数据所有店铺同步",
    "统计主键=Item ID",
    `数据日期=${options.dataDate}`,
    `店铺数=${options.storeCount}`,
    `抓取商品数=${options.fetchedCount}`,
    `写入条数=${options.writtenCount}`,
    `过滤跳过条数=${options.skippedCount}`,
    `失败店铺=${options.failedStores.length > 0 ? options.failedStores.join("|") : "无"}`,
    `广告记录数=${options.adRecordCount}`,
    `广告总花费=${Number(options.adTotalCost.toFixed(2))}`,
  ];

  if (options.errors.length > 0) {
    parts.push(`非阻塞错误=${options.errors.join("；")}`);
  }

  return parts.join("，");
}

export interface DailyRowsResult {
  rows: SheetRow[];
  rawRows: SheetRow[];
  results: StoreSyncResult[];
  totals: ReturnType<typeof sumResults>;
  failedStores: string[];
  nonBlockingErrors: string[];
  skippedCount: number;
}

export async function generateDailyRowsForDate(dataDate: string, writer: FeishuSheetWriter): Promise<DailyRowsResult> {
  const config = loadConfig();
  config.timeoutMs = TIMEOUT_MS;
  const client = new LingxingClient(config);
  const itemOwnerMap = readItemOwnerMap(writer);
  const results: StoreSyncResult[] = [];

  for (const [index, store] of STORES.entries()) {
    if (index > 0) {
      console.log("店铺间等待 1000ms，降低限速风险");
      await sleep(1000);
    }

    results.push(await syncStore(client, store, dataDate, itemOwnerMap));
  }

  const totals = sumResults(results);
  const failedStores = results.filter((result) => result.failed).map((result) => result.store.storeName);
  const nonBlockingErrors = results.flatMap((result) =>
    result.errors.map((message) => `${result.store.storeName}: ${message}`),
  );

  if (failedStores.length === STORES.length) {
    throw new Error(`全部店铺同步失败，已停止写入，避免清空当日数据。失败原因：${nonBlockingErrors.join("；")}`);
  }

  const rawRows = results.flatMap((result) => result.rawRows);
  const rows = ENABLE_ZERO_ACTIVITY_FILTER ? rawRows.filter((row) => shouldIncludeDailyItem(row)) : rawRows;
  const skippedCount = rawRows.length - rows.length;

  return {
    rows,
    rawRows,
    results,
    totals,
    failedStores,
    nonBlockingErrors,
    skippedCount,
  };
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

  let fetchedCount = 0;
  let writtenCount = 0;
  let skippedCount = 0;
  let failedCount = 0;
  let status = "success";
  let errorMessage = "";
  let writeRange = "A2:V2";
  let clearRange = `A2:V${BASE_CLEAR_END_ROW}`;
  let logSuccess = false;
  let writeSuccess = false;
  let clearSuccess = false;
  let remark = `CODEX执行：当日数据所有店铺同步，统计主键=Item ID，数据日期=${DEFAULT_DATA_DATE}，原因：未执行`;

  console.log("当日数据所有 Walmart 店铺同步");
  console.log(`运行ID: ${runId}`);
  console.log(`写入模式: ${confirmWrite ? "confirm-write" : "dry-run"}`);
  console.log(`数据日期: ${DEFAULT_DATA_DATE}`);
  console.log("统计主键=Item ID");
  console.log(`目标 Sheet: ${TARGET_SHEET_NAME} (${currentReport.sheets[TARGET_SHEET_NAME]})`);
  console.log(`店铺数: ${STORES.length}`);
  console.log(`零活跃过滤规则: ${ENABLE_ZERO_ACTIVITY_FILTER ? "启用" : "未启用"}`);

  try {
    const generated = await generateDailyRowsForDate(DEFAULT_DATA_DATE, writer);
    const { totals, failedStores, nonBlockingErrors } = generated;
    fetchedCount = totals.fetchedCount;
    const rows = generated.rows;
    skippedCount = generated.skippedCount;
    writtenCount = rows.length;
    applyFormulaColumns(rows);
    writeRange = getWriteRange(rows.length);
    // 用实际行数作为清空上限，防止旧数据残留
    const sheetRowCount = writer.getRowCount({
      spreadsheetToken: currentReport.spreadsheetToken,
      sheetId: currentReport.sheets[TARGET_SHEET_NAME],
      sheetName: TARGET_SHEET_NAME,
    });
    const dynamicClearEnd = Math.max(BASE_CLEAR_END_ROW, sheetRowCount, rows.length + 1);
    clearRange = `A2:V${dynamicClearEnd}`;
    validateClearRange(clearRange);
    failedCount = failedStores.length;
    status = failedStores.length > 0 ? "partial_success" : "success";

    console.log("");
    console.log("汇总结果:");
    console.log(`数据日期: ${DEFAULT_DATA_DATE}`);
    console.log("统计主键=Item ID");
    console.log(`店铺数: ${STORES.length}`);
    console.log(`失败店铺: ${failedStores.length > 0 ? failedStores.join(", ") : "无"}`);
    console.log(`Walmart商品抓取页数: ${totals.pageCount}`);
    console.log(`Walmart商品抓取条数: ${fetchedCount}`);
    console.log(`销量接口抓取条数: ${totals.salesQtyFetchedCount}`);
    console.log(`匹配销量数量: ${totals.matchedSalesQtyCount}`);
    console.log(`销售额接口抓取条数: ${totals.salesAmountFetchedCount}`);
    console.log(`匹配销售额数量: ${totals.matchedSalesAmountCount}`);
    console.log(`广告接口抓取条数: ${totals.adFetchedCount}`);
    console.log(`匹配广告花费数量: ${totals.matchedAdCostCount}`);
    console.log(`广告总花费: ${Number(totals.adTotalCost.toFixed(2))}`);
    console.log(`产品成本接口请求批次数: ${totals.productCostBatchCount}`);
    console.log(`匹配采购成本数量: ${totals.matchedPurchaseCostCount}`);
    console.log(`匹配头程成本数量: ${totals.matchedLogisticsCostCount}`);
    console.log(`匹配负责人数量: ${totals.matchedOwnerCount}`);
    console.log(`匹配WFS费用数量: ${totals.matchedWfsFeeCount}`);
    console.log(`零活跃过滤跳过条数: ${skippedCount}`);
    console.log(`清空范围: ${clearRange}`);
    console.log(`写入范围: ${writeRange}`);
    console.log("写入预览（前 3 行）:");
    console.log(JSON.stringify(rows.slice(0, 3), null, 2));

    if (confirmWrite) {
      writer.clearRange({
        spreadsheetToken: currentReport.spreadsheetToken,
        sheetId: currentReport.sheets[TARGET_SHEET_NAME],
        sheetName: TARGET_SHEET_NAME,
        range: clearRange,
        dryRun,
        confirmWrite,
      });
      clearSuccess = true;
      console.log("是否清理成功: 是");

      if (rows.length > 0) {
        writer.writeCells({
          spreadsheetToken: currentReport.spreadsheetToken,
          sheetId: currentReport.sheets[TARGET_SHEET_NAME],
          sheetName: TARGET_SHEET_NAME,
          range: writeRange,
          rows,
          dryRun,
          confirmWrite,
          allowOverwrite: true,
        });
      }
    } else {
      writer.writeCells({
        spreadsheetToken: currentReport.spreadsheetToken,
        sheetId: currentReport.sheets[TARGET_SHEET_NAME],
        sheetName: TARGET_SHEET_NAME,
        range: writeRange,
        rows: rows.length > 0 ? rows : [new Array(22).fill("")],
        dryRun,
        confirmWrite,
        allowOverwrite: true,
      });
    }

    writeSuccess = true;
    console.log(`是否写入成功: ${writeSuccess ? "是" : "否"}`);

    remark = buildRemark({
      dataDate: DEFAULT_DATA_DATE,
      storeCount: STORES.length,
      fetchedCount,
      writtenCount,
      skippedCount,
      failedStores,
      adRecordCount: totals.adFetchedCount,
      adTotalCost: totals.adTotalCost,
      errors: nonBlockingErrors,
    });
  } catch (error) {
    failedCount = STORES.length;
    status = "failed";
    errorMessage = getErrorMessage(error);
    console.log(`同步失败: ${errorMessage}`);
    console.log(`是否清理成功: ${clearSuccess ? "是" : "否"}`);
    console.log(`是否写入成功: ${writeSuccess ? "是" : "否"}`);
    remark = `CODEX执行：当日数据所有店铺同步，统计主键=Item ID，数据日期=${DEFAULT_DATA_DATE}，店铺数=${STORES.length}，抓取商品数=${fetchedCount}，写入条数=${writtenCount}，过滤跳过条数=${skippedCount}，失败店铺=全部，广告记录数=0，广告总花费=0，原因：${errorMessage}`;
  } finally {
    const durationSeconds = Number(((Date.now() - startedAt) / 1000).toFixed(3));

    try {
      logger.append({
        executedAt: new Date().toISOString(),
        taskName: TASK_NAME,
        targetSheet: TARGET_SHEET_NAME,
        operationType: dryRun ? "dry-run" : "replace",
        dataSource: WALMART_LIST_PATH,
        dateRange: DEFAULT_DATA_DATE,
        fetchedCount,
        writtenCount,
        updatedCount: 0,
        skippedCount,
        failedCount,
        status: dryRun && status === "success" ? "dry-run" : status,
        errorMessage,
        durationSeconds,
        runId,
        environment: "local",
        remark,
      });
      logSuccess = true;
    } catch (logError) {
      console.log(`记录操作日志失败: ${getErrorMessage(logError)}`);
    }

    console.log(`日志是否写入成功: ${logSuccess ? "是" : "否"}`);
    if (status === "failed") {
      process.exitCode = 1;
    }
  }
}

if (require.main === module) {
  main().catch((error) => {
    console.log(`执行失败: ${getErrorMessage(error)}`);
    process.exitCode = 1;
  });
}
