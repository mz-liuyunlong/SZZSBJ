import { describe, expect, it } from "vitest";
import originalWorkspace from "./ApprovalWorkspacePage.tsx?raw";
import originalDrawer from "./components/DemoApprovalDrawer.tsx?raw";
import originalColumns from "./approvalDemoPresentation.tsx?raw";

describe("approval original clearance UI contract", () => {
  it("reuses the original clearance columns and drawer", () => {
    expect(originalWorkspace).toContain("demoColumnsForBusiness(business, setSelected");
    expect(originalWorkspace).toContain("<DemoApprovalDrawer");
    expect(originalWorkspace).not.toContain("<ClearanceReviewDrawer");
    expect(originalColumns).toContain("approval-clearance-cell");
    expect(originalDrawer).toContain("approval-demo__clearance-main");
    expect(originalDrawer).toContain("approval-demo__clearance-action-modal");
  });
  it("does not submit fake decisions for real clearance records", () => {
    expect(originalDrawer).toContain("if (isLive) return;");
    expect(originalDrawer).toContain("disabled={isLive || clearanceStatus");
    expect(originalWorkspace).toContain('item.approval_type === "clearance_request" && !isDemoApproval(item)');
    expect(originalWorkspace).toContain("setClearanceTableAction");
    expect(originalColumns).toContain('onAction?.(row,"approve")');
  });
});
