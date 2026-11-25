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
    path.split("?")[0].includes("/summary")
      ? { data: { total: 0, online: 0, listing_exception: 3, buybox_exception: 0, rating_warning: 0, resold_warning: 0, strike_price_exception: 0 } }
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

describe("Listing independent filter transport", () => {
  const filters = {
    productTagValues: ["provider,tag", "other"],
    customTagValues: ["custom"],
    lifecycleValues: ["上升期", "稳定期"],
    gradeValues: ["A", "D"],
    summaryFilter: "listing_exception",
  };
  const expected = {
    product_tag: JSON.stringify(filters.productTagValues),
    custom_tag: JSON.stringify(filters.customTagValues),
    lifecycle: "上升期,稳定期",
    grade: "A,D",
  };

  it("passes separate dimensions in GET listing, summary and export", async () => {
    await fetchListingManagementRows(filters);
    await fetchListingManagementSummary(filters);
    await exportListingManagementRows(filters);
    for (const [path] of [
      ...calls.backendRequest.mock.calls,
      ...calls.backendDownload.mock.calls,
    ]) {
      const params = Object.fromEntries(new URLSearchParams(path.split("?")[1]));
      expect(params).toMatchObject(expected);
      expect(params.tag).toBeUndefined();
    }
    expect(calls.backendRequest.mock.calls[0][0]).toContain("summary_filter=listing_exception");
    expect(calls.backendRequest.mock.calls[1][0]).not.toContain("summary_filter=");
    expect(calls.backendDownload.mock.calls[0][0]).toContain("summary_filter=listing_exception");
  });

  it("preserves dimensions through batch POST and real summary mapping", async () => {
    const args = { ...filters, batchValues: ["SKU-NEW-FILTER"] };
    await fetchListingManagementRows(args);
    const result = await fetchListingManagementSummary(args);
    await exportListingManagementRows(args);
    for (const [, init] of calls.backendRequest.mock.calls) {
      expect(JSON.parse(init.body).query).toMatchObject(expected);
    }
    expect(JSON.parse(calls.backendDownload.mock.calls[0][2].body).query).toMatchObject(expected);
    expect(result.listingException).toBe(3);
  });
});

describe("Listing statistics card query transport V2", () => {
  it.each(["total", "online", "listing_exception", "buybox", "rating", "resold", "strike"])(
    "uses the same card and scope for list and export: %s", async (summaryFilter) => {
      const params = {
        summaryFilter,
        stores: ["store-v2"],
        owners: ["owner-v2"],
        archiveStatuses: ["active"],
        productTagValues: ["provider-v2"],
        customTagValues: ["custom-v2"],
        lifecycleValues: ["稳定期"],
        gradeValues: ["D"],
        keyword: `v2-card-${summaryFilter}`,
      };
      await fetchListingManagementRows(params);
      await exportListingManagementRows(params);
      const rowQuery = new URLSearchParams(calls.backendRequest.mock.calls[0][0].split("?")[1]);
      const exportQuery = new URLSearchParams(calls.backendDownload.mock.calls[0][0].split("?")[1]);
      for (const query of [rowQuery, exportQuery]) {
        expect(query.get("summary_filter")).toBe(summaryFilter === "total" ? null : summaryFilter);
        expect(query.get("store_id")).toBe("store-v2");
        expect(query.get("owner_ref")).toBe("owner-v2");
        expect(query.get("archive_status")).toBe("active");
        expect(query.get("product_tag")).toBe(JSON.stringify(["provider-v2"]));
        expect(query.get("custom_tag")).toBe(JSON.stringify(["custom-v2"]));
        expect(query.get("lifecycle")).toBe("稳定期");
        expect(query.get("grade")).toBe("D");
      }
    },
  );
});
