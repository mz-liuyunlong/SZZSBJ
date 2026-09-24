/**
 * Typed client for the PMC purchase board read routes (`/api/pmc/purchase/*`).
 *
 * Contract: `docs/api/pmc-purchase-api.md`. Every request goes through `backendRequest`
 * (envelope + preview token); list filters are sent as repeated query keys because the
 * backend parses them with a strict pydantic model (`extra="forbid"`).
 */
import { backendRequest } from "@/api/backendApi";
import type {
  MoneyByCurrency,
  PendingPurchasePlan,
  PendingPurchasePlanListResult,
  PurchaseBoardFilters,
  PurchaseBoardItemIdSource,
  PurchaseBoardListResult,
  PurchaseBoardRow,
  PurchaseBoardSearchType,
  PurchaseBoardSort,
  PurchaseBoardStatusFilter,
  PurchaseBoardSummary,
  PurchaseItemIdRef,
  PurchaseOrderDetail,
  PurchaseOwnerRef,
  PurchaseOverdueKind,
  PurchaseReadMeta,
  PurchaseStageCode,
  PurchaseStageRef,
  PurchaseStoreRef,
  SkuCycle,
  SkuCycleBrief,
  SkuCycleExclusion,
  SkuCycleSample,
  SkuCycleSource,
} from "@/pages/pmc/purchase-board/purchaseBoardTypes";

// --- backend (snake_case) shapes -----------------------------------------------------------

interface BackendStoreRef {
  id: string | null;
  name: string | null;
  attributed: boolean;
}

interface BackendOwnerRef {
  uid: string | null;
  name: string | null;
}

interface BackendItemIdRef {
  item_id: string | null;
  source: PurchaseBoardItemIdSource;
  source_ref: string | null;
  matched_at: string | null;
  match_status: "matched" | "pending" | "unresolved";
  msku: string | null;
  gtin: string | null;
  fulfillment_type: string | null;
  wfs_not_ready: boolean | null;
}

interface BackendStageRef {
  stage_code: PurchaseStageCode;
  stage_start: string | null;
  stage_start_estimated: boolean;
  threshold_days: number | null;
  due_date: string | null;
  overdue_days: number;
  overdue_kind: PurchaseOverdueKind | null;
  alert_due_since: string | null;
}

interface BackendSkuCycleBrief {
  value_days: string | null;
  source: SkuCycleSource | null;
  sample_count: number | null;
  unstable: boolean;
}

interface BackendSkuCycleSample {
  purchase_order_sn: string;
  order_date: string;
  arrival_date: string;
  cycle_days: number;
  used: boolean;
  exclusion: SkuCycleExclusion | null;
}

interface BackendSkuCycle {
  sku: string;
  value_days: string | null;
  source: SkuCycleSource;
  sample_count: number;
  baseline_days: number | null;
  baseline_set_on: string | null;
  lingxing_default_days: number | null;
  unstable: boolean;
  range_days: number | null;
  samples: BackendSkuCycleSample[];
  rule_version: number;
  calculated_at: string;
}

interface BackendBoardRow {
  purchase_order_sn: string;
  order_item_id: string;
  plan_sn: string | null;
  plan_sns: string[];
  order_status: number | null;
  stage: BackendStageRef;
  store: BackendStoreRef;
  sku: string | null;
  product_name: string | null;
  item_id: BackendItemIdRef;
  owner: BackendOwnerRef;
  quantity_total: number | null;
  quantity_allocated: number;
  quantity_received: number;
  progress_ratio: string | null;
  remaining_quantity: number;
  order_date: string | null;
  order_create_date: string | null;
  plan_create_date: string | null;
  arrival_date: string | null;
  arrival_receipt_order_sn: string | null;
  purchase_cycle_days: number | null;
  approval_cycle_days: number | null;
  sku_cycle: BackendSkuCycleBrief;
  unit_price: string | null;
  amount_allocated: string | null;
  amount_total: string | null;
  currency_code: string | null;
  calculated_at: string;
}

interface BackendBoardListData {
  items: BackendBoardRow[];
  total: number;
}

interface BackendMoneyByCurrency {
  currency_code: string | null;
  amount: string;
}

interface BackendBoardSummaryData {
  awaiting_arrival_orders: number;
  arrival_overdue_orders: number;
  purchase_overdue_orders: number;
  purchase_overdue_plans: number;
  average_purchase_cycle_days_90d: string | null;
  month_purchase_amount: BackendMoneyByCurrency[];
  unstable_sku_count: number;
  itemid_pending_lines: number;
  wfs_not_ready_lines: number;
  unattributed_store_lines: number;
  as_of: string;
}

interface BackendOrderReceiptRef {
  receipt_order_sn: string;
  is_arrival_receipt: boolean;
}

interface BackendOrderPlanRef {
  plan_sn: string;
  plan_status: number | null;
  plan_create_date: string | null;
  quantity_plan: number | null;
  remark_item_id: string | null;
  store_id: string | null;
}

interface BackendOrderDetailData {
  purchase_order_sn: string;
  order_status: number | null;
  order_date: string | null;
  order_create_date: string | null;
  quantity_total: number | null;
  quantity_received: number;
  progress_ratio: string | null;
  arrival_date: string | null;
  amount_total: string | null;
  currency_code: string | null;
  stage: BackendStageRef;
  lines: BackendBoardRow[];
  receipts: BackendOrderReceiptRef[];
  plans: BackendOrderPlanRef[];
  sku_cycles: BackendSkuCycle[];
}

interface BackendPendingPlan {
  plan_sn: string;
  plan_status: number | null;
  plan_create_date: string | null;
  pending_since: string | null;
  pending_since_estimated: boolean;
  pending_days: number | null;
  overdue_days: number;
  store: BackendStoreRef;
  sku: string | null;
  product_name: string | null;
  quantity_plan: number | null;
  remark_item_id: string | null;
}

interface BackendPendingPlanListData {
  items: BackendPendingPlan[];
  total: number;
  threshold_days: number;
}

interface BackendPurchaseReadMeta {
  source?: string;
  source_objects?: string[];
  freshness_at?: string | null;
  rule_version?: number | null;
  page?: number | null;
  page_size?: number | null;
  total?: number | null;
}

interface BackendProductManagementOptions {
  owners?: { uid: string; name: string; count?: number }[];
}

export interface PurchaseBoardOwnerOption {
  uid: string;
  name: string;
  count?: number;
}

// --- helpers -------------------------------------------------------------------------------

const toNumber = (value: string | number | null | undefined): number | null => {
  if (value === null || value === undefined || value === "") return null;
  const parsed = typeof value === "number" ? value : Number(value);
  return Number.isFinite(parsed) ? parsed : null;
};

const mapMeta = (meta: BackendPurchaseReadMeta | undefined): PurchaseReadMeta => ({
  freshnessAt: meta?.freshness_at ?? null,
  ruleVersion: meta?.rule_version ?? null,
  total: meta?.total ?? null,
});

const mapStore = (store: BackendStoreRef): PurchaseStoreRef => ({
  id: store.id,
  name: store.name,
  attributed: store.attributed,
});

const mapOwner = (owner: BackendOwnerRef): PurchaseOwnerRef => ({ uid: owner.uid, name: owner.name });

const mapItemId = (item: BackendItemIdRef): PurchaseItemIdRef => ({
  itemId: item.item_id,
  source: item.source,
  sourceRef: item.source_ref,
  matchedAt: item.matched_at,
  matchStatus: item.match_status,
  msku: item.msku,
  gtin: item.gtin,
  fulfillmentType: item.fulfillment_type,
  wfsNotReady: item.wfs_not_ready,
});

const mapStage = (stage: BackendStageRef): PurchaseStageRef => ({
  stageCode: stage.stage_code,
  stageStart: stage.stage_start,
  stageStartEstimated: stage.stage_start_estimated,
  thresholdDays: stage.threshold_days,
  dueDate: stage.due_date,
  overdueDays: stage.overdue_days,
  overdueKind: stage.overdue_kind,
  alertDueSince: stage.alert_due_since,
});

const mapSkuCycleBrief = (cycle: BackendSkuCycleBrief): SkuCycleBrief => ({
  valueDays: toNumber(cycle.value_days),
  source: cycle.source,
  sampleCount: cycle.sample_count,
  unstable: cycle.unstable,
});

const mapSkuCycleSample = (sample: BackendSkuCycleSample): SkuCycleSample => ({
  purchaseOrderSn: sample.purchase_order_sn,
  orderDate: sample.order_date,
  arrivalDate: sample.arrival_date,
  cycleDays: sample.cycle_days,
  used: sample.used,
  exclusion: sample.exclusion,
});

const mapSkuCycle = (cycle: BackendSkuCycle): SkuCycle => ({
  sku: cycle.sku,
  valueDays: toNumber(cycle.value_days),
  source: cycle.source,
  sampleCount: cycle.sample_count,
  baselineDays: cycle.baseline_days,
  baselineSetOn: cycle.baseline_set_on,
  lingxingDefaultDays: cycle.lingxing_default_days,
  unstable: cycle.unstable,
  rangeDays: cycle.range_days,
  samples: cycle.samples.map(mapSkuCycleSample),
  ruleVersion: cycle.rule_version,
  calculatedAt: cycle.calculated_at,
});

export const purchaseBoardRowId = (
  row: Pick<BackendBoardRow, "purchase_order_sn" | "order_item_id" | "plan_sn">,
) => `${row.purchase_order_sn}::${row.order_item_id}::${row.plan_sn ?? ""}`;

const mapRow = (row: BackendBoardRow): PurchaseBoardRow => ({
  id: purchaseBoardRowId(row),
  purchaseOrderSn: row.purchase_order_sn,
  orderItemId: row.order_item_id,
  planSn: row.plan_sn,
  planSns: row.plan_sns,
  orderStatus: row.order_status,
  stage: mapStage(row.stage),
  store: mapStore(row.store),
  sku: row.sku,
  productName: row.product_name,
  itemId: mapItemId(row.item_id),
  owner: mapOwner(row.owner),
  quantityTotal: row.quantity_total,
  quantityAllocated: row.quantity_allocated,
  quantityReceived: row.quantity_received,
  progressRatio: toNumber(row.progress_ratio),
  remainingQuantity: row.remaining_quantity,
  orderDate: row.order_date,
  orderCreateDate: row.order_create_date,
  planCreateDate: row.plan_create_date,
  arrivalDate: row.arrival_date,
  arrivalReceiptOrderSn: row.arrival_receipt_order_sn,
  purchaseCycleDays: row.purchase_cycle_days,
  approvalCycleDays: row.approval_cycle_days,
  skuCycle: mapSkuCycleBrief(row.sku_cycle),
  unitPrice: toNumber(row.unit_price),
  amountAllocated: toNumber(row.amount_allocated),
  amountTotal: toNumber(row.amount_total),
  currencyCode: row.currency_code,
  calculatedAt: row.calculated_at,
});

const mapMoneyByCurrency = (item: BackendMoneyByCurrency): MoneyByCurrency => ({
  currencyCode: item.currency_code,
  amount: toNumber(item.amount) ?? 0,
});

const mapPendingPlan = (plan: BackendPendingPlan): PendingPurchasePlan => ({
  planSn: plan.plan_sn,
  planStatus: plan.plan_status,
  planCreateDate: plan.plan_create_date,
  pendingSince: plan.pending_since,
  pendingSinceEstimated: plan.pending_since_estimated,
  pendingDays: plan.pending_days,
  overdueDays: plan.overdue_days,
  store: mapStore(plan.store),
  sku: plan.sku,
  productName: plan.product_name,
  quantityPlan: plan.quantity_plan,
  remarkItemId: plan.remark_item_id,
});

/** Splits batch input the same way the backend normalises `search_values`. */
export const normalizeSearchValues = (values: string[]) => {
  const seen = new Set<string>();
  for (const raw of values) {
    for (const piece of raw.replace(/,/g, " ").split(/\s+/)) {
      const trimmed = piece.trim();
      if (trimmed) seen.add(trimmed);
    }
  }
  return [...seen];
};

const appendAll = (query: URLSearchParams, key: string, values: readonly string[]) => {
  for (const value of values) query.append(key, value);
};

/** Builds the shared filter part of `/board` and `/board/summary` (repeated keys for lists). */
export function buildPurchaseBoardFilterQuery(filters: PurchaseBoardFilters) {
  const query = new URLSearchParams();
  appendAll(query, "owner_uid", filters.ownerUids);
  appendAll(query, "status", filters.statuses);

  const searchValues = normalizeSearchValues(
    filters.batchValues && filters.batchValues.length > 0
      ? filters.batchValues
      : [filters.keyword],
  );
  if (searchValues.length > 0) {
    query.set("search_type", filters.searchType);
    appendAll(query, "search_values", searchValues);
  }

  appendAll(query, "item_id_source", filters.itemIdSources);
  if (filters.orderDateFrom) query.set("order_date_from", filters.orderDateFrom);
  if (filters.orderDateTo) query.set("order_date_to", filters.orderDateTo);
  if (filters.qtyMin !== undefined) query.set("qty_min", String(filters.qtyMin));
  if (filters.qtyMax !== undefined) query.set("qty_max", String(filters.qtyMax));
  if (filters.priceMin !== undefined && filters.priceMin !== "") query.set("price_min", filters.priceMin);
  if (filters.priceMax !== undefined && filters.priceMax !== "") query.set("price_max", filters.priceMax);
  if (filters.wfsNotReady !== undefined) query.set("wfs_not_ready", String(filters.wfsNotReady));
  if (filters.todayFollowup) query.set("today_followup", "true");
  return query;
}

export function buildPurchaseBoardListQuery(
  filters: PurchaseBoardFilters,
  page: number,
  pageSize: number,
  sort: PurchaseBoardSort = filters.sort,
) {
  const query = buildPurchaseBoardFilterQuery(filters);
  query.set("page", String(page));
  query.set("page_size", String(pageSize));
  query.set("sort", sort);
  return query;
}

// --- requests ------------------------------------------------------------------------------

export async function listPurchaseBoard(
  filters: PurchaseBoardFilters,
  page: number,
  pageSize: number,
  signal?: AbortSignal,
): Promise<PurchaseBoardListResult> {
  const query = buildPurchaseBoardListQuery(filters, page, pageSize);
  const response = await backendRequest<BackendBoardListData, BackendPurchaseReadMeta>(
    `/api/pmc/purchase/board?${query.toString()}`,
    { signal },
  );
  return {
    rows: response.data.items.map(mapRow),
    total: response.data.total,
    meta: mapMeta(response.meta),
  };
}

export async function getPurchaseBoardSummary(
  filters: PurchaseBoardFilters,
  signal?: AbortSignal,
): Promise<PurchaseBoardSummary> {
  const query = buildPurchaseBoardFilterQuery(filters);
  const suffix = query.toString();
  const response = await backendRequest<BackendBoardSummaryData, BackendPurchaseReadMeta>(
    `/api/pmc/purchase/board/summary${suffix ? `?${suffix}` : ""}`,
    { signal },
  );
  const data = response.data;
  return {
    awaitingArrivalOrders: data.awaiting_arrival_orders,
    arrivalOverdueOrders: data.arrival_overdue_orders,
    purchaseOverdueOrders: data.purchase_overdue_orders,
    purchaseOverduePlans: data.purchase_overdue_plans,
    averagePurchaseCycleDays90d: toNumber(data.average_purchase_cycle_days_90d),
    monthPurchaseAmount: data.month_purchase_amount.map(mapMoneyByCurrency),
    unstableSkuCount: data.unstable_sku_count,
    itemidPendingLines: data.itemid_pending_lines,
    wfsNotReadyLines: data.wfs_not_ready_lines,
    unattributedStoreLines: data.unattributed_store_lines,
    asOf: data.as_of,
    meta: mapMeta(response.meta),
  };
}

export async function getPurchaseOrderDetail(
  orderSn: string,
  signal?: AbortSignal,
): Promise<PurchaseOrderDetail> {
  const response = await backendRequest<BackendOrderDetailData, BackendPurchaseReadMeta>(
    `/api/pmc/purchase/orders/${encodeURIComponent(orderSn)}`,
    { signal },
  );
  const data = response.data;
  return {
    purchaseOrderSn: data.purchase_order_sn,
    orderStatus: data.order_status,
    orderDate: data.order_date,
    orderCreateDate: data.order_create_date,
    quantityTotal: data.quantity_total,
    quantityReceived: data.quantity_received,
    progressRatio: toNumber(data.progress_ratio),
    arrivalDate: data.arrival_date,
    amountTotal: toNumber(data.amount_total),
    currencyCode: data.currency_code,
    stage: mapStage(data.stage),
    lines: data.lines.map(mapRow),
    receipts: data.receipts.map((receipt) => ({
      receiptOrderSn: receipt.receipt_order_sn,
      isArrivalReceipt: receipt.is_arrival_receipt,
    })),
    plans: data.plans.map((plan) => ({
      planSn: plan.plan_sn,
      planStatus: plan.plan_status,
      planCreateDate: plan.plan_create_date,
      quantityPlan: plan.quantity_plan,
      remarkItemId: plan.remark_item_id,
      storeId: plan.store_id,
    })),
    skuCycles: data.sku_cycles.map(mapSkuCycle),
    meta: mapMeta(response.meta),
  };
}

export async function listPendingPurchasePlans(
  params: { page: number; pageSize: number; overdueOnly?: boolean; searchValues?: string[] },
  signal?: AbortSignal,
): Promise<PendingPurchasePlanListResult> {
  const query = new URLSearchParams();
  query.set("page", String(params.page));
  query.set("page_size", String(params.pageSize));
  if (params.overdueOnly) query.set("overdue_only", "true");
  appendAll(query, "search_values", normalizeSearchValues(params.searchValues ?? []));
  const response = await backendRequest<BackendPendingPlanListData, BackendPurchaseReadMeta>(
    `/api/pmc/purchase/plans/pending?${query.toString()}`,
    { signal },
  );
  return {
    rows: response.data.items.map(mapPendingPlan),
    total: response.data.total,
    thresholdDays: response.data.threshold_days,
    meta: mapMeta(response.meta),
  };
}

/**
 * Owner options come from Product Management (page spec §5: the only approved source).
 * Only the `owners` field of that approved contract is read here.
 */
export async function getPurchaseBoardOwnerOptions(
  signal?: AbortSignal,
): Promise<PurchaseBoardOwnerOption[]> {
  const response = await backendRequest<BackendProductManagementOptions>(
    "/api/product-management/options",
    { signal },
  );
  return (response.data.owners ?? []).map((owner) => ({
    uid: owner.uid,
    name: owner.name,
    count: owner.count,
  }));
}

export type { PurchaseBoardSearchType, PurchaseBoardStatusFilter };
