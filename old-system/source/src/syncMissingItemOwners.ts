import { execFileSync } from "child_process";
import currentReport from "../config/currentReportFieldMapping.json";
import { loadConfig } from "./config";
import { FeishuSheetWriter } from "./feishuSheetWriter";
import { LingxingClient } from "./lingxingClient";
import { TableOperationLogger } from "./tableOperationLogger";

interface OwnerCandidate {
  sku: string;
  msku: string;
  itemId: string;
  productName: string;
  source: string;
  nonWfsInventory: number;
  wfsInventory: number;
}

type CellPayload = { value: string | number | boolean | null };
type SheetName = keyof typeof currentReport.sheets;

const LARK_CLI = "./scripts/lark-cli";
const DETAIL_SHEET_NAME = "5月销售明细_复盘";
const OWNER_SHEET_NAME = "ItemID负责人";
const LOG_SHEET_NAME = "表格操作日志";
const TASK_NAME = "补充ItemID负责人";
const DETAIL_START_ROW = 2;
// DETAIL_END_ROW 在运行时通过 getRowCount() 动态获取
const OWNER_START_ROW = 2;
const READ_BATCH_SIZE = 500;
const PREVIEW_LIMIT = 60;
const YUESI_CS_WFS_FEE = 4;
const WALMART_LIST_PATH = "/basicOpen/multiplatform/walmart/list";
const WALMART_LIST_PAGE_SIZE = 200;
const WALMART_LIST_MAX_PAGES = 100;
const TIMEOUT_MS = 120000;
const YUESI_STORE = {
  storeId: "110687428693128704",
  storeName: "CN2502-悦斯电子(陈文胜）",
};

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

function normalizeText(value: unknown): string {
  return String(value ?? "").trim();
}

function toNumber(value: unknown): number {
  const num = Number(value);
  return Number.isFinite(num) ? num : 0;
}

function extractDataArray(value: unknown): unknown[] {
  if (Array.isArray(value)) return value;
  if (!value || typeof value !== "object") return [];

  const record = value as Record<string, unknown>;
  if (Array.isArray(record.data)) return record.data;
  if (record.data && typeof record.data === "object") {
    const nested = record.data as Record<string, unknown>;
    if (Array.isArray(nested.list)) return nested.list;
    if (Array.isArray(nested.items)) return nested.items;
    if (Array.isArray(nested.rows)) return nested.rows;
    if (Array.isArray(nested.data)) return nested.data;
  }
  if (Array.isArray(record.list)) return record.list;
  if (Array.isArray(record.items)) return record.items;
  if (Array.isArray(record.rows)) return record.rows;
  return [];
}

function extractTotal(value: unknown): number {
  if (!value || typeof value !== "object") return 0;
  const record = value as Record<string, unknown>;
  const direct = Number(record.total);
  if (Number.isFinite(direct) && direct > 0) return direct;
  if (record.data && typeof record.data === "object") {
    const nested = record.data as Record<string, unknown>;
    const nestedTotal = Number(nested.total);
    if (Number.isFinite(nestedTotal) && nestedTotal > 0) return nestedTotal;
  }
  return 0;
}

function createRunId(): string {
  return `run_${new Date().toISOString().replace(/[-:.TZ]/g, "")}_${Math.random()
    .toString(36)
    .slice(2, 8)}`;
}

function parseCellRows(output: string): { rowNumber: number; values: unknown[] }[] {
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
    throw new Error(parsed.error?.message ?? "读取飞书单元格失败");
  }

  const range = parsed.data?.ranges?.[0];
  const cells = range?.cells ?? [];
  const rowIndices = range?.row_indices ?? [];

  return cells.map((row, index) => ({
    rowNumber: rowIndices[index] ?? index + 1,
    values: row.map((cell) => cell.value ?? ""),
  }));
}

function readRange(sheetId: string, range: string): { rowNumber: number; values: unknown[] }[] {
  const output = execLarkCli([
    "sheets",
    "+cells-get",
    "--spreadsheet-token",
    currentReport.spreadsheetToken,
    "--sheet-id",
    sheetId,
    "--range",
    range,
    "--include",
    "value",
    "--format",
    "json",
  ]);

  return parseCellRows(output);
}

function getSheetRowCount(sheetName: SheetName): number {
  const output = execLarkCli([
    "sheets",
    "+sheet-info",
    "--spreadsheet-token",
    currentReport.spreadsheetToken,
    "--sheet-id",
    currentReport.sheets[sheetName],
    "--format",
    "json",
  ]);

  const parsed = JSON.parse(output) as {
    ok?: boolean;
    data?: { range?: string };
    error?: { message?: string };
  };

  if (!parsed.ok) {
    throw new Error(parsed.error?.message ?? `读取 ${sheetName} 行数失败`);
  }

  const match = /[A-Z]+1:[A-Z]+(\d+)/.exec(parsed.data?.range ?? "");
  if (!match) {
    throw new Error(`无法解析 ${sheetName} range: ${parsed.data?.range ?? ""}`);
  }

  return Number(match[1]);
}

function readDetailCandidates(): Map<string, OwnerCandidate> {
  const candidates = new Map<string, OwnerCandidate>();

  const writer = new FeishuSheetWriter();
  const sheetRowCount = writer.getRowCount({
    spreadsheetToken: currentReport.spreadsheetToken,
    sheetId: currentReport.sheets[DETAIL_SHEET_NAME],
    sheetName: DETAIL_SHEET_NAME,
  });
  console.log(`${DETAIL_SHEET_NAME} 实际行数: ${sheetRowCount}`);

  for (let startRow = DETAIL_START_ROW; startRow <= sheetRowCount; startRow += READ_BATCH_SIZE) {
    const endRow = Math.min(startRow + READ_BATCH_SIZE - 1, sheetRowCount);
    const range = `A${startRow}:G${endRow}`;
    const rows = readRange(currentReport.sheets[DETAIL_SHEET_NAME], range);
    let validCount = 0;

    for (const row of rows) {
      const itemId = normalizeText(row.values[2]); // 5月销售明细 C 商品ID
      if (!itemId) {
        continue;
      }

      validCount += 1;
      const nextValue: OwnerCandidate = {
        sku: normalizeText(row.values[4]), // E SKU
        msku: normalizeText(row.values[3]), // D MSKU
        itemId,
        productName: normalizeText(row.values[5]), // F 品名
        source: DETAIL_SHEET_NAME,
        nonWfsInventory: 0,
        wfsInventory: 0,
      };
      const currentValue = candidates.get(itemId);

      if (!currentValue) {
        candidates.set(itemId, nextValue);
        continue;
      }

      candidates.set(itemId, {
        sku: currentValue.sku || nextValue.sku,
        msku: currentValue.msku || nextValue.msku,
        itemId,
        productName: currentValue.productName || nextValue.productName,
        source: currentValue.source || nextValue.source,
        nonWfsInventory: Math.max(currentValue.nonWfsInventory, nextValue.nonWfsInventory),
        wfsInventory: Math.max(currentValue.wfsInventory, nextValue.wfsInventory),
      });
    }

    console.log(`读取 ${DETAIL_SHEET_NAME} ${range}: 有效商品行 ${validCount}`);
    if (endRow >= sheetRowCount) break;
  }

  return candidates;
}

async function readYuesiInventoryCandidates(client: LingxingClient): Promise<Map<string, OwnerCandidate>> {
  const candidates = new Map<string, OwnerCandidate>();
  let fetchedCount = 0;

  for (let page = 0; page < WALMART_LIST_MAX_PAGES; page += 1) {
    const offset = page * WALMART_LIST_PAGE_SIZE;
    const response = await client.request<unknown>({
      method: "POST",
      path: WALMART_LIST_PATH,
      params: {
        offset,
        length: WALMART_LIST_PAGE_SIZE,
        store_ids: [YUESI_STORE.storeId],
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

      // 2026-07-27 UNPUBLISHED(已下架)不进负责人候选：下架品无需匹配负责人。
      if (normalizeText(record.status_name).toUpperCase() === "UNPUBLISHED") {
        continue;
      }

      const nonWfsInventory = toNumber(record.available_quantity);
      const wfsInventory = toNumber(record.wfs_available_quantity);
      if (nonWfsInventory <= 0 && wfsInventory <= 0) {
        continue;
      }

      candidates.set(itemId, {
        sku: normalizeText(record.local_sku),
        msku: normalizeText(record.msku),
        itemId,
        productName: normalizeText(record.local_name) || normalizeText(record.name),
        source: `${YUESI_STORE.storeName}库存`,
        nonWfsInventory,
        wfsInventory,
      });
    }

    const total = extractTotal(response.data);
    if (items.length < WALMART_LIST_PAGE_SIZE || (total > 0 && fetchedCount >= total)) {
      break;
    }
  }

  console.log(
    `读取 ${YUESI_STORE.storeName} Walmart在线商品: 抓取 ${fetchedCount} 条，库存>0候选 ${candidates.size} 个`,
  );
  return candidates;
}

function mergeCandidates(base: Map<string, OwnerCandidate>, extra: Map<string, OwnerCandidate>): Map<string, OwnerCandidate> {
  const merged = new Map(base);

  for (const [itemId, nextValue] of extra) {
    const currentValue = merged.get(itemId);
    if (!currentValue) {
      merged.set(itemId, nextValue);
      continue;
    }

    merged.set(itemId, {
      sku: currentValue.sku || nextValue.sku,
      msku: currentValue.msku || nextValue.msku,
      itemId,
      productName: currentValue.productName || nextValue.productName,
      source: currentValue.source.includes(nextValue.source)
        ? currentValue.source
        : `${currentValue.source}+${nextValue.source}`,
      nonWfsInventory: Math.max(currentValue.nonWfsInventory, nextValue.nonWfsInventory),
      wfsInventory: Math.max(currentValue.wfsInventory, nextValue.wfsInventory),
    });
  }

  return merged;
}

function readExistingOwnerItemIds(ownerEndRow: number): { existingItemIds: Set<string>; lastDataRow: number } {
  const existingItemIds = new Set<string>();
  let lastDataRow = 1;

  for (let startRow = OWNER_START_ROW; startRow <= ownerEndRow; startRow += READ_BATCH_SIZE) {
    const endRow = Math.min(startRow + READ_BATCH_SIZE - 1, ownerEndRow);
    const range = `A${startRow}:F${endRow}`;
    const rows = readRange(currentReport.sheets[OWNER_SHEET_NAME], range);
    let validCount = 0;

    for (const row of rows) {
      const sku = normalizeText(row.values[0]);
      const msku = normalizeText(row.values[1]);
      const itemId = normalizeText(row.values[2]);
      const productName = normalizeText(row.values[3]);

      if (itemId) {
        existingItemIds.add(itemId);
      }
      if (sku || msku || itemId || productName) {
        validCount += 1;
        lastDataRow = Math.max(lastDataRow, row.rowNumber);
      }
    }

    console.log(`读取 ${OWNER_SHEET_NAME} ${range}: 已维护有效行 ${validCount}`);
  }

  return { existingItemIds, lastDataRow };
}

function buildMissingRows(candidates: Map<string, OwnerCandidate>, existingItemIds: Set<string>): OwnerCandidate[] {
  return Array.from(candidates.values())
    .filter((candidate) => !existingItemIds.has(candidate.itemId))
    .sort((a, b) => a.itemId.localeCompare(b.itemId));
}

function getDefaultWfsFee(candidate: OwnerCandidate): string | number {
  return candidate.msku.trim().toUpperCase().startsWith("CS") ? YUESI_CS_WFS_FEE : "";
}

function toCells(rows: OwnerCandidate[]): CellPayload[][] {
  return rows.map((row) => [
    { value: row.sku },
    { value: row.msku },
    { value: row.itemId },
    { value: row.productName },
    { value: "" },
    { value: getDefaultWfsFee(row) },
  ]);
}

function writeMissingRows(rows: OwnerCandidate[], startRow: number): void {
  const endRow = startRow + rows.length - 1;
  const output = execLarkCli([
    "sheets",
    "+cells-set",
    "--spreadsheet-token",
    currentReport.spreadsheetToken,
    "--sheet-id",
    currentReport.sheets[OWNER_SHEET_NAME],
    "--range",
    `A${startRow}:F${endRow}`,
    "--cells",
    JSON.stringify(toCells(rows)),
    "--allow-overwrite=false",
  ]).trim();

  if (output) {
    console.log(output);
  }
}

function ensureOwnerSheetRows(requiredEndRow: number, currentRowCount: number): void {
  if (requiredEndRow <= currentRowCount) {
    return;
  }

  const insertCount = requiredEndRow - currentRowCount;
  console.log(`ItemID负责人 当前行数 ${currentRowCount}，需要插入空白行 ${insertCount}`);
  const output = execLarkCli([
    "sheets",
    "+dim-insert",
    "--spreadsheet-token",
    currentReport.spreadsheetToken,
    "--sheet-id",
    currentReport.sheets[OWNER_SHEET_NAME],
    "--position",
    String(currentRowCount),
    "--count",
    String(insertCount),
    "--inherit-style",
    "none",
    "--format",
    "json",
  ]).trim();

  if (output) {
    console.log(output);
  }
}

async function main(): Promise<void> {
  const startedAt = Date.now();
  const runId = createRunId();
  const confirmWrite = process.argv.includes("--confirm-write");
  const dryRun = !confirmWrite;
  const writer = new FeishuSheetWriter();
  const client = new LingxingClient(loadConfig());
  const logger = new TableOperationLogger(writer, {
    spreadsheetToken: currentReport.spreadsheetToken,
    logSheetId: currentReport.sheets[LOG_SHEET_NAME],
    dryRun,
    confirmWrite,
  });
  let candidateCount = 0;
  let detailCandidateCount = 0;
  let yuesiInventoryCandidateCount = 0;
  let existingCount = 0;
  let missingCount = 0;
  let status = dryRun ? "dry-run" : "success";
  let errorMessage = "";
  let logSuccess = false;

  console.log("补充 ItemID负责人 缺失商品");
  console.log(`运行ID: ${runId}`);
  console.log(`写入模式: ${confirmWrite ? "confirm-write" : "dry-run"}`);
  console.log(`来源 Sheet: ${DETAIL_SHEET_NAME} (${currentReport.sheets[DETAIL_SHEET_NAME]})`);
  console.log(`补充规则: ${YUESI_STORE.storeName} 非WFS库存或WFS库存 > 0 且 ItemID负责人 未维护时自动新增`);
  console.log(`目标 Sheet: ${OWNER_SHEET_NAME} (${currentReport.sheets[OWNER_SHEET_NAME]})`);
  console.log("写入列: A SKU, B MSKU, C 商品ID, D 中文名称, E 负责人留空, F WFS配送费（$）；MSKU为CS开头默认填4");

  try {
    const ownerRowCount = getSheetRowCount(OWNER_SHEET_NAME);
    const detailCandidates = readDetailCandidates();
    const yuesiInventoryCandidates = await readYuesiInventoryCandidates(client);
    const candidates = mergeCandidates(detailCandidates, yuesiInventoryCandidates);
    const { existingItemIds, lastDataRow } = readExistingOwnerItemIds(ownerRowCount);
    const missingRows = buildMissingRows(candidates, existingItemIds);
    const writeStartRow = lastDataRow + 1;
    const writeEndRow = writeStartRow + missingRows.length - 1;
    detailCandidateCount = detailCandidates.size;
    yuesiInventoryCandidateCount = yuesiInventoryCandidates.size;
    candidateCount = candidates.size;
    existingCount = existingItemIds.size;
    missingCount = missingRows.length;

    console.log("");
    console.log("补充汇总:");
    console.log(`销售明细唯一商品ID数: ${detailCandidateCount}`);
    console.log(`悦斯库存>0唯一商品ID数: ${yuesiInventoryCandidateCount}`);
    console.log(`合并后唯一商品ID数: ${candidateCount}`);
    console.log(`ItemID负责人已维护商品ID数: ${existingCount}`);
    console.log(`待新增商品ID数: ${missingCount}`);
    console.log(`ItemID负责人当前总行数: ${ownerRowCount}`);
    console.log(`当前最后有效行: ${lastDataRow}`);
    console.log(`计划写入范围: ${missingRows.length > 0 ? `A${writeStartRow}:F${writeEndRow}` : "无"}`);
    console.log(`预览前 ${PREVIEW_LIMIT} 行:`);
    console.table(
      missingRows.slice(0, PREVIEW_LIMIT).map((row) => ({
        SKU: row.sku,
        MSKU: row.msku,
        商品ID: row.itemId,
        中文名称: row.productName,
        负责人: "",
        "WFS配送费（$）": getDefaultWfsFee(row),
        来源: row.source,
        非WFS库存: row.nonWfsInventory,
        WFS库存: row.wfsInventory,
      })),
    );

    if (missingRows.length === 0) {
      console.log("没有需要新增的 ITEM ID。");
      return;
    }

    if (dryRun) {
      console.log("dry-run: 不写入飞书。确认无误后运行 npm run sync:missing-item-owners -- --confirm-write");
      return;
    }

    ensureOwnerSheetRows(writeEndRow, ownerRowCount);
    writeMissingRows(missingRows, writeStartRow);
    console.log(`是否写入成功: 是`);
    console.log(`新增 ITEM ID 数: ${missingRows.length}`);
  } catch (error) {
    status = "failed";
    errorMessage = error instanceof Error ? error.message : String(error);
    console.log(`执行失败: ${errorMessage}`);
    process.exitCode = 1;
  } finally {
    try {
      logger.append({
        executedAt: new Date().toISOString(),
        taskName: TASK_NAME,
        targetSheet: OWNER_SHEET_NAME,
        operationType: dryRun ? "dry-run" : "append",
        dataSource: DETAIL_SHEET_NAME,
        dateRange: "",
        fetchedCount: candidateCount,
        writtenCount: dryRun ? 0 : missingCount,
        updatedCount: 0,
        skippedCount: existingCount,
        failedCount: status === "failed" ? 1 : 0,
        status,
        errorMessage,
        durationSeconds: Number(((Date.now() - startedAt) / 1000).toFixed(3)),
        runId,
        environment: "local",
        remark:
          `CODEX执行：补充ItemID负责人，来源=${DETAIL_SHEET_NAME}` +
          `，销售明细唯一商品ID数=${detailCandidateCount}` +
          `，悦斯库存>0商品ID数=${yuesiInventoryCandidateCount}` +
          `，合并后唯一商品ID数=${candidateCount}` +
          `，已维护商品ID数=${existingCount}` +
          `，新增ItemID=${missingCount}` +
          `，规则=${YUESI_STORE.storeName}非WFS库存或WFS库存>0且未维护时自动新增` +
          "，负责人留空待人工填写，MSKU为CS开头的WFS配送费默认填4",
      });
      logSuccess = true;
    } catch (logError) {
      console.log(`记录操作日志失败: ${logError instanceof Error ? logError.message : String(logError)}`);
    }

    console.log(`日志是否写入成功: ${logSuccess ? "是" : "否"}`);
  }
}

main().catch((error) => {
  console.log(`执行失败: ${error instanceof Error ? error.message : String(error)}`);
  process.exitCode = 1;
});
