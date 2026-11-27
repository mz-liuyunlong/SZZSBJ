import { describe, expect, it, vi } from "vitest";
import type { ApprovalItem } from "./approvalTypes";
vi.mock("./approvalApi", () => ({}));
vi.mock("@/pages/products/clearance/clearanceApi", () => ({}));
import { canBatchApprove, pendingBatchRow, validBatchRow } from "./batchApproval";
const make = (patch: Partial<ApprovalItem> = {}): ApprovalItem => ({
  id:"123", version:1, approval_type:"clearance_request", business_ref:"x", title:"Test",
  source_account_ref:"account", applicant_id:"51", status:"submitted", risk_level:"unknown",
  amount:null, currency_code:null, submitted_at:null, reviewed_at:null, reviewed_by:null,
  reason:"test", can_review:true, requires_verification:false, ...patch,
});
describe("unified batch eligibility", () => {
  it("accepts real pending supported kinds under existing permissions", () => {
    for (const type of ["clearance_request","new_product_purchase","new_product_evaluation_review",
      "wfs_case_abandon","purchase_exception","finance_exception","operations_plan_ack","access_change"]) {
      expect(canBatchApprove(make({approval_type:type}),["*"])).toBe(true);
    }
  });
  it("does not allow demos, unconnected kinds, or unauthorized and completed rows", () => {
    for (const patch of [{id:"DEMO-1"},{approval_type:"price_adjustment"},{approval_type:"listing_archive"},
      {can_review:false},{status:"approved" as const},{requires_verification:true}]) {
      expect(canBatchApprove(make(patch),["*"])).toBe(false);
    }
    expect(canBatchApprove(make({approval_type:"new_product_purchase"}),[])).toBe(false);
  });
  it("requires explicit confirmation and verified purchase data", () => {
    const row = make({approval_type:"new_product_purchase"});
    const entry = {...pendingBatchRow(row), detail:{...row,snapshot:{},evidence:null,current_case:null,
      data_changed:false,can_supplement:false,events:[]}, confirmed:true, stores:[{store_id:"s",store_name:"S"}],storeId:"s",quantity:2};
    expect(validBatchRow(entry)).toBe(true);
    expect(validBatchRow({...entry,quantity:0})).toBe(false);
    expect(validBatchRow({...entry,storeId:"wrong"})).toBe(false);
    expect(validBatchRow({...entry,confirmed:false})).toBe(false);
  });
});
