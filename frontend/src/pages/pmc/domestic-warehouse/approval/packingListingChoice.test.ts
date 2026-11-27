import { describe, expect, it } from "vitest";
import { listingChoiceLabel, listingSkuMismatchText, type ListingChoice } from "./packingApprovalApi";

const choice = (patch: Partial<ListingChoice>): ListingChoice => ({
  store_id: "S1",
  store_name: "Store One",
  item_id: "11111111111",
  gtin: null,
  msku: null,
  listing_version: "v1",
  cross_store: false,
  ...patch,
});

describe("target Listing options (#288 P2-2)", () => {
  it("marks a Listing whose local SKU differs from the row SKU", () => {
    expect(listingChoiceLabel(choice({}))).toBe("Store One / 11111111111");
    expect(listingChoiceLabel(choice({ sku_mismatch: true, local_sku: "YC9" }))).toBe("Store One / 11111111111（SKU 不一致）");
    expect(listingChoiceLabel(choice({ cross_store: true, sku_mismatch: true }))).toBe("Store One / 11111111111（跨店铺）（SKU 不一致）");
  });

  it("says why the Listing cannot be used and names both SKUs", () => {
    const text = listingSkuMismatchText(choice({ sku_mismatch: true, local_sku: "YC9" }), "YC1");
    expect(text).toContain("本地 SKU 是 YC9，不是本行 SKU YC1");
    expect(text).toContain("不能用于本打包单");
  });
});
