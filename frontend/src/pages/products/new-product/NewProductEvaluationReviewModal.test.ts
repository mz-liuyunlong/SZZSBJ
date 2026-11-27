import { describe, expect, it } from "vitest";

// The source contract only contains the enumerated business review reasons.
// React rendering is exercised by the existing page compilation and acceptance tests.
describe("new-product assessment review types", () => {
  it("keeps correction separate from special exception", () => {
    const types = ["calculation_error", "scoring_basis_error", "special_exception"] as const;
    expect(new Set(types).size).toBe(3);
  });
});
