import { describe, expect, it } from "vitest";
import { defaultAccountKey, isCashAccount, manualAccounts } from "@/pages/finance/cash-flow/manualEntryOptions";

const bank = { account_key: "B", currency_code: "CNY", display_name: "银行", provider: "boc" };
const usd = { account_key: "U", currency_code: "USD", display_name: "美元户", provider: "boc" };
const cnh = { account_key: "H", currency_code: "CNH", display_name: "专用户", provider: "pingpong" };
const cash = { account_key: "C", currency_code: "CNY", display_name: "现金", provider: "manual" };
const cashUsd = { account_key: "M", currency_code: "USD", display_name: "现金", provider: "manual" };

describe("manual entry accounts", () => {
  it("finds cash by its name, in RMB only, and defaults to it", () => {
    expect(isCashAccount(cash)).toBe(true);
    expect(isCashAccount(cashUsd)).toBe(false);
    expect(isCashAccount(bank)).toBe(false);
    expect(defaultAccountKey([bank, cashUsd, cash])).toBe("C");
    expect(defaultAccountKey([bank, usd])).toBeUndefined();
  });

  it("lists every account including USD, cash first, without non-RMB manual accounts", () => {
    const rows = [bank, usd, cnh, cash, cashUsd];
    expect(manualAccounts(rows).map((row) => row.account_key)).toEqual(["C", "B", "U", "H"]);
    expect(rows[0]).toBe(bank);
  });
});
