/** File-only preview. Nothing here uploads data or persists business rows. */
import type { BatchComponent, DomesticBatch, DomesticFilters, DomesticSummary, DomesticTrace, InboundEvent } from "./domesticWarehouseTypes";

export interface PreviewManifest {
  format_version: number; complete: boolean; source: string; account: string; warehouse: string;
  start_inclusive: string; end_exclusive: string; source_observed_at: string; source_timezone: string | null;
  files: Record<string, { rows: number; sha256: string }>;
}
export interface InboundPreview {
  manifest: PreviewManifest; rows: DomesticBatch[]; traces: Map<string, InboundEvent[]>;
}
const invalid = (detail: string): never => { throw new Error(`无法加载 CSV：${detail}`); };
const isRecord = (value: unknown): value is Record<string, unknown> => typeof value === "object" && value !== null && !Array.isArray(value);
const textId = (value: unknown): string => typeof value === "string" && value.trim() && value.length <= 255 ? value : invalid("来源标识为空或超长");
const nullableText = (value: unknown): string | null => value === null ? null : typeof value === "string" ? value : invalid("文本字段格式不符");
const integer = (value: unknown): number | null => {
  if (value === null) return null;
  if ((typeof value !== "string" && typeof value !== "number") || !/^-?\d+$/.test(String(value))) return invalid("数量不是整数");
  const n = Number(value);
  return Number.isSafeInteger(n) && n >= -2147483648 && n <= 2147483647 ? n : invalid("数量超出范围");
};
const strings = (value: unknown): string[] => Array.isArray(value) ? value.map(textId) : invalid("数组字段格式不符");
const choice = <T extends string>(value: unknown, choices: readonly T[]): T => choices.includes(value as T) ? value as T : invalid("枚举字段格式不符");
const boolean = (value: unknown): boolean => value === "True" || value === true ? true : value === "False" || value === false ? false : invalid("布尔字段格式不符");
function date(value: unknown): string | null {
  if (value === null) return null;
  if (typeof value !== "string" || !/^\d{4}-\d{2}-\d{2}$/.test(value) || !Number.isFinite(Date.parse(value)) || new Date(value).toISOString().slice(0, 10) !== value) return invalid("业务日期格式不符");
  return value;
}
const timestamp = (value: unknown): string => typeof value === "string" && /(?:Z|[+-]\d{2}:\d{2})$/.test(value) && Number.isFinite(Date.parse(value)) ? value : invalid("采集时间缺少有效时区");
export const taipeiToday = () => new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Taipei", year: "numeric", month: "2-digit", day: "2-digit" }).format(new Date());
function normalizeRow(raw: Record<string, unknown>, asOf: string): { row: DomesticBatch; events: InboundEvent[] } {
  const arrival = date(raw.arrival_business_date);
  const balance = integer(raw.balance_num);
  const parent = integer(raw.parent_inbound_qty);
  const details = raw.batch_details;
  if (!Array.isArray(details) || !Array.isArray(raw.inbound_events)) return invalid("缺少批次组成或入库流水");
  const batchDetails: BatchComponent[] = details.map((v: unknown) => {
    if (!isRecord(v)) return invalid("批次组成无效");
    return { batch_no: textId(v.batch_no), store_id: nullableText(v.store_id), balance_num: integer(v.balance_num),
      source_batch_nos: strings(v.source_batch_nos), receipt_order_sns: strings(v.receipt_order_sns) };
  });
  const events: InboundEvent[] = raw.inbound_events.map((v: unknown) => {
    if (!isRecord(v)) return invalid("入库流水无效");
    if (typeof v.statement_id === "number" && !Number.isSafeInteger(v.statement_id)) return invalid("流水 ID 超出精确范围，请以文本 ID 重新采集");
    return { statement_id: v.statement_id == null ? null : textId(String(v.statement_id)),
      order_sn: nullableText(v.order_sn), sub_type: v.sub_type == null ? null : String(v.sub_type),
      product_total: integer(v.product_total), product_qc_num: integer(v.product_qc_num), opt_time: nullableText(v.opt_time) };
  });
  const row: DomesticBatch = {
    id: textId(raw.id), publication_id: null, source_account_ref: textId(raw.source_account_ref), source_warehouse_id: textId(raw.source_warehouse_id),
    warehouse_name: nullableText(raw.warehouse_name), inbound_order_sn: textId(raw.inbound_order_sn), sku: textId(raw.sku),
    product_name: nullableText(raw.product_name) ?? "", store_id: nullableText(raw.store_id), store_name: nullableText(raw.store_name),
    attribution_status: choice(raw.attribution_status, ["known", "unknown"]), purchase_order_sns: strings(raw.purchase_order_sns),
    inbound_at_raw: nullableText(raw.inbound_at_raw), inbound_at: raw.inbound_at === null ? null : timestamp(raw.inbound_at),
    arrival_business_date: arrival, arrival_source: choice(raw.arrival_source, ["inventory_statement", "batch_fallback", "unknown"]),
    arrival_date_status: choice(raw.arrival_date_status, ["known", "unknown"]),
    days_in_warehouse: arrival === null ? null : Math.round((Date.parse(asOf) - Date.parse(arrival)) / 86400000),
    total_inbound_qty: integer(raw.total_inbound_qty), parent_inbound_qty: parent, quantity_scope: choice(raw.quantity_scope, ["inbound_sku", "unknown"]),
    balance_num: balance, inventory_status: choice(raw.inventory_status, ["known", "unknown"]), batch_nos: strings(raw.batch_nos), batch_details: batchDetails,
    history_complete: boolean(raw.history_complete), source_kind: choice(raw.source_kind, ["inventory_statement", "batch_backfill"]),
  };
  if ((row.inventory_status === "known") !== (balance !== null) || (row.arrival_date_status === "known") !== (arrival !== null)
    || (row.quantity_scope === "inbound_sku") !== (parent !== null) || (row.attribution_status === "known") !== Boolean(row.store_id)
    || row.total_inbound_qty !== null) return invalid("数量、日期或归属状态与字段不一致");
  if (batchDetails.some((b) => b.store_id !== row.store_id) || new Set(row.batch_nos).size !== row.batch_nos.length
    || row.batch_nos.length !== batchDetails.length || batchDetails.some((b) => !row.batch_nos.includes(b.batch_no))) return invalid("批次组成与行不一致");
  const componentBalance = batchDetails.length && batchDetails.every((b) => b.balance_num !== null)
    ? batchDetails.reduce((sum, b) => sum + b.balance_num!, 0) : null;
  if (componentBalance !== balance) return invalid("批次余额合计与行不一致");
  return { row, events };
}

/** Requires the untouched generated CSV and its successful manifest from the same directory. */
export async function readInboundPreview(csvBytes: ArrayBuffer, manifestText: string, asOf = taipeiToday()): Promise<InboundPreview> {
  if (csvBytes.byteLength > 20 * 1024 * 1024 || manifestText.length > 1024 * 1024) return invalid("文件过大（CSV 上限 20 MiB，清单上限 1 MiB）");
  let m: unknown;
  try { m = JSON.parse(manifestText); } catch { return invalid("manifest.json 无法解析"); }
  if (!isRecord(m) || m.format_version !== 1 || m.complete !== true || m.source !== "lingxing_openapi"
    || m.csv_null !== "\\N" || m.csv_escape !== "leading backslash doubled" || !isRecord(m.files)) return invalid("采集清单不完整或版本不支持");
  const start = date(m.start_inclusive), end = date(m.end_exclusive);
  if (!start || !end || start >= end) return invalid("采集日期范围无效");
  textId(m.account); textId(m.warehouse); timestamp(m.source_observed_at);
  const file = m.files["inbound_board_preview.csv"];
  if (!isRecord(file) || typeof file.rows !== "number" || !Number.isInteger(file.rows) || file.rows < 0 || file.rows > 50000
    || typeof file.sha256 !== "string" || !/^[a-f0-9]{64}$/.test(file.sha256)) return invalid("预览文件清单无效或超过 50,000 行");
  const hash = Array.from(new Uint8Array(await crypto.subtle.digest("SHA-256", csvBytes)), (b) => b.toString(16).padStart(2, "0")).join("");
  if (hash !== file.sha256) return invalid("CSV 哈希与清单不符，请选择同一次采集的原始文件");
  const { read, utils } = await import("xlsx");
  const book = read(new TextDecoder("utf-8", { fatal: true }).decode(csvBytes).replace(/^\uFEFF/, ""), {
    type: "string", raw: true, cellFormula: false, FS: ",", sheetRows: 50002,
  });
  const grid = utils.sheet_to_json<string[]>(book.Sheets[book.SheetNames[0]], { header: 1, raw: true, defval: "", blankrows: false });
  const headers = grid.shift() ?? [];
  if (new Set(headers).size !== headers.length || grid.length !== file.rows) return invalid("CSV 表头重复或行数与清单不符");
  const traces = new Map<string, InboundEvent[]>();
  const rows: DomesticBatch[] = [];
  const identities = new Set<string>(), parents = new Map<string, number | null>(), stocks = new Map<string, number | null>();
  for (const cells of grid) {
    if (cells.length !== headers.length) return invalid("CSV 列数不一致");
    const raw: Record<string, unknown> = {};
    for (const [i, key] of headers.entries()) {
      const v = cells[i];
      if (v === "\\N") raw[key] = null;
      else if (["purchase_order_sns", "batch_nos", "batch_details", "inbound_events"].includes(key)) {
        try { raw[key] = JSON.parse(v); } catch { return invalid("数组内容无法解析"); }
      } else raw[key] = v.startsWith("\\\\") ? v.slice(1) : v;
    }
    const { row, events } = normalizeRow(raw, asOf);
    if (row.source_account_ref !== m.account || row.source_warehouse_id !== m.warehouse) return invalid("账号或仓库与清单不一致");
    const parentKey = JSON.stringify([row.source_account_ref, row.source_warehouse_id, row.inbound_order_sn, row.sku]);
    const identity = JSON.stringify([parentKey, row.store_id]);
    if (traces.has(row.id) || identities.has(identity)) return invalid("存在重复的入库展示行");
    if (parents.has(parentKey) && parents.get(parentKey) !== row.parent_inbound_qty) return invalid("同一入库单 SKU 的父数量冲突");
    parents.set(parentKey, row.parent_inbound_qty); identities.add(identity);
    for (const b of row.batch_details) {
      const key = stockKey(row, b);
      if (stocks.has(key)) return invalid("库存批次身份重复，请核对来源");
      stocks.set(key, b.balance_num);
    }
    rows.push(row); traces.set(row.id, events);
  }
  return { manifest: m as unknown as PreviewManifest, rows, traces };
}
const parentKey = (r: DomesticBatch) => JSON.stringify([r.source_account_ref, r.source_warehouse_id, r.inbound_order_sn, r.sku]);
const stockKey = (r: DomesticBatch, b: BatchComponent) => JSON.stringify([r.source_account_ref, r.source_warehouse_id, b.batch_no, r.sku, r.store_id]);

export function previewBoard(dataset: InboundPreview, filters: DomesticFilters, page: number, pageSize: number, asOf = taipeiToday()) {
  const values = filters.batchValues?.length ? filters.batchValues : filters.search.trim() ? [filters.search.trim()] : [];
  const rows = dataset.rows.filter((r) => (!filters.storeIds.length || (r.store_id !== null && filters.storeIds.includes(r.store_id)))
    && (!filters.warehouseIds.length || filters.warehouseIds.includes(r.source_warehouse_id))
    && (!filters.inventoryStatus || r.inventory_status === filters.inventoryStatus)
    && (!filters.inboundFrom || (r.arrival_business_date !== null && r.arrival_business_date >= filters.inboundFrom))
    && (!filters.inboundTo || (r.arrival_business_date !== null && r.arrival_business_date <= filters.inboundTo))
    && (!values.length || (filters.searchType === "sku" ? values.includes(r.sku)
      : filters.searchType === "inbound" ? values.includes(r.inbound_order_sn)
      : filters.searchType === "purchase" ? r.purchase_order_sns.some((v) => values.includes(v))
      : [r.sku, r.inbound_order_sn, ...r.purchase_order_sns, ...r.batch_nos].some((v) => v.includes(values[0])))));
  rows.sort((a, b) => {
    const av = filters.sort === "balance_desc" ? a.balance_num : a.arrival_business_date;
    const bv = filters.sort === "balance_desc" ? b.balance_num : b.arrival_business_date;
    if (av === null && bv !== null) return 1;
    if (bv === null && av !== null) return -1;
    const delta = av === bv ? 0 : av! < bv! ? -1 : 1;
    return delta * (filters.sort === "inbound_date_asc" ? 1 : -1) || a.id.localeCompare(b.id);
  });
  const parents = new Map(rows.map((r) => [parentKey(r), r.parent_inbound_qty]));
  const stocks = new Map(rows.flatMap((r) => r.batch_details.map((b) => [stockKey(r, b), b.balance_num] as const)));
  const summary: DomesticSummary = {
    board_row_count: rows.length, inbound_order_count: new Set(rows.map((r) => JSON.stringify([r.source_account_ref, r.source_warehouse_id, r.inbound_order_sn]))).size,
    sku_count: new Set(rows.map((r) => r.sku)).size, balance_qty: [...stocks.values()].reduce<number>((s, v) => s + (v ?? 0), 0),
    unknown_inventory_row_count: rows.filter((r) => r.balance_num === null).length,
    total_inbound_qty: [...parents.values()].reduce<number>((s, v) => s + (v ?? 0), 0), unknown_inbound_qty_count: [...parents.values()].filter((v) => v === null).length,
    missing_arrival_date_count: rows.filter((r) => r.arrival_business_date === null).length, as_of: asOf,
  };
  return { rows: rows.slice((page - 1) * pageSize, page * pageSize), total: rows.length, summary };
}
export function previewTrace(dataset: InboundPreview, id?: string): DomesticTrace | undefined {
  const batch = dataset.rows.find((r) => r.id === id);
  return batch ? { batch, inbound_events: dataset.traces.get(batch.id) ?? [], outbound_status: "unknown", outbound_reason: "source_not_published" } : undefined;
}
