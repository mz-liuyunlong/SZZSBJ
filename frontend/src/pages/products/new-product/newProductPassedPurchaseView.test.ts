import { describe, expect, it } from "vitest";
import type { Product } from "./newProductModel";
import { passedPurchaseView } from "./newProductPassedPurchaseView";

const row = (status: string, extra: Record<string, unknown> = {}) => ({
  requestQty: 200, actualQty: 999, storeName: "2601",
  backend: { purchaseId: "p1", purchaseStatus: status, suggestedQty: 300,
    purchaseSuggestedQty: 200, purchaseSourceStoreId: "s1", ...extra },
} as unknown as Product);
describe("passed purchase view", () => {
  it("shows original snapshot and quantity decrease and store change", () => {
    const v = passedPurchaseView(row("approved", {purchaseApprovedQty:150,approvedPurchaseStoreId:"s2",approvedPurchaseStoreName:"2603",purchaseReviewReason:"批准原因"}));
    expect(v).toMatchObject({suggested:200,requested:200,approvedQty:150,delta:-50,reason:"批准原因",storeChange:{from:"2601",to:"2603"}});
  });
  it("highlights increase but not unchanged store or quantity", () => {
    expect(passedPurchaseView(row("approved", {purchaseApprovedQty:250,approvedPurchaseStoreId:"s1"}))).toMatchObject({delta:50,storeChange:null});
    expect(passedPurchaseView(row("approved", {purchaseApprovedQty:200}))).toMatchObject({delta:0,storeChange:null,reason:null});
  });
  it("does not infer missing approvals or use stale tracking quantity", () => {
    expect(passedPurchaseView(row("approved"))).toMatchObject({approvedQty:null,delta:null,storeChange:null});
    expect(passedPurchaseView(row("submitted", {purchaseApprovedQty:100,approvedPurchaseStoreId:"s2",purchaseReviewReason:"stale"}))).toMatchObject({approvedQty:null,storeChange:null,reason:null});
    expect(passedPurchaseView(row("rejected", {purchaseReviewReason:"驳回原因"}))).toMatchObject({reason:"驳回原因",rejected:true,approvedQty:null});
    expect(passedPurchaseView(row("", {purchaseId:null}))).toMatchObject({suggested:300,requested:null,approvedQty:null});
  });
});
