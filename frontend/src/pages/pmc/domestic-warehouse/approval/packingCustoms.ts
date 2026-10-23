/** One choice vocabulary for list, manual creation and approval; defaults come from the server. */
import type { ApprovalCandidate } from "./packingApprovalApi";
export type CustomsChoice = "default" | "declare" | "skip";
export const customsSourceLabel = (source: string) =>
  ({
    default: "默认",
    purchase_order: "采购单",
    product_remark: "产品采购备注",
    purchase_remark: "采购备注",
    manual: "人工",
  })[source] ?? "未知";
export function customsHint(row: ApprovalCandidate, choice: CustomsChoice) {
  return choice === "default"
    ? `${customsSourceLabel(row.customs_default_src ?? "default")}${row.customs_proof?.remark ? `：${row.customs_proof.remark}` : "：未关联采购单或不符合报关条件，默认不报关"}`
    : "人工选择，审批通过时保存";
}
