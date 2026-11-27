/**
 * 订单审核接口层（/api/finance/order-review，结算利润 V3 PR-OR）。
 * 金额后端按字符串给（amount + currency_code），这里只做显示；写操作全部走接口，页面不留本地状态。
 */
import { keepPreviousData, useQuery, useQueryClient } from "@tanstack/react-query";
import { backendRequest, BackendRequestError } from "@/api/backendApi";

const BASE = "/api/finance/order-review";
export const ROOT_KEY = ["finance-order-review"] as const;

export type ReviewStatus = "pending" | "auto" | "first_passed" | "final_passed" | "rejected";
export type LineKind = "sale" | "refund" | "mcf";
export type Reason =
  | "wfs_carrier_shipment" | "self_fulfilled" | "fixed_value" | "last_received"
  | "cost_missing" | "shipment_detail_invalid" | "owner_missing" | "cancelled_refund";

export interface ApiMoney { amount: string; currency_code: string }
export interface ApiPeriod {
  store_id: string; store_name: string | null; period_key: string; report_date: string;
  period_start_date: string | null; period_end_date: string | null; bill_month: string | null;
  line_count: number; pending_count: number; auto_count: number; first_passed_count: number;
  final_passed_count: number; rejected_count: number; calc_version: number | null; calculated_at: string | null;
}
export interface ApiCostSource {
  kind: string; quantity?: string | null; msku?: string | null; scope_ref?: string | null;
  purchase_cny?: string | null; head_cny?: string | null; last_leg_cny?: string | null;
  reasons?: string[]; entry_id?: string | null; entry_kind?: string | null;
  shipping_list_code?: string | null; outbound_order_no?: string | null; business_number?: string | null;
  logistics_provider_name?: string | null; logistics_way?: string | null; cost_source?: string | null;
  prefill?: Record<string, string | null> | null; last_leg_prefill_cny?: string | null; note?: string | null;
  returned?: boolean;
}
export interface ApiLine {
  id: string; review_id: string; store_id: string; period_key: string; bill_month: string; line_key: string;
  line_kind: LineKind; fulfillment_type: "wfs" | "seller"; platform_order_no: string; order_line_no: string;
  gtin: string | null; item_id: string | null; sku: string | null; msku: string | null; owner_id: string | null;
  posted_date: string | null; quantity: string; transaction_types: string[];
  sales: ApiMoney; refund: ApiMoney; promotion: ApiMoney; commission: ApiMoney; return_fee: ApiMoney;
  tax_withheld: ApiMoney; wfs_fulfillment_fee: ApiMoney; mcf_fee: ApiMoney; settlement_amount: ApiMoney;
  purchase: ApiMoney | null; head: ApiMoney | null; last_leg: ApiMoney | null; cost_total: ApiMoney | null;
  cost_total_usd: ApiMoney | null; profit_usd: ApiMoney | null; fx_rate: string | null; fx_status: "final" | "missing";
  cost_sources: ApiCostSource[]; cost_entry_ids: string[]; reasons: Reason[]; auto_passed: boolean;
  review_status: ReviewStatus; first_reviewed_by: string | null; first_reviewed_at: string | null;
  final_reviewed_by: string | null; final_reviewed_at: string | null; version: number; calc_version: number;
}
export interface ApiLineMeta { total: number; page: number; page_size: number }
export interface ApiTransactionType { code: string; name_zh: string | null; name_en: string; category: string; translated: boolean }
export interface ApiCostEntry {
  id: string; store_id: string; msku: string; scope_ref: string; shipping_list_code: string | null; outbound_order_no: string | null;
  entry_kind: "confirm" | "override"; purchase_cny: string | null; head_cny: string | null; last_leg_cny: string | null;
  reason: string | null; status: string; version: number; actor_id: string; created_at: string;
}
export interface ApiCostEntryResult { entry: ApiCostEntry; affected_lines: number; recalculated_periods: number; replayed: boolean }
export interface ApiReviewResult { items: { review_id: string; line_key: string; ok: boolean; review_status: string; version: number; error_code: string | null; message: string | null }[]; succeeded: number; failed: number }
export interface ApiRecalcResult { items: { store_id: string; period_key: string; status: string; lines_total: number; lines_new_version: number; auto_passed: number; pending: number }[]; periods_total: number }

export interface LineFilters {
  periodKeys: string[]; storeIds: string[]; statuses: ReviewStatus[]; reasons: Reason[]; transactionTypes: string[];
  lineKinds: LineKind[]; itemIds: string[]; skus: string[]; mskus: string[]; keyword: string;
  sortBy: string; sortOrder: "asc" | "desc"; page: number; pageSize: number;
}

export const DEFAULT_FILTERS: LineFilters = {
  periodKeys: [], storeIds: [], statuses: [], reasons: [], transactionTypes: [], lineKinds: [],
  itemIds: [], skus: [], mskus: [], keyword: "", sortBy: "posted_date", sortOrder: "desc", page: 1, pageSize: 50,
};

const list = (params: URLSearchParams, name: string, values: string[]) => values.forEach((v) => params.append(name, v));

export function lineQuery(filters: LineFilters): string {
  const params = new URLSearchParams();
  list(params, "period_keys", filters.periodKeys);
  list(params, "store_ids", filters.storeIds);
  list(params, "status", filters.statuses);
  list(params, "reason", filters.reasons);
  list(params, "transaction_types", filters.transactionTypes);
  list(params, "line_kinds", filters.lineKinds);
  list(params, "item_ids", filters.itemIds);
  list(params, "skus", filters.skus);
  list(params, "mskus", filters.mskus);
  if (filters.keyword.trim()) params.set("keyword", filters.keyword.trim());
  params.set("sort_by", filters.sortBy);
  params.set("sort_order", filters.sortOrder);
  params.set("page", String(filters.page));
  params.set("page_size", String(filters.pageSize));
  return params.toString();
}

export function usePeriods() {
  return useQuery({
    queryKey: [...ROOT_KEY, "periods"],
    queryFn: async () => (await backendRequest<{ items: ApiPeriod[] }>(`${BASE}/periods`)).data.items,
    retry: false,
  });
}

export function useLines(filters: LineFilters) {
  const query = lineQuery(filters);
  return useQuery({
    queryKey: [...ROOT_KEY, "lines", query],
    queryFn: async () => {
      const envelope = await backendRequest<{ items: ApiLine[] }, ApiLineMeta>(`${BASE}/lines?${query}`);
      return { items: envelope.data.items, total: envelope.meta?.total ?? envelope.data.items.length };
    },
    placeholderData: keepPreviousData,
    retry: false,
  });
}

export function useTransactionTypes() {
  return useQuery({
    queryKey: [...ROOT_KEY, "transaction-types"],
    queryFn: async () => (await backendRequest<{ items: ApiTransactionType[] }>(`${BASE}/transaction-types`)).data.items,
    retry: false,
    staleTime: 5 * 60 * 1000,
  });
}

export async function lookup(kind: "item_id" | "sku" | "msku" | "order_no", q: string, limit = 1000) {
  const params = new URLSearchParams({ kind, q, limit: String(limit) });
  return (await backendRequest<{ kind: string; items: string[]; truncated: boolean }>(`${BASE}/lookup?${params}`)).data;
}

export function useOrderReviewRefresh() {
  const client = useQueryClient();
  return () => client.invalidateQueries({ queryKey: ROOT_KEY });
}

const post = async <T,>(path: string, body: unknown, headers?: Record<string, string>) =>
  (await backendRequest<T>(path, { method: "POST", body: JSON.stringify(body), headers: { "Content-Type": "application/json", ...headers } })).data;

export interface CostEntryInput {
  store_id: string;
  scope: { msku: string; shipping_list_code?: string | null; outbound_order_no?: string | null };
  entry_kind: "confirm" | "override";
  purchase_cny?: string | null; head_cny?: string | null; last_leg_cny?: string | null; reason?: string | null;
}
export const postCostEntry = (input: CostEntryInput, idempotencyKey: string) =>
  post<ApiCostEntryResult>(`${BASE}/cost-entries`, input, { "Idempotency-Key": idempotencyKey });
export const getCostEntry = async (entryId: string) => (await backendRequest<ApiCostEntry>(`${BASE}/cost-entries/${entryId}`)).data;
export const revokeCostEntry = (entryId: string, reason: string, expectedVersion: number) =>
  post<ApiCostEntryResult>(`${BASE}/cost-entries/${entryId}/revoke`, { reason, expected_version: expectedVersion });
export const postReview = (reviewIds: string[], stage: "first" | "final", decision: "pass" | "reject" | "revert", comment?: string) =>
  post<ApiReviewResult>(`${BASE}/review`, { review_ids: reviewIds, stage, decision, comment: comment ?? null });
export const postRecalc = (storeIds: string[], periodKeys: string[]) =>
  post<ApiRecalcResult>(`${BASE}/recalc`, { store_ids: storeIds, period_keys: periodKeys });

const CODE_TEXT: Record<string, string> = {
  MONTH_CLOSED: "该月已结账，先解锁",
  STALE_VERSION: "数据已被他人修改，请刷新",
  STAGE_ORDER: "审核顺序不对（终审前须初审）",
  SAME_REVIEWER: "同一人不能既初审又终审",
  COST_MISSING: "先录成本再审核",
  COST_ENTRY_EXISTS: "这个范围已有未撤销的录入，先撤销再录",
  ALREADY_REVOKED: "这条录入已经撤销",
  ALREADY_PASSED: "自动通过的行不需要审核",
  VALIDATION_ERROR: "填写的内容不符合要求",
  NOT_FOUND: "没有这条数据",
};

export function errorText(error: unknown): string {
  if (!(error instanceof BackendRequestError)) return "操作失败，请稍后重试";
  const code = error.code && CODE_TEXT[error.code];
  const tail = error.requestId ? `（request_id ${error.requestId}）` : "";
  if (code) return `${code}${tail}`;
  if (error.status === 401) return "登录已过期，请重新登录";
  if (error.status === 403) return "没有这个操作的权限（录成本 / 初审 / 终审 / 重算分开授权）";
  if (error.status === 422) return `填写的内容不符合要求${tail}`;
  return `操作失败，请稍后重试${tail}`;
}

export const isForbidden = (error: unknown) => error instanceof BackendRequestError && error.status === 403;

export const STATUS_TEXT: Record<ReviewStatus, { text: string; color: string }> = {
  pending: { text: "待审", color: "orange" },
  auto: { text: "自动通过", color: "green" },
  first_passed: { text: "初审通过", color: "blue" },
  final_passed: { text: "终审通过", color: "green" },
  rejected: { text: "退回", color: "red" },
};
export const REASON_TEXT: Record<Reason, string> = {
  wfs_carrier_shipment: "WFS 承运货件（确认头程）",
  self_fulfilled: "自发货（采购价、头程、尾程）",
  fixed_value: "成本来源 = 固定值",
  last_received: "成本来源 = 最近签收成本",
  cost_missing: "没有成本来源",
  shipment_detail_invalid: "发货单明细不完整",
  owner_missing: "商品无负责人",
  cancelled_refund: "同期卖出又取消（确认无成本）",
};
export const KIND_TEXT: Record<LineKind, string> = { sale: "销售", refund: "退款", mcf: "MCF" };
export const SOURCE_KIND_TEXT: Record<string, string> = {
  shipment: "发货单", entry: "人工录入", fixed_value: "固定值", last_received: "最近签收", missing: "无来源",
  outbound: "出库单", refund: "退款冲回", cancelled_refund: "取消退款",
};

export const n = (value: ApiMoney | null | undefined): number | null => (value ? Number(value.amount) : null);
