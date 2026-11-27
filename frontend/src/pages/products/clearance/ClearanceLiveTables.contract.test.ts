import { describe, expect, it } from "vitest";
import liveSource from "./ClearanceLiveTables.tsx?raw";
import { ANALYSIS_FIELDS, MANAGEMENT_FIELDS } from "./clearanceUiConfig";


describe("Clearance original header/UI contract over live data", () => {
  it("preserves the approved 21 analysis and 16 management columns", () => {
    expect(ANALYSIS_FIELDS).toHaveLength(21);
    expect(MANAGEMENT_FIELDS).toHaveLength(16);
    expect(ANALYSIS_FIELDS.map(([key])=>key)).toEqual([
      "identity","sku","store","risk","source","wfs","age","coverage","stockCost","price",
      "daily","revenue","ads","adRate","profit","profitRate","returns","rating","units","status","action",
    ]);
    expect(MANAGEMENT_FIELDS.map(([key])=>key)).toEqual([
      "identity","sku","store","source","reason","method","goal","sold","revenue","progress",
      "cost","plannedStart","due","status","submitted","action",
    ]);
  });
  it("uses original grouped ProTable headers instead of new AntD plain table columns", () => {
    expect(liveSource).toContain("ANALYSIS_FIELDS");
    expect(liveSource).toContain("MANAGEMENT_FIELDS");
    expect(liveSource).toContain('name:"销售表现"');
    expect(liveSource).toContain('name:"广告表现"');
    expect(liveSource).toContain('name:"利润表现"');
    expect(liveSource).toContain("clearance-metric-group-header");
    expect(liveSource).toContain("ResizableColumnTitle");
    expect(liveSource).not.toContain("CLEARANCE_PRODUCTS");
    expect(liveSource).not.toContain("localStorage");
  });
});
