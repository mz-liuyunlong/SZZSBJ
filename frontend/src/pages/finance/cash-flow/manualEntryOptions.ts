/** 手工录入的账户规则，单独放一个文件方便测试。只有现金账户固定人民币，其他账户按自己的币种记（Rocky 2026-11-05）。 */
const CASH_CURRENCY = "CNY";
const CASH_ACCOUNT_NAME = "现金";

interface AccountRow { account_key: string; currency_code: string; display_name: string; provider: string }

/** 现金账户按名字认。 */
export const isCashAccount = (row: AccountRow) => row.display_name === CASH_ACCOUNT_NAME && row.currency_code === CASH_CURRENCY;

/** 列出全部账户，现金排最前；手工账户只收人民币，别的币种的手工账户不列。 */
export const manualAccounts = <T extends AccountRow>(rows: T[]): T[] =>
  rows
    .filter((row) => row.provider !== "manual" || row.currency_code === CASH_CURRENCY)
    .sort((left, right) => Number(isCashAccount(right)) - Number(isCashAccount(left)));

export const defaultAccountKey = (rows: AccountRow[]): string | undefined => rows.find(isCashAccount)?.account_key;
