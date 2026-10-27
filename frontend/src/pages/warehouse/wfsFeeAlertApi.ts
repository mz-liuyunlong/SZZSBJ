import { backendRequest } from "@/api/backendApi";
import type {
  WfsFeeAlertFollowFormValues,
  WfsFeeRecoveredFormValues,
  WfsFeeAlertRow,
} from "@/pages/warehouse/wfsFeeAlertTypes";

type BackendWfsFeeCaseStatus = "pending_confirm" | "following" | "archive_pending" | "archived" | "recovered";
type BackendWfsFeeCasePriority = "high" | "medium" | "low";

type NumericLike = string | number | null;

interface BackendWfsFeeCase {
  id: string;
  source_kind: string;
  source_case_ref: string | null;
  legacy_case_id: number | null;
  legacy_status: string | null;
  legacy_updated_at: string | null;
  last_mirrored_at: string | null;
  platform: string;
  source_account_ref: string;
  store_id: string;
  item_id: string;
  msku: string;
  store_name_snapshot: string | null;
  local_sku_snapshot: string | null;
  product_name_snapshot: string | null;
  owner_ref: string | null;
  owner_name_snapshot: string | null;
  currency_code: string;
  manual_unit_fee: NumericLike;
  actual_unit_fee: NumericLike;
  product_management_unit_wfs_fee?: NumericLike;
  unit_fee_diff: NumericLike;
  fee_source: string;
  fee_source_ref: string | null;
  fee_calculated_at: string | null;
  calculation_version: string | null;
  affected_units: number;
  affected_sales_start_date: string | null;
  affected_sales_end_date: string | null;
  affected_units_source: string | null;
  estimated_recover_amount: NumericLike;
  pending_recover_amount: NumericLike;
  valid_sample_units?: NumericLike;
  valid_fee_orders?: number | null;
  mode_count?: number | null;
  theoretical_overcharge_amount?: NumericLike;
  net_sample_difference_amount?: NumericLike;
  latest_settlement_date?: string | null;
  detection_status?: string | null;
  data_freshness_status?: string | null;
  standard_fee_source?: string | null;
  detected_at?: string | null;
  sales_coverage_status?: string | null;
  sales_coverage_reason?: string | null;
  sales_coverage_start_date?: string | null;
  sales_coverage_end_date?: string | null;
  fee_scope_status?: string | null;
  automatic_case_eligible?: boolean | null;
  claim_amount: NumericLike;
  recovered_amount: NumericLike;
  recovered_at: string | null;
  status: BackendWfsFeeCaseStatus;
  priority: BackendWfsFeeCasePriority;
  severity: BackendWfsFeeCasePriority;
  status_changed_at: string | null;
  status_changed_by: string | null;
  first_alert_at: string | null;
  case_opened_at: string | null;
  done_at: string | null;
  archived_at: string | null;
  case_nos: string | null;
  follow_log: string | null;
  latest_follow_note: string | null;
  log_updated_at: string | null;
  next_follow_at: string | null;
  follow_count: number;
  last_follow_by: string | null;
  last_follow_at: string | null;
  walmart_response_summary: string | null;
  last_rejection_reason: string | null;
  evidence_summary: string | null;
  archive_requested_by: string | null;
  archive_requested_at: string | null;
  archive_reason_type: string | null;
  archive_reason: string | null;
  archive_evidence: string | null;
  archive_review_status: string;
  archive_reviewed_by: string | null;
  archive_reviewed_at: string | null;
  archive_review_note: string | null;
  reason: string | null;
  remark: string | null;
  internal_note: string | null;
  created_at: string;
  updated_at: string;
  updated_by: string | null;
}

interface BackendWfsFeeCaseData {
  items: BackendWfsFeeCase[];
}

interface BackendMeta {
  page: number;
  page_size: number;
  total: number;
}

const statusLabelMap: Record<BackendWfsFeeCaseStatus, WfsFeeAlertRow["status"]> = {
  pending_confirm: "未开Case",
  following: "跟进中",
  archive_pending: "待归档审核",
  archived: "已归档",
  recovered: "已追回",
};

const priorityLabelMap: Record<BackendWfsFeeCasePriority, WfsFeeAlertRow["level"]> = {
  high: "高",
  medium: "中",
  low: "低",
};

const numberValue = (value: NumericLike | undefined) => Number(value ?? 0);
const dateValue = (value: string | null | undefined) => value?.slice(0, 10) ?? "";

const toRow = (item: BackendWfsFeeCase): WfsFeeAlertRow => {
  const affectedUnits = numberValue(item.affected_units);
  const actualUnitFee = numberValue(item.actual_unit_fee);
  const manualUnitFee = numberValue(item.manual_unit_fee);
  const estimatedRecoverAmount = numberValue(item.estimated_recover_amount);
  const productName = item.product_name_snapshot ?? item.local_sku_snapshot ?? item.item_id;
  const discoveredAt = dateValue(item.first_alert_at ?? item.created_at);

  return {
    id: item.id,
    imageLabel: productName,
    imageSymbol: "📦",
    sku: item.local_sku_snapshot ?? "-",
    msku: item.msku,
    store: item.store_name_snapshot ?? item.store_id,
    owner: item.owner_name_snapshot ?? item.owner_ref ?? "未分配",
    productId: item.item_id,
    productName,
    category: "-",
    orders: affectedUnits,
    units: affectedUnits,
    validFeeOrders: item.valid_fee_orders ?? null,
    validSampleUnits:
      item.valid_sample_units == null ? null : numberValue(item.valid_sample_units),
    modeCount: item.mode_count ?? null,
    chargedFee: actualUnitFee * affectedUnits,
    standardFee: manualUnitFee * affectedUnits,
    productUnitWfsFee:
      item.product_management_unit_wfs_fee == null
        ? null
        : numberValue(item.product_management_unit_wfs_fee),
    unitCharged: actualUnitFee,
    unitStandard: manualUnitFee,
    overFee: estimatedRecoverAmount,
    theoreticalOvercharge:
      item.theoretical_overcharge_amount == null
        ? null
        : numberValue(item.theoretical_overcharge_amount),
    netSampleDifference:
      item.net_sample_difference_amount == null
        ? null
        : numberValue(item.net_sample_difference_amount),
    unitOverFee: numberValue(item.unit_fee_diff),
    recoveredAmount: numberValue(item.recovered_amount),
    status: statusLabelMap[item.status],
    caseNo: item.case_nos ?? "",
    reason: item.reason ?? item.archive_reason ?? "实收费率高于人工配送费",
    discoveredAt,
    caseOpenedAt: dateValue(item.case_opened_at ?? item.first_alert_at),
    nextFollowAt: item.next_follow_at ?? "-",
    level: priorityLabelMap[item.priority],
    followLog: item.follow_log ?? "",
    followCount: item.follow_count,
    lastFollowBy: item.last_follow_by,
    lastFollowAt: item.last_follow_at,
    latestFollow: (item.follow_log ?? "").split(/\r?\n/).map((line) => line.trim()).filter(Boolean).at(-1) ?? item.latest_follow_note ?? "",
    latestSettlementDate: dateValue(item.latest_settlement_date) || "-",
    detectionStatus: item.detection_status ?? "历史案件",
    freshnessStatus: item.data_freshness_status ?? "unknown",
    standardFeeSource: item.standard_fee_source ?? item.fee_source,
    detectedAt: dateValue(item.detected_at) || discoveredAt,
    salesCoverageStatus: item.sales_coverage_status ?? "unknown",
    salesCoverageReason: item.sales_coverage_reason ?? "unproven",
    salesCoverageStartDate: dateValue(item.sales_coverage_start_date) || "-",
    salesCoverageEndDate: dateValue(item.sales_coverage_end_date) || "-",
    feeScopeStatus: item.fee_scope_status ?? "unverified",
    automaticCaseEligible: item.automatic_case_eligible ?? null,
  };
};

export interface WfsFeeDetectionPreview {
  scanned_accounts: number;
  scanned_stores: number;
  scanned_skus: number;
  valid_samples: number;
  overcharge_candidates: number;
  would_create: number;
  already_exists: number;
  review_required: number;
  skipped: number;
  failed: number;
}

export async function previewWfsFeeDetection(
  startDate: string,
  endDate: string,
): Promise<WfsFeeDetectionPreview> {
  const envelope = await backendRequest<WfsFeeDetectionPreview, null>(
    "/api/warehouse/wfs-fee-alerts/detection-preview",
    {
      method: "POST",
      body: JSON.stringify({ start_date: startDate, end_date: endDate }),
    },
  );
  return envelope.data;
}

export async function fetchWfsFeeAlerts(
  startDate?: string,
  endDate?: string,
): Promise<WfsFeeAlertRow[]> {
  const rows: WfsFeeAlertRow[] = [];
  const pageSize = 500;
  for (let page = 1; page <= 10_000; page += 1) {
    const search = new URLSearchParams({ page: String(page), page_size: String(pageSize) });
    if (startDate) search.set("start_date", startDate);
    if (endDate) search.set("end_date", endDate);
    const envelope = await backendRequest<BackendWfsFeeCaseData, BackendMeta>(
      `/api/warehouse/wfs-fee-cases?${search.toString()}`,
    );
    rows.push(...envelope.data.items.map(toRow));
    if (rows.length >= envelope.meta.total || envelope.data.items.length < pageSize) return rows;
  }
  throw new Error("WFS fee case pagination exceeded the safety limit");
}

export async function updateWfsFeeAlertCase(
  id: string,
  values: WfsFeeAlertFollowFormValues,
): Promise<void> {
  await backendRequest<{ updated: boolean }, null>(
    `/api/warehouse/wfs-fee-cases/${encodeURIComponent(id)}/follow`,
    {
      method: "POST",
      body: JSON.stringify({
        case_nos: values.caseNo,
        latest_follow_note: values.latestFollow,
      }),
    },
  );
}

export async function markWfsFeeCaseRecovered(
  id: string,
  values: WfsFeeRecoveredFormValues,
): Promise<void> {
  await backendRequest<{ updated: boolean }, null>(
    `/api/warehouse/wfs-fee-cases/${encodeURIComponent(id)}/mark-recovered`,
    {
      method: "POST",
      body: JSON.stringify({
        recovered_amount: values.recoveredAmount,
        latest_follow_note: values.latestFollowNote?.trim() ?? "",
      }),
    },
  );
}
