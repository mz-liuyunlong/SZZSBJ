export type RuleFamily =
  | "create_long_unshipped"
  | "arrival_overdue"
  | "arrival_no_receiving"
  | "receiving_incomplete"
  | "closed_shortage_damage"
  | "appeal_deadline";

export type CaseStatus = "OPEN" | "IN_PROGRESS" | "WAITING_EXTERNAL" | "RESOLVED" | "CLOSED";
export type Severity = "HIGH" | "MEDIUM" | "LOW";

export interface ExceptionFilters {
  keyword: string;
  keyword_field: "shipment" | "pk" | "summary" | "platform_case";
  store_id?: string;
  shipment_id?: string;
  rule_family?: RuleFamily;
  status?: CaseStatus;
  severity?: Severity;
  assignee_user_id?: string;
  only_test: boolean;
  due_soon: boolean;
}

export interface ExceptionRow {
  id: string;
  shipment_id: string;
  shipment_row_id?: string | null;
  rule_family: RuleFamily;
  rule_label: string;
  severity: Severity;
  status: CaseStatus;
  status_label: string;
  summary: string;
  store_id: string;
  store_name?: string | null;
  pk?: string | null;
  sku?: string | null;
  item_id?: string | null;
  gtin?: string | null;
  msku?: string | null;
  assignee_user_id?: string | null;
  platform_case_ref?: string | null;
  due_at?: string | null;
  due_basis?: string | null;
  qty_variance?: number | null;
  business_test: boolean;
  first_detected_at: string;
  version: number;
  rule_version: string;
  lingxing_data_status: "PENDING";
}

export interface ExceptionSummary {
  open_shipments: number;
  open_cases: number;
  due_soon_cases: number;
}

export interface TimelineItem {
  id: string;
  kind: "detection" | "action";
  action_type?: string | null;
  actor_uid?: string | null;
  message: string;
  payload: Record<string, unknown>;
  created_at: string;
}

export interface ExceptionDetail extends ExceptionRow {
  evidence: Record<string, unknown>;
  timeline: TimelineItem[];
  quantity_reconciliation_note: string;
  lingxing_updated_at?: string | null;
}
