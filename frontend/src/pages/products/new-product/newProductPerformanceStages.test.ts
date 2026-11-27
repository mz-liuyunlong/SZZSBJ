import { describe, expect, it } from "vitest";
import type { Product } from "./newProductModel";
import { allPerformanceStatuses, performanceFlowStatus, performanceStageStatuses, performanceStatusParam } from "./newProductPerformanceStages";

describe("new product five-card stages", () => {
  it("keeps all detailed options unique and limits them by card", () => {
    expect(allPerformanceStatuses.length).toBe(13);
    expect(new Set(allPerformanceStatuses).size).toBe(13);
    expect(performanceStageStatuses("pending")).toEqual(["待市场评分", "待等级确认", "待测评确认"]);
    expect(performanceStageStatuses("all")).toEqual(allPerformanceStatuses);
    expect(performanceStatusParam("all", [])).toBe("");
    expect(performanceStatusParam("passed", ["采购已驳回"])).toBe("flow:采购已驳回");
    expect(performanceStatusParam("failed", ["测评未通过"])).toBe("flow:测评未通过");
    expect(performanceStatusParam("passed", ["复核审批中"])).toBe("__none__");
    expect(performanceStatusParam("evaluating", [])).toBe("flow:测评中");
    expect(performanceStageStatuses("evaluating")).toEqual(["测评中"]);
    expect(performanceStatusParam("evaluating", ["待到货"])).toBe("__none__");
    expect(performanceStatusParam("all", ["待到货"])).toBe("flow:待到货");
  });
  it("keeps unarrived goods only in the all card and preserves final conclusions", () => {
    const row = (status: string, extra: Record<string, unknown> = {}) => ({status, ...extra} as Product);
    expect(performanceFlowStatus(row("测评中", {launch:"2026-11-01",backend:{firstWfsDate:null}}))).toBe("待到货");
    expect(performanceFlowStatus(row("测评中", {backend:{firstWfsDate:"2026-11-02"},inventory:0}))).toBe("测评中");
    expect(performanceFlowStatus(row("测评通过", {backend:{firstWfsDate:null}}))).toBe("待申请采购");
  });
  it("projects approval and review states without mutating the assessment conclusion", () => {
    const row = (status: string, extra: Record<string, unknown> = {}) => ({status, ...extra} as Product);
    expect(performanceFlowStatus(row("测评通过"))).toBe("待申请采购");
    for (const [state, expected] of [["submitted", "采购审批中"], ["approved", "采购已批准"], ["rejected", "采购已驳回"]]) {
      expect(performanceFlowStatus(row("测评通过", {backend:{purchaseStatus:state}}))).toBe(expected);
    }
    expect(performanceFlowStatus(row("测评未通过", {evaluationReviewStatus:"submitted"}))).toBe("复核审批中");
    expect(performanceFlowStatus(row("测评未通过", {evaluationReviewStatus:"approved",evaluationRecheckRequired:true}))).toBe("待重新核算");
    expect(performanceFlowStatus(row("测评未通过", {evaluationReviewStatus:"rejected"}))).toBe("复核已驳回");
    expect(performanceFlowStatus(row("待等级确认", {backend:{purchaseStatus:"rejected"}}))).toBe("待等级确认");
  });
});
