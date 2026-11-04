import * as XLSX from "xlsx";
import { describe, expect, it } from "vitest";
import { syntheticExport } from "@/pages/pmc/overview/overviewFixtures";
import { buildOverviewWorkbook, overviewWorkbookFilename } from "@/pages/pmc/overview/overviewWorkbook";

describe("overview workbook", () => {
  it("has the five 8088 sheets and a totals row", () => {
    const wb = buildOverviewWorkbook(syntheticExport, "全部");
    expect(wb.SheetNames).toEqual(["汇总", "ItemID总看板明细", "店铺×SKU明细", "仓库分布", "说明"]);
    const summary = XLSX.utils.sheet_to_json<unknown[]>(wb.Sheets["汇总"], { header: 1 });
    expect(summary.at(-1)?.[0]).toBe("合计");
    const items = XLSX.utils.sheet_to_json<unknown[]>(wb.Sheets["ItemID总看板明细"], { header: 1 });
    // title, note, blank, heads, 1 row; 国内仓可用 = domestic − lock
    expect(items[3]?.[9]).toBe("国内仓可用");
    expect(items[4]?.[0]).toBe("1001");
    expect(items[4]?.[9]).toBe(3);
  });

  it("names the file after the data day", () => {
    expect(overviewWorkbookFilename("2026-11-02", false)).toBe("PMC总看板_20261102_筛选.xlsx");
  });
});
