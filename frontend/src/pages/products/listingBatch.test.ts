import { describe, expect, it } from "vitest";
import { failedBatchIds, runListingBatch } from "@/pages/products/listingBatch";

describe("Listing batch requests", () => {
  it("limits concurrency, reports progress, and keeps only failed rows for retry", async () => {
    const rows = Array.from({ length: 12 }, (_, index) => ({ id: `synthetic-${index}` }));
    const progress: number[] = [];
    let active = 0;
    let maximumActive = 0;

    const results = await runListingBatch(rows, async (row) => {
      active += 1;
      maximumActive = Math.max(maximumActive, active);
      await new Promise((resolve) => setTimeout(resolve, 1));
      active -= 1;
      if (row.id === "synthetic-3" || row.id === "synthetic-8") throw new Error("synthetic failure");
    }, (completed) => progress.push(completed));

    expect(maximumActive).toBeLessThanOrEqual(5);
    expect(progress).toEqual([5, 10, 12]);
    expect(results.filter((result) => result.status === "fulfilled")).toHaveLength(10);
    expect(failedBatchIds(rows, results)).toEqual(["synthetic-3", "synthetic-8"]);
  });
});
