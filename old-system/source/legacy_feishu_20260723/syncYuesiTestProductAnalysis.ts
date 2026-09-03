import currentReport from "../config/currentReportFieldMapping.json";
import { readFileSync } from "fs";
import { loadConfig } from "./config";
import { FeishuSheetWriter, SheetRow, WriteCellsOptions } from "./feishuSheetWriter";
import { LingxingClient } from "./lingxingClient";
import { STORES } from "./syncDailyBaseData";
import { TableOperationLogger } from "./tableOperationLogger";

const axios = require("axios/dist/node/axios.cjs") as typeof import("axios").default;

const TASK_NAME = "悦斯店铺测品数据分析";
const JIANGZIBO_OPEN_ID = "<REDACTED_FEISHU_OPEN_ID>";
const SOURCE_SHEET_NAME = "5月销售明细_复盘";
const TARGET_SHEET_NAME = "悦斯测品汇总";
const OPERATION_LOG_SHEET_NAME = "悦斯测品运营日志";
const YUESI_AI_CONFIG_SHEET_NAME = "悦斯AI诊断配置";
const AI_PROMPT_CONFIG_SHEET_NAME = "AI诊断提示词配置";
const AUTO_AD_SEARCH_TERM_SHEET_NAME = "自动广告搜索词聚合分析";
const LOG_SHEET_NAME = "表格操作日志";
const STORE_NAME = "CN2502-悦斯电子(陈文胜）";
const STORE = STORES.find((store) => store.storeName === STORE_NAME);
const READ_START_ROW = 2;
const READ_END_ROW = 20000;
const READ_BATCH_SIZE = 500;
const WALMART_LIST_PATH = "/basicOpen/multiplatform/walmart/list";
const WALMART_SP_AD_PATH = "/basicOpen/multiplatform/ads/reportAdItemSpList";
const WALMART_SP_KEYWORD_PATH = "/basicOpen/multiplatform/ads/reportKeywordSpList";
const WALMART_LIST_PAGE_SIZE = 200;
const WALMART_LIST_MAX_PAGES = 50;
const AD_PAGE_SIZE = 200;
const AD_MAX_PAGES = 40;
const TIMEOUT_MS = 120000;
const DEFAULT_RECENT_AD_DAYS = 3;
const DEFAULT_AD_HISTORY_START_DATE = "2026-05-01";
const MAIN_SHEET_HEADERS = [
  "店铺",
  "商品ID",
  "MSKU",
  "负责人",
  "首次广告日期",
  "测品天数",
  "累计销量",
  "累计销售额",
  "累计广告费",
  "广告占比",
  "非WFS库存",
  "运营日志执行情况AI分析",
  "测品结果AI分析",
  "人工审核结果",
  "备注",
];
const OPERATION_LOG_HEADERS = [
  "分析日期",
  "商品ID",
  "MSKU",
  "负责人",
  "非WFS库存",
  "近3天广告花费",
  "近3天广告销售额",
  "近3天广告订单数",
  "近3天广告曝光",
  "近3天广告点击",
  "近3天CTR",
  "近3天CPC",
  "近3天CVR",
  "近3天ACOS",
  "产品数据问题",
  "广告调整意见",
  "运营日志",
  "备注",
  "测品预警",
];
const MAIN_ALLOWED_UPDATE_FIELDS = [
  "首次广告日期",
  "测品天数",
  "累计销量",
  "累计销售额",
  "累计广告费",
  "广告占比",
  "非WFS库存",
  "运营日志执行情况AI分析",
  "测品结果AI分析",
];
const MAIN_PROTECTED_FIELDS = ["负责人", "人工审核结果", "备注"];
const OPERATION_LOG_AUTO_FIELDS = OPERATION_LOG_HEADERS.slice(0, OPERATION_LOG_HEADERS.indexOf("运营日志"));
const OPERATION_LOG_PROTECTED_FIELDS = ["运营日志", "备注"];
const REQUIRED_YUESI_AI_RULE_TYPES = [
  "AI测品评分",
  "测品预警",
  "广告ACOS标准",
  "CPC标准",
  "CTR标准",
  "CVR标准",
  "自动广告分析规则",
  "手动广告分析规则",
  "否定词规则",
  "放量暂停淘汰规则",
  "通用扣分",
  "一票否决",
  "AI提示词模板",
  "分析项开关",
  "评级规则",
];

const SHEETS = currentReport.sheets as Record<string, string>;
let activeTargetSheetName = TARGET_SHEET_NAME;

type RuntimeEnv = "dev" | "staging" | "prod";

interface DetailRow {
  date: string;
  storeName: string;
  itemId: string;
  msku: string;
  sku: string;
  productName: string;
  owner: string;
  salesQty: number;
  salesAmount: number;
  adCost: number;
}

interface ProductSummary {
  storeName: string;
  itemId: string;
  msku: string;
  owner: string;
  firstSaleDate: string;
  firstAdActivityDate: string;
  lastSaleDate: string;
  activeDays: Set<string>;
  totalSalesQty: number;
  totalSalesAmount: number;
  totalAdCost: number;
}

interface ListingStatusInfo {
  statusName: string;
  availableQuantity: number;
  wfsAvailableQuantity: number;
  listingStartTime: string;
  offerStartDate: string;
  offerEndDate: string;
}

interface AdItemMetric {
  firstAdDate: string;
  recentAdSpend: number;
  recentAdSales: number;
  recentAdOrders: number;
  recentImpressions: number;
  recentClicks: number;
  recentAdRecordCount: number;
}

interface AdItemFetchResult {
  metricMap: Map<string, AdItemMetric>;
  fetchedCount: number;
  errorMessages: string[];
}

interface KeywordAdRecord {
  keyword: string;
  campaignName: string;
  adGroupName: string;
  matchType: string;
  campaignType: string;
  impressions: number;
  clicks: number;
  adSpend: number;
  attributedSales: number;
  attributedOrders: number;
  ctr: number;
  cpc: number;
  cvr: number;
  acos: number;
}

interface KeywordAdFetchResult {
  recordMap: Map<string, KeywordAdRecord[]>;
  allRecords: KeywordAdRecord[];
  fetchedCount: number;
  matchedCount: number;
  errorMessages: string[];
}

interface ExternalAutoAdSheetConfig {
  spreadsheetToken: string;
  sheetId: string;
  sheetName: string;
}

interface AutoAdSearchTermResult {
  map: Map<string, KeywordAdRecord[]>;
  fetchedCount: number;
  matchedCount: number;
  sheetConfigured: boolean;
}

interface MainSheetPreviewRow {
  rowNumber: number;
  storeName: string;
  itemId: string;
  msku: string;
  owner: string;
  firstAdDate: string;
  testDays: number;
  totalSalesQty: number;
  totalSalesAmount: number;
  totalAdCost: number;
  adRatio: string;
  nonWfsInventory: number;
}

interface LogSheetExistingInfo {
  existingKeys: Set<string>;
  rowByKey: Map<string, number>;
  nextRowNumber: number;
}

interface MainSheetExistingInfo {
  rowByKey: Map<string, number>;
  nextRowNumber: number;
}

interface AnalysisWindow {
  startDate: string;
  endDate: string;
  text: string;
}

interface OperationLogMetricInput {
  adSpend: number;
  adSales: number;
  adOrders: number;
  impressions: number;
  clicks: number;
}

interface SafeWriteResult {
  mainUpdatedItemIds: string[];
  mainInsertedItemIds: string[];
  logInsertedItemIds: string[];
  logOverwrittenItemIds: string[];
  logAdMetricRepairedItemIds: string[];
  duplicateLogSkippedCount: number;
  skippedNoAdMetricCount: number;
  filteredCandidateCount: number;
}

interface FirstAdDateBackfillResult {
  scannedCount: number;
  writableCount: number;
  updatedCount: number;
  skippedCount: number;
  missingCount: number;
  updatedItemIds: string[];
}

interface BackfillLogRow {
  rowNumber: number;
  analysisDate: string;
  itemId: string;
}

interface BackfillAdData {
  adResult: AdItemFetchResult;
  keywordResult: KeywordAdFetchResult;
  analysisWindow: AnalysisWindow;
}

interface BackfillAdMetricsResult {
  totalRows: number;
  repairedCount: number;
  skippedNoApiDataCount: number;
  apiFailedCount: number;
  lastProcessedRow: number;
}

interface YuesiAiConfigRule {
  ruleType: string;
  dimension: string;
  weight: string;
  standard: string;
  minScore: string;
  maxScore: string;
  triggerResult: string;
  scoreImpact: string;
  ratingLimit: string;
  description: string;
  enabled: string;
}

interface AiPromptConfig {
  raw: Record<string, string>;
}

interface ScoreDimensionResult {
  dimension: string;
  score: number;
  weight: number;
  weightedScore: number;
  source: "人工" | "AI";
  rule: YuesiAiConfigRule | undefined;
  note: string;
}

function getArg(name: string, defaultValue = ""): string {
  const prefix = `--${name}=`;
  const arg = process.argv.find((item) => item.startsWith(prefix));
  return arg ? arg.slice(prefix.length) : defaultValue;
}

function resolveRuntimeEnv(): RuntimeEnv {
  const value = getArg("env", "dev").toLowerCase();
  if (value === "dev" || value === "staging" || value === "prod") {
    return value;
  }
  throw new Error(`--env 只支持 dev/staging/prod，当前值: ${value}`);
}

function configureRuntimeSheets(env: RuntimeEnv): void {
  if (env === "staging" && SHEETS[`${TARGET_SHEET_NAME}_staging`]) {
    activeTargetSheetName = `${TARGET_SHEET_NAME}_staging`;
    return;
  }
  activeTargetSheetName = TARGET_SHEET_NAME;
}

function getActiveTargetSheetId(): string {
  return SHEETS[activeTargetSheetName] || SHEETS[TARGET_SHEET_NAME];
}

function isAiEnabledForLog(): boolean {
  return normalizeText(process.env.ENABLE_AI_DIAGNOSIS).toLowerCase() === "true";
}

/**
 * 发送悦斯运营群飞书机器人通知
 * 优先使用 FEISHU_YUESI_WEBHOOK_URL；未配置时回退到 FEISHU_NO_ORDER_WEBHOOK_URL
 */
async function sendYuesiAlertMessage(text: string): Promise<void> {
  const webhookUrl = (
    process.env.FEISHU_YUESI_WEBHOOK_URL ??
    process.env.FEISHU_NO_ORDER_WEBHOOK_URL ??
    ""
  ).trim();
  if (!webhookUrl) {
    console.log(`[飞书通知] 未配置 FEISHU_YUESI_WEBHOOK_URL，跳过发送`);
    return;
  }
  try {
    const resp = await axios.post(
      webhookUrl,
      { msg_type: "text", content: { text } },
      { headers: { "Content-Type": "application/json" }, timeout: 10000 },
    );
    const data = resp.data as Record<string, unknown>;
    const ok = data.StatusCode === 0 || data.code === 0;
    console.log(ok ? `[飞书通知] 发送成功` : `[飞书通知] 响应异常: ${JSON.stringify(data)}`);
  } catch (e) {
    console.log(`[飞书通知] 请求失败: ${e instanceof Error ? e.message : String(e)}`);
  }
}

function printRuntimeContext(options: {
  env: RuntimeEnv;
  confirmWrite: boolean;
  dryRun: boolean;
  allowFeishuWrite: boolean;
  limit?: number;
}): void {
  console.log(`当前 env: ${options.env}`);
  console.log(`写入模式: ${options.confirmWrite ? "confirm-write" : "dry-run"}`);
  console.log(`是否允许写飞书: ${options.allowFeishuWrite ? "是" : "否"}`);
  console.log(`是否AI启用: ${isAiEnabledForLog() ? "是" : "否"}`);
  console.log(`limit: ${options.limit ?? "未设置"}`);
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

function normalizeHeader(value: unknown): string {
  return normalizeText(value).replace(/\s+/g, "").toLowerCase();
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

function ratio(numerator: number, denominator: number): number {
  return denominator === 0 ? 0 : Number((numerator / denominator).toFixed(4));
}

function money(value: number): number {
  return Number(value.toFixed(2));
}

function percentText(value: number): string {
  return `${Math.round(value * 100)}%`;
}

function percentText2(value: number): string {
  return `${(value * 100).toFixed(2)}%`;
}

function columnName(index: number): string {
  let value = index;
  let result = "";
  while (value > 0) {
    const remainder = (value - 1) % 26;
    result = String.fromCharCode(65 + remainder) + result;
    value = Math.floor((value - 1) / 26);
  }
  return result;
}

function addDays(dateText: string, days: number): string {
  const [year, month, day] = dateText.split("-").map(Number);
  const date = new Date(Date.UTC(year, month - 1, day));
  date.setUTCDate(date.getUTCDate() + days);
  return date.toISOString().slice(0, 10);
}

function daysBetweenInclusive(startDate: string, endDate: string): number {
  const [startYear, startMonth, startDay] = startDate.split("-").map(Number);
  const [endYear, endMonth, endDay] = endDate.split("-").map(Number);
  if (!startYear || !startMonth || !startDay || !endYear || !endMonth || !endDay) {
    return 0;
  }
  const start = Date.UTC(startYear, startMonth - 1, startDay);
  const end = Date.UTC(endYear, endMonth - 1, endDay);
  if (end < start) {
    return 0;
  }
  return Math.floor((end - start) / 86400000) + 1;
}

function toDateOnly(value: unknown): string {
  return normalizeText(value).slice(0, 10);
}

function extractDataArray(data: unknown): unknown[] {
  if (Array.isArray(data)) {
    return data;
  }
  if (data && typeof data === "object") {
    const value = data as { data?: unknown; list?: unknown; rows?: unknown; records?: unknown };
    if (Array.isArray(value.data)) return value.data;
    if (Array.isArray(value.list)) return value.list;
    if (Array.isArray(value.rows)) return value.rows;
    if (Array.isArray(value.records)) return value.records;
    if (value.data && typeof value.data === "object") {
      const nested = value.data as { list?: unknown; rows?: unknown; records?: unknown };
      if (Array.isArray(nested.list)) return nested.list;
      if (Array.isArray(nested.rows)) return nested.rows;
      if (Array.isArray(nested.records)) return nested.records;
    }
  }
  return [];
}

function extractTotal(data: unknown): number {
  if (data && typeof data === "object") {
    const value = data as { total?: unknown; data?: unknown };
    const direct = Number(value.total);
    if (Number.isFinite(direct) && direct > 0) return direct;
    if (value.data && typeof value.data === "object") {
      const nested = value.data as { total?: unknown };
      const nestedTotal = Number(nested.total);
      if (Number.isFinite(nestedTotal) && nestedTotal > 0) return nestedTotal;
    }
  }
  return 0;
}

function firstText(record: Record<string, unknown>, keys: string[]): string {
  for (const key of keys) {
    const value = normalizeText(record[key]);
    if (value) {
      return value;
    }
  }
  return "";
}

function firstNumber(record: Record<string, unknown>, keys: string[]): number {
  for (const key of keys) {
    const value = toNumber(record[key]);
    if (value !== 0) {
      return value;
    }
  }
  return 0;
}

function firstDateText(record: Record<string, unknown>, keys: string[]): string {
  for (const key of keys) {
    const value = toDateOnly(record[key]);
    if (/^\d{4}-\d{2}-\d{2}$/.test(value)) {
      return value;
    }
  }
  return "";
}

function splitDateRanges(startDate: string, endDate: string, maxDays: number): Array<{ startDate: string; endDate: string }> {
  const ranges: Array<{ startDate: string; endDate: string }> = [];
  let cursor = startDate;
  while (cursor <= endDate) {
    const rangeEnd = addDays(cursor, maxDays - 1);
    const end = rangeEnd < endDate ? rangeEnd : endDate;
    ranges.push({ startDate: cursor, endDate: end });
    cursor = addDays(end, 1);
  }
  return ranges;
}

function readDetailRows(writer: FeishuSheetWriter, startDate: string, endDate: string): DetailRow[] {
  const rows: DetailRow[] = [];
  const sourceSheetId = SHEETS[SOURCE_SHEET_NAME];
  const sourceRowCount = writer.getRowCount({
    spreadsheetToken: currentReport.spreadsheetToken,
    sheetId: sourceSheetId,
    sheetName: SOURCE_SHEET_NAME,
  });
  const readEndRow = Math.min(READ_END_ROW, sourceRowCount);

  for (let startRow = READ_START_ROW; startRow <= readEndRow; startRow += READ_BATCH_SIZE) {
    const endRow = Math.min(startRow + READ_BATCH_SIZE - 1, readEndRow);
    const range = `A${startRow}:L${endRow}`;
    const chunk = writer.readValues({
      spreadsheetToken: currentReport.spreadsheetToken,
      sheetId: sourceSheetId,
      range,
    });
    const validRows = chunk
      .map((row): DetailRow => ({
        date: normalizeText(row[0]),
        storeName: normalizeText(row[1]),
        itemId: normalizeText(row[2]),
        msku: normalizeText(row[3]),
        sku: normalizeText(row[4]),
        productName: normalizeText(row[5]),
        owner: normalizeText(row[6]),
        salesQty: toNumber(row[9]),
        salesAmount: toNumber(row[10]),
        adCost: toNumber(row[11]),
      }))
      .filter((row) => {
        if (!row.date || !row.itemId || row.storeName !== STORE_NAME) {
          return false;
        }
        if (startDate && row.date < startDate) {
          return false;
        }
        if (endDate && row.date > endDate) {
          return false;
        }
        return true;
      });

    rows.push(...validRows);
    console.log(`读取 ${SOURCE_SHEET_NAME} ${range}: 悦斯有效行 ${validRows.length}`);
  }

  return rows;
}

function summarizeRows(rows: DetailRow[]): ProductSummary[] {
  const map = new Map<string, ProductSummary>();

  for (const row of rows) {
    const existing = map.get(row.itemId);
    if (!existing) {
      map.set(row.itemId, {
        storeName: row.storeName,
        itemId: row.itemId,
        msku: row.msku,
        owner: row.owner,
        firstSaleDate: row.date,
        firstAdActivityDate: row.adCost > 0 ? row.date : "",
        lastSaleDate: row.date,
        activeDays: row.salesQty > 0 ? new Set([row.date]) : new Set<string>(),
        totalSalesQty: row.salesQty,
        totalSalesAmount: row.salesAmount,
        totalAdCost: row.adCost,
      });
      continue;
    }

    existing.msku = existing.msku || row.msku;
    existing.owner = existing.owner || row.owner;
    existing.firstSaleDate = row.date < existing.firstSaleDate ? row.date : existing.firstSaleDate;
    if (row.adCost > 0 && (!existing.firstAdActivityDate || row.date < existing.firstAdActivityDate)) {
      existing.firstAdActivityDate = row.date;
    }
    existing.lastSaleDate = row.date > existing.lastSaleDate ? row.date : existing.lastSaleDate;
    if (row.salesQty > 0) {
      existing.activeDays.add(row.date);
    }
    existing.totalSalesQty += row.salesQty;
    existing.totalSalesAmount += row.salesAmount;
    existing.totalAdCost += row.adCost;
  }

  return Array.from(map.values()).sort((a, b) => {
    if (b.totalSalesQty !== a.totalSalesQty) {
      return b.totalSalesQty - a.totalSalesQty;
    }
    return a.itemId.localeCompare(b.itemId);
  });
}

async function fetchListingStatusMap(client: LingxingClient): Promise<Map<string, ListingStatusInfo>> {
  if (!STORE) {
    throw new Error(`未找到店铺配置：${STORE_NAME}`);
  }

  const map = new Map<string, ListingStatusInfo>();
  let fetchedCount = 0;
  for (let page = 0; page < WALMART_LIST_MAX_PAGES; page += 1) {
    const offset = page * WALMART_LIST_PAGE_SIZE;
    const response = await client.request<unknown>({
      method: "POST",
      path: WALMART_LIST_PATH,
      params: {
        offset,
        length: WALMART_LIST_PAGE_SIZE,
        store_ids: [STORE.storeId],
        status: [0, 1, 2, 3, 4, 5],
      },
      timeoutMs: TIMEOUT_MS,
    });
    const items = extractDataArray(response.data);
    fetchedCount += items.length;

    for (const item of items) {
      if (!item || typeof item !== "object") {
        continue;
      }
      const record = item as Record<string, unknown>;
      const itemId = normalizeText(record.item_id);
      if (!itemId) {
        continue;
      }
      map.set(itemId, {
        statusName: normalizeText(record.status_name),
        availableQuantity: toNumber(record.available_quantity),
        wfsAvailableQuantity: toNumber(record.wfs_available_quantity),
        listingStartTime: toDateOnly(record.listing_start_time),
        offerStartDate: toDateOnly(record.offer_start_date),
        offerEndDate: toDateOnly(record.offer_end_date),
      });
    }

    const total = extractTotal(response.data);
    if (items.length < WALMART_LIST_PAGE_SIZE || (total > 0 && fetchedCount >= total)) {
      break;
    }
  }

  console.log(`Walmart在线商品状态读取: ${map.size} 个商品`);
  return map;
}

async function fetchAdItemMetrics(
  client: LingxingClient,
  startDate: string,
  endDate: string,
  recentStartDate: string,
  recentEndDate: string,
): Promise<AdItemFetchResult> {
  const metricMap = new Map<string, AdItemMetric>();
  const errorMessages: string[] = [];
  let fetchedCount = 0;

  if (!STORE?.advertiserId) {
    return {
      metricMap,
      fetchedCount,
      errorMessages: [`${STORE_NAME}: advertiserId为空，无法读取广告商品报表`],
    };
  }

  const ensureMetric = (itemId: string): AdItemMetric => {
    const existing = metricMap.get(itemId);
    if (existing) {
      return existing;
    }
    const metric: AdItemMetric = {
      firstAdDate: "",
      recentAdSpend: 0,
      recentAdSales: 0,
      recentAdOrders: 0,
      recentImpressions: 0,
      recentClicks: 0,
      recentAdRecordCount: 0,
    };
    metricMap.set(itemId, metric);
    return metric;
  };

  const readAdItemRange = async (
    rangeStartDate: string,
    rangeEndDate: string,
    includeRecentMetrics: boolean,
  ): Promise<void> => {
    try {
      for (let pageNum = 1; pageNum <= AD_MAX_PAGES; pageNum += 1) {
        const response = await client.request<unknown>({
          method: "POST",
          path: WALMART_SP_AD_PATH,
          params: {
            advertiserIds: [STORE.advertiserId],
            campaignType: ["sponsoredProducts-manual", "sponsoredProducts-auto"],
            startDate: rangeStartDate,
            endDate: rangeEndDate,
            pageNum,
            pageSize: AD_PAGE_SIZE,
            paging: true,
          },
          timeoutMs: TIMEOUT_MS,
        });
        const items = extractDataArray(response.data);
        fetchedCount += items.length;

        for (const item of items) {
          if (!item || typeof item !== "object") {
            continue;
          }
          const record = item as Record<string, unknown>;
          const itemId = firstText(record, [
            "itemId",
            "item_id",
            "platformProductId",
            "platform_product_id",
            "productId",
            "product_id",
          ]);
          if (!itemId) {
            continue;
          }
          const addDate = firstDateText(record, [
            "addDate",
            "entityCreateAt",
            "createTime",
            "createdAt",
            "creationDate",
            "startDate",
            "adCreateTime",
            "adCreatedAt",
          ]);
          const existing = ensureMetric(itemId);

          if (addDate && (!existing.firstAdDate || addDate < existing.firstAdDate)) {
            existing.firstAdDate = addDate;
          }

          if (includeRecentMetrics) {
            existing.recentAdSpend += firstNumber(record, ["adSpend", "cost", "spend"]);
            existing.recentAdSales += firstNumber(record, ["attributedSales", "sales", "attributedRevenue"]);
            existing.recentAdOrders += firstNumber(record, ["attributedOrders", "orders"]);
            existing.recentImpressions += firstNumber(record, ["numAdsShown", "impressions", "adImpressions"]);
            existing.recentClicks += firstNumber(record, ["numAdsClicks", "clicks", "adClicks"]);
            existing.recentAdRecordCount += 1;
          }

          metricMap.set(itemId, existing);
        }

        const total = extractTotal(response.data);
        if (items.length < AD_PAGE_SIZE || (total > 0 && pageNum * AD_PAGE_SIZE >= total)) {
          break;
        }
      }
    } catch (error) {
      errorMessages.push(
        `${rangeStartDate}~${rangeEndDate}: ${error instanceof Error ? error.message : String(error)}`,
      );
    }
  };

  for (const range of splitDateRanges(startDate, endDate, 31)) {
    await readAdItemRange(range.startDate, range.endDate, false);
  }

  for (const range of splitDateRanges(recentStartDate, recentEndDate, 31)) {
    await readAdItemRange(range.startDate, range.endDate, true);
  }

  console.log(`SP广告商品报表读取: 记录数=${fetchedCount}，商品数=${metricMap.size}`);
  return { metricMap, fetchedCount, errorMessages };
}

function normalizeKeywordAdRecord(record: Record<string, unknown>): { itemId: string; ad: KeywordAdRecord } {
  const impressions = firstNumber(record, ["impressions", "numAdsShown", "adImpressions"]);
  const clicks = firstNumber(record, ["clicks", "numAdsClicks", "adClicks"]);
  const adSpend = firstNumber(record, ["adSpend", "cost", "spend"]);
  const attributedSales = firstNumber(record, ["attributedSales", "sales", "attributedRevenue"]);
  const attributedOrders = firstNumber(record, ["attributedOrders", "orders"]);

  return {
    itemId: firstText(record, ["itemId", "item_id", "platformProductId", "platform_product_id", "productId"]),
    ad: {
      keyword: firstText(record, [
        "keywordName",
        "keyword_name",
        "keyword",
        "keywordText",
        "keyword_text",
        "keywordValue",
        "keyword_value",
        "biddedKeyword",
        "bidKeyword",
        "searchedKeyword",
        "searchKeyword",
        "searchTerm",
        "query",
        "queryText",
        "targetingText",
        "targetingValue",
        "targetingName",
        "target",
        "word",
        "phrase",
        "adKeyword",
        "walmartKeyword",
        "关键词",
        "投放词",
        "搜索词",
      ]),
      campaignName: firstText(record, ["campaignName", "campaign_name", "name"]),
      adGroupName: firstText(record, ["adGroupName", "ad_group_name", "groupName"]),
      matchType: firstText(record, ["matchType", "match_type"]),
      campaignType: firstText(record, ["campaignType", "campaign_type", "type"]),
      impressions,
      clicks,
      adSpend,
      attributedSales,
      attributedOrders,
      ctr: firstNumber(record, ["ctr", "clickThroughRate"]) || ratio(clicks, impressions),
      cpc: firstNumber(record, ["cpc", "avgCpc"]) || ratio(adSpend, clicks),
      cvr: firstNumber(record, ["cvr", "conversionRate"]) || ratio(attributedOrders, clicks),
      acos: firstNumber(record, ["acos", "adCostSaleRatio"]) || ratio(adSpend, attributedSales),
    },
  };
}

async function fetchKeywordAdRecords(
  client: LingxingClient,
  startDate: string,
  endDate: string,
): Promise<KeywordAdFetchResult> {
  const recordMap = new Map<string, KeywordAdRecord[]>();
  const allRecords: KeywordAdRecord[] = [];
  const errorMessages: string[] = [];
  let fetchedCount = 0;
  let matchedCount = 0;

  if (!STORE?.advertiserId) {
    return {
      recordMap,
      allRecords,
      fetchedCount,
      matchedCount,
      errorMessages: [`${STORE_NAME}: advertiserId为空，无法读取关键词广告报表`],
    };
  }

  try {
    for (let pageNum = 1; pageNum <= AD_MAX_PAGES; pageNum += 1) {
      const response = await client.request<unknown>({
        method: "POST",
        path: WALMART_SP_KEYWORD_PATH,
        params: {
          advertiserIds: [STORE.advertiserId],
          campaignType: ["sponsoredProducts-manual", "sponsoredProducts-auto"],
          startDate,
          endDate,
          pageNum,
          pageSize: AD_PAGE_SIZE,
          paging: true,
        },
        timeoutMs: TIMEOUT_MS,
      });
      const items = extractDataArray(response.data);
      fetchedCount += items.length;

      for (const item of items) {
        if (!item || typeof item !== "object") {
          continue;
        }
        const normalized = normalizeKeywordAdRecord(item as Record<string, unknown>);
        allRecords.push(normalized.ad);
        if (!normalized.itemId) {
          continue;
        }
        const records = recordMap.get(normalized.itemId) ?? [];
        records.push(normalized.ad);
        recordMap.set(normalized.itemId, records);
        matchedCount += 1;
      }

      const total = extractTotal(response.data);
      if (items.length < AD_PAGE_SIZE || (total > 0 && pageNum * AD_PAGE_SIZE >= total)) {
        break;
      }
    }
  } catch (error) {
    errorMessages.push(error instanceof Error ? error.message : String(error));
  }

  for (const records of recordMap.values()) {
    records.sort((a, b) => b.adSpend - a.adSpend);
  }
  console.log(`SP广告关键词报表读取: 记录数=${fetchedCount}，直接匹配商品记录=${matchedCount}，直接商品数=${recordMap.size}`);
  return { recordMap, allRecords, fetchedCount, matchedCount, errorMessages };
}

function keywordRecordMatchesRow(record: KeywordAdRecord, row: MainSheetPreviewRow): boolean {
  const tokens = [row.itemId, row.msku, row.msku.split("-")[0]]
    .map((token) => normalizeText(token).toLowerCase())
    .filter(Boolean);
  const haystack = [
    record.keyword,
    record.campaignName,
    record.adGroupName,
    record.matchType,
    record.campaignType,
  ]
    .join(" ")
    .toLowerCase();
  return tokens.some((token) => haystack.includes(token));
}

function getKeywordAdsForRow(keywordResult: KeywordAdFetchResult, row: MainSheetPreviewRow): KeywordAdRecord[] {
  const direct = keywordResult.recordMap.get(row.itemId) ?? [];
  if (direct.length > 0) {
    return direct.slice(0, 30);
  }
  return keywordResult.allRecords.filter((record) => keywordRecordMatchesRow(record, row)).slice(0, 30);
}

function getExternalAutoAdSheetConfig(): ExternalAutoAdSheetConfig | null {
  const report = currentReport as typeof currentReport & {
    externalSheets?: { autoAdSearchTermAnalysis?: ExternalAutoAdSheetConfig };
  };
  return report.externalSheets?.autoAdSearchTermAnalysis ?? null;
}

function buildHeaderIndexMap(headers: SheetRow): Map<string, number> {
  const map = new Map<string, number>();
  headers.forEach((header, index) => {
    const normalized = normalizeHeader(header);
    if (normalized) {
      map.set(normalized, index);
    }
  });
  return map;
}

function getHeaderValue(row: SheetRow, headerMap: Map<string, number>, candidates: string[]): unknown {
  for (const candidate of candidates) {
    const index = headerMap.get(normalizeHeader(candidate));
    if (index !== undefined) {
      return row[index];
    }
  }
  return "";
}

function parseDateRangeText(value: string): { startDate: string; endDate: string } | null {
  const matches = normalizeText(value).replace(/[—–至到]/g, "~").match(/\d{4}-\d{2}-\d{2}/g);
  if (!matches || matches.length === 0) {
    return null;
  }
  return {
    startDate: matches[0],
    endDate: matches[1] ?? matches[0],
  };
}

function rangesOverlap(
  first: { startDate: string; endDate: string },
  second: { startDate: string; endDate: string },
): boolean {
  return first.startDate <= second.endDate && second.startDate <= first.endDate;
}

function normalizeAutoAdSearchTermRow(
  row: SheetRow,
  headerMap: Map<string, number>,
): { itemId: string; ad: KeywordAdRecord; dateRange: string } {
  const dateRange = normalizeText(getHeaderValue(row, headerMap, ["广告时间段", "时间段", "日期范围"]));
  const impressions = toNumber(getHeaderValue(row, headerMap, ["曝光", "Impressions"]));
  const clicks = toNumber(getHeaderValue(row, headerMap, ["点击", "Clicks"]));
  const adSpend = toNumber(getHeaderValue(row, headerMap, ["花费", "Spend", "Cost"]));
  const attributedSales = toNumber(getHeaderValue(row, headerMap, ["销售额", "Attributed Sales", "Ad Sales"]));
  const attributedOrders = toNumber(getHeaderValue(row, headerMap, ["订单", "Orders", "Attributed Orders"]));
  return {
    itemId: normalizeText(getHeaderValue(row, headerMap, ["Item ID", "商品ID", "ITEMID", "ItemID"])),
    dateRange,
    ad: {
      keyword: normalizeText(getHeaderValue(row, headerMap, ["搜索词", "Search Term", "SearchTerm"])),
      campaignName: normalizeText(getHeaderValue(row, headerMap, ["Campaign Name", "Campaign"])),
      adGroupName: normalizeText(getHeaderValue(row, headerMap, ["Ad Group Name", "Ad Group"])),
      matchType: normalizeText(getHeaderValue(row, headerMap, ["Match Type", "匹配类型"])) || "自动",
      campaignType: AUTO_AD_SEARCH_TERM_SHEET_NAME,
      impressions,
      clicks,
      adSpend,
      attributedSales,
      attributedOrders,
      ctr: toNumber(getHeaderValue(row, headerMap, ["CTR"])) || ratio(clicks, impressions),
      cpc: toNumber(getHeaderValue(row, headerMap, ["CPC"])) || ratio(adSpend, clicks),
      cvr: toNumber(getHeaderValue(row, headerMap, ["CVR", "转化率"])) || ratio(attributedOrders, clicks),
      acos: toNumber(getHeaderValue(row, headerMap, ["ACoS", "ACOS"])) || ratio(adSpend, attributedSales),
    },
  };
}

function readAutoAdSearchTermMap(writer: FeishuSheetWriter, analysisWindow: AnalysisWindow): AutoAdSearchTermResult {
  const sheetConfig = getExternalAutoAdSheetConfig();
  if (!sheetConfig) {
    console.log(`${AUTO_AD_SEARCH_TERM_SHEET_NAME}: 未配置外部 Sheet，跳过`);
    return { map: new Map(), fetchedCount: 0, matchedCount: 0, sheetConfigured: false };
  }

  const sheetRowCount = writer.getRowCount({
    spreadsheetToken: sheetConfig.spreadsheetToken,
    sheetId: sheetConfig.sheetId,
    sheetName: sheetConfig.sheetName,
  });
  const endLimit = Math.min(sheetRowCount, READ_END_ROW);
  if (endLimit < 2) {
    return { map: new Map(), fetchedCount: 0, matchedCount: 0, sheetConfigured: true };
  }

  const headerRows = writer.readValues({
    spreadsheetToken: sheetConfig.spreadsheetToken,
    sheetId: sheetConfig.sheetId,
    range: "A1:AE1",
  });
  const headerMap = buildHeaderIndexMap(headerRows[0] ?? []);
  const result = new Map<string, KeywordAdRecord[]>();
  let fetchedCount = 0;
  let matchedCount = 0;

  for (let startRow = 2; startRow <= endLimit; startRow += READ_BATCH_SIZE) {
    const endRow = Math.min(startRow + READ_BATCH_SIZE - 1, endLimit);
    const rows = writer.readValues({
      spreadsheetToken: sheetConfig.spreadsheetToken,
      sheetId: sheetConfig.sheetId,
      range: `A${startRow}:AE${endRow}`,
    });

    for (const row of rows) {
      const normalized = normalizeAutoAdSearchTermRow(row, headerMap);
      if (!normalized.itemId) {
        continue;
      }
      fetchedCount += 1;
      const parsedRange = parseDateRangeText(normalized.dateRange);
      if (parsedRange && !rangesOverlap(parsedRange, analysisWindow)) {
        continue;
      }
      const records = result.get(normalized.itemId) ?? [];
      records.push(normalized.ad);
      result.set(normalized.itemId, records);
      matchedCount += 1;
    }
  }

  for (const [itemId, records] of result.entries()) {
    result.set(
      itemId,
      records
        .sort((a, b) => b.adSpend - a.adSpend || b.clicks - a.clicks || b.impressions - a.impressions)
        .slice(0, 30),
    );
  }

  console.log(
    `${AUTO_AD_SEARCH_TERM_SHEET_NAME}读取: Sheet=${sheetConfig.sheetId}，读取记录=${fetchedCount}，匹配日期窗口记录=${matchedCount}，商品数=${result.size}`,
  );
  return { map: result, fetchedCount, matchedCount, sheetConfigured: true };
}

function isStopped(listing: ListingStatusInfo | undefined): boolean {
  if (!listing) {
    return false;
  }
  const status = listing.statusName.toUpperCase();
  if (status.includes("UNPUBLISHED") || status.includes("已停售") || status.includes("停售")) {
    return true;
  }
  return listing.availableQuantity === 0 && listing.wfsAvailableQuantity === 0;
}

function buildListingRemark(listing: ListingStatusInfo | undefined): string {
  if (!listing) {
    return "未在在线商品接口匹配到";
  }
  if (isStopped(listing)) {
    return "已停售/无库存";
  }
  return "在售或有库存";
}

function calculateTestDays(firstAdDate: string, stockOutDate: string, today: string): number {
  const normalizedFirstAdDate = toDateOnly(firstAdDate);
  if (!normalizedFirstAdDate) {
    return 0;
  }
  const endDate = toDateOnly(stockOutDate) || toDateOnly(today);
  return daysBetweenInclusive(normalizedFirstAdDate, endDate);
}

function legacyRewriteDisabled(): never {
  throw new Error("Legacy rewrite logic disabled");
}

function assertNoLegacyRewriteSymbols(): void {
  const source = readFileSync(__filename, "utf8");
  const forbiddenSymbols = [
    ["build", "Output", "Rows"].join(""),
    ["TARGET", "_HEADERS"].join(""),
  ];
  const rangeA2R = ["A2", "R"].join(":");
  const rangeA2T = ["A2", "T"].join(":");
  const forbiddenRangePatterns = [
    new RegExp(`${rangeA2R}\\d+`, "i"),
    new RegExp(`${rangeA2T}\\d+`, "i"),
    /clear\s+sheet/i,
    /full\s+overwrite/i,
  ];
  if (
    forbiddenSymbols.some((symbol) => source.includes(symbol)) ||
    forbiddenRangePatterns.some((pattern) => pattern.test(source))
  ) {
    legacyRewriteDisabled();
  }
}

const LEGACY_FORBIDDEN_FIELD_TOKENS = [
  ["累计", "毛利润"].join(""),
  ["毛", "利率"].join(""),
];

function assertSafeYuesiWrite(options: WriteCellsOptions): void {
  const normalizedRange = options.range.replace(/\s+/g, "").toUpperCase();
  if (/^A2:[RT]\d+$/.test(normalizedRange)) {
    legacyRewriteDisabled();
  }

  const serializedRows = JSON.stringify(options.rows);
  if (LEGACY_FORBIDDEN_FIELD_TOKENS.some((token) => serializedRows.includes(token))) {
    legacyRewriteDisabled();
  }
}

function writeYuesiCells(writer: FeishuSheetWriter, options: WriteCellsOptions): void {
  assertSafeYuesiWrite(options);
  const maxAttempts = 3;
  for (let attempt = 1; attempt <= maxAttempts; attempt += 1) {
    try {
      writer.writeCells(options);
      return;
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      const retryable =
        message.includes("900015205") ||
        message.includes("cs recommited") ||
        message.includes("timeout") ||
        message.includes("no such host") ||
        message.includes('"type":"network"') ||
        message.includes('"subtype":"transport"');
      if (!retryable || attempt === maxAttempts) {
        throw error;
      }
      console.log(`飞书版本冲突，重试写入 ${attempt}/${maxAttempts - 1}: ${options.range}`);
    }
  }
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function backfillModeViolation(): never {
  throw new Error("Backfill mode violation: unsafe write detected");
}

function assertSafeBackfillAdMetricWrite(options: WriteCellsOptions): void {
  const normalizedRange = options.range.replace(/\s+/g, "").toUpperCase();
  // 删除"在售判断"列后，近3天广告指标从 F 列开始（F~N，共9列）
  const match = normalizedRange.match(/^F(\d+):N(\d+)$/);
  if (!match || match[1] !== match[2]) {
    backfillModeViolation();
  }
  if (options.sheetId !== SHEETS[OPERATION_LOG_SHEET_NAME]) {
    backfillModeViolation();
  }
  if (!options.allowOverwrite || options.rows.length !== 1 || options.rows[0].length !== 9) {
    backfillModeViolation();
  }
}

function writeBackfillAdMetricCells(writer: FeishuSheetWriter, options: WriteCellsOptions): void {
  assertSafeBackfillAdMetricWrite(options);
  const maxAttempts = 3;
  for (let attempt = 1; attempt <= maxAttempts; attempt += 1) {
    try {
      writer.writeCells(options);
      return;
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      const retryable =
        message.includes("900015205") ||
        message.includes("cs recommited") ||
        message.includes("timeout") ||
        message.includes("no such host") ||
        message.includes('"type":"network"') ||
        message.includes('"subtype":"transport"');
      if (!retryable || attempt === maxAttempts) {
        throw error;
      }
      console.log(`飞书版本冲突，重试回填写入 ${attempt}/${maxAttempts - 1}: ${options.range}`);
    }
  }
}

function getDateRangeFromRows(rows: DetailRow[], inputStartDate: string, inputEndDate: string): {
  startDate: string;
  endDate: string;
} {
  const dates = rows.map((row) => row.date).filter(Boolean).sort();
  return {
    startDate: inputStartDate || dates[0] || "",
    endDate: inputEndDate || dates[dates.length - 1] || "",
  };
}

function headersMatch(actual: string[], expected: string[]): boolean {
  return expected.every((header, index) => normalizeText(actual[index]) === header);
}

function readHeaderRow(writer: FeishuSheetWriter, sheetName: string, sheetId: string, endColumn: string): string[] {
  const rows = writer.readValues({
    spreadsheetToken: currentReport.spreadsheetToken,
    sheetId,
    range: `A1:${endColumn}1`,
  });
  return (rows[0] ?? []).map((value) => normalizeText(value));
}

function readYuesiAiConfigGrouped(writer: FeishuSheetWriter): Map<string, YuesiAiConfigRule[]> {
  const sheetId = SHEETS[YUESI_AI_CONFIG_SHEET_NAME];
  if (!sheetId) {
    throw new Error(`缺少配置：${YUESI_AI_CONFIG_SHEET_NAME}`);
  }

  const rows = writer.readValues({
    spreadsheetToken: currentReport.spreadsheetToken,
    sheetId,
    range: "A1:K200",
  });
  const grouped = new Map<string, YuesiAiConfigRule[]>();

  for (const row of rows.slice(1)) {
    const ruleType = normalizeText(row[0]);
    if (!ruleType) {
      continue;
    }
    const rule: YuesiAiConfigRule = {
      ruleType,
      dimension: normalizeText(row[1]),
      weight: normalizeText(row[2]),
      standard: normalizeText(row[3]),
      minScore: normalizeText(row[4]),
      maxScore: normalizeText(row[5]),
      triggerResult: normalizeText(row[6]),
      scoreImpact: normalizeText(row[7]),
      ratingLimit: normalizeText(row[8]),
      description: normalizeText(row[9]),
      enabled: normalizeText(row[10]),
    };
    const rules = grouped.get(ruleType) ?? [];
    rules.push(rule);
    grouped.set(ruleType, rules);
  }

  return grouped;
}

function readAiPromptConfig(writer: FeishuSheetWriter): AiPromptConfig {
  const sheetId = SHEETS[AI_PROMPT_CONFIG_SHEET_NAME];
  if (!sheetId) {
    throw new Error(`缺少配置：${AI_PROMPT_CONFIG_SHEET_NAME}`);
  }

  const rows = writer.readValues({
    spreadsheetToken: currentReport.spreadsheetToken,
    sheetId,
    range: "A1:D200",
  });
  const raw: Record<string, string> = {};
  for (const row of rows.slice(1)) {
    const key = normalizeText(row[0]).toUpperCase();
    const value = normalizeText(row[1]);
    const enabled = normalizeText(row[3]).toLowerCase();
    if (!key || !value || ["false", "0", "否", "禁用"].includes(enabled)) {
      continue;
    }
    raw[key] = value;
  }
  if (!raw.KEYWORD_ANALYSIS_RULES) {
    throw new Error(`${AI_PROMPT_CONFIG_SHEET_NAME} 未命中 KEYWORD_ANALYSIS_RULES，禁止使用代码兜底广告诊断规则`);
  }
  return { raw };
}

function hasHeader(headers: string[], expectedHeader: string): boolean {
  return headers.some((header) => normalizeText(header) === expectedHeader);
}

function printRuleTypeCounts(grouped: Map<string, YuesiAiConfigRule[]>): void {
  console.log("各规则类型数量:");
  for (const ruleType of REQUIRED_YUESI_AI_RULE_TYPES) {
    console.log(`- ${ruleType}: ${grouped.get(ruleType)?.length ?? 0}`);
  }
}

function runYuesiAiConfigCheck(writer: FeishuSheetWriter): void {
  const configSheetId = SHEETS[YUESI_AI_CONFIG_SHEET_NAME];
  const mainSheetId = getActiveTargetSheetId();
  const operationLogSheetId = SHEETS[OPERATION_LOG_SHEET_NAME];
  if (!configSheetId) {
    throw new Error(`缺少配置：${YUESI_AI_CONFIG_SHEET_NAME}`);
  }
  if (!mainSheetId) {
    throw new Error(`缺少配置：${TARGET_SHEET_NAME}`);
  }
  if (!operationLogSheetId) {
    throw new Error(`缺少配置：${OPERATION_LOG_SHEET_NAME}`);
  }

  const grouped = readYuesiAiConfigGrouped(writer);
  const missingRuleTypes = REQUIRED_YUESI_AI_RULE_TYPES.filter((ruleType) => !grouped.has(ruleType));
  const mainHeaders = readHeaderRow(writer, TARGET_SHEET_NAME, mainSheetId, "AZ");
  const operationLogHeaders = readHeaderRow(writer, OPERATION_LOG_SHEET_NAME, operationLogSheetId, "AZ");
  const hasMainAiScoreHeader = hasHeader(mainHeaders, "测品结果AI分析") || hasHeader(mainHeaders, "AI测品评分与说明");
  const hasOperationWarningHeader = hasHeader(operationLogHeaders, "测品预警");

  console.log("悦斯AI诊断配置读取校验");
  console.log(`配置 Sheet: ${YUESI_AI_CONFIG_SHEET_NAME} (${configSheetId})`);
  console.log(`读取范围: A1:K200`);
  console.log(`<REDACTED_FEISHU_SHEET_ID> 是否加入配置: 是`);
  console.log(`<REDACTED_FEISHU_SHEET_ID> 是否能读取并按规则类型分组: ${missingRuleTypes.length === 0 ? "是" : "否"}`);
  printRuleTypeCounts(grouped);
  if (missingRuleTypes.length > 0) {
    console.log(`缺失规则类型: ${missingRuleTypes.join("、")}`);
  }
  console.log(`${TARGET_SHEET_NAME} 是否存在「测品结果AI分析」: ${hasMainAiScoreHeader ? "是" : "否"}`);
  console.log(`${OPERATION_LOG_SHEET_NAME} 是否存在「测品预警」: ${hasOperationWarningHeader ? "是" : "否"}`);
  console.log("是否执行真实业务写入: 否");
}

function isListingAvailable(text: string): boolean {
  const normalized = text.trim();
  if (!normalized) {
    return false;
  }
  if (normalized.includes("停售") || normalized.includes("无库存")) {
    return false;
  }
  return normalized.includes("在售") || normalized.includes("有库存");
}

function readMainSheetPreviewRows(writer: FeishuSheetWriter): MainSheetPreviewRow[] {
  const sheetId = getActiveTargetSheetId();
  const rowCount = writer.getRowCount({
    spreadsheetToken: currentReport.spreadsheetToken,
    sheetId,
    sheetName: activeTargetSheetName,
  });
  const rows: MainSheetPreviewRow[] = [];
  const readEndRow = Math.min(rowCount, 2000);

  for (let startRow = 2; startRow <= readEndRow; startRow += READ_BATCH_SIZE) {
    const endRow = Math.min(startRow + READ_BATCH_SIZE - 1, readEndRow);
    // 读取 A:K 即可（已删除"在售判断"列，非WFS库存在 K 列 index=10）
    const chunk = writer.readValues({
      spreadsheetToken: currentReport.spreadsheetToken,
      sheetId,
      range: `A${startRow}:K${endRow}`,
    });

    for (let index = 0; index < chunk.length; index += 1) {
      const row = chunk[index];
      const itemId = normalizeText(row[1]);
      if (!itemId) {
        continue;
      }
      const previewRow: MainSheetPreviewRow = {
        rowNumber: startRow + index,
        storeName: normalizeText(row[0]),
        itemId,
        msku: normalizeText(row[2]),
        owner: normalizeText(row[3]),
        firstAdDate: normalizeText(row[4]),
        testDays: toNumber(row[5]),
        totalSalesQty: toNumber(row[6]),
        totalSalesAmount: toNumber(row[7]),
        totalAdCost: toNumber(row[8]),
        adRatio: normalizeText(row[9]),
        nonWfsInventory: toNumber(row[10]),
      };
      if (previewRow.nonWfsInventory > 0) {
        rows.push(previewRow);
      }
    }
  }

  return rows;
}

function buildFallbackPreviewRowsFromSource(
  writer: FeishuSheetWriter,
  listingMap: Map<string, ListingStatusInfo>,
  adMetricMap: Map<string, AdItemMetric>,
): MainSheetPreviewRow[] {
  const detailRows = readDetailRows(writer, "", "");
  const summaries = summarizeRows(detailRows);

  return summaries
    .map((summary): MainSheetPreviewRow => {
      const listing = listingMap.get(summary.itemId);
      const adMetric = adMetricMap.get(summary.itemId);
      const firstAdDate = adMetric?.firstAdDate || summary.firstAdActivityDate;
      const stockOutDate = listing && isStopped(listing) ? listing.offerEndDate : "";
      return {
        rowNumber: 0,
        storeName: summary.storeName,
        itemId: summary.itemId,
        msku: summary.msku,
        owner: summary.owner,
        firstAdDate,
        testDays: calculateTestDays(firstAdDate, stockOutDate, getTodayInChina()),
        totalSalesQty: summary.totalSalesQty,
        totalSalesAmount: money(summary.totalSalesAmount),
        totalAdCost: money(summary.totalAdCost),
        adRatio: percentText(ratio(summary.totalAdCost, summary.totalSalesAmount)),
        nonWfsInventory: listing?.availableQuantity ?? 0,
      };
    })
    .filter((row) => row.nonWfsInventory > 0);
}

function buildFirstAdActivityDateMap(writer: FeishuSheetWriter): Map<string, string> {
  const map = new Map<string, string>();
  const detailRows = readDetailRows(writer, "", "");
  for (const row of detailRows) {
    if (row.adCost <= 0) {
      continue;
    }
    const existing = map.get(row.itemId);
    if (!existing || row.date < existing) {
      map.set(row.itemId, row.date);
    }
  }
  return map;
}

async function runFirstAdDateBackfill(options: {
  writer: FeishuSheetWriter;
  client: LingxingClient;
  analysisDate: string;
  dryRun: boolean;
  confirmWrite: boolean;
}): Promise<FirstAdDateBackfillResult> {
  const sheetId = getActiveTargetSheetId();
  if (!sheetId) {
    throw new Error(`缺少配置：${TARGET_SHEET_NAME}`);
  }

  const adHistoryStartDate = getAdHistoryStartDate();
  const adResult = await fetchAdItemMetrics(
    options.client,
    adHistoryStartDate,
    options.analysisDate,
    options.analysisDate,
    options.analysisDate,
  );
  const firstAdActivityDateMap = buildFirstAdActivityDateMap(options.writer);
  const rowCount = options.writer.getRowCount({
    spreadsheetToken: currentReport.spreadsheetToken,
    sheetId,
    sheetName: activeTargetSheetName,
  });
  const rows = options.writer.readValues({
    spreadsheetToken: currentReport.spreadsheetToken,
    sheetId,
    range: `A2:E${Math.max(rowCount, 2)}`,
  });

  let scannedCount = 0;
  let writableCount = 0;
  let skippedCount = 0;
  let missingCount = 0;
  const updatedItemIds: string[] = [];

  console.log("悦斯店铺数据分析 首次广告日期补写");
  console.log(`目标 Sheet: ${TARGET_SHEET_NAME} (${sheetId})`);
  console.log(`补写列: E 首次广告日期`);
  console.log(`首次广告日期查询范围: ${adHistoryStartDate}~${options.analysisDate}`);
  console.log("首次广告日期来源: 广告商品报表优先，销售明细首次广告花费日期兜底");

  for (let index = 0; index < rows.length; index += 1) {
    const row = rows[index];
    const rowNumber = index + 2;
    const itemId = normalizeText(row[1]);
    const existingFirstAdDate = normalizeText(row[4]);
    if (!itemId) {
      continue;
    }
    scannedCount += 1;
    const firstAdDate =
      adResult.metricMap.get(itemId)?.firstAdDate ||
      firstAdActivityDateMap.get(itemId) ||
      "";

    if (!firstAdDate) {
      missingCount += 1;
      continue;
    }
    if (existingFirstAdDate === firstAdDate) {
      skippedCount += 1;
      continue;
    }

    writableCount += 1;
    writeYuesiCells(options.writer, {
      spreadsheetToken: currentReport.spreadsheetToken,
      sheetId,
      sheetName: activeTargetSheetName,
      range: `E${rowNumber}:E${rowNumber}`,
      rows: [[firstAdDate]],
      dryRun: options.dryRun,
      confirmWrite: options.confirmWrite,
      allowOverwrite: true,
    });
    if (options.confirmWrite && !options.dryRun) {
      updatedItemIds.push(itemId);
    }
  }

  return {
    scannedCount,
    writableCount,
    updatedCount: options.confirmWrite && !options.dryRun ? updatedItemIds.length : 0,
    skippedCount,
    missingCount,
    updatedItemIds,
  };
}

function getTodayInChina(): string {
  const formatter = new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Shanghai",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  });
  const parts = formatter.formatToParts(new Date());
  const year = parts.find((part) => part.type === "year")?.value;
  const month = parts.find((part) => part.type === "month")?.value;
  const day = parts.find((part) => part.type === "day")?.value;
  if (!year || !month || !day) {
    throw new Error("无法解析中国当前日期");
  }
  return `${year}-${month}-${day}`;
}

function resolveAnalysisDate(): { serverCurrentDate: string; analysisDate: string; source: string } {
  const manualAnalysisDate = getArg("analysisDate");
  const serverCurrentDate = getTodayInChina();
  if (manualAnalysisDate) {
    return {
      serverCurrentDate,
      analysisDate: manualAnalysisDate,
      source: "手动传入",
    };
  }

  return {
    serverCurrentDate,
    analysisDate: addDays(serverCurrentDate, -2),
    source: "默认当前日期-2天",
  };
}

function getRecentAdStartDate(analysisDate: string): string {
  return addDays(analysisDate, -(DEFAULT_RECENT_AD_DAYS - 1));
}

function resolveAnalysisWindow(analysisDate: string): AnalysisWindow {
  const endDate = toDateOnly(analysisDate);
  const startDate = endDate ? getRecentAdStartDate(endDate) : "";
  if (!startDate || !endDate) {
    throw new Error("analysisWindow 缺失，禁止写入悦斯测品运营日志");
  }
  return {
    startDate,
    endDate,
    text: `${startDate} ~ ${endDate}`,
  };
}

function getAdHistoryStartDate(): string {
  return getArg("adHistoryStartDate", DEFAULT_AD_HISTORY_START_DATE);
}

function printAnalysisDateContext(serverCurrentDate: string, analysisDate: string, source: string): void {
  const analysisWindow = resolveAnalysisWindow(analysisDate);
  console.log(`服务器当前日期: ${serverCurrentDate}`);
  console.log(`实际 analysisDate: ${analysisDate}`);
  console.log(`analysisDate 来源: ${source}`);
  console.log(`analysisWindow: ${analysisWindow.text}`);
  console.log(`近3天广告范围: ${analysisWindow.startDate}~${analysisWindow.endDate}`);
}

function printFieldList(title: string, fields: string[]): void {
  console.log(`${title}:`);
  for (const field of fields) {
    console.log(`- ${field}`);
  }
}

function getRequiredLimit(env: RuntimeEnv): number {
  const rawLimit = getArg("limit");
  if (!rawLimit) {
    throw new Error("本阶段真实写入必须显式传 --limit，例如 --limit=3；未传 limit 时禁止全量写入");
  }
  if (rawLimit.toLowerCase() === "auto") {
    if (env !== "prod") {
      throw new Error(`--limit=auto 只允许 env=prod，当前 env=${env}`);
    }
    return 208;
  }
  const limit = Number(rawLimit);
  if (!Number.isInteger(limit) || limit <= 0) {
    throw new Error(`--limit 必须是正整数，当前值: ${rawLimit}`);
  }
  if (env !== "prod" && limit > 50) {
    throw new Error(`env=${env} 禁止全量写入，limit > 50 直接拒绝，当前 limit=${limit}`);
  }
  if (env === "staging" && limit > 5) {
    throw new Error(`env=staging 强制 limit <= 5，当前 limit=${limit}`);
  }
  if (env === "prod" && limit > 208) {
    throw new Error(`env=prod 强制 limit <= 208，当前 limit=${limit}`);
  }
  return limit;
}

function findLogSheetExistingInfo(writer: FeishuSheetWriter): LogSheetExistingInfo {
  const sheetId = SHEETS[OPERATION_LOG_SHEET_NAME];
  const rowCount = writer.getRowCount({
    spreadsheetToken: currentReport.spreadsheetToken,
    sheetId,
    sheetName: OPERATION_LOG_SHEET_NAME,
  });
  const readEndRow = Math.max(rowCount, 2);
  const rows = writer.readValues({
    spreadsheetToken: currentReport.spreadsheetToken,
    sheetId,
    range: `A1:B${readEndRow}`,
  });
  const existingKeys = new Set<string>();
  const rowByKey = new Map<string, number>();
  let lastNonEmptyIndex = 0;

  rows.forEach((row, index) => {
    const analysisDate = normalizeText(row[0]);
    const itemId = normalizeText(row[1]);
    if (analysisDate || itemId) {
      lastNonEmptyIndex = index;
    }
    if (analysisDate && itemId) {
      const key = `${analysisDate}::${itemId}`;
      existingKeys.add(key);
      rowByKey.set(key, index + 1);
    }
  });

  return {
    existingKeys,
    rowByKey,
    nextRowNumber: Math.max(lastNonEmptyIndex + 2, 2),
  };
}

function getBackfillLimit(): number {
  const rawLimit = getArg("limit");
  if (!rawLimit) {
    throw new Error("--backfill-ad-metrics 必须显式传 --limit=auto 或 --limit=正整数");
  }
  if (rawLimit.toLowerCase() === "auto") {
    return Number.MAX_SAFE_INTEGER;
  }
  const limit = Number(rawLimit);
  if (!Number.isInteger(limit) || limit <= 0) {
    throw new Error(`--limit 必须是 auto 或正整数，当前值: ${rawLimit}`);
  }
  return limit;
}

function getBackfillBatchSize(): number {
  const rawBatch = getArg("batch", "20");
  const batch = Number(rawBatch);
  if (!Number.isInteger(batch) || batch <= 0) {
    throw new Error(`--batch 必须是正整数，当前值: ${rawBatch}`);
  }
  return batch;
}

function getBackfillLastProcessedRow(): number {
  const rawLastProcessedRow = getArg("lastProcessedRow", "1");
  const lastProcessedRow = Number(rawLastProcessedRow);
  if (!Number.isInteger(lastProcessedRow) || lastProcessedRow < 1) {
    throw new Error(`--lastProcessedRow 必须是大于等于1的整数，当前值: ${rawLastProcessedRow}`);
  }
  return lastProcessedRow;
}

function readBackfillLogRows(writer: FeishuSheetWriter, limit: number, lastProcessedRow: number): BackfillLogRow[] {
  const sheetId = SHEETS[OPERATION_LOG_SHEET_NAME];
  const rowCount = writer.getRowCount({
    spreadsheetToken: currentReport.spreadsheetToken,
    sheetId,
    sheetName: OPERATION_LOG_SHEET_NAME,
  });
  const startRow = Math.max(2, lastProcessedRow + 1);
  const rows: BackfillLogRow[] = [];
  if (startRow > rowCount) {
    return rows;
  }

  for (let currentRow = startRow; currentRow <= rowCount && rows.length < limit; currentRow += READ_BATCH_SIZE) {
    const endRow = Math.min(currentRow + READ_BATCH_SIZE - 1, rowCount);
    const chunk = writer.readValues({
      spreadsheetToken: currentReport.spreadsheetToken,
      sheetId,
      range: `A${currentRow}:B${endRow}`,
    });
    for (let index = 0; index < chunk.length && rows.length < limit; index += 1) {
      const rowNumber = currentRow + index;
      const analysisDate = toDateOnly(chunk[index][0]);
      const itemId = normalizeText(chunk[index][1]);
      if (!analysisDate || !itemId) {
        continue;
      }
      rows.push({ rowNumber, analysisDate, itemId });
    }
  }

  return rows;
}

async function fetchBackfillAdData(
  client: LingxingClient,
  analysisDate: string,
  cache: Map<string, BackfillAdData>,
): Promise<BackfillAdData> {
  const cached = cache.get(analysisDate);
  if (cached) {
    return cached;
  }
  const analysisWindow = resolveAnalysisWindow(analysisDate);
  const adResult = await fetchAdItemMetrics(
    client,
    analysisWindow.startDate,
    analysisWindow.endDate,
    analysisWindow.startDate,
    analysisWindow.endDate,
  );
  const keywordResult = await fetchKeywordAdRecords(client, analysisWindow.startDate, analysisWindow.endDate);
  assertAdApiDataReady(adResult, keywordResult);
  const data = { adResult, keywordResult, analysisWindow };
  cache.set(analysisDate, data);
  return data;
}

async function runBackfillAdMetrics(options: {
  writer: FeishuSheetWriter;
  client: LingxingClient;
  limit: number;
  batchSize: number;
  lastProcessedRow: number;
}): Promise<BackfillAdMetricsResult> {
  const operationLogSheetId = SHEETS[OPERATION_LOG_SHEET_NAME];
  if (!operationLogSheetId) {
    throw new Error(`缺少配置：${OPERATION_LOG_SHEET_NAME}`);
  }

  const rows = readBackfillLogRows(options.writer, options.limit, options.lastProcessedRow);
  const adDataCache = new Map<string, BackfillAdData>();
  const failedDateSet = new Set<string>();
  const result: BackfillAdMetricsResult = {
    totalRows: rows.length,
    repairedCount: 0,
    skippedNoApiDataCount: 0,
    apiFailedCount: 0,
    lastProcessedRow: options.lastProcessedRow,
  };

  console.log("<REDACTED_FEISHU_SHEET_ID> 历史广告指标回填");
  console.log(`目标 Sheet: ${OPERATION_LOG_SHEET_NAME} (${operationLogSheetId})`);
  console.log("回填列: F:N（删除在售判断列后，广告指标起始列由G改为F）");
  console.log("广告数据来源: 领星广告商品报表 + 关键词报表");
  console.log(`读取历史行数: ${rows.length}`);
  console.log(`批大小: ${options.batchSize}`);
  console.log(`断点 lastProcessedRow: ${options.lastProcessedRow}`);

  for (let offset = 0; offset < rows.length; offset += options.batchSize) {
    const batchRows = rows.slice(offset, offset + options.batchSize);
    const dates = Array.from(new Set(batchRows.map((row) => row.analysisDate)));
    for (const analysisDate of dates) {
      if (failedDateSet.has(analysisDate)) {
        continue;
      }
      try {
        const data = await fetchBackfillAdData(options.client, analysisDate, adDataCache);
        console.log(
          `广告API读取成功: analysisDate=${analysisDate}，analysisWindow=${data.analysisWindow.startDate}~${data.analysisWindow.endDate}` +
            `，商品报表记录=${data.adResult.fetchedCount}，关键词报表记录=${data.keywordResult.fetchedCount}`,
        );
      } catch (error) {
        failedDateSet.add(analysisDate);
        console.log(
          `广告API读取失败: analysisDate=${analysisDate}，原因=${error instanceof Error ? error.message : String(error)}`,
        );
      }
    }

    for (const row of batchRows) {
      result.lastProcessedRow = row.rowNumber;
      if (failedDateSet.has(row.analysisDate)) {
        result.apiFailedCount += 1;
        continue;
      }
      const data = adDataCache.get(row.analysisDate);
      if (!data) {
        result.apiFailedCount += 1;
        continue;
      }
      const adMetric = data.adResult.metricMap.get(row.itemId);
      if (!hasOperationLogAdMetricData(adMetric)) {
        result.skippedNoApiDataCount += 1;
        continue;
      }
      writeBackfillAdMetricCells(options.writer, {
        spreadsheetToken: currentReport.spreadsheetToken,
        sheetId: operationLogSheetId,
        sheetName: OPERATION_LOG_SHEET_NAME,
        // 删除"在售判断"列后，近3天广告指标位于 F~N（共9列）
        range: `F${row.rowNumber}:N${row.rowNumber}`,
        rows: [buildOperationLogAdMetricCells(adMetric, row.itemId)],
        dryRun: false,
        confirmWrite: true,
        allowOverwrite: true,
      });
      result.repairedCount += 1;
    }

    console.log(
      `批次完成: ${Math.floor(offset / options.batchSize) + 1}` +
        `，本批行数=${batchRows.length}` +
        `，累计修复=${result.repairedCount}` +
        `，跳过无API数据=${result.skippedNoApiDataCount}` +
        `，API失败=${result.apiFailedCount}` +
        `，lastProcessedRow=${result.lastProcessedRow}`,
    );
    if (offset + options.batchSize < rows.length) {
      await sleep(500);
    }
  }

  return result;
}

function buildMainSheetKey(storeName: string, itemId: string): string {
  return `${storeName}::${itemId}`;
}

function findMainSheetExistingInfo(writer: FeishuSheetWriter): MainSheetExistingInfo {
  const sheetId = getActiveTargetSheetId();
  const rowCount = writer.getRowCount({
    spreadsheetToken: currentReport.spreadsheetToken,
    sheetId,
    sheetName: activeTargetSheetName,
  });
  const readEndRow = Math.max(rowCount, 2);
  const rows = writer.readValues({
    spreadsheetToken: currentReport.spreadsheetToken,
    sheetId,
    range: `A1:B${readEndRow}`,
  });
  const rowByKey = new Map<string, number>();
  let lastNonEmptyIndex = 0;

  rows.forEach((row, index) => {
    const storeName = normalizeText(row[0]);
    const itemId = normalizeText(row[1]);
    if (storeName || itemId) {
      lastNonEmptyIndex = index;
    }
    if (storeName && itemId) {
      rowByKey.set(buildMainSheetKey(storeName, itemId), index + 1);
    }
  });

  return {
    rowByKey,
    nextRowNumber: Math.max(lastNonEmptyIndex + 2, 2),
  };
}

function readOperationExecutionSummaryMap(writer: FeishuSheetWriter): Map<string, string> {
  const sheetId = SHEETS[OPERATION_LOG_SHEET_NAME];
  const rowCount = writer.getRowCount({
    spreadsheetToken: currentReport.spreadsheetToken,
    sheetId,
    sheetName: OPERATION_LOG_SHEET_NAME,
  });
  const rows = writer.readValues({
    spreadsheetToken: currentReport.spreadsheetToken,
    sheetId,
    range: `A1:AZ${Math.max(rowCount, 2)}`,
  });
  const headers = (rows[0] ?? []).map((header) => normalizeText(header));
  const itemIdIndex = headers.findIndex((header) => header === "商品ID");
  const operationLogIndex = headers.findIndex((header) => header === "运营日志");
  const productIssueIndex = headers.findIndex((header) => header === "产品数据问题");
  const adAdjustmentIndex = headers.findIndex((header) => header === "广告调整意见");
  const map = new Map<string, string>();

  if (itemIdIndex < 0) {
    return map;
  }

  for (const row of rows.slice(1)) {
    const itemId = normalizeText(row[itemIdIndex]);
    if (!itemId) {
      continue;
    }
    const operationLog = operationLogIndex >= 0 ? normalizeText(row[operationLogIndex]) : "";
    const productIssue = productIssueIndex >= 0 ? normalizeText(row[productIssueIndex]) : "";
    const adAdjustment = adAdjustmentIndex >= 0 ? normalizeText(row[adAdjustmentIndex]) : "";
    if (!operationLog && !productIssue && !adAdjustment) {
      continue;
    }
    const executionScore = operationLog ? "待AI评分-有运营日志" : "待AI评分-缺少运营日志";
    map.set(
      itemId,
      `执行力评分=${executionScore}；行为问题总结=运营日志：${operationLog || "空"}；产品数据问题：${productIssue || "空"}；广告调整意见：${adAdjustment || "空"}`,
    );
  }

  return map;
}

function isRuleEnabled(rule: YuesiAiConfigRule): boolean {
  const enabled = rule.enabled.trim().toLowerCase();
  return !["false", "0", "否", "禁用"].includes(enabled);
}

function getAiScoreRules(aiRuleGroups: Map<string, YuesiAiConfigRule[]>, dimension: string): YuesiAiConfigRule[] {
  return (aiRuleGroups.get("AI测品评分") ?? []).filter(
    (rule) => isRuleEnabled(rule) && normalizeText(rule.dimension) === dimension,
  );
}

function parseWeight(value: string): number {
  const text = normalizeText(value);
  if (!text) {
    return 0;
  }
  const parsed = Number(text.replace(/,/g, "").replace("%", ""));
  return Number.isFinite(parsed) ? parsed : 0;
}

function getRuleWeight(aiRuleGroups: Map<string, YuesiAiConfigRule[]>, dimension: string, fallbackWeight: number): number {
  const rule = getAiScoreRules(aiRuleGroups, dimension)[0];
  const weight = parseWeight(rule?.weight ?? "");
  return weight > 0 ? weight : fallbackWeight;
}

function findScoreRule(rules: YuesiAiConfigRule[], score: number): YuesiAiConfigRule | undefined {
  return rules.find((rule) => {
    const minScore = toNumber(rule.minScore);
    const maxScore = toNumber(rule.maxScore);
    return score >= minScore && score <= maxScore;
  });
}

function parseManualScore(text: string): number {
  const match = text.match(/(?:^|[^\d])(\d{1,2})(?:\s*分|[^\d]|$)/);
  if (!match) {
    return 0;
  }
  const score = Number(match[1]);
  if (!Number.isFinite(score)) {
    return 0;
  }
  return Math.max(1, Math.min(10, score));
}

function weightedScore(score: number, weight: number): number {
  return Number(((score / 10) * weight).toFixed(1));
}

function buildManualScoreResult(
  dimension: string,
  scoreText: string,
  weight: number,
  aiRuleGroups: Map<string, YuesiAiConfigRule[]>,
): ScoreDimensionResult | undefined {
  const score = parseManualScore(scoreText);
  if (score === 0) {
    return undefined;
  }
  const rules = getAiScoreRules(aiRuleGroups, dimension);
  return {
    dimension,
    score,
    weight,
    weightedScore: weightedScore(score, weight),
    source: "人工",
    rule: findScoreRule(rules, score),
    note: scoreText,
  };
}

function buildOrderSpeedScoreResult(
  row: MainSheetPreviewRow,
  adMetric: AdItemMetric | undefined,
  weight: number,
  aiRuleGroups: Map<string, YuesiAiConfigRule[]>,
): ScoreDimensionResult {
  const recentOrders = adMetric?.recentAdOrders ?? 0;
  const recentClicks = adMetric?.recentClicks ?? 0;
  let score = 1;
  let note = `累计销量${row.totalSalesQty}，测品天数${row.testDays}，近3天广告订单${recentOrders}`;

  if ((row.testDays > 0 && row.testDays <= 3 && row.totalSalesQty >= 10) || recentOrders >= 5) {
    score = 9;
    note += "，出单速度接近优秀档";
  } else if ((row.testDays > 0 && row.testDays <= 5 && row.totalSalesQty >= 3) || recentOrders >= 2) {
    score = 7;
    note += "，已有多单且仍在测试窗口内";
  } else if (row.totalSalesQty > 0 || recentOrders > 0) {
    score = 5;
    note += "，已有少量订单但速度一般";
  } else if (recentClicks > 0 || row.totalSalesQty === 0) {
    score = 3;
    note += "，有曝光/点击但订单不足";
  }

  const rules = getAiScoreRules(aiRuleGroups, "出单速度");
  return {
    dimension: "出单速度",
    score,
    weight,
    weightedScore: weightedScore(score, weight),
    source: "AI",
    rule: findScoreRule(rules, score),
    note,
  };
}

function buildAdEffectivenessScoreResult(
  adMetric: AdItemMetric | undefined,
  weight: number,
  aiRuleGroups: Map<string, YuesiAiConfigRule[]>,
): ScoreDimensionResult {
  const spend = adMetric?.recentAdSpend ?? 0;
  const sales = adMetric?.recentAdSales ?? 0;
  const orders = adMetric?.recentAdOrders ?? 0;
  const clicks = adMetric?.recentClicks ?? 0;
  const impressions = adMetric?.recentImpressions ?? 0;
  const cvr = ratio(orders, clicks);
  const acos = ratio(spend, sales);
  let score = 1;
  let note = `近3天花费${money(spend)}，销售${money(sales)}，订单${orders}，曝光${impressions}，点击${clicks}，CVR${percentText2(cvr)}，ACOS${sales > 0 ? percentText2(acos) : "N/A"}`;

  if (clicks > 50 && orders === 0) {
    score = 1;
    note += "，点击较多但无转化";
  } else if (spend > 0 && sales === 0) {
    score = 1;
    note += "，有花费无销售额";
  } else if (orders > 0 && cvr >= 0.08 && acos < 0.5) {
    score = 9;
    note += "，转化和ACOS均较好";
  } else if (orders > 0 && cvr >= 0.05 && (sales === 0 || acos <= 0.7)) {
    score = 7;
    note += "，广告有订单且转化可继续观察";
  } else if (orders > 0 || clicks > 0) {
    score = 5;
    note += "，广告有互动但效率一般";
  } else if (impressions > 0) {
    score = 3;
    note += "，有曝光但缺少点击/订单";
  } else {
    note += "，广告商品报表缺少有效曝光点击";
  }

  const rules = getAiScoreRules(aiRuleGroups, "广告有效性");
  return {
    dimension: "广告有效性",
    score,
    weight,
    weightedScore: weightedScore(score, weight),
    source: "AI",
    rule: findScoreRule(rules, score),
    note,
  };
}

function resolveScoreGrade(totalScore: number, aiRuleGroups: Map<string, YuesiAiConfigRule[]>): string {
  const ratingRules = (aiRuleGroups.get("评级规则") ?? []).filter(isRuleEnabled);
  const matched = ratingRules.find((rule) => {
    const standard = `${rule.dimension} ${rule.standard} ${rule.description}`;
    if (/最终得分\s*≥\s*85|>=\s*85/.test(standard)) return totalScore >= 85;
    if (/70\s*≤\s*最终得分\s*<\s*85|70.*85/.test(standard)) return totalScore >= 70 && totalScore < 85;
    if (/55\s*≤\s*最终得分\s*<\s*70|55.*70/.test(standard)) return totalScore >= 55 && totalScore < 70;
    if (/40\s*≤\s*最终得分\s*<\s*55|40.*55/.test(standard)) return totalScore >= 40 && totalScore < 55;
    if (/最终得分\s*<\s*40|<\s*40/.test(standard)) return totalScore < 40;
    return false;
  });
  if (matched) {
    return [matched.standard, matched.triggerResult, matched.description].filter(Boolean).join("，");
  }
  if (totalScore >= 85) return "A级，可继续测试或小幅放量";
  if (totalScore >= 70) return "B级，继续测试，重点优化广告和Listing";
  if (totalScore >= 55) return "C级，谨慎观察，不建议大货放量";
  if (totalScore >= 40) return "D级，建议暂停或只保留低成本观察";
  return "Pass，建议淘汰";
}

function formatScoreResult(result: ScoreDimensionResult): string {
  const ruleText = result.rule?.standard ? `，命中=${result.rule.standard}` : "";
  return `${result.dimension}${result.score}分/${result.weight}权重=${result.weightedScore}分(${result.source}${ruleText})`;
}

/**
 * 【AI分析字段备注】
 * 字段名    : 测品结果AI分析
 * 写入位置  : sheet=<REDACTED_FEISHU_SHEET_ID>（悦斯测品汇总）M列
 * 分析维度  : 出单速度 + 广告有效性，各自输出独立得分（10分制），不算总分不评级
 * 规则来源  : sheet=<REDACTED_FEISHU_SHEET_ID>（悦斯AI诊断配置）规则类型=AI测品评分
 *             - 出单速度：看累计销量/测品天数/近3天广告订单数，对照 <REDACTED_FEISHU_SHEET_ID> 出单速度评分标准
 *             - 广告有效性：看近3天 CVR/ACOS/点击/花费，对照 <REDACTED_FEISHU_SHEET_ID> 广告有效性评分标准
 * 输出格式  : "出单速度=X/10（说明）；广告有效性=X/10（说明）"
 * 注意      : 市场竞争/利润空间/风险与供应链三个维度由人工在 Q/R/S 黄色列填写，不参与此字段
 */
function buildAiTestScoreSummary(
  row: MainSheetPreviewRow,
  adMetric: AdItemMetric | undefined,
  aiRuleGroups: Map<string, YuesiAiConfigRule[]>,
): string {
  const scoreRuleCount = aiRuleGroups.get("AI测品评分")?.length ?? 0;
  if (scoreRuleCount === 0) {
    throw new Error(`${YUESI_AI_CONFIG_SHEET_NAME} 缺少 AI测品评分 规则，禁止生成测品评分说明`);
  }

  // 只评估出单速度和广告有效性，各自输出独立得分（10分制），不算总分不评级
  const orderSpeedResult = buildOrderSpeedScoreResult(row, adMetric, 0, aiRuleGroups);
  const adEffectivenessResult = buildAdEffectivenessScoreResult(adMetric, 0, aiRuleGroups);

  return (
    `出单速度=${orderSpeedResult.score}/10（${orderSpeedResult.note}）；` +
    `广告有效性=${adEffectivenessResult.score}/10（${adEffectivenessResult.note}）`
  );
}

/**
 * 【AI分析字段备注】
 * 字段名    : 运营日志执行情况AI分析
 * 写入位置  : sheet=<REDACTED_FEISHU_SHEET_ID>（悦斯测品汇总）L列
 * 分析逻辑  : 读取 sheet=<REDACTED_FEISHU_SHEET_ID>（悦斯测品运营日志）同一 ItemID 最近一条运营日志（Q列），
 *             结合该条日志对应的 产品数据问题（O列）、广告调整意见（P列），
 *             对运营动作的执行质量做简要评价；
 *             如无运营日志记录则输出占位文本（含近3天广告概要数据）
 * 规则来源  : 无独立 <REDACTED_FEISHU_SHEET_ID> 规则，逻辑由代码生成，依赖 <REDACTED_FEISHU_SHEET_ID> 的实际填写内容
 * 输出格式  : "执行力评分=XXX；行为问题总结=XXX"（有日志）
 *             或 "执行力评分=待AI评分-无运营日志记录；..." （无日志）
 */
function buildMainUpdateRow(
  row: MainSheetPreviewRow,
  adMetric: AdItemMetric | undefined,
  operationExecutionSummary: string,
  aiRuleGroups: Map<string, YuesiAiConfigRule[]>,
): SheetRow {
  const recentSpend = money(adMetric?.recentAdSpend ?? 0);
  const recentSales = money(adMetric?.recentAdSales ?? 0);
  const recentOrders = adMetric?.recentAdOrders ?? 0;
  const operationAiSummary =
    operationExecutionSummary ||
    `执行力评分=待AI评分-无运营日志记录；行为问题总结=近3天广告花费${recentSpend}，广告销售额${recentSales}，广告订单${recentOrders}，未读取到运营日志/产品数据问题/广告调整意见。`;
  const testResultAiSummary = buildAiTestScoreSummary(row, adMetric, aiRuleGroups);

  // 返回 9 列：E(首次广告日期)~M(测品结果AI分析)，已删除"在售判断"(原L列)
  return [
    adMetric?.firstAdDate || row.firstAdDate,
    row.testDays,
    row.totalSalesQty,
    money(row.totalSalesAmount),
    money(row.totalAdCost),
    row.adRatio,
    row.nonWfsInventory,
    operationAiSummary,
    testResultAiSummary,
  ];
}

function buildMainInsertRow(
  row: MainSheetPreviewRow,
  adMetric: AdItemMetric | undefined,
  operationExecutionSummary: string,
  aiRuleGroups: Map<string, YuesiAiConfigRule[]>,
): SheetRow {
  return [
    row.storeName,
    row.itemId,
    row.msku,
    row.owner,
    ...buildMainUpdateRow(row, adMetric, operationExecutionSummary, aiRuleGroups),
  ];
}

function keywordLabel(record: KeywordAdRecord): string {
  if (record.keyword) {
    return record.keyword;
  }
  const source = [record.campaignName, record.adGroupName, record.matchType].filter(Boolean).join("/");
  return source ? `接口未返回关键词文本(${source})` : "接口未返回关键词文本";
}

function isAutoAd(record: KeywordAdRecord): boolean {
  const text = `${record.campaignType} ${record.campaignName} ${record.adGroupName}`.toLowerCase();
  return text.includes("auto") || text.includes("自动");
}

function formatKeywordMetric(record: KeywordAdRecord): string {
  return `${keywordLabel(record)} 花费${money(record.adSpend)} 销售${money(record.attributedSales)} 订单${record.attributedOrders} ACOS${percentText(record.acos)}`;
}

function keywordLocator(record: KeywordAdRecord): string {
  return (
    `广告组=${record.adGroupName || "接口未返回"}` +
    `，关键词=${keywordLabel(record)}` +
    `，匹配类型=${record.matchType || "接口未返回"}`
  );
}

function joinTop(records: KeywordAdRecord[], emptyText: string, limit = 3): string {
  if (records.length === 0) {
    return emptyText;
  }
  return records.slice(0, limit).map(formatKeywordMetric).join("；");
}

function summarizeAdGroup(records: KeywordAdRecord[], label: string): string {
  const spend = money(records.reduce((sum, record) => sum + record.adSpend, 0));
  const sales = money(records.reduce((sum, record) => sum + record.attributedSales, 0));
  const orders = records.reduce((sum, record) => sum + record.attributedOrders, 0);
  const impressions = records.reduce((sum, record) => sum + record.impressions, 0);
  const clicks = records.reduce((sum, record) => sum + record.clicks, 0);
  const acos = percentText(ratio(spend, sales));
  if (records.length === 0) {
    return `${label}近3天无关键词记录。`;
  }
  return `${label}近3天花费${spend}，销售额${sales}，订单${orders}，曝光${impressions}，点击${clicks}，ACOS${acos}。`;
}

function summarizeAdChannel(records: KeywordAdRecord[], label: string): string {
  const summary = summarizeAdGroup(records, label);
  if (records.length === 0) {
    return summary;
  }
  const effective = records
    .filter((record) => record.attributedOrders > 0 || record.attributedSales > 0)
    .sort((a, b) => b.attributedSales - a.attributedSales || b.attributedOrders - a.attributedOrders);
  const invalid = records
    .filter((record) => (record.clicks >= 20 || record.adSpend >= 5) && record.attributedOrders === 0)
    .sort((a, b) => b.adSpend - a.adSpend || b.clicks - a.clicks);
  const lowExposure = records
    .filter((record) => record.impressions < 50 && record.clicks === 0 && record.adSpend === 0)
    .sort((a, b) => a.impressions - b.impressions);
  return (
    `${summary}` +
    ` 有效关键词/搜索词：${joinTop(effective, "近3天未发现有订单或有销售额的有效词", 3)}。` +
    ` 无效关键词/搜索词：${
      [...invalid, ...lowExposure].slice(0, 3).map(formatKeywordMetric).join("；") ||
      "近3天未发现明显无效词"
    }。`
  );
}

function summarizeRecordMetrics(records: KeywordAdRecord[]): {
  spend: number;
  sales: number;
  orders: number;
  impressions: number;
  clicks: number;
  cvr: number;
  acos: number;
} {
  const spend = records.reduce((sum, record) => sum + record.adSpend, 0);
  const sales = records.reduce((sum, record) => sum + record.attributedSales, 0);
  const orders = records.reduce((sum, record) => sum + record.attributedOrders, 0);
  const impressions = records.reduce((sum, record) => sum + record.impressions, 0);
  const clicks = records.reduce((sum, record) => sum + record.clicks, 0);
  return {
    spend,
    sales,
    orders,
    impressions,
    clicks,
    cvr: ratio(orders, clicks),
    acos: ratio(spend, sales),
  };
}

function describeWarningRule(rule: YuesiAiConfigRule | undefined, fallback: string): string {
  if (!rule) {
    return fallback;
  }
  return [rule.dimension, rule.standard, rule.triggerResult, rule.description].filter(Boolean).join("，");
}

function findWarningRule(rules: YuesiAiConfigRule[], patterns: RegExp[]): YuesiAiConfigRule | undefined {
  return rules.find((rule) => {
    const text = `${rule.dimension} ${rule.standard} ${rule.triggerResult} ${rule.description}`;
    return patterns.every((pattern) => pattern.test(text));
  });
}

/**
 * 【AI分析字段备注】
 * 字段名    : 测品预警
 * 写入位置  : sheet=<REDACTED_FEISHU_SHEET_ID>（悦斯测品运营日志）S列
 * 分析维度  : 基于近3天关键词广告数据，逐条命中以下预警规则后输出
 * 规则来源  : sheet=<REDACTED_FEISHU_SHEET_ID>（悦斯AI诊断配置）规则类型=测品预警
 *   - 广告点击无转化   : 单个 ItemID 近3天总点击 > 50 且广告订单数 = 0
 *   - 小额花费无成交   : 近3天广告花费 > $10 且广告订单数 = 0
 *   - 高广告占比低转化 : 广告销售额 > 0 且 ACOS > 80% 且整体 CVR < 3%
 *   - 手动词低效自动词有效: 手动广告 CVR < 3% 且自动广告 CVR > 5%
 *   - 自动广告有效     : 自动广告有成交且 CVR ≥ 5%（提示提取词转手动）
 *   - Exact有效        : Exact匹配有订单且 ACOS < 50%（提示可放量）
 * 输出格式  : 命中的预警规则描述拼接（最多4条）；无命中时输出数据概要
 * 注意      : 低动销预警（测品天数≥20天且销量≤5）在主表维度判断，此处只做广告维度预警
 */
function buildTestWarning(records: KeywordAdRecord[], aiRuleGroups: Map<string, YuesiAiConfigRule[]>): string {
  const warningRules = (aiRuleGroups.get("测品预警") ?? []).filter(isRuleEnabled);
  if (warningRules.length === 0) {
    throw new Error(`${YUESI_AI_CONFIG_SHEET_NAME} 缺少 测品预警 规则，禁止生成测品预警`);
  }
  if (records.length === 0) {
    return "测品预警=暂无法判断；原因=未匹配到手动关键词或自动广告搜索词数据。";
  }

  const autoRecords = records.filter(isAutoAd);
  const manualRecords = records.filter((record) => !isAutoAd(record));
  const allMetric = summarizeRecordMetrics(records);
  const autoMetric = summarizeRecordMetrics(autoRecords);
  const manualMetric = summarizeRecordMetrics(manualRecords);
  const exactWinners = records.filter(
    (record) => /exact|精准/i.test(record.matchType) && record.attributedOrders > 0 && record.acos < 0.5,
  );
  const warnings: string[] = [];

  if (allMetric.clicks > 50 && allMetric.orders === 0) {
    warnings.push(
      describeWarningRule(
        findWarningRule(warningRules, [/点击|click/i, /订单|转化|无成交|无转化/i]),
        "广告点击无转化：近3天点击>50且广告订单=0，建议暂停测品或检查Listing转化问题",
      ),
    );
  }
  if (allMetric.spend > 10 && allMetric.orders === 0) {
    warnings.push(
      describeWarningRule(
        findWarningRule(warningRules, [/花费|消耗/i, /无成交|无订单|订单数\s*=\s*0/i]),
        "小额花费无成交：近3天广告花费>10且广告订单=0，需要检查搜索词、价格、图片和Listing",
      ),
    );
  }
  if (allMetric.sales > 0 && allMetric.acos > 0.8 && allMetric.cvr < 0.03) {
    warnings.push(
      describeWarningRule(
        findWarningRule(warningRules, [/广告占比|ACOS|依赖/i, /CVR|转化/i]),
        "高广告占比低转化：广告依赖过高且CVR<3%，继续投放风险较高",
      ),
    );
  }
  if (manualRecords.length > 0 && autoRecords.length > 0 && manualMetric.cvr < 0.03 && autoMetric.cvr > 0.05) {
    warnings.push(
      describeWarningRule(
        findWarningRule(warningRules, [/手动/i, /自动/i]),
        "手动词低效自动词有效：手动广告CVR<3%，自动广告CVR>5%，需要从自动广告重新筛有效词",
      ),
    );
  }
  if (autoMetric.orders > 0 && autoMetric.cvr >= 0.05) {
    warnings.push(
      describeWarningRule(
        findWarningRule(warningRules, [/自动/i, /CVR|成交|转化/i]),
        "自动广告有效：自动广告有成交且CVR≥5%，建议提取搜索词转手动Exact/Phrase",
      ),
    );
  }
  if (exactWinners.length > 0) {
    warnings.push(
      describeWarningRule(
        findWarningRule(warningRules, [/Exact|精准/i, /ACOS|成交/i]),
        `Exact有效：${joinTop(exactWinners, "无", 2)}，可放量观察`,
      ),
    );
  }

  if (warnings.length === 0) {
    return `测品预警=未触发；近3天点击${allMetric.clicks}，订单${allMetric.orders}，花费${money(allMetric.spend)}，CVR${percentText2(allMetric.cvr)}，ACOS${allMetric.sales > 0 ? percentText2(allMetric.acos) : "N/A"}。`;
  }
  return Array.from(new Set(warnings)).slice(0, 4).join("；");
}

/**
 * 读取 <REDACTED_FEISHU_SHEET_ID> 某规则类型的标准/描述文本，用于在诊断结果中标注参考依据。
 */
function getWdxAydRuleRef(aiRuleGroups: Map<string, YuesiAiConfigRule[]>, ruleType: string): string {
  const rules = (aiRuleGroups.get(ruleType) ?? []).filter(isRuleEnabled);
  if (rules.length === 0) return "";
  return rules
    .slice(0, 3)
    .map((rule) => [rule.dimension, rule.standard, rule.description].filter(Boolean).join("："))
    .join("；");
}

/**
 * 解析 <REDACTED_FEISHU_SHEET_ID> 规则中的数值阈值（如 "30%" → 0.3，"1.5" → 1.5）。
 */
function parseRuleThreshold(rules: YuesiAiConfigRule[], fallback: number): number {
  for (const rule of rules) {
    const text = (rule.standard || "").replace(/[^0-9.]/g, "");
    const value = Number(text);
    if (Number.isFinite(value) && value > 0) {
      // 若原文包含 % 则除以 100
      return (rule.standard || "").includes("%") ? value / 100 : value;
    }
  }
  return fallback;
}

/**
 * 【AI分析字段备注】
 * 字段名    : 产品数据问题（O列）+ 广告调整意见（P列）
 * 写入位置  : sheet=<REDACTED_FEISHU_SHEET_ID>（悦斯测品运营日志）
 * 分析维度  : 同时读取4类规则，两列均基于这4类规则进行诊断和建议
 *
 * 产品数据问题（O列）—— 诊断当前哪里有问题：
 *   - 广告ACOS标准  : 检测 ACOS>50% 的关键词，标注超标词和规则依据
 *   - CPC标准       : 检测 CPC>$1 且点击>5 的关键词，标注高CPC词
 *   - 自动广告分析规则: 检测自动广告点击>30无订单、高花费无成交、曝光>100无点击
 *   - 手动广告分析规则: 检测手动广告高花费无订单词
 *
 * 广告调整意见（P列）—— 基于问题给出可执行操作建议：
 *   - 广告ACOS标准  : 高ACOS词 → 降低竞价或暂停
 *   - CPC标准       : 高CPC词 → 降低竞价
 *   - 自动广告分析规则: 有效→提取词转手动Exact/Phrase；高花费无成交→降预算或否词；无问题→继续观察
 *   - 手动广告分析规则: 无效词→否定/降价；Exact有效词→小幅加价；无问题→维持观察
 *
 * 规则来源  : sheet=<REDACTED_FEISHU_SHEET_ID>（悦斯AI诊断配置）
 *             规则类型=广告ACOS标准、CPC标准、自动广告分析规则、手动广告分析规则
 * 数据来源  : 近3天关键词广告数据（SP关键词报表，按 ItemID 匹配）
 * ACOS阈值  : 固定 50%（代码常量）
 * CPC阈值   : 固定 $1.0（代码常量）
 */
function buildProductIssueAndAdjustment(
  records: KeywordAdRecord[],
  analysisWindow: AnalysisWindow,
  aiRuleGroups: Map<string, YuesiAiConfigRule[]>,
): [string, string] {
  // 从 <REDACTED_FEISHU_SHEET_ID> 读取全部4类规则
  const acosRules = (aiRuleGroups.get("广告ACOS标准") ?? []).filter(isRuleEnabled);
  const cpcRules = (aiRuleGroups.get("CPC标准") ?? []).filter(isRuleEnabled);
  const autoAdRules = (aiRuleGroups.get("自动广告分析规则") ?? []).filter(isRuleEnabled);
  const manualAdRules = (aiRuleGroups.get("手动广告分析规则") ?? []).filter(isRuleEnabled);

  // 规则参考文本（用于标注来源）
  const acosRef = getWdxAydRuleRef(aiRuleGroups, "广告ACOS标准");
  const cpcRef = getWdxAydRuleRef(aiRuleGroups, "CPC标准");
  const autoRuleRef = autoAdRules.slice(0, 2).map((r) => r.description || r.standard).filter(Boolean).join("；");
  const manualRuleRef = manualAdRules.slice(0, 2).map((r) => r.description || r.standard).filter(Boolean).join("；");

  // ACOS 阈值（取50%作为基准，CPC阈值取1.0）
  const acosThreshold = 0.5;
  const cpcThreshold = 1.0;

  if (records.length === 0) {
    return [
      `分析窗口=${analysisWindow.text}；关键词广告数据缺失，无法定位具体问题`,
      "先核对广告报表ItemID映射，确认有关键词数据后再做否词、竞价和预算调整",
    ];
  }

  const autoRecords = records.filter(isAutoAd);
  const manualRecords = records.filter((record) => !isAutoAd(record));
  const autoMetric = summarizeRecordMetrics(autoRecords);
  const manualMetric = summarizeRecordMetrics(manualRecords);

  // 关键词级问题识别（4类规则阈值）
  const invalid = records
    .filter((record) => (record.clicks >= 20 || record.adSpend >= 5) && record.attributedOrders === 0)
    .sort((a, b) => b.adSpend - a.adSpend || b.clicks - a.clicks);
  const highAcos = records
    .filter((record) => record.attributedSales > 0 && record.acos > acosThreshold)
    .sort((a, b) => b.acos - a.acos);
  const highCpc = records
    .filter((record) => record.cpc > cpcThreshold && record.clicks > 5)
    .sort((a, b) => b.cpc - a.cpc);
  const exactWinners = records.filter(
    (record) => /exact|精准/i.test(record.matchType) && record.attributedOrders > 0 && record.acos <= acosThreshold,
  );
  const invalidManual = invalid.filter((record) => !isAutoAd(record));

  // ---------- 产品数据问题：只陈述事实，不给建议 ----------
  const issueLines: string[] = [];

  // 广告ACOS标准 → 陈述哪些词超标、超标多少
  if (highAcos.length > 0) {
    issueLines.push(`ACOS超标(阈值${Math.round(acosThreshold * 100)}%)共${highAcos.length}条，最高：${joinTop(highAcos, "无", 2)}`);
  }
  // CPC标准 → 陈述哪些词CPC过高
  if (highCpc.length > 0) {
    issueLines.push(`CPC过高(阈值$${cpcThreshold})共${highCpc.length}条，最高：${joinTop(highCpc, "无", 2)}`);
  }
  // 自动广告分析规则 → 陈述自动广告表现异常
  if (autoRecords.length > 0) {
    if (autoMetric.clicks > 30 && autoMetric.orders === 0) {
      issueLines.push(`自动广告近3天点击${autoMetric.clicks}次，无订单转化`);
    } else if (autoMetric.spend > 5 && autoMetric.orders === 0) {
      issueLines.push(`自动广告近3天花费$${money(autoMetric.spend)}，无成交`);
    } else if (autoMetric.impressions > 100 && autoMetric.clicks === 0) {
      issueLines.push(`自动广告近3天曝光${autoMetric.impressions}次，无点击`);
    }
  }
  // 手动广告分析规则 → 陈述手动广告无效词
  if (invalidManual.length > 0) {
    issueLines.push(`手动广告高花费无订单词${invalidManual.length}条：${joinTop(invalidManual, "无", 2)}`);
  } else if (invalid.length > 0) {
    issueLines.push(`高花费/高点击无订单词${invalid.length}条：${joinTop(invalid, "无", 2)}`);
  }

  const productIssue =
    issueLines.length > 0
      ? issueLines.join("；")
      : "近3天广告指标正常，无明显超标问题";

  // ---------- 广告调整意见：只给可执行操作，不重复诊断数据 ----------
  const adjustParts: string[] = [];

  // 针对ACOS超标词 → 操作：降价/暂停
  if (highAcos.length > 0) {
    adjustParts.push(`高ACOS词(${joinTop(highAcos, "无", 1)})降低竞价或暂停`);
  }
  // 针对高CPC词 → 操作：降竞价
  if (highCpc.length > 0) {
    adjustParts.push(`高CPC词(${joinTop(highCpc, "无", 1)})降低竞价`);
  }
  // 针对自动广告 → 操作：提取词/降预算/否词
  if (autoRecords.length > 0) {
    if (autoMetric.orders > 0 && autoMetric.acos <= acosThreshold) {
      adjustParts.push(`自动广告有效，提取搜索词转手动Exact/Phrase`);
    } else if (autoMetric.spend > 5 && autoMetric.orders === 0) {
      adjustParts.push(`自动广告降低日预算，批量否定无关词`);
    } else if (autoMetric.clicks > 30 && autoMetric.orders === 0) {
      adjustParts.push(`自动广告暂停或降低出价，等待复盘关键词列表`);
    }
  }
  // 针对手动广告 → 操作：否定无效词/加价有效词
  if (manualRecords.length > 0) {
    if (invalidManual.length > 0) {
      adjustParts.push(`手动广告否定或降价无效词：${joinTop(invalidManual, "无", 2)}`);
    } else if (exactWinners.length > 0) {
      adjustParts.push(`Exact有效词小幅加价：${joinTop(exactWinners, "无", 2)}`);
    }
  }

  const adjustment =
    adjustParts.join("；") || "近3天广告无明显问题，维持当前设置继续观察";

  return [productIssue, adjustment];
}

function buildOperationLogMetricInput(adMetric: AdItemMetric | undefined, itemId: string): OperationLogMetricInput {
  if (!hasOperationLogAdMetricData(adMetric)) {
    throw new Error(`商品ID=${itemId} 缺少广告商品API记录，禁止用0作为fallback写入<REDACTED_FEISHU_SHEET_ID>广告指标`);
  }
  return {
    adSpend: money(adMetric.recentAdSpend),
    adSales: money(adMetric.recentAdSales),
    adOrders: adMetric.recentAdOrders,
    impressions: adMetric.recentImpressions,
    clicks: adMetric.recentClicks,
  };
}

function hasOperationLogAdMetricData(adMetric: AdItemMetric | undefined): adMetric is AdItemMetric {
  return Boolean(adMetric && adMetric.recentAdRecordCount > 0);
}

function assertAdApiDataReady(adResult: AdItemFetchResult, keywordResult: KeywordAdFetchResult): void {
  if (adResult.fetchedCount === 0 || adResult.metricMap.size === 0) {
    throw new Error("广告商品报表未返回有效数据，禁止进入写入链路，避免fallback 0");
  }
  if (keywordResult.fetchedCount === 0) {
    throw new Error("关键词报表未返回有效数据，禁止进入写入链路，避免fallback prompt/空关键词分析");
  }
}

function buildOperationLogAdMetricCells(adMetric: AdItemMetric | undefined, itemId: string): SheetRow {
  const metricInput = buildOperationLogMetricInput(adMetric, itemId);
  const spend = money(metricInput.adSpend);
  const sales = money(metricInput.adSales);
  const orders = metricInput.adOrders;
  const impressions = metricInput.impressions;
  const clicks = metricInput.clicks;
  return [
    spend,
    sales,
    orders,
    impressions,
    clicks,
    percentText2(ratio(clicks, impressions)),
    money(ratio(spend, clicks)),
    percentText2(ratio(orders, clicks)),
    percentText2(ratio(spend, sales)),
  ];
}

function buildOperationLogRow(options: {
  row: MainSheetPreviewRow;
  adMetric: AdItemMetric | undefined;
  analysisDate: string;
  analysisWindow: AnalysisWindow;
  keywordAds: KeywordAdRecord[];
  aiRuleGroups: Map<string, YuesiAiConfigRule[]>;
}): SheetRow {
  if (!options.analysisDate || !options.analysisWindow.startDate || !options.analysisWindow.endDate) {
    throw new Error("analysisDate 或 analysisWindow 缺失，禁止写入悦斯测品运营日志");
  }
  const adMetricCells = buildOperationLogAdMetricCells(options.adMetric, options.row.itemId);
  // 产品数据问题 + 广告调整意见，读取 <REDACTED_FEISHU_SHEET_ID>（悦斯AI诊断配置）规则
  const [productIssue, adjustment] = buildProductIssueAndAdjustment(
    options.keywordAds,
    options.analysisWindow,
    options.aiRuleGroups,
  );
  const warning = buildTestWarning(options.keywordAds, options.aiRuleGroups);

  // 返回 19 列 A~S（已删除"在售判断"/自动广告表现总结/手动广告表现总结/本轮AI结论）
  return [
    options.analysisDate,      // A 分析日期
    options.row.itemId,        // B 商品ID
    options.row.msku,          // C MSKU
    options.row.owner,         // D 负责人
    options.row.nonWfsInventory, // E 非WFS库存
    ...adMetricCells,          // F~N 近3天广告指标（9列）
    productIssue,              // O 产品数据问题
    adjustment,                // P 广告调整意见
    "",                        // Q 运营日志
    "",                        // R 备注
    warning,                   // S 测品预警
  ];
}

async function runLimitedConfirmWrite(options: {
  writer: FeishuSheetWriter;
  client: LingxingClient;
  analysisDate: string;
  limit: number;
  itemId: string;
  repairAdMetrics: boolean;
  overwriteExistingLog: boolean;
  dryRun: boolean;
  confirmWrite: boolean;
}): Promise<SafeWriteResult> {
  if (!options.confirmWrite || options.dryRun) {
    throw new Error("没有 --confirm-write 时禁止写入飞书");
  }

  const mainSheetId = getActiveTargetSheetId();
  const operationLogSheetId = SHEETS[OPERATION_LOG_SHEET_NAME];
  if (!mainSheetId) {
    throw new Error(`缺少配置：${TARGET_SHEET_NAME}`);
  }
  if (!operationLogSheetId) {
    throw new Error(`缺少配置：${OPERATION_LOG_SHEET_NAME}`);
  }

  const recentStartDate = getRecentAdStartDate(options.analysisDate);
  const analysisWindow = resolveAnalysisWindow(options.analysisDate);
  const adHistoryStartDate = getAdHistoryStartDate();
  const adResult = await fetchAdItemMetrics(
    options.client,
    adHistoryStartDate,
    options.analysisDate,
    recentStartDate,
    options.analysisDate,
  );
  const keywordResult = await fetchKeywordAdRecords(options.client, recentStartDate, options.analysisDate);
  assertAdApiDataReady(adResult, keywordResult);
  const mainInfo = findMainSheetExistingInfo(options.writer);
  const operationExecutionSummaryMap = readOperationExecutionSummaryMap(options.writer);
  const aiRuleGroups = readYuesiAiConfigGrouped(options.writer);
  // aiPromptConfig（<REDACTED_FEISHU_SHEET_ID>）已不再用于 <REDACTED_FEISHU_SHEET_ID> 诊断，<REDACTED_FEISHU_SHEET_ID> 规则直接由 aiRuleGroups 提供
  const autoAdSearchTermResult = readAutoAdSearchTermMap(options.writer, analysisWindow);
  // 检查1HeaCn是否有对应日期数据，缺失时发飞书群通知 @江梓博，本次跳过搜索词分析
  if (autoAdSearchTermResult.sheetConfigured && autoAdSearchTermResult.fetchedCount > 0 && autoAdSearchTermResult.matchedCount === 0) {
    const alertMsg =
      `⚠️ 悦斯自动广告搜索词聚合分析（sheet=1HeaCn）缺少 ${options.analysisDate} 的数据\n` +
      `本次跳过自动广告搜索词分析，请及时补传。\n` +
      `<at user_id="${JIANGZIBO_OPEN_ID}">江梓博</at>`;
    console.log(`[警告] 1HeaCn 无 ${options.analysisDate} 数据，已跳过搜索词分析并发送群通知`);
    await sendYuesiAlertMessage(alertMsg);
  }
  const firstAdActivityDateMap = buildFirstAdActivityDateMap(options.writer);
  let mainCandidates = readMainSheetPreviewRows(options.writer);
  let candidateSource = TARGET_SHEET_NAME;
  if (mainCandidates.length < options.limit) {
    console.log(
      `${TARGET_SHEET_NAME} 符合条件的候选数 ${mainCandidates.length} 小于 limit ${options.limit}，改从 ${SOURCE_SHEET_NAME} 补齐候选。`,
    );
    const listingMap = await fetchListingStatusMap(options.client);
    mainCandidates = buildFallbackPreviewRowsFromSource(options.writer, listingMap, adResult.metricMap);
    candidateSource = SOURCE_SHEET_NAME;
  }
  mainCandidates = mainCandidates.filter((row) => {
    return !options.itemId || row.itemId === options.itemId;
  });
  mainCandidates = mainCandidates.map((row) => {
    const firstAdDate =
      adResult.metricMap.get(row.itemId)?.firstAdDate ||
      row.firstAdDate ||
      firstAdActivityDateMap.get(row.itemId) ||
      "";
    return {
      ...row,
      firstAdDate,
      testDays: calculateTestDays(firstAdDate, "", getTodayInChina()),
    };
  });
  const logInfo = findLogSheetExistingInfo(options.writer);
  const selectedRows = mainCandidates.slice(0, options.limit);
  const mainUpdatedItemIds: string[] = [];
  const mainInsertedItemIds: string[] = [];
  const logInsertedItemIds: string[] = [];
  const logOverwrittenItemIds: string[] = [];
  const logAdMetricRepairedItemIds: string[] = [];
  let duplicateLogSkippedCount = 0;
  let skippedNoAdMetricCount = 0;
  let nextLogRowNumber = logInfo.nextRowNumber;
  let nextMainRowNumber = mainInfo.nextRowNumber;

  console.log("");
  console.log("悦斯测品小范围 confirm-write:");
  console.log(`分析日期: ${options.analysisDate}`);
  console.log(`limit: ${options.limit}`);
  console.log(`指定商品ID: ${options.itemId || "未指定"}`);
  console.log(`广告指标修复模式: ${options.repairAdMetrics ? "启用，仅更新已存在日志G:O" : "未启用，重复日志跳过"}`);
  console.log(
    `已有日志覆盖模式: ${options.overwriteExistingLog ? "启用，仅覆盖A:V自动字段，不覆盖运营日志/备注" : "未启用"}`,
  );
  console.log(`候选来源: ${candidateSource}`);
  console.log(`候选商品数: ${mainCandidates.length}`);
  console.log("写入节奏: 每个ITEMID分析完成后立即写回主表和日志表");
  console.log(
    `可写入首次广告日期商品数: ${mainCandidates.filter((row) => Boolean(row.firstAdDate)).length}`,
  );
  console.log(`首次广告日期查询范围: ${adHistoryStartDate}~${options.analysisDate}`);
  console.log("首次广告日期来源: 广告商品报表优先，销售明细首次广告花费日期兜底");
  console.log(`近3天广告范围: ${recentStartDate}~${options.analysisDate}`);
  console.log(`广告记录数: ${adResult.fetchedCount}`);
  console.log(`关键词广告记录数: ${keywordResult.fetchedCount}`);
  console.log(
    `${AUTO_AD_SEARCH_TERM_SHEET_NAME}可匹配商品数: ${autoAdSearchTermResult.map.size}（配置=${autoAdSearchTermResult.sheetConfigured ? "是" : "否"}）`,
  );
  console.log(`AI测品评分规则数: ${aiRuleGroups.get("AI测品评分")?.length ?? 0}`);
  console.log(`测品预警规则数: ${aiRuleGroups.get("测品预警")?.length ?? 0}`);
  console.log(`<REDACTED_FEISHU_SHEET_ID> 广告ACOS标准规则数: ${aiRuleGroups.get("广告ACOS标准")?.length ?? 0}`);
  if (keywordResult.errorMessages.length > 0) {
    console.log(`关键词广告报表非阻塞错误: ${keywordResult.errorMessages.join("；")}`);
  }

  for (const row of selectedRows) {
    const adMetric = adResult.metricMap.get(row.itemId);
    const manualKeywordAds = getKeywordAdsForRow(keywordResult, row).filter((record) => !isAutoAd(record));
    const autoSearchTermAds = autoAdSearchTermResult.map.get(row.itemId) ?? [];
    const keywordAds = [...manualKeywordAds, ...autoSearchTermAds].slice(0, 60);
    const operationExecutionSummary = operationExecutionSummaryMap.get(row.itemId) || "";
    const mainKey = buildMainSheetKey(row.storeName, row.itemId);
    const existingMainRowNumber = row.rowNumber > 0 ? row.rowNumber : mainInfo.rowByKey.get(mainKey);
    if (existingMainRowNumber) {
      // 主表更新范围 E:M（9列，已删除原L列"在售判断"）
      const mainUpdateRange = `E${existingMainRowNumber}:M${existingMainRowNumber}`;
      writeYuesiCells(options.writer, {
        spreadsheetToken: currentReport.spreadsheetToken,
        sheetId: mainSheetId,
        sheetName: activeTargetSheetName,
        range: mainUpdateRange,
        rows: [buildMainUpdateRow(row, adMetric, operationExecutionSummary, aiRuleGroups)],
        dryRun: false,
        confirmWrite: true,
        allowOverwrite: true,
      });
      mainUpdatedItemIds.push(row.itemId);
    } else {
      // 主表插入范围 A:M（13列，已删除原L列"在售判断"）
      const mainInsertRange = `A${nextMainRowNumber}:M${nextMainRowNumber}`;
      writeYuesiCells(options.writer, {
        spreadsheetToken: currentReport.spreadsheetToken,
        sheetId: mainSheetId,
        sheetName: activeTargetSheetName,
        range: mainInsertRange,
        rows: [buildMainInsertRow(row, adMetric, operationExecutionSummary, aiRuleGroups)],
        dryRun: false,
        confirmWrite: true,
        allowOverwrite: false,
      });
      mainInfo.rowByKey.set(mainKey, nextMainRowNumber);
      mainInsertedItemIds.push(row.itemId);
      nextMainRowNumber += 1;
    }

    const logKey = `${options.analysisDate}::${row.itemId}`;
    if (!hasOperationLogAdMetricData(adMetric)) {
      skippedNoAdMetricCount += 1;
      console.log(`跳过日志写入: 商品ID=${row.itemId} 缺少广告商品API记录，禁止fallback 0`);
      continue;
    }
    const operationLogRow = buildOperationLogRow({
      row,
      adMetric,
      analysisDate: options.analysisDate,
      analysisWindow,
      keywordAds,
      aiRuleGroups,
    });
    if (logInfo.existingKeys.has(logKey)) {
      if (options.overwriteExistingLog) {
        const existingLogRowNumber = logInfo.rowByKey.get(logKey);
        if (!existingLogRowNumber) {
          throw new Error(`无法定位已有日志行: ${logKey}`);
        }
        const autoLogCells = operationLogRow.slice(0, OPERATION_LOG_HEADERS.indexOf("运营日志"));
        const warningCell = operationLogRow[OPERATION_LOG_HEADERS.indexOf("测品预警")];
        const warningColumn = columnName(OPERATION_LOG_HEADERS.indexOf("测品预警") + 1);
        writeYuesiCells(options.writer, {
          spreadsheetToken: currentReport.spreadsheetToken,
          sheetId: operationLogSheetId,
          sheetName: OPERATION_LOG_SHEET_NAME,
          range: `A${existingLogRowNumber}:${columnName(autoLogCells.length)}${existingLogRowNumber}`,
          rows: [autoLogCells],
          dryRun: false,
          confirmWrite: true,
          allowOverwrite: true,
        });
        writeYuesiCells(options.writer, {
          spreadsheetToken: currentReport.spreadsheetToken,
          sheetId: operationLogSheetId,
          sheetName: OPERATION_LOG_SHEET_NAME,
          range: `${warningColumn}${existingLogRowNumber}:${warningColumn}${existingLogRowNumber}`,
          rows: [[warningCell]],
          dryRun: false,
          confirmWrite: true,
          allowOverwrite: true,
        });
        logOverwrittenItemIds.push(row.itemId);
        continue;
      }
      if (options.repairAdMetrics) {
        const existingLogRowNumber = logInfo.rowByKey.get(logKey);
        if (!existingLogRowNumber) {
          throw new Error(`无法定位已有日志行: ${logKey}`);
        }
        writeYuesiCells(options.writer, {
          spreadsheetToken: currentReport.spreadsheetToken,
          sheetId: operationLogSheetId,
          sheetName: OPERATION_LOG_SHEET_NAME,
          // 删除"在售判断"列后，近3天广告指标位于 F~N（共9列）
          range: `F${existingLogRowNumber}:N${existingLogRowNumber}`,
          rows: [buildOperationLogAdMetricCells(adMetric, row.itemId)],
          dryRun: false,
          confirmWrite: true,
          allowOverwrite: true,
        });
        logAdMetricRepairedItemIds.push(row.itemId);
        continue;
      }
      duplicateLogSkippedCount += 1;
      continue;
    }

    const logRange = `A${nextLogRowNumber}:${columnName(operationLogRow.length)}${nextLogRowNumber}`;
    writeYuesiCells(options.writer, {
      spreadsheetToken: currentReport.spreadsheetToken,
      sheetId: operationLogSheetId,
      sheetName: OPERATION_LOG_SHEET_NAME,
      range: logRange,
      rows: [operationLogRow],
      dryRun: false,
      confirmWrite: true,
      allowOverwrite: false,
    });
    logInfo.existingKeys.add(logKey);
    logInfo.rowByKey.set(logKey, nextLogRowNumber);
    logInsertedItemIds.push(row.itemId);
    nextLogRowNumber += 1;
  }

  return {
    mainUpdatedItemIds,
    mainInsertedItemIds,
    logInsertedItemIds,
    logOverwrittenItemIds,
    logAdMetricRepairedItemIds,
    duplicateLogSkippedCount,
    skippedNoAdMetricCount,
    filteredCandidateCount: mainCandidates.length,
  };
}

async function runMappingDryRun(options: {
  writer: FeishuSheetWriter;
  client: LingxingClient;
  analysisDate: string;
}): Promise<void> {
  const mainSheetId = getActiveTargetSheetId();
  const operationLogSheetId = SHEETS[OPERATION_LOG_SHEET_NAME];
  if (!mainSheetId) {
    throw new Error(`缺少配置：${TARGET_SHEET_NAME}`);
  }
  if (!operationLogSheetId) {
    throw new Error(`缺少配置：${OPERATION_LOG_SHEET_NAME}`);
  }

  console.log("悦斯测品双 Sheet 字段映射 dry-run");
  console.log(`写入模式: dry-run，只读取和预览，不写入飞书`);
  console.log(`主表: ${TARGET_SHEET_NAME} (${mainSheetId})`);
  console.log(`日志表: ${OPERATION_LOG_SHEET_NAME} (${operationLogSheetId})`);
  console.log(`唯一键: 店铺 + 商品ID`);
  console.log(`分析日期: ${options.analysisDate}`);

  const mainHeaders = readHeaderRow(options.writer, TARGET_SHEET_NAME, mainSheetId, "O");
  const logHeaders = readHeaderRow(options.writer, OPERATION_LOG_SHEET_NAME, operationLogSheetId, "AB");
  const mainHeaderOk = headersMatch(mainHeaders, MAIN_SHEET_HEADERS);
  const logHeaderOk = headersMatch(logHeaders, OPERATION_LOG_HEADERS);

  console.log("");
  console.log(`主表表头检查: ${mainHeaderOk ? "通过" : "有差异"}`);
  console.log(mainHeaders.map((header, index) => `${String.fromCharCode(65 + index)}:${header}`).join(" | "));
  console.log(`日志表表头检查: ${logHeaderOk ? "通过" : "有差异"}`);
  console.log(
    logHeaders
      .map((header, index) => {
        const column =
          index < 26 ? String.fromCharCode(65 + index) : `A${String.fromCharCode(65 + index - 26)}`;
        return `${column}:${header}`;
      })
      .join(" | "),
  );

  console.log("");
  printFieldList("主表允许更新字段", MAIN_ALLOWED_UPDATE_FIELDS);
  printFieldList("主表不会覆盖字段", MAIN_PROTECTED_FIELDS);
  printFieldList("日志表自动写入字段", [...OPERATION_LOG_AUTO_FIELDS, "测品预警"]);
  printFieldList("日志表不自动写入字段", OPERATION_LOG_PROTECTED_FIELDS);

  const mainRows = readMainSheetPreviewRows(options.writer);
  const recentStartDate = getRecentAdStartDate(options.analysisDate);
  const analysisWindow = resolveAnalysisWindow(options.analysisDate);
  const adResult = await fetchAdItemMetrics(
    options.client,
    recentStartDate,
    options.analysisDate,
    recentStartDate,
    options.analysisDate,
  );
  const keywordResult = await fetchKeywordAdRecords(options.client, recentStartDate, options.analysisDate);
  assertAdApiDataReady(adResult, keywordResult);
  const autoAdSearchTermResult = readAutoAdSearchTermMap(options.writer, analysisWindow);
  const previewRows = mainRows.slice(0, 5);

  console.log("");
  console.log(`dry-run筛选: 非WFS库存 > 0 且在售判断为在售/有库存`);
  console.log(`主表符合筛选商品数: ${mainRows.length}`);
  console.log(`analysisWindow: ${analysisWindow.text}`);
  console.log(`近3天广告日期范围: ${analysisWindow.startDate}~${analysisWindow.endDate}`);
  console.log(`近3天广告记录数: ${adResult.fetchedCount}`);
  console.log(
    `${AUTO_AD_SEARCH_TERM_SHEET_NAME}可匹配商品数: ${autoAdSearchTermResult.map.size}（配置=${autoAdSearchTermResult.sheetConfigured ? "是" : "否"}）`,
  );
  if (adResult.errorMessages.length > 0) {
    console.log(`广告读取非阻塞错误: ${adResult.errorMessages.join("；")}`);
  }

  console.log("");
  console.log("主表预览前 5 个商品:");
  console.table(
    previewRows.map((row) => ({
      店铺: row.storeName,
      商品ID: row.itemId,
      MSKU: row.msku,
      准备更新字段: MAIN_ALLOWED_UPDATE_FIELDS.join("、"),
      不会覆盖字段: MAIN_PROTECTED_FIELDS.join("、"),
    })),
  );

  console.log("");
  console.log("日志表预览前 5 个商品:");
  console.table(
    previewRows.map((row) => {
      const adMetric = adResult.metricMap.get(row.itemId);
      if (!hasOperationLogAdMetricData(adMetric)) {
        return {
          分析日期: options.analysisDate,
          分析窗口: analysisWindow.text,
          商品ID: row.itemId,
          MSKU: row.msku,
          广告API状态: "缺少广告商品API记录，日志写入将跳过，禁止fallback 0",
        };
      }
      const metricInput = buildOperationLogMetricInput(adMetric, row.itemId);
      const spend = money(metricInput.adSpend);
      const sales = money(metricInput.adSales);
      const orders = metricInput.adOrders;
      const impressions = metricInput.impressions;
      const clicks = metricInput.clicks;
      return {
        分析日期: options.analysisDate,
        分析窗口: analysisWindow.text,
        商品ID: row.itemId,
        MSKU: row.msku,
        近3天广告花费: spend,
        近3天广告销售额: sales,
        近3天广告订单数: orders,
        近3天广告曝光: impressions,
        近3天广告点击: clicks,
        近3天CTR: percentText2(ratio(clicks, impressions)),
        近3天CPC: money(ratio(spend, clicks)),
        近3天CVR: percentText2(ratio(orders, clicks)),
        近3天ACOS: percentText2(ratio(spend, sales)),
        AI字段预览: "待AI生成，本步骤不调用AI",
        "运营日志/备注": "保持空白或保留人工填写",
      };
    }),
  );

  console.log("");
  console.log(`是否已配置 ${OPERATION_LOG_SHEET_NAME}: 是 (${operationLogSheetId})`);
  console.log(`主表字段映射是否成功: ${mainHeaderOk ? "是" : "否，表头存在差异"}`);
  console.log(`日志表字段映射是否成功: ${logHeaderOk ? "是" : "否，表头存在差异"}`);
  console.log("是否正式写入飞书: 否");
}

async function main(): Promise<void> {
  assertNoLegacyRewriteSymbols();
  const startedAt = Date.now();
  const runId = createRunId();
  const env = resolveRuntimeEnv();
  configureRuntimeSheets(env);
  const requestedConfirmWrite = process.argv.includes("--confirm-write");
  const explicitDryRun = process.argv.includes("--dry-run");
  const mappingDryRun = process.argv.includes("--mapping-dry-run");
  const checkYuesiAiConfig = process.argv.includes("--check-yuesi-ai-config");
  const backfillFirstAdDate = process.argv.includes("--backfill-first-ad-date");
  const backfillAdMetrics = process.argv.includes("--backfill-ad-metrics");
  const confirmWrite = env === "dev" ? false : requestedConfirmWrite || backfillAdMetrics;
  const dryRun = !confirmWrite;
  const allowFeishuWrite = env !== "dev" && confirmWrite;
  const startDate = getArg("startDate");
  const endDate = getArg("endDate");
  const analysisDateContext = resolveAnalysisDate();
  const { serverCurrentDate, analysisDate } = analysisDateContext;
  const itemId = getArg("item-id");
  const repairAdMetrics = process.argv.includes("--repair-ad-metrics");
  const overwriteExistingLog = process.argv.includes("--overwrite-existing-log");
  const recentAdDays = Number(getArg("recentAdDays", String(DEFAULT_RECENT_AD_DAYS)));
  const writer = new FeishuSheetWriter();
  const client = new LingxingClient(loadConfig());
  const logger = new TableOperationLogger(writer, {
    spreadsheetToken: currentReport.spreadsheetToken,
    logSheetId: currentReport.sheets[LOG_SHEET_NAME],
    dryRun,
    confirmWrite,
  });

  if ((requestedConfirmWrite || backfillAdMetrics) && explicitDryRun) {
    throw new Error("--dry-run 和 --confirm-write 不能同时使用");
  }
  if (env === "dev" && requestedConfirmWrite) {
    console.log("env=dev 强制 dry-run：已忽略 --confirm-write，不会写入飞书。");
  }
  if (backfillAdMetrics && env !== "prod") {
    throw new Error(`--backfill-ad-metrics 只允许 env=prod，当前 env=${env}`);
  }
  printRuntimeContext({
    env,
    confirmWrite,
    dryRun,
    allowFeishuWrite,
    limit: getArg("limit") && getArg("limit") !== "auto" ? Number(getArg("limit")) : undefined,
  });
  if (getArg("limit") === "auto") {
    console.log(`limit参数: auto（${backfillAdMetrics ? "回填模式解析为全部历史行" : "生产写入解析为208"}）`);
  }

  if (checkYuesiAiConfig) {
    runYuesiAiConfigCheck(writer);
    return;
  }

  if (mappingDryRun) {
    printAnalysisDateContext(serverCurrentDate, analysisDate, analysisDateContext.source);
    await runMappingDryRun({ writer, client, analysisDate });
    return;
  }

  if (backfillAdMetrics) {
    const limit = getBackfillLimit();
    const batchSize = getBackfillBatchSize();
    const lastProcessedRow = getBackfillLastProcessedRow();
    let status = "success";
    let errorMessage = "";
    let result: BackfillAdMetricsResult = {
      totalRows: 0,
      repairedCount: 0,
      skippedNoApiDataCount: 0,
      apiFailedCount: 0,
      lastProcessedRow,
    };
    let logSuccess = false;

    console.log(TASK_NAME);
    console.log(`运行ID: ${runId}`);
    console.log("写入模式: backfill-ad-metrics");
    console.log(`当前 env: ${env}`);
    console.log(`是否允许写飞书: 是，仅允许更新 ${OPERATION_LOG_SHEET_NAME} F:N（近3天广告指标）`);
    console.log(`limit: ${getArg("limit")}`);
    console.log(`batch: ${batchSize}`);
    console.log(`lastProcessedRow: ${lastProcessedRow}`);
    console.log("安全规则: 不新增行、不清空、不整行覆盖、不触碰运营日志/备注/人工字段、不读取主表聚合广告数据");

    try {
      result = await runBackfillAdMetrics({
        writer,
        client,
        limit,
        batchSize,
        lastProcessedRow,
      });
    } catch (error) {
      status = "failed";
      errorMessage = error instanceof Error ? error.message : String(error);
      console.log(`<REDACTED_FEISHU_SHEET_ID>历史广告指标回填失败: ${errorMessage}`);
    } finally {
      try {
        logger.append({
          executedAt: new Date().toISOString(),
          taskName: `${TASK_NAME}-<REDACTED_FEISHU_SHEET_ID>历史广告指标回填`,
          targetSheet: OPERATION_LOG_SHEET_NAME,
          operationType: "backfill_ad_metrics",
          dataSource: `${WALMART_SP_AD_PATH}+${WALMART_SP_KEYWORD_PATH}`,
          dateRange: "按<REDACTED_FEISHU_SHEET_ID>每行分析日期回填近3天",
          fetchedCount: result.totalRows,
          writtenCount: result.repairedCount,
          updatedCount: result.repairedCount,
          skippedCount: result.skippedNoApiDataCount,
          failedCount: status === "failed" ? 1 : result.apiFailedCount,
          status,
          errorMessage,
          durationSeconds: Number(((Date.now() - startedAt) / 1000).toFixed(3)),
          runId,
          environment: "local",
          remark:
            `CODEX执行：悦斯测品运营日志历史广告指标回填` +
            `，只更新G:O` +
            `，修复总行数=${result.totalRows}` +
            `，成功修复=${result.repairedCount}` +
            `，跳过无API数据=${result.skippedNoApiDataCount}` +
            `，API失败=${result.apiFailedCount}` +
            `，lastProcessedRow=${result.lastProcessedRow}` +
            `，数据来源=领星广告商品报表+关键词报表` +
            (errorMessage ? `，失败原因=${errorMessage}` : ""),
        });
        logSuccess = true;
      } catch (logError) {
        console.log(`记录操作日志失败: ${logError instanceof Error ? logError.message : String(logError)}`);
      }

      console.log("");
      console.log("<REDACTED_FEISHU_SHEET_ID>历史广告指标回填汇总:");
      console.log(`修复总行数: ${result.totalRows}`);
      console.log(`成功修复行数: ${result.repairedCount}`);
      console.log(`跳过（无API数据）行数: ${result.skippedNoApiDataCount}`);
      console.log(`API失败行数: ${result.apiFailedCount}`);
      console.log(`lastProcessedRow: ${result.lastProcessedRow}`);
      console.log("是否新增日志行: 否");
      console.log("是否覆盖运营日志/备注/人工字段: 否");
      console.log(`表格操作日志是否写入成功: ${logSuccess ? "是" : "否"}`);

      if (status === "failed") {
        process.exitCode = 1;
      }
    }
    return;
  }

  if (backfillFirstAdDate) {
    if (confirmWrite && env !== "prod") {
      throw new Error(`--backfill-first-ad-date 属于批量补写，只有 env=prod 才允许 confirm-write，当前 env=${env}`);
    }
    let status = dryRun ? "dry-run" : "success";
    let errorMessage = "";
    let result: FirstAdDateBackfillResult = {
      scannedCount: 0,
      writableCount: 0,
      updatedCount: 0,
      skippedCount: 0,
      missingCount: 0,
      updatedItemIds: [],
    };
    let logSuccess = false;

    console.log(TASK_NAME);
    console.log(`运行ID: ${runId}`);
    console.log(`写入模式: ${confirmWrite ? "confirm-write" : "dry-run"}`);
    printAnalysisDateContext(serverCurrentDate, analysisDate, analysisDateContext.source);

    try {
      result = await runFirstAdDateBackfill({
        writer,
        client,
        analysisDate,
        dryRun,
        confirmWrite,
      });
    } catch (error) {
      status = "failed";
      errorMessage = error instanceof Error ? error.message : String(error);
      console.log(`首次广告日期补写失败: ${errorMessage}`);
    } finally {
      try {
        logger.append({
          executedAt: new Date().toISOString(),
          taskName: `${TASK_NAME}-首次广告日期补写`,
          targetSheet: activeTargetSheetName,
          operationType: confirmWrite ? "confirm-write" : "dry-run",
          dataSource: `${SOURCE_SHEET_NAME}+/basicOpen/multiplatform/ads/reportAdItemSpList`,
          dateRange: analysisDate,
          fetchedCount: result.scannedCount,
          writtenCount: result.updatedCount,
          updatedCount: result.updatedCount,
          skippedCount: result.skippedCount,
          failedCount: status === "failed" ? 1 : result.missingCount,
          status,
          errorMessage,
          durationSeconds: Number(((Date.now() - startedAt) / 1000).toFixed(3)),
          runId,
          environment: "local",
          remark:
            `CODEX执行：悦斯店铺数据分析首次广告日期补写` +
            `，目标Sheet=${getActiveTargetSheetId()}` +
            `，查询截止日期=${analysisDate}` +
            `，扫描商品=${result.scannedCount}` +
            `，计划写入=${result.writableCount}` +
            `，实际写入=${result.updatedCount}` +
            `，已一致跳过=${result.skippedCount}` +
            `，缺少日期=${result.missingCount}` +
            `，只更新E列，不覆盖人工字段` +
            (errorMessage ? `，失败原因=${errorMessage}` : ""),
        });
        logSuccess = true;
      } catch (logError) {
        console.log(`记录操作日志失败: ${logError instanceof Error ? logError.message : String(logError)}`);
      }

      console.log("");
      console.log("首次广告日期补写汇总:");
      console.log(`扫描商品数: ${result.scannedCount}`);
      console.log(`计划写入数: ${result.writableCount}`);
      console.log(`实际写入数: ${result.updatedCount}`);
      console.log(`已一致跳过数: ${result.skippedCount}`);
      console.log(`缺少日期数: ${result.missingCount}`);
      console.log(`更新商品ID: ${result.updatedItemIds.join(", ") || "无"}`);
      console.log("是否只更新 E 列: 是");
      console.log(`表格操作日志是否写入成功: ${logSuccess ? "是" : "否"}`);

      if (status === "failed") {
        process.exitCode = 1;
      }
    }
    return;
  }

  if (confirmWrite) {
    const limit = getRequiredLimit(env);
    let status = "success";
    let errorMessage = "";
    let result: SafeWriteResult = {
      mainUpdatedItemIds: [],
      mainInsertedItemIds: [],
      logInsertedItemIds: [],
      logOverwrittenItemIds: [],
      logAdMetricRepairedItemIds: [],
      duplicateLogSkippedCount: 0,
      skippedNoAdMetricCount: 0,
      filteredCandidateCount: 0,
    };
    let logSuccess = false;

    console.log(TASK_NAME);
    console.log(`运行ID: ${runId}`);
    console.log("写入模式: confirm-write");
    console.log(`目标店铺: ${STORE_NAME}`);
    console.log(`主表: ${activeTargetSheetName} (${getActiveTargetSheetId()})`);
    console.log(`日志表: ${OPERATION_LOG_SHEET_NAME} (${SHEETS[OPERATION_LOG_SHEET_NAME]})`);
    printAnalysisDateContext(serverCurrentDate, analysisDate, analysisDateContext.source);
    console.log(`指定商品ID: ${itemId || "未指定"}`);
    console.log(`limit: ${limit}`);
    console.log(`广告指标修复模式: ${repairAdMetrics ? "启用 --repair-ad-metrics" : "未启用"}`);
    console.log(`已有日志覆盖模式: ${overwriteExistingLog ? "启用 --overwrite-existing-log" : "未启用"}`);
    console.log("安全规则: 不清空、不整表重写、不覆盖负责人/人工审核结果/备注、不覆盖运营日志/备注");

    try {
      result = await runLimitedConfirmWrite({
        writer,
        client,
        analysisDate,
        limit,
        itemId,
        repairAdMetrics,
        overwriteExistingLog,
        dryRun: false,
        confirmWrite: true,
      });
    } catch (error) {
      status = "failed";
      errorMessage = error instanceof Error ? error.message : String(error);
      console.log(`悦斯测品小范围写入失败: ${errorMessage}`);
    } finally {
      try {
        logger.append({
          executedAt: new Date().toISOString(),
          taskName: TASK_NAME,
          targetSheet: `${TARGET_SHEET_NAME}+${OPERATION_LOG_SHEET_NAME}`,
          operationType: "limited_confirm_write",
          dataSource: `${TARGET_SHEET_NAME}+/basicOpen/multiplatform/ads/reportAdItemSpList`,
          dateRange: analysisDate,
          fetchedCount: result.filteredCandidateCount,
          writtenCount: result.logInsertedItemIds.length + result.logOverwrittenItemIds.length,
          updatedCount:
            result.mainUpdatedItemIds.length +
            result.mainInsertedItemIds.length +
            result.logOverwrittenItemIds.length +
            result.logAdMetricRepairedItemIds.length,
          skippedCount: result.duplicateLogSkippedCount + result.skippedNoAdMetricCount,
          failedCount: status === "failed" ? 1 : 0,
          status,
          errorMessage,
          durationSeconds: Number(((Date.now() - startedAt) / 1000).toFixed(3)),
          runId,
          environment: "local",
          remark:
            `CODEX执行：悦斯测品小范围真实写入，分析日期=${analysisDate}` +
            `，limit=${limit}` +
            `，主表新增商品ID=${result.mainInsertedItemIds.join("/") || "无"}` +
            `，主表更新商品ID=${result.mainUpdatedItemIds.join("/") || "无"}` +
            `，日志表新增商品ID=${result.logInsertedItemIds.join("/") || "无"}` +
            `，日志表覆盖商品ID=${result.logOverwrittenItemIds.join("/") || "无"}` +
            `，日志广告指标修复商品ID=${result.logAdMetricRepairedItemIds.join("/") || "无"}` +
            `，重复日志跳过=${result.duplicateLogSkippedCount}` +
            `，缺少广告API记录跳过=${result.skippedNoAdMetricCount}` +
            `，未覆盖人工字段=负责人/人工审核结果/备注/运营日志/备注` +
            (errorMessage ? `，失败原因=${errorMessage}` : ""),
        });
        logSuccess = true;
      } catch (logError) {
        console.log(`记录操作日志失败: ${logError instanceof Error ? logError.message : String(logError)}`);
      }

      console.log("");
      console.log("悦斯测品小范围写入汇总:");
      console.log(`实际处理商品数: ${result.mainUpdatedItemIds.length + result.mainInsertedItemIds.length}`);
      console.log(`主表新增商品ID: ${result.mainInsertedItemIds.join(", ") || "无"}`);
      console.log(`主表更新商品ID: ${result.mainUpdatedItemIds.join(", ") || "无"}`);
      console.log(`日志表新增商品ID: ${result.logInsertedItemIds.join(", ") || "无"}`);
      console.log(`日志表覆盖商品ID: ${result.logOverwrittenItemIds.join(", ") || "无"}`);
      console.log(`日志表广告指标修复商品ID: ${result.logAdMetricRepairedItemIds.join(", ") || "无"}`);
      console.log(`重复日志跳过: ${result.duplicateLogSkippedCount}`);
      console.log(`缺少广告API记录跳过: ${result.skippedNoAdMetricCount}`);
      console.log("是否覆盖人工字段: 没有");
      console.log(`表格操作日志是否写入成功: ${logSuccess ? "是" : "否"}`);

      if (status === "failed") {
        process.exitCode = 1;
      }
    }
    return;
  }

  let fetchedCount = 0;
  let writtenCount = 0;
  let status = dryRun ? "dry-run" : "success";
  let errorMessage = "";
  let logSuccess = false;

  console.log(TASK_NAME);
  console.log(`运行ID: ${runId}`);
  console.log(`写入模式: ${confirmWrite ? "confirm-write" : "dry-run"}`);
  console.log(`目标店铺: ${STORE_NAME}`);
  console.log(`目标 Sheet: ${activeTargetSheetName} (${getActiveTargetSheetId()})`);
  printAnalysisDateContext(serverCurrentDate, analysisDate, analysisDateContext.source);
  console.log(`日期范围: ${startDate || "不限"}~${endDate || "不限"}`);
  console.log(`近N天广告分析: ${recentAdDays}`);

  try {
    await runMappingDryRun({ writer, client, analysisDate });
  } catch (error) {
    status = "failed";
    errorMessage = error instanceof Error ? error.message : String(error);
    console.log(`悦斯测品分析失败: ${errorMessage}`);
  } finally {
    try {
      logger.append({
        executedAt: new Date().toISOString(),
        taskName: TASK_NAME,
        targetSheet: activeTargetSheetName,
        operationType: "safe_preview",
        dataSource: SOURCE_SHEET_NAME,
        dateRange: `${startDate || "不限"}~${endDate || "不限"}`,
        fetchedCount,
        writtenCount: status === "failed" ? 0 : writtenCount,
        updatedCount: 0,
        skippedCount: 0,
        failedCount: status === "failed" ? 1 : 0,
        status,
        errorMessage,
        durationSeconds: Number(((Date.now() - startedAt) / 1000).toFixed(3)),
        runId,
        environment: "local",
        remark:
          `CODEX执行：悦斯店铺测品数据分析，店铺=${STORE_NAME}` +
          `，来源=${SOURCE_SHEET_NAME}` +
          `，写入系统收口重构后仅允许upsert和append-only日志` +
          `，默认分支只做安全预览，不执行legacy overwrite` +
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

main();
