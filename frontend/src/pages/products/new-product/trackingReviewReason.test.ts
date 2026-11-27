import { describe, expect, it } from "vitest";
import { trackingReviewReasonLength, validTrackingReviewReason } from "./trackingReviewReason";
import source from "./NewProductPages.tsx?raw";

describe("tracking review reason", () => {
  it.each(["", "  \n\t　", "123456789", "12345 6789", "123456789\u0085"])("rejects %j", value => {
    expect(validTrackingReviewReason(value)).toBe(false);
  });
  it.each(["1234567890", "12345 67890", "销量持续下降需要继续优化", "123456789😀"])("accepts %j", value => {
    expect(validTrackingReviewReason(value)).toBe(true);
  });
  it("counts code points and non-blank characters", () => {
    expect(trackingReviewReasonLength("一 二\n三😀　")).toBe(4);
  });
  it("guards both submit paths and preserves historical read-only display", () => {
    expect(source.match(/if\(!validTrackingReviewReason\(note\)\)/g)).toHaveLength(2);
    expect(source).toContain("disabled={flowSaving || !validTrackingReviewReason(note)");
    expect(source).toContain("aria-required={!reviewReadOnly}");
    expect(source).toContain('reviewReadOnly ? "仅供查看" : `');
  });
});
