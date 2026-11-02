import { describe, expect, it } from "vitest";
import { safeListingImageUrls, toListingRow, toListingStartText } from "@/pages/products/listingManagementApi";
import { listingColumnFields } from "@/pages/products/listingManagementData";

describe("toListingStartText", () => {
  it("shows only the first observed WFS stock date", () => {
    expect(toListingStartText("2026-09-08")).toBe("2026-09-08");
    expect(toListingStartText(null)).toBe("");
    expect(toListingStartText(undefined)).toBe("");
  });

  it("does not use an ERP date when no first WFS stock was observed", () => {
    const item = {
      launch_date_cn: null,
      listing_start_at_utc: "2026-09-08T16:31:47Z",
      listing_start_source_raw: "2026-09-01 12:00:00",
      calculated_at: "2026-09-09T00:00:00Z",
    } as Parameters<typeof toListingRow>[0];
    expect(toListingRow(item).listedAt).toBe("");
    expect(toListingRow({ ...item, launch_date_cn: "2026-09-10" }).listedAt).toBe("2026-09-10");
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
