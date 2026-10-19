/** Frontend display model only; no packing API contract or business persistence is implied. */
export type PackingWarehouseStatus = "todo" | "packed" | "all";
export type PackingWarehouseSort = "approved_desc" | "approved_asc" | "received_desc" | "received_asc";

export interface PackingWarehouseFilters {
  storeId?: string;
  status: PackingWarehouseStatus;
  search: string;
  approvedFrom?: string;
  approvedTo?: string;
  sort: PackingWarehouseSort;
}

export interface PackingWarehouseRow {
  id: string;
  approvedDate: string | null;
  packingNumber: string | null;
  source: "system" | "lingxing_manual";
  receipts: { receiptOrderSn: string; receivedDate: string | null }[];
  inboundOrderSns: string[];
  purchaseOrderSns: string[];
  sku: string | null;
  productName: string | null;
  storeName: string | null;
  itemId: string | null;
  msku: string | null;
  gtin: string | null;
  approvedQuantity: number | null;
  status: "todo" | "packed";
}

export const initialPackingWarehouseFilters = (): PackingWarehouseFilters => ({
  status: "todo", search: "", sort: "approved_desc",
});

export const packingWarehouseFields = [
  { key: "approved", title: "审批日期", width: 126 },
  { key: "number", title: "打包单", width: 170 },
  { key: "received", title: "到仓日期", width: 140 },
  { key: "inbound", title: "入库单号", width: 160 },
  { key: "purchase", title: "采购单号", width: 160 },
  { key: "sku", title: "SKU", width: 180 },
  { key: "store", title: "店铺", width: 170 },
  { key: "item", title: "ItemID", width: 190 },
  { key: "gtin", title: "GTIN", width: 160 },
  { key: "labels", title: "产品标签", width: 126 },
  { key: "actions", title: "操作", width: 210 },
] as const;
