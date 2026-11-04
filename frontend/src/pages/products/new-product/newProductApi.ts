import { backendRequest } from "@/api/backendApi";

export interface NewProductPeriodMetrics {
  days: number;
  from: string;
  to_exclusive: string;
  sales: number | null;
  orders: number | null;
  revenue: number | null;
  ad_spend: number | null;
  clicks: number | null;
  profit: number | null;
  margin: number | null;
  acos: number | null;
  ad_spend_ratio: number | null;
  attributed_sales: number | null;
  currency_code?: string | null;
  ad_days: number;
  observed_days: number;
  complete_cost_days: number;
  complete: boolean;
}

export interface NewProductMetrics {
  account: string;
  sku: string;
  business_timezone: string;
  as_of_exclusive: string;
  verified_start_date?: string | null;
  source_tables: string[];
  periods: Record<"30" | "60" | "90", NewProductPeriodMetrics>;
  inventory: {
    available: number | null;
    wfs_available: number | null;
    listing_count: number;
    refreshed_at: string | null;
  };
  rule_version: number;
  score: { status: string; grade?: string | null; score?: number | null };
  launch: { status: string; result: string | null };
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

function apiPath(skuId: string, action = ""): string {
  if (!/^[0-9a-fA-F-]{36}$/.test(skuId)) throw new Error("无效的 SKU 身份");
  return `/api/new-products/workflows/${skuId}${action}`;
}

export async function getNewProductAccounts(): Promise<string[]> {
  const result = (await backendRequest<{ items: string[] }>("/api/new-products/source-accounts")).data;
  return result.items;
}

export async function getNewProductWorkflows(account: string, page = 1): Promise<NewProductWorkflowList> {
  if (!account.trim()) throw new Error("需要先选择真实数据账户");
  const q = new URLSearchParams({ source_account_ref: account, page: String(page) });
  return (await backendRequest<NewProductWorkflowList>(`/api/new-products/workflows?${q}`)).data;
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

export async function getNewProductRules() {
  return (await backendRequest<Record<string, unknown>>("/api/new-products/rules")).data;
}

export async function getNewProductMetrics(skuId: string): Promise<NewProductMetrics> {
  return (await backendRequest<NewProductMetrics>(apiPath(skuId, "/metrics"))).data;
}
