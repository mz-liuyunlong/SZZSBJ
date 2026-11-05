import { describe, expect, it } from "vitest";
import { defaultAccountKey, isCashAccount, manualAccounts } from "@/pages/finance/cash-flow/manualEntryOptions";

const bank = { account_key: "B", currency_code: "CNY", display_name: "银行" };
const usd = { account_key: "U", currency_code: "USD", display_name: "美元户" };
const cnh = { account_key: "H", currency_code: "CNH", display_name: "专用户" };
const cash = { account_key: "C", currency_code: "CNY", display_name: "现金" };
const cashUsd = { account_key: "M", currency_code: "USD", display_name: "现金" };
const other = { account_key: "O", currency_code: "CNY", display_name: "备用金" };

describe("manual entry accounts", () => {
  it("finds cash by its name, in RMB only, and defaults to it", () => {
    expect(isCashAccount(cash)).toBe(true);
    expect(isCashAccount(cashUsd)).toBe(false);
    expect(isCashAccount(other)).toBe(false);
    expect(defaultAccountKey([bank, cashUsd, other, cash])).toBe("C");
    expect(defaultAccountKey([bank, usd])).toBeUndefined();
  });

  it("lists only CNY accounts with cash first and leaves the input alone", () => {
    const rows = [bank, usd, cnh, other, cash, cashUsd];
    expect(manualAccounts(rows).map((row) => row.account_key)).toEqual(["C", "B", "O"]);
    expect(rows[0]).toBe(bank);
  });
});
