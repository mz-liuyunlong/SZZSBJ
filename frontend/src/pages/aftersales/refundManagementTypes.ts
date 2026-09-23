export type RefundMetric = "qty" | "rate" | "loss";
export type RefundAnalysisView = "trend" | "heat";
export type RefundProductSort = "rate" | "loss" | "qty";
export type RefundDatePreset = "today" | "week" | "month" | "year" | "custom";
export type RefundSearchField = "sku" | "msku" | "productId" | "productName" | "orderId";

export interface RefundFilters {
  owners: string[];
  stores: string[];
  reasons: string[];
  responsibilities: string[];
  currency: "USD";
  datePreset: RefundDatePreset;
  dateRange?: [string, string];
  searchField: RefundSearchField;
  keyword: string;
  batchValues?: string[];
}

export interface RefundFilterOption {
  value: string;
  label: string;
  color?: string;
}

export interface RefundReasonTag {
  code: string;
  name: string;
  categoryCode: string;
  categoryName: string;
  color: string;
}

export interface RefundResponsibilityTag {
  code: string;
  name: string;
  color: string;
  source: string;
  confidence: string;
  editable: boolean;
}

export interface RefundReasonDatum extends RefundReasonTag {
  count: number;
  qty: number;
  amount: number;
  loss: number;
}

export interface RefundResponsibilityDatum {
  code: string;
  name: string;
  color: string;
  count: number;
  qty: number;
  amount: number;
  loss: number;
}

export interface RefundLagDatum {
  key: "0_3" | "4_7" | "8_14" | "15_30" | "31_plus";
  name: string;
  orders: number;
  count: number;
  ratio: number | null;
  amount: number;
  loss: number;
}

export interface RefundLagAnalysis {
  averageDays: number | null;
  medianDays: number | null;
  mainBucket: RefundLagDatum["key"] | null;
  mainBucketRatio: number | null;
  eligibleItemRows: number;
  missingTimeRows: number;
  buckets: RefundLagDatum[];
}

export interface RefundProductDatum {
  productKey: string;
  storeId: string;
  store: string;
  sku: string;
  msku: string;
  productId: string;
  name: string;
  owner: string;
  sales: number;
  orders: number;
  qty: number;
  amount: number;
  rate: number | null;
  loss: number;
  topReason: RefundReasonTag | null;
  topResponsibility: RefundResponsibilityTag | null;
  risk: "pending";
}

export interface RefundProductDetail extends RefundProductDatum {
  trend: number[];
  reasons: RefundReasonDatum[];
  lag: RefundLagAnalysis;
}

export interface RefundDetailRow {
  id: string;
  store: string;
  storeId: string;
  productId: string;
  productName: string;
  sku: string;
  msku: string;
  owner: string;
  orderId: string;
  returnOrderId: string;
  orderedAt: string;
  refundedAt: string;
  refundLagDays: number | null;
  qty: number;
  amount: number | null;
  currency: "USD";
  loss: number | null;
  rawReasonCode: string;
  rawDescription: string;
  reason: RefundReasonTag;
  responsibility: RefundResponsibilityTag;
  status: string;
  completed: boolean;
}

export interface RefundSummaryView {
  refundOrders: number;
  refundItemRows: number;
  refundQty: number;
  refundAmount: number;
  refundLossAmount: number;
  salesQty: number;
  refundRate: number | null;
  avgRefundAmountPerUnit: number | null;
  avgRefundLossPerUnit: number | null;
  ordersChangeRate: number | null;
  qtyChangeRate: number | null;
  lossChangeRate: number | null;
  refundRateChangePp: number | null;
}

export interface RefundOverviewView {
  summary: RefundSummaryView;
  dates: string[];
  trend: {
    qty: number[];
    rate: number[];
    loss: number[];
  };
  reasons: RefundReasonDatum[];
  responsibilities: RefundResponsibilityDatum[];
  stores: RefundFilterOption[];
  owners: RefundFilterOption[];
  reasonOptions: RefundFilterOption[];
  responsibilityOptions: RefundFilterOption[];
  latestUpdatedAt: string | null;
}

export interface RefundProductAnalysisViewData {
  dates: string[];
  items: RefundProductDatum[];
  heat: number[][];
  selected: RefundProductDetail | null;
  latestUpdatedAt: string | null;
}

export interface RefundDetailApiResult {
  rows: RefundDetailRow[];
  page: number;
  pageSize: number;
  total: number;
  latestUpdatedAt: string | null;
}
