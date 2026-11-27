import { describe, expect, it } from "vitest";
import { appendSalesReportSort, dailySalesSortFields, nextSalesReportSort, orderProfitSortFields } from "./reportSort";

describe("sales report single-column server sort", () => {
  for (const fields of [dailySalesSortFields, orderProfitSortFields]) {
    it(`switches and clears all ${Object.keys(fields).length} sortable columns`, () => {
      for (const field of Object.values(fields)) {
        const first = nextSalesReportSort(null, field);
        expect(first).toEqual({ field, direction: "asc" });
        const descending = nextSalesReportSort(first, field);
        expect(descending).toEqual({ field, direction: "desc" });
        expect(nextSalesReportSort(descending, field)).toBeNull();
        for (const second of Object.values(fields)) {
          if (second === field) continue;
          expect(nextSalesReportSort(first, second)).toEqual({ field: second, direction: "asc" });
        }
      }
    });
  }
  it("keeps non-sort queries free of sort parameters", () => {
    const search = new URLSearchParams();
    appendSalesReportSort(search, null, "USD");
    expect(search.toString()).toBe("");
    appendSalesReportSort(search, {field: "sales_amount", direction: "desc"}, "CNY");
    expect(Object.fromEntries(search)).toEqual({sort_field: "sales_amount", sort_direction: "desc", sort_currency: "CNY"});
  });
});

it("does not sort product identity, SKU, owner or store", () => {
  expect(Object.keys(dailySalesSortFields)).toHaveLength(30);
  expect(Object.keys(orderProfitSortFields)).toHaveLength(31);

  for (const key of [
    "store", "owner", "mskuProductId", "skuProductName",
    "productIdName", "skuMsku",
  ]) {
    expect(dailySalesSortFields[key]).toBeUndefined();
    expect(orderProfitSortFields[key]).toBeUndefined();
  }
});
