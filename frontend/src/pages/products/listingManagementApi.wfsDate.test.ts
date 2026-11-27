import { describe, expect, it } from "vitest";
import { toListingStartText } from "@/pages/products/listingManagementApi";

describe("WFS first-stock LA business date", () => {
  it("displays the LA inventory date without timezone conversion", () => {
    expect(toListingStartText("2026-11-01")).toBe("2026-11-01");
    expect(toListingStartText("2026-10-29")).toBe("2026-10-29");
  });

  it("leaves never-stocked Listings without a launch date", () => {
    expect(toListingStartText(null)).toBe("");
  });

  it("does not accept ERP date or China first-stock date as a fallback", () => {
    const legacyCall = toListingStartText as unknown as (
      firstWfsDateLa: string | null,
      erpDate?: string,
      launchDateCn?: string,
    ) => string;
    expect(legacyCall(null, "2026-09-04 00:00:00", "2026-11-02")).toBe("");
  });
});
