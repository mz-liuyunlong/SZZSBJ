import { beforeEach, describe, expect, it, vi } from "vitest";

const calls = vi.hoisted(() => ({ backendRequest: vi.fn(), backendDownload: vi.fn() }));
vi.mock("@/api/backendApi", () => ({ backendRequest: calls.backendRequest, backendDownload: calls.backendDownload }));

import {
  exportListingManagementRows, fetchListingExactFacetOptions, fetchListingExactFacetBatchOptions,
  fetchListingManagementRows, fetchListingManagementSummary,
} from "@/pages/products/listingManagementApi";
import { listingMainFacets, listingMoreFacetGroups, listingMoreDraft, mergeListingMoreDraft, listingMoreFacetScope } from "@/pages/products/listingExactFacetLogic";

const exactFilters = { sku: ['v:"SKU,1"'], rating: ['v:"3.9950"', "n:"] };

beforeEach(() => {
  calls.backendRequest.mockReset();
  calls.backendDownload.mockReset();
  calls.backendRequest.mockImplementation((path: string) => Promise.resolve(
    path.includes("facet-options") ? { data: { options: [{ value: 'v:"SKU,1"', label: "SKU,1", count: 7 }], has_more: false } }
      : path.includes("summary") ? { data: { total: 7, online: 7, listing_exception: 1, buybox_exception: 1, rating_warning: 1, resold_warning: 0, strike_price_exception: 0 } }
      : { data: { items: [] }, meta: { page: 2, page_size: 50, total: 7, latest_calculated_at: null } },
  ));
  calls.backendDownload.mockResolvedValue(undefined);
});

describe("Listing exact-value filtering", () => {
  it("exposes 25 unique fields without duplicating the seven main facets", () => {
    const main = listingMainFacets.map(([field]) => field);
    const more = listingMoreFacetGroups.flatMap<string>(group => group.fields.map(([field]) => field));
    expect(main).toHaveLength(7);
    expect(more).toHaveLength(18);
    expect(new Set([...main, ...more]).size).toBe(25);
  });

  it("uses POST JSON and keeps exact values, pagination, batch and active card", async () => {
    await fetchListingManagementRows({ exactFilters, page: 2, summaryFilter: "listing_exception", batchValues: ["sku-a"] });
    const [path, init] = calls.backendRequest.mock.calls[0];
    expect(path).toBe("/api/listings/walmart/query");
    const body = JSON.parse(init.body);
    expect(body.batch_values).toEqual(["sku-a"]);
    expect(body.query.page).toBe("2");
    expect(body.query.summary_filter).toBe("listing_exception");
    expect(JSON.parse(body.query.exact_filters)).toEqual(exactFilters);
  });

  it("summary and export share the exact filters without changing card counts", async () => {
    await fetchListingManagementSummary({ exactFilters, summaryFilter: "rating" });
    const [path, init] = calls.backendRequest.mock.calls[0];
    expect(path).toBe("/api/listings/walmart/summary/query");
    expect(JSON.parse(JSON.parse(init.body).query.exact_filters)).toEqual(exactFilters);
    expect(JSON.parse(init.body).query.summary_filter).toBeUndefined();
    await exportListingManagementRows({ exactFilters, summaryFilter: "rating" }, ["sku"]);
    const [exportPath, , exportInit] = calls.backendDownload.mock.calls[0];
    expect(exportPath).toBe("/api/listings/walmart/export/query");
    expect(JSON.parse(exportInit.body).query.summary_filter).toBe("rating");
    expect(JSON.parse(JSON.parse(exportInit.body).query.exact_filters)).toEqual(exactFilters);
  });

  it("requests a single facet with a real count and stable pagination", async () => {
    const result = await fetchListingExactFacetOptions("sku", { exactFilters, summaryFilter: "online" }, 1000);
    const [path, init] = calls.backendRequest.mock.calls[0];
    expect(path).toBe("/api/listings/walmart/facet-options");
    const body = JSON.parse(init.body);
    expect(body.field).toBe("sku");
    expect(body.offset).toBe(1000);
    expect(body.query.summary_filter).toBe("online");
    expect(JSON.parse(body.query.exact_filters)).toEqual(exactFilters);
    expect(result.options[0].count).toBe(7);
  });
});

it("loads multiple facets through one scoped batch request", async () => {
  calls.backendRequest.mockResolvedValueOnce({ data: { items: {
    rating: { options: [{ value: 'v:"4"', label: "4", count: 6 }], has_more: false },
    brand: { options: [], has_more: false },
  } } });
  const result = await fetchListingExactFacetBatchOptions({ rating: 0, brand: 0 }, {
    exactFilters, summaryFilter: "online", batchValues: ["sku-a"],
  });
  const [path, init] = calls.backendRequest.mock.calls[0];
  expect(path).toBe("/api/listings/walmart/facet-options/batch");
  const body = JSON.parse(init.body);
  expect(body.fields).toEqual({ rating: 0, brand: 0 });
  expect(body.complete).toBe(true);
  expect(body.query.summary_filter).toBe("online");
  expect(body.batch_values).toEqual(["sku-a"]);
  expect(result.rating.options[0].count).toBe(6);
});

it("keeps applied filters untouched until draft is merged", () => {
  const applied = { store: ['v:"store-a"'], rating: ['v:"4"'], brand: ['v:"A"'] };
  const draft = listingMoreDraft(applied);
  expect(draft).toEqual({ rating: ['v:"4"'], brand: ['v:"A"'] });
  expect(mergeListingMoreDraft(applied, { rating: ['v:"3"'] })).toEqual({
    store: ['v:"store-a"'], rating: ['v:"3"'],
  });
  expect(applied.rating).toEqual(['v:"4"']);
  expect(mergeListingMoreDraft(applied, {})).toEqual({ store: ['v:"store-a"'] });
});

it("invalidates other facets but not the changed facet itself", () => {
  const a = { exactFilters: { store: ['v:"store-a"'], rating: ['v:"4"'] } };
  const b = { exactFilters: { store: ['v:"store-a"'], rating: ['v:"3"'] } };
  expect(listingMoreFacetScope(a, "rating")).toBe(listingMoreFacetScope(b, "rating"));
  expect(listingMoreFacetScope(a, "brand")).not.toBe(listingMoreFacetScope(b, "brand"));
});

it("reconstructs an opt-in compact facet label without changing its token or count", async () => {
  const label = 'Long, "quoted" 商品描述 '.repeat(10);
  const value = `v:${JSON.stringify(label)}`;
  calls.backendRequest.mockResolvedValueOnce({ data: { items: {
    keyFeatures: { options: [{ value, label: "", count: 3 }], has_more: false },
    rating: { options: [{ value: 'v:"4.0000"', label: "4", count: 6 }], has_more: false },
  } } });
  const result = await fetchListingExactFacetBatchOptions({ keyFeatures: 0, rating: 0 }, {});
  expect(result.keyFeatures.options[0]).toEqual({ value, label, count: 3 });
  expect(result.rating.options[0].label).toBe("4");
  expect(JSON.parse(calls.backendRequest.mock.calls[0][1].body).compact_labels).toBe(true);
});

it("passes the same ordered fields through GET, exact POST and CSV but not summary", async () => {
  const sorts = [{ key: "rating", direction: "asc" }, { key: "sales90Days", direction: "desc" }] as const;
  const expected = "rating:asc,sales90Days:desc";
  await fetchListingManagementRows({ sorts, page: 2, keyword: "global-sort-contract" });
  const [getPath] = calls.backendRequest.mock.calls[0];
  expect(new URLSearchParams(getPath.split("?")[1]).get("sort_by")).toBe(expected);
  await fetchListingManagementRows({ sorts, exactFilters, page: 3, keyword: "global-sort-contract" });
  const [postPath, postInit] = calls.backendRequest.mock.calls[1];
  expect(postPath).toBe("/api/listings/walmart/query");
  expect(JSON.parse(postInit.body).query.sort_by).toBe(expected);
  expect(JSON.parse(postInit.body).query.page).toBe("3");
  await exportListingManagementRows({ sorts, exactFilters }, ["sku"]);
  expect(JSON.parse(calls.backendDownload.mock.calls[0][2].body).query.sort_by).toBe(expected);
  await fetchListingManagementSummary({ sorts, keyword: "global-sort-contract" });
  const [summaryPath] = calls.backendRequest.mock.calls[2];
  expect(new URLSearchParams(summaryPath.split("?")[1]).has("sort_by")).toBe(false);
});
