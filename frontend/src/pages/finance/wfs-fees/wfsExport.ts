/** 导出当前页（原行 + 分摊子行）为 Excel，列同页面。 */
import * as XLSX from "xlsx";
import type { Row } from "./FinanceWfsFeesPage";
import { ATTRIBUTION_TEXT, SOURCE_TEXT } from "./wfsFeesApi";

export function exportLines(rows: Row[], typeName: Map<string, string>) {
  const header = ["店铺", "账单日", "扣费日期", "交易日期", "费用类型", "Fee Type", "Reason", "PO / 货件号", "GTIN", "ITEM ID", "MSKU", "SKU", "数量", "金额（USD）", "归属", "依据", "来源", "说明", "分摊子行"];
  const body: (string | number | null)[][] = [];
  for (const row of rows) {
    const line = (r: Row, child: boolean) => [
      row.storeCode, row.report_date ?? "", row.date_charged, row.transaction_date, typeName.get(row.fee_type) ?? row.fee_type, row.fee_type, row.reason_code,
      r.po_number, r.gtin, r.item_id, r.msku, r.local_sku, r.quantity ? Number(r.quantity) : null, r.amount,
      child ? "分摊" : ATTRIBUTION_TEXT[row.attribution] + (row.adjusted ? " · 人工" : ""), r.allocation_basis || (child ? "" : row.bill_match),
      SOURCE_TEXT[row.fee_source], child ? "" : row.detail, child ? "是" : "",
    ];
    body.push(line(row, false));
    for (const child of row.children ?? []) body.push(line(child, true));
  }
  const sheet = XLSX.utils.aoa_to_sheet([header, ...body]);
  const book = XLSX.utils.book_new();
  XLSX.utils.book_append_sheet(book, sheet, "WFS费用明细");
  XLSX.writeFile(book, `WFS费用明细_${new Date().toISOString().slice(0, 10)}.xlsx`);
}