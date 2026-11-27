/** Real SZZSBJ clearance API adapter; never calls Walmart API from the browser. */
import { backendRequest } from "@/api/backendApi";
import type { ApprovalFilters, ApprovalItem, ApprovalListData, ApprovalMeta } from "@/pages/data-center/approval-workspace/approvalTypes";

export type RiskLevel = "high" | "medium" | "low" | "none" | "unknown";
export interface ClearanceSignal { kind: string; reason: string }
export interface ClearanceListing {
  source_account_ref: string;
  store_id: string;
  item_id: string;
  listing_id: string;
  title: string | null;
  local_name?: string | null;
  product_name?: string | null;
  sku: string | null;
  msku: string | null;
  store_name: string | null;
  owner: string | null;
  owner_name?: string | null;
  picture_url: string | null;
  available: number;
  price_amount: string | null;
  risk: RiskLevel;
  reasons: string[];
  signals: ClearanceSignal[];
  data_gaps: string[];
  metrics: Record<string, string | number | boolean | null | string[]>;
  rule_version: number;
}
export interface ClearanceFilterOption { value: string; label: string; source_account_ref?: string }
export interface ClearanceFilterOptions { stores: ClearanceFilterOption[]; owners: ClearanceFilterOption[]; risks: ClearanceFilterOption[] }
export interface ClearanceMultiFilters { store_refs?: string[]; owner_names?: string[]; risk_levels?: string[] }
export async function getClearanceFilterOptions(signal?: AbortSignal): Promise<ClearanceFilterOptions> {
  return (await backendRequest<ClearanceFilterOptions, null>("/api/clearance/filter-options", { signal })).data;
}
export interface ClearanceList {
  items: ClearanceListing[];
  page: number;
  page_size: number;
  has_more: boolean;
  /** Exact count of the specified total_scope, or null when not calculated. */
  total?: number | null;
  total_scope?: "all_wfs_stock_eligible" | "filtered_wfs_stock_eligible" | "clearance_rule_candidates" | "not_calculated";
  risk_filter_applied?: boolean;
  rule_version: number;
  risk_model_ready?: boolean;
  risk_calculated_in_memory?: boolean;
}
export type ClearanceRules = Record<string, number | boolean>;
export interface RuleSpec { group: string; key: string; label: string; kind: "number" | "switch" | "lookback" }
export interface RuleResponse { version: number; persisted: boolean; config: ClearanceRules; catalog: RuleSpec[]; can_edit: boolean }
export interface ClearanceApplication {
  id: string;
  source_account_ref: string;
  store_id: string;
  item_id: string;
  applicant_ref: string;
  applicant_name?: string | null;
  status: "pending" | "rejected" | "cancelled" | "running" | "done" | "stock_closed";
  title: string | null;
  local_sku: string | null;
  msku: string | null;
  store_name: string | null;
  owner_ref: string | null;
  v44_current_target_cost_usd?: number;
  display_product_name?: string | null;
  display_owner_name?: string | null;
  listing_days?: number | null;
  inventory_cost_usd?: number | null;
  wfs_available_quantity?: number | string | null;
  /** Submission snapshot, only when confirmed purchase + first-leg costs exist. */
  target_inventory_cost_usd?: number | null;
  requested_qty: number;
  approved_qty: number | null;
  sold_qty: string | number;
  /** Read-only observed MART totals for the displayed clearance plan window. */
  plan_start_date_la?: string | null;
  plan_sales_through_la?: string | null;
  plan_sold_qty?: number | null;
  plan_sales_amount_usd?: number | null;
  reason: string;
  note: string;
  methods_json: string[];
  risk_at_submission: RiskLevel;
  current_risk: RiskLevel | null;
  rule_version: number;
  version: number;
  can_review?: boolean;
  submitted_at: string;
  approved_at: string | null;
  approved_date_la: string | null;
  planned_completion_date?: string | null;
  finished_at: string | null;
  finish_reason: string | null;
}
export interface ApplicationList { items: ClearanceApplication[]; total: number; page: number; page_size: number }
export interface ApplicationDetail {
  application: ClearanceApplication;
  current: ClearanceListing;
  /** Only values persisted in the same account/store/Item approval snapshot. */
  submission_suggestion?: {
    suggested_qty?: number | string | null;
    rule_floor_price_usd?: number | string | null;
    snapshot_unit_margin_usd?: number | string | null;
    snapshot_available_qty?: number | string | null;
  } | null;
  events: Array<{ event_type: string; actor_ref: string; detail_json: Record<string, unknown>; created_at: string }>;
}

const json = (data: unknown): RequestInit => ({ method: "POST", body: JSON.stringify(data) });
export async function listClearanceListings(keyword = "", page = 1, riskOnly = true, pageSize = 50, filters: ClearanceMultiFilters = {}, signal?: AbortSignal): Promise<ClearanceList> {
  void riskOnly; // Risk admission remains disabled during rule validation.
  const params = new URLSearchParams({ keyword, page: String(page), page_size: String(pageSize), risk_only: "false", exact_total: "true" });
  for (const ref of filters.store_refs ?? []) params.append("store_refs", ref);
  for (const name of filters.owner_names ?? []) params.append("owner_names", name);
  for (const level of filters.risk_levels ?? []) params.append("risk_levels", level);
  return (await backendRequest<ClearanceList, null>(`/api/clearance/listings?${params}`, { signal })).data;
}
export async function getClearanceListing(listing: Pick<ClearanceListing,"source_account_ref"|"store_id"|"item_id">) {
  const params = new URLSearchParams({ source_account_ref: listing.source_account_ref, store_id: listing.store_id, item_id: listing.item_id });
  return (await backendRequest<ClearanceListing, null>(`/api/clearance/listing?${params}`)).data;
}
export async function getClearanceRules() {
  return (await backendRequest<RuleResponse, null>("/api/clearance/rules")).data;
}
export async function saveClearanceRules(expectedVersion: number, config: ClearanceRules, reason: string) {
  return (await backendRequest<{version:number;recalculation:string}, null>("/api/clearance/rules", {
    method: "PUT", body: JSON.stringify({ expected_version: expectedVersion, config, reason }),
  })).data;
}
export async function getClearanceRuleHistory() {
  return (await backendRequest<{items: Array<{version:number;changed_by:string;change_reason:string;changed_at:string|null} >}, null>("/api/clearance/rules/history")).data.items;
}

// The server returns batch-enriched application facts; never fetch each Item here.
export async function listClearanceApplications(page = 1, pageSize = 50, status?: string, includeLive = true, signal?: AbortSignal): Promise<ApplicationList> {
  const params = new URLSearchParams({ page: String(page), page_size: String(pageSize), include_live: String(includeLive) });
  if (status) params.set("status", status);
  return (await backendRequest<ApplicationList, null>(`/api/clearance/applications?${params}`, { cache: "no-store", signal })).data;
}
export async function getClearanceApplication(id: string) {
  return (await backendRequest<ApplicationDetail, null>(`/api/clearance/applications/${encodeURIComponent(id)}`)).data;
}
export async function submitClearanceApplication(payload: {
  source_account_ref: string; store_id: string; item_id: string;
  qty: number; reason: string; methods: string[]; note: string;
  planned_completion_date?: string;
}) {
  return (await backendRequest<{id:string;approval_id:string;status:string}, null>("/api/clearance/applications", json(payload))).data;
}
export async function cancelClearanceApplication(id: string, note = "") {
  return (await backendRequest<{id:string;status:string}, null>(`/api/clearance/applications/${encodeURIComponent(id)}/cancel`, json({ note }))).data;
}
export async function reviewClearanceApplication(id: string, expectedVersion: number, decision: "approved"|"rejected", note: string) {
  return (await backendRequest<{id:string;status:string;approved_qty:number|null;latest_available:number}, null>(`/api/clearance/applications/${encodeURIComponent(id)}/review`, json({ expected_version: expectedVersion, decision, note }))).data;
}
export async function completeClearanceApplication(id: string, note: string) {
  return (await backendRequest<{id:string;status:string}, null>(`/api/clearance/applications/${encodeURIComponent(id)}/complete`, json({ note }))).data;
}
export async function reconcileClearanceApplication(id: string) {
  return (await backendRequest<{id:string;status:string;sold_qty:number;approved_qty:number}, null>(`/api/clearance/applications/${encodeURIComponent(id)}/reconcile`, json({}))).data;
}

/** Workbench reuses the real clearance application API rather than Demo seeds. */
export async function fetchClearanceApprovals(filters: ApprovalFilters): Promise<{ data: ApprovalListData; meta: ApprovalMeta }> {
  const data = await listClearanceApplications(filters.page, filters.page_size, filters.tab);
  const mapped: ApprovalItem[] = data.items
    .filter(row => !filters.risk_level || row.risk_at_submission === filters.risk_level)
    .filter(row => !filters.keyword || [row.item_id,row.local_sku,row.msku,row.title,row.reason].join(" ").toLowerCase().includes(filters.keyword.toLowerCase()))
    .map(row => ({
      id: row.id, version: row.version, approval_type: "clearance_request",
      business_ref: `${row.store_id}/${row.item_id}`,
      title: row.display_product_name || row.title || row.item_id,
      source_account_ref: row.source_account_ref,
      applicant_id: row.applicant_ref,
      applicant_name: row.applicant_name ?? null,
      status: row.status === "pending" ? "submitted" : row.status === "rejected" ? "rejected" : row.status === "running" || row.status === "done" ? "approved" : "withdrawn",
      risk_level: row.risk_at_submission,
      amount: null, currency_code: null, submitted_at: row.submitted_at,
      reviewed_at: row.approved_at, reviewed_by: null, reason: row.reason,
      can_review: Boolean(row.can_review), requires_verification: false, case_review: false,
      clearance_details: {
        sku: row.local_sku, msku: row.msku, item_id: row.item_id,
        store_id: row.store_id, store_name: row.store_name,
        owner_ref: row.display_owner_name || row.owner_ref,
        requested_qty: row.requested_qty, methods: row.methods_json,
        wfs_available_quantity: row.wfs_available_quantity ?? null,
        listing_days: row.listing_days ?? null,
        inventory_cost_usd: row.inventory_cost_usd ?? null,
      },
    }));
  return { data: { items: mapped }, meta: { total: data.total, page: data.page, page_size: data.page_size } };
}

/** Sandbox lifecycle projection; no real Listing database write occurs in local DEV. */
export async function getClearanceLifecycleOverrides(): Promise<Array<{
  source_account_ref: string; store_id: string; item_id: string; stage: string;
}>> {
  return (await backendRequest<{items:Array<{
    source_account_ref:string; store_id:string; item_id:string; stage:string;
  }>}, null>("/api/clearance/lifecycle-overrides")).data.items;
}
