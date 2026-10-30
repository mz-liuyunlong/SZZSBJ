export type ShipmentKeywordField = "shipment" | "pk" | "msku" | "sku" | "item" | "gtin";

export interface ShipmentBoardFilters {
  store_id?: string;
  keyword: string;
  keyword_field: ShipmentKeywordField;
  only_test: boolean;
}

export interface ShipmentBoardRow {
  id: string;
  shipment_id: string;
  operation_id: string;
  ticket_id: string;
  ticket_number: number;
  order_id: string;
  pk: string;
  store_id: string;
  store_name?: string | null;
  sku?: string | null;
  product_name?: string | null;
  item_id?: string | null;
  gtin?: string | null;
  msku?: string | null;
  business_test: boolean;
  its: boolean;
  label_state: "PENDING" | "READY" | "FAILED";
  creation_state: string;
  ticket_state: string;
  lingxing_sync_status: "PENDING";
  declared_units: number | null;
  shipped_units: number | null;
  received_units: number | null;
  created_at: string;
}

export interface ShipmentBoardDetail extends ShipmentBoardRow {
  return_address?: Record<string, string> | null;
  expected_delivery_at?: string | null;
  allocation?: Record<string, unknown> | null;
  lingxing_note: string;
}

export interface ShipmentBoardSummary {
  total: number;
  pending_lingxing_sync: number;
  test: number;
}
