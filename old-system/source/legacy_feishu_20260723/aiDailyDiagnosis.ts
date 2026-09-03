import currentReport from "../config/currentReportFieldMapping.json";
import { loadConfig } from "./config";
import { FeishuSheetWriter, SheetRow } from "./feishuSheetWriter";
import { LingxingClient } from "./lingxingClient";
import { STORES, StoreConfig } from "./syncDailyBaseData";
import { TableOperationLogger } from "./tableOperationLogger";

const axios = require("axios/dist/node/axios.cjs") as typeof import("axios").default;

type ProductLevel = "A" | "B" | "C" | "D" | "";

interface DailyLogRow {
  rowNumber: number;
  date: string;
  storeName: string;
  itemId: string;
  msku: string;
  owner: string;
  productLevel: ProductLevel;
  productIssue: string;
  solution: string;
  operationLog: string;
  diagnosisRecord: string;
}

interface HeaderMap {
  date: number;
  store: number;
  itemId: number;
  msku: number;
  owner: number;
  productLevel: number;
  productIssue: number;
  solution: number;
  operationLog: number;
  diagnosisRecord?: number;
}

interface RecentMetric {
  salesAmount5d: number;
  salesQty5d: number;
  adCost5d: number;
  adRatio5d: number;
  grossProfit5d: number;
  grossMargin5d: number;
}

interface DailyMetric {
  grossProfit: number;
  grossMargin: number;
  salesQty: number;
  salesAmount: number;
  adCost: number;
  adRatio: number;
  wfsAvailableQty: number;
}

interface KeywordAdRecord {
  keyword: string;
  keywordSource: string;
  adType: "manual" | "auto";
  dataSource: string;
  adDateRange: string;
  operator: string;
  campaignName: string;
  adGroupName: string;
  matchType: string;
  keywordStatus: string;
  campaignStatus: string;
  adGroupStatus: string;
  impressions: number;
  clicks: number;
  ctr: number;
  cpc: number;
  cvr: number;
  adSpend: number;
  attributedSales: number;
  attributedOrders: number;
  attributedUnits: number;
  acos: number;
  roas: number;
  systemDiagnosis: string;
  aiAnalysisResult: string;
}

interface DiagnosisText {
  productIssue: string;
  solution: string;
}

interface AiDiagnosisConfig {
  adAnalysisDays: number;
  bLevelIntervalDays: number;
  cLevelIntervalDays: number;
  dLevelIntervalDays: number;
  systemPrompt: string;
  outputFormat: string;
  keywordAnalysisRules: string;
  forbiddenActions: string;
  raw: Record<string, string>;
}

interface AdAnalysisRange {
  startDate: string;
  endDate: string;
  label: string;
}

const TASK_NAME = "每日运营跟进日志AI诊断";
const DAILY_LOG_SHEET_NAME = "每日运营跟进日志";
const RECENT_PROFIT_SHEET_NAME = "近期利润与广告";
const DAILY_DATA_SHEET_NAME = "当日数据";
const AI_CONFIG_SHEET_NAME = "AI诊断配置";
const LOG_SHEET_NAME = "表格操作日志";
const WALMART_SP_KEYWORD_PATH = "/basicOpen/multiplatform/ads/reportKeywordSpList";
const AUTO_AD_SEARCH_TERM_SHEET_NAME = "自动广告搜索词聚合分析";
const TIME_ZONE = "Asia/Shanghai";
const READ_BATCH_SIZE = 500;
const DAILY_LOG_READ_END_ROW = 100000; // 每日运营跟进日志持续增长，不设小上限
const RECENT_READ_END_ROW = 50000;
const DAILY_DATA_READ_END_ROW = 3000; // 当日数据每日重写，行数固定可控
const AD_PAGE_SIZE = 200;
const AD_MAX_PAGES = 20;
const AUTO_AD_READ_BATCH_SIZE = 1000;
const AUTO_AD_READ_END_ROW = 20000;
const LINGXING_TIMEOUT_MS = 120000;
const AI_TIMEOUT_MS = 180000;
const AI_BATCH_SIZE = 1;

const DEFAULT_AI_DIAGNOSIS_CONFIG: AiDiagnosisConfig = {
  adAnalysisDays: 7,
  bLevelIntervalDays: 7,
  cLevelIntervalDays: 5,
  dLevelIntervalDays: 3,
  systemPrompt: "你是沃尔玛广告运营诊断助手，只基于给定数据做判断。",
  outputFormat: "只返回严格 JSON：{\"productDataIssue\":\"...\",\"solution\":\"...\"}",
  keywordAnalysisRules:
    "必须分析到具体关键词；重点检查高花费低转化、低曝光、长期无消耗、无订单、高ACOS、关键词与产品不相关、品牌词或泛词误投放等问题；解决意见必须点名关键词和动作。",
  forbiddenActions: "不要建议发货、退款、改库存；不要编造不存在的数据；不要覆盖运营日志。",
  raw: {},
};

interface ExternalAutoAdSheetConfig {
  spreadsheetToken: string;
  sheetId: string;
  sheetName: string;
}

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

function isAiEnabled(): boolean {
  return normalizeText(process.env.ENABLE_AI_DIAGNOSIS).toLowerCase() === "true";
}

function isConfigEnabled(value: unknown): boolean {
  const text = normalizeText(value).toLowerCase();
  return !text || ["1", "true", "yes", "y", "是", "启用", "开启"].includes(text);
}

function toPositiveInteger(value: string, defaultValue: number): number {
  const parsed = Number(value);
  return Number.isInteger(parsed) && parsed > 0 ? parsed : defaultValue;
}

function readAiDiagnosisConfig(writer: FeishuSheetWriter): AiDiagnosisConfig {
  const sheetId = currentReport.sheets[AI_CONFIG_SHEET_NAME];
  if (!sheetId) {
    console.log(`AI诊断配置: 未配置 Sheet ID，使用默认规则`);
    return { ...DEFAULT_AI_DIAGNOSIS_CONFIG, raw: {} };
  }

  const rows = writer.readValues({
    spreadsheetToken: currentReport.spreadsheetToken,
    sheetId,
    range: "A1:D200",
  });

  const raw: Record<string, string> = {};
  for (const row of rows) {
    const key = normalizeText(row[0]);
    const value = normalizeText(row[1]);
    if (!key || normalizeHeader(key) === normalizeHeader("配置项") || !value || !isConfigEnabled(row[3])) {
      continue;
    }
    raw[key.trim().toUpperCase()] = value;
  }

  const config: AiDiagnosisConfig = {
    ...DEFAULT_AI_DIAGNOSIS_CONFIG,
    raw,
    adAnalysisDays: toPositiveInteger(raw.AI_AD_ANALYSIS_DAYS, DEFAULT_AI_DIAGNOSIS_CONFIG.adAnalysisDays),
    bLevelIntervalDays: toPositiveInteger(raw.B_LEVEL_INTERVAL_DAYS, DEFAULT_AI_DIAGNOSIS_CONFIG.bLevelIntervalDays),
    cLevelIntervalDays: toPositiveInteger(raw.C_LEVEL_INTERVAL_DAYS, DEFAULT_AI_DIAGNOSIS_CONFIG.cLevelIntervalDays),
    dLevelIntervalDays: toPositiveInteger(raw.D_LEVEL_INTERVAL_DAYS, DEFAULT_AI_DIAGNOSIS_CONFIG.dLevelIntervalDays),
    systemPrompt: raw.AI_SYSTEM_PROMPT || DEFAULT_AI_DIAGNOSIS_CONFIG.systemPrompt,
    outputFormat: raw.AI_OUTPUT_FORMAT || DEFAULT_AI_DIAGNOSIS_CONFIG.outputFormat,
    keywordAnalysisRules: raw.KEYWORD_ANALYSIS_RULES || DEFAULT_AI_DIAGNOSIS_CONFIG.keywordAnalysisRules,
    forbiddenActions: raw.FORBIDDEN_ACTIONS || DEFAULT_AI_DIAGNOSIS_CONFIG.forbiddenActions,
  };

  console.log(
    `AI诊断配置: Sheet=${sheetId}，广告分析天数=${config.adAnalysisDays}，B/C/D频次=${config.bLevelIntervalDays}/${config.cLevelIntervalDays}/${config.dLevelIntervalDays}天`,
  );
  return config;
}

function buildAdAnalysisRange(dataDate: string, config: AiDiagnosisConfig): AdAnalysisRange {
  const days = Math.max(1, config.adAnalysisDays);
  const startDate = addDays(dataDate, -(days - 1));
  return {
    startDate,
    endDate: dataDate,
    label: `${startDate}~${dataDate}`,
  };
}

function getDiagnosisIntervalDays(level: ProductLevel, config: AiDiagnosisConfig): number {
  if (level === "B") return config.bLevelIntervalDays;
  if (level === "C") return config.cLevelIntervalDays;
  if (level === "D") return config.dLevelIntervalDays;
  return config.adAnalysisDays;
}

function parseNextDiagnosisDate(record: string): string {
  const match = /下次AI诊断日期\s*[=:：]\s*(\d{4}-\d{2}-\d{2})/.exec(record);
  return match?.[1] ?? "";
}

function formatDiagnosisRecord(options: {
  dataDate: string;
  nextDate: string;
  status: string;
  runId: string;
  adRange: AdAnalysisRange;
}): string {
  return [
    `上次AI诊断日期=${options.dataDate}`,
    `下次AI诊断日期=${options.nextDate}`,
    `AI诊断状态=${options.status}`,
    `AI诊断运行ID=${options.runId}`,
    `广告分析日期范围=${options.adRange.label}`,
  ].join("\n");
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
  const headerMap: HeaderMap = {
    date: requireHeader(headers, ["日期"], "日期"),
    store: requireHeader(headers, ["店铺"], "店铺"),
    itemId: requireHeader(headers, ["商品ID", "ItemID", "ITEMID", "ITEM ID"], "商品ID"),
    msku: requireHeader(headers, ["MSKU"], "MSKU"),
    owner: requireHeader(headers, ["负责人"], "负责人"),
    productLevel: requireHeader(headers, ["产品等级"], "产品等级"),
    productIssue: requireHeader(headers, ["产品数据问题"], "产品数据问题"),
    solution: requireHeader(headers, ["解决意见"], "解决意见"),
    operationLog: requireHeader(headers, ["运营日志"], "运营日志"),
  };
  const diagnosisRecord = findHeaderIndex(headers, ["AI诊断记录"]);
  if (diagnosisRecord >= 0) {
    headerMap.diagnosisRecord = diagnosisRecord;
  }
  return headerMap;
}

function normalizeProductLevel(value: unknown): ProductLevel {
  const text = normalizeText(value).toUpperCase();
  return text === "A" || text === "B" || text === "C" || text === "D" ? text : "";
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

function readDailyLogRows(writer: FeishuSheetWriter, dataDate: string): {
  headers: SheetRow;
  headerMap: HeaderMap;
  rows: DailyLogRow[];
} {
  const sheetRowCount = writer.getRowCount({
    spreadsheetToken: currentReport.spreadsheetToken,
    sheetId: currentReport.sheets[DAILY_LOG_SHEET_NAME],
    sheetName: DAILY_LOG_SHEET_NAME,
  });
  const endLimit = Math.min(DAILY_LOG_READ_END_ROW, sheetRowCount);

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
  const rows: DailyLogRow[] = [];

  // 分批读取数据行（同 readRecentMetricMap 模式），避免超大范围被截断
  for (let startRow = 2; startRow <= endLimit; startRow += READ_BATCH_SIZE) {
    const endRow = Math.min(startRow + READ_BATCH_SIZE - 1, endLimit);
    const batchRows = writer.readValues({
      spreadsheetToken: currentReport.spreadsheetToken,
      sheetId: currentReport.sheets[DAILY_LOG_SHEET_NAME],
      range: `A${startRow}:Z${endRow}`,
    });
    batchRows.forEach((row, batchIndex) => {
      const rowNumber = startRow + batchIndex;
      const date = normalizeText(row[headerMap.date]);
      const storeName = normalizeText(row[headerMap.store]);
      const itemId = normalizeText(row[headerMap.itemId]);
      if (date !== dataDate || !storeName || !itemId) {
        return;
      }
      rows.push({
        rowNumber,
        date,
        storeName,
        itemId,
        msku: normalizeText(row[headerMap.msku]),
        owner: normalizeText(row[headerMap.owner]),
        productLevel: normalizeProductLevel(row[headerMap.productLevel]),
        productIssue: normalizeText(row[headerMap.productIssue]),
        solution: normalizeText(row[headerMap.solution]),
        operationLog: normalizeText(row[headerMap.operationLog]),
        diagnosisRecord:
          headerMap.diagnosisRecord === undefined ? "" : normalizeText(row[headerMap.diagnosisRecord]),
      });
    });
  }

  return { headers, headerMap, rows };
}

function readRecentMetricMap(writer: FeishuSheetWriter): Map<string, RecentMetric> {
  const map = new Map<string, RecentMetric>();
  const sheetRowCount = writer.getRowCount({
    spreadsheetToken: currentReport.spreadsheetToken,
    sheetId: currentReport.sheets[RECENT_PROFIT_SHEET_NAME],
    sheetName: RECENT_PROFIT_SHEET_NAME,
  });
  const endLimit = Math.min(RECENT_READ_END_ROW, sheetRowCount);

  for (let startRow = 2; startRow <= endLimit; startRow += READ_BATCH_SIZE) {
    const endRow = Math.min(startRow + READ_BATCH_SIZE - 1, endLimit);
    const rows = writer.readValues({
      spreadsheetToken: currentReport.spreadsheetToken,
      sheetId: currentReport.sheets[RECENT_PROFIT_SHEET_NAME],
      range: `A${startRow}:R${endRow}`,
    });

    for (const row of rows) {
      const storeName = normalizeText(row[0]);
      const itemId = normalizeText(row[1]);
      if (!storeName || !itemId) {
        continue;
      }
      map.set(buildItemKey(storeName, itemId), {
        salesAmount5d: toNumber(row[12]),
        salesQty5d: toNumber(row[13]),
        adCost5d: toNumber(row[14]),
        adRatio5d: toNumber(row[15]),
        grossProfit5d: toNumber(row[16]),
        grossMargin5d: toNumber(row[17]),
      });
    }
  }

  return map;
}

function readDailyMetricMap(writer: FeishuSheetWriter, dataDate: string): Map<string, DailyMetric> {
  const map = new Map<string, DailyMetric>();
  const sheetRowCount = writer.getRowCount({
    spreadsheetToken: currentReport.spreadsheetToken,
    sheetId: currentReport.sheets[DAILY_DATA_SHEET_NAME],
    sheetName: DAILY_DATA_SHEET_NAME,
  });
  const endLimit = Math.min(DAILY_DATA_READ_END_ROW, sheetRowCount);

  for (let startRow = 2; startRow <= endLimit; startRow += READ_BATCH_SIZE) {
    const endRow = Math.min(startRow + READ_BATCH_SIZE - 1, endLimit);
    const rows = writer.readValues({
      spreadsheetToken: currentReport.spreadsheetToken,
      sheetId: currentReport.sheets[DAILY_DATA_SHEET_NAME],
      range: `A${startRow}:T${endRow}`,
    });

    for (const row of rows) {
      const date = normalizeText(row[0]);
      const storeName = normalizeText(row[1]);
      const itemId = normalizeText(row[2]);
      if (date !== dataDate || !storeName || !itemId) {
        continue;
      }
      map.set(buildItemKey(storeName, itemId), {
        grossProfit: toNumber(row[7]),
        grossMargin: toNumber(row[8]),
        salesQty: toNumber(row[9]),
        salesAmount: toNumber(row[10]),
        adCost: toNumber(row[11]),
        adRatio: toNumber(row[12]),
        wfsAvailableQty: toNumber(row[19]),
      });
    }
  }

  return map;
}

function shouldDiagnose(row: DailyLogRow, recent: RecentMetric | undefined, daily: DailyMetric | undefined): {
  shouldRun: boolean;
  reason: string;
} {
  if (daily && daily.wfsAvailableQty === 0) {
    return { shouldRun: false, reason: "当日库存为0，不需要AI诊断" };
  }
  if (row.productLevel === "A") {
    return { shouldRun: false, reason: "A级稳健款，不需要AI诊断" };
  }
  if (row.productLevel === "B") {
    const adRatio5d = recent?.adRatio5d ?? 0;
    return adRatio5d >= 0.1
      ? { shouldRun: true, reason: "B级且近5天广告占比>=10%" }
      : { shouldRun: false, reason: "B级且近5天广告占比<10%，不需要AI诊断" };
  }
  if (row.productLevel === "C" || row.productLevel === "D") {
    return { shouldRun: true, reason: `${row.productLevel}级需要AI诊断` };
  }
  return { shouldRun: false, reason: "产品等级为空，不诊断" };
}

function storeConfigByName(storeName: string): StoreConfig | undefined {
  return STORES.find((store) => store.storeName === storeName || storeName.startsWith(store.storeName));
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

function firstTextWithSource(record: Record<string, unknown>, keys: string[]): { value: string; source: string } {
  for (const key of keys) {
    const value = normalizeText(record[key]);
    if (value) {
      return { value, source: key };
    }
  }
  return { value: "", source: "" };
}

function firstTextByKeyPattern(
  record: Record<string, unknown>,
  patterns: string[],
): { value: string; source: string } {
  for (const [key, rawValue] of Object.entries(record)) {
    const normalizedKey = key.replace(/[_\-\s]/g, "").toLowerCase();
    if (
      /(id|type|status|count|num|page|date|time)$/.test(normalizedKey) ||
      normalizedKey.includes("campaign") ||
      normalizedKey.includes("group") ||
      normalizedKey.includes("advertiser")
    ) {
      continue;
    }
    if (!patterns.some((pattern) => normalizedKey.includes(pattern))) {
      continue;
    }
    const value = normalizeText(rawValue);
    if (value) {
      return { value, source: key };
    }
  }
  return { value: "", source: "" };
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

function normalizeKeywordRecord(record: Record<string, unknown>): { itemId: string; ad: KeywordAdRecord } {
  // TODO: 待按领星 reportKeywordSpList 实际响应字段固化字段名。
  const keyword = firstTextWithSource(record, [
    "keywordName",
    "keyword_name",
    "keyword",
    "keywordText",
    "keyword_text",
    "keywordValue",
    "keyword_value",
    "biddedKeyword",
    "bidded_keyword",
    "bidKeyword",
    "bid_keyword",
    "searchedKeyword",
    "searched_keyword",
    "searchKeyword",
    "search_keyword",
    "searchTerm",
    "search_term",
    "query",
    "queryText",
    "query_text",
    "targetingText",
    "targeting_text",
    "targetingValue",
    "targeting_value",
    "targetingName",
    "targeting_name",
    "targetText",
    "target_text",
    "targetName",
    "target_name",
    "target",
    "word",
    "phrase",
    "adKeyword",
    "ad_keyword",
    "walmartKeyword",
    "关键词",
    "投放词",
    "搜索词",
  ]);
  const keywordPattern = firstTextByKeyPattern(record, [
    "keyword",
    "target",
    "search",
    "query",
    "word",
    "phrase",
    "关键词",
    "投放词",
    "搜索词",
  ]);
  const keywordValue = keyword.value || keywordPattern.value;
  const keywordSource = keyword.source || keywordPattern.source;
  return {
    itemId: firstText(record, ["itemId", "item_id", "platformProductId", "platform_product_id", "productId"]),
    ad: {
      keyword: keywordValue,
      keywordSource,
      adType: "manual",
      dataSource: "Lingxing reportKeywordSpList",
      adDateRange: "",
      operator: "",
      campaignName: firstText(record, ["campaignName", "campaign_name", "name"]),
      adGroupName: firstText(record, ["adGroupName", "ad_group_name", "groupName"]),
      matchType: firstText(record, ["matchType", "match_type"]),
      keywordStatus: firstText(record, ["keywordStatus", "keyword_status", "state", "status"]),
      campaignStatus: firstText(record, ["campaignStatus", "campaign_status"]),
      adGroupStatus: firstText(record, ["adGroupStatus", "ad_group_status"]),
      impressions: firstNumber(record, ["impressions", "numAdsShown", "adImpressions"]),
      clicks: firstNumber(record, ["clicks", "numAdsClicks", "adClicks"]),
      ctr: firstNumber(record, ["ctr", "clickThroughRate"]),
      cpc: firstNumber(record, ["cpc", "avgCpc"]),
      cvr: firstNumber(record, ["cvr", "conversionRate"]),
      adSpend: firstNumber(record, ["adSpend", "cost", "spend"]),
      attributedSales: firstNumber(record, ["attributedSales", "sales", "attributedRevenue"]),
      attributedOrders: firstNumber(record, ["attributedOrders", "orders"]),
      attributedUnits: firstNumber(record, ["attributedUnits", "units"]),
      acos: firstNumber(record, ["acos", "adCostSaleRatio"]),
      roas: firstNumber(record, ["roas"]),
      systemDiagnosis: "",
      aiAnalysisResult: "",
    },
  };
}

function buildProductMatchTokens(row: DailyLogRow): string[] {
  const tokens = [row.itemId, row.msku];
  const baseMsku = row.msku.split("-")[0];
  if (baseMsku && baseMsku !== row.msku) {
    tokens.push(baseMsku);
  }
  return Array.from(new Set(tokens.map((token) => normalizeText(token).toLowerCase()).filter(Boolean)));
}

function parseDateRangeText(value: string): { startDate: string; endDate: string } | null {
  const normalized = normalizeText(value).replace(/[—–至到]/g, "~");
  const matches = normalized.match(/\d{4}-\d{2}-\d{2}/g);
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

function normalizeAutoAdSearchTermRow(
  row: SheetRow,
  headerMap: Map<string, number>,
): { itemId: string; ad: KeywordAdRecord; dateRange: string } {
  const dateRange = normalizeText(getHeaderValue(row, headerMap, ["广告时间段", "时间段", "日期范围"]));
  const adSpend = toNumber(getHeaderValue(row, headerMap, ["花费", "Spend", "Cost"]));
  const attributedSales = toNumber(getHeaderValue(row, headerMap, ["销售额", "Attributed Sales", "Ad Sales"]));
  const attributedOrders = toNumber(getHeaderValue(row, headerMap, ["订单", "Orders", "Attributed Orders"]));
  const impressions = toNumber(getHeaderValue(row, headerMap, ["曝光", "Impressions"]));
  const clicks = toNumber(getHeaderValue(row, headerMap, ["点击", "Clicks"]));
  return {
    itemId: normalizeText(getHeaderValue(row, headerMap, ["Item ID", "商品ID", "ITEMID", "ItemID"])),
    dateRange,
    ad: {
      keyword: normalizeText(getHeaderValue(row, headerMap, ["搜索词", "Search Term", "SearchTerm"])),
      keywordSource: "自动广告搜索词聚合分析.搜索词",
      adType: "auto",
      dataSource: AUTO_AD_SEARCH_TERM_SHEET_NAME,
      adDateRange: dateRange,
      operator: normalizeText(getHeaderValue(row, headerMap, ["运营人员", "负责人"])),
      campaignName: normalizeText(getHeaderValue(row, headerMap, ["Campaign Name", "Campaign"])),
      adGroupName: normalizeText(getHeaderValue(row, headerMap, ["Ad Group Name", "Ad Group"])),
      matchType: normalizeText(getHeaderValue(row, headerMap, ["Match Type", "匹配类型"])),
      keywordStatus: "",
      campaignStatus: "",
      adGroupStatus: "",
      impressions,
      clicks,
      ctr: toNumber(getHeaderValue(row, headerMap, ["CTR"])),
      cpc: toNumber(getHeaderValue(row, headerMap, ["CPC"])),
      cvr: toNumber(getHeaderValue(row, headerMap, ["CVR", "转化率"])),
      adSpend,
      attributedSales,
      attributedOrders,
      attributedUnits: toNumber(getHeaderValue(row, headerMap, ["Units Sold", "销量"])),
      acos: toNumber(getHeaderValue(row, headerMap, ["ACoS", "ACOS"])),
      roas: toNumber(getHeaderValue(row, headerMap, ["RoAS", "ROAS"])),
      systemDiagnosis: normalizeText(getHeaderValue(row, headerMap, ["系统诊断"])),
      aiAnalysisResult: normalizeText(getHeaderValue(row, headerMap, ["AI分析结果"])),
    },
  };
}

function readAutoAdSearchTermMap(
  writer: FeishuSheetWriter,
  adRange: AdAnalysisRange,
): { map: Map<string, KeywordAdRecord[]>; fetchedCount: number; matchedCount: number; sheetConfigured: boolean } {
  const sheetConfig = getExternalAutoAdSheetConfig();
  if (!sheetConfig) {
    console.log("自动广告搜索词聚合分析: 未配置外部 Sheet，跳过");
    return { map: new Map(), fetchedCount: 0, matchedCount: 0, sheetConfigured: false };
  }

  const sheetRowCount = writer.getRowCount({
    spreadsheetToken: sheetConfig.spreadsheetToken,
    sheetId: sheetConfig.sheetId,
    sheetName: sheetConfig.sheetName,
  });
  const endLimit = Math.min(AUTO_AD_READ_END_ROW, sheetRowCount);
  if (endLimit < 2) {
    return { map: new Map(), fetchedCount: 0, matchedCount: 0, sheetConfigured: true };
  }

  const headerRows = writer.readValues({
    spreadsheetToken: sheetConfig.spreadsheetToken,
    sheetId: sheetConfig.sheetId,
    range: "A1:AE1",
  });
  const headers = headerRows[0] ?? [];
  const headerMap = buildHeaderIndexMap(headers);
  const result = new Map<string, KeywordAdRecord[]>();
  let fetchedCount = 0;
  let matchedCount = 0;

  for (let startRow = 2; startRow <= endLimit; startRow += AUTO_AD_READ_BATCH_SIZE) {
    const endRow = Math.min(startRow + AUTO_AD_READ_BATCH_SIZE - 1, endLimit);
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
      if (parsedRange && !rangesOverlap(parsedRange, adRange)) {
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
    `自动广告搜索词聚合分析读取: Sheet=${sheetConfig.sheetId}，读取记录=${fetchedCount}，匹配日期窗口记录=${matchedCount}，商品数=${result.size}`,
  );
  return { map: result, fetchedCount, matchedCount, sheetConfigured: true };
}

function keywordRecordMatchesProduct(normalized: { itemId: string; ad: KeywordAdRecord }, row: DailyLogRow): boolean {
  if (normalized.itemId && normalized.itemId === row.itemId) {
    return true;
  }

  const haystack = `${normalized.ad.campaignName} ${normalized.ad.adGroupName}`.toLowerCase();
  return buildProductMatchTokens(row).some((token) => haystack.includes(token));
}

async function fetchKeywordAds(
  client: LingxingClient,
  store: StoreConfig,
  row: DailyLogRow,
  adRange: AdAnalysisRange,
): Promise<{ records: KeywordAdRecord[]; fetchedCount: number; errorMessage: string }> {
  if (!store.advertiserId) {
    return { records: [], fetchedCount: 0, errorMessage: "advertiserId为空，跳过关键词广告诊断数据" };
  }

  const records: KeywordAdRecord[] = [];
  let fetchedCount = 0;
  try {
    for (let pageNum = 1; pageNum <= AD_MAX_PAGES; pageNum += 1) {
      const response = await client.request<unknown>({
        method: "POST",
        path: WALMART_SP_KEYWORD_PATH,
        params: {
          advertiserIds: [store.advertiserId],
          campaignType: ["sponsoredProducts-manual"],
          startDate: adRange.startDate,
          endDate: adRange.endDate,
          pageNum,
          pageSize: AD_PAGE_SIZE,
          paging: true,
        },
        timeoutMs: LINGXING_TIMEOUT_MS,
      });
      const pageItems = extractDataArray(response.data);
      fetchedCount += pageItems.length;

      for (const item of pageItems) {
        if (!item || typeof item !== "object") {
          continue;
        }
        const normalized = normalizeKeywordRecord(item as Record<string, unknown>);
        if (keywordRecordMatchesProduct(normalized, row)) {
          normalized.ad.adDateRange = adRange.label;
          records.push(normalized.ad);
        }
      }

      const total = extractTotal(response.data);
      if (pageItems.length < AD_PAGE_SIZE || (total > 0 && fetchedCount >= total)) {
        break;
      }
    }
  } catch (error) {
    return {
      records: [],
      fetchedCount,
      errorMessage: error instanceof Error ? error.message : String(error),
    };
  }

  records.sort((a, b) => b.adSpend - a.adSpend);
  return { records: records.slice(0, 30), fetchedCount, errorMessage: "" };
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

interface StoreKeywordData {
  byItemId: Map<string, KeywordAdRecord[]>;
  allRecords: KeywordAdRecord[];
  fetchedCount: number;
}

async function fetchAllKeywordAdsForStore(
  client: LingxingClient,
  store: StoreConfig,
  adRange: AdAnalysisRange,
): Promise<StoreKeywordData> {
  if (!store.advertiserId) {
    return { byItemId: new Map(), allRecords: [], fetchedCount: 0 };
  }
  const allRecords: KeywordAdRecord[] = [];
  const byItemId = new Map<string, KeywordAdRecord[]>();
  let fetchedCount = 0;
  try {
    for (let pageNum = 1; pageNum <= AD_MAX_PAGES; pageNum += 1) {
      const response = await client.request<unknown>({
        method: "POST",
        path: WALMART_SP_KEYWORD_PATH,
        params: {
          advertiserIds: [store.advertiserId],
          campaignType: ["sponsoredProducts-manual"],
          startDate: adRange.startDate,
          endDate: adRange.endDate,
          pageNum,
          pageSize: AD_PAGE_SIZE,
          paging: true,
        },
        timeoutMs: LINGXING_TIMEOUT_MS,
      });
      const pageItems = extractDataArray(response.data);
      fetchedCount += pageItems.length;
      for (const item of pageItems) {
        if (!item || typeof item !== "object") {
          continue;
        }
        const normalized = normalizeKeywordRecord(item as Record<string, unknown>);
        normalized.ad.adDateRange = adRange.label;
        allRecords.push(normalized.ad);
        if (normalized.itemId) {
          const list = byItemId.get(normalized.itemId) ?? [];
          list.push(normalized.ad);
          byItemId.set(normalized.itemId, list);
        }
      }
      if (pageItems.length < AD_PAGE_SIZE) {
        break;
      }
    }
  } catch (error) {
    console.log(
      `${store.storeName} 关键词广告预拉取失败: ${error instanceof Error ? error.message : String(error)}`,
    );
  }
  console.log(
    `${store.storeName} 关键词广告预拉取完成: 记录数=${fetchedCount}，商品数=${byItemId.size}`,
  );
  return { byItemId, allRecords, fetchedCount };
}

function getKeywordAdsFromStoreCache(row: DailyLogRow, storeData: StoreKeywordData | undefined): KeywordAdRecord[] {
  if (!storeData) {
    return [];
  }
  const exact = storeData.byItemId.get(row.itemId);
  if (exact && exact.length > 0) {
    return exact.slice(0, 30);
  }
  const tokens = buildProductMatchTokens(row);
  return storeData.allRecords
    .filter((record) => {
      const haystack = `${record.campaignName} ${record.adGroupName}`.toLowerCase();
      return tokens.some((token) => haystack.includes(token));
    })
    .slice(0, 30);
}

interface BatchItemInput {
  row: DailyLogRow;
  recent: RecentMetric | undefined;
  daily: DailyMetric | undefined;
  manualKeywordAds: KeywordAdRecord[];
  autoSearchTermAds: KeywordAdRecord[];
  triggerReason: string;
}

async function callAiBatch(input: {
  batchData: BatchItemInput[];
  aiConfig: AiDiagnosisConfig;
  adRange: AdAnalysisRange;
}): Promise<Map<string, DiagnosisText>> {
  const baseUrl = readAiEnv("BASE_URL").replace(/\/$/, "");
  const model = readAiEnv("MODEL");
  const apiKey = readAiEnv("API_KEY");

  const itemsPayload = input.batchData.map((item) => ({
    itemId: item.row.itemId,
    store: item.row.storeName,
    msku: item.row.msku,
    owner: item.row.owner,
    productLevel: item.row.productLevel,
    triggerReason: item.triggerReason,
    recent5Days: item.recent ?? null,
    daily: item.daily ?? null,
    manualKeywordAds: item.manualKeywordAds,
    autoSearchTermAds: item.autoSearchTermAds,
    adAnalysisDateRange: input.adRange.label,
  }));

  const prompt =
    `${input.aiConfig.systemPrompt}\n\n` +
    `以下是${itemsPayload.length}个商品的广告和运营数据，请逐一分析并返回诊断结论。\n\n` +
    `输出格式（严格JSON，不含Markdown代码块）：\n` +
    `{"results":[{"itemId":"xxx","productDataIssue":"...","solution":"..."}]}\n\n` +
    `分析规则：\n${input.aiConfig.keywordAnalysisRules}\n\n` +
    `禁止事项：\n${input.aiConfig.forbiddenActions}\n\n` +
    `硬性要求：\n` +
    `1. results数组中每项必须包含 itemId、productDataIssue、solution 三个字段。\n` +
    `2. 如果某个itemId无法分析，直接从results中省略该条，不要返回错误占位。\n` +
    `3. 手动广告必须点名 Campaign、Ad Group、关键词、匹配类型；manualKeywordAds为空时写"手动广告暂无匹配关键词数据"。\n` +
    `4. 自动广告必须点名搜索词；autoSearchTermAds为空时写"自动广告暂无匹配搜索词数据"。\n` +
    `5. 单字段不超过220字，中文，具体可执行。\n` +
    `6. 广告分析范围：${input.adRange.label}。\n\n` +
    `商品数据：\n` +
    JSON.stringify(itemsPayload, null, 2);

  const response = await axios.post(
    `${baseUrl}/chat/completions`,
    {
      model,
      messages: [
        { role: "system", content: input.aiConfig.systemPrompt },
        { role: "user", content: prompt },
      ],
      temperature: 0.2,
    },
    {
      timeout: AI_TIMEOUT_MS,
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${apiKey}`,
      },
    },
  );

  const content = normalizeText(response.data?.choices?.[0]?.message?.content);
  if (!content) {
    throw new Error("AI批量返回为空");
  }

  const jsonText = content
    .replace(/^```json\s*/i, "")
    .replace(/^```\s*/i, "")
    .replace(/```$/i, "")
    .trim();
  const parsed = JSON.parse(jsonText) as { results?: unknown[] };
  const resultMap = new Map<string, DiagnosisText>();

  for (const item of parsed.results ?? []) {
    if (!item || typeof item !== "object") {
      continue;
    }
    const record = item as Record<string, unknown>;
    const itemId = normalizeText(record.itemId);
    const productIssue = normalizeText(record.productDataIssue);
    const solution = normalizeText(record.solution);
    if (itemId && productIssue && solution) {
      resultMap.set(itemId, { productIssue, solution });
    }
  }

  return resultMap;
}

function readAiEnv(name: "BASE_URL" | "MODEL" | "API_KEY"): string {
  const primaryName = `AI_${name}`;
  const legacyName = `OPENCLAW_AI_${name}`;
  const value = normalizeText(process.env[primaryName] || process.env[legacyName]);
  if (!value) {
    throw new Error(`Missing required environment variable: ${primaryName}`);
  }
  return value;
}

function maskSecret(value: string): string {
  return value.length <= 8 ? "****" : `${value.slice(0, 4)}...${value.slice(-4)}`;
}

/**
 * 写占位提示（仅写产品数据问题+解决意见，不更新诊断记录）
 * 用于：整批AI失败、AI未返回结果、AI开关关闭
 * 不写诊断记录 → 下次运行时仍会重新触发诊断
 */
function writeDiagnosisPlaceholder(options: {
  writer: FeishuSheetWriter;
  headerMap: HeaderMap;
  row: DailyLogRow;
  productIssue: string;
  solution: string;
  dryRun: boolean;
  confirmWrite: boolean;
}): void {
  options.writer.writeCells({
    spreadsheetToken: currentReport.spreadsheetToken,
    sheetId: currentReport.sheets[DAILY_LOG_SHEET_NAME],
    sheetName: DAILY_LOG_SHEET_NAME,
    range:
      `${columnName(options.headerMap.productIssue)}${options.row.rowNumber}:` +
      `${columnName(options.headerMap.solution)}${options.row.rowNumber}`,
    rows: [[options.productIssue, options.solution]],
    dryRun: options.dryRun,
    confirmWrite: options.confirmWrite,
    allowOverwrite: true,
  });
}

function writeDiagnosisResult(options: {
  writer: FeishuSheetWriter;
  headerMap: HeaderMap;
  row: DailyLogRow;
  productIssue: string;
  solution: string;
  diagnosisRecord: string;
  dryRun: boolean;
  confirmWrite: boolean;
}): void {
  options.writer.writeCells({
    spreadsheetToken: currentReport.spreadsheetToken,
    sheetId: currentReport.sheets[DAILY_LOG_SHEET_NAME],
    sheetName: DAILY_LOG_SHEET_NAME,
    range:
      `${columnName(options.headerMap.productIssue)}${options.row.rowNumber}:` +
      `${columnName(options.headerMap.solution)}${options.row.rowNumber}`,
    rows: [[options.productIssue, options.solution]],
    dryRun: options.dryRun,
    confirmWrite: options.confirmWrite,
    allowOverwrite: true,
  });

  if (options.headerMap.diagnosisRecord !== undefined) {
    const column = columnName(options.headerMap.diagnosisRecord);
    options.writer.writeCells({
      spreadsheetToken: currentReport.spreadsheetToken,
      sheetId: currentReport.sheets[DAILY_LOG_SHEET_NAME],
      sheetName: DAILY_LOG_SHEET_NAME,
      range: `${column}${options.row.rowNumber}:${column}${options.row.rowNumber}`,
      rows: [[options.diagnosisRecord]],
      dryRun: options.dryRun,
      confirmWrite: options.confirmWrite,
      allowOverwrite: true,
    });
  }
}

function writeDiagnosisRecordOnly(options: {
  writer: FeishuSheetWriter;
  headerMap: HeaderMap;
  row: DailyLogRow;
  diagnosisRecord: string;
  dryRun: boolean;
  confirmWrite: boolean;
}): void {
  if (options.headerMap.diagnosisRecord === undefined) return;
  const column = columnName(options.headerMap.diagnosisRecord);
  options.writer.writeCells({
    spreadsheetToken: currentReport.spreadsheetToken,
    sheetId: currentReport.sheets[DAILY_LOG_SHEET_NAME],
    sheetName: DAILY_LOG_SHEET_NAME,
    range: `${column}${options.row.rowNumber}:${column}${options.row.rowNumber}`,
    rows: [[options.diagnosisRecord]],
    dryRun: options.dryRun,
    confirmWrite: options.confirmWrite,
    allowOverwrite: true,
  });
}

async function callOpenClawCompatibleAi(input: {
  row: DailyLogRow;
  recent?: RecentMetric;
  daily?: DailyMetric;
  manualKeywordAds: KeywordAdRecord[];
  autoSearchTermAds: KeywordAdRecord[];
  triggerReason: string;
  aiConfig: AiDiagnosisConfig;
  adRange: AdAnalysisRange;
}): Promise<DiagnosisText> {
  const baseUrl = readAiEnv("BASE_URL").replace(/\/$/, "");
  const model = readAiEnv("MODEL");
  const apiKey = readAiEnv("API_KEY");

  const prompt =
    `输出格式:\n${input.aiConfig.outputFormat}\n\n` +
    `关键词分析规则:\n${input.aiConfig.keywordAnalysisRules}\n\n` +
    `禁止事项:\n${input.aiConfig.forbiddenActions}\n\n` +
    `硬性要求:\n` +
    `1. 只返回 JSON，不要 Markdown。\n` +
    `2. JSON字段必须是 productDataIssue, solution。\n` +
    `3. manualKeywordAds=领星手动广告关键词；autoSearchTermAds=飞书自动广告搜索词。\n` +
    `4. 手动广告必须点名 Campaign、Ad Group、关键词、匹配类型；为空则写”手动广告暂无匹配关键词数据”。\n` +
    `5. 自动广告必须点名搜索词；为空则写”自动广告暂无匹配搜索词数据”。\n` +
    `6. keyword为空时写”接口未返回关键词文本”，不写”空关键词”。\n` +
    `7. 广告数据范围：${input.adRange.label}。\n` +
    `8. 库存为0或偏低时，广告动作避免盲目放量。\n` +
    `9. 中文，具体可执行，单字段不超过220字。\n\n` +
    `诊断依据:\n` +
    JSON.stringify(
      {
        date: input.row.date,
        store: input.row.storeName,
        itemId: input.row.itemId,
        msku: input.row.msku,
        owner: input.row.owner,
        productLevel: input.row.productLevel,
        triggerReason: input.triggerReason,
        recent5Days: input.recent ?? null,
        daily: input.daily ?? null,
        manualKeywordAds: input.manualKeywordAds,
        autoSearchTermAds: input.autoSearchTermAds,
      },
      null,
      2,
    );

  const response = await axios.post(
    `${baseUrl}/chat/completions`,
    {
      model,
      messages: [
        { role: "system", content: input.aiConfig.systemPrompt },
        { role: "user", content: prompt },
      ],
      temperature: 0.2,
    },
    {
      timeout: AI_TIMEOUT_MS,
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${apiKey}`,
      },
    },
  );

  const content = normalizeText(response.data?.choices?.[0]?.message?.content);
  if (!content) {
    throw new Error("AI返回为空");
  }

  const jsonText = content.replace(/^```json\s*/i, "").replace(/^```\s*/i, "").replace(/```$/i, "").trim();
  const parsed = JSON.parse(jsonText) as { productDataIssue?: unknown; solution?: unknown };
  const productIssue = normalizeText(parsed.productDataIssue);
  const solution = normalizeText(parsed.solution);
  if (!productIssue || !solution) {
    throw new Error("AI返回JSON缺少 productDataIssue 或 solution");
  }
  return { productIssue, solution };
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
  const targetItemId = normalizeText(getArg("item-id"));
  const targetOwner = normalizeText(getArg("owner"));
  const limitArg = parseInt(getArg("limit"), 10);
  const triggerLimit = Number.isFinite(limitArg) && limitArg > 0 ? limitArg : 0;
  const forceRun = process.argv.includes("--force");
  const aiEnabled = isAiEnabled();
  const aiBaseUrl = normalizeText(process.env.AI_BASE_URL || process.env.OPENCLAW_AI_BASE_URL);
  const aiModel = normalizeText(process.env.AI_MODEL || process.env.OPENCLAW_AI_MODEL);
  const aiApiKey = normalizeText(process.env.AI_API_KEY || process.env.OPENCLAW_AI_API_KEY);
  const writer = new FeishuSheetWriter();
  const logger = new TableOperationLogger(writer, {
    spreadsheetToken: currentReport.spreadsheetToken,
    logSheetId: currentReport.sheets[LOG_SHEET_NAME],
    dryRun,
    confirmWrite,
  });
  const client = new LingxingClient(loadConfig());
  let aiConfig: AiDiagnosisConfig = { ...DEFAULT_AI_DIAGNOSIS_CONFIG, raw: {} };
  let adRange: AdAnalysisRange = buildAdAnalysisRange(dataDate, aiConfig);

  let totalRows = 0;
  let triggerAiCount = 0;
  let skippedNoNeedCount = 0;
  let frequencySkippedCount = 0;
  let zeroStockSkippedCount = 0;
  let aiSuccessCount = 0;
  let aiFailureCount = 0;
  let updatedCount = 0;
  let noDiagnosisWriteCount = 0;
  let keywordRecordCount = 0;
  let manualKeywordRecordCount = 0;
  let autoSearchTermRecordCount = 0;
  let status = dryRun ? "dry-run" : "success";
  let errorMessage = "";
  let logSuccess = false;
  const aiErrors: string[] = [];

  console.log("每日运营跟进日志 AI 诊断");
  console.log(`运行ID: ${runId}`);
  console.log(`写入模式: ${confirmWrite ? "confirm-write" : "dry-run"}`);
  console.log(`数据日期: ${dataDate}`);
  console.log(`单品过滤: ${targetItemId || "未启用"}`);
  console.log(`负责人过滤: ${targetOwner || "未启用"}`);
  console.log(`强制重跑=${forceRun}`);
  console.log(`AI开关=${aiEnabled}`);
  console.log(`AI_BASE_URL=${aiBaseUrl || "未配置"}`);
  console.log(`AI_MODEL=${aiModel || "未配置"}`);
  console.log(`AI_API_KEY=${aiApiKey ? maskSecret(aiApiKey) : "未配置"}`);
  console.log("判断来源: 每日运营跟进日志产品等级 + 近期利润与广告近5天广告占比 + 当日数据WFS可售库存");
  console.log("写回字段: 产品数据问题、解决意见、AI诊断记录");
  console.log("写入节奏: 每个ITEMID诊断完成后立即写回一组");

  try {
    aiConfig = readAiDiagnosisConfig(writer);
    adRange = buildAdAnalysisRange(dataDate, aiConfig);
    console.log(`广告分析日期范围: ${adRange.label}`);

    const dailyLogs = readDailyLogRows(writer, dataDate);
    const recentMap = readRecentMetricMap(writer);
    const dailyMetricMap = readDailyMetricMap(writer, dataDate);
    const autoAdSearchTermResult = readAutoAdSearchTermMap(writer, adRange);
    const targetRows = dailyLogs.rows.filter((row) => {
      if (targetItemId && row.itemId !== targetItemId) {
        return false;
      }
      if (targetOwner && row.owner !== targetOwner) {
        return false;
      }
      return true;
    });
    if (targetItemId && targetRows.length === 0) {
      throw new Error(`每日运营跟进日志中未找到 ${dataDate} / ItemID=${targetItemId}`);
    }
    if (targetOwner && targetRows.length === 0) {
      throw new Error(`每日运营跟进日志中未找到 ${dataDate} / 负责人=${targetOwner}`);
    }

    totalRows = targetRows.length;
    console.log(`每日运营跟进日志匹配行数: ${totalRows}`);
    console.log(`近期利润与广告可匹配商品数: ${recentMap.size}`);
    console.log(`当日数据可匹配商品数: ${dailyMetricMap.size}`);
    console.log(
      `自动广告搜索词可匹配商品数: ${autoAdSearchTermResult.map.size}（配置=${autoAdSearchTermResult.sheetConfigured ? "是" : "否"}）`,
    );

    // 第一步：筛选需要触发 AI 的行
    const triggerRows: Array<{ row: DailyLogRow; decision: { shouldRun: boolean; reason: string } }> = [];
    for (const row of targetRows) {
      const itemKey = buildItemKey(row.storeName, row.itemId);
      const recent = recentMap.get(itemKey);
      const daily = dailyMetricMap.get(itemKey);
      const decision = shouldDiagnose(row, recent, daily);

      const nextDiagnosisDate = parseNextDiagnosisDate(row.diagnosisRecord);
      if (!forceRun && !targetItemId && nextDiagnosisDate && nextDiagnosisDate > dataDate) {
        skippedNoNeedCount += 1;
        frequencySkippedCount += 1;
        continue;
      }
      if (!decision.shouldRun) {
        skippedNoNeedCount += 1;
        if (decision.reason.includes("库存为0")) {
          zeroStockSkippedCount += 1;
        }
        // 无需诊断但记录为空时，写入简要状态，避免列空白
        if (
          dailyLogs.headerMap.diagnosisRecord !== undefined &&
          !row.diagnosisRecord &&
          confirmWrite &&
          !dryRun
        ) {
          const intervalDays = decision.reason.includes("库存为0")
            ? 1
            : getDiagnosisIntervalDays(row.productLevel, aiConfig);
          const nextDate = addDays(dataDate, intervalDays);
          writeDiagnosisRecordOnly({
            writer,
            headerMap: dailyLogs.headerMap,
            row,
            diagnosisRecord: `今日无需诊断\n下次AI诊断日期=${nextDate}`,
            dryRun,
            confirmWrite,
          });
          noDiagnosisWriteCount += 1;
          updatedCount += 1;
        }
        continue;
      }
      triggerAiCount += 1;
      triggerRows.push({ row, decision });
    }

    // 限制处理数量（--limit=N）
    if (triggerLimit > 0 && triggerRows.length > triggerLimit) {
      console.log(`[limit] 触发行 ${triggerRows.length} 条，限制处理前 ${triggerLimit} 条`);
      triggerRows.splice(triggerLimit);
    }

    if (!aiEnabled && !dryRun && confirmWrite && triggerRows.length > 0) {
      // AI开关关闭时，给所有触发行写提示
      console.log(`AI开关已关闭，给 ${triggerRows.length} 个触发行写入占位提示`);
      for (const { row } of triggerRows) {
        writeDiagnosisPlaceholder({
          writer,
          headerMap: dailyLogs.headerMap,
          row,
          productIssue: "AI诊断未启用",
          solution: "请联系管理员开启ENABLE_AI_DIAGNOSIS",
          dryRun,
          confirmWrite,
        });
        updatedCount += 1;
      }
    }

    if (!aiEnabled || dryRun) {
      console.log(`AI开关=${aiEnabled}，写入模式=${dryRun ? "dry-run" : "confirm-write"}，跳过AI调用`);
    } else {
      // 第二步：每店预拉取关键词广告数据（每店只拉一次）
      const storeNames = new Set(triggerRows.map((item) => item.row.storeName));
      const storeKeywordCache = new Map<string, StoreKeywordData>();
      for (const storeName of storeNames) {
        const store = storeConfigByName(storeName);
        if (store) {
          storeKeywordCache.set(storeName, await fetchAllKeywordAdsForStore(client, store, adRange));
        }
      }

      // 第三步：按每 AI_BATCH_SIZE 个分批处理
      for (let batchStart = 0; batchStart < triggerRows.length; batchStart += AI_BATCH_SIZE) {
        const batch = triggerRows.slice(batchStart, batchStart + AI_BATCH_SIZE);
        const batchIndex = Math.floor(batchStart / AI_BATCH_SIZE) + 1;
        const batchLabel = `批次${batchIndex}(${batchStart + 1}~${batchStart + batch.length})`;

        // 组装每个商品的数据
        const batchData: BatchItemInput[] = batch.map((item) => {
          const itemKey = buildItemKey(item.row.storeName, item.row.itemId);
          const manualKeywordAds = getKeywordAdsFromStoreCache(
            item.row,
            storeKeywordCache.get(item.row.storeName),
          );
          const autoSearchTermAds = autoAdSearchTermResult.map.get(item.row.itemId) ?? [];
          manualKeywordRecordCount += manualKeywordAds.length;
          autoSearchTermRecordCount += autoSearchTermAds.length;
          keywordRecordCount += manualKeywordAds.length + autoSearchTermAds.length;
          return {
            row: item.row,
            recent: recentMap.get(itemKey),
            daily: dailyMetricMap.get(itemKey),
            manualKeywordAds,
            autoSearchTermAds,
            triggerReason: item.decision.reason,
          };
        });

        // 逐条调用 AI（单条失败不影响其他条）
        for (const { row } of batchData) {
          let diagnosis: DiagnosisText | null = null;
          const itemKey = buildItemKey(row.storeName, row.itemId);
          const itemManualAds = getKeywordAdsFromStoreCache(row, storeKeywordCache.get(row.storeName));
          const itemAutoAds = autoAdSearchTermResult.map.get(row.itemId) ?? [];
          try {
            diagnosis = await callOpenClawCompatibleAi({
              row,
              recent: recentMap.get(itemKey),
              daily: dailyMetricMap.get(itemKey),
              manualKeywordAds: itemManualAds,
              autoSearchTermAds: itemAutoAds,
              triggerReason: triggerRows.find((t) => t.row === row)?.decision.reason ?? "",
              aiConfig,
              adRange,
            });
            aiSuccessCount += 1;
            console.log(`${batchLabel}: ${row.itemId} AI调用成功`);
          } catch (error) {
            const reason = error instanceof Error ? error.message : String(error);
            aiFailureCount += 1;
            aiErrors.push(`${row.itemId}: ${reason}`);
            console.log(`${batchLabel}: ${row.itemId} AI调用失败 - ${reason}`);
            writeDiagnosisPlaceholder({
              writer,
              headerMap: dailyLogs.headerMap,
              row,
              productIssue: "AI调用失败",
              solution: "请检查AI接口，下次运行时会重新诊断",
              dryRun,
              confirmWrite,
            });
            updatedCount += 1;
            continue;
          }

          // diagnosis 已确认非空（失败时 catch 已处理）
          const nextDate = addDays(dataDate, getDiagnosisIntervalDays(row.productLevel, aiConfig));
          writeDiagnosisResult({
            writer,
            headerMap: dailyLogs.headerMap,
            row,
            productIssue: diagnosis.productIssue,
            solution: diagnosis.solution,
            diagnosisRecord: formatDiagnosisRecord({
              dataDate,
              nextDate,
              status: "已完成",
              runId,
              adRange,
            }),
            dryRun,
            confirmWrite,
          });
          updatedCount += 1;

          // 调用间限速，避免 API 频控
          await sleep(500);
        }
      }
    }

    console.log("");
    console.log("AI诊断汇总:");
    console.log(`每日运营跟进日志行数: ${totalRows}`);
    console.log(`触发AI数量: ${triggerAiCount}`);
    console.log(`无需诊断跳过数量: ${skippedNoNeedCount}`);
    console.log(`未到下次诊断日期跳过数量: ${frequencySkippedCount}`);
    console.log(`其中库存为0跳过数量: ${zeroStockSkippedCount}`);
    console.log(`关键词广告记录数: ${keywordRecordCount}`);
    console.log(`手动广告关键词记录数: ${manualKeywordRecordCount}`);
    console.log(`自动广告搜索词记录数: ${autoSearchTermRecordCount}`);
    console.log(`AI成功数: ${aiSuccessCount}`);
    console.log(`AI失败数: ${aiFailureCount}`);
    console.log(`写回每日运营跟进日志数量: ${updatedCount}`);
    console.log(`其中无需诊断写入数量: ${noDiagnosisWriteCount}`);
  } catch (error) {
    status = "failed";
    errorMessage = error instanceof Error ? error.message : String(error);
    console.log(`AI诊断执行失败: ${errorMessage}`);
  } finally {
    try {
      logger.append({
        executedAt: new Date().toISOString(),
        taskName: TASK_NAME,
        targetSheet: DAILY_LOG_SHEET_NAME,
        operationType: dryRun ? "dry-run" : "ai_diagnosis",
        dataSource:
          `${DAILY_LOG_SHEET_NAME}+${RECENT_PROFIT_SHEET_NAME}+${DAILY_DATA_SHEET_NAME}+` +
          `${WALMART_SP_KEYWORD_PATH}+${AUTO_AD_SEARCH_TERM_SHEET_NAME}`,
        dateRange: dataDate,
        fetchedCount: totalRows,
        writtenCount: updatedCount,
        updatedCount,
        skippedCount: skippedNoNeedCount,
        failedCount: status === "failed" ? 1 : aiFailureCount,
        status,
        errorMessage,
        durationSeconds: Number(((Date.now() - startedAt) / 1000).toFixed(3)),
        runId,
        environment: "local",
        remark:
          `CODEX执行：每日运营跟进日志AI诊断，数据日期=${dataDate}` +
          `，AI开关=${aiEnabled}` +
          `，强制重跑=${forceRun}` +
          `，负责人过滤=${targetOwner || "未启用"}` +
          `，AI诊断配置Sheet=${currentReport.sheets[AI_CONFIG_SHEET_NAME] ?? "未配置"}` +
          `，广告分析日期范围=${adRange.label}` +
          `，判断依据=产品等级/近5天广告占比/当日库存` +
          `，触发AI数量=${triggerAiCount}` +
          `，无需诊断=${skippedNoNeedCount}` +
          `，未到下次诊断日期跳过=${frequencySkippedCount}` +
          `，库存为0跳过=${zeroStockSkippedCount}` +
          `，关键词广告记录数=${keywordRecordCount}` +
          `，手动广告关键词记录数=${manualKeywordRecordCount}` +
          `，自动广告搜索词记录数=${autoSearchTermRecordCount}` +
          `，AI成功=${aiSuccessCount}` +
          `，AI失败=${aiFailureCount}` +
          `，写回产品数据问题和解决意见=${updatedCount}` +
          (aiErrors.length > 0 ? `，AI错误=${aiErrors.slice(0, 5).join("；")}` : "") +
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
