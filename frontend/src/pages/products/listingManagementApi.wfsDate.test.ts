import { describe, expect, it } from "vitest";
import { toListingStartText } from "./listingManagementApi";

describe("Listing China first WFS stock date", () => {
  it("uses the exact China calendar date without browser timezone conversion", () => {
    expect(toListingStartText(null, null, "2026-10-14")).toBe("2026-10-14");
    expect(toListingStartText(null, "2026-09-01 12:00:00", "2026-10-14")).toBe("2026-10-14");
  });

  it("preserves an existing verified legacy MART date", () => {
    expect(
      toListingStartText("2026-09-01T12:00:00+00:00", "2026-08-21", "2026-10-14"),
    ).toBe("2026-09-01");
  });

  it("retains the existing raw source fallback for old rows", () => {
    expect(toListingStartText(null, "2026-08-21 07:31:00")).toBe("2026-08-21");
    expect(toListingStartText(null, "")).toBe("");
  });
});
