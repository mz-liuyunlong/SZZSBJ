/** 手工录入的账户规则，单独放一个文件方便测试。手工录入只记人民币（Rocky 2026-11-05）。 */
const MANUAL_CURRENCY = "CNY";
const CASH_ACCOUNT_NAME = "现金";

interface AccountRow { account_key: string; currency_code: string; display_name: string }

/** 现金账户按名字认。 */
export const isCashAccount = (row: AccountRow) => row.display_name === CASH_ACCOUNT_NAME && row.currency_code === MANUAL_CURRENCY;

/** 只列人民币账户，现金排最前，其余顺序不变。 */
export const manualAccounts = <T extends AccountRow>(rows: T[]): T[] =>
  rows
    .filter((row) => row.currency_code === MANUAL_CURRENCY)
    .sort((left, right) => Number(isCashAccount(right)) - Number(isCashAccount(left)));

export const defaultAccountKey = (rows: AccountRow[]): string | undefined => rows.find(isCashAccount)?.account_key;
