/**
 * syncNoMovingProducts.ts - 不动销产品记录同步
 *
 * 每天 08:00（北京时间）执行：
 * 1. 读取 ItemID负责人 表获取负责人映射
 * 2. 拉取所有店铺 Walmart 商品列表（含 WFS 库存）
 * 3. 拉取近 30/14/7/3 天各商品销量
 * 4. 筛选不动销产品（近30天均值 < 1/3单/天，且 WFS 库存 > 0）
 * 5. 清空 sheet=f20boF，写入表头 + 当日数据
 *
 * dry-run（不写入）：
 *   npx ts-node src/syncNoMovingProducts.ts
 *
 * 实际写入：
 *   npx ts-node src/syncNoMovingProducts.ts --confirm-write
 */

import "dotenv/config";
import currentReport from "../config/currentReportFieldMapping.json";
import { STORES } from "./syncDailyBaseData";
import { loadConfig } from "./config";
import { FeishuSheetWriter, SheetRow } from "./feishuSheetWriter";
import { LingxingClient } from "./lingxingClient";
import { TableOperationLogger } from "./tableOperationLogger";

// ── 常量 ─────────────────────────────────────────────────────────────
const TASK_NAME = "不动销产品记录同步";
const TARGET_SHEET_NAME = "不动销产品记录";
const TARGET_SHEET_ID = "<REDACTED_FEISHU_SHEET_ID>";
const TIMEOUT_MS = 120000;
const MAX_RETRIES = 3;
const RETRY_DELAY_MS = 2000;

const WALMART_LIST_PATH = "/basicOpen/multiplatform/walmart/list";
const SALE_STAT_PATH = "/basicOpen/platformStatisticsV2/saleStat/pageList";
const PAGE_LENGTH = 20;
const WALMART_LIST_MAX_PAGES = 100;
const SALE_STAT_PAGE_LENGTH = 200;
const SALE_STAT_MAX_PAGES = 10;

// 近30天不足10单 = 均值 < 1/3单/天
const THIRTY_DAY_THRESHOLD = 10;

// 清空范围（预留足够行数）
const CLEAR_RANGE = "A1:M3000";

// 表头
const SHEET_HEADERS: string[] = [
  "记录日期", "店铺", "商品ID", "MSKU", "SKU", "品名", "负责人",
  "近30天销量", "近14天销量", "近7天销量", "近3天销量",
  "不动销状态", "WFS可售库存",
];

// ── 工具函数 ─────────────────────────────────────────────────────────
function createRunId(): string {
  return `run_${new Date().toISOString().replace(/[-:.TZ]/g, "")}_${Math.random().toString(36).slice(2, 8)}`;
}

function getShanghaiDate(daysAgo = 0): string {
  const d = new Date(Date.now() + 8 * 3600 * 1000);
  d.setUTCDate(d.getUTCDate() - daysAgo);
  return d.toISOString().slice(0, 10);
}

function toNum(v: unknown): number {
  const n = Number(v);
  return Number.isFinite(n) ? n : 0;
}

function norm(v: unknown): string {
  return String(v ?? "").trim();
}

function sleep(ms: number): Promise<void> {
  return new Promise((r) => setTimeout(r, ms));
}

// ── 不动销状态标签 ────────────────────────────────────────────────────
function calcStatus(qty30: number, qty14: number, qty7: number, qty3: number): string {
  if (qty30 === 0) return "30天不动销";
  if (qty14 === 0) return "14天以上不动销";
  if (qty7 === 0) return "7天以上不动销";
  if (qty3 === 0) return "近3天不动销";
  return `低销量(近30天${qty30}单)`;
}

// ── 工具：提取列表数据 ────────────────────────────────────────────────
function extractItems(data: unknown): Record<string, unknown>[] {
  if (Array.isArray(data)) return data as Record<string, unknown>[];
  if (data && typeof data === "object") {
    const d = data as Record<string, unknown>;
    for (const key of ["list", "data", "rows", "records"]) {
      if (Array.isArray(d[key])) return d[key] as Record<string, unknown>[];
    }
  }
  return [];
}

async function withRetry<T>(label: string, fn: () => Promise<T>): Promise<T> {
  let lastErr: unknown;
  for (let i = 1; i <= MAX_RETRIES; i++) {
    try {
      return await fn();
    } catch (e) {
      lastErr = e;
      if (i < MAX_RETRIES) await sleep(RETRY_DELAY_MS * i);
    }
  }
  throw lastErr;
}

// ── 领星 API ─────────────────────────────────────────────────────────
interface WalmartItem {
  item_id: string;
  msku: string;
  local_sku: string;
  local_name: string;
  store_id: string;
  store_name: string;
  wfs_qty: number;
}

async function fetchWalmartItems(
  client: LingxingClient,
  store_id: string,
  store_name: string,
): Promise<WalmartItem[]> {
  const items: WalmartItem[] = [];
  for (let page = 0; page < WALMART_LIST_MAX_PAGES; page++) {
    const resp = await withRetry(`${store_name} 商品列表 p${page + 1}`, () =>
      client.request<unknown>({
        method: "POST",
        path: WALMART_LIST_PATH,
        params: { store_ids: [store_id], offset: page * PAGE_LENGTH, length: PAGE_LENGTH },
        timeoutMs: TIMEOUT_MS,
      }),
    );
    const rows = extractItems(resp.data);
    for (const r of rows) {
      items.push({
        item_id: norm(r.item_id),
        msku: norm(r.msku),
        local_sku: norm(r.local_sku),
        local_name: norm(r.local_name) || norm(r.local_sku),
        store_id,
        store_name,
        wfs_qty: toNum(r.wfs_available_quantity),
      });
    }
    if (rows.length < PAGE_LENGTH) break;
  }
  return items;
}

async function fetchSalesMap(
  client: LingxingClient,
  store_id: string,
  start_date: string,
  end_date: string,
): Promise<Map<string, number>> {
  const map = new Map<string, number>();
  for (let page = 1; page <= SALE_STAT_MAX_PAGES; page++) {
    const resp = await withRetry(`${store_id} 销量 ${start_date}~${end_date} p${page}`, () =>
      client.request<unknown>({
        method: "POST",
        path: SALE_STAT_PATH,
        params: {
          sids: [store_id],
          start_date,
          end_date,
          result_type: "1",
          date_unit: "4",
          data_type: "1",
          page,
          length: SALE_STAT_PAGE_LENGTH,
        },
        timeoutMs: TIMEOUT_MS,
      }),
    );
    const data = (resp as any)?.data ?? resp;
    const rows = extractItems(data);
    for (const r of rows) {
      const qty = toNum(r.volumeTotal);
      const ids: string[] = Array.isArray(r.platform_product_id)
        ? (r.platform_product_id as unknown[]).map((x) => String(x ?? "").trim()).filter(Boolean)
        : [];
      for (const id of ids) {
        map.set(id, (map.get(id) ?? 0) + qty);
      }
    }
    if (rows.length < SALE_STAT_PAGE_LENGTH) break;
  }
  return map;
}

// ── 读取负责人映射 ────────────────────────────────────────────────────
function buildOwnerMap(rows: SheetRow[]): Map<string, string> {
  if (rows.length < 2) return new Map();
  const headers = rows[0];
  const itemIdx = headers.findIndex((h) =>
    ["商品id", "itemid", "商品ID"].includes(norm(h).replace(/\s+/g, "").toLowerCase()),
  );
  const ownerIdx = headers.findIndex((h) => norm(h) === "负责人");
  if (itemIdx < 0 || ownerIdx < 0) return new Map();
  const map = new Map<string, string>();
  for (const row of rows.slice(1)) {
    const id = norm(row[itemIdx]);
    const owner = norm(row[ownerIdx]);
    if (id && owner) map.set(id, owner);
  }
  return map;
}

// ── 主函数 ───────────────────────────────────────────────────────────
async function main(): Promise<void> {
  const startedAt = Date.now();
  const runId = createRunId();
  const confirmWrite = process.argv.includes("--confirm-write");

  const today = getShanghaiDate(0);
  const yesterday = getShanghaiDate(1);
  const d3 = getShanghaiDate(3);
  const d7 = getShanghaiDate(7);
  const d14 = getShanghaiDate(14);
  const d30 = getShanghaiDate(30);

  console.log("=".repeat(60));
  console.log(TASK_NAME);
  console.log(`记录日期: ${today}  数据窗口: ${d30} ~ ${yesterday}`);
  console.log(`模式: ${confirmWrite ? "✅ 写入" : "dry-run（加 --confirm-write 实际写入）"}`);
  console.log("=".repeat(60));

  const config = loadConfig();
  config.timeoutMs = TIMEOUT_MS;
  const client = new LingxingClient(config);
  const writer = new FeishuSheetWriter();
  const logger = new TableOperationLogger(writer, {
    spreadsheetToken: currentReport.spreadsheetToken,
    logSheetId: (currentReport.sheets as Record<string, string>)["表格操作日志"],
    dryRun: !confirmWrite,
    confirmWrite,
  });

  let status = confirmWrite ? "success" : "dry-run";
  let errorMessage = "";
  let fetchedCount = 0;
  let writtenCount = 0;

  try {
    // ── 步骤0：先写表头（提前写入，不依赖API）───────────────────────
    if (confirmWrite) {
      console.log("\n[0/4] 写入表头...");
      writer.clearRange({
        spreadsheetToken: currentReport.spreadsheetToken,
        sheetId: TARGET_SHEET_ID,
        sheetName: TARGET_SHEET_NAME,
        range: CLEAR_RANGE,
        dryRun: false,
        confirmWrite: true,
      });
      writer.writeCells({
        spreadsheetToken: currentReport.spreadsheetToken,
        sheetId: TARGET_SHEET_ID,
        sheetName: TARGET_SHEET_NAME,
        range: "A1:M1",
        rows: [SHEET_HEADERS],
        dryRun: false,
        confirmWrite: true,
      });
      console.log("  表头写入完成");
    }

    // ── 步骤1：读取负责人映射 ─────────────────────────────────────────
    console.log("\n[1/4] 读取 ItemID负责人 表...");
    const ownerRows = writer.readValues({
      spreadsheetToken: currentReport.spreadsheetToken,
      sheetId: (currentReport.sheets as Record<string, string>)["ItemID负责人"],
      range: "A1:U3000",
    });
    const ownerMap = buildOwnerMap(ownerRows);
    console.log(`  负责人映射: ${ownerMap.size} 条`);

    // ── 步骤2：抓取商品列表 ───────────────────────────────────────────
    console.log(`\n[2/4] 抓取商品列表（${STORES.length} 个店铺）...`);
    const allItems: WalmartItem[] = [];
    for (const store of STORES) {
      const items = await fetchWalmartItems(client, store.storeId, store.storeName);
      console.log(`  ${store.storeName}: ${items.length} 件`);
      allItems.push(...items);
    }
    fetchedCount = allItems.length;
    console.log(`  商品总数: ${fetchedCount}`);

    // ── 步骤3：抓取4个窗口销量 ───────────────────────────────────────
    console.log("\n[3/4] 抓取销量（30/14/7/3天窗口）...");
    const map30 = new Map<string, number>();
    const map14 = new Map<string, number>();
    const map7 = new Map<string, number>();
    const map3 = new Map<string, number>();

    for (const store of STORES) {
      console.log(`  ${store.storeName}...`);
      const s30 = await fetchSalesMap(client, store.storeId, d30, yesterday);
      await sleep(1500);
      const s14 = await fetchSalesMap(client, store.storeId, d14, yesterday);
      await sleep(1500);
      const s7 = await fetchSalesMap(client, store.storeId, d7, yesterday);
      await sleep(1500);
      const s3 = await fetchSalesMap(client, store.storeId, d3, yesterday);
      await sleep(1500);
      for (const [id, qty] of s30) map30.set(id, (map30.get(id) ?? 0) + qty);
      for (const [id, qty] of s14) map14.set(id, (map14.get(id) ?? 0) + qty);
      for (const [id, qty] of s7) map7.set(id, (map7.get(id) ?? 0) + qty);
      for (const [id, qty] of s3) map3.set(id, (map3.get(id) ?? 0) + qty);
    }

    // ── 步骤4：筛选 + 写入 ───────────────────────────────────────────
    console.log("\n[4/4] 筛选不动销产品并写入...");
    const dataRows: SheetRow[] = [];

    for (const item of allItems) {
      if (item.wfs_qty <= 0) continue; // 无库存跳过

      const qty30 = map30.get(item.item_id) ?? 0;
      const qty14 = map14.get(item.item_id) ?? 0;
      const qty7 = map7.get(item.item_id) ?? 0;
      const qty3 = map3.get(item.item_id) ?? 0;

      // 近30天 >= 10单 → 动销，跳过
      if (qty30 >= THIRTY_DAY_THRESHOLD) continue;

      dataRows.push([
        today,
        item.store_name,
        item.item_id,
        item.msku,
        item.local_sku,
        item.local_name,
        ownerMap.get(item.item_id) ?? "",
        qty30,
        qty14,
        qty7,
        qty3,
        calcStatus(qty30, qty14, qty7, qty3),
        item.wfs_qty,
      ]);
    }

    writtenCount = dataRows.length;
    console.log(`  不动销产品: ${writtenCount} 件`);

    if (!confirmWrite) {
      console.log("\n[dry-run] 不写入，前3行预览:");
      dataRows.slice(0, 3).forEach((r, i) =>
        console.log(`  [${i + 1}] ${r[2]} | ${r[1]} | ${r[11]} | WFS=${r[12]}`),
      );
    } else {
      // 表头已在步骤0写好，这里只写数据行（从第2行开始）
      if (dataRows.length > 0) {
        const endRow = 1 + dataRows.length;
        writer.writeCells({
          spreadsheetToken: currentReport.spreadsheetToken,
          sheetId: TARGET_SHEET_ID,
          sheetName: TARGET_SHEET_NAME,
          range: `A2:M${endRow}`,
          rows: dataRows,
          dryRun: false,
          confirmWrite: true,
        });
      }
      console.log(`  写入完成: ${writtenCount} 行数据`);
    }

    console.log(`\n✅ 执行完毕，耗时 ${((Date.now() - startedAt) / 1000).toFixed(1)}s`);
  } catch (e) {
    status = "failed";
    errorMessage = e instanceof Error ? e.message : String(e);
    console.log(`[错误] ${errorMessage}`);
    process.exitCode = 1;
  } finally {
    try {
      logger.append({
        executedAt: new Date().toISOString(),
        taskName: TASK_NAME,
        targetSheet: TARGET_SHEET_NAME,
        operationType: confirmWrite ? "write:replace" : "dry-run",
        dataSource: "领星API + ItemID负责人",
        dateRange: `${d30}~${yesterday}`,
        fetchedCount,
        writtenCount,
        updatedCount: 0,
        skippedCount: fetchedCount - writtenCount,
        failedCount: status === "failed" ? 1 : 0,
        status,
        errorMessage,
        durationSeconds: Number(((Date.now() - startedAt) / 1000).toFixed(3)),
        runId,
        environment: "server",
        remark:
          `不动销产品同步，阈值=近30天<10单，仅含WFS库存>0` +
          `，商品总数=${fetchedCount}，不动销=${writtenCount}` +
          (errorMessage ? `，错误=${errorMessage}` : ""),
      });
    } catch (logError) {
      console.log(`操作日志写入失败: ${logError instanceof Error ? logError.message : String(logError)}`);
    }
  }
}

if (require.main === module) {
  main().catch((e) => {
    console.log(`[致命错误] ${e instanceof Error ? e.message : String(e)}`);
    process.exitCode = 1;
  });
}
