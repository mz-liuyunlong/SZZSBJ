/**
 * syncProductNameFromLingxing.ts
 *
 * Task D: Refresh dim_product.product_name from Lingxing local product details.
 *
 * Dry-run calls Lingxing and writes a report CSV only.
 * Confirm-write calls Lingxing again, writes raw_lingxing_api first, then updates
 * only dim_product.product_name and empty dim_product.sku.
 */

import "dotenv/config";
import * as crypto from "crypto";
import * as fs from "fs";
import * as path from "path";
import * as mysql from "mysql2/promise";
import { loadConfig } from "./config";
import { LingxingClient } from "./lingxingClient";

const SCRIPT_NAME = "syncProductNameFromLingxing";
const API_PATH = "/erp/sc/routing/data/local_inventory/batchGetProductInfo";
const PLATFORM = "walmart";
const BATCH_SIZE = 100;
const BATCH_DELAY_MS = 1100;
const RETRY_MAX = 2;
const TIMEOUT_MS = 120000;

const CONFIRM_WRITE = process.argv.includes("--confirm-write");
const DRY_RUN = !CONFIRM_WRITE;
const ONLY_EMPTY_PRODUCT_NAME = process.argv.includes("--only-empty-product-name");

interface ProductRow extends mysql.RowDataPacket {
  platform: string;
  store_id: string;
  store_name: string | null;
  item_id: string;
  msku: string;
  old_product_name: string | null;
  item_name: string | null;
  old_sku: string | null;
}

interface ApiItem {
  sku: string;
  product_name: string;
  status: string;
  sku_identifier: string;
  raw: Record<string, unknown>;
}

interface BatchResult {
  params: Record<string, string[]>;
  response: unknown;
  items: ApiItem[];
  rawId?: number;
  rawHash?: string;
}

interface ReportRow {
  platform: string;
  store_id: string;
  store_name: string;
  item_id: string;
  msku: string;
  old_product_name: string;
  new_product_name: string;
  old_sku: string;
  new_sku: string;
  match_group_key: string;
  sku_will_update: string;
  sku_update_reason: string;
  product_name_will_update: string;
  match_method: string;
  api_sku: string;
  api_product_name: string;
  api_status: string;
  matched_dim_rows_count: string;
  is_multi_dim_same_lingxing_sku: string;
  base_sku: string;
  base_sku_pattern_valid: string;
  is_matched: string;
  is_ambiguous: string;
  ambiguous_reason: string;
  skip_reason: string;
  raw_id: string;
}

interface BaseSkuAudit {
  skuNonemptySampleTotal: number;
  mskuSkuSuffixMatchCount: number;
  ratio: number;
  isValid: boolean;
  mismatchSamples: ProductRow[];
}

interface Stats {
  total: number;
  matched: number;
  unmatched: number;
  ambiguous: number;
  multiDimSameLingxingSku: number;
  productNameWillUpdate: number;
  productNameUnchanged: number;
  productNameEmptySkipped: number;
  skuEmptyTotal: number;
  skuCanUpdate: number;
  skuCanUpdateByIdentifier: number;
  skuCanUpdateByBaseSku: number;
  skuStillEmpty: number;
  failedBatches: number;
}

function argValue(name: string): string {
  const prefix = `--${name}=`;
  const found = process.argv.find((arg) => arg.startsWith(prefix));
  return found ? found.slice(prefix.length).trim() : "";
}

function limitValue(): number | null {
  const raw = argValue("limit");
  if (!raw) return null;
  const n = Number(raw);
  if (!Number.isInteger(n) || n <= 0) throw new Error("--limit must be a positive integer");
  return n;
}

function dbConfig() {
  return {
    host: process.env.DB_HOST ?? "127.0.0.1",
    port: Number(process.env.DB_PORT ?? 3306),
    user: process.env.DB_USER ?? "",
    password: process.env.DB_PASSWORD ?? "",
    database: process.env.DB_NAME ?? "walmart_ai_data",
  };
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function text(value: unknown): string {
  return String(value ?? "").trim();
}

function stripMskuSuffix(msku: string): string {
  return msku.replace(/-[^-]+$/, "").trim();
}

function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function hasSkuSuffixPattern(msku: string, sku: string): boolean {
  if (!msku || !sku) return false;
  return new RegExp(`^${escapeRegExp(sku)}-[A-Za-z0-9]+$`).test(msku);
}

function auditBaseSkuPattern(rows: ProductRow[]): BaseSkuAudit {
  const skuRows = rows.filter((row) => text(row.old_sku));
  const matched = skuRows.filter((row) => hasSkuSuffixPattern(text(row.msku), text(row.old_sku)));
  const ratio = skuRows.length ? matched.length / skuRows.length : 0;
  return {
    skuNonemptySampleTotal: skuRows.length,
    mskuSkuSuffixMatchCount: matched.length,
    ratio,
    isValid: ratio >= 0.95,
    mismatchSamples: skuRows.filter((row) => !hasSkuSuffixPattern(text(row.msku), text(row.old_sku))).slice(0, 20),
  };
}

function chunkArray<T>(items: T[], size: number): T[][] {
  const chunks: T[][] = [];
  for (let i = 0; i < items.length; i += size) chunks.push(items.slice(i, i + size));
  return chunks;
}

function timestamp(): string {
  const d = new Date();
  const p = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}${p(d.getMonth() + 1)}${p(d.getDate())}_${p(d.getHours())}${p(d.getMinutes())}${p(d.getSeconds())}`;
}

function csvEscape(value: unknown): string {
  const s = String(value ?? "");
  return /[",\n\r]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
}

function writeCsv(filePath: string, rows: ReportRow[]): void {
  const headers = [
    "platform",
    "store_id",
    "store_name",
    "item_id",
    "msku",
    "old_product_name",
    "new_product_name",
    "old_sku",
    "new_sku",
    "match_group_key",
    "sku_will_update",
    "sku_update_reason",
    "product_name_will_update",
    "match_method",
    "api_sku",
    "api_product_name",
    "api_status",
    "matched_dim_rows_count",
    "is_multi_dim_same_lingxing_sku",
    "base_sku",
    "base_sku_pattern_valid",
    "is_matched",
    "is_ambiguous",
    "ambiguous_reason",
    "skip_reason",
    "raw_id",
  ];
  const lines = [headers.join(",")];
  for (const row of rows) {
    lines.push(headers.map((h) => csvEscape((row as unknown as Record<string, string>)[h])).join(","));
  }
  fs.writeFileSync(filePath, `${lines.join("\n")}\n`, "utf-8");
}

function parseApiItems(response: unknown): ApiItem[] {
  const data = (response as { data?: unknown } | undefined)?.data;
  if (!Array.isArray(data)) return [];
  const items: ApiItem[] = [];
  for (const item of data) {
    if (!item || typeof item !== "object") continue;
    const raw = item as Record<string, unknown>;
    items.push({
      sku: text(raw.sku),
      product_name: text(raw.product_name),
      status: text(raw.status),
      sku_identifier: text(raw.sku_identifier),
      raw,
    });
  }
  return items;
}

async function requestBatch(
  client: LingxingClient,
  params: Record<string, string[]>,
  label: string,
): Promise<BatchResult> {
  let lastError: unknown;
  for (let attempt = 1; attempt <= RETRY_MAX; attempt++) {
    try {
      const response = await client.request<unknown>({
        method: "POST",
        path: API_PATH,
        params,
        timeoutMs: TIMEOUT_MS,
      });
      return { params, response, items: parseApiItems(response) };
    } catch (err) {
      lastError = err;
      console.warn(`  [retry ${attempt}/${RETRY_MAX}] ${label}: ${String(err)}`);
      if (attempt < RETRY_MAX) await sleep(BATCH_DELAY_MS);
    }
  }
  throw lastError;
}

async function saveRawRecord(
  db: mysql.Connection,
  params: Record<string, string[]>,
  response: unknown,
  batchNo: string,
): Promise<{ rawId: number; rawHash: string }> {
  const requestJson = JSON.stringify(params);
  const responseJson = JSON.stringify(response);
  const rawHash = crypto
    .createHash("sha256")
    .update(`${API_PATH}\n${requestJson}\n${responseJson}`)
    .digest("hex");
  const responseCode = text((response as { code?: unknown } | undefined)?.code);
  const requestId = text((response as { request_id?: unknown } | undefined)?.request_id);
  const extraJson = JSON.stringify({
    script: SCRIPT_NAME,
    batch_no: batchNo,
    request_id: requestId,
  });

  await db.query(
    `INSERT IGNORE INTO raw_lingxing_api
       (source_system, api_path, request_method, request_params_json, response_json,
        response_code, is_success, error_message, data_date, raw_hash, extra_json)
     VALUES ('lingxing', ?, 'POST', CAST(? AS JSON), CAST(? AS JSON),
             ?, 1, NULL, CURDATE(), ?, CAST(? AS JSON))`,
    [API_PATH, requestJson, responseJson, responseCode || "0", rawHash, extraJson],
  );

  const [rows] = await db.query<mysql.RowDataPacket[]>(
    `SELECT id
     FROM raw_lingxing_api
     WHERE api_path = ? AND data_date = CURDATE() AND raw_hash = ?
     ORDER BY id DESC
     LIMIT 1`,
    [API_PATH, rawHash],
  );
  const rawId = Number(rows[0]?.id ?? 0);
  if (!rawId) throw new Error(`RAW insert/query failed for batch ${batchNo}`);
  return { rawId, rawHash };
}

async function loadProducts(db: mysql.Connection): Promise<ProductRow[]> {
  const conditions = ["platform = ?"];
  const params: Array<string | number> = [PLATFORM];
  if (ONLY_EMPTY_PRODUCT_NAME) conditions.push("(product_name IS NULL OR product_name = '')");
  const limit = limitValue();
  const sql = `
    SELECT platform, store_id, store_name, item_id, msku,
           product_name AS old_product_name, item_name, sku AS old_sku
    FROM dim_product
    WHERE ${conditions.join(" AND ")}
      AND COALESCE(store_id, '') <> ''
      AND COALESCE(item_id, '') <> ''
      AND COALESCE(msku, '') <> ''
    ORDER BY item_id, msku
    ${limit ? "LIMIT ?" : ""}
  `;
  if (limit) params.push(limit);
  const [rows] = await db.query<ProductRow[]>(sql, params);
  return rows;
}

function initReportRow(row: ProductRow): ReportRow {
  return {
    platform: text(row.platform),
    store_id: text(row.store_id),
    store_name: text(row.store_name),
    item_id: text(row.item_id),
    msku: text(row.msku),
    old_product_name: text(row.old_product_name),
    new_product_name: "",
    old_sku: text(row.old_sku),
    new_sku: "",
    match_group_key: "",
    sku_will_update: "0",
    sku_update_reason: "",
    product_name_will_update: "0",
    match_method: "",
    api_sku: "",
    api_product_name: "",
    api_status: "",
    matched_dim_rows_count: "",
    is_multi_dim_same_lingxing_sku: "0",
    base_sku: "",
    base_sku_pattern_valid: "",
    is_matched: "0",
    is_ambiguous: "0",
    ambiguous_reason: "",
    skip_reason: "unmatched",
    raw_id: "",
  };
}

function groupIndexesByKey(rows: ProductRow[], indexes: number[], keyFn: (row: ProductRow) => string): Map<string, number[]> {
  const map = new Map<string, number[]>();
  for (const idx of indexes) {
    const key = keyFn(rows[idx]);
    if (!key) continue;
    const arr = map.get(key) ?? [];
    arr.push(idx);
    map.set(key, arr);
  }
  return map;
}

function indexApiItems(items: ApiItem[], keyFn: (item: ApiItem) => string): Map<string, ApiItem[]> {
  const map = new Map<string, ApiItem[]>();
  for (const item of items) {
    const key = keyFn(item);
    if (!key) continue;
    const arr = map.get(key) ?? [];
    arr.push(item);
    map.set(key, arr);
  }
  return map;
}

function uniqueValues(items: ApiItem[], valueFn: (item: ApiItem) => string): string[] {
  return Array.from(new Set(items.map(valueFn).map(text).filter(Boolean)));
}

function markAmbiguous(
  reports: ReportRow[],
  rowIndexes: number[],
  method: string,
  reason: string,
  groupKey: string,
  items: ApiItem[],
  rawId?: number,
): void {
  const first = items[0];
  for (const idx of rowIndexes) {
    reports[idx].is_matched = "0";
    reports[idx].is_ambiguous = "1";
    reports[idx].ambiguous_reason = reason;
    reports[idx].skip_reason = reason;
    reports[idx].match_method = method;
    reports[idx].match_group_key = groupKey;
    reports[idx].matched_dim_rows_count = String(rowIndexes.length);
    reports[idx].api_sku = first?.sku ?? "";
    reports[idx].api_product_name = first?.product_name ?? "";
    reports[idx].api_status = first?.status ?? "";
    reports[idx].raw_id = rawId ? String(rawId) : "";
  }
}

function selectUniqueApiItem(items: ApiItem[]): { item?: ApiItem; ambiguousReason?: string } {
  if (items.length === 0) return {};
  const skus = uniqueValues(items, (item) => item.sku);
  if (skus.length > 1) return { ambiguousReason: "multiple_api_sku" };
  const productNames = uniqueValues(items, (item) => item.product_name);
  if (productNames.length > 1) return { ambiguousReason: "multiple_api_product_name" };
  if (!text(items[0].product_name)) return { ambiguousReason: "empty_product_name" };
  return { item: items[0] };
}

function applyMatch(
  rows: ProductRow[],
  reports: ReportRow[],
  rowIndexes: number[],
  item: ApiItem,
  method: string,
  groupKey: string,
  baseSkuPatternValid: boolean,
  rawId?: number,
): void {
  const newName = text(item.product_name);
  const newSku = text(item.sku);
  const isMultiDimSameLingxingSku = rowIndexes.length > 1;

  for (const idx of rowIndexes) {
    const row = rows[idx];
    const report = reports[idx];
    const oldName = text(row.old_product_name);
    const oldSku = text(row.old_sku);
    const baseSku = method === "stripped_msku_sku" ? stripMskuSuffix(text(row.msku)) : "";

    report.is_matched = "1";
    report.is_ambiguous = "0";
    report.ambiguous_reason = "";
    report.skip_reason = "";
    report.match_method = method;
    report.match_group_key = groupKey;
    report.api_sku = newSku;
    report.api_product_name = newName;
    report.api_status = item.status;
    report.matched_dim_rows_count = String(rowIndexes.length);
    report.is_multi_dim_same_lingxing_sku = isMultiDimSameLingxingSku ? "1" : "0";
    report.new_product_name = newName;
    report.new_sku = newSku;
    report.base_sku = baseSku;
    report.base_sku_pattern_valid = method === "stripped_msku_sku" ? (baseSkuPatternValid ? "1" : "0") : "";
    report.raw_id = rawId ? String(rawId) : "";

    if (newName && oldName !== newName) {
      report.product_name_will_update = "1";
    }

    if (!oldSku && newSku) {
      if (method === "sku_identifier") {
        report.sku_will_update = "1";
        report.sku_update_reason = "sku_identifier_exact_msku";
      } else if (method === "stripped_msku_sku") {
        if (!baseSkuPatternValid) {
          report.sku_update_reason = "base_sku_pattern_invalid";
        } else if (newSku === baseSku) {
          report.sku_will_update = "1";
          report.sku_update_reason = "base_sku_unique_match";
        } else {
          report.sku_update_reason = "base_sku_api_sku_mismatch";
        }
      }
    }
  }
}

async function processGroups(
  db: mysql.Connection,
  client: LingxingClient,
  rows: ProductRow[],
  reports: ReportRow[],
  pending: Set<number>,
  groupMap: Map<string, number[]>,
  paramName: "skus" | "sku_identifiers",
  method: string,
  itemKeyFn: (item: ApiItem) => string,
  baseSkuPatternValid: boolean,
): Promise<{ failedBatches: number }> {
  let failedBatches = 0;
  const keys = Array.from(groupMap.keys()).filter((key) => key);
  const batches = chunkArray(keys, BATCH_SIZE);
  for (let i = 0; i < batches.length; i++) {
    const batch = batches[i];
    const batchNo = `${method}_${i + 1}_${batches.length}`;
    try {
      const result = await requestBatch(client, { [paramName]: batch }, batchNo);
      if (CONFIRM_WRITE) {
        const raw = await saveRawRecord(db, result.params, result.response, batchNo);
        result.rawId = raw.rawId;
        result.rawHash = raw.rawHash;
      }

      const apiMap = indexApiItems(result.items, itemKeyFn);
      for (const key of batch) {
        const rowIndexes = (groupMap.get(key) ?? []).filter((idx) => pending.has(idx));
        if (rowIndexes.length === 0) continue;
        const items = apiMap.get(key) ?? [];
        if (items.length === 0) continue;
        const { item, ambiguousReason } = selectUniqueApiItem(items);
        if (ambiguousReason || !item) {
          markAmbiguous(reports, rowIndexes, method, ambiguousReason ?? "unknown_api_match_conflict", key, items, result.rawId);
          for (const idx of rowIndexes) pending.delete(idx);
          continue;
        }
        applyMatch(rows, reports, rowIndexes, item, method, key, baseSkuPatternValid, result.rawId);
        for (const idx of rowIndexes) pending.delete(idx);
      }
    } catch (err) {
      failedBatches++;
      for (const key of batch) {
        for (const idx of groupMap.get(key) ?? []) {
          if (pending.has(idx)) {
            reports[idx].skip_reason = `failed_batch: ${String(err)}`;
            reports[idx].match_method = method;
          }
        }
      }
      console.error(`  batch failed ${batchNo}: ${String(err)}`);
    }

    if (i < batches.length - 1) await sleep(BATCH_DELAY_MS);
  }
  return { failedBatches };
}

async function writeDimUpdates(db: mysql.Connection, reports: ReportRow[]): Promise<{ productNameUpdated: number; skuUpdated: number }> {
  let productNameUpdated = 0;
  let skuUpdated = 0;
  for (const r of reports) {
    if (r.is_matched !== "1" || r.is_ambiguous === "1") continue;

    if (r.product_name_will_update === "1" && text(r.new_product_name)) {
      const [result] = await db.query<mysql.ResultSetHeader>(
        `UPDATE dim_product
         SET product_name = ?, updated_at = NOW()
         WHERE platform = ? AND store_id = ? AND item_id = ? AND msku = ?
           AND ? IS NOT NULL AND TRIM(?) <> ''`,
        [r.new_product_name, r.platform, r.store_id, r.item_id, r.msku, r.new_product_name, r.new_product_name],
      );
      productNameUpdated += result.affectedRows;
    }

    if (r.sku_will_update === "1" && text(r.new_sku)) {
      const [result] = await db.query<mysql.ResultSetHeader>(
        `UPDATE dim_product
         SET sku = ?, updated_at = NOW()
         WHERE platform = ? AND store_id = ? AND item_id = ? AND msku = ?
           AND (sku IS NULL OR sku = '')
           AND ? IS NOT NULL AND TRIM(?) <> ''`,
        [r.new_sku, r.platform, r.store_id, r.item_id, r.msku, r.new_sku, r.new_sku],
      );
      skuUpdated += result.affectedRows;
    }
  }
  return { productNameUpdated, skuUpdated };
}

function buildStats(reports: ReportRow[]): Stats {
  const skuEmptyTotal = reports.filter((r) => !r.old_sku).length;
  const skuCanUpdate = reports.filter((r) => r.sku_will_update === "1").length;
  return {
    total: reports.length,
    matched: reports.filter((r) => r.is_matched === "1").length,
    unmatched: reports.filter((r) => r.is_matched !== "1" && r.is_ambiguous !== "1").length,
    ambiguous: reports.filter((r) => r.is_ambiguous === "1").length,
    multiDimSameLingxingSku: reports.filter((r) => r.is_multi_dim_same_lingxing_sku === "1" && r.is_ambiguous !== "1").length,
    productNameWillUpdate: reports.filter((r) => r.product_name_will_update === "1").length,
    productNameUnchanged: reports.filter((r) => r.is_matched === "1" && r.api_product_name && r.product_name_will_update !== "1").length,
    productNameEmptySkipped: reports.filter((r) => r.ambiguous_reason === "empty_product_name").length,
    skuEmptyTotal,
    skuCanUpdate,
    skuCanUpdateByIdentifier: reports.filter((r) => r.sku_will_update === "1" && r.sku_update_reason === "sku_identifier_exact_msku").length,
    skuCanUpdateByBaseSku: reports.filter((r) => r.sku_will_update === "1" && r.sku_update_reason === "base_sku_unique_match").length,
    skuStillEmpty: skuEmptyTotal - skuCanUpdate,
    failedBatches: 0,
  };
}

function printSamples(label: string, rows: ReportRow[]): void {
  console.log(`\n${label}:`);
  console.table(rows.slice(0, 20).map((r) => ({
    item_id: r.item_id,
    msku: r.msku,
    old_sku: r.old_sku,
    new_sku: r.new_sku,
    old_name: r.old_product_name,
    new_name: r.new_product_name,
    api_sku: r.api_sku,
    group_count: r.matched_dim_rows_count,
    sku_reason: r.sku_update_reason,
    method: r.match_method,
    reason: r.ambiguous_reason || r.skip_reason,
  })));
}

async function main() {
  console.log(`${SCRIPT_NAME} mode=${DRY_RUN ? "dry-run" : "confirm-write"}`);
  console.log(`limit=${limitValue() ?? "all"} only_empty_product_name=${ONLY_EMPTY_PRODUCT_NAME ? "yes" : "no"}`);

  const db = await mysql.createConnection(dbConfig());
  try {
    const rows = await loadProducts(db);
    const reports = rows.map(initReportRow);
    const pending = new Set(rows.map((_, idx) => idx));
    const client = new LingxingClient(loadConfig());
    let failedBatches = 0;
    const baseSkuAudit = auditBaseSkuPattern(rows);

    const skuIndexes = rows
      .map((row, idx) => ({ row, idx }))
      .filter(({ row }) => text(row.old_sku))
      .map(({ idx }) => idx);
    const bySku = groupIndexesByKey(rows, skuIndexes, (row) => text(row.old_sku));
    failedBatches += (await processGroups(
      db,
      client,
      rows,
      reports,
      pending,
      bySku,
      "skus",
      "sku",
      (item) => item.sku,
      baseSkuAudit.isValid,
    )).failedBatches;

    const skuEmptyPending = Array.from(pending).filter((idx) => !text(rows[idx].old_sku));
    const byMskuIdentifier = groupIndexesByKey(rows, skuEmptyPending, (row) => text(row.msku));
    failedBatches += (await processGroups(
      db,
      client,
      rows,
      reports,
      pending,
      byMskuIdentifier,
      "sku_identifiers",
      "sku_identifier",
      (item) => item.sku_identifier || item.sku,
      baseSkuAudit.isValid,
    )).failedBatches;

    const stillSkuEmptyPending = Array.from(pending).filter((idx) => !text(rows[idx].old_sku));
    const byBaseSku = groupIndexesByKey(rows, stillSkuEmptyPending, (row) => stripMskuSuffix(text(row.msku)));
    failedBatches += (await processGroups(
      db,
      client,
      rows,
      reports,
      pending,
      byBaseSku,
      "skus",
      "stripped_msku_sku",
      (item) => item.sku,
      baseSkuAudit.isValid,
    )).failedBatches;

    let writeResult: { productNameUpdated: number; skuUpdated: number } | undefined;
    let rollbackPath = "";
    if (CONFIRM_WRITE) {
      const rollbackRows = reports.filter((r) => r.product_name_will_update === "1" || r.sku_will_update === "1");
      rollbackPath = path.join(process.cwd(), "reports", `sync_product_name_lingxing_rollback_${timestamp()}.csv`);
      writeCsv(rollbackPath, rollbackRows);
      writeResult = await writeDimUpdates(db, reports);
    }

    const reportPath = path.join(process.cwd(), "reports", `sync_product_name_lingxing_${timestamp()}.csv`);
    writeCsv(reportPath, reports);

    const stats = buildStats(reports);
    stats.failedBatches = failedBatches;

    console.log("\nSummary:");
    console.log(JSON.stringify({
      total_products: stats.total,
      product_name_matched: stats.matched,
      product_name_will_update: stats.productNameWillUpdate,
      product_name_unchanged: stats.productNameUnchanged,
      product_name_empty_skipped: stats.productNameEmptySkipped,
      unmatched: stats.unmatched,
      true_ambiguous: stats.ambiguous,
      multi_dim_same_lingxing_sku: stats.multiDimSameLingxingSku,
      sku_empty_total: stats.skuEmptyTotal,
      sku_can_update: stats.skuCanUpdate,
      sku_can_update_by_sku_identifier: stats.skuCanUpdateByIdentifier,
      sku_can_update_by_base_sku: stats.skuCanUpdateByBaseSku,
      sku_still_empty: stats.skuStillEmpty,
      base_sku_pattern_audit: {
        sku_nonempty_sample_total: baseSkuAudit.skuNonemptySampleTotal,
        msku_equals_sku_plus_suffix_count: baseSkuAudit.mskuSkuSuffixMatchCount,
        ratio: Number(baseSkuAudit.ratio.toFixed(4)),
        is_valid_for_sku_fill: baseSkuAudit.isValid,
      },
      failed_batches: stats.failedBatches,
      report_csv: reportPath,
      rollback_csv: rollbackPath || null,
      write_result: writeResult ?? null,
    }, null, 2));

    printSamples("Sample matched candidates", reports.filter((r) => r.is_matched === "1"));
    printSamples("Multi dim same Lingxing sku samples", reports.filter((r) => r.is_multi_dim_same_lingxing_sku === "1"));
    printSamples("True ambiguous samples", reports.filter((r) => r.is_ambiguous === "1"));
    printSamples("Unmatched samples", reports.filter((r) => r.is_matched !== "1" && r.is_ambiguous !== "1"));
    printSamples("BaseSku sku-fill allowed samples", reports.filter((r) => r.match_method === "stripped_msku_sku" && r.sku_will_update === "1"));
    printSamples("BaseSku sku-fill not allowed samples", reports.filter((r) => r.match_method === "stripped_msku_sku" && !r.old_sku && r.sku_will_update !== "1"));

    console.log("\nBaseSku pattern mismatch samples:");
    console.table(baseSkuAudit.mismatchSamples.map((row) => ({
      item_id: text(row.item_id),
      msku: text(row.msku),
      sku: text(row.old_sku),
      product_name: text(row.old_product_name),
    })));

    if (DRY_RUN) {
      console.log("\nDRY-RUN completed. No RAW or DIM writes were executed.");
      console.log("Wait for confirmation before running --confirm-write.");
    }
  } finally {
    await db.end();
  }
}

main().catch((err) => {
  console.error(`${SCRIPT_NAME} failed:`, err);
  process.exit(1);
});
