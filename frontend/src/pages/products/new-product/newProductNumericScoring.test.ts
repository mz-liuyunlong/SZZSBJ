import { describe, expect, it } from "vitest";
import { samples } from "./nativeData";
import { initialNumericRules, metricValue, numericMetricScore, previewDimension,
  previewNumericScore, validateNumericRules } from "./newProductNumericScoring";

describe("PR337 numeric score preview",()=>{
  it("uses deterministic interpolation on configured anchors",()=>{
    expect(numericMetricScore(1.5,initialNumericRules.roi)).toBe(8);
    expect(numericMetricScore(1.8,initialNumericRules.roi)).toBe(10);
    expect(numericMetricScore(.8,initialNumericRules.roi)).toBe(4);
    expect(numericMetricScore(15,initialNumericRules.acos)).toBe(10);
    expect(numericMetricScore(100,initialNumericRules.acos)).toBe(0);
  });
  it("rejects overlapping or reversed thresholds",()=>{
    expect(validateNumericRules(initialNumericRules)).toBeNull();
    expect(validateNumericRules({...initialNumericRules,acos:{direction:"lower",values:[10,20,20,30,40,50]}})).toMatch(/严格递增/);
  });
  it("never fabricates unobserved metrics",()=>{
    const p=samples[0];
    expect(metricValue(p,"singleOrderRatio")).toBeNull();
    const trust=previewDimension(p,initialNumericRules,"trust");
    expect(trust.score).toBeNull();
    expect(trust.complete).toBe(false);
    const profit=previewDimension(p,initialNumericRules,"profit");
    expect(profit.complete).toBe(true);
    expect(profit.score).not.toBeNull();
    expect(previewNumericScore(p,initialNumericRules).complete).toBe(false);
  });
});
