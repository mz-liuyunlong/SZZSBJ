import { describe, expect, it } from "vitest";
import { approvalBusinesses, approvalBusinessByKey, approvalBusinessLabel } from "./approvalBusiness";
describe("V3 approval business registry",()=>{
 it("contains the seven approved business families plus all",()=>{
  expect(approvalBusinesses.map(x=>x.key)).toEqual(["all","purchase","wfs","clearance","listing","disposal","price","finance"]);
 });
 it("preserves WFS-only columns and does not pretend unsupported types are live",()=>{
  expect(approvalBusinessByKey.wfs.columns).toContain("follow_log");
  expect(approvalBusinessByKey.clearance.live).toBe(false);
  expect(approvalBusinessByKey.listing.live).toBe(false);
  expect(approvalBusinessByKey.disposal.live).toBe(false);
  expect(approvalBusinessByKey.price.live).toBe(false);
  expect(approvalBusinessLabel("wfs_case_abandon")).toBe("WFS异常费用");
 });
});
