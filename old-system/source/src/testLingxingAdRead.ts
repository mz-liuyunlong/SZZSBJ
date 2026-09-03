import "dotenv/config";
import { loadConfig } from "./config";
import { LingxingClient } from "./lingxingClient";
import { STORES, StoreConfig } from "./syncDailyBaseData";

const WALMART_SP_AD_PATH = "/basicOpen/multiplatform/ads/reportAdItemSpList";
const AD_PAGE_LENGTH = 200;
const AD_MAX_PAGES = 20;
const TIMEOUT_MS = 120000;
const TARGET_ITEM_ID = "19941909440";
const STORE_NAME = "CN2601-瑞盈龙盛(刘云龙）";

interface ProductAdSummary {
  itemId: string;
  adSpend: number;
  attributedSales: number;
  clicks: number;
  impressions: number;
  acos: number;
  adRatio: number;
  rawApiSuccess: boolean;
  rawFetchedCount: number;
}

function getArg(name: string, defaultValue = ""): string {
  const prefix = `--${name}=`;
  const arg = process.argv.find((item) => item.startsWith(prefix));
  return arg ? arg.slice(prefix.length) : defaultValue;
}

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

function getChinaDateText(date = new Date()): string {
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Shanghai",
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

function firstNumber(record: Record<string, unknown>, keys: string[]): number {
  for (const key of keys) {
    const value = toNumber(record[key]);
    if (value !== 0) {
      return value;
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

async function fetchItemAdSummary(client: LingxingClient, store: StoreConfig, startDate: string, endDate: string): Promise<ProductAdSummary> {
  if (!store.advertiserId) {
    throw new Error(`店铺 ${store.storeName} advertiserId 为空`);
  }

  let fetchedCount = 0;
  let found = false;
  const summary: ProductAdSummary = {
    itemId: TARGET_ITEM_ID,
    adSpend: 0,
    attributedSales: 0,
    clicks: 0,
    impressions: 0,
    acos: 0,
    adRatio: 0,
    rawApiSuccess: true,
    rawFetchedCount: 0,
  };

  for (let pageNum = 1; pageNum <= AD_MAX_PAGES; pageNum += 1) {
    const response = await client.request<unknown>({
      method: "POST",
      path: WALMART_SP_AD_PATH,
      params: {
        advertiserIds: [store.advertiserId],
        campaignType: ["sponsoredProducts-manual", "sponsoredProducts-auto"],
        startDate,
        endDate,
        pageNum,
        pageSize: AD_PAGE_LENGTH,
        paging: true,
      },
      timeoutMs: TIMEOUT_MS,
    });

    const pageItems = extractDataArray(response.data);
    fetchedCount += pageItems.length;

    for (const item of pageItems) {
      if (!item || typeof item !== "object") {
        continue;
      }
      const record = item as Record<string, unknown>;
      const itemId = firstText(record, ["itemId", "item_id", "platformProductId", "platform_product_id", "productId"]);
      if (itemId !== TARGET_ITEM_ID) {
        continue;
      }

      found = true;
      summary.adSpend += firstNumber(record, ["adSpend", "cost", "spend"]);
      summary.attributedSales += firstNumber(record, ["attributedSales", "sales", "attributedRevenue"]);
      summary.clicks += firstNumber(record, ["clicks", "click"]);
      summary.impressions += firstNumber(record, ["impressions", "impression"]);
    }

    const total = extractTotal(response.data);
    if (pageItems.length < AD_PAGE_LENGTH || (total > 0 && fetchedCount >= total)) {
      break;
    }
  }

  summary.rawFetchedCount = fetchedCount;
  summary.acos = summary.attributedSales > 0 ? summary.adSpend / summary.attributedSales : 0;
  summary.adRatio = summary.acos;
  if (!found) {
    summary.rawApiSuccess = true;
  }
  return summary;
}

async function main(): Promise<void> {
  const endDate = getArg("endDate") || addDays(getChinaDateText(), -1);
  const startDate = getArg("startDate") || addDays(endDate, -2);
  const store = findStore(STORE_NAME);
  const client = new LingxingClient(loadConfig());

  const summary = await fetchItemAdSummary(client, store, startDate, endDate);

  console.log(JSON.stringify({
    itemId: summary.itemId,
    dateRange: `${startDate} ~ ${endDate}`,
    adSpend: Number(summary.adSpend.toFixed(2)),
    attributedSales: Number(summary.attributedSales.toFixed(2)),
    clicks: Number(summary.clicks.toFixed(0)),
    impressions: Number(summary.impressions.toFixed(0)),
    acos: `${Number((summary.acos * 100).toFixed(2))}%`,
    adRatio: `${Number((summary.adRatio * 100).toFixed(2))}%`,
    rawApiSuccess: summary.rawApiSuccess,
    rawFetchedCount: summary.rawFetchedCount,
  }, null, 2));
}

main().catch((error) => {
  console.error(error instanceof Error ? error.message : String(error));
  process.exit(1);
});
