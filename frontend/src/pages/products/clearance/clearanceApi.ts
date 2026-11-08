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
export async function getClearanceFilterOptions(): Promise<ClearanceFilterOptions> {
  return (await backendRequest<ClearanceFilterOptions, null>("/api/clearance/filter-options")).data;
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
export interface RuleResponse { version: number; config: ClearanceRules; catalog: RuleSpec[]; can_edit: boolean }
export interface ClearanceApplication {
  id: string;
  source_account_ref: string;
  store_id: string;
  item_id: string;
  applicant_ref: string;
  status: "pending" | "rejected" | "cancelled" | "running" | "done" | "stock_closed";
  title: string | null;
  local_sku: string | null;
  msku: string | null;
  store_name: string | null;
  owner_ref: string | null;
  v44_current_target_cost_usd?: number;
  /** Submission snapshot, only when confirmed purchase + first-leg costs exist. */
  target_inventory_cost_usd?: number | null;
  requested_qty: number;
  approved_qty: number | null;
  sold_qty: string | number;
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
export async function listClearanceListings(keyword = "", page = 1, riskOnly = true, pageSize = 50, filters: ClearanceMultiFilters = {}): Promise<ClearanceList> {
  void riskOnly; // Risk admission remains disabled during rule validation.
  const params = new URLSearchParams({ keyword, page: String(page), page_size: String(pageSize), risk_only: "false", exact_total: "true" });
  for (const ref of filters.store_refs ?? []) params.append("store_refs", ref);
  for (const name of filters.owner_names ?? []) params.append("owner_names", name);
  for (const level of filters.risk_levels ?? []) params.append("risk_levels", level);
  return (await backendRequest<ClearanceList, null>(`/api/clearance/listings?${params}`)).data;
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

// CLEARANCE_MISSING_IDENTITY_V44: read only missing current product facts from
// the authorized primary Listing API. Never persist or modify application data.
const v44IdentityCache = new Map<string,{at:number;value:Promise<ClearanceListing|null>}>();
const v44ItemId = (row: ClearanceApplication): string => {
  const parts = row.item_id.split("::");
  return parts.length===3 && parts[0]===row.source_account_ref &&
    parts[1]===row.store_id && /^\d+$/.test(parts[2]) ? parts[2] : row.item_id;
};
async function v44GetListing(row: ClearanceApplication): Promise<ClearanceListing|null> {
  const itemId=v44ItemId(row);
  const key=JSON.stringify([row.source_account_ref,row.store_id,itemId]);
  const cached=v44IdentityCache.get(key);
  if(cached && Date.now()-cached.at<10000)return cached.value;
  const value=getClearanceListing({source_account_ref:row.source_account_ref,
    store_id:row.store_id,item_id:itemId}).then(live=>{
      if(live.source_account_ref!==row.source_account_ref || live.store_id!==row.store_id || live.item_id!==itemId)
        throw new Error("Listing identity mismatch");
      return live;
    }).catch(async error=>{
      // Historical applications may exist without a matching detail endpoint
      // record. Search the existing read-only WFS listing index by Item ID,
      // then require the EXACT account, store and Item ID before using facts.
      // Never match on SKU alone or borrow another store's product record.
      try {
        const candidates=await listClearanceListings(itemId,1,false,50);
        const exact=candidates.items.filter(live=>
          live.source_account_ref===row.source_account_ref &&
          live.store_id===row.store_id && live.item_id===itemId);
        if(exact.length===1)return exact[0];
        if(exact.length>1)throw new Error("Ambiguous exact Listing identity");
      }catch(fallbackError){
        console.warn("Clearance historical Listing lookup failed",{
          item_id:itemId,error:fallbackError});
      }
      v44IdentityCache.delete(key);
      console.warn("Clearance Listing facts unavailable after exact lookup",{
        item_id:itemId,error});
      return null;
    });
  v44IdentityCache.set(key,{at:Date.now(),value});
  return value;
}
// CLEARANCE_MANAGEMENT_FIELDS_V50_V52: only read authoritative data. Cost is
// verified purchase + first-leg unit inventory cost × the task quantity.
// Never use full sale unit cost (which includes selling expenses).
const v50FiniteNumber = (value: unknown): number | null => {
  if (typeof value === "number") return Number.isFinite(value) ? value : null;
  if (typeof value === "string" && value.trim()) {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : null;
  }
  return null;
};
const v50ValidDate = (value: unknown): string | null => {
  if (typeof value !== "string" || !/^\d{4}-\d{2}-\d{2}$/.test(value)) return null;
  const parsed = new Date(`${value}T00:00:00.000Z`);
  return Number.isFinite(parsed.getTime()) && parsed.toISOString().slice(0, 10) === value ? value : null;
};
const v50CompletionCache = new Map<string,{at:number;value:Promise<string|null>}>();
async function v50ReadCompletionDate(row: ClearanceApplication): Promise<string|null> {
  const own = v50ValidDate(row.planned_completion_date);
  if (own) return own;
  const cached = v50CompletionCache.get(row.id);
  if (cached && Date.now() - cached.at < 30000) return cached.value;
  const value = getClearanceApplication(row.id).then(detail => {
    // The application detail and its submission event are read-only sources.
    // No fallback to approval dates, current date, or arbitrary note text.
    const recorded = v50ValidDate(detail.application?.planned_completion_date);
    if (recorded) return recorded;
    for (const event of detail.events ?? []) {
      const saved = v50ValidDate(event.detail_json?.["planned_completion_date"]);
      if (saved) return saved;
    }
    return null;
  }).catch(() => null);
  v50CompletionCache.set(row.id,{at:Date.now(),value});
  return value;
}
function v50CurrentTargetCost(row: ClearanceApplication, live: ClearanceListing|null): number|null {
  if (!live) return null;
  const qty = v50FiniteNumber(row.approved_qty ?? row.requested_qty);
  if (qty === null || qty <= 0 || !Number.isInteger(qty)) return null;
  // Use inventory cost only: purchase + first leg. The 0076 fallback's
  // capital_at_cost_usd includes full-sale fees and MUST NOT be used here.
  let unit = v50FiniteNumber(live.metrics?.["unit_inventory_cost_usd"]);
  if (unit === null) unit = v50FiniteNumber(live.metrics?.["inventory_unit_cost_usd"]);
  if (unit === null) {
    const purchase = v50FiniteNumber(live.metrics?.["purchase_unit_cost_usd"]);
    const firstLeg = v50FiniteNumber(live.metrics?.["first_leg_unit_cost_usd"]);
    if (purchase !== null && firstLeg !== null) unit = purchase + firstLeg;
  }
  if (unit === null) {
    const capital = v50FiniteNumber(live.metrics?.["capital_purchase_first_leg_usd"]);
    const available = v50FiniteNumber(live.available);
    if (capital !== null && capital >= 0 && available !== null && available > 0) {
      unit = capital / available;
    }
  }
  if (unit === null || unit < 0) return null;
  const amount = unit * qty;
  return Number.isFinite(amount) ? Math.round((amount + Number.EPSILON) * 100) / 100 : null;
}
async function v44EnrichApplications(items: ClearanceApplication[]):Promise<ClearanceApplication[]> {
  // V48 presentation source is the application list. Never overwrite
  // persisted title, owner, SKU, store, item or task status with Listing data.
  const result = items.map(row => ({ ...row, item_id: v44ItemId(row) }));
  let cursor = 0;
  const worker = async () => {
    while (cursor < result.length) {
      const index = cursor++;
      const row = result[index];
      if (!row.id || !row.source_account_ref || !row.store_id || !row.item_id) continue;
      const [live, deadline] = await Promise.all([
        v44GetListing(row),
        v50ReadCompletionDate(row),
      ]);
      const cost = v50CurrentTargetCost(row, live);
      result[index] = {
        ...row,
        ...(cost !== null ? {v44_current_target_cost_usd: cost} : {}),
        ...(deadline ? {planned_completion_date: deadline} : {}),
      };
    }
  };
  await Promise.all(Array.from({length:Math.min(4,result.length)},() => worker()));
  return result;
}

export async function listClearanceApplications(page = 1, pageSize = 50, status?: string): Promise<ApplicationList> {
  const params = new URLSearchParams({ page: String(page), page_size: String(pageSize) });
  if (status) params.set("status", status);
  const fresh = /* CLEARANCE_APPLICATIONS_NO_CACHE_V36 */ (await backendRequest<ApplicationList, null>(`/api/clearance/applications?${params}`, { cache: "no-store" })).data;
  return {...fresh,items:await v44EnrichApplications(fresh.items)};
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
      title: row.title || row.item_id, source_account_ref: row.source_account_ref,
      applicant_id: row.applicant_ref,
      status: row.status === "pending" ? "submitted" : row.status === "rejected" ? "rejected" : row.status === "running" || row.status === "done" ? "approved" : "withdrawn",
      risk_level: row.risk_at_submission,
      amount: null, currency_code: null, submitted_at: row.submitted_at,
      reviewed_at: row.approved_at, reviewed_by: null, reason: row.reason,
      can_review: Boolean(row.can_review), requires_verification: false, case_review: false,
      clearance_details: {
        sku: row.local_sku, msku: row.msku, item_id: row.item_id,
        store_id: row.store_id, store_name: row.store_name, owner_ref: row.owner_ref,
        requested_qty: row.requested_qty, methods: row.methods_json,
        wfs_available_quantity: (row as ClearanceApplication & {
          wfs_available_quantity?: string | number | null
        }).wfs_available_quantity ?? null,
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
