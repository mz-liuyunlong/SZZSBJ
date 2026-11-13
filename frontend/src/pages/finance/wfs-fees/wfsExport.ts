/** 导出当前页为 Excel，列同页面（有分摊的原行按分摊行导出，合计 = 原行）。 */
import * as XLSX from "xlsx";
import type { Row } from "./FinanceWfsFeesPage";
import { ATTRIBUTION_GROUP, ATTRIBUTION_GROUP_TEXT, ATTRIBUTION_TEXT, SOURCE_TEXT, detailText, reasonText } from "./wfsFeesApi";

export function exportLines(rows: Row[], typeName: Map<string, string>) {
  const header = ["店铺", "账单日", "扣费日期", "交易日期", "费用类型", "费用类型（原文）", "原因", "原因（原文）", "订单 / 货件号", "商品条码", "商品 ID", "店铺 SKU", "本地 SKU", "数量", "金额（USD）", "分摊", "归属", "依据", "来源", "说明", "说明（原文）"];
  const body = rows.map((row) => [
    row.storeCode, row.report_date ?? "", row.date_charged, row.transaction_date, typeName.get(row.fee_type) ?? row.fee_type, row.fee_type, reasonText(row.reason_code), row.reason_code,
    row.po_number, row.gtin, row.item_id, row.msku, row.local_sku, row.quantity ? Number(row.quantity) : null, row.amount,
    row.share ?? "", ATTRIBUTION_GROUP_TEXT[ATTRIBUTION_GROUP[row.attribution]] + (row.adjusted ? " · 人工" : ""),
    [ATTRIBUTION_TEXT[row.attribution], row.shareBasis || row.allocation_basis, row.bill_match].filter(Boolean).join(" · "),
    SOURCE_TEXT[row.fee_source], detailText(row.detail), row.detail,
  ]);
  const sheet = XLSX.utils.aoa_to_sheet([header, ...body]);
  const book = XLSX.utils.book_new();
  XLSX.utils.book_append_sheet(book, sheet, "WFS费用明细");
  XLSX.writeFile(book, `WFS费用明细_${new Date().toISOString().slice(0, 10)}.xlsx`);
}
