import { backendRequest } from "@/api/backendApi";

export type GradeStage =
  | "测品期" | "打品期" | "启动期" | "上升期" | "稳定期"
  | "下滑期" | "断货期" | "修复期";

export interface TierPercents {
  lt2: number;
  from2to5: number;
  from5to10: number;
  from10to20: number;
  gte20: number;
}

export interface LifecycleRuleConfig {
  min_week_valid_days: number;
  growth_min_valid_days_30: number;
  stable_min_valid_days_30: number;
  decline_min_valid_days_30: number;
  growth_threshold_pct: TierPercents;
  decline_threshold_pct: TierPercents;
  stable_tolerance_pct: TierPercents;
}
export interface InventoryRepairRuleConfig {
  low_stock_max_units: number;
  stockout_consecutive_days: number;
  long_stockout_days: number;
  stockout_repair_valid_days: number;
  strike_price_abnormal_days: number;
  buybox_abnormal_days: number;
  abnormal_recovery_days: number;
}
export interface FollowUpRuleConfig {
  reminder_time: string | null;
  deadline_time: string | null;
  overdue_notice: boolean;
}

export interface ListingGradeRuleConfig {
  execution_time: string; // HH:mm in Asia/Shanghai; default 22:30
  short_days: number;
  medium_days: number;
  short_weight_percent: number;
  medium_weight_percent: number;
  short_min_valid_days: number;
  medium_min_valid_days: number;
  c_min_percent: string;
  b_min_percent: string;
  a_above_percent: string;
  included_stages: GradeStage[];
  lifecycle: LifecycleRuleConfig;
  inventory_repair: InventoryRepairRuleConfig;
  follow_up: FollowUpRuleConfig;
}

export interface ListingGradeRuleRead {
  version: number;
  config: ListingGradeRuleConfig;
  protected: {
    execution_timezone: "Asia/Shanghai";
    business_timezone: "America/Los_Angeles";
    closing_lag_days: 2;
    requires_complete_financial_inputs: true;
    permanently_excluded_stages: string[];
  };
  effective_from: string | null;
  created_at: string | null;
  created_by: string | null;
  change_reason: string | null;
  is_pending: boolean;
  source: "default" | "database";
  can_edit: boolean;
  storage_ready: boolean;
}

export interface ListingGradeRuleHistory {
  total: number;
  storage_ready: boolean;
  items: Array<{
    version: number;
    config: ListingGradeRuleConfig;
    effective_from: string;
    created_at: string;
    created_by: string;
    change_reason: string;
  }>;
}

const BASE_PATH = "/api/listings/rule-config";

export async function fetchListingGradeRule(): Promise<ListingGradeRuleRead> {
  return (await backendRequest<ListingGradeRuleRead>(BASE_PATH)).data;
}

export async function saveListingGradeRule(
  config: ListingGradeRuleConfig,
  expectedVersion: number,
  reason: string,
): Promise<ListingGradeRuleRead> {
  return (await backendRequest<ListingGradeRuleRead>(BASE_PATH, {
    method: "PUT",
    body: JSON.stringify({
      config,
      expected_version: expectedVersion,
      change_reason: reason,
    }),
  })).data;
}

export async function fetchListingGradeRuleHistory(
  limit = 20,
): Promise<ListingGradeRuleHistory> {
  return (await backendRequest<ListingGradeRuleHistory>(`${BASE_PATH}/history?limit=${limit}`)).data;
}
