import { describe, expect, it, vi } from "vitest";
import type { ApprovalFilters } from "./approvalTypes";

vi.mock("./approvalApi", () => ({
  fetchApprovals: vi.fn(async (filters: ApprovalFilters) => ({
    data: {
      items: [{
        id: "REAL-WFS-001",
        approval_type: "wfs_case_abandon",
        status: "submitted",
      }],
    },
    meta: {
      page: filters.page,
      page_size: filters.page_size,
      total: 1,
    },
  })),
}));

import { fetchApprovals } from "./approvalApi";
import {
  demoSeeds,
  fetchWorkbenchList,
  getFilteredDemoItems,
  isDemoApproval,
} from "./approvalDemoData";

const filters: ApprovalFilters = {
  tab: "pending",
  view: "mine",
  page: 1,
  page_size: 50,
};

describe("approval workbench demo isolation", () => {
  it("provides 12 demo records with all three statuses", () => {
    expect(demoSeeds).toHaveLength(12);
    expect(new Set(demoSeeds.map((r) => r.status))).toEqual(
      new Set(["submitted", "approved", "rejected"]),
    );
  });

  it("marks demo records as non-reviewable", () => {
    const rows = getFilteredDemoItems({
      ...filters,
      approval_type: "clearance_request",
    });

    expect(rows).toHaveLength(1);
    expect(isDemoApproval(rows[0])).toBe(true);
    expect(rows[0].can_review).toBe(false);
  });

  it("never queries the backend for demo-only business", async () => {
    vi.mocked(fetchApprovals).mockClear();

    const data = await fetchWorkbenchList({
      ...filters,
      approval_type: "price_adjustment",
    });

    expect(data.meta.total).toBe(1);
    expect(fetchApprovals).not.toHaveBeenCalled();
  });

  it("preserves the original WFS request", async () => {
    vi.mocked(fetchApprovals).mockClear();

    const request = {
      ...filters,
      approval_type: "wfs_case_abandon",
    };

    const result = await fetchWorkbenchList(request);

    expect(fetchApprovals).toHaveBeenCalledWith(request);
    expect(result.data.items[0].id).toBe("REAL-WFS-001");
  });

  it("combines real WFS and demo rows only in All", async () => {
    const result = await fetchWorkbenchList(filters);

    expect(result.meta.total).toBe(5);
    expect(result.data.items[0].id).toBe("REAL-WFS-001");
    expect(result.data.items.slice(1).every(isDemoApproval)).toBe(true);
  });
});
