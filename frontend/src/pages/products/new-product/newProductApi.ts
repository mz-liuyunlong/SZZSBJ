import { backendRequest } from "@/api/backendApi";

export interface NewProductPeriodMetrics {
  days: number;
  from: string;
  to_exclusive: string;
  sales: number | null;
  orders: number | null;
  revenue: number | null;
  ad_spend: number | null;
  sp_ad_spend: number | null;
  sem_ad_spend: number | null;
  clicks: number | null;
  profit: number | null;
  margin: number | null;
  acos: number | null;
  ad_spend_ratio: number | null;
  attributed_sales: number | null;
  currency_code?: string | null;
  ad_days: number;
  cpc?: number | null;
  cvr?: number | null;
  ctr?: number | null;
  roi?: number | null;
  roas?: number | null;
  roi_status?: string;
  impressions?: number | null;
  attributed_orders?: number | null;
  observed_days: number;
  missing_days?: number;
  complete_cost_days: number;
  data_issues?: string[];
  complete: boolean;
}

export interface NewProductMetrics {
  account: string;
  sku: string;
  business_timezone: string;
  as_of_exclusive: string;
  verified_start_date?: string | null;
  order_milestones?: {
    first_order_date: string | null;
    days_to_first_order: number | null;
    sales_7d: number | null;
    sales_10d: number | null;
    sales_20d: number | null;
    coverage_20d: number | null;
    status: string;
  };
  financial_visibility?: "authorized" | "restricted";
  source_tables: string[];
  periods: Record<"30" | "60" | "90", NewProductPeriodMetrics>;
  inventory: {
    available: number | null;
    wfs_available: number | null;
    listing_count: number;
    refreshed_at: string | null;
  };
  rule_version: number;
  formal_policy?: { status: string; blockers: string[]; auto_publish: boolean };
  score: { status: string; grade?: string | null; score?: number | null;
    provisional_score?: number | null; provisional_grade?: string | null;
    purchase_preview?: { status: string; suggested_qty: number | null; range: number[] | null };
    formal_policy?: { status: string; blockers: string[]; auto_publish: boolean };
    approved_correction_dimensions?: string[] };
  launch: { status: string; result: string | null };
}

export interface NewProductReconciliation {
  account: string;
  sku: string;
  window: { from: string; to_exclusive: string; days: number };
  mapping: {
    listing_rows: number; stores: number; item_ids: number;
    store_item_pairs: number; first_listing_date: string | null;
  };
  market_review_readiness: { status: string; elapsed_days: number | null };
  sales: {
    mart_days: number; recorded_zero_days: number;
    item_mart_days: number; cost_missing_rows: number;
    currency: string | null;
  };
  ads: {
    candidate_rows: number; matched_rows: number; unmatched_rows: number;
    observed_days: number; spend_currency: string | null;
    attributed_currency: string | null;
  };
  finance: {
    visibility: "authorized" | "restricted";
    sku_sales_amount?: number | null;
    item_sales_amount?: number | null;
    sales_difference?: number | null;
    gross_profit_amount?: number | null;
    ad_spend_amount?: number | null;
    attributed_sales_amount?: number | null;
    roas?: number | null;
  };
  status: string;
  zero_sales_days_verification: string;
  issues: string[];
  read_only: boolean;
  formal_grade_status: string;
  confirmed_purchase_bands: Record<string, [number, number]>;
}

export type NewProductRealMode = "performance" | "tracking";

export type NewProductDashboardGroup =
  "category" | "developer" | "operator" | "purchase_status" | "tracking_status";

export interface NewProductDashboard {
  account: string;
  total: number;
  groups: Record<NewProductDashboardGroup, { name: string; count: number }[]>;
  formal_grade_distribution: null;
  formal_launch_success_rate: null;
  formal_rules_status: string;
}

export interface NewProductScoreCorrection {
  id: string;
  sku_identity_id: string;
  source_account_ref: string;
  dimension: "order" | "ads" | "profit" | "trust";
  from_score: number;
  requested_score: number;
  rule_version: number;
  status: "pending" | "approved" | "rejected";
  reason: string;
  requested_by: string;
  reviewed_by: string | null;
  review_note: string | null;
  created_at: string;
  reviewed_at: string | null;
}

export interface NewProductCorrectionList {
  items: NewProductScoreCorrection[];
  total: number;
  page: number;
}

export interface NewProductDraftRules {
  version: number;
  confirmed_purchase_bands?: Record<string, [number, number]>;
  formal_policy?: { status: string; blockers: string[]; auto_publish: boolean };
  rule_json: {
    weights: Record<"market" | "order" | "ads" | "profit" | "trust", number>;
    success_days: 30 | 60 | 90;
    min_sales: number;
    min_margin: number;
    max_acos: number;
  } | null;
  actor?: string;
  reason?: string;
  created_at?: string;
}

export interface NewProductRulesHistory {
  items: NewProductDraftRules[];
  total: number;
}

export interface NewProductListingCandidate {
  id: string;
  source_account_ref: string;
  store_id: string;
  store_name: string | null;
  item_id: string;
  local_sku: string | null;
  msku: string | null;
  local_name: string | null;
  title: string | null;
  picture_url: string | null;
  category: string | null;
  listing_status: string | null;
  lifecycle_status: string | null;
  fulfillment_type_name: string | null;
  listing_start_at_utc: string | null;
  available_quantity: number | null;
  wfs_available_quantity: number | null;
  sales_7d: number | null;
  sales_14d: number | null;
  sales_30d: number | null;
  tags_json: Record<string, unknown>[] | null;
  calculated_at: string;
}

export interface NewProductListingCandidates {
  source_account_ref: string;
  source_table: "mart_listing_management_current";
  selection_mode: "all_listings_pending_new_product_tag";
  read_only: true;
  items: NewProductListingCandidate[];
  page: number;
  page_size: number;
  total: number;
}

export async function getNewProductListingCandidates(
  account: string, page = 1, options: { sku?: string } = {},
): Promise<NewProductListingCandidates> {
  if (!account.trim()) throw new Error("需要先选择真实数据账户");
  const q = new URLSearchParams({ source_account_ref: account, page: String(page) });
  if (options.sku?.trim()) q.set("sku_query", options.sku.trim());
  return (await backendRequest<NewProductListingCandidates>(
    `/api/new-products/listing-candidates?${q}`,
  )).data;
}

export interface NewProductWorkflowRecord {
  sku_identity_id: string;
  source_account_ref: string;
  sku: string | null;
  product_name: string | null;
  category: string | null;
  developer?: string | null;
  operator?: string | null;
  product_observed_at?: string | null;
  status: "pending_market" | "scored" | "pending_purchase" | "approved_draft" | "rejected" | null;
  row_version: number | null;
  market_score: number | null;
  purchase_request_qty: number | null;
  plan_id?: string | null;
  plan_number?: string | null;
  plan_execution_status?: string | null;
  tracking_status?: "not_in_pool" | "awaiting_sellable" | "observing" | "optimize" | "due_review";
  review_due_at?: string | null;
  review_result: "observe" | "optimize" | "success" | "failure" | null;
  arrival_date?: string | null;
  sellable_date?: string | null;
  dates_verified_by?: string | null;
}

export interface NewProductWorkflowList {
  items: NewProductWorkflowRecord[];
  page: number;
  total: number;
}

export interface NewProductPurchasePlan {
  id: string;
  plan_number: string;
  sku_identity_id: string;
  source_account_ref: string;
  sku: string;
  quantity: number;
  status: "approved";
  execution_status: "not_executed";
  market_score: number;
  rule_version: number;
  approved_by: string;
  approval_note: string;
  approval_workflow_version: number;
  created_at: string;
}

export interface NewProductPurchasePlanDetail extends NewProductPurchasePlan {
  snapshot_json: {
    approved_quantity: number;
    market_score: number;
    rule_version: number;
    approval_workflow_version?: number;
    workflow_version?: number;
    purchase_reason: string;
    approval_note: string;
    formal_score_verified: boolean;
    execution_status: "not_executed";
    creates_pmc_order: false;
  };
}

export interface NewProductPurchasePlanList {
  items: NewProductPurchasePlan[];
  page: number;
  total: number;
}

function apiPath(skuId: string, action = ""): string {
  if (!/^[0-9a-fA-F-]{36}$/.test(skuId)) throw new Error("无效的 SKU 身份");
  return `/api/new-products/workflows/${skuId}${action}`;
}

export async function getNewProductAccounts(): Promise<string[]> {
  const result = (await backendRequest<{ items: string[] }>("/api/new-products/source-accounts")).data;
  return result.items;
}

export async function getNewProductWorkflows(
  account: string, page = 1,
  options: { status?: "approved_draft"; sku?: string } = {},
): Promise<NewProductWorkflowList> {
  if (!account.trim()) throw new Error("需要先选择真实数据账户");
  const q = new URLSearchParams({ source_account_ref: account, page: String(page) });
  if (options.status) q.set("status", options.status);
  if (options.sku?.trim()) q.set("sku_query", options.sku.trim());
  return (await backendRequest<NewProductWorkflowList>(`/api/new-products/workflows?${q}`)).data;
}

export async function getNewProductDashboard(account: string): Promise<NewProductDashboard> {
  if (!account.trim()) throw new Error("需要先选择真实数据账户");
  const q = new URLSearchParams({ source_account_ref: account });
  return (await backendRequest<NewProductDashboard>(
    `/api/new-products/dashboard?${q}`,
  )).data;
}

export async function getNewProductScoreCorrections(
  account: string, page = 1,
): Promise<NewProductCorrectionList> {
  if (!account.trim()) throw new Error("需要先选择真实数据账户");
  const q = new URLSearchParams({ source_account_ref: account, page: String(page) });
  return (await backendRequest<NewProductCorrectionList>(
    `/api/new-products/score-corrections?${q}`,
  )).data;
}

export async function getNewProductRulesHistory(page = 1): Promise<NewProductRulesHistory> {
  return (await backendRequest<NewProductRulesHistory>(
    `/api/new-products/rules/history?page=${page}`,
  )).data;
}

export async function requestNewProductScoreCorrection(
  id: string, expectedVersion: number,
  dimension: NewProductScoreCorrection["dimension"],
  targetScore: number, reason: string,
) {
  return mutate(id, "/score-correction", {
    expected_version: expectedVersion, dimension, target_score: targetScore, reason,
  });
}

export async function decideNewProductScoreCorrection(
  id: string, decision: "approved" | "rejected", note: string,
) {
  if (!/^[0-9a-fA-F-]{36}$/.test(id)) throw new Error("无效的修正申请编号");
  return (await backendRequest<Record<string, unknown>>(
    `/api/new-products/score-corrections/${id}/decision`, {
      method: "POST",
      body: JSON.stringify({ decision, note }),
    },
  )).data;
}

export async function updateNewProductDraftRules(
  payload: NewProductDraftRules["rule_json"] & { expected_version: number; reason: string },
) {
  return (await backendRequest<NewProductDraftRules>("/api/new-products/rules", {
    method: "PUT",
    body: JSON.stringify(payload),
  })).data;
}

export async function getIndependentNewProductPlans(
  account: string, page = 1,
): Promise<NewProductPurchasePlanList> {
  if (!account.trim()) throw new Error("需要先选择真实数据账户");
  const q = new URLSearchParams({ source_account_ref: account, page: String(page) });
  return (await backendRequest<NewProductPurchasePlanList>(
    `/api/new-products/purchase-plans?${q}`,
  )).data;
}

export async function getIndependentNewProductPlan(
  planId: string,
): Promise<NewProductPurchasePlanDetail> {
  if (!/^[0-9a-fA-F-]{36}$/.test(planId)) throw new Error("无效的独立新品计划编号");
  return (await backendRequest<NewProductPurchasePlanDetail>(
    `/api/new-products/purchase-plans/${planId}`,
  )).data;
}

export async function getNewProductWorkflow(skuId: string) {
  return (await backendRequest<NewProductWorkflowRecord>(apiPath(skuId))).data;
}

async function mutate(skuId: string, suffix: string, payload: object) {
  return (await backendRequest<Record<string, unknown>>(apiPath(skuId, suffix), {
    method: "POST",
    body: JSON.stringify(payload),
  })).data;
}

export const saveMarketScore = (id: string, expectedVersion: number, score: number, reason: string) =>
  mutate(id, "/market", { expected_version: expectedVersion, score, reason });
export const requestNewProductPurchase = (id: string, expectedVersion: number, quantity: number, reason: string) =>
  mutate(id, "/purchase-request", { expected_version: expectedVersion, quantity, reason });
export const decideNewProductPurchase = (id: string, expectedVersion: number, decision: "approved_draft" | "rejected", note: string) =>
  mutate(id, "/purchase-decision", { expected_version: expectedVersion, decision, note });
export const reviewNewProductLaunch = (id: string, expectedVersion: number, result: "observe" | "optimize", reason: string, nextReview?: string) =>
  mutate(id, "/review", { expected_version: expectedVersion, result, reason, next_review: nextReview ?? null });

export const verifyNewProductDates = (
  id: string, expectedVersion: number, arrivalDate: string, sellableDate: string, evidence: string,
) => mutate(id, "/verified-dates", {
  expected_version: expectedVersion,
  arrival_date: arrivalDate,
  sellable_date: sellableDate,
  evidence,
});

export async function getNewProductRules(): Promise<NewProductDraftRules> {
  return (await backendRequest<NewProductDraftRules>("/api/new-products/rules")).data;
}

export async function getNewProductReconciliation(
  skuId: string,
  days: 7 | 14 | 30 | 60 | 90 = 30,
): Promise<NewProductReconciliation> {
  return (await backendRequest<NewProductReconciliation>(
    apiPath(skuId, `/reconciliation?days=${days}`),
  )).data;
}

export async function getNewProductMetrics(skuId: string): Promise<NewProductMetrics> {
  return (await backendRequest<NewProductMetrics>(apiPath(skuId, "/metrics"))).data;
}
