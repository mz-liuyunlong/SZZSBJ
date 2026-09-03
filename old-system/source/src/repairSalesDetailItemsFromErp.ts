import currentReport from "../config/currentReportFieldMapping.json";
import { loadConfig } from "./config";
import { FeishuSheetWriter, SheetRow } from "./feishuSheetWriter";
import { LingxingClient } from "./lingxingClient";
import { STORES, StoreConfig } from "./syncDailyBaseData";
import { TableOperationLogger } from "./tableOperationLogger";

const TASK_NAME = "销售明细指定商品修复";
const DETAIL_SHEET_NAME = "5月销售明细_复盘";
const LOG_SHEET_NAME = "表格操作日志";
const SALE_STAT_PATH = "/basicOpen/platformStatisticsV2/saleStat/pageList";
const WALMART_SP_AD_PATH = "/basicOpen/multiplatform/ads/reportAdItemSpList";
const READ_BATCH_SIZE = 500;
const TIMEOUT_MS = 120000;
const PAGE_LENGTH = 200;
const MAX_SALE_PAGES = 10;
const MAX_AD_PAGES = 20;
const AMOUNT_TOLERANCE = 0.01;
const SHEETS = currentReport.sheets as Record<string, string>;

interface DetailRowRef {
  rowNumber: number;
  row: SheetRow;
  date: string;
  storeName: string;
  itemId: string;
  currentSalesQty: number;
  currentSalesAmount: number;
  currentAdCost: number;
}

interface ErpMetrics {
  salesQty: number;
  salesAmount: number;
  adCost: number;
}

interface RepairPlan {
  target: DetailRowRef;
  erp: ErpMetrics;
  needsUpdate: boolean;
  reason: string;
}

function getArg(name: string, defaultValue = ""): string {
  const prefix = `--${name}=`;
  const arg = process.argv.find((item) => item.startsWith(prefix));
  return arg ? arg.slice(prefix.length) : defaultValue;
}

function hasFlag(name: string): boolean {
  return process.argv.includes(`--${name}`);
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
  const text = normalizeText(value).replace(/,/g, "").replace(/%$/, "");
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
      // Plain API string.
    }
    return [text];
  }
  const text = normalizeText(value);
  return text ? [text] : [];
}

function getItemIds(): string[] {
  const raw = getArg("item-ids") || getArg("item-id");
  return raw.split(",").map((item) => item.trim()).filter(Boolean);
}

function addDays(dateText: string, days: number): string {
  const [year, month, day] = dateText.split("-").map(Number);
  const date = new Date(Date.UTC(year, month - 1, day));
  date.setUTCDate(date.getUTCDate() + days);
  return date.toISOString().slice(0, 10);
}

function buildDateRange(startDate: string, endDate: string): string[] {
  const dates: string[] = [];
  let current = startDate;
  while (current <= endDate) {
    dates.push(current);
    current = addDays(current, 1);
  }
  return dates;
}

function getRunId(): string {
  const timestamp = new Date().toISOString().replace(/[-:.TZ]/g, "").slice(0, 17);
  return `run_${timestamp}_${Math.random().toString(36).slice(2, 8)}`;
}

function readDetailRows(writer: FeishuSheetWriter): DetailRowRef[] {
  const rowRefs: DetailRowRef[] = [];
  const rowCount = writer.getRowCount({
    spreadsheetToken: currentReport.spreadsheetToken,
    sheetId: SHEETS[DETAIL_SHEET_NAME],
    sheetName: DETAIL_SHEET_NAME,
  });

  for (let startRow = 2; startRow <= rowCount; startRow += READ_BATCH_SIZE) {
    const endRow = Math.min(startRow + READ_BATCH_SIZE - 1, rowCount);
    const rows = writer.readValues({
      spreadsheetToken: currentReport.spreadsheetToken,
      sheetId: SHEETS[DETAIL_SHEET_NAME],
      range: `A${startRow}:L${endRow}`,
    });

    rows.forEach((row, index) => {
      const date = normalizeText(row[0]).slice(0, 10);
      const storeName = normalizeText(row[1]);
      const itemId = normalizeText(row[2]);
      if (!date || !storeName || !itemId) {
        return;
      }
      rowRefs.push({
        rowNumber: startRow + index,
        row,
        date,
        storeName,
        itemId,
        currentSalesQty: toNumber(row[9]),
        currentSalesAmount: toNumber(row[10]),
        currentAdCost: toNumber(row[11]),
      });
    });
  }

  return rowRefs;
}

function filterTargets(rows: DetailRowRef[], dates: string[], itemIds: string[], storeName: string): DetailRowRef[] {
  const dateSet = new Set(dates);
  const itemIdSet = new Set(itemIds);
  return rows.filter((row) => {
    const sameDate = dateSet.has(row.date);
    const sameItem = itemIdSet.has(row.itemId);
    const sameStore = storeName ? row.storeName === storeName : true;
    return sameDate && sameItem && sameStore;
  });
}

function findStore(storeName: string): StoreConfig {
  const store = STORES.find((item) => item.storeName === storeName);
  if (!store) {
    throw new Error(`未找到店铺配置：${storeName}`);
  }
  return store;
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
  date: string;
  resultType: "1" | "3";
}): Promise<number> {
  let total = 0;
  for (let page = 1; page <= MAX_SALE_PAGES; page += 1) {
    const response = await options.client.request<unknown>({
      method: "POST",
      path: SALE_STAT_PATH,
      params: {
        start_date: options.date,
        end_date: options.date,
        result_type: options.resultType,
        date_unit: "4",
        data_type: "1",
        page,
        length: PAGE_LENGTH,
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
    if (rows.length < PAGE_LENGTH) {
      break;
    }
  }
  return Number(total.toFixed(2));
}

async function fetchAdCost(options: {
  client: LingxingClient;
  store: StoreConfig;
  itemId: string;
  date: string;
}): Promise<number> {
  if (!options.store.advertiserId) {
    return 0;
  }

  let total = 0;
  for (let pageNum = 1; pageNum <= MAX_AD_PAGES; pageNum += 1) {
    const response = await options.client.request<unknown>({
      method: "POST",
      path: WALMART_SP_AD_PATH,
      params: {
        advertiserIds: [options.store.advertiserId],
        campaignType: ["sponsoredProducts-manual", "sponsoredProducts-auto"],
        startDate: options.date,
        endDate: options.date,
        pageNum,
        pageSize: PAGE_LENGTH,
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
    if (rows.length < PAGE_LENGTH) {
      break;
    }
  }
  return Number(total.toFixed(2));
}

async function buildRepairPlan(client: LingxingClient, target: DetailRowRef): Promise<RepairPlan> {
  const store = findStore(target.storeName);
  const salesQty = await fetchSaleMetric({
    client,
    storeId: store.storeId,
    itemId: target.itemId,
    date: target.date,
    resultType: "1",
  });
  const salesAmount = await fetchSaleMetric({
    client,
    storeId: store.storeId,
    itemId: target.itemId,
    date: target.date,
    resultType: "3",
  });
  const adCost = await fetchAdCost({
    client,
    store,
    itemId: target.itemId,
    date: target.date,
  });
  const erp = { salesQty, salesAmount, adCost };
  const qtyDiff = Math.abs(target.currentSalesQty - erp.salesQty);
  const amountDiff = Math.abs(target.currentSalesAmount - erp.salesAmount);
  const adDiff = Math.abs(target.currentAdCost - erp.adCost);
  const needsUpdate = qtyDiff > AMOUNT_TOLERANCE || amountDiff > AMOUNT_TOLERANCE || adDiff > AMOUNT_TOLERANCE;
  const reason = [
    `销量 ${target.currentSalesQty} -> ${erp.salesQty}`,
    `销售额 ${target.currentSalesAmount} -> ${erp.salesAmount}`,
    `广告费 ${target.currentAdCost} -> ${erp.adCost}`,
  ].join("；");

  return { target, erp, needsUpdate, reason };
}

function writeRepairs(writer: FeishuSheetWriter, plans: RepairPlan[], dryRun: boolean, confirmWrite: boolean): void {
  for (const plan of plans.filter((item) => item.needsUpdate)) {
    writer.writeCells({
      spreadsheetToken: currentReport.spreadsheetToken,
      sheetId: SHEETS[DETAIL_SHEET_NAME],
      sheetName: DETAIL_SHEET_NAME,
      range: `J${plan.target.rowNumber}:L${plan.target.rowNumber}`,
      rows: [[plan.erp.salesQty, plan.erp.salesAmount, plan.erp.adCost]],
      dryRun,
      confirmWrite,
      allowOverwrite: true,
    });
  }
}

async function main(): Promise<void> {
  const startedAt = Date.now();
  const runId = getRunId();
  const date = getArg("date");
  const startDate = getArg("startDate", date);
  const endDate = getArg("endDate", date);
  const itemIds = getItemIds();
  const storeName = getArg("store");
  const confirmWrite = hasFlag("confirm-write");
  const dryRun = !confirmWrite;
  const writer = new FeishuSheetWriter();
  const logger = new TableOperationLogger(writer, {
    spreadsheetToken: currentReport.spreadsheetToken,
    logSheetId: SHEETS[LOG_SHEET_NAME],
    dryRun,
    confirmWrite,
  });

  console.log("销售明细指定商品修复");
  console.log(`运行ID: ${runId}`);
  console.log(`写入模式: ${confirmWrite ? "confirm-write" : "dry-run"}`);
  console.log(`目标 Sheet: ${DETAIL_SHEET_NAME} (${SHEETS[DETAIL_SHEET_NAME]})`);
  console.log(`日期范围: ${startDate || "未指定"}~${endDate || "未指定"}`);
  console.log(`商品ID: ${itemIds.join(",") || "未指定"}`);
  console.log(`店铺过滤: ${storeName || "未启用"}`);
  console.log("修复列: J 今日销量, K 今日销售额（$）, L 广告花费（$）");

  let status = "success";
  let errorMessage = "";
  let plans: RepairPlan[] = [];

  try {
    if (!/^\d{4}-\d{2}-\d{2}$/.test(startDate) || !/^\d{4}-\d{2}-\d{2}$/.test(endDate)) {
      throw new Error("必须传入 --date=YYYY-MM-DD，或 --startDate=YYYY-MM-DD --endDate=YYYY-MM-DD");
    }
    if (startDate > endDate) {
      throw new Error("startDate 不能晚于 endDate");
    }
    if (itemIds.length === 0) {
      throw new Error("必须传入 --item-id=xxx 或 --item-ids=id1,id2");
    }

    const dates = buildDateRange(startDate, endDate);
    const detailRows = readDetailRows(writer);
    const targets = filterTargets(detailRows, dates, itemIds, storeName);
    if (targets.length === 0) {
      throw new Error(`未在 ${DETAIL_SHEET_NAME} 找到目标行`);
    }

    const client = new LingxingClient(loadConfig());
    for (const target of targets) {
      plans.push(await buildRepairPlan(client, target));
    }

    console.log("");
    console.log("修复计划:");
    console.log("行号 | 日期 | 店铺 | 商品ID | 是否需要修复 | 变化");
    for (const plan of plans) {
      console.log(
        `${plan.target.rowNumber} | ${plan.target.date} | ${plan.target.storeName} | ${plan.target.itemId} | ` +
          `${plan.needsUpdate ? "是" : "否"} | ${plan.reason}`,
      );
    }

    writeRepairs(writer, plans, dryRun, confirmWrite);
  } catch (error) {
    status = "failed";
    errorMessage = error instanceof Error ? error.message : String(error);
    console.log(`修复失败: ${errorMessage}`);
    process.exitCode = 1;
  } finally {
    const updatedCount = plans.filter((item) => item.needsUpdate).length;
    try {
      logger.append({
        executedAt: new Date().toISOString(),
        taskName: TASK_NAME,
        targetSheet: DETAIL_SHEET_NAME,
        operationType: confirmWrite ? "update" : "dry-run",
        dataSource: "领星ERP saleStat + Walmart SP广告",
        dateRange: startDate === endDate ? startDate : `${startDate}~${endDate}`,
        fetchedCount: plans.length,
        writtenCount: 0,
        updatedCount,
        skippedCount: Math.max(plans.length - updatedCount, 0),
        failedCount: status === "success" ? 0 : 1,
        status: status === "success" ? (confirmWrite ? "success" : "dry-run") : "failed",
        errorMessage,
        durationSeconds: Number(((Date.now() - startedAt) / 1000).toFixed(3)),
        runId,
        environment: "local",
        remark:
          `CODEX执行：销售明细指定商品修复，日期=${startDate === endDate ? startDate : `${startDate}~${endDate}`}，商品ID=${itemIds.join("/")}` +
          `，修复列=J/K/L，需更新行数=${updatedCount}，错误=${errorMessage || "无"}`,
      });
      console.log("日志是否写入成功: 是");
    } catch (logError) {
      console.log(`日志是否写入成功: 否，原因：${logError instanceof Error ? logError.message : String(logError)}`);
    }
  }
}

main();
