import { backendRequest } from "@/api/backendApi";

export async function reattestLegacyWfs(
  caseId: string, reasonType: string, reason: string, evidence: string,
): Promise<string> {
  const result = await backendRequest<{ approval_id: string }, null>(
    "/api/approvals/legacy/" + encodeURIComponent(caseId) + "/reattest",
    { method: "POST", body: JSON.stringify({
      reason_type: reasonType, reason, evidence,
    }) },
  );
  return result.data.approval_id;
}

export async function approveLowRiskBatch(
 items: {id:string;version:number}[], note:string,
): Promise<number> {
 const result = await backendRequest<{approved:number},null>(
  "/api/approvals/workflow/bulk-approve", {
   method:"POST", body:JSON.stringify({
    approval_ids:items.map(item=>item.id),
    expected_versions:Object.fromEntries(items.map(item=>[item.id,item.version])),
    note,
   }),
  },
 );
 return result.data.approved;
}
