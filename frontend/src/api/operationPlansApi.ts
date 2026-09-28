import { BackendRequestError, backendRequest, type BackendEnvelope } from "@/api/backendApi";

export type OperationPlanPeriodType = "month" | "quarter";
export type OperationStatus = "normal" | "new_product" | "clearance";
export type PlanStatus = "normal" | "lagging" | "severe_lagging" | "unplanned" | "clearance";
export type StockStatus = "normal" | "risk";
export type SearchField = "item_id" | "sku" | "msku" | "product_name";
export type ConflictPolicy = "skip_existing" | "overwrite_existing";

export interface OperationPlanSummary {
  sales_target_amount: number;
  sales_actual_amount: number;
  sales_forecast_amount: number;
  gross_profit_target_amount: number;
  gross_profit_actual_amount: number;
  gross_profit_forecast_amount: number;
  product_count: number;
  unplanned_count: number;
  lagging_count: number;
  severe_lagging_count: number;
  adjusted_product_count: number;
  sales_target_adjust_amount: number;
  gross_profit_target_adjust_amount: number;
  clearance_count: number;
  period_label: string;
  period_progress_rate: number;
}

export interface OperationPlanOwnerRow {
  owner_ref?: string | null;
  owner_name: string;
  product_count: number;
  sales_target_amount: number;
  sales_actual_amount: number;
  sales_actual_qty: number;
  sales_completion_rate: number;
  gross_profit_target_amount: number;
  gross_profit_actual_amount: number;
  gross_profit_completion_rate: number;
  lagging_count: number;
  severe_lagging_count: number;
  stock_risk_count: number;
}

export interface OperationPlanSummaryData {
  summary: OperationPlanSummary;
  owners: OperationPlanOwnerRow[];
}

export interface OperationPlanProductRow {
  plan_id: string;
  item_id: string;
  product_name?: string | null;
  sku?: string | null;
  msku: string;
  owner_ref?: string | null;
  owner_name?: string | null;
  store_id?: string | null;
  store_name?: string | null;
  last_sales_amount: number;
  last_gross_profit_amount: number;
  last_gross_profit_rate: number;
  sales_target_amount: number;
  sales_actual_amount: number;
  sales_actual_qty: number;
  sales_completion_rate: number;
  sales_forecast_amount: number;
  gross_profit_target_amount: number;
  gross_profit_actual_amount: number;
  gross_profit_completion_rate: number;
  gross_profit_forecast_amount: number;
  wfs_available_qty: number;
  inbound_qty: number;
  arriving_qty: number;
  inventory_support_rate: number;
  operation_status: OperationStatus;
  plan_status: PlanStatus;
  stock_status: StockStatus;
  adjusted: boolean;
  event_count: number;
  remark?: string | null;
}

export interface OperationPlanProductListData {
  items: OperationPlanProductRow[];
  total: number;
  page: number;
  page_size: number;
}

export interface OperationPlanOptionsData {
  owners: Array<{ label: string; value: string }>;
  stores: Array<{ label: string; value: string }>;
  operation_statuses: Array<{ label: string; value: string }>;
  plan_statuses: Array<{ label: string; value: string }>;
  stock_statuses: Array<{ label: string; value: string }>;
}

export interface OperationPlanImportRowResult {
  row_number: number;
  item_id?: string | null;
  msku?: string | null;
  sales_target_amount?: number | null;
  gross_profit_target_amount?: number | null;
  remark?: string | null;
  import_status: "success" | "updated" | "skipped" | "failed";
  error_message?: string | null;
  suggestion?: string | null;
}

export interface OperationPlanImportData {
  batch_id: string;
  status: "completed" | "partial_completed" | "failed";
  row_count: number;
  success_count: number;
  failed_count: number;
  warning_count: number;
  existing_count: number;
  created_plan_count: number;
  updated_plan_count: number;
  skipped_count: number;
  rows: OperationPlanImportRowResult[];
}

export interface OperationPlanEventRow {
  event_id: string;
  event_type: string;
  event_label: string;
  sales_target_amount?: number | null;
  gross_profit_target_amount?: number | null;
  reason?: string | null;
  actor_name: string;
  created_at: string;
}

export interface OperationPlanEventListData {
  items: OperationPlanEventRow[];
}

const apiBase = "/api/operations/plans";

const appendCommonParams = (params: URLSearchParams, periodType: OperationPlanPeriodType, periodKey: string) => {
  params.set("period_type", periodType);
  params.set("period_key", periodKey);
};

const buildUrl = (path: string, params?: URLSearchParams) => {
  const query = params?.toString();
  return query ? `${apiBase}${path}?${query}` : `${apiBase}${path}`;
};

export async function fetchOperationPlanSummary(periodType: OperationPlanPeriodType, periodKey: string) {
  const params = new URLSearchParams();
  appendCommonParams(params, periodType, periodKey);
  const response = await backendRequest<OperationPlanSummaryData>(buildUrl("/summary", params));
  return response.data;
}

export async function fetchOperationPlanProducts(args: {
  periodType: OperationPlanPeriodType;
  periodKey: string;
  ownerRef?: string;
  storeId?: string;
  operationStatus?: OperationStatus;
  planStatus?: PlanStatus;
  stockStatus?: StockStatus;
  searchField: SearchField;
  keyword?: string;
  batchValues?: string[];
  page: number;
  pageSize: number;
}) {
  const params = new URLSearchParams();
  appendCommonParams(params, args.periodType, args.periodKey);
  if (args.ownerRef) params.set("owner_ref", args.ownerRef);
  if (args.storeId) params.set("store_id", args.storeId);
  if (args.operationStatus) params.set("operation_status", args.operationStatus);
  if (args.planStatus) params.set("plan_status", args.planStatus);
  if (args.stockStatus) params.set("stock_status", args.stockStatus);
  params.set("search_field", args.searchField);
  if (args.keyword) params.set("keyword", args.keyword);
  for (const value of args.batchValues ?? []) params.append("batch_values", value);
  params.set("page", String(args.page));
  params.set("page_size", String(args.pageSize));
  const response = await backendRequest<OperationPlanProductListData>(buildUrl("/products", params));
  return response.data;
}

export async function fetchOperationPlanOptions(periodType: OperationPlanPeriodType, periodKey: string) {
  const params = new URLSearchParams();
  appendCommonParams(params, periodType, periodKey);
  const response = await backendRequest<OperationPlanOptionsData>(buildUrl("/options", params));
  return response.data;
}

export async function updateOperationPlanTargets(planId: string, payload: {
  sales_target_amount: number;
  gross_profit_target_amount: number;
  reason?: string;
}) {
  const response = await backendRequest<OperationPlanProductRow>(`${apiBase}/products/${planId}/targets`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
  return response.data;
}

export async function clearOperationPlanProduct(planId: string, reason?: string) {
  const response = await backendRequest<OperationPlanProductRow>(`${apiBase}/products/${planId}/clearance`, {
    method: "POST",
    body: JSON.stringify({ reason }),
  });
  return response.data;
}

export async function fetchOperationPlanEvents(planId: string) {
  const response = await backendRequest<OperationPlanEventListData>(`${apiBase}/products/${planId}/events`);
  return response.data;
}

export async function importOperationPlans(args: {
  periodType: OperationPlanPeriodType;
  periodKey: string;
  conflictPolicy: ConflictPolicy;
  file: File;
}) {
  const params = new URLSearchParams();
  appendCommonParams(params, args.periodType, args.periodKey);
  params.set("conflict_policy", args.conflictPolicy);
  const envelope = await rawEnvelopeRequest<OperationPlanImportData>(buildUrl("/import", params), {
    method: "POST",
    body: args.file,
    headers: {
      "Content-Type": "application/octet-stream",
      "X-File-Name": encodeURIComponent(args.file.name),
    },
  });
  return envelope.data;
}

export async function downloadOperationPlanTemplate(periodType: OperationPlanPeriodType, periodKey: string) {
  const params = new URLSearchParams();
  appendCommonParams(params, periodType, periodKey);
  await downloadFile(buildUrl("/template", params), "运营计划导入模板.xlsx");
}

export async function downloadOperationPlanFailedRows(batchId: string) {
  await downloadFile(`${apiBase}/import-batches/${batchId}/failed-export`, "运营计划导入失败明细.xlsx");
}

async function rawEnvelopeRequest<T>(path: string, init?: RequestInit): Promise<BackendEnvelope<T>> {
  const previewToken = import.meta.env.VITE_PRODUCT_MANAGEMENT_PREVIEW_TOKEN;
  const response = await fetch(path, {
    credentials: "same-origin",
    ...init,
    headers: {
      ...(previewToken ? { "X-Product-Management-Preview-Token": previewToken } : {}),
      ...init?.headers,
    },
  });
  const body = await response.json() as BackendEnvelope<T>;
  if (!response.ok || !body.success) {
    const errorCode = body.error?.code ?? "BACKEND_REQUEST_FAILED";
    throw new BackendRequestError(response.status, errorCode, body.request_id);
  }
  return body;
}

async function downloadFile(path: string, filename: string) {
  const previewToken = import.meta.env.VITE_PRODUCT_MANAGEMENT_PREVIEW_TOKEN;
  const response = await fetch(path, {
    credentials: "same-origin",
    headers: {
      ...(previewToken ? { "X-Product-Management-Preview-Token": previewToken } : {}),
    },
  });
  if (!response.ok) {
    throw new BackendRequestError(response.status, "DOWNLOAD_FAILED");
  }
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}
