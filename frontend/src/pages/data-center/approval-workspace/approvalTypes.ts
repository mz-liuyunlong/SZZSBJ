export type ApprovalTab = "pending" | "approved" | "rejected";
export type ApprovalView = "mine" | "created" | "all";
export type ApprovalRisk = "low" | "medium" | "high";
export type ApprovalStatus = "submitted" | "info_required" | "approved" | "rejected" | "withdrawn" | "legacy_unverified";
export type Decision = "approved" | "rejected" | "info_required";
export interface ApprovalItem {
 id: string; version: number; approval_type: string; business_ref: string;
 title: string; source_account_ref: string; applicant_id: string | null;
 status: ApprovalStatus; risk_level: ApprovalRisk; amount: string | null;
 currency_code: string | null; submitted_at: string | null;
 reviewed_at: string | null; reviewed_by: string | null;
 reason: string; can_review: boolean; requires_verification: boolean;
}
export interface ApprovalListData { items: ApprovalItem[] }
export interface ApprovalMeta { page: number; page_size: number; total: number }
export interface ApprovalSummary { pending: number; high_risk: number; info_required: number; approved: number }
export interface ApprovalEvent { event_type: string; actor_id: string; note: string | null; created_at: string }
export interface WfsSnapshot {
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
 snapshot: WfsSnapshot; current_case: WfsSnapshot | null;
 data_changed: boolean; events: ApprovalEvent[];
}
export interface ApprovalFilters {
 tab: ApprovalTab; view: ApprovalView; approval_type?: string;
 risk_level?: ApprovalRisk; keyword: string; page: number; page_size: number;
}
export const approvalColumnFields = [
 { key: "title", title: "审批事项" },
 { key: "approval_type", title: "业务类型" },
 { key: "risk_level", title: "风险等级" },
 { key: "amount", title: "涉及金额" },
 { key: "applicant_id", title: "申请人" },
 { key: "submitted_at", title: "提交时间" },
 { key: "status", title: "审批状态" },
 { key: "action", title: "操作" },
];
export const riskNames: Record<ApprovalRisk, string> = { low: "低风险", medium: "中风险", high: "高风险" };
export const statusNames: Record<ApprovalStatus, string> = {
 submitted: "待审批", info_required: "待补资料",
 approved: "已审批", rejected: "已驳回", withdrawn: "已撤回",
 legacy_unverified: "历史待核验",
};
