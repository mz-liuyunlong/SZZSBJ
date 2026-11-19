/** PR337 Phase2: live backend API only; no mock or localStorage fallback. */
import { backendRequest, backendDownload } from "@/api/backendApi";
import { queryClient } from "@/api/queryClient";
import type { RuleDraft } from "./NewProductRulesModel";

export type Identity = { source_account_ref: string; store_id: string; item_id: string };
/** Read-only risk status derived on the backend from saved real-data evidence. */
export type SystemRiskStatus = "hit" | "clear" | "unverified" | "disabled";
export type SystemRiskDisplay = {
  source: "saved_verified_risk_evidence";
  rule_version: number;
  grade_cap_applied: boolean;
  rules: Array<{
    code:string; name:string; enabled:boolean; status:SystemRiskStatus;
    basis:string; limit:string; cutoff_la:string|null;
  }>;
};
export type RealScore = {
  rule_version: number;
  total: string | null;
  grade: "S" | "A" | "B" | "C" | "D" | "Pass" | null;
  dimensions: Record<"market" | "speed" | "ad" | "profit" | "trust", string | null>;
  missing: string[];
  ad_excluded: boolean;
  observation_state: string;
};
export type ScoreCorrectionView = {
  revision: number;
  system: {total:string|null;grade:string|null;dimensions:Record<string,string|null>;rule_version:number};
  effective: {total:string|null;grade:string|null;dimensions:Record<string,string|null>};
  history: Array<{revision:number;dimension:string;actor_id:string;at:string;system_score:string;before:string;after:string;delta:string;reason:string}>;
};
export type NewProductListing = {
  system_risk_display?: SystemRiskDisplay | null;
  evaluation_status?: "待到货"|"测评中"|"待市场评分"|"测评通过"|"测评未通过";
  evaluation_review_status?: "submitted"|"info_required"|"approved"|"rejected"|null;
  evaluation_review_id?: string|null;
  evaluation_job_status?: "none"|"queued"|"running"|"completed"|"failed"|null;
  evaluation_manual_exception?: boolean;
  evaluation_recheck_required?: boolean;
  listing: {
    id: string; source_account_ref: string; store_id: string; item_id: string;
    msku: string | null; local_sku: string | null; title: string | null;
    local_name: string | null; store_name: string | null; owner_name: string | null;
    picture_url: string | null; wfs_available_quantity: string | null;
    launch_date_cn?: string | null; category?: string | null; category_path?: string | null; // PR337_PERSISTED_DISPLAY_V1
    product_developer_name?: string | null; sale_price_amount?: string | number | null;
    sales_7d?: string | number | null; sales_30d?: string | number | null;
    ad_spend_30d_amount?: string | number | null;
    product_tags: Array<{ id: string | null; label: string; color: string | null }>;
    first_wfs_available_date_la: string | null;
  };
  facts: Record<string, unknown>;
  evaluation: RealScore;
  tracking_decision: string | null;
  tracking_reason: string | null;
  market_reason: string | null;
  market_version: number;
  score_correction?: ScoreCorrectionView | null;
  market_competitor_ids?: string[];
  market_no_competitors?: boolean;
  suggested_qty: number | null;
  purchase_status: string | null;
  purchase_id: string | null;
  tracking_final_result?: string | null;
  tracking_review_status?: string | null;
  tracking_review_application?: {
    proposed_result: string; reason: string; status: string; created_at: string | null;
  } | null;
  tracking_started_date_la?: string | null;
  tracking_start_status?: string | null;
  tracking_status?: string | null;
  purchase_version?: number | null;
  requested_qty?: number | null;
  approved_qty?: number | null;
  purchase_reason?: string | null;
  tracking_version?: number;
  system_recommendation: { value: string; reasons: string[] };
};
export type PageResponse = { items: NewProductListing[]; total: number; page: number; page_size: number; rule_version: number };

export type NewProductBoardGroup = {
  name:string;count:number;completed:number;passed:number;
  rate:string;highRate:string;avg:string;
  grades:Record<"S"|"A"|"B"|"C"|"D"|"Pass",number>;
  subcategories:Array<{raw:string;zh:string;label:string}>;
};
export type NewProductBoardSummary = {
  date_basis:"first_wfs_available_date_la";
  status_basis:"latest_saved_evaluation";
  start_date:string;end_date:string;
  counts:{total:number;evaluating:number;market:number;passed:number;failed:number;completed:number;low_grade:number;due:number};
  pass_rate:string;
  grades:Record<"S"|"A"|"B"|"C"|"D"|"Pass",number>;
  failure_dimensions:Record<"market"|"speed"|"ad"|"profit"|"trust",number>;
  categories:NewProductBoardGroup[];developers:NewProductBoardGroup[];
  untranslated_categories:number;
  reminders:Array<{id:string;sku:string;name:string;developer:string;days:number}>;
};
export async function getNewProductBoardSummary(startDate:string,endDate:string,init?:RequestInit):Promise<NewProductBoardSummary>{
  const params=new URLSearchParams({start_date:startDate,end_date:endDate});
  return (await backendRequest<NewProductBoardSummary>(`/api/new-products/board/summary?${params}`,init)).data;
}

export type PerformanceSummary = {
  counts: { all:number; evaluating:number; market:number; passed:number; failed:number };
  status_options: Array<{value:string;label:string;count:number}>;
  owner_options: Array<{value:string;label:string;count:number}>;
  rating_options: Array<{value:string;label:string;count:number}>;
};
export async function getNewProductSummary(init?:RequestInit):Promise<PerformanceSummary> {
  return (await backendRequest<PerformanceSummary>("/api/new-products/summary",init)).data;
}
export type RuleResponse = { kind: "performance" | "tracking"; version: number; config: RuleDraft | Record<string, unknown> | null; source: string; applied_at: string | null };
export type RuleApplyResult = RuleResponse & { unchanged: boolean };
export async function listNewProducts(params: {page?:number;pageSize?:number;storeId?:string;keyword?:string;searchField?:"sku"|"msku"|"item_id"|"title";npStatuses?:string;npOwners?:string;npRatings?:string;npOwnerKeyword?:string} = {},init?:RequestInit):Promise<PageResponse> {
  const query = new URLSearchParams({page:String(params.page??1),page_size:String(params.pageSize??50)});
  if(params.storeId) query.set("store_id",params.storeId);
  if(params.keyword) query.set("keyword",params.keyword);
  if(params.searchField) query.set("search_field",params.searchField);
  if(params.npStatuses) query.set("np_statuses",params.npStatuses);
  if(params.npOwners) query.set("np_owners",params.npOwners);
  if(params.npRatings) query.set("np_ratings",params.npRatings);
  if(params.npOwnerKeyword) query.set("np_owner_keyword",params.npOwnerKeyword);
  const envelope = await backendRequest<PageResponse>(`/api/new-products/listings?${query}`,init);
  return envelope.data;
}
export async function getNewProductRules(kind:"performance"|"tracking"="performance"):Promise<RuleResponse> {
  return (await backendRequest<RuleResponse>(`/api/new-products/rules?kind=${kind}`)).data;
}
export async function applyNewProductRules(kind:"performance"|"tracking",expectedVersion:number,config:RuleDraft|Record<string,unknown>,reason=""):Promise<RuleApplyResult> {
  return (await backendRequest<RuleApplyResult>("/api/new-products/rules/apply",{
    method:"PUT",body:JSON.stringify({kind,expected_version:expectedVersion,config,change_reason:reason})
  })).data;
}
export async function getNewProductDetail(identity:Identity) {
  const {source_account_ref:a,store_id:s,item_id:i}=identity;
  return (await backendRequest<Record<string,unknown>>(`/api/new-products/listings/${encodeURIComponent(a)}/${encodeURIComponent(s)}/${encodeURIComponent(i)}`)).data;
}
// NP_DETAIL_CACHE_V4_REFRESH_GUARD: share one existing QueryClient across tabs and drawer mounts.
// Keys include account + store + Item ID; logout already clears all query cache.
export const newProductDetailQueryKey = (identity:Identity) => [
  "np-product-detail", identity.source_account_ref, identity.store_id, identity.item_id,
] as const;
export const newProductDetailQueryOptions = (identity:Identity) => ({
  queryKey: newProductDetailQueryKey(identity),
  queryFn: () => getNewProductDetail(identity),
  staleTime: 5 * 60_000,
  gcTime: 30 * 60_000,
  retry: 1,
});
export const getCachedNewProductDetail = (identity:Identity) =>
  queryClient.fetchQuery(newProductDetailQueryOptions(identity));
export const prefetchNewProductDetail = (identity:Identity) =>
  queryClient.prefetchQuery(newProductDetailQueryOptions(identity));
export const invalidateNewProductDetail = (identity?:Identity) =>
  queryClient.invalidateQueries({
    queryKey: identity ? newProductDetailQueryKey(identity) : ["np-product-detail"],
    exact: Boolean(identity),
    refetchType: "none",
  });
// PR337_MANUAL_RISK_V1: explicit human risk selection is required by the API.
export async function saveNewProductMarketScore(identity:Identity,score:number,reason:string,expectedVersion:number,riskConditions:string[],competitorIds:string[],noCompetitors:boolean) {
  return (await backendRequest<{version:number;score:number;reason:string}>("/api/new-products/market-score",{
    method:"PUT",body:JSON.stringify({...identity,score,reason,expected_version:expectedVersion,risk_conditions:riskConditions,competitor_ids:competitorIds,no_competitors:noCompetitors})
  })).data;
}
// NP_OPERATOR_SCORE_CORRECTION_V1_20261119
export async function saveNewProductScoreCorrection(identity:Identity,dimension:"speed"|"ad"|"profit"|"trust",newScore:number,reason:string,expectedRevision:number) {
  return (await backendRequest<ScoreCorrectionView>("/api/new-products/score-corrections",{
    method:"PUT",body:JSON.stringify({...identity,dimension,new_score:newScore,reason,expected_revision:expectedRevision})
  })).data;
}
export async function getNewProductPurchaseSnapshot(applicationId:string) {
  return (await backendRequest<{id:string;status:string;version:number;score_snapshot:{evaluation:RealScore;score_correction?:ScoreCorrectionView;facts?:Record<string,unknown>};requested_qty:number;suggested_qty:number;applicant:string;reason:string;created_at:string}>(
    `/api/new-products/purchase-applications/${encodeURIComponent(applicationId)}`)).data;
}
export async function saveNewProductTrackingDecision(identity:Identity,decision:string,reason:string,expectedVersion:number) {
  return (await backendRequest<{version:number;decision:string}>("/api/new-products/tracking/decision",{
    method:"PUT",body:JSON.stringify({...identity,decision,reason,expected_version:expectedVersion})
  })).data;
}
export async function submitNewProductPurchase(identity:Identity,requestedQty:number,reason:string,ruleVersion:number) {
  return (await backendRequest<{application_id:string;status:string;version:number}>("/api/new-products/purchase-applications",{
    method:"POST",body:JSON.stringify({...identity,requested_qty:requestedQty,reason,expected_rule_version:ruleVersion})
  })).data;
}
export async function reviewNewProductPurchase(id:string,decision:"approved"|"rejected",reason:string,expectedVersion:number) {
  return (await backendRequest<{id:string;status:string;version:number}>(`/api/new-products/purchase-applications/${encodeURIComponent(id)}/decision`,{
    method:"POST",body:JSON.stringify({decision,reason,expected_version:expectedVersion})
  })).data;
}
export async function exportNewProductListings() {
  await backendDownload("/api/new-products/listings-export","new-products-real.csv");
}

// PR337_EVALUATION_FULL_WORKFLOW_20261116: all evaluation mutations use the existing authenticated backendRequest.
export async function requestNewProductEvaluation(identity: Identity) {
  return (await backendRequest<{status:string;trigger:string;item_id:string;missing?:string[]},null>(
    "/api/new-products/evaluations/calculate", {method:"POST",body:JSON.stringify(identity)})).data;
}
export async function getNewProductEvaluationJob(identity: Identity) {
  const a=encodeURIComponent(identity.source_account_ref),s=encodeURIComponent(identity.store_id),
        i=encodeURIComponent(identity.item_id);
  return (await backendRequest<{status:string;item_id:string},null>(
    `/api/new-products/evaluations/status/${a}/${s}/${i}`)).data;
}
export async function requestNewProductEvaluationReview(identity: Identity,
  reasonType:"calculation_error"|"scoring_basis_error"|"special_exception",reason:string,evidence:string) {
  return (await backendRequest<{application_id:string;status:string;version:number},null>(
    "/api/new-products/evaluation-reviews", {method:"POST",body:JSON.stringify(
      {...identity,reason_type:reasonType,reason,evidence})})).data;
}

export async function requestNewProductEvaluationRecheck(applicationId: string) {
  return (await backendRequest<{status:string;execution_id:string;grade:string},null>(
    "/api/new-products/evaluation-reviews/" + encodeURIComponent(applicationId) + "/recheck",
    {method:"POST"})).data;
}
