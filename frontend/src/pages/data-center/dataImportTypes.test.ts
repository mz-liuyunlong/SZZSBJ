import { describe, expect, it } from "vitest";
import { dataImportRecords, dataImportTypes } from "@/pages/data-center/dataImportMockData";
import { createInitialDataImportFilters } from "@/pages/data-center/dataImportTypes";

describe("data import mock data", () => {
  it("provides six import types from the prototype", () => {
    expect(dataImportTypes.map((type) => type.name)).toEqual([
      "沃尔玛广告费用",
      "沃尔玛广告账单",
      "沃尔玛自动广告",
      "竞品文案信息",
      "卖家精灵关键词",
      "竞品图片分析表",
    ]);
  });

  it("uses exactly 100 upload records for table acceptance", () => {
    expect(dataImportRecords).toHaveLength(100);
  });

  it("creates empty filters by default", () => {
    expect(createInitialDataImportFilters()).toMatchObject({
      quickRange: "all",
      startDate: "",
      endDate: "",
      typeName: "",
      status: "",
      keyword: "",
    });
  });
});
