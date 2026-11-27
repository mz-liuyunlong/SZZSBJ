import { hasPermission } from "@/shared/permissions/mockAccess";
import { reviewClearanceApplication } from "@/pages/products/clearance/clearanceApi";
import {
  decideApproval, decideCurrentWfsCase, decideNewProductEvaluationReview,
  decideNewProductPurchase, fetchApprovalDetail, fetchNewProductPurchaseDetail,
  fetchNewProductPurchaseStoreOptions, fetchWfsCaseReviewDetail,
  type PurchaseApprovalStoreOption,
} from "./approvalApi";
import type { ApprovalItem, ApprovalDetail } from "./approvalTypes";

const genericTypes = new Set([
  "purchase_exception", "finance_exception", "access_change", "operations_plan_ack",
]);
export function canBatchApprove(row: ApprovalItem, permissions: readonly string[]): boolean {
  if (row.id.startsWith("DEMO-") || !row.can_review || row.requires_verification) return false;
  if (row.status !== "submitted" && !(row.case_review && row.status === "info_required")) return false;
  const admin = hasPermission(permissions, "internal:approval:administrator");
  const wfs = hasPermission(permissions, "action:warehouse:wfs-fee-alert:archive-review");
  const np = hasPermission(permissions, "action:products:new-product-analysis:review");
  if (row.approval_type === "clearance_request") return row.status === "submitted" && !row.case_review;
  if (row.approval_type === "new_product_purchase") return (admin || np) && row.status === "submitted" && !row.case_review;
  if (row.approval_type === "new_product_evaluation_review") return np && !row.case_review;
  if (row.approval_type === "wfs_case_abandon") return wfs;
  return genericTypes.has(row.approval_type) && admin && wfs && !row.case_review;
}

export interface BatchRow {
  row: ApprovalItem;
  detail?: ApprovalDetail;
  stores: PurchaseApprovalStoreOption[];
  storeId?: string;
  quantity: number | null;
  confirmed: boolean;
  identityConfirmed: boolean;
  error?: string;
}
export function pendingBatchRow(row: ApprovalItem): BatchRow {
  return { row, stores: [], quantity: null, confirmed: false, identityConfirmed: false };
}
export async function prepareBatchRow(row: ApprovalItem, permissions: readonly string[]): Promise<BatchRow> {
  const result = pendingBatchRow(row);
  if (!canBatchApprove(row, permissions)) return {...result, error: "无审批权限、状态不符或业务尚未接入"};
  // Clearance uses the same latest-stock/version validation on submit as single approval.
  if (row.approval_type === "clearance_request") return result;
  try {
    const detail = await (row.approval_type === "new_product_purchase"
      ? fetchNewProductPurchaseDetail(row.id)
      : row.case_review ? fetchWfsCaseReviewDetail(row.id) : fetchApprovalDetail(row.id));
    if (detail.id !== row.id || detail.version !== row.version ||
        detail.approval_type !== row.approval_type || detail.source_account_ref !== row.source_account_ref ||
        detail.business_ref !== row.business_ref || Boolean(detail.case_review) !== Boolean(row.case_review) ||
        !canBatchApprove(detail, permissions) || detail.data_changed) {
      return {...result, error: "审批资料、版本或权限已变化，请刷新后重新选择"};
    }
    if (detail.approval_type === "new_product_purchase") {
      const options = await fetchNewProductPurchaseStoreOptions(detail.id);
      const stores = options.stores;
      if (!stores.some(s => s.store_id === options.source_store_id)) {
        return {...result, error: "原申请店铺无法核实，请单独检查"};
      }
      return {...result, detail, stores, storeId: options.source_store_id,
        quantity: detail.purchase_details?.requested_qty ?? null};
    }
    return {...result, detail};
  } catch {
    return {...result, error: "正式审批资料读取失败，请刷新或单独核实"};
  }
}
export function validBatchRow(entry: BatchRow): boolean {
  const row = entry.detail ?? entry.row;
  if (entry.error || !entry.confirmed) return false;
  if (row.approval_type !== "clearance_request" && !entry.detail) return false;
  if (row.case_review && !row.applicant_id && !entry.identityConfirmed) return false;
  if (row.approval_type === "new_product_purchase") {
    return entry.quantity !== null && Number.isSafeInteger(entry.quantity) &&
      entry.quantity >= 1 && entry.quantity <= 100000 &&
      entry.stores.some(s => s.store_id === entry.storeId);
  }
  return true;
}
export async function submitBatchRow(entry: BatchRow, permissions: readonly string[], note: string): Promise<"submitted" | "closed"> {
  const row = entry.detail ?? entry.row;
  if (!validBatchRow(entry) || !canBatchApprove(row, permissions)) throw new Error("invalid approval");
  if (row.approval_type === "clearance_request") {
    const result = await reviewClearanceApplication(row.id, row.version, "approved", note);
    if (result.status === "stock_closed") return "closed";
    if (result.status !== "running") throw new Error("unexpected clearance status");
  } else if (row.approval_type === "new_product_purchase") {
    if (!entry.storeId || entry.quantity === null) throw new Error("missing purchase confirmation");
    await decideNewProductPurchase(row.id, row.version, "approved", note, {
      purchase_store_id: entry.storeId, approved_qty: entry.quantity,
    });
  } else if (row.approval_type === "new_product_evaluation_review") {
    await decideNewProductEvaluationReview(row.id, row.version, "approved", note);
  } else if (row.case_review && row.approval_type === "wfs_case_abandon") {
    await decideCurrentWfsCase(row.business_ref, row.version, "approved", note, entry.identityConfirmed);
  } else if (row.approval_type === "wfs_case_abandon" || genericTypes.has(row.approval_type)) {
    await decideApproval(row.id, row.version, "approved", note);
  } else {
    throw new Error("unsupported approval");
  }
  return "submitted";
}
