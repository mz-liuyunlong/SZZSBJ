import { beforeEach, describe, expect, it, vi } from "vitest";

const calls = vi.hoisted(() => ({
  backendRequest: vi.fn(),
  backendDownload: vi.fn(),
}));

vi.mock("@/api/backendApi", () => ({
  backendRequest: calls.backendRequest,
  backendDownload: calls.backendDownload,
}));

import {
  exportListingManagementRows,
  fetchListingManagementRows,
  fetchListingManagementSummary,
} from "@/pages/products/listingManagementApi";

beforeEach(() => {
  calls.backendRequest.mockReset();
  calls.backendDownload.mockReset();
  calls.backendRequest.mockImplementation((path: string) => Promise.resolve(
    path.includes("summary")
      ? { data: { total: 0, online: 0, buybox_exception: 0, rating_warning: 0, resold_warning: 0, strike_price_exception: 0 } }
      : { data: { items: [] }, meta: { page: 1, page_size: 50, total: 0, latest_calculated_at: null } },
  ));
  calls.backendDownload.mockResolvedValue(undefined);
});

describe("Listing 1000-item batch-search transport", () => {
  const values = Array.from({ length: 1000 }, (_, i) => `SKU-${String(i).padStart(4, "0")}-${"x".repeat(116)}`);

  it("uses POST JSON with 1000 values and preserves pagination", async () => {
    await fetchListingManagementRows({ batchValues: values, page: 3, pageSize: 50, searchType: "sku" });
    const [path, init] = calls.backendRequest.mock.calls[0];
    expect(path).toBe("/api/listings/walmart/batch-search");
    expect(init.method).toBe("POST");
    const payload = JSON.parse(init.body);
    expect(payload.batch_values).toEqual(values);
    expect(payload.query.page).toBe("3");
    expect(payload.query.page_size).toBe("50");
    expect(payload.query.batch_values).toBeUndefined();
  });

  it("keeps matching summary in the same POST batch", async () => {
    await fetchListingManagementSummary({ batchValues: values, searchType: "sku" });
    const [path, init] = calls.backendRequest.mock.calls[0];
    expect(path).toBe("/api/listings/walmart/summary/batch-search");
    expect(JSON.parse(init.body).batch_values).toHaveLength(1000);
  });

  it("exports the exact batch by POST without query-string identifiers", async () => {
    await exportListingManagementRows({ batchValues: values, searchType: "sku" }, ["sku", "msku"]);
    const [path, filename, init] = calls.backendDownload.mock.calls[0];
    expect(path).toBe("/api/listings/walmart/export/batch-search");
    expect(filename).toBe("listing-management-export.csv");
    expect(JSON.parse(init.body).batch_values).toHaveLength(1000);
    expect(JSON.parse(init.body).columns).toEqual(["sku", "msku"]);
  });

  it("does not change GET requests without a batch", async () => {
    await fetchListingManagementRows({ keyword: "coffee", searchType: "sku" });
    const [path, init] = calls.backendRequest.mock.calls[0];
    expect(path).toContain("/api/listings/walmart?");
    expect(path).toContain("keyword=coffee");
    expect(init).toBeUndefined();
  });
});
