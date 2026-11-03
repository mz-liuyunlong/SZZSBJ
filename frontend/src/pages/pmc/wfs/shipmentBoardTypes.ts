export type ShipmentKeywordField = "shipment" | "inbound" | "pk" | "msku" | "sku" | "item" | "gtin" | "shipping";
export type LingxingSync = "SYNCED" | "PENDING";
export type ArrivalBucket = "overdue" | "d15" | "d30" | "d60" | "d60_plus" | "none";
export type EtaSource = "real" | "plan" | "region";

export interface ShipmentBoardFilters {
  store_id?: string;
  keyword: string;
  keyword_field: ShipmentKeywordField;
  only_test: boolean;
  status?: number;
  sync?: LingxingSync;
  owner?: string;
  region?: string;
  arrival_bucket?: ArrivalBucket;
  only_exceptions?: boolean;
  only_external?: boolean;
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
  // 8088 derived view (computed when read, rule version WFS-RULES-20261010)
  owners?: string[];
  region?: string | null;
  its_inferred?: boolean;
  baseline_units?: number | null;
  baseline_from?: "SP" | "declare" | null;
  diff_units?: number | null;
  boxes?: number | null;
  eta?: string | null;
  eta_source?: EtaSource | null;
  eta_source_label?: string | null;
  eta_passed_days?: number | null;
  sellable_date?: string | null;
  sellable_real?: boolean;
  arrival_bucket?: ArrivalBucket | null;
  shipped_out?: boolean;
  carrier_delivered_at?: string | null;
  walmart_signed_date?: string | null;
  walmart_first_receipt?: string | null;
  walmart_last_receipt?: string | null;
  walmart_receiving?: boolean;
  walmart_done?: boolean;
  d0?: string | null;
  d0_real?: boolean;
  days_since_d0?: number | null;
  external?: boolean;
  age_days?: number | null;
  exception_types?: string[];
}

export interface ShipmentItemLine {
  msku: string;
  sku: string;
  product_name: string;
  gtin: string;
  item_id?: string | null;
  owners: string[];
  declared_units: number;
  shipped_units: number;
  lingxing_received_units: number;
  walmart_received_units?: number | null;
  put_away_units?: number | null;
  damaged_units: number;
  normal_units: number;
  over_units: number;
  abnormal_units?: number | null;
  abnormal: boolean;
}

export interface ShipmentException {
  type: string;
  rule_family: string;
  severity: "high" | "mid" | "low";
  found?: string | null;
  description: string;
  source: "real" | "calc" | "demo";
  qty?: number | null;
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
  items?: ShipmentItemLine[];
  exceptions?: ShipmentException[];
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
  by_arrival_bucket?: Record<string, number>;
  with_exceptions?: number;
  external?: number;
  rule_version?: string;
  freshness: BoardFreshness;
}

export interface ProductShipmentLine {
  shipment_id: string;
  status_name: string;
  msku: string;
  shipped_units: number;
  signed_units: number;
  shelved_units: number;
  eta?: string | null;
  eta_source?: EtaSource | null;
  sellable_date?: string | null;
  sellable_real: boolean;
  bucket: string;
  region?: string | null;
}

/** 8088 产品维度：店铺 × Item ID，已发货未可售件数按预计可售日分段。 */
export interface ProductBoardRow {
  id: string;
  store_id: string;
  store_name?: string | null;
  item_id: string;
  mskus: string[];
  skus: string[];
  product_name?: string | null;
  shipments: number;
  in_transit_units: number;
  buckets: Record<string, number>;
  signed_not_put_units: number;
  arrived_shipped_units: number;
  arrived_signed_units: number;
  arrived_shelved_units: number;
  receiving_gap_units: number;
  signed_zero_shelved: number;
  next_eta?: string | null;
  next_sellable?: string | null;
  lines: ProductShipmentLine[];
}

export const ARRIVAL_BUCKETS: { value: ArrivalBucket; label: string }[] = [
  { value: "overdue", label: "已过预计可售日未上架" },
  { value: "d15", label: "15 天内可售" },
  { value: "d30", label: "15–30 天可售" },
  { value: "d60", label: "30–60 天可售" },
  { value: "d60_plus", label: "超过 60 天可售" },
  { value: "none", label: "无预计日期" },
];

export const ETA_SOURCE_TEXT: Record<EtaSource, string> = { real: "真实", plan: "预计", region: "地区兜底" };

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
