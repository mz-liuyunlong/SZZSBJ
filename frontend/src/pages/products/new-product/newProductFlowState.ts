/** PR337_FLOW_WFS_REAL_STATUS_20261116: presentation state from persisted evidence. */
import type { NewProductListing, RealScore } from "./newProductBusinessApi";
import type { Product } from "./nativeData";

const validDate = (value: unknown): boolean =>
  typeof value === "string" && /^\d{4}-\d{2}-\d{2}$/.test(value) &&
  !Number.isNaN(Date.parse(value + "T00:00:00Z"));
const number = (value: unknown): number | null => {
  if (value === null || value === undefined || value === "") return null;
  const n = Number(value);
  return Number.isFinite(n) ? n : null;
};
const TERMINAL = new Set(["打品成功", "打品失败"]);

export function resolveNewProductFlow(row: NewProductListing, evaluation: RealScore): string {
  const f = row.facts || {};
  const final = row.tracking_final_result || row.tracking_decision;
  if (final && TERMINAL.has(final)) return final;
  if (row.tracking_review_status === "submitted") return "结果审核中";

  const stage = row.tracking_status || "";
  if (
    !!row.tracking_started_date_la ||
    ["打品跟踪中", "观察中", "跟踪中", "active", "tracking", "in_progress"].includes(stage) ||
    ["继续观察", "需要优化"].includes(row.tracking_decision || "")
  ) return "打品跟踪中";

  const purchase = row.purchase_status;
  if (purchase === "submitted") return "采购审核中";
  if (purchase === "approved") {
    if (["awaiting_sellable", "waiting_open", "waiting_for_sale", "not_started", "等待开售"].includes(row.tracking_start_status || "")) {
      return "等待开售";
    }
    return "采购已通过";
  }
  if (purchase === "rejected") return "采购已驳回";

  const firstWfs = f.first_wfs_available_date_la || row.listing.first_wfs_available_date_la;
  if (!validDate(firstWfs)) {
    const stock = number(row.listing.wfs_available_quantity);
    if (f.data_status === "awaiting_wfs" && (stock === null || stock <= 0)) {
      return "待首次可售";
    }
    return "可售时间待核实";
  }
  if (evaluation.observation_state === "not_calculated") return "待计算";
  const hasAutomatic = (["speed", "ad", "profit", "trust"] as const)
    .some((key) => number(evaluation.dimensions?.[key]) !== null);
  if (!hasAutomatic) return "数据待评估";
  if (number(f.market_score) === null) return "待市场评分";
  if (evaluation.grade === null || evaluation.total === null) return "数据待评估";
  if (evaluation.grade === "D" || evaluation.grade === "Pass") return "测评未通过";
  return "待采购";
}

/** PR337_PERFORMANCE_FIVE_STATES_20261116: evaluation-only business states.
 * Purchase and tracking remain in their separate business modules.
 * Zero orders never mean 'not listed'.
 */
export function resolveNewProductEvaluationFlow(row: NewProductListing, evaluation: RealScore): string {
  const f = row.facts || {};
  // The listing start field is evidence of listing; an absent order date is not.
  const listed = [f.first_wfs_available_date_la, row.listing.first_wfs_available_date_la,
    row.listing.launch_date_cn].some(value =>
    typeof value === "string" && validDate(value.slice(0,10)));
  if (!listed) return "待到货";

  // A score published in the past is retained and cannot be rewritten here.
  const finalGrade = evaluation.grade;
  if (finalGrade !== null && evaluation.total !== null) {
    if (finalGrade === "D" || finalGrade === "Pass") return "测评未通过";
    if (["S", "A", "B", "C"].includes(finalGrade)) return "测评通过";
  }

  // The approved automatic triggers: 14 LA days OR verified first-batch sold-out
  // OR a saved operator calculation decision. This view does NOT invent trigger records.
  const elapsed = number(f.elapsed_days);
  const soldOutVerified = f.sold_out_evidence_status === "verified" &&
    validDate(f.first_batch_sold_out_date_la);
  const manualApproved = f.evaluation_trigger_source === "manual" &&
    f.evaluation_trigger_status === "completed";
  const triggerMet = (elapsed !== null && elapsed >= 14) ||
    soldOutVerified || manualApproved;
  if (!triggerMet) return "测评中";

  const auto = (["speed", "ad", "profit", "trust"] as const)
    .some(key => number(evaluation.dimensions?.[key]) !== null);
  if (!auto || evaluation.observation_state === "not_calculated") return "测评中";
  if (number(f.market_score) === null) return "待市场评分";
  // Missing source evidence is NOT a failed business evaluation.
  return "测评中";
}

/** Zero is a legitimate score; missing evidence is not. */
export function hasNewProductScoreDetails(row: Product): boolean {
  if (row.backend) {
    if (!row.backend.firstWfsDate && !row.launch && !TERMINAL.has(row.tracking)) return false;
    const evaluation = row.backend.evaluation;
    if (evaluation.total !== null || evaluation.grade !== null) return true;
    return (["speed", "ad", "profit", "trust"] as const)
      .some((key) => number(evaluation.dimensions?.[key]) !== null);
  }
  return row.status !== "待计算" && row.status !== "待首次可售" &&
    row.status !== "可售时间待核实" &&
    Object.values(row.scores).some((v) => number(v) !== null);
}
