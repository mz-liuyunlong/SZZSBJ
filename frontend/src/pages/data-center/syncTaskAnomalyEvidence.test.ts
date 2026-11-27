import { describe, expect, it } from "vitest";
import { evidenceChanges, sampleFinancialStatus, sampleReviewBlocked, sampleAnomalyGuide } from "./syncTaskAnomalyEvidence";

describe("verified sample anomaly evidence", () => {
  it("shows cancellation and the original/new evidence without guessing", () => {
    expect(evidenceChanges({ changes: [
      { field: "cancel_time_raw", previous: "0", observed: "1795639001" },
      { field: "is_cancelled", previous: false, observed: true },
      { field: "item_id", previous: "item-a", observed: null },
      { field: "unknown", previous: "ignored" },
      null,
    ] })).toEqual([
      { field: "取消时间（来源原值）", previous: "0", observed: "1795639001" },
      { field: "是否取消", previous: "否", observed: "是" },
      { field: "Item ID", previous: "item-a", observed: "未提供" },
    ]);
    expect(sampleAnomalyGuide.DATA_PAGES_SAMPLE_CANCELLATION_APPLIED).toContain("无需人工处理");
  });

  it("prevents manual closing until the source and financial evidence are validated", () => {
    expect(sampleReviewBlocked({ sample_isolation_active: true, financial_status: "partial" })).toBe(true);
    expect(sampleReviewBlocked({ sample_isolation_active: false, financial_status: "pending" })).toBe(true);
    expect(sampleReviewBlocked({ sample_isolation_active: false, financial_status: "ready" })).toBe(false);
    expect(sampleReviewBlocked({ financial_status: "pending" })).toBe(false);
    expect(sampleFinancialStatus({ sample_isolation_active: true })).toBe("争议商品利润待核实");
    expect(sampleFinancialStatus({ financial_status: "ready" })).toBe("已复验");
  });
});
