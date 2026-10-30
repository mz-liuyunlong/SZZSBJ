export type ShipmentKeywordField = "shipment" | "inbound" | "pk" | "msku" | "sku" | "item" | "gtin" | "shipping";
export type LingxingSync = "SYNCED" | "PENDING";

export interface ShipmentBoardFilters {
  store_id?: string;
  keyword: string;
  keyword_field: ShipmentKeywordField;
  only_test: boolean;
  status?: number;
  sync?: LingxingSync;
}

export interface BoardFreshness {
  publication_id?: string | null;
  source_observed_at?: string | null;
  published_at?: string | null;
  coverage_start?: string | null;
  coverage_end?: string | null;
  stale: boolean;
}

export interface ShipmentBoardRow {
  id: string;
  source: "lingxing" | "creation_only";
  shipment_id: string;
  inbound_order_id?: string | null;
  store_id: string;
  store_name?: string | null;
  status?: number | null;
  status_name?: string | null;
  status_label: string;
  cargo_sync_status?: string | null;
  lingxing_sync_status: LingxingSync;
  business_test: boolean;
  its?: boolean | null;
  pk?: string | null;
  sku?: string | null;
  product_name?: string | null;
  item_id?: string | null;
  gtin?: string | null;
  msku?: string | null;
  sku_count: number;
  declared_units: number | null;
  shipped_units: number | null;
  received_units: number | null;
  damaged_units: number | null;
  logistics_code?: string | null;
  shipping_codes: string[];
  shipping_status?: string | null;
  warehouse_id?: string | null;
  actual_delivery_date?: string | null;
  arrival_date?: string | null;
  expected_arrival_date?: string | null;
  logistics_numbers: string[];
  created_at?: string | null;
  updated_at?: string | null;
  to_await_at?: string | null;
  to_receive_at?: string | null;
  to_closed_at?: string | null;
  to_cancelled_at?: string | null;
  operation_id?: string | null;
  ticket_id?: string | null;
  ticket_number?: number | null;
  order_id?: string | null;
  label_state?: "PENDING" | "READY" | "FAILED" | null;
  creation_state?: string | null;
  ticket_state?: string | null;
}

export interface ShipmentGoodsLine {
  msku?: string | null;
  sku?: string | null;
  product_name?: string | null;
  gtin?: string | null;
  declare_num?: number | null;
  shipments_num?: number | null;
  received_num?: number | null;
  damaged_qty?: number | null;
}

export interface ShipmentBoardDetail extends ShipmentBoardRow {
  goods: ShipmentGoodsLine[];
  shipping_lists: Record<string, unknown>[];
  distribution_addresses?: string | null;
  return_addresses?: string | null;
  creator?: string | null;
  country_name?: string | null;
  return_address?: Record<string, string> | null;
  expected_delivery_at?: string | null;
  allocation?: Record<string, unknown> | null;
  lingxing_note?: string | null;
}

export interface ShipmentBoardSummary {
  total: number;
  by_status: Record<string, number>;
  pending_lingxing_sync: number;
  test: number;
  received_short: number;
  freshness: BoardFreshness;
}

export interface ProductBoardRow {
  id: string;
  store_id: string;
  store_name?: string | null;
  msku?: string | null;
  sku?: string | null;
  product_name?: string | null;
  gtin?: string | null;
  shipments: number;
  declared_units: number | null;
  shipped_units: number | null;
  received_units: number | null;
  damaged_units: number | null;
  in_transit_units: number | null;
}

export const STATUS_OPTIONS: { value: number; label: string }[] = [
  { value: 0, label: "待发货" },
  { value: 1, label: "在途" },
  { value: 2, label: "收货中" },
  { value: 3, label: "已关闭" },
  { value: 4, label: "已取消" },
];

export const STATUS_TONE: Record<string, string> = {
  "0": "default",
  "1": "processing",
  "2": "warning",
  "3": "success",
  "4": "error",
};
