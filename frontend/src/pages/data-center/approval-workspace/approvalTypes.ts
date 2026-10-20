export type ApprovalTab = "pending" | "approved" | "rejected";
export type ApprovalView = "mine" | "created" | "all";
export const approvalTabs: { label: string; value: ApprovalTab }[] = [
 { label: "待审批", value: "pending" },
 { label: "已审批", value: "approved" },
 { label: "驳回记录", value: "rejected" },
];
export type ApprovalRisk = "low" | "medium" | "high";
export type ApprovalStatus = "submitted" | "info_required" | "approved" | "rejected" | "withdrawn" | "legacy_unverified";
export type Decision = "approved" | "rejected" | "info_required";
export interface ApprovalItem {
  case_opened_at?: string | null;
  follow_count?: number | null;
 id: string; version: number; approval_type: string; business_ref: string;
 title: string; source_account_ref: string; applicant_id: string | null;
 status: ApprovalStatus; risk_level: ApprovalRisk; amount: string | null;
 currency_code: string | null; submitted_at: string | null;
 reviewed_at: string | null; reviewed_by: string | null;
 reason: string; can_review: boolean; requires_verification: boolean; case_review?: boolean; follow_log?: string | null;
}
export interface ApprovalListData { items: ApprovalItem[] }
export interface ApprovalMeta { page: number; page_size: number; total: number }
export interface ApprovalSummary { pending: number; high_risk: number; info_required: number; approved: number; legacy_unverified: number }
export interface ApprovalEvent { event_type: string; actor_id: string; note: string | null; created_at: string }
export interface WfsSnapshot {
  case_opened_at?: string | null;
  first_alert_at?: string | null;
 [key: string]: unknown;
 follow_log?: string | null;
 status?: string; estimated_recover_amount?: string;
 pending_recover_amount?: string; recovered_amount?: string;
 currency_code?: string; msku?: string; item_id?: string;
 store_name_snapshot?: string; owner_name_snapshot?: string;
 case_nos?: string; walmart_response_summary?: string;
 evidence_summary?: string;
}
export interface ApprovalDetail extends ApprovalItem {
 snapshot: WfsSnapshot; evidence: string | null; current_case: WfsSnapshot | null;
 data_changed: boolean; can_supplement: boolean; events: ApprovalEvent[];
}
export interface ApprovalFilters {
 tab: ApprovalTab; risk_level?: ApprovalRisk; page: number; page_size: number;
}
export const approvalColumnFields = [
 { key: "approval_type", title: "业务类型 / 编号" },
 { key: "title", title: "审批事项" },
 { key: "follow_log", title: "运营跟进记录" },
  { key: "case_opened_at", title: "立案时间" },
  { key: "follow_count", title: "跟进次数" },
 { key: "risk_level", title: "风险等级" },
 { key: "amount", title: "金额" },
 { key: "applicant_id", title: "申请人" },
 { key: "submitted_at", title: "提交时间" },
 { key: "status", title: "状态" },
 { key: "action", title: "操作" },
];
export const riskNames: Record<ApprovalRisk, string> = { low: "低风险", medium: "中风险", high: "高风险" };
export const statusNames: Record<ApprovalStatus, string> = {
 submitted: "待审批", info_required: "待补资料",
 approved: "已审批", rejected: "已驳回", withdrawn: "已撤回",
 legacy_unverified: "历史待核验",
};
