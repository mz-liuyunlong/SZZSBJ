import { describe, expect, it } from "vitest";
import { previewFiles, previewRow } from "../../../../e2e/fixtures/domesticInbound";
import { readInboundPreview, previewBoard, previewTrace } from "./domesticInboundPreview";
import { initialDomesticFilters } from "./domesticWarehouseTypes";

describe("verified browser-only inbound preview", () => {
  it("preserves text IDs, zero, arrays, dates and trace evidence without a publication", async () => {
    const f = await previewFiles([{ ...previewRow(), product_name: '含逗号,与"引号"\n换行', sku: "000123456789012345678" }]);
    const p = await readInboundPreview(f.bytes, f.text, "2026-10-20");
    expect(p.rows[0].sku).toBe("000123456789012345678"); expect(p.rows[0].balance_num).toBe(0);
    expect(p.rows[0].product_name).toBe('含逗号,与"引号"\n换行'); expect(p.rows[0].days_in_warehouse).toBe(19);
    expect(p.rows[0].publication_id).toBeNull(); expect(previewTrace(p, p.rows[0].id)?.inbound_events[0].statement_id).toBe("123456789012345678");
  });
  it("deduplicates parent quantity across stores and filters the full file before pagination", async () => {
    const a = previewRow(2), b = { ...previewRow(3, "002"), inbound_order_sn: a.inbound_order_sn, sku: a.sku, parent_inbound_qty: a.parent_inbound_qty };
    const f = await previewFiles([a, b]); const p = await readInboundPreview(f.bytes, f.text);
    const board = previewBoard(p, initialDomesticFilters(), 2, 1);
    expect(board.rows).toHaveLength(1); expect(board.total).toBe(2); expect(board.summary.total_inbound_qty).toBe(100);
    expect(board.summary.balance_qty).toBe(80); expect(board.summary.inbound_order_count).toBe(1);
    const store = previewBoard(p, { ...initialDomesticFilters(), storeIds: ["002"] }, 1, 50);
    expect(store.summary.total_inbound_qty).toBe(100); expect(store.summary.balance_qty).toBe(40);
    expect(previewBoard(p, { ...initialDomesticFilters(), searchType: "purchase", search: "PO-20" }, 1, 50).total).toBe(0);
    expect(previewBoard(p, { ...initialDomesticFilters(), searchType: "inbound", batchValues: ["IB-2"] }, 1, 50).total).toBe(2);
  });
  it("keeps unknown quantities unknown and excludes undated rows from date filters", async () => {
    const r = { ...previewRow(), arrival_business_date: null, arrival_date_status: "unknown", arrival_source: "unknown", inbound_at: null,
      inbound_at_raw: null, parent_inbound_qty: null, quantity_scope: "unknown", balance_num: null, inventory_status: "unknown", batch_nos: [], batch_details: [] };
    const f = await previewFiles([r]); const p = await readInboundPreview(f.bytes, f.text);
    const board = previewBoard(p, initialDomesticFilters(), 1, 50);
    expect(board.rows[0].days_in_warehouse).toBeNull(); expect(board.summary.unknown_inbound_qty_count).toBe(1);
    expect(board.summary.unknown_inventory_row_count).toBe(1); expect(board.summary.missing_arrival_date_count).toBe(1);
    expect(previewBoard(p, { ...initialDomesticFilters(), inboundFrom: "2026-10-01" }, 1, 50).total).toBe(0);
  });
  it("accepts a proven successful empty CSV", async () => {
    const f = await previewFiles([]); const p = await readInboundPreview(f.bytes, f.text);
    expect(previewBoard(p, initialDomesticFilters(), 1, 50).total).toBe(0);
  });
  it("rejects incomplete manifests, mismatched hashes/counts/scopes, duplicate rows and quantity conflicts", async () => {
    const f = await previewFiles();
    await expect(readInboundPreview(f.bytes, JSON.stringify({ ...f.manifest, complete: false }))).rejects.toThrow("不完整");
    await expect(readInboundPreview(new TextEncoder().encode("tampered").buffer, f.text)).rejects.toThrow("哈希");
    await expect(readInboundPreview(f.bytes, JSON.stringify({ ...f.manifest, warehouse: "other" }))).rejects.toThrow("仓库");
    const wrongCount = structuredClone(f.manifest); wrongCount.files["inbound_board_preview.csv"].rows = 2;
    await expect(readInboundPreview(f.bytes, JSON.stringify(wrongCount))).rejects.toThrow("行数");
    for (const rows of [[previewRow(), previewRow()], [{ ...previewRow(), balance_num: 10 }],
      [previewRow(), { ...previewRow(2, "002"), inbound_order_sn: "IB-1", sku: "SKU-1", parent_inbound_qty: 200 }]]) {
      const bad = await previewFiles(rows); await expect(readInboundPreview(bad.bytes, bad.text)).rejects.toThrow();
    }
  });
});
