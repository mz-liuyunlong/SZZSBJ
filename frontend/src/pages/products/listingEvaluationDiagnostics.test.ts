import { describe, expect, it } from "vitest";

import {
  applyListingEvaluationPreview,
  withPendingListingDiagnostics,
  type ListingEvaluationPreviewResult,
} from "@/pages/products/listingManagementApi";
import type { ListingManagementRow } from "@/pages/products/listingManagementData";

const listing = {
  id: "00000000-0000-0000-0000-000000000001",
  lifecycle: "待判定",
  productGrade: "未分级",
  wfsAvailableInventory: 12,
} as ListingManagementRow;

const preview: ListingEvaluationPreviewResult = {
  listing_id: listing.id,
  cutoff_la: "2026-11-03",
  current_lifecycle: null,
  current_grade: null,
  lifecycle_candidate: null,
  lifecycle_evidence_reason: "HISTORICAL_FIRST_WFS_NOT_LAUNCH_VERIFIED",
  first_positive_date_la: "2026-09-16",
  cutoff_wfs_available_quantity: "12",
  consecutive_low_stock_days: 0,
  grade_candidate: "B",
  valid_short: 6,
  valid_medium: 11,
  weighted_margin_percent: "12.5",
  valid_stock_days_30: 18,
  observed_stock_days_7: 7,
  low_stock_days_7: 0,
  prior_effective_stock: true,
  currently_archived: false,
  rule_version: 2,
  missing_evidence: ["ADS_COST_PUBLICATION_PROOF_MISSING"],
  published: false,
};

describe("production Listing diagnostics", () => {
  it("always provides an explanation icon even when preview API is disabled", () => {
    const row = withPendingListingDiagnostics(listing);
    expect(row.lifecycleDiagnostic?.reasonCode).toBe("PREVIEW_NOT_AVAILABLE");
    expect(row.gradeDiagnostic?.sourceVerified).toBe(false);
  });

  it("explains historical WFS evidence without claiming this is not WFS", () => {
    const row = applyListingEvaluationPreview(listing, preview);
    expect(row.lifecycle).toBe("待判定");
    expect(row.lifecycleDiagnostic?.reasonCode).toBe("HISTORICAL_LAUNCH_UNVERIFIED");
    expect(row.lifecycleDiagnostic?.evidence).toContainEqual({
      label: "历史首次有货观测",
      value: "2026-09-16",
    });
    expect(row.lifecycleDiagnostic?.ruleVersion).toBe(2);
  });

  it("shows unpublished grade candidates without claiming a persisted rating", () => {
    const row = applyListingEvaluationPreview(listing, preview);
    expect(row.productGrade).toBe("未分级");
    expect(row.gradeDiagnostic?.candidate).toBe("B");
    expect(row.gradePreviewCandidate).toBe(true);
    expect(row.gradeDiagnostic?.sourceVerified).toBe(false);
    expect(row.gradeDiagnostic?.reason).toMatch(/未发布/);
  });

  it("never overwrites a stored published grade with a diagnostic candidate", () => {
    const row = applyListingEvaluationPreview(
      { ...listing, productGrade: "A", lifecycle: "稳定期" },
      { ...preview, lifecycle_candidate: "上升期" },
    );
    expect(row.productGrade).toBe("A");
    expect(row.lifecycle).toBe("稳定期");
    expect(row.gradePreviewCandidate).toBe(false);
    expect(row.lifecycleDiagnostic?.candidateStage).toBe("上升期");
  });

  it("ignores evidence for another Listing", () => {
    expect(applyListingEvaluationPreview(listing, { ...preview, listing_id: "other" }))
      .toEqual(listing);
  });
});
