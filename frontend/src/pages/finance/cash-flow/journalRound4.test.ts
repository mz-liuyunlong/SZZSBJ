import { describe, expect, it, vi } from "vitest";
import { toCashLine, type ApiLine } from "@/pages/finance/cash-flow/journalApi";
import { hasCard, luhnOk, maskCards } from "@/pages/finance/cash-flow/cardMask";
import { amountDiff, compareAmount, compareRows, type ApprovalView } from "@/pages/finance/cash-flow/journalShared";
import { partApprovalGroups, partGroupCompareLine, wholeCompareLine } from "@/pages/finance/cash-flow/journalParts";

vi.mock("@/api/backendApi", async (importOriginal) => ({ ...(await importOriginal<typeof import("@/api/backendApi")>()), backendRequest: vi.fn() }));

const api = (over: Partial<ApiLine> = {}): ApiLine => ({
  line_uid: "0123456789abcdef", account_key: "P", business_date: "2026-10-30", month: "2026-10", time: null, currency_code: "USD",
  amount: "-14.5900", amount_cny: "-104.0000", balance_after: null, description: "", memo: "", counterparty_name: "", counterparty_account_last4: "",
  source_ref: "", file_row_order: 1, category_code: "S03", category_source: "人工", pair_id: null, flags: [], refs: ["209901010001"],
  exclude_amount: null, exclude_reason: null, list_excluded_cny: "0", stage: "todo", stage_reason: null, review_note: null, version: 0, ...over,
});
const view = (amount: number, cur: string) => ({ serial: "209901010001", amount, cur } as ApprovalView);

describe("RMB approval against a foreign-currency line (Rocky 11-12)", () => {
  it("manual CNY equal to the approval → no difference, no note needed", () => {
    const line = wholeCompareLine(toCashLine(api({ amount_cny: "-96.9400", fx_source: "manual", fx_rate: "6.6443" })));
    expect(compareAmount(line, [view(96.94, "CNY")])).toMatchObject({ amt: 96.94, cur: "CNY", converted: true, exact: true });
    expect(amountDiff(line, [view(96.94, "CNY")])).toBe(0);
    const [amount] = compareRows(line, [view(96.94, "CNY")]);
    expect(amount).toMatchObject({ ok: true, result: "一致" });
    expect(amount.line).toContain("14.59");
    expect(amount.line).toContain("96.94");
  });

  it("system-rate CNY is compared in RMB and says to set the agreed rate", () => {
    const line = toCashLine(api({ fx_source: "lingxing", fx_rate: "7.1280" }));
    expect(amountDiff(line, [view(96.94, "CNY")])).toBe(-7.06);
    const [amount] = compareRows(line, [view(96.94, "CNY")]);
    expect(amount.ok).toBe(false);
    expect(amount.result).toContain("按系统汇率");
    expect(amount.result).toContain("改折人民币");
  });

  it("no CNY on the foreign line → cannot compare instead of a wrong difference", () => {
    const line = toCashLine(api({ amount_cny: null }));
    expect(amountDiff(line, [view(96.94, "CNY")])).toBeNull();
    expect(compareRows(line, [view(96.94, "CNY")])[0]).toMatchObject({ ok: null, result: "币种不同、流水还没折人民币，看凭证" });
  });

  it("same currency still compares the original amount; CNH counts as RMB", () => {
    expect(amountDiff(toCashLine(api()), [view(14.59, "USD")])).toBe(0);
    const cnh = toCashLine(api({ currency_code: "CNH", amount: "-100.0000", amount_cny: "-100.0000" }));
    expect(amountDiff(cnh, [view(100, "CNY")])).toBe(0);
  });
});

describe("split foreign lines keep the rate source (刘云龙 #341 P2)", () => {
  const split = (source: string) => toCashLine(api({
    amount: "-100.0000", amount_cny: "-712.8000", fx_source: source, fx_rate: "7.1280", refs: ["209901010002"],
    parts: [{ amount: "60.0000", category_code: null, refs: ["209901010001"] }, { amount: "40.0000", category_code: null }],
  }));

  it("the rest after split parts, converted by the system rate, is still flagged as an estimate", () => {
    const whole = wholeCompareLine(split("lingxing"));
    expect(whole).toMatchObject({ amt: -285.12, cur: "CNY", cnyFrom: { cur: "USD", amt: -40 } });
    expect(compareAmount(whole, [view(300, "CNY")])).toMatchObject({ converted: true, exact: false, original: { cur: "USD", amt: -40 } });
    const [amount] = compareRows(whole, [view(300, "CNY")]);
    expect(amount.result).toContain("按系统汇率");
    expect(amount.line).toContain("40.00");
    expect(amount.line).toContain("285.12");
  });

  it("Payoneer or manual CNY on a split line is exact", () => {
    const whole = wholeCompareLine(split("payoneer"));
    expect(compareAmount(whole, [view(300, "CNY")])).toMatchObject({ converted: true, exact: true });
    expect(compareRows(whole, [view(300, "CNY")])[0].result).toBe("差额 ¥14.88");
  });

  it("a split row compared with a USD approval uses the original USD amount", () => {
    const line = split("lingxing");
    const group = partGroupCompareLine(line, partApprovalGroups(line)[0]);
    expect(amountDiff(group, [view(60, "USD")])).toBe(0);
    expect(compareAmount(group, [view(400, "CNY")])).toMatchObject({ converted: true, exact: false });
  });
});

describe("CNH split lines stay same-currency (刘云龙 #341 round 3)", () => {
  it("100 CNH split 60 (A) + 40 (B), B = 50 CNY → plain difference of 10, no system-rate hint", () => {
    const line = toCashLine(api({
      currency_code: "CNH", amount: "-100.0000", amount_cny: "-100.0000", fx_source: "", refs: ["209901010002"],
      parts: [{ amount: "60.0000", category_code: null, refs: ["209901010001"] }, { amount: "40.0000", category_code: null }],
    }));
    const whole = wholeCompareLine(line);
    expect(whole).toMatchObject({ amt: -40, cur: "CNH" });
    expect(whole.cnyFrom).toBeUndefined();
    expect(compareAmount(whole, [view(50, "CNY")])).toMatchObject({ amt: 40, converted: false, exact: true });
    expect(amountDiff(whole, [view(50, "CNY")])).toBe(10);
    const [amount] = compareRows(whole, [view(50, "CNY")]);
    expect(amount.result).toBe("差额 ¥10.00");
    expect(amount.result).not.toContain("系统汇率");
    const group = partGroupCompareLine(line, partApprovalGroups(line)[0]);
    expect(group).toMatchObject({ amt: -60, cur: "CNH" });
    expect(amountDiff(group, [view(60, "CNY")])).toBe(0);
  });
});

describe("card numbers in approval text (Rocky 11-12)", () => {
  const card = "4111 1111 1111 1111";
  it("keeps only the last 4 digits and the spacing", () => {
    expect(maskCards(`卡号：${card}，待还款`)).toBe("卡号：**** **** **** 1111，待还款");
    expect(maskCards("4111-1111-1111-1111")).toBe("****-****-****-1111");
    expect(hasCard(card)).toBe(true);
  });

  it("keeps amounts and dates next to the card visible and the card hidden (刘云龙 #341 P1)", () => {
    expect(maskCards(`银行卡号 ${card} 10元`)).toBe("银行卡号 **** **** **** 1111 10元");
    expect(maskCards(`10 ${card}`)).toBe("10 **** **** **** 1111");
    expect(maskCards(`2026-10-30 ${card} 金额 10 20`)).toBe("2026-10-30 **** **** **** 1111 金额 10 20");
    expect(maskCards("4111111111111111 10")).toBe("************1111 10");
  });

  it("after 卡号 / 银行卡 / 账号 a card is hidden even without a Luhn check digit", () => {
    expect(maskCards("卡号 1234 5678 9012 3456 10")).toBe("卡号 **** **** **** 3456 10");
    expect(maskCards("1234 5678 9012 3456 10")).toBe("1234 5678 9012 3456 10");
  });

  it("other separators and full-width digits are recognised, separators kept as written (刘云龙 #341 补)", () => {
    expect(maskCards("4111  1111  1111  1111")).toBe("****  ****  ****  1111");
    expect(maskCards("4111 - 1111 - 1111 - 1111")).toBe("**** - **** - **** - 1111");
    expect(maskCards("4111\u30001111\u30001111\u30001111")).toBe("****\u3000****\u3000****\u30001111");
    expect(maskCards("4111.1111.1111.1111")).toBe("****.****.****.1111");
    expect(maskCards("4111/1111/1111/1111")).toBe("****/****/****/1111");
    expect(maskCards("\uFF14" + "\uFF11".repeat(15))).toBe("*".repeat(12) + "\uFF11".repeat(4));   // 全角的 4111111111111111
    expect(maskCards("卡号是：1234 5678 9012 3456")).toBe("卡号是：**** **** **** 3456");
    expect(maskCards("账号为 1234567890123456")).toBe("账号为 ************3456");
  });

  it("dates and amounts written with dots or slashes are left alone", () => {
    expect(maskCards("2026.10.30")).toBe("2026.10.30");
    expect(maskCards("1.5")).toBe("1.5");
    expect(maskCards("10/20")).toBe("10/20");
    expect(maskCards("金额 96.94 4111 1111 1111 1111")).toBe("金额 96.94 **** **** **** 1111");
  });

  it("amount lists and date ranges are never masked without a card hint (刘云龙 #341 审核)", () => {
    for (const text of [
      "明细：37446.72 / 24135.68 / 21333.90",
      "明细：41864.61/83796.35/75895.44/68539.15/53771.59/49154.43",
      "15267.92 54637.69 18607.47 2574.71",
      "2026.10.1-2026.10.15 报销 1234.56元",
      "622202 1234567894",
    ]) expect(maskCards(text)).toBe(text);
    expect(maskCards("卡号 622202 1234567894")).toBe("卡号 ****** ******7894");
  });

  it("with a card hint, any 13–19 digit grouping is masked even without a check digit (刘云龙 #341 round 3)", () => {
    expect(maskCards("卡号 622202 1234567895")).toBe("卡号 ****** ******7895");
    expect(maskCards("账号：123 4567 890123")).toBe("账号：*** **** **0123");
    expect(maskCards("银行卡 6222021234567895 10元")).toBe("银行卡 ************7895 10元");
    expect(maskCards("卡号 2026.10.30 1234.56")).toBe("卡号 2026.10.30 1234.56");
    expect(maskCards("账号 2026-10-01 至 2026-10-15 金额 96.94")).toBe("账号 2026-10-01 至 2026-10-15 金额 96.94");
  });

  it("leaves 12-digit approval serials, short numbers and non-Luhn strings alone", () => {
    expect(maskCards("单号 202610270001 金额 96.94")).toBe("单号 202610270001 金额 96.94");
    expect(luhnOk("4111111111111112")).toBe(false);
    expect(maskCards("4111 1111 1111 1112")).toBe("4111 1111 1111 1112");
    expect(hasCard("订单号 123456")).toBe(false);
  });
});
