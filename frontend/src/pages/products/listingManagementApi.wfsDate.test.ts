import { describe, expect, it } from "vitest";
import { toListingStartText } from "@/pages/products/listingManagementApi";

const legacyToListingStartText = toListingStartText as unknown as (
  normalizedValue: string | null,
  sourceRawValue?: string | null,
  launchDateCn?: string | null,
) => string;

describe("toListingStartText", () => {
  it("uses only MART listing_start_at_utc as date-only text", () => {
    expect(toListingStartText("2026-09-08T16:31:47Z")).toBe("2026-09-08");
    expect(toListingStartText("2026-09-08")).toBe("2026-09-08");
    expect(toListingStartText(null)).toBe("");
  });

  it("does not fall back to raw source dates or WFS launch dates", () => {
    expect(legacyToListingStartText(null, null, "2026-10-14")).toBe("");
    expect(legacyToListingStartText(null, "2026-09-01 12:00:00", "2026-10-14")).toBe("");
    expect(legacyToListingStartText(null, "2026-08-21 07:31:00")).toBe("");
  });
});
