import { describe, expect, it } from "vitest";
import { toListingRow } from "@/pages/products/listingManagementApi";

type Input = Parameters<typeof toListingRow>[0];

const fromRaw = (overrides: Record<string, unknown>) => toListingRow({
  id: "row-1", source_account_ref: "primary", store_id: "store-1",
  store_name: "Store", item_id: "20002021638", msku: "MSKU",
  title: "Monitor title", local_name: "ERP name", sales_30d: "5",
  sale_price_amount: "25.99", strike_price_amount: "35.99",
  calculated_at: "2026-11-04T00:00:00Z",
  ...overrides,
} as Input);

describe("Listing monitor RAW field rendering", () => {
  it("uses the successful monitor captured time instead of MART refresh time", () => {
    const row = fromRaw({ monitor_checked_at: "2026-11-03T09:56:15Z" });
    expect(row.checkedAt).toBe("2026-11-03 17:56");
  });

  it("distinguishes missing values from genuine zero/false", () => {
    const row = fromRaw({
      is_hijacked: null, average_rating: null, review_count: null,
      sale_price_amount: null, strike_price_amount: null,
      monitor_has_strikethrough: false, monitor_seller_offer_count: 0,
      monitor_image_count: 0,
    });
    expect(row.resold).toBe("待检测");
    expect(row.rating).toBeNull();
    expect(row.reviewCount).toBeNull();
    expect(row.salePrice).toBeNull();
    expect(row.listPrice).toBeNull();
    expect(row.hasStrikethrough).toBe(false);
    expect(row.sellerOfferCount).toBe(0);
    expect(row.imageCount).toBe(0);
  });

  it("supports structured seller and image arrays plus feature bullets", () => {
    const row = fromRaw({
      monitor_seller_names: ["Ritonbr"], monitor_image_urls: ["https://example.invalid/a.jpg"],
      monitor_key_features: ["F1", "F2"], monitor_review_fetch_status: "OK",
      buybox_status: "NORMAL", is_hijacked: false,
    });
    expect(row.sellerNames).toEqual(["Ritonbr"]);
    expect(row.imageUrls).toHaveLength(1);
    expect(row.keyFeatures).toEqual(["F1", "F2"]);
    expect(row.reviewFetchStatus).toBe("OK");
    expect(row.buyBoxStatus).toBe("正常");
    expect(row.resold).toBe("否");
  });
});

describe("Listing commercial exception V3", () => {
  const normal = {
    listing_status: "OFFLINE",
    wfs_available_quantity: "10",
    buybox_status: "NORMAL",
    monitor_has_strikethrough: true,
    is_hijacked: false,
  };
  it.each([
    [{}, "正常"],
    [{ wfs_available_quantity: "0", is_hijacked: true }, "—"],
    [{ wfs_available_quantity: null, buybox_status: "LOST" }, "—"],
    [{ wfs_available_quantity: "0", monitor_has_strikethrough: false }, "—"],
    [{ wfs_available_quantity: "1", is_hijacked: true }, "异常"],
    [{ monitor_has_strikethrough: false }, "异常"],
    [{ is_hijacked: true }, "异常"],
    [{ buybox_status: "LOST" }, "异常"],
    [{ buybox_status: " secondary " }, "异常"],
    [{ buybox_status: "NOT_FOUND" }, "异常"],
    [{ buybox_status: "UNAVAILABLE" }, "异常"],
    [{ buybox_status: "OUT_OF_STOCK" }, "正常"],
    [{ buybox_status: "FETCH_ERROR" }, "待确认"],
    [{ monitor_has_strikethrough: null }, "待确认"],
    [{ is_hijacked: null }, "待确认"],
    [{ buybox_status: null, is_hijacked: true }, "异常"],
  ] as const)("maps confirmed operational evidence %j to %s", (change, expected) => {
    expect(fromRaw({ ...normal, ...change }).listingStatus).toBe(expected);
  });
});
