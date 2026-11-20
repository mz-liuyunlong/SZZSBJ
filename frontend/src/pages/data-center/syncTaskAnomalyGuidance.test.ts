import { describe, expect, it } from "vitest";
import { describeSyncAnomaly } from "@/pages/data-center/syncTaskAnomalyGuidance";

describe("describeSyncAnomaly", () => {
  it("explains the exact known sample/SaleStat mismatch without asserting a data correction", () => {
    const value = describeSyncAnomaly({
      error_code: "DATA_PAGES_CONFIRMED_SAMPLE_EXCEEDS_SALESTAT",
      details: {
        sku_day_sample_qty: "4.0000",
        sku_day_salestat_qty: "2.0000",
        sku_day_sample_reference_amount: "51.96000000",
        sku_day_salestat_sales: "25.9800",
      },
    });
    expect(value.title).toContain("送样");
    expect(value.category).toBe("sample");
    expect(value.comparison).toContain("送样 4 件");
    expect(value.comparison).toContain("SaleStat 2 件");
    expect(value.comparison).toContain("差 2 件");
    expect(value.comparison).toContain("$51.96");
    expect(value.safeNextStep).toContain("不能靠改状态");
    expect(value.requiredEvidence.length).toBeGreaterThan(0);
  });

  it("does not invent sample metrics for a date-scope summary anomaly", () => {
    const value = describeSyncAnomaly({
      error_code: "DATA_PAGES_CONFIRMED_SAMPLE_EXCEEDS_SALESTAT",
      details: {
        phase: "financial_validation",
        financial_status: "pending",
      },
    });
    expect(value.comparison).toBeUndefined();
    expect(value.requiredEvidence).toContain("SaleStat 对应日期、店铺、商品的数量和金额凭据");
  });

  it.each([
    ["FINANCE_SEM_CAMPAIGN_SPEND_UNALLOCATED", "SEM"],
    ["DATA_PAGES_SEM_SPEND_UNATTRIBUTED", "SEM"],
    ["FINANCE_SP_SPEND_UNALLOCATED", "SP"],
  ])("explains advertising exception %s as %s without guessing a product", code => {
    const value = describeSyncAnomaly({ error_code: code });
    expect(value.title).toContain("广告");
    expect(value.category).toBe("advertising");
    expect(value.requiredEvidence.length).toBeGreaterThan(0);
    expect(value.safeNextStep).not.toContain("自动完成");
  });

  it("preserves unknown codes as non-actionable review cases", () => {
    const value = describeSyncAnomaly({ error_code: "UNKNOWN_FUTURE_CODE" });
    expect(value.category).toBe("other");
    expect(value.safeNextStep).toContain("待核对");
  });

  it("never shows inaccurate comparisons for absent, negative, or malformed metrics", () => {
    const value = describeSyncAnomaly({
      error_code: "DATA_PAGES_CONFIRMED_SAMPLE_EXCEEDS_SALESTAT",
      details: {
        sku_day_sample_qty: "-3",
        sku_day_salestat_qty: "bogus",
        sku_day_sample_reference_amount: "",
        sku_day_salestat_sales: null,
      },
    });
    expect(value.comparison).toBeUndefined();
  });
});
