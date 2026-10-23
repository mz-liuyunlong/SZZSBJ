/** Synthetic fixtures only; never used as a business data fallback. */
export const makeInbound = (index = 1, store = "001") => ({
  id: `00000000-0000-4000-8000-${String(index).padStart(12, "0")}`, publication_id: "synthetic-publication",
  source_account_ref: "synthetic-account", source_warehouse_id: "WH-TEST", warehouse_name: "测试惠州仓",
  inbound_order_sn: `IB-${index}`, sku: `SKU-${index}`, product_name: "合成验收商品", store_id: store, store_name: "测试店铺",
  attribution_status: "known" as const, purchase_order_sns: [`PO-${index}`], inbound_at_raw: "2026-10-01 10:00:00",
  inbound_at: "2026-10-01T02:00:00Z", arrival_business_date: "2026-10-01", arrival_source: "inventory_statement" as const,
  arrival_date_status: "known" as const, days_in_warehouse: 19, total_inbound_qty: null, parent_inbound_qty: 100,
  quantity_scope: "inbound_sku" as const, balance_num: index === 1 ? 0 : 40, inventory_status: "known" as const,
  batch_nos: [`B-${index}`], batch_details: [{ batch_no: `B-${index}`, store_id: store, balance_num: index === 1 ? 0 : 40, source_batch_nos: ["B-PREV"], receipt_order_sns: ["RCPT-TEST"] }],
  history_complete: false, source_kind: "inventory_statement" as const,
});
export const previewRow = (index = 1, store = "001") => ({
  ...makeInbound(index, store), inbound_events: [{ statement_id: "123456789012345678", order_sn: `IB-${index}`, sub_type: "2202", product_total: 100, product_qc_num: 100, opt_time: "2026-10-01 10:00:00" }],
});
export async function previewFiles(rows: Record<string, unknown>[] = [previewRow()]) {
  const fields = rows.length ? Object.keys(rows[0]).filter((k) => !["publication_id", "days_in_warehouse"].includes(k)) : ["record_status"];
  const value = (v: unknown) => v === null ? "\\N" : typeof v === "boolean" ? v ? "True" : "False" : typeof v === "object" ? JSON.stringify(v) : String(v);
  const cell = (v: string) => `"${v.replaceAll('"', '""')}"`;
  const csv = "\uFEFF" + [fields, ...rows.map((r) => fields.map((k) => value(r[k])))].map((r) => r.map(cell).join(",")).join("\r\n") + "\r\n";
  const bytes = new TextEncoder().encode(csv).buffer;
  const sha = [...new Uint8Array(await crypto.subtle.digest("SHA-256", bytes))].map((b) => b.toString(16).padStart(2, "0")).join("");
  const manifest = { format_version: 1, complete: true, source: "lingxing_openapi", account: "synthetic-account", warehouse: "WH-TEST",
    start_inclusive: "2026-10-01", end_exclusive: "2026-10-21", source_observed_at: "2026-10-20T02:00:00Z", source_timezone: "Asia/Shanghai",
    csv_null: "\\N", csv_escape: "leading backslash doubled", files: { "inbound_board_preview.csv": { rows: rows.length, sha256: sha } } };
  return { bytes, manifest, text: JSON.stringify(manifest) };
}
