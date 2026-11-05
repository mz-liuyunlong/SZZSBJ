/** 手工录入的账户规则，单独放一个文件方便测试。先选人民币或美元，再选这个币种的账户（Rocky 2026-11-05）。 */
import { isRmb } from "@/pages/finance/currencyName";

export type ManualCurrency = "CNY" | "USD";
export const DEFAULT_MANUAL_CURRENCY: ManualCurrency = "CNY";
export const MANUAL_CURRENCIES: { value: ManualCurrency; label: string }[] = [
  { value: "CNY", label: "人民币" },
  { value: "USD", label: "美元" },
];
const CASH_ACCOUNT_NAME = "现金";

interface AccountRow { account_key: string; currency_code: string; display_name: string; provider: string }

/** 现金账户按名字认，只有人民币的算。 */
export const isCashAccount = (row: AccountRow) => row.display_name === CASH_ACCOUNT_NAME && row.currency_code === "CNY";

/** 这个币种能录的账户，现金排最前。人民币含 CNH。手工账户只收人民币，所以美元不列手工账户。 */
export const manualAccounts = <T extends AccountRow>(rows: T[], currency: ManualCurrency): T[] =>
  rows
    .filter((row) => (currency === "CNY" ? isRmb(row.currency_code) : row.currency_code === currency && row.provider !== "manual"))
    .sort((left, right) => Number(isCashAccount(right)) - Number(isCashAccount(left)));

export const defaultAccountKey = (rows: AccountRow[]): string | undefined => rows.find(isCashAccount)?.account_key;

/** 下拉里只写账户名和币种（尾号有就带上），不写平台。 */
export const accountLabel = (name: string, currency: string, last4: string): string =>
  [name, currency, last4 ? `尾号 ${last4}` : ""].filter(Boolean).join(" · ");
