import { describe, expect, it } from "vitest";
import { makeNewProductDevMockRows } from "./newProductDevelopmentFixtures";
import { samples } from "./nativeData";

describe("PR337 local Product fixture consistency", () => {
  const rows = makeNewProductDevMockRows(samples);
  it("generates unique real-schema IDs and 20 distinct category/developer groups", () => {
    expect(rows).toHaveLength(100);
    expect(new Set(rows.map((x) => x.id)).size).toBe(100);
    expect(new Set(rows.map((x) => x.item)).size).toBe(100);
    expect(new Set(rows.map((x) => x.category)).size).toBe(20);
    expect(new Set(rows.map((x) => x.developer)).size).toBe(20);
  });
  it("has >=20 actionable overdue score reminders, all from the same Product source", () => {
    const due = rows.filter((x) => x.market === null && x.days >= 30);
    expect(due.length).toBeGreaterThanOrEqual(20);
    expect(due.every((x) => x.status === "待市场评分")).toBe(true);
  });
  it("keeps the unchanged seven original demo products for legacy tests", () => {
    expect(samples).toHaveLength(7);
  });
});
