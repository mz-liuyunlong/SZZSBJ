import type { Product } from "./newProductModel";

/** Read-only, no guesses from tracking quantities or current rule for a submitted request. */
export function passedPurchaseView(row: Product) {
  const b = row.backend;
  const hasApplication = Boolean(b?.purchaseId);
  const approved = b?.purchaseStatus === "approved";
  const requested = hasApplication ? row.requestQty ?? null : null;
  const approvedQty = approved ? b?.purchaseApprovedQty ?? null : null;
  const suggested = hasApplication ? b?.purchaseSuggestedQty ?? null : b?.suggestedQty ?? null;
  const source = b?.purchaseSourceStoreId;
  const target = b?.approvedPurchaseStoreId;
  const storeChange = approved && source && target && source !== target
    ? { from: (row as Product & {storeName?: string | null}).storeName || source,
        to: b?.approvedPurchaseStoreName || target, fromId: source, toId: target }
    : null;
  const reason = b?.purchaseStatus === "approved" || b?.purchaseStatus === "rejected"
    ? b.purchaseReviewReason?.trim() || null : null;
  return { suggested, requested, approvedQty, storeChange, reason,
    delta: approvedQty !== null && requested !== null ? approvedQty - requested : null,
    rejected: b?.purchaseStatus === "rejected" };
}
