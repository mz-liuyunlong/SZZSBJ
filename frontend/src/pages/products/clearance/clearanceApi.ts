import { backendRequest } from "@/api/backendApi";

export type RiskLevel = "high" | "medium" | "low" | "unknown";
export type CandidateStatus = "auto" | "observe" | "none" | "review_required";
export type ClearanceMethod = "降价" | "促销" | "广告清货" | "WFS 移除" | "弃置";

export interface ClearanceListing {
  id: string;
  source_account_ref: string;
  store_id: string;
  store_name: string | null;
  item_id: string;
  local_sku: string | null;
  msku: string | null;
  title: string | null;
  picture_url: string | null;
  owner_ref: string | null;
  listing_status: string | null;
  sale_price_amount: string | null;
  sale_price_currency_code: string | null;
  wfs_available_quantity: string | null;
  snapshot_wfs_available: string | null;
  inventory_captured_at: string | null;
  inbound_quantity: string | null;
  average_rating: string | null;
  review_count: number | null;
  buybox_status: string | null;
  listing_start_at_utc: string | null;
}
export interface ClearanceEvaluation {
  risk_level: RiskLevel;
  candidate_status: CandidateStatus;
  coverage_days: number | null;
  current_wfs_available: string | null;
  inventory_captured_at: string | null;
  stock_capital_usd: string | null;
  unit_cost_usd: string | null;
  high_stock_capital?: boolean;
  conflict_alerts?: string[];
  profit_30d_amount?: string | null;
  refund_loss_30d?: string | null;
  sales_30d: string | null;
  margin_30d_percent: string | null;
  refund_rate_percent: string | null;
  suggested_qty: number | null;
  positive_stock_days_30d: number;
  snapshot_coverage_days_30d: number;
  business_signal_groups: string[];
  risk_reasons: string[];
  protections: string[];
  warnings: string[];
  sales_complete: boolean;
  source_sales_coverage_days_30d?: number;
  cost_complete: boolean;
  rule_version: string;
  as_of_date: string;
}
export interface ClearanceRow {
  listing: ClearanceListing;
  evaluation: ClearanceEvaluation;
  rule_config_version: number;
}
export interface ClearancePage<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
  evaluation_status?: "ready" | "not_ready" | "live_wfs";
  run_date_la?: string | null;
  as_of_date_la?: string | null;
}
export interface ClearanceSummary {
  total: number;
  high: number;
  medium: number | null;
  observe: number | null;
  review_required: number | null;
  eligible_manual: number;
  evaluation_status: "ready" | "not_ready";
  run_date_la: string | null;
  as_of_date_la: string | null;
}
export interface ClearanceFacets {
  stores: {source_account_ref: string; store_id: string; store_name: string | null}[];
  accounts: string[];
}
export interface ClearanceReadiness {
  evaluation_status: "ready" | "not_ready";
  run_date_la: string | null;
  as_of_date_la: string | null;
  total_listings: number;
  evaluated_listings: number;
  not_evaluated_listings: number;
  missing_sales_window: number | null;
  missing_wfs_stock: number | null;
  missing_profit_cost: number | null;
  sales_source_30day_covered?: number;
  refund_period_data_complete: boolean;
}
export type ClearanceStatus =
  | "pending" | "approved" | "rejected" | "withdrawn"
  | "running" | "paused" | "done";
export interface ClearanceRequest {
  id: string;
  listing_id: string;
  approval_id: string;
  source_account_ref: string;
  store_id: string;
  item_id: string;
  requester_id: string;
  target_qty: number;
  methods: ClearanceMethod[];
  reason: string;
  remark: string;
  due_date: string | null;
  source: "manual" | "auto";
  risk_level: "high" | "medium" | "low";
  status: ClearanceStatus;
  sold_qty: number;
  removed_qty: number;
  disposed_qty: number;
  version: number;
  created_at: string;
  updated_at: string;
}
export interface ClearanceRequestDetail {
  request: ClearanceRequest;
  current: ClearanceRow;
  events: { event_type: string; actor_id: string; note: string | null; created_at: string }[];
}
export interface ClearanceRules {
  source_account_ref: string;
  version: number;
  rules: Record<string, number | boolean>;
}
export interface ClearanceApplication {
  listing_id: string;
  target_qty: number;
  methods: ClearanceMethod[];
  reason: string;
  remark: string;
  due_date?: string | null;
  proposed_price?: string | null;
  source: "manual" | "auto";
}

const API = "/api/products/clearance-center";
const params = (query: Record<string, string | number | null | undefined>) => {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(query)) {
    if (value !== undefined && value !== null && value !== "") search.set(key, String(value));
  }
  return "?" + search.toString();
};
const get = async <T,>(path: string): Promise<T> => (await backendRequest<T, null>(API + path)).data;
const write = async <T,>(path: string, method: "POST" | "PUT", body: unknown): Promise<T> =>
  (await backendRequest<T, null>(API + path, {method, body: JSON.stringify(body)})).data;

export const fetchClearanceListings = (query: Record<string, string | number | undefined> = {}) =>
  get<ClearancePage<ClearanceRow>>("/listings" + params(query));
export const fetchEligibleListings = (query: Record<string, string | number | undefined> = {}) =>
  get<ClearancePage<ClearanceRow>>("/eligible-listings" + params(query));
export const fetchClearanceFacets = () => get<ClearanceFacets>("/facets");
export const fetchClearanceSummary = (store_id?: string) =>
  get<ClearanceSummary>("/summary" + params({store_id}));
export const fetchClearanceReadiness = (store_id?: string) =>
  get<ClearanceReadiness>("/data-readiness" + params({store_id}));
export const fetchClearanceDetail = (listingId: string) =>
  get<ClearanceRow>("/listings/" + encodeURIComponent(listingId));
export const fetchClearanceRules = (sourceAccountRef: string) =>
  get<ClearanceRules>("/rules" + params({source_account_ref: sourceAccountRef}));
export const saveClearanceRules = (value: ClearanceRules) =>
  write<{version: number; rules: ClearanceRules["rules"]}>("/rules", "PUT", {
    source_account_ref: value.source_account_ref, expected_version: value.version, rules: value.rules,
  });
export const fetchClearanceRequests = (query: Record<string, string | number | undefined> = {}) =>
  get<ClearancePage<ClearanceRequest>>("/requests" + params(query));
export const fetchClearanceRequestDetail = (id: string) =>
  get<ClearanceRequestDetail>("/requests/" + encodeURIComponent(id));
export const submitClearance = (body: ClearanceApplication) =>
  write<{request_id: string; approval_id: string; status: string}>("/requests", "POST", body);
export const withdrawClearance = (id: string) =>
  write<{status: string}>("/requests/" + encodeURIComponent(id) + "/withdraw", "POST", {});
export const updateClearanceProgress = (id: string, body: {
  sold_qty: number; removed_qty: number; disposed_qty: number; expected_version: number;
}) => write<{status: string; version: number}>("/requests/" + encodeURIComponent(id) + "/progress", "PUT", body);
export const pauseClearance = (id: string) =>
  write<{status: string}>("/requests/" + encodeURIComponent(id) + "/pause", "POST", {});
export const resumeClearance = (id: string) =>
  write<{status: string}>("/requests/" + encodeURIComponent(id) + "/resume", "POST", {});
