import { describe, expect, it } from "vitest";
import { currencyName, currencyText, isRmb } from "@/pages/finance/currencyName";

describe("currencyName", () => {
  it("writes every renminbi code as 人民币 and USD as 美元", () => {
    expect(["CNY", "CNH", "RMB"].map(currencyName)).toEqual(["人民币", "人民币", "人民币"]);
    expect(currencyName("USD")).toBe("美元");
    expect(currencyName("EUR")).toBe("EUR");
    expect(currencyName(null)).toBe("");
  });

  it("knows which codes are renminbi", () => {
    expect(["CNY", "CNH", "RMB"].every(isRmb)).toBe(true);
    expect(isRmb("USD")).toBe(false);
    expect(isRmb(undefined)).toBe(false);
  });
});

describe("currencyText", () => {
  it("replaces standalone codes in names and messages only", () => {
    expect(currencyText("中行 · USD")).toBe("中行 · 美元");
    expect(currencyText("专用户 CNH")).toBe("专用户 人民币");
    expect(currencyText("扣款 USD 100.00，到账 100.00 CNY")).toBe("扣款 美元 100.00，到账 100.00 人民币");
    expect(currencyText("CNYX USDT 交易号 AUSD1")).toBe("CNYX USDT 交易号 AUSD1");
  });
});
