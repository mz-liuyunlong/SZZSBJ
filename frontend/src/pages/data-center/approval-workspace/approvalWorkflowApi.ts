import { backendRequest } from "@/api/backendApi";

export interface ApprovalRule {
  approval_type: string;
  title: string;
  required_steps: number;
  min_reason_length: number;
  due_hours: number;
  allows_bulk: boolean;
  is_active: boolean;
  version: number;
}
export interface ApprovalNotification {
  id: string;
  approval_id: string;
  event_key: string;
  status: "read" | "unread";
  created_at: string;
}
export type GenericApprovalType = "purchase_exception" | "finance_exception" | "access_change" | "operations_plan_ack";

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

export async function submitGenericApproval(
  type: GenericApprovalType, sourceRef: string,
  account: string, reason: string, evidence: string,
): Promise<string> {
  const result = await backendRequest<{ approval_id: string }, null>(
    "/api/approvals/workflow/requests",
    { method: "POST", body: JSON.stringify({
      approval_type: type, source_ref: sourceRef,
      source_account_ref: account, reason, evidence,
    }) },
  );
  return result.data.approval_id;
}
export async function fetchApprovalRules(): Promise<ApprovalRule[]> {
  return (await backendRequest<ApprovalRule[], null>("/api/approvals/workflow/rules")).data;
}
export async function updateApprovalRule(
  kind: string, rule: ApprovalRule, updates: {
    required_steps: number; due_hours: number; allows_bulk: boolean;
  },
): Promise<void> {
  await backendRequest<{ updated: boolean }, null>(
    "/api/approvals/workflow/rules/" + encodeURIComponent(kind), {
      method: "PUT",
      body: JSON.stringify({ ...updates, expected_version: rule.version }),
    },
  );
}
export async function fetchApprovalNotifications(): Promise<ApprovalNotification[]> {
  return (await backendRequest<ApprovalNotification[], null>(
    "/api/approvals/workflow/notifications",
  )).data;
}
export async function markApprovalNotificationRead(id: string): Promise<boolean> {
  return (await backendRequest<{ updated: boolean }, null>(
    "/api/approvals/workflow/notifications/" + encodeURIComponent(id) + "/read",
    { method: "POST", body: "{}" },
  )).data.updated;
}
