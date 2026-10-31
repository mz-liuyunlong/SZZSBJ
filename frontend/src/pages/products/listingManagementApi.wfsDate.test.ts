import { describe, expect, it } from "vitest";
import { safeListingImageUrls, toListingStartText } from "@/pages/products/listingManagementApi";
import { listingColumnFields } from "@/pages/products/listingManagementData";

describe("toListingStartText", () => {
  it("uses normalized UTC date when reliable normalized time exists", () => {
    expect(toListingStartText("2026-09-08T16:31:47Z")).toBe("2026-09-08");
    expect(toListingStartText("2026-09-08")).toBe("2026-09-08");
    expect(toListingStartText(null)).toBe("");
    expect(toListingStartText("2026-09-09T00:31:47+08:00")).toBe("2026-09-08");
    expect(toListingStartText("2026-09-08")).toBe("2026-09-08");
  });

  it("shows the raw date prefix without parsing or using WFS launch evidence", () => {
    expect(toListingStartText(null, "2026-09-01 12:00:00")).toBe("2026-09-01");
    expect(toListingStartText(null, "2026-08-21")).toBe("2026-08-21");
    expect(toListingStartText(null, null)).toBe("");
    expect(toListingStartText(null, "unverified")).toBe("unverified");
    expect(toListingStartText("2026-09-08T16:31:47Z", "2026-08-21")).toBe("2026-09-08");
  });
});


describe("Listing sales-window contract", () => {
  it("labels the 30-day backend sales metric as 30-day sales", () => {
    const field = listingColumnFields.find((item) => item.key === "sales30Days");
    expect(field?.title).toBe("近30天销量");
    expect(listingColumnFields.map((item) => String(item.key))).not.toContain("sales90Days");
  });
});

describe("monitor image URL boundary", () => {
  it("shows only secure image URLs from monitor evidence", () => {
    expect(safeListingImageUrls([
      "https://example.invalid/photo.jpg",
      "http://example.invalid/insecure.jpg",
      "javascript:alert(1)",
      null,
    ])).toEqual(["https://example.invalid/photo.jpg"]);
  });
});
