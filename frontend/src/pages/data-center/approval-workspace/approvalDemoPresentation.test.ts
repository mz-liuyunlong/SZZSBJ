import { describe, expect, it } from "vitest";
import { demoColumnsForBusiness, demoProfiles } from "./approvalDemoPresentation";
import { demoSeeds } from "./approvalDemoData";

const keys = (business: "purchase" | "clearance" | "listing" | "price") =>
  demoColumnsForBusiness(business, () => {})?.map((col) => col.key);

describe("V3 dedicated demo list columns and detail profiles", () => {
  it("uses different V3 columns for each business", () => {
    expect(keys("purchase")).toEqual(["title", "supplier", "qty", "due", "amount", "risk", "applicant", "status", "action"]);
    expect(keys("clearance")).toEqual(["title", "store", "qty", "methods", "amount", "risk", "applicant", "submitted", "status", "action"]);
    expect(keys("listing")).toEqual(["title", "item", "sku", "store", "listingStatus", "risk", "applicant", "submitted", "status", "action"]);
    expect(keys("price")).toEqual(["title", "sku", "oldPrice", "newPrice", "priceDelta", "priceMargin", "risk", "applicant", "status", "action"]);
  });
  it("never replaces the shared All view or real WFS table", () => {
    expect(demoColumnsForBusiness("wfs", () => {})).toBeNull();
    expect(demoColumnsForBusiness("all", () => {})).toBeNull();
  });
  it("has complete distinct business snapshots for the 12 demo records", () => {
    expect(demoSeeds).toHaveLength(12);
    for (const seed of demoSeeds) {
      expect(demoProfiles[seed.id]).toBeDefined();
      expect(demoProfiles[seed.id].kind).toBe(
        seed.approval_type === "purchase_exception" ? "purchase" :
          seed.approval_type === "clearance_request" ? "clearance" :
            seed.approval_type === "listing_archive" ? "listing" : "price",
      );
    }
    expect(demoProfiles["DEMO-CLR-001"].clearanceSkus).toHaveLength(2);
    expect(demoProfiles["DEMO-CLR-001"].clearanceSkus?.[0].sales).toHaveLength(3);
    expect(demoProfiles["DEMO-PRC-003"].newMargin).toBeLessThan(0);
  });
});

