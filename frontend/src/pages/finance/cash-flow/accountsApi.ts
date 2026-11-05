/**
 * 账户管理、手工录入的接口（/api/finance/cashflow/accounts、/manual-lines）。
 * 识别值（完整账号、用户号）只往后端写，后端不回传，页面只显示尾号和「已填」。
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { backendRequest, BackendRequestError } from "@/api/backendApi";
import { cashErrorText } from "@/pages/finance/cash-flow/journalApi";

const BASE = "/api/finance/cashflow";
const ADMIN_KEY = ["finance-cashflow", "accounts-admin"];
const JOURNAL_KEY = ["finance-cashflow", "journal"];

export type CashProvider = "manual" | "boc" | "shenzhen_rural_bank" | "cmb" | "payoneer" | "worldfirst" | "pingpong";

export const PROVIDER_LABEL: Record<CashProvider, string> = {
  manual: "手工录入（不导入，如现金）",
  boc: "中国银行（交易明细 xls）",
  cmb: "招商银行个人（交易流水 PDF）",
  shenzhen_rural_bank: "深圳农商 / 银座（交易明细）",
  payoneer: "派安盈（CSV）",
  worldfirst: "万里汇（xlsx）",
  pingpong: "PingPong（账单明细）",
};
export const PROVIDER_SHORT: Record<string, string> = {
  manual: "手工", boc: "中行", cmb: "招行个人", shenzhen_rural_bank: "银座", payoneer: "派安盈", worldfirst: "万里汇", pingpong: "PingPong",
};
export const CURRENCY_OPTIONS = ["CNY", "USD", "CNH"];
export const KIND_OPTIONS = ["对公", "对私", "平台", "现金"];

export interface AdminAccount {
  account_key: string; display_name: string; entity: string; currency_code: string; kind: string; provider: string;
  account_no_last4: string; is_active: boolean; sort_order: number; identity_fields: string[];
  pingpong_main: boolean | null; payoneer_feature: string | null; line_count: number;
}
export type Identity = Record<string, string | boolean>;
export interface AccountInput {
  display_name: string; entity: string; currency_code: string; kind: string; provider: CashProvider; account_no_last4?: string; identity?: Identity; sort_order?: number;
}
export type AccountPatch = Partial<AccountInput> & { is_active?: boolean };

export interface ManualLineInput {
  account_key: string; business_date: string; direction: "in" | "out"; amount: string; description: string;
  counterparty_name?: string; memo?: string; category_code?: string | null; idempotency_key: string;
}

/** 每个平台导入时靠什么认出账户；空数组 = 不用填。 */
export function identityMissing(provider: CashProvider, identity: Identity): string | null {
  const digits = (value: unknown) => String(value ?? "").replace(/\D/g, "");
  if (provider === "boc" && digits(identity.inquiry_account).length < 6) return "中行要填查询账号（交易明细表头里的那个）";
  if ((provider === "cmb" || provider === "shenzhen_rural_bank") && digits(identity.account_no).length < 8) return "要填完整银行账号";
  if (provider === "payoneer" && !identity.feature) return "派安盈要选是卖家收款户还是归集户";
  if (provider === "pingpong" && !digits(identity.user_no)) return "PingPong 要填用户编号";
  if (provider === "pingpong" && !identity.main && !String(identity.account_id ?? "").trim()) return "PingPong 店铺子账户要填子账户 ID";
  return null;
}

export function useAdminAccounts(enabled = true) {
  return useQuery({ queryKey: ADMIN_KEY, enabled, retry: false, queryFn: async () => (await backendRequest<AdminAccount[]>(`${BASE}/accounts/admin`)).data });
}

export function useSaveAccount() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: async ({ key, body }: { key?: string; body: AccountInput | AccountPatch }) =>
      (await backendRequest<AdminAccount>(key ? `${BASE}/accounts/${encodeURIComponent(key)}` : `${BASE}/accounts`, { method: key ? "PATCH" : "POST", body: JSON.stringify(body) })).data,
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ADMIN_KEY });
      void client.invalidateQueries({ queryKey: JOURNAL_KEY });
    },
  });
}

export function useCreateManualLine() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: async (body: ManualLineInput) => (await backendRequest<{ line_uid: string; replayed: boolean }>(`${BASE}/manual-lines`, { method: "POST", body: JSON.stringify(body) })).data,
    onSuccess: () => void client.invalidateQueries({ queryKey: JOURNAL_KEY }),
  });
}

/** 后端不回传详细原因，这里按错误码给能看懂的话。 */
export function accountErrorText(error: unknown): string {
  if (error instanceof BackendRequestError && error.code === "CASHFLOW_ACCOUNT_REJECTED") {
    return error.status === 409 ? "已经有启用中的账户用同样的账号，或者这个账户已有流水，不能改平台和币种" : "填写不完整：检查名称、币种和识别号";
  }
  if (error instanceof BackendRequestError && error.code === "CASHFLOW_ACCOUNT_NOT_FOUND") return "账户不存在，请刷新";
  return cashErrorText(error);
}

export function manualErrorText(error: unknown): string {
  if (error instanceof BackendRequestError && error.code === "CASHFLOW_MANUAL_LINE_REJECTED") return "没录进去：检查账户是否停用、日期不能晚于今天、类别是否存在";
  if (error instanceof BackendRequestError && error.code === "CASHFLOW_ACCOUNT_NOT_FOUND") return "账户不存在，请刷新";
  return cashErrorText(error);
}
