import "dotenv/config";
import { loadConfig } from "./config";
import { LingxingClient } from "./lingxingClient";
import { STORES, StoreConfig } from "./syncDailyBaseData";

const PRODUCT_PATH = "/basicOpen/multiplatform/ads/reportProductSpList";
const KEYWORD_PATH = "/basicOpen/multiplatform/ads/reportKeywordSpList";
const FALLBACK_PRODUCT_PATH = "/basicOpen/multiplatform/ads/reportAdItemSpList";
const TARGET_ITEM_ID = "19941909440";
const TARGET_DATE = "2026-06-06";
const STORE_NAME = "CN2601-瑞盈龙盛(刘云龙）";
const PAGE_SIZE = 200;
const MAX_PAGES = 20;
const TIMEOUT_MS = 120000;

function normalizeText(value: unknown): string {
  return String(value ?? "").trim();
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

function firstText(record: Record<string, unknown>, keys: string[]): string {
  for (const key of keys) {
    const value = normalizeText(record[key]);
    if (value) {
      return value;
    }
  }
  return "";
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

function findStore(storeName: string): StoreConfig {
  const store = STORES.find((item) => item.storeName === storeName || storeName.startsWith(item.storeName));
  if (!store) {
    throw new Error(`未找到店铺配置: ${storeName}`);
  }
  return store;
}

function guessMeaning(key: string): { meaning: string; confidence: "确定" | "推测" } {
  const map: Array<{ pattern: RegExp; meaning: string; confidence: "确定" | "推测" }> = [
    { pattern: /^item(Id|_id)?$/i, meaning: "Walmart Item ID / 商品ID", confidence: "确定" },
    { pattern: /^advertiserId$/i, meaning: "广告主ID", confidence: "确定" },
    { pattern: /^campaign(Id|_id)?$/i, meaning: "广告活动ID", confidence: "确定" },
    { pattern: /^campaignName$/i, meaning: "广告活动名称", confidence: "确定" },
    { pattern: /^adGroup(Id|_id)?$/i, meaning: "广告组ID", confidence: "确定" },
    { pattern: /^adGroupName$/i, meaning: "广告组名称", confidence: "确定" },
    { pattern: /^keyword(Text)?$/i, meaning: "关键词文本", confidence: "确定" },
    { pattern: /^searchTerm$/i, meaning: "搜索词", confidence: "确定" },
    { pattern: /^target(ing)?Text$/i, meaning: "投放词/定向文本", confidence: "确定" },
    { pattern: /^matchType$/i, meaning: "匹配类型", confidence: "确定" },
    { pattern: /^numAdsShown$/i, meaning: "广告展示量", confidence: "确定" },
    { pattern: /^numAdsClicks$/i, meaning: "广告点击量", confidence: "确定" },
    { pattern: /^adCost$/i, meaning: "广告花费", confidence: "确定" },
    { pattern: /^adSales$/i, meaning: "广告销售额", confidence: "确定" },
    { pattern: /^orders?$|^conversions?$/i, meaning: "广告归因订单量/转化量", confidence: "推测" },
    { pattern: /^ctr$/i, meaning: "点击率", confidence: "确定" },
    { pattern: /^cpc$/i, meaning: "平均点击花费", confidence: "确定" },
    { pattern: /^acos$/i, meaning: "广告成本销售比", confidence: "确定" },
    { pattern: /^roas$/i, meaning: "广告投入产出比", confidence: "确定" },
    { pattern: /^sku$/i, meaning: "SKU", confidence: "推测" },
    { pattern: /^msku$/i, meaning: "MSKU", confidence: "推测" },
    { pattern: /date/i, meaning: "日期字段", confidence: "推测" },
    { pattern: /status/i, meaning: "状态字段", confidence: "推测" },
    { pattern: /name/i, meaning: "名称字段", confidence: "推测" },
    { pattern: /cost|spend/i, meaning: "费用类字段", confidence: "推测" },
    { pattern: /sales|revenue/i, meaning: "销售额类字段", confidence: "推测" },
    { pattern: /click/i, meaning: "点击类字段", confidence: "推测" },
    { pattern: /show|impression/i, meaning: "展示类字段", confidence: "推测" },
  ];

  for (const item of map) {
    if (item.pattern.test(key)) {
      return { meaning: item.meaning, confidence: item.confidence };
    }
  }
  return { meaning: "需结合文档或更多样本确认", confidence: "推测" };
}

function sortObject(value: Record<string, unknown>): Record<string, unknown> {
  return Object.fromEntries(Object.keys(value).sort().map((key) => [key, value[key]]));
}

async function fetchAllPages(
  client: LingxingClient,
  path: string,
  baseParams: Record<string, unknown>,
): Promise<{ rows: Record<string, unknown>[]; rawPages: unknown[] }> {
  const rows: Record<string, unknown>[] = [];
  const rawPages: unknown[] = [];

  for (let pageNum = 1; pageNum <= MAX_PAGES; pageNum += 1) {
    const response = await client.request<unknown>({
      method: "POST",
      path,
      params: {
        ...baseParams,
        pageNum,
        pageSize: PAGE_SIZE,
        paging: true,
      },
      timeoutMs: TIMEOUT_MS,
    });

    rawPages.push(response.data);
    const pageItems = extractDataArray(response.data);
    for (const item of pageItems) {
      if (item && typeof item === "object") {
        rows.push(item as Record<string, unknown>);
      }
    }

    const total = extractTotal(response.data);
    if (pageItems.length < PAGE_SIZE || (total > 0 && rows.length >= total)) {
      break;
    }
  }

  return { rows, rawPages };
}

function filterByItem(rows: Record<string, unknown>[], itemId: string): Record<string, unknown>[] {
  return rows.filter((record) => {
    const candidates = [
      "itemId",
      "item_id",
      "platformProductId",
      "platform_product_id",
      "productId",
    ];
    return firstText(record, candidates) === itemId;
  });
}

function summarizeFieldMap(record: Record<string, unknown>): Array<{ field: string; value: unknown; meaning: string; confidence: "确定" | "推测" }> {
  return Object.keys(record)
    .sort()
    .map((field) => {
      const guessed = guessMeaning(field);
      return {
        field,
        value: record[field],
        meaning: guessed.meaning,
        confidence: guessed.confidence,
      };
    });
}

function uniqueFieldList(rows: Record<string, unknown>[]): string[] {
  return Array.from(new Set(rows.flatMap((row) => Object.keys(row)))).sort();
}

function pickKeywordSample(rows: Record<string, unknown>[]): Record<string, unknown>[] {
  return rows
    .slice()
    .sort((a, b) => toNumber(b.adCost ?? b.cost ?? b.spend) - toNumber(a.adCost ?? a.cost ?? a.spend))
    .slice(0, 10)
    .map((row) => sortObject(row));
}

async function main(): Promise<void> {
  const store = findStore(STORE_NAME);
  if (!store.advertiserId) {
    throw new Error(`店铺 ${store.storeName} advertiserId 为空`);
  }

  const client = new LingxingClient(loadConfig());
  const baseParams = {
    advertiserIds: [store.advertiserId],
    campaignType: ["sponsoredProducts-manual", "sponsoredProducts-auto"],
    startDate: TARGET_DATE,
    endDate: TARGET_DATE,
  };

  const productAttemptPaths = [PRODUCT_PATH, FALLBACK_PRODUCT_PATH];
  let productPathUsed = "";
  let productRows: Record<string, unknown>[] = [];
  let productRawPages: unknown[] = [];
  let productError = "";

  for (const path of productAttemptPaths) {
    try {
      const result = await fetchAllPages(client, path, baseParams);
      const matched = filterByItem(result.rows, TARGET_ITEM_ID);
      if (matched.length > 0 || path === FALLBACK_PRODUCT_PATH) {
        productPathUsed = path;
        productRows = matched;
        productRawPages = result.rawPages;
        break;
      }
    } catch (error) {
      productError = error instanceof Error ? error.message : String(error);
      if (path === FALLBACK_PRODUCT_PATH) {
        throw error;
      }
    }
  }

  const productSample = productRows[0] ? sortObject(productRows[0]) : {};
  const linkHints = Array.from(new Set(productRows.flatMap((row) => [
    firstText(row, ["campaignId", "campaign_id"]),
    firstText(row, ["adGroupId", "ad_group_id"]),
    firstText(row, ["advertiserId"]),
    firstText(row, ["sku"]),
    firstText(row, ["msku"]),
  ]).filter(Boolean)));

  let keywordRows: Record<string, unknown>[] = [];
  let keywordRawPages: unknown[] = [];
  let keywordError = "";
  try {
    const result = await fetchAllPages(client, KEYWORD_PATH, baseParams);
    keywordRawPages = result.rawPages;

    const directMatched = filterByItem(result.rows, TARGET_ITEM_ID);
    if (directMatched.length > 0) {
      keywordRows = directMatched;
    } else {
      const campaignIds = new Set(productRows.map((row) => firstText(row, ["campaignId", "campaign_id"])).filter(Boolean));
      const adGroupIds = new Set(productRows.map((row) => firstText(row, ["adGroupId", "ad_group_id"])).filter(Boolean));
      const advertiserIds = new Set(productRows.map((row) => firstText(row, ["advertiserId"])).filter(Boolean));
      const skus = new Set(productRows.map((row) => firstText(row, ["sku"])).filter(Boolean));
      const mskus = new Set(productRows.map((row) => firstText(row, ["msku"])).filter(Boolean));

      keywordRows = result.rows.filter((row) => {
        const campaignId = firstText(row, ["campaignId", "campaign_id"]);
        const adGroupId = firstText(row, ["adGroupId", "ad_group_id"]);
        const advertiserId = firstText(row, ["advertiserId"]);
        const sku = firstText(row, ["sku"]);
        const msku = firstText(row, ["msku"]);
        return (
          campaignIds.has(campaignId) ||
          adGroupIds.has(adGroupId) ||
          advertiserIds.has(advertiserId) ||
          skus.has(sku) ||
          mskus.has(msku)
        );
      });
    }
  } catch (error) {
    keywordError = error instanceof Error ? error.message : String(error);
  }

  const productFieldRows = productRows.length > 0 ? summarizeFieldMap(productRows[0]) : [];
  const keywordFieldRows = keywordRows.length > 0 ? summarizeFieldMap(keywordRows[0]) : [];
  const productFields = uniqueFieldList(productRows);
  const keywordFields = uniqueFieldList(keywordRows);
  const productOnlyFields = productFields.filter((field) => !keywordFields.includes(field));
  const keywordOnlyFields = keywordFields.filter((field) => !productFields.includes(field));
  const sharedFields = productFields.filter((field) => keywordFields.includes(field));

  const result = {
    meta: {
      storeName: store.storeName,
      advertiserId: store.advertiserId,
      targetItemId: TARGET_ITEM_ID,
      targetDate: TARGET_DATE,
      productPathUsed,
      productError,
      keywordError,
      productMatchedCount: productRows.length,
      keywordMatchedCount: keywordRows.length,
      productRawPageCount: productRawPages.length,
      keywordRawPageCount: keywordRawPages.length,
      linkHints,
      validationSample: productRows[0]
        ? {
            adCost: productRows[0].adCost,
            adSales: productRows[0].adSales,
            numAdsClicks: productRows[0].numAdsClicks,
            numAdsShown: productRows[0].numAdsShown,
          }
        : null,
    },
    product: {
      fieldList: productFields,
      firstMatchedRecord: productSample,
      annotatedFields: productFieldRows,
    },
    keyword: {
      fieldList: keywordFields,
      firstMatchedRecord: keywordRows[0] ? sortObject(keywordRows[0]) : {},
      annotatedFields: keywordFieldRows,
      samples: pickKeywordSample(keywordRows),
    },
    diff: {
      sharedFields,
      productOnlyFields,
      keywordOnlyFields,
    },
  };

  console.log(JSON.stringify(result, null, 2));
}

main().catch((error) => {
  console.error(error instanceof Error ? error.stack || error.message : String(error));
  process.exit(1);
});
