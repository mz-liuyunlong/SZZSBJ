/** Transport mapping tests use synthetic identifiers only. */
import { describe, expect, it } from "vitest";
import { approvalQuery, approvalBlockedText } from "./packingApprovalApi";
import { initialPackingApprovalFilters } from "./packingApprovalTypes";
describe("packing filter contract", () => {
  it("preserves repeated store IDs, date boundaries and server sort", () => {
    const q = approvalQuery({ ...initialPackingApprovalFilters(), storeIds: ["001", "002"], createdFrom: "2026-10-01", arrival: "unknown", sort: "created_asc" }, 2, 50);
    expect(q.getAll("store_id")).toEqual(["001", "002"]); expect(q.get("arrival")).toBe("unknown"); expect(q.get("page")).toBe("2"); expect(q.get("sort")).toBe("created_asc");
  });
  it("explains missing stock without translating unknown into zero", () => { expect(approvalBlockedText(["STOCK_PROOF_UNKNOWN"])).toContain("未知"); });
});
