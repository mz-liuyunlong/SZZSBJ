/** WFS preparation contracts; domestic facts retain their original types. */
import type { PackingWarehouseRow } from "../domestic-warehouse/packing/packingWarehouseTypes";
export interface PendingRow {
  order: PackingWarehouseRow; business_test: boolean; occupied_line_ids: string[];
  available_line_ids: string[]; blocked_reasons: string[]; can_edit: boolean;
}
export interface PendingFilters { store_id?: string; keyword: string; only_test: boolean }
export interface PendingSummary {
  completed: number; ready: number; test: number; waiting: number; no_box: number;
  filled_not_done: number; available_boxes: number; available_units: number;
}
export interface ReturnAddress {
  address_line1: string; city: string; state_code: string; postal_code: string; country_code: "US";
}
export interface DraftCommand {
  source_account_ref: string; idempotency_key: string; its: boolean; return_address: ReturnAddress;
  selections: { order_id: string; expected_version: number; expected_box_version: number; box_line_ids: string[] }[];
}
export interface DraftRead {
  id: string; number: string; status: "pending"; store_id: string; business_test: boolean;
  actor_uid: string; created_at: string; payload: { items: unknown[] };
}
export interface IdentityChoice {
  store_id: string; store_name: string | null; item_id: string; gtin: string | null;
  msku: string | null; listing_version: string; cross_store: boolean;
}
export interface IdentityFields {
  target_store_id: string; target_item_id: string; listing_version: string; reason: string;
}
