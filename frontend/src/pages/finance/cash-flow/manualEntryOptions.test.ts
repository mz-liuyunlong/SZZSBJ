import { describe, expect, it } from "vitest";
import { accountLabel, defaultAccountKey, isCashAccount, MANUAL_CURRENCIES, manualAccounts, manualCategoryOptions } from "@/pages/finance/cash-flow/manualEntryOptions";

const bank = { account_key: "B", currency_code: "CNY", display_name: "银行", provider: "boc" };
const usd = { account_key: "U", currency_code: "USD", display_name: "美元户", provider: "boc" };
const cnh = { account_key: "H", currency_code: "CNH", display_name: "专用户", provider: "pingpong" };
const cash = { account_key: "C", currency_code: "CNY", display_name: "现金", provider: "manual" };
const cashUsd = { account_key: "M", currency_code: "USD", display_name: "现金", provider: "manual" };
const cashCnh = { account_key: "N", currency_code: "CNH", display_name: "手工离岸", provider: "manual" };
const rows = [bank, usd, cnh, cash, cashUsd, cashCnh];

describe("manual entry categories", () => {
  it("leaves out X01 and keeps the others", () => {
    const cats = [{ code: "F01", big: "财务费用", name: "手续费" }, { code: "X01", big: "剔除", name: "非本公司" }];
    expect(manualCategoryOptions(cats)).toEqual([{ value: "F01", label: "F01 财务费用·手续费" }]);
  });
});

describe("manual entry accounts", () => {
  it("offers 人民币 first, then 美元", () => {
    expect(MANUAL_CURRENCIES.map((item) => item.label)).toEqual(["人民币", "美元"]);
  });

  it("finds cash by its name, in RMB only, and defaults to it", () => {
    expect(isCashAccount(cash)).toBe(true);
    expect(isCashAccount(cashUsd)).toBe(false);
    expect(isCashAccount(bank)).toBe(false);
    expect(defaultAccountKey(manualAccounts(rows, "CNY"))).toBe("C");
    expect(defaultAccountKey(manualAccounts(rows, "USD"))).toBeUndefined();
  });

  it("lists renminbi accounts with cash first, including CNH", () => {
    expect(manualAccounts(rows, "CNY").map((row) => row.account_key)).toEqual(["C", "B", "H"]);
    expect(rows[0]).toBe(bank);
  });

  it("lists only USD accounts for USD, without manual ones", () => {
    expect(manualAccounts(rows, "USD").map((row) => row.account_key)).toEqual(["U"]);
  });

  it("labels an account without its platform", () => {
    expect(accountLabel("派安盈 · 主账号", "美元", "")).toBe("派安盈 · 主账号 · 美元");
    expect(accountLabel("银行", "人民币", "0000")).toBe("银行 · 人民币 · 尾号 0000");
  });
});
