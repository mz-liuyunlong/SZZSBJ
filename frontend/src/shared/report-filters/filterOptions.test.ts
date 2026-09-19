import { describe, expect, it } from "vitest";
import {
  mergeSelectedFilterOptions,
  mergeSelectedFilterValues,
  normalizeReportFilterOptions,
  selectedValuesFromFilterValue,
} from "@/shared/report-filters/filterOptions";

describe("report filter options", () => {
  it("normalizes duplicate and empty options", () => {
    expect(normalizeReportFilterOptions([
      { value: " Walmart ", label: "" },
      { value: "Walmart", label: "Walmart duplicate", count: 99 },
      { value: "", label: "empty" },
      { value: "TEMU", label: "TEMU", count: 2 },
    ])).toEqual([
      { value: "Walmart", label: "Walmart" },
      { value: "TEMU", label: "TEMU", count: 2 },
    ]);
  });

  it("keeps selected values even when cascaded options no longer include them", () => {
    expect(mergeSelectedFilterOptions(
      ["张三", "李四"],
      [{ value: "张三", label: "张三", count: 12 }],
    )).toEqual([
      { value: "张三", label: "张三", count: 12 },
      { value: "李四", label: "李四（已选）", count: 0 },
    ]);
  });

  it("returns selected value arrays for legacy callers", () => {
    expect(mergeSelectedFilterValues(
      ["A"],
      [{ value: "B", label: "B", count: 1 }],
    )).toEqual(["B", "A"]);
  });

  it("normalizes select values", () => {
    expect(selectedValuesFromFilterValue([" A ", "", "B"])).toEqual(["A", "B"]);
    expect(selectedValuesFromFilterValue(" A ")).toEqual(["A"]);
    expect(selectedValuesFromFilterValue(undefined)).toEqual([]);
  });
});
