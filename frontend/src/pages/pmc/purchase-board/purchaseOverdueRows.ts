/**
 * 待采购超时 rows: order lines (S2 overdue) and approved-but-unconverted plans merged into
 * one list (Rocky 2026-11-01). Kept out of the table component so the component file only
 * exports components (react-refresh/only-export-components).
 */
import type {
  PendingPurchasePlan,
  PurchaseBoardRow,
  PurchaseStoreRef,
} from "@/pages/pmc/purchase-board/purchaseBoardTypes";

export interface PurchaseOverdueRow {
  key: string;
  kind: "order" | "plan";
  docSn: string;
  planSn: string | null;
  sku: string | null;
  productName: string | null;
  store: PurchaseStoreRef;
  quantity: number | null;
  createdDate: string | null;
  pendingDays: number | null;
  pendingEstimated: boolean;
  overdueDays: number;
  ownerName: string | null;
  remarkItemId: string | null;
}

const daysSince = (iso: string | null, today: Date) => {
  if (!iso) return null;
  const start = new Date(`${iso.slice(0, 10)}T00:00:00Z`).getTime();
  if (Number.isNaN(start)) return null;
  const now = Date.UTC(today.getUTCFullYear(), today.getUTCMonth(), today.getUTCDate());
  return Math.max(0, Math.round((now - start) / 86_400_000));
};

export function overdueRowFromOrder(row: PurchaseBoardRow, today = new Date()): PurchaseOverdueRow {
  return {
    key: `order:${row.id}`,
    kind: "order",
    docSn: row.purchaseOrderSn,
    planSn: row.planSn,
    sku: row.sku,
    productName: row.productName,
    store: row.store,
    quantity: row.quantityTotal,
    createdDate: row.orderCreateDate ?? row.planCreateDate,
    pendingDays: daysSince(row.stage.stageStart, today),
    pendingEstimated: row.stage.stageStartEstimated,
    overdueDays: row.stage.overdueDays,
    ownerName: row.owner.name,
    remarkItemId: null,
  };
}

export function overdueRowFromPlan(plan: PendingPurchasePlan): PurchaseOverdueRow {
  return {
    key: `plan:${plan.planSn}`,
    kind: "plan",
    docSn: plan.planSn,
    planSn: plan.planSn,
    sku: plan.sku,
    productName: plan.productName,
    store: plan.store,
    quantity: plan.quantityPlan,
    createdDate: plan.planCreateDate,
    pendingDays: plan.pendingDays,
    pendingEstimated: plan.pendingSinceEstimated,
    overdueDays: plan.overdueDays,
    ownerName: null,
    remarkItemId: plan.remarkItemId,
  };
}

export function mergeOverdueRows(orders: PurchaseBoardRow[], plans: PendingPurchasePlan[], today = new Date()) {
  return [
    ...orders.map((row) => overdueRowFromOrder(row, today)),
    ...plans.map(overdueRowFromPlan),
  ].sort((a, b) => (
    b.overdueDays - a.overdueDays
    || (b.pendingDays ?? -1) - (a.pendingDays ?? -1)
    || a.docSn.localeCompare(b.docSn)
  ));
}
