/**
 * 日记账接口层（/api/finance/cashflow）。
 * 数据来源由 VITE_FINANCE_CASH_SOURCE 决定：demo 读 Demo 快照，api 读接口；不设时开发环境 demo、正式构建 api。
 * 接口结果转成页面现有的 CashSnapshot 结构，页面组件不用分两套。金额后端按字符串给，这里才转数字，只用来显示。
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { backendRequest, BackendRequestError } from "@/api/backendApi";
import type { CashAccount, CashLine, CashSnapshot, FeishuApproval } from "@/pages/finance/localFinData";
import type { FsDetail } from "@/pages/finance/cash-flow/data";

const BASE = "/api/finance/cashflow";
const PAGE_SIZE = 2000;

export const resolveCashSource = (value: string | undefined, isDev: boolean): "demo" | "api" =>
  value === "api" || value === "demo" ? value : isDev ? "demo" : "api";

export const CASH_SOURCE = resolveCashSource(import.meta.env.VITE_FINANCE_CASH_SOURCE as string | undefined, import.meta.env.DEV);
export const isCashLive = CASH_SOURCE === "api";

/** 每个资金流水页读什么：接口版日记账读接口；开发环境其余页读 Demo；正式构建其余页显示「建设中」。 */
export const cashViewSource = (view: string, isDev: boolean, live: boolean): "live" | "demo" | "building" =>
  view === "journal" && live ? "live" : isDev ? "demo" : "building";

export type LineEventKind = "review1_pass" | "review1_reject" | "review2_pass" | "review2_reject" | "set_category" | "attach_ref" | "detach_ref" | "exclude" | "unexclude";

export interface ApiAccount {
  account_key: string; display_name: string; entity: string; currency_code: string; kind: string; provider: string; account_no_last4: string; is_active: boolean;
  line_count: number; last_file_name: string | null; cover_from: string | null; cover_to: string | null; cover_source: string | null;
}
export interface ApiCategory { code: string; big: string; name: string; is_internal: boolean; is_exclude: boolean }
export interface ApiLine {
  line_uid: string; account_key: string; business_date: string; month: string; time: string | null; currency_code: string;
  amount: string; amount_cny: string | null; balance_after: string | null; description: string; memo: string; counterparty_name: string; counterparty_account_last4: string;
  source_ref: string; file_row_order: number; category_code: string | null; category_source: string; pair_id: string | null; flags: string[]; refs: string[];
  exclude_amount: string | null; exclude_reason: string | null; list_excluded_cny: string; stage: string; stage_reason: string | null; review_note: string | null; version: number;
  approval_candidates?: string[];
}
export interface ApiAnomaly { type: string; account_key: string; date: string; message: string; amount: string | null; line_uid: string | null }
export interface ApiFileResult {
  file_id: string | null; file_name: string; status: string; reject_reason: string | null; duplicate_of_file: boolean; account_keys: string[];
  rows_parsed: number; rows_new: number; rows_duplicate: number; balance_chain_ok: boolean | null; warnings: string[];
}

/** 接口流水：页面的 CashLine 加上写操作要用的字段。 */
export interface LiveCashLine extends CashLine { uid: string; version: number; stage: string; stageReason?: string; reviewNote?: string; excludeReason?: string; candidates: string[] }

export interface ApiApproval {
  serial: string; kind: string; status: string; status_text: string; state: string; started_at: string; completed_at: string; handled_at: string; applicant: string;
  reason: string; amount: string | null; currency_code: string; amount_cny: string | null; pay_method: string; invoice: string; payee: string; bank: string; last4: string;
  fee_category: string; related_serial: string; items: { content: string; amount: string | null; category: string }[];
  attachments: { source: string; what: string; item: number; is_image: boolean; title: string }[];
  records: { node: string; act: string; who: string; time: string; note: string; files: number }[];
  comments: { who: string; time: string; note: string }[];
  paid: { line_uid: string; amount_cny: string | null }[]; paid_sum: string; fetched_at: string | null;
}
export interface ApprovalSyncState { run_id: string | null; status: string; started_at: string | null; finished_at: string | null; error_code: string | null; records_seen: number; records_written: number; last_success_at: string | null }
export const asLive = (line: CashLine) => ("uid" in line ? (line as LiveCashLine) : undefined);

const num = (value: string | null | undefined) => (value == null ? null : Number(value));

export function toCashAccount(row: ApiAccount): CashAccount {
  return { id: row.account_key, name: row.display_name, entity: row.entity, cur: row.currency_code, kind: row.kind, stmt: row.account_no_last4 ? `尾号 ${row.account_no_last4}` : "" };
}

export function toCashLine(row: ApiLine): LiveCashLine {
  return {
    id: `${row.account_key}:${row.business_date}:${row.line_uid.slice(-6)}`,
    uid: row.line_uid,
    version: row.version,
    acct: row.account_key,
    date: row.business_date,
    time: row.time ?? undefined,
    m: row.month,
    cur: row.currency_code,
    amt: Number(row.amount),
    cny: num(row.amount_cny),
    bal: num(row.balance_after),
    sum: row.description,
    memo: row.memo,
    party: row.counterparty_name,
    refs: row.refs,
    cat: row.category_code ?? "",
    cat_src: row.category_source,
    pair: row.pair_id ?? "",
    flags: row.flags,
    masked: false,
    ord: row.file_row_order,
    excl: row.exclude_amount != null || Number(row.list_excluded_cny) > 0,
    stage: row.stage,
    stageReason: row.stage_reason ?? undefined,
    reviewNote: row.review_note ?? undefined,
    excludeReason: row.exclude_reason ?? undefined,
    candidates: row.approval_candidates ?? [],
  };
}

export function toFeishuApproval(row: ApiApproval, idOfLine: Map<string, string>): FeishuApproval {
  const paid = row.paid.flatMap((item) => {
    const line = idOfLine.get(item.line_uid);
    return line ? [{ line, date: "", acct: "", amt: item.amount_cny == null ? null : Number(item.amount_cny), cur: "CNY" }] : [];
  });
  return {
    serial: row.serial, kind: row.kind, status: row.status_text, start: row.started_at.slice(0, 10), end: row.completed_at.slice(0, 10), applicant: row.applicant, reason: row.reason,
    amount: num(row.amount), cur: row.currency_code, pay: row.pay_method, payee: row.payee, bank: row.bank, last4: row.last4,
    items: row.items.map((item) => ({ c: item.content, a: num(item.amount) })), rel: row.related_serial, invoice: row.invoice, src: "飞书审批同步", cat: "", masked: false,
    paid, paid_sum: Number(row.paid_sum), cny: num(row.amount_cny), state: row.state,
  };
}

/** 附件只存了元数据：name 留空，页面据此只列文件名，不出下载链接。 */
export function toFsDetail(row: ApiApproval): FsDetail {
  return {
    serial: row.serial, kind: row.kind, status: row.status_text, start: row.started_at, end: row.completed_at, handled: row.handled_at, applicant: row.applicant,
    reason: row.reason, amount: num(row.amount), cur: row.currency_code, invoice: row.invoice, pay: row.pay_method, payee: row.payee, account_name: row.payee, bank: row.bank, last4: row.last4,
    items: row.items.map((item) => ({ c: item.content, a: num(item.amount) })),
    files: row.attachments.map((file) => ({ name: "", src: file.source, what: file.what, item: file.item, img: file.is_image, title: file.title })),
    records: row.records, comments: row.comments,
  };
}

export function buildLiveSnapshot(accounts: ApiAccount[], categories: ApiCategory[], lines: ApiLine[], anomalies: ApiAnomaly[], approvals: ApiApproval[] = []): CashSnapshot {
  const cashLines = lines.map(toCashLine);
  const idOf = new Map(cashLines.map((line) => [line.uid, line.id]));
  const months = Array.from(new Set(cashLines.map((line) => line.m))).sort();
  return {
    meta: { built: "", start: months[0] ?? "", months, feishu_src: ["飞书审批同步"], fx: {}, summary: {} },
    accounts: accounts.map(toCashAccount),
    cats: categories.map((row) => ({ code: row.code, big: row.big, name: row.name, internal: row.is_internal })),
    lines: cashLines,
    feishu: approvals.map((row) => toFeishuApproval(row, idOf)),
    flow: { months, by_acct: {} },
    anomalies: anomalies.map((row) => ({
      type: row.type, sev: "", acct: row.account_key, date: row.date, msg: row.message, amt: num(row.amount),
      ...(row.line_uid && idOf.has(row.line_uid) ? { line: idOf.get(row.line_uid) } : {}),
    })),
  };
}

async function fetchAllLines(): Promise<ApiLine[]> {
  const all: ApiLine[] = [];
  for (let page = 1; ; page += 1) {
    const { data } = await backendRequest<{ items: ApiLine[]; total: number }>(`${BASE}/lines?page=${page}&page_size=${PAGE_SIZE}`);
    all.push(...data.items);
    if (!data.items.length || all.length >= data.total) return all;
  }
}

async function fetchSnapshot() {
  const [accounts, categories, lines, anomalies, approvals] = await Promise.all([
    backendRequest<ApiAccount[]>(`${BASE}/accounts`),
    backendRequest<ApiCategory[]>(`${BASE}/categories`),
    fetchAllLines(),
    backendRequest<ApiAnomaly[]>(`${BASE}/anomalies`),
    backendRequest<ApiApproval[]>(`${BASE}/approvals`),
  ]);
  return {
    accounts: accounts.data,
    snapshot: buildLiveSnapshot(accounts.data, categories.data, lines, anomalies.data, approvals.data),
    details: Object.fromEntries(approvals.data.map((row) => [row.serial, toFsDetail(row)])) as Record<string, FsDetail>,
  };
}

const QUERY_KEY = ["finance-cashflow", "journal"];

export function useLiveJournal(enabled: boolean) {
  return useQuery({ queryKey: QUERY_KEY, queryFn: fetchSnapshot, enabled, retry: false });
}

export function useRefreshJournal() {
  const client = useQueryClient();
  return () => client.invalidateQueries({ queryKey: QUERY_KEY });
}

const SYNC_KEY = ["finance-cashflow", "approval-sync"];
const isSyncActive = (status?: string) => status === "queued" || status === "running";

/** 同步审批单：点一下建一次任务；跑的时候每 3 秒看一次状态。 */
export function useApprovalSync(enabled: boolean) {
  const client = useQueryClient();
  const state = useQuery({
    queryKey: SYNC_KEY,
    enabled,
    retry: false,
    refetchInterval: (query) => (isSyncActive(query.state.data?.status) ? 3000 : false),
    queryFn: async () => (await backendRequest<ApprovalSyncState>(`${BASE}/approvals/sync`)).data,
  });
  const start = useMutation({
    mutationFn: async () => (await backendRequest<ApprovalSyncState>(`${BASE}/approvals/sync`, { method: "POST" })).data,
    onSuccess: (data) => client.setQueryData(SYNC_KEY, data),
  });
  return { state: state.data, running: start.isPending || isSyncActive(state.data?.status), start: start.mutateAsync };
}

/** 同步失败的原因：飞书错误码原样带上，方便查。 */
export function syncErrorText(error: unknown): string {
  if (error instanceof BackendRequestError && error.status === 409) return "审批单同步任务还没配置，请联系管理员";
  if (error instanceof BackendRequestError && error.status === 503) return "任务队列暂时不可用，请稍后再试";
  return cashErrorText(error);
}
export const syncFailedText = (code: string | null) => `同步失败${code ? `（${code}）` : ""}，已同步的单子不受影响，可以再点一次`;

export async function postLineEvent(line: LiveCashLine, kind: LineEventKind, fields: { payload?: Record<string, unknown>; reason?: string } = {}) {
  const { data } = await backendRequest<{ stage: string; version: number; auto_reset: boolean }>(`${BASE}/lines/${line.uid}/events`, {
    method: "POST",
    body: JSON.stringify({ kind, payload: fields.payload ?? {}, reason: fields.reason, expected_version: line.version, idempotency_key: crypto.randomUUID() }),
  });
  return data;
}

export async function uploadStatement(file: File, importId: string): Promise<ApiFileResult> {
  const { data } = await backendRequest<{ import_id: string; file: ApiFileResult }>(`${BASE}/imports`, {
    method: "POST",
    body: file,
    headers: { "Content-Type": "application/octet-stream", "X-File-Name": encodeURIComponent(file.name), "X-Import-Id": importId },
  });
  return data.file;
}

/** 后端错误不带详情，这里按状态码给财务能看懂的话。 */
export function cashErrorText(error: unknown): string {
  if (!(error instanceof BackendRequestError)) return "操作失败，请稍后重试";
  if (error.status === 401) return "登录已过期，请重新登录";
  if (error.status === 403) return "只有超级管理员能操作";
  if (error.status === 404) return "这笔流水不存在，可能所在批次已作废";
  if (error.status === 409) return "这笔的状态已经变了，页面已刷新，请看过后再操作";
  if (error.status === 413) return "文件超过 20MB";
  if (error.status === 422) return "填写的内容不符合要求，请检查后再提交";
  if (error.status === 503) return "服务器还没配好文件存放目录，请联系管理员";
  return "操作失败，请稍后重试";
}

/** 下一个交表节点：每周二 15:00。 */
export function nextImportNode(now: Date): string {
  const next = new Date(now);
  next.setHours(15, 0, 0, 0);
  const days = (2 - now.getDay() + 7) % 7;
  next.setDate(now.getDate() + (days === 0 && now > next ? 7 : days));
  const pad = (value: number) => String(value).padStart(2, "0");
  return `${next.getFullYear()}-${pad(next.getMonth() + 1)}-${pad(next.getDate())} 15:00`;
}
