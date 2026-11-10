/**
 * 回款对账接口层（/api/finance/payout-recon，PR-2）+ 沃尔玛账单同步状态（/api/finance/walmart-bills/sync）。
 * 金额后端按字符串给，这里转数字，只用来显示和合计；写操作全部走接口，页面不留本地状态。
 */
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { backendRequest, BackendRequestError } from "@/api/backendApi";

const BASE = "/api/finance/payout-recon";
const BILLS = "/api/finance/walmart-bills";
export const PERIODS_KEY = ["finance-payout-recon", "periods"] as const;
export const ACCOUNTS_KEY = ["finance-payout-recon", "accounts"] as const;

export type PayState = "not_due" | "waiting" | "paid" | "mismatch" | "unpaid" | "no_pay" | "voided";
export type ReviewStage = "todo" | "ok1" | "rej2" | "ok2";
export type ReviewKind = "review1_pass" | "review2_pass" | "review2_reject";

export interface ApiFollow { content: string; case_no: string | null; next_follow_date: string | null; actor: string; created_at: string }
export interface ApiPeriod {
  store_id: string; store_code: string; store_name: string | null; report_key: string; report_date: string;
  period_start_date: string | null; period_end_date: string | null; currency_code: string | null; payable_amount: string;
  period_status: string; pay_state: PayState; anomaly: boolean; arrived_amount: string | null; diff: string | null; arrived_date: string | null;
  line_uid: string | null; match_id: string | null; match_method: "auto" | "manual" | null; match_size: number;
  account_key: string | null; account_name: string | null; org: string | null; payee: string | null;
  stage: ReviewStage; stage_reason: string | null; follow_count: number; latest_follow: ApiFollow | null;
}
export interface ApiPeriodList { items: ApiPeriod[]; today: string; recon_start: string; auto_ready: number; limit: number; truncated: boolean }
export interface ApiPeriodDetail {
  period: ApiPeriod;
  amounts_by_type: Record<string, string>;
  reviews: { kind: string; reason: string | null; actor: string; created_at: string }[];
  follow_ups: ApiFollow[];
  matches: { match_id: string; line_uid: string; method: string; payable_amount: string; created_by: string; created_at: string; undone_at: string | null; undone_by: string | null; undo_reason: string | null }[];
}
export interface ApiLine { line_uid: string; account_key: string; account_name: string; business_date: string; amount: string; currency_code: string; counterparty_name: string; description: string; matched: boolean }
export interface ApiAccountRow {
  id: string; store_id: string; store_code: string; account_key: string; account_name: string; org: string; payee: string;
  effective_from: string; effective_to: string | null; is_active: boolean; change_reason: string | null; updated_by: string; updated_at: string;
}
export interface ApiAccountList {
  items: ApiAccountRow[];
  accounts: { account_key: string; account_name: string; org: string; currency_code: string }[];
  stores: { store_id: string; store_code: string; store_name: string | null }[];
}
export interface ApiSync { run_id: string | null; status: string; trigger_type: string | null; started_at: string | null; finished_at: string | null; error_code: string | null; last_success_at: string | null }

/** 页面一行 = 一店一期。 */
export interface ReconRow {
  key: string;
  sid: string;
  code: string;
  rk: string;
  payDate: string;
  cycleFrom: string;
  cycleTo: string;
  currency: string;
  payable: number;
  arrived: number | null;
  arrivedAt: string;
  diff: number | null;
  state: PayState;
  anomaly: boolean;
  org: string;
  payee: string;
  accountName: string;
  lineUid: string;
  matchId: string;
  matchMethod: "auto" | "manual" | null;
  matchSize: number;
  stage: ReviewStage;
  stageReason: string;
  followCount: number;
  latestFollow: ApiFollow | null;
}

const num = (value: string | null) => (value == null ? null : Number(value));

export function toRow(item: ApiPeriod): ReconRow {
  return {
    key: `${item.store_id}|${item.report_key}`,
    sid: item.store_id,
    code: item.store_code,
    rk: item.report_key,
    payDate: item.report_date,
    cycleFrom: item.period_start_date ?? "",
    cycleTo: item.period_end_date ?? "",
    currency: item.currency_code ?? "USD",
    payable: Number(item.payable_amount),
    arrived: num(item.arrived_amount),
    arrivedAt: item.arrived_date ?? "",
    diff: num(item.diff),
    state: item.pay_state,
    anomaly: item.anomaly,
    org: item.org ?? "",
    payee: item.payee ?? "",
    accountName: item.account_name ?? "",
    lineUid: item.line_uid ?? "",
    matchId: item.match_id ?? "",
    matchMethod: item.match_method,
    matchSize: item.match_size,
    stage: item.stage,
    stageReason: item.stage_reason ?? "",
    followCount: item.follow_count,
    latestFollow: item.latest_follow,
  };
}

export const periodKey = (row: ReconRow) => ({ store_id: row.sid, report_key: row.rk });

export function usePayoutPeriods() {
  return useQuery({
    queryKey: PERIODS_KEY,
    queryFn: async () => (await backendRequest<ApiPeriodList>(`${BASE}/periods`)).data,
    retry: false,
  });
}

export function usePeriodDetail(row?: ReconRow) {
  return useQuery({
    queryKey: ["finance-payout-recon", "detail", row?.key],
    queryFn: async () => (await backendRequest<ApiPeriodDetail>(`${BASE}/periods/${row?.sid}/${encodeURIComponent(row?.rk ?? "")}`)).data,
    enabled: Boolean(row),
    retry: false,
  });
}

export function useCandidateLines(storeId: string | undefined, enabled: boolean) {
  return useQuery({
    queryKey: ["finance-payout-recon", "lines", storeId],
    queryFn: async () => (await backendRequest<{ items: ApiLine[] }>(`${BASE}/lines?store_id=${storeId ?? ""}`)).data.items,
    enabled: enabled && Boolean(storeId),
    retry: false,
  });
}

export function useAccountMap(enabled: boolean) {
  return useQuery({ queryKey: ACCOUNTS_KEY, queryFn: async () => (await backendRequest<ApiAccountList>(`${BASE}/accounts`)).data, enabled, retry: false });
}

export function useBillSync() {
  return useQuery({ queryKey: ["finance-payout-recon", "sync"], queryFn: async () => (await backendRequest<ApiSync>(`${BILLS}/sync`)).data, retry: false, refetchInterval: 30_000 });
}

/** 写完一律刷新期次、详情、映射。 */
export function useReconRefresh() {
  const client = useQueryClient();
  return () => client.invalidateQueries({ queryKey: ["finance-payout-recon"] });
}

const post = async <T,>(path: string, body?: unknown, method = "POST") =>
  (await backendRequest<T>(path, { method, body: body === undefined ? undefined : JSON.stringify(body) })).data;

export const startBillSync = () => post<ApiSync>(`${BILLS}/sync`);
export const autoMatch = () => post<{ matched_periods: number; matched_lines: number }>(`${BASE}/auto-match`);
export const createMatch = (lineUid: string, rows: ReconRow[], note?: string) =>
  post<{ match_id: string; periods: number }>(`${BASE}/matches`, { line_uid: lineUid, periods: rows.map(periodKey), note: note || undefined });
export const undoMatch = (matchId: string, reason: string) => post<{ match_id: string; periods: number }>(`${BASE}/matches/${matchId}/undo`, { reason });
export const postReview = (kind: ReviewKind, rows: ReconRow[], reason?: string) =>
  post<{ done: number; skipped: { store_id: string; report_key: string; reason: string }[] }>(`${BASE}/reviews`, { kind, periods: rows.map(periodKey), reason: reason || undefined });
export const postFollow = (row: ReconRow, values: { content: string; caseNo?: string; nextAt?: string }) =>
  post<ApiFollow>(`${BASE}/follow-ups`, { ...periodKey(row), content: values.content, case_no: values.caseNo || undefined, next_follow_date: values.nextAt || undefined });
export const createAccount = (body: { store_id: string; account_key: string; payee: string; effective_from: string; reason?: string }) => post<ApiAccountRow>(`${BASE}/accounts`, body);
export const updateAccount = (id: string, body: { account_key: string; payee: string; reason?: string }) => post<ApiAccountRow>(`${BASE}/accounts/${id}`, body, "PUT");
export const deactivateAccount = (id: string, reason: string) => post<null>(`${BASE}/accounts/${id}/deactivate`, { reason });

const CODE_TEXT: Record<string, string> = {
  PAYOUT_RECON_STAGE_NOT_ALLOWED: "已初审 / 终审的期次不能改配对，先请终审驳回",
  PAYOUT_RECON_CONFLICT: "这一期或这笔到账已经配过了（或账单作废），刷新后再看",
  PAYOUT_RECON_NOT_FOUND: "找不到这一期或这笔到账，刷新后再看",
  PAYOUT_RECON_INVALID: "填写的内容不符合要求（原因必填、币种要一致、账户要有效）",
  WALMART_BILL_SYNC_NOT_CONFIGURED: "沃尔玛账单同步任务还没打开，请联系管理员",
  WALMART_BILL_SYNC_UNAVAILABLE: "任务队列暂时不可用，请稍后再试",
};

export function reconErrorText(error: unknown): string {
  if (!(error instanceof BackendRequestError)) return "操作失败，请稍后重试";
  if (error.code && CODE_TEXT[error.code]) return CODE_TEXT[error.code];
  if (error.status === 401) return "登录已过期，请重新登录";
  if (error.status === 403) return "没有这个操作的权限（初审 / 终审 / 跟进分开授权）";
  if (error.status === 422) return "填写的内容不符合要求，请检查后再提交";
  return "操作失败，请稍后重试";
}

export const isForbidden = (error: unknown) => error instanceof BackendRequestError && error.status === 403;
