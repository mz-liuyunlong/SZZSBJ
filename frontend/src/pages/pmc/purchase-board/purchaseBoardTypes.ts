/**
 * View types for the PMC purchase board (Gate 4a, read-only).
 *
 * Field semantics come from the approved backend contract `docs/api/pmc-purchase-api.md`
 * (`backend/app/modules/pmc_purchase/schemas.py`). The frontend does not derive business
 * values; it only renames snake_case to camelCase and parses decimal strings for display.
 */

export type PurchaseBoardStatusFilter =
  | "s2"
  | "s3"
  | "s4"
  | "overdue"
  | "s9"
  | "s0"
  | "unattributed";

export type PurchaseBoardSearchType = "sku" | "item_id" | "gtin" | "msku" | "order_sn";

export type PurchaseBoardItemIdSource =
  | "from_system_plan"
  | "from_plan_remark"
  | "from_packing_slip"
  | "pending_packing_slip"
  | "unresolved";

export type PurchaseBoardSort =
  | "order_date_desc"
  | "order_date_asc"
  | "overdue_days_desc"
  | "arrival_date_desc"
  | "amount_desc";

export type PurchaseStageCode = "S1" | "S2" | "S3" | "S4" | "S9" | "S0" | "UNKNOWN";

export type PurchaseOverdueKind = "purchase" | "arrival";

export type SkuCycleSource = "samples" | "baseline_mix" | "lingxing_default" | "no_baseline";

export type SkuCycleExclusion = "auto_short" | "manual" | "before_baseline" | "outside_window";

/** Filters kept in page state; only committed values reach the API. */
export interface PurchaseBoardFilters {
  ownerUids: string[];
  statuses: PurchaseBoardStatusFilter[];
  searchType: PurchaseBoardSearchType;
  keyword: string;
  batchValues?: string[];
  orderDateFrom?: string;
  orderDateTo?: string;
  itemIdSources: PurchaseBoardItemIdSource[];
  qtyMin?: number;
  qtyMax?: number;
  priceMin?: string;
  priceMax?: string;
  wfsNotReady?: boolean;
  todayFollowup: boolean;
  sort: PurchaseBoardSort;
}

export type PurchaseBoardMoreFilters = Pick<
  PurchaseBoardFilters,
  "itemIdSources" | "qtyMin" | "qtyMax" | "priceMin" | "priceMax" | "wfsNotReady"
>;

export const createInitialPurchaseBoardFilters = (): PurchaseBoardFilters => ({
  ownerUids: [],
  statuses: [],
  searchType: "sku",
  keyword: "",
  batchValues: undefined,
  orderDateFrom: undefined,
  orderDateTo: undefined,
  itemIdSources: [],
  qtyMin: undefined,
  qtyMax: undefined,
  priceMin: undefined,
  priceMax: undefined,
  wfsNotReady: undefined,
  todayFollowup: false,
  sort: "order_date_desc",
});

export const emptyMoreFilters: PurchaseBoardMoreFilters = {
  itemIdSources: [],
  qtyMin: undefined,
  qtyMax: undefined,
  priceMin: undefined,
  priceMax: undefined,
  wfsNotReady: undefined,
};

export const countMoreFilters = (value: PurchaseBoardMoreFilters) => (
  (value.itemIdSources.length > 0 ? 1 : 0)
  + (value.qtyMin !== undefined || value.qtyMax !== undefined ? 1 : 0)
  + ((value.priceMin ?? "") !== "" || (value.priceMax ?? "") !== "" ? 1 : 0)
  + (value.wfsNotReady !== undefined ? 1 : 0)
);

export interface PurchaseStoreRef {
  id: string | null;
  name: string | null;
  attributed: boolean;
}

export interface PurchaseOwnerRef {
  uid: string | null;
  name: string | null;
}

export interface PurchaseItemIdRef {
  itemId: string | null;
  source: PurchaseBoardItemIdSource;
  sourceRef: string | null;
  matchedAt: string | null;
  matchStatus: "matched" | "pending" | "unresolved";
  msku: string | null;
  gtin: string | null;
  fulfillmentType: string | null;
  wfsNotReady: boolean | null;
}

export interface PurchaseStageRef {
  stageCode: PurchaseStageCode;
  stageStart: string | null;
  stageStartEstimated: boolean;
  thresholdDays: number | null;
  dueDate: string | null;
  overdueDays: number;
  overdueKind: PurchaseOverdueKind | null;
  alertDueSince: string | null;
}

export interface SkuCycleBrief {
  valueDays: number | null;
  source: SkuCycleSource | null;
  sampleCount: number | null;
  unstable: boolean;
}

export interface SkuCycleSample {
  purchaseOrderSn: string;
  orderDate: string;
  arrivalDate: string;
  cycleDays: number;
  used: boolean;
  exclusion: SkuCycleExclusion | null;
}

export interface SkuCycle {
  sku: string;
  valueDays: number | null;
  source: SkuCycleSource;
  sampleCount: number;
  baselineDays: number | null;
  baselineSetOn: string | null;
  lingxingDefaultDays: number | null;
  unstable: boolean;
  rangeDays: number | null;
  samples: SkuCycleSample[];
  ruleVersion: number;
  calculatedAt: string;
}

export interface PurchaseBoardRow {
  /** Stable row key: `${purchaseOrderSn}::${orderItemId}::${planSn ?? ""}`. */
  id: string;
  purchaseOrderSn: string;
  orderItemId: string;
  planSn: string | null;
  planSns: string[];
  orderStatus: number | null;
  stage: PurchaseStageRef;
  store: PurchaseStoreRef;
  sku: string | null;
  productName: string | null;
  itemId: PurchaseItemIdRef;
  owner: PurchaseOwnerRef;
  quantityTotal: number | null;
  quantityAllocated: number;
  quantityReceived: number;
  progressRatio: number | null;
  remainingQuantity: number;
  orderDate: string | null;
  orderCreateDate: string | null;
  planCreateDate: string | null;
  arrivalDate: string | null;
  arrivalReceiptOrderSn: string | null;
  purchaseCycleDays: number | null;
  approvalCycleDays: number | null;
  skuCycle: SkuCycleBrief;
  unitPrice: number | null;
  amountAllocated: number | null;
  amountTotal: number | null;
  currencyCode: string | null;
  calculatedAt: string;
}

export interface PurchaseReadMeta {
  freshnessAt: string | null;
  ruleVersion: number | null;
  total: number | null;
}

export interface PurchaseBoardListResult {
  rows: PurchaseBoardRow[];
  total: number;
  meta: PurchaseReadMeta;
}

export interface MoneyByCurrency {
  currencyCode: string | null;
  amount: number;
}

export interface PurchaseBoardSummary {
  awaitingArrivalOrders: number;
  arrivalOverdueOrders: number;
  purchaseOverdueOrders: number;
  purchaseOverduePlans: number;
  averagePurchaseCycleDays90d: number | null;
  monthPurchaseAmount: MoneyByCurrency[];
  unstableSkuCount: number;
  itemidPendingLines: number;
  wfsNotReadyLines: number;
  unattributedStoreLines: number;
  asOf: string;
  meta: PurchaseReadMeta;
}

export interface PurchaseOrderReceiptRef {
  receiptOrderSn: string;
  isArrivalReceipt: boolean;
}

export interface PurchaseOrderPlanRef {
  planSn: string;
  planStatus: number | null;
  planCreateDate: string | null;
  quantityPlan: number | null;
  remarkItemId: string | null;
  storeId: string | null;
}

export interface PurchaseOrderDetail {
  purchaseOrderSn: string;
  orderStatus: number | null;
  orderDate: string | null;
  orderCreateDate: string | null;
  quantityTotal: number | null;
  quantityReceived: number;
  progressRatio: number | null;
  arrivalDate: string | null;
  amountTotal: number | null;
  currencyCode: string | null;
  stage: PurchaseStageRef;
  lines: PurchaseBoardRow[];
  receipts: PurchaseOrderReceiptRef[];
  plans: PurchaseOrderPlanRef[];
  skuCycles: SkuCycle[];
  meta: PurchaseReadMeta;
}

export interface PendingPurchasePlan {
  planSn: string;
  planStatus: number | null;
  planCreateDate: string | null;
  pendingSince: string | null;
  pendingSinceEstimated: boolean;
  pendingDays: number | null;
  overdueDays: number;
  store: PurchaseStoreRef;
  sku: string | null;
  productName: string | null;
  quantityPlan: number | null;
  remarkItemId: string | null;
}

export interface PendingPurchasePlanListResult {
  rows: PendingPurchasePlan[];
  total: number;
  thresholdDays: number;
  meta: PurchaseReadMeta;
}

export interface PurchaseBoardColumnField {
  key: string;
  title: string;
}

/** Column catalogue (business rules v4 §9); order here is the default column order. */
export const purchaseBoardColumnFields: PurchaseBoardColumnField[] = [
  { key: "purchaseOrderSn", title: "采购单号" },
  { key: "stage", title: "状态" },
  { key: "store", title: "店铺" },
  { key: "sku", title: "SKU" },
  { key: "productName", title: "产品名" },
  { key: "gtin", title: "GTIN" },
  { key: "itemId", title: "ItemID" },
  { key: "owner", title: "负责人" },
  { key: "progress", title: "进度" },
  { key: "orderDate", title: "下单日期" },
  { key: "arrivalDate", title: "到仓日期" },
  { key: "purchaseCycleDays", title: "采购交期" },
  { key: "approvalCycleDays", title: "审批周期" },
  { key: "skuCycle", title: "实际采购交期" },
  { key: "unitPrice", title: "单价" },
  { key: "amountAllocated", title: "金额" },
  { key: "planSn", title: "计划号" },
];

/** Default widths for the board columns (px); users can resize at runtime. */
export const purchaseBoardDefaultColumnWidths: Record<string, number> = {
  purchaseOrderSn: 168,
  stage: 220,
  store: 140,
  sku: 150,
  productName: 220,
  gtin: 140,
  itemId: 170,
  owner: 100,
  progress: 130,
  orderDate: 112,
  arrivalDate: 112,
  purchaseCycleDays: 120,
  approvalCycleDays: 100,
  skuCycle: 170,
  unitPrice: 110,
  amountAllocated: 120,
  planSn: 150,
  actions: 80,
};

export const fixedPurchaseBoardColumnKeys = ["purchaseOrderSn", "stage"];

export const purchaseBoardStatusOptions: { value: PurchaseBoardStatusFilter; label: string }[] = [
  { value: "s2", label: "待下单" },
  { value: "s3", label: "已下单未到货" },
  { value: "s4", label: "部分到货" },
  { value: "overdue", label: "已逾期" },
  { value: "s9", label: "已到货" },
  { value: "s0", label: "已作废" },
  { value: "unattributed", label: "未归属店铺" },
];

export const purchaseBoardSearchTypeOptions: { value: PurchaseBoardSearchType; label: string }[] = [
  { value: "sku", label: "SKU" },
  { value: "item_id", label: "ItemID" },
  { value: "gtin", label: "GTIN" },
  { value: "msku", label: "MSKU" },
  { value: "order_sn", label: "采购单号" },
];

export const purchaseBoardItemIdSourceOptions: {
  value: PurchaseBoardItemIdSource;
  label: string;
}[] = [
  { value: "from_system_plan", label: "已归属（系统计划）" },
  { value: "from_plan_remark", label: "已归属（计划备注）" },
  { value: "from_packing_slip", label: "已归属（打包单）" },
  { value: "pending_packing_slip", label: "待打包单" },
  { value: "unresolved", label: "待处理" },
];

export const purchaseBoardSortOptions: { value: PurchaseBoardSort; label: string }[] = [
  { value: "order_date_desc", label: "下单日期 新→旧" },
  { value: "order_date_asc", label: "下单日期 旧→新" },
  { value: "overdue_days_desc", label: "逾期天数 多→少" },
  { value: "arrival_date_desc", label: "到仓日期 新→旧" },
  { value: "amount_desc", label: "金额 高→低" },
];

/** Backend `page_size` is capped at 200 for this contract (schemas.BoardListQuery). */
export const PURCHASE_BOARD_PAGE_SIZE_OPTIONS = ["50", "100", "200"];
export const PURCHASE_BOARD_MAX_PAGE_SIZE = 200;
