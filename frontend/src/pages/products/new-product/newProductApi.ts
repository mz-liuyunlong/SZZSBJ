import { backendRequest } from "@/api/backendApi";

export interface NewProductWorkflowRecord {
  sku_identity_id: string;
  source_account_ref: string;
  sku: string | null;
  product_name: string | null;
  category: string | null;
  status: "pending_market" | "scored" | "pending_purchase" | "approved_draft" | "rejected" | null;
  row_version: number | null;
  market_score: number | null;
  purchase_request_qty: number | null;
  review_result: "observe" | "optimize" | "success" | "failure" | null;
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

export async function getNewProductRules() {
  return (await backendRequest<Record<string, unknown>>("/api/new-products/rules")).data;
}
