import { describe, expect, it } from "vitest";
import { parseFollowLog } from "./followLog";
import { approvalColumnFields, approvalTabs, statusNames } from "./approvalTypes";

describe("approval workbench", () => {
 it("lists legacy WFS only under pending, retaining its unverified status", () => {
  expect(approvalTabs.map((tab) => tab.value)).toEqual(["pending", "approved", "rejected"]);
  expect(statusNames.legacy_unverified).toBe("历史待核验");
 });
 it("retains entire ordered legacy follow history", () => {
  const original = "10-01 09:00 第1次跟进：申请\n\n10-07 18:00 第2次跟进：追问结果";
  expect(parseFollowLog(original)).toEqual([
   "10-01 09:00 第1次跟进：申请",
   "10-07 18:00 第2次跟进：追问结果",
  ]);
 });
 it("keeps the three state views and high-density table fields", () => {
  expect(statusNames.submitted).toBe("待审批");
  expect(statusNames.approved).toBe("已审批");
  expect(statusNames.rejected).toBe("已驳回");
  expect(approvalColumnFields.find((x) => x.key === "title")).toBeTruthy();
 });
});
