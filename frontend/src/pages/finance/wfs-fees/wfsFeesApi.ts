/**
 * WFS 费用明细接口层（/api/finance/wfs-fees）。金额后端给字符串（我方视角：正 = Walmart 付我们，负 = 扣费），
 * 这里转数字只用来显示和合计；写操作全部走接口。店铺代码 / 账单期从沃尔玛账单接口取（回款对账已有）。
 */
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { backendRequest, BackendRequestError } from "@/api/backendApi";

const BASE = "/api/finance/wfs-fees";
export const ROOT_KEY = ["finance-wfs-fees"] as const;
export const MAX_UPLOAD_BYTES = 16 * 1024 * 1024;

export type FeeSource = "settlement" | "storage" | "inbound";
export type Attribution = "matched" | "unmatched" | "allocated" | "allocated_check" | "unallocated" | "company";

export interface ApiFeeType { code: string; name: string; source: FeeSource }
export interface ApiLine {
  id: string; store_id: string; fee_source: FeeSource; fee_type: string; reason_code: string; detail: string; source_ref: string;
  transaction_date: string; date_charged: string; period_start: string | null; period_end: string | null;
  report_key: string | null; report_date: string | null; bill_match: string; po_number: string; partner_id: string;
  gtin: string; item_id: string; msku: string; local_sku: string; quantity: string | null; amount_usd: string;
  original_amount: string | null; discount_savings: string | null; attribution: Attribution; allocation_basis: string;
  parent_line_id: string | null; missing_since: string | null; raw_file_id: string; adjusted: boolean; children: ApiLine[];
}
export interface ApiLineList { items: ApiLine[]; total: number; page: number; page_size: number }
export interface ApiSummaryRow { store_id: string; report_key: string | null; report_date: string | null; fee_type: string; rows: number; amount_usd: string }
export interface ApiSummary { items: ApiSummaryRow[]; total_amount_usd: string }
export interface ApiCheck {
  store_id: string; report_key: string; fee_type: string; report_date: string | null; lingxing_amount: string | null; lingxing_rows: number;
  report_amount: string | null; report_rows: number; status: "ok" | "diff" | "lx_only" | "report_only";
  verified_reason: string | null; verified_by: string | null; verified_at: string | null; refreshed_at: string;
}
export interface ApiFile {
  id: string; store_id: string; fee_source: FeeSource; origin: string; file_name: string; period_start: string | null; period_end: string | null;
  declared_total: string | null; row_count: number; rows_new: number; rows_duplicate: number; status: "parsed" | "rejected" | "empty";
  reject_reason: string | null; actor: string; created_at: string;
}
export interface ApiImport {
  file_id: string; file_name: string; store_id: string; fee_source: FeeSource; period_start: string | null; period_end: string | null;
  status: "parsed" | "rejected" | "empty"; rows_parsed: number; rows_new: number; rows_duplicate: number; duplicate_of_file: boolean;
  reject_reason: string | null; warnings: string[]; needs_store: boolean;
}
export interface ApiBillPeriod { store_id: string; store_code: string; store_name: string | null; report_key: string | null; report_date: string | null; period_start_date: string | null; period_end_date: string | null }

export interface LineFilter {
  store_id?: string; report_key?: string; fee_type?: string; fee_source?: FeeSource; attribution?: string;
  date_from?: string; date_to?: string; q?: string; include_missing?: boolean; page: number; page_size: number;
}
/** 归属筛选按三档传给后端（逗号分隔多个细分码） */
export const attributionParam = (group?: AttributionGroup) => (group ? ATTRIBUTION_GROUP_CODES[group].join(",") : undefined);

const qs = (params: object) => {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params as Record<string, unknown>)) if (value !== undefined && value !== "" && value !== null) search.set(key, String(value));
  const text = search.toString();
  return text ? `?${text}` : "";
};

export const num = (value: string | null | undefined) => (value == null || value === "" ? null : Number(value));

export const SOURCE_TEXT: Record<FeeSource, string> = { settlement: "结算报表", storage: "仓储费报表", inbound: "入库运输报告" };
/** 页面上归属只分三档（Rocky 11-13：不要那么复杂）；细分原因放「依据」列。 */
export type AttributionGroup = "done" | "todo" | "company";
export const ATTRIBUTION_GROUP: Record<Attribution, AttributionGroup> = {
  matched: "done", allocated: "done", allocated_check: "todo", unmatched: "todo", unallocated: "todo", company: "company",
};
export const ATTRIBUTION_GROUP_TEXT: Record<AttributionGroup, string> = { done: "已到商品", todo: "待处理", company: "记公司" };
export const ATTRIBUTION_GROUP_CODES: Record<AttributionGroup, Attribution[]> = {
  done: ["matched", "allocated"], todo: ["unmatched", "unallocated", "allocated_check"], company: ["company"],
};
/** 细分原因（依据列 / 导出用） */
export const ATTRIBUTION_TEXT: Record<Attribution, string> = {
  matched: "GTIN 对上商品", unmatched: "GTIN 对不上商品", allocated: "按规则分摊", allocated_check: "已分摊，基数待核", unallocated: "等货件明细，未分摊", company: "记公司",
};
export const CHECK_TEXT: Record<ApiCheck["status"], string> = { ok: "一致", diff: "不一致", lx_only: "报表缺", report_only: "领星缺" };

export function useFeeTypes() {
  return useQuery({ queryKey: [...ROOT_KEY, "types"], queryFn: async () => (await backendRequest<ApiFeeType[]>(`${BASE}/fee-types`)).data, staleTime: 3_600_000, retry: false });
}
export function useLines(filter: LineFilter) {
  return useQuery({ queryKey: [...ROOT_KEY, "lines", filter], queryFn: async () => (await backendRequest<ApiLineList>(`${BASE}/lines${qs(filter)}`)).data, retry: false, placeholderData: (previous) => previous });
}
export function useSummary(filter: Pick<LineFilter, "store_id" | "report_key" | "date_from" | "date_to">) {
  return useQuery({ queryKey: [...ROOT_KEY, "summary", filter], queryFn: async () => (await backendRequest<ApiSummary>(`${BASE}/summary${qs(filter)}`)).data, retry: false });
}
export function useChecks(filter: { store_id?: string; report_key?: string }) {
  return useQuery({ queryKey: [...ROOT_KEY, "checks", filter], queryFn: async () => (await backendRequest<{ items: ApiCheck[] }>(`${BASE}/checks${qs({ ...filter, only_problem: true })}`)).data.items, retry: false });
}
export function useFiles(enabled: boolean) {
  return useQuery({ queryKey: [...ROOT_KEY, "files"], queryFn: async () => (await backendRequest<{ items: ApiFile[] }>(`${BASE}/files`)).data.items, enabled, retry: false });
}
/** 店铺代码和账单期来自领星同步的沃尔玛账单（本模块自己的接口，同一个查看权限）。 */
export function useBillPeriods() {
  return useQuery({
    queryKey: [...ROOT_KEY, "bill-periods"],
    queryFn: async () => (await backendRequest<{ items: ApiBillPeriod[] }>(`${BASE}/periods`)).data.items,
    retry: false, staleTime: 600_000,
  });
}
export function useWfsRefresh() {
  const client = useQueryClient();
  return () => client.invalidateQueries({ queryKey: ROOT_KEY });
}

const post = async <T,>(path: string, body?: unknown) =>
  (await backendRequest<T>(path, { method: "POST", body: body === undefined ? undefined : JSON.stringify(body) })).data;

export async function uploadReport(file: File, options: { storeId?: string; periodStart?: string; periodEnd?: string }): Promise<ApiImport[]> {
  const headers: Record<string, string> = { "Content-Type": "application/octet-stream", "X-File-Name": encodeURIComponent(file.name) };
  if (options.storeId) headers["X-Store-Id"] = options.storeId;
  if (options.periodStart) headers["X-Period-Start"] = options.periodStart;
  if (options.periodEnd) headers["X-Period-End"] = options.periodEnd;
  // CSV 返回一条；卖家后台下载的 ZIP 按里面每个 CSV 各一条
  return (await backendRequest<{ items: ApiImport[] }>(`${BASE}/imports`, { method: "POST", body: file, headers })).data.items;
}
export const adjustLine = (lineId: string, body: { kind: "realloc" | "company"; reason: string; payload?: Record<string, unknown> }) =>
  post<ApiLine>(`${BASE}/lines/${lineId}/adjust`, body);
export const verifyCheck = (check: Pick<ApiCheck, "store_id" | "report_key" | "fee_type">, reason: string) =>
  post<ApiCheck>(`${BASE}/checks/verify`, { ...check, reason });

const CODE_TEXT: Record<string, string> = {
  WFS_FEE_STORE_MISMATCH: "文件里的 Partner ID 和选的店铺不一致",
  WFS_FEE_LINE_NOT_FOUND: "这笔费用不存在，或者它是分摊子行（请调整原行）",
  WFS_FEE_REASON_REQUIRED: "要写原因",
  WFS_FEE_SHARES_REQUIRED: "要给出分到哪些商品、各多少",
  WFS_FEE_SHARES_SUM: "分摊合计和原行金额不相等",
  WFS_FEE_CHECK_NOT_FOUND: "没有这条核对记录",
  WFS_FEE_STORAGE_NOT_CONFIGURED: "原件存储目录没有配置，请联系管理员",
  WFS_FEE_UPLOAD_TOO_LARGE: "文件超过 16MB",
  WFS_FEE_EMPTY_UPLOAD: "文件是空的",
};
export function wfsErrorText(error: unknown): string {
  if (!(error instanceof BackendRequestError)) return "操作失败，请稍后重试";
  if (error.code && CODE_TEXT[error.code]) return CODE_TEXT[error.code];
  if (error.status === 401) return "登录已过期，请重新登录";
  if (error.status === 403) return "没有这个操作的权限（导入 / 调整分开授权）";
  if (error.status === 413) return "文件超过 16MB";
  if (error.status === 422) return "填写的内容不符合要求，请检查后再提交";
  return "操作失败，请稍后重试";
}
export const isForbidden = (error: unknown) => error instanceof BackendRequestError && error.status === 403;
