import { backendRequest } from "@/api/backendApi";

export type CommissionRuleScope = "store" | "item" | "price_range";
export type StoreCommissionSource = "store_rule" | "default_15_percent";
export type StoreCommissionApplyScope = "all_dates" | "from_date";
export type BusinessRuleOperationStatus = "queued" | "running" | "succeeded" | "failed";

export interface BusinessRuleOperationLog {
  id: string;
  source_account_ref: string;
  platform_code: string;
  operation_type: string;
  status: BusinessRuleOperationStatus;
  store_id: string | null;
  rule_scope: CommissionRuleScope | null;
  item_ids: string[];
  price_min_amount: string | null;
  price_max_amount: string | null;
  start_date: string | null;
  end_date: string | null;
  days_recalculated: number;
  daily_sales_rows: number;
  order_profit_rows: number;
  actor_ref: string;
  request_id: string;
  message: string | null;
  error_message: string | null;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  updated_at: string;
}

interface StoreCommissionApiItem {
  id: string | null;
  source_account_ref: string;
  platform_code: string;
  store_id: string;
  store_name: string | null;
  rule_scope: CommissionRuleScope;
  item_id: string | null;
  price_min_amount: string | null;
  price_max_amount: string | null;
  priority: number;
  commission_rate: string;
  commission_percent: string;
  source: StoreCommissionSource;
  effective_from: string | null;
  effective_to: string | null;
  is_active: boolean;
  rule_version: string | null;
  change_reason: string | null;
  approved_by: string | null;
  approved_at: string | null;
  needs_recalculate: boolean;
  active_operation_id: string | null;
  active_operation_status: BusinessRuleOperationStatus | null;
  active_operation_actor: string | null;
  active_operation_created_at: string | null;
}

interface StoreCommissionListData {
  store_rules: StoreCommissionApiItem[];
  special_rules: StoreCommissionApiItem[];
  active_operations: BusinessRuleOperationLog[];
  operation_logs: BusinessRuleOperationLog[];
}

interface StoreCommissionMutationData {
  items: StoreCommissionApiItem[];
}

export interface StoreCommissionRecord {
  id: string | null;
  sourceAccountRef: string;
  platformCode: string;
  storeId: string;
  storeName: string | null;
  ruleScope: CommissionRuleScope;
  itemId: string | null;
  priceMinAmount: number | null;
  priceMaxAmount: number | null;
  priority: number;
  commissionRate: number;
  commissionPercent: number;
  source: StoreCommissionSource;
  effectiveFrom: string | null;
  effectiveTo: string | null;
  isActive: boolean;
  ruleVersion: string | null;
  changeReason: string | null;
  approvedBy: string | null;
  approvedAt: string | null;
  needsRecalculate: boolean;
  activeOperationId: string | null;
  activeOperationStatus: BusinessRuleOperationStatus | null;
  activeOperationActor: string | null;
  activeOperationCreatedAt: string | null;
}

export interface StoreCommissionListResult {
  storeRules: StoreCommissionRecord[];
  specialRules: StoreCommissionRecord[];
  activeOperations: BusinessRuleOperationLog[];
  operationLogs: BusinessRuleOperationLog[];
}

export interface SaveStoreCommissionPayload {
  sourceAccountRef: string;
  platformCode: "walmart";
  storeId: string;
  ruleScope: CommissionRuleScope;
  itemIds?: string[];
  priceMinAmount?: string | null;
  priceMaxAmount?: string | null;
  priority: number;
  commissionRate: string;
  applyScope: StoreCommissionApplyScope;
  effectiveFrom: string | null;
  effectiveTo?: string | null;
  changeReason: string;
  replaceRuleId?: string | null;
}

export interface RecalculateStoreCommissionPayload {
  sourceAccountRef: string;
  storeId: string;
  ruleScope: CommissionRuleScope;
  itemIds?: string[];
  priceMinAmount?: string | null;
  priceMaxAmount?: string | null;
  startDate?: string | null;
  endDate?: string | null;
  confirmAllDates: boolean;
}

export interface RecalculateStoreCommissionResult {
  operation_id: string;
  source_account_ref: string;
  store_id: string;
  rule_scope: CommissionRuleScope;
  item_ids: string[];
  status: BusinessRuleOperationStatus;
  message: string;
}

const numericOrNull = (value: string | null) => {
  if (value == null || value === "") return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
};

const normalizeRecord = (item: StoreCommissionApiItem): StoreCommissionRecord => ({
  id: item.id,
  sourceAccountRef: item.source_account_ref,
  platformCode: item.platform_code,
  storeId: item.store_id,
  storeName: item.store_name,
  ruleScope: item.rule_scope,
  itemId: item.item_id,
  priceMinAmount: numericOrNull(item.price_min_amount),
  priceMaxAmount: numericOrNull(item.price_max_amount),
  priority: item.priority,
  commissionRate: Number(item.commission_rate),
  commissionPercent: Number(item.commission_percent),
  source: item.source,
  effectiveFrom: item.effective_from,
  effectiveTo: item.effective_to,
  isActive: item.is_active,
  ruleVersion: item.rule_version,
  changeReason: item.change_reason,
  approvedBy: item.approved_by,
  approvedAt: item.approved_at,
  needsRecalculate: item.needs_recalculate,
  activeOperationId: item.active_operation_id,
  activeOperationStatus: item.active_operation_status,
  activeOperationActor: item.active_operation_actor,
  activeOperationCreatedAt: item.active_operation_created_at,
});

export async function listStoreCommissions(): Promise<StoreCommissionListResult> {
  const response = await backendRequest<StoreCommissionListData>(
    "/api/business-rules/store-commissions",
  );
  return {
    storeRules: response.data.store_rules.map(normalizeRecord),
    specialRules: response.data.special_rules.map(normalizeRecord),
    activeOperations: response.data.active_operations,
    operationLogs: response.data.operation_logs,
  };
}

export async function saveStoreCommission(payload: SaveStoreCommissionPayload) {
  const response = await backendRequest<StoreCommissionMutationData>(
    "/api/business-rules/store-commissions",
    {
      method: "POST",
      body: JSON.stringify({
        source_account_ref: payload.sourceAccountRef,
        platform_code: payload.platformCode,
        store_id: payload.storeId,
        rule_scope: payload.ruleScope,
        item_ids: payload.itemIds ?? [],
        price_min_amount: payload.priceMinAmount ?? null,
        price_max_amount: payload.priceMaxAmount ?? null,
        priority: payload.priority,
        commission_rate: payload.commissionRate,
        apply_scope: payload.applyScope,
        effective_from: payload.effectiveFrom,
        effective_to: payload.effectiveTo ?? null,
        change_reason: payload.changeReason,
        replace_rule_id: payload.replaceRuleId ?? null,
      }),
    },
  );
  return response.data.items.map(normalizeRecord);
}

export async function deactivateStoreCommission(sourceAccountRef: string, ruleId: string) {
  await backendRequest<StoreCommissionMutationData>(
    "/api/business-rules/store-commissions/deactivate",
    {
      method: "POST",
      body: JSON.stringify({
        source_account_ref: sourceAccountRef,
        rule_id: ruleId,
      }),
    },
  );
}

export async function recalculateStoreCommission(payload: RecalculateStoreCommissionPayload) {
  const response = await backendRequest<RecalculateStoreCommissionResult>(
    "/api/business-rules/store-commissions/recalculate",
    {
      method: "POST",
      body: JSON.stringify({
        source_account_ref: payload.sourceAccountRef,
        store_id: payload.storeId,
        rule_scope: payload.ruleScope,
        item_ids: payload.itemIds ?? [],
        price_min_amount: payload.priceMinAmount ?? null,
        price_max_amount: payload.priceMaxAmount ?? null,
        start_date: payload.startDate ?? null,
        end_date: payload.endDate ?? null,
        confirm_all_dates: payload.confirmAllDates,
      }),
    },
  );
  return response.data;
}

export async function listStoreCommissionLogs() {
  const response = await backendRequest<{ items: BusinessRuleOperationLog[] }>(
    "/api/business-rules/store-commissions/logs",
  );
  return response.data.items;
}
