/** PR337 Phase2: live backend API only; no mock or localStorage fallback. */
import { backendRequest, backendDownload } from "@/api/backendApi";
import type { RuleDraft } from "./NewProductRulesModel";

export type Identity = { source_account_ref: string; store_id: string; item_id: string };
export type RealScore = {
  rule_version: number;
  total: string | null;
  grade: "S" | "A" | "B" | "C" | "D" | "Pass" | null;
  dimensions: Record<"market" | "speed" | "ad" | "profit" | "trust", string | null>;
  missing: string[];
  ad_excluded: boolean;
  observation_state: string;
};
export type NewProductListing = {
  listing: {
    id: string; source_account_ref: string; store_id: string; item_id: string;
    msku: string | null; local_sku: string | null; title: string | null;
    local_name: string | null; store_name: string | null; owner_name: string | null;
    picture_url: string | null; wfs_available_quantity: string | null;
    launch_date_cn?: string | null; category?: string | null;
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
  suggested_qty: number | null;
  purchase_status: string | null;
  purchase_id: string | null;
  system_recommendation: { value: string; reasons: string[] };
};
export type PageResponse = { items: NewProductListing[]; total: number; page: number; page_size: number; rule_version: number };
export type RuleResponse = { kind: "performance" | "tracking"; version: number; config: RuleDraft | Record<string, unknown> | null; source: string; applied_at: string | null };
export type RuleApplyResult = RuleResponse & { unchanged: boolean };
export async function listNewProducts(params: {page?:number;pageSize?:number;storeId?:string;keyword?:string;searchField?:"sku"|"msku"|"item_id"|"title"} = {}):Promise<PageResponse> {
  const query = new URLSearchParams({page:String(params.page??1),page_size:String(params.pageSize??50)});
  if(params.storeId) query.set("store_id",params.storeId);
  if(params.keyword) query.set("keyword",params.keyword);
  if(params.searchField) query.set("search_field",params.searchField);
  const envelope = await backendRequest<PageResponse>(`/api/new-products/listings?${query}`);
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
export async function saveNewProductMarketScore(identity:Identity,score:number,reason:string,expectedVersion:number) {
  return (await backendRequest<{version:number;score:number;reason:string}>("/api/new-products/market-score",{
    method:"PUT",body:JSON.stringify({...identity,score,reason,expected_version:expectedVersion})
  })).data;
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
