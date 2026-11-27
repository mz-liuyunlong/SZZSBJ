import type { Product } from "./newProductModel";

export const performanceStages: Record<string, readonly string[]> = {
  evaluating: ["测评中"],
  pending: ["待市场评分", "待等级确认", "待测评确认"],
  passed: ["待申请采购", "采购审批中", "采购已批准", "采购已驳回"],
  failed: ["测评未通过", "复核审批中", "待重新核算", "复核已驳回"],
};
export const allPerformanceStatuses = ["待到货", ...Object.values(performanceStages).flat()];
export const performanceStageStatuses = (phase: string): readonly string[] =>
  performanceStages[phase] ?? allPerformanceStatuses;

export function performanceFlowStatus(row: Product): string {
  const status = row.evaluationStatus ?? row.status;
  const firstWfs = row.backend ? row.backend.firstWfsDate : row.arrival;
  if (status === "测评中" && !firstWfs) return "待到货";
  if (status === "测评通过") {
    switch (row.backend?.purchaseStatus) {
      case "submitted": return "采购审批中";
      case "approved": return "采购已批准";
      case "rejected": return "采购已驳回";
      default: return "待申请采购";
    }
  }
  if (status === "测评未通过") {
    if (row.evaluationReviewStatus === "submitted" || row.evaluationReviewStatus === "info_required") return "复核审批中";
    if (row.evaluationReviewStatus === "approved" && row.evaluationRecheckRequired) return "待重新核算";
    if (row.evaluationReviewStatus === "rejected") return "复核已驳回";
  }
  return status;
}

export function performanceStatusParam(phase: string, selected: string[]): string {
  const allowed = performanceStageStatuses(phase);
  const filtered = selected.length ? selected.filter(s => allowed.includes(s)) : performanceStages[phase] ?? [];
  if (selected.length && !filtered.length) return "__none__";
  return filtered.map(s => `flow:${s}`).join(",");
}
