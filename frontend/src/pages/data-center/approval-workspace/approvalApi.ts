import { backendRequest } from "@/api/backendApi";
import type { ApprovalDetail, ApprovalFilters, ApprovalItem, ApprovalListData, ApprovalMeta, ApprovalSummary, Decision } from "./approvalTypes";

export async function fetchApprovals(filters: ApprovalFilters) {
 // The simplified workbench merges pending-for-review and created applications.
 // The server excludes formal applications already linked to WFS Cases.
 const params = new URLSearchParams({
  tab: filters.tab, view: filters.view ?? "all", page: String(filters.page),
  page_size: String(filters.page_size),
 });
 if (filters.risk_level) params.set("risk_level", filters.risk_level);
 if (filters.approval_type) params.set("approval_type",filters.approval_type);
 if (filters.keyword?.trim()) params.set("keyword",filters.keyword.trim());
 return backendRequest<ApprovalListData, ApprovalMeta>("/api/approvals?" + params.toString());
}
export async function fetchApprovalSummary(): Promise<ApprovalSummary> {
 return (await backendRequest<ApprovalSummary, null>("/api/approvals/summary")).data;
}
export async function fetchWfsCaseReviewDetail(caseId: string): Promise<ApprovalDetail> {
 return (await backendRequest<ApprovalDetail, null>("/api/approvals/wfs-cases/" + encodeURIComponent(caseId) + "/detail")).data;
}
export async function fetchApprovalDetail(id: ApprovalItem["id"]): Promise<ApprovalDetail> {
 return (await backendRequest<ApprovalDetail, null>("/api/approvals/" + encodeURIComponent(id))).data;
}
export async function decideCurrentWfsCase(
  caseId: string, version: number, decision: Decision, note: string,
  acknowledgeMissingApplicant: boolean,
) {
  await backendRequest<{ updated: boolean }, null>(
    "/api/approvals/wfs-cases/" + encodeURIComponent(caseId) + "/decision",
    { method: "POST", body: JSON.stringify({
      expected_version: version, decision, note,
      acknowledge_missing_applicant: acknowledgeMissingApplicant,
    }) },
  );
}

export async function decideApproval(id: string, version: number, decision: Decision, note: string) {
 await backendRequest<{ updated: boolean }, null>("/api/approvals/" + encodeURIComponent(id) + "/decision", {
  method: "POST", body: JSON.stringify({ expected_version: version, decision, note }),
 });
}
export async function supplementApproval(id: string, version: number, note: string, evidence: string) {
 await backendRequest<{ updated: boolean }, null>("/api/approvals/" + encodeURIComponent(id) + "/supplement", {
  method: "POST", body: JSON.stringify({ expected_version: version, note, evidence }),
 });
}
export async function submitWfsArchiveRequest(caseId: string, reasonType: string, reason: string, evidence: string) {
 return backendRequest<{ approval_id: string; created: boolean }, null>(
  "/api/approvals/wfs-cases/" + encodeURIComponent(caseId),
  { method: "POST", body: JSON.stringify({
   archive_reason_type: reasonType, archive_reason: reason, archive_evidence: evidence,
  }) },
 );
}

/** Business review decision is permissioned by new-product assessment, not WFS. */
export async function decideNewProductEvaluationReview(id: string, version: number,
  decision: "approved" | "rejected", reason: string) {
  await backendRequest<{id:string;status:string;version:number}, null>(
    "/api/new-products/evaluation-reviews/" + encodeURIComponent(id) + "/decision", {
      method: "POST", body: JSON.stringify({expected_version:version,decision,reason}),
    });
}


// NP_PURCHASE_WORKBENCH_REAL_API_V1_20261116
export async function fetchNewProductPurchaseApprovals(filters: ApprovalFilters) {
  const params = new URLSearchParams({
    tab: filters.tab, view: filters.view ?? "all",
    page: String(filters.page), page_size: String(filters.page_size),
  });
  if (filters.risk_level) params.set("risk_level", filters.risk_level);
  if (filters.keyword?.trim()) params.set("keyword", filters.keyword.trim());
  return backendRequest<ApprovalListData, ApprovalMeta>(
    "/api/approvals/new-products/purchases?" + params.toString()
  );
}
export async function fetchNewProductPurchaseDetail(id: string): Promise<ApprovalDetail> {
  return (await backendRequest<ApprovalDetail, null>(
    "/api/approvals/new-products/purchases/" + encodeURIComponent(id)
  )).data;
}
export async function decideNewProductPurchase(
  id: string, version: number, decision: "approved" | "rejected", note: string
): Promise<void> {
  await backendRequest<{updated:boolean},null>(
    "/api/approvals/new-products/purchases/" + encodeURIComponent(id) + "/decision",
    {method:"POST", body:JSON.stringify({expected_version:version,decision,note})}
  );
}
