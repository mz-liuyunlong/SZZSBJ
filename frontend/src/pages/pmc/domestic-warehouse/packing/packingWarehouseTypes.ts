/** Warehouse-only contracts; reference stock is not a second allocation. */
export type PackingWarehouseStatus = "todo" | "packed" | "all";
export type PackingWarehouseSort = "approved_desc" | "approved_asc";
export interface PackingWarehouseFilters { exception?: "overpack"; storeId?: string; status: PackingWarehouseStatus; search: string; approvedFrom?: string; approvedTo?: string; sort: PackingWarehouseSort }
export const initialPackingWarehouseFilters = (): PackingWarehouseFilters => ({ status: "todo", search: "", sort: "approved_desc" });
export const noteCategories = [{ value: "arrival_incomplete", label: "到货不齐" }, { value: "labels", label: "等标签" }, { value: "materials", label: "等包材" }, { value: "operations", label: "等运营确认" }, { value: "schedule", label: "仓库排期" }, { value: "quality", label: "质检问题" }, { value: "other", label: "其他" }, { value: "resolved", label: "已处理" }] as const;
export type NoteCategory = typeof noteCategories[number]["value"];
export interface PackageData { length_cm: number | string; width_cm: number | string; height_cm: number | string; gross_weight_g: number | string; net_weight_g?: number | string | null }
export interface BoxInput { box_type: "A" | "B" | "C" | "custom"; boxes: number; units_per_box: number; gross_weight_kg: number | string; length_cm?: number | string | null; width_cm?: number | string | null; height_cm?: number | string | null }
export interface BoxLine extends BoxInput { id: string; line_no: number }
export interface PackingWarehouseRow {
  id: string; source_account_ref: string; version: number; pk: string; is_test: boolean; approved_at: string; approved_date: string;
  inbound_order_sn: string; inbound_date: string | null; arrival_date: string | null; arrival_status: "inbound_date" | "unknown";
  warehouse_days: number | null; received_dates: string[]; receipt_order_sns: string[]; purchase_order_sns: string[];
  sku: string; product_name: string | null; store_id: string | null; store_name: string | null; item_id: string | null; gtin: string | null; msku: string | null;
  approved_quantity: number; stock_balance: number | null; balance_publication_id: string | null; balance_observed_at: string | null;
  status: "todo" | "packed"; packing_days: number; customs_value: boolean | null; customs_src: string;
  product_requirement: { state: "complete" | "missing" | "unknown"; version: string; source_snapshot_id: string | null; package: PackageData | null; reason: string | null };
  box_set: { id: string; version: number; total_qty: number; variance_qty: number; variance_reason: string | null; lines: BoxLine[]; completed_at: string | null; completed_by: string | null; package_snapshot: { source?: string; values?: PackageData } | null } | null;
  current_note: { category: NoteCategory; category_label: string; text: string; resolved: boolean; actor_uid: string; updated_at: string } | null;
  variance_case?: { kind: "under" | "over"; state: string; quantity: number; gap_qty: number | null; reason_category: string | null; reason: string | null; supplemental_ib: string | null; last_sync_code?: string | null; last_sync_gap?: number | null; notification_state?: string | null; proposed_lines?: BoxInput[] | null } | null;
  extra_allocations?: { source_publication_id: string; source_board_id: string; inbound_order_sn: string; quantity: number }[];
  extra_available?: number | null; extra_publication_id?: string | null; command_outcome?: "saved" | "completed" | "blocked" | "ready" | null;
  can_complete: boolean; completion_blocked_reasons: string[]; shipment_status: "not_connected"; boxspec_sync_status: "not_connected";
}
export interface WarehouseBase { source_account_ref: string; expected_version: number; idempotency_key: string }
export type WarehouseAction = "boxes" | "done" | "customs" | "notes" | "unpacked" | "rebox" | "supplemental-inbound" | "supplemental-sync";
export interface WarehouseFields { inbound_order_sn?: string; action?: "resend" | "void"; lines?: BoxInput[]; reason?: string; package?: PackageData; value?: boolean; category?: NoteCategory; text?: string; reason_category?: "shortage" | "damage" | "box_capacity" | "other"; confirm_extra?: boolean; expected_box_version?: number; requirement_version?: string }
export interface WarehouseEvent { id: string; kind: string; actor_uid: string; order_version: number; occurred_at: string; reason: string | null; before: Record<string, unknown> | null; result: Record<string, unknown> }
export const packingWarehouseFields = [
  { key: "approved", title: "审批日期", width: 120 }, { key: "number", title: "打包单", width: 160 },
  { key: "arrival", title: "到仓日期（入库日）", width: 150 }, { key: "received", title: "实际收货日", width: 140 },
  { key: "inbound", title: "入库单号", width: 150 }, { key: "purchase", title: "采购单号", width: 150 },
  { key: "sku", title: "SKU / 产品", width: 170 }, { key: "store", title: "店铺", width: 140 },
  { key: "item", title: "ItemID / MSKU", width: 180 }, { key: "gtin", title: "GTIN", width: 170 },
  { key: "quantity", title: "审批 / 装箱 / 余额", width: 150 }, { key: "boxes", title: "装箱数据", width: 240 },
  { key: "status", title: "状态", width: 130 }, { key: "days", title: "打包 / 在仓天数", width: 130 },
  { key: "customs", title: "是否报关", width: 110 }, { key: "package", title: "单品包装 / 毛重", width: 190 },
  { key: "note", title: "延迟备注", width: 180 }, { key: "labels", title: "产品标签", width: 100 },
  { key: "actions", title: "操作", width: 340 },
] as const;
