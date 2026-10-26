/** Column definitions and filter state for the local packing approval API. */
import type { DomesticFilterOptions } from "../domesticWarehouseTypes";

export type PackingApprovalOverdueFilter = "all" | "overdue" | "not_overdue";
export type PackingApprovalArrivalFilter = "all" | "full" | "partial" | "none" | "unknown";
export type PackingApprovalSort = "created_desc" | "created_asc";

export interface PackingApprovalFilters {
  storeIds: string[];
  overdue: PackingApprovalOverdueFilter;
  arrival: PackingApprovalArrivalFilter;
  search: string;
  createdFrom?: string;
  createdTo?: string;
  sort: PackingApprovalSort;
}

export interface PackingApprovalRow {
  id: string;
  packingNumber: string | null;
  inboundOrderSn: string | null;
  purchaseOrderSn: string | null;
  arrivalPurchased: number | null;
  arrivalReceived: number | null;
  arrivalPending: number | null;
  sku: string | null;
  gtin: string | null;
  itemId: string | null;
  msku: string | null;
  storeName: string | null;
  stockQuantity: number | null;
  customsMode: "default" | "declare" | "skip";
  status: "pending" | "approved" | "rejected";
}

export const initialPackingApprovalFilters = (): PackingApprovalFilters => ({
  storeIds: [],
  overdue: "all",
  arrival: "all",
  search: "",
  sort: "created_desc",
});

export const packingApprovalFields = [
  { key: "number", title: "打包单号", width: 150 },
  { key: "draft", title: "草稿号", width: 160 },
  { key: "inbound", title: "入库单号", width: 150 },
  { key: "purchase", title: "采购单号", width: 150 },
  { key: "arrival", title: "到货情况（采购/已到/未到）", width: 200 },
  { key: "sku", title: "SKU", width: 140 },
  { key: "gtin", title: "GTIN（按 ItemID）", width: 170 },
  { key: "item", title: "ItemID", width: 150 },
  { key: "msku", title: "MSKU", width: 130 },
  { key: "store", title: "店铺", width: 170 },
  { key: "qty", title: "备货数量", width: 100 },
  { key: "customs", title: "是否报关", width: 120 },
  { key: "waiting", title: "待审批天数", width: 100 },
  { key: "coverage", title: "历史覆盖", width: 100 },
  { key: "status", title: "状态", width: 100 },
  { key: "actions", title: "操作", width: 96 },
] as const;

export type PackingApprovalFilterOptions = Pick<DomesticFilterOptions, "stores">;
