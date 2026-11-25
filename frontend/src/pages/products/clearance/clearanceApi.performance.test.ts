import { describe, expect, it, vi } from "vitest";
import { listClearanceApplications } from "./clearanceApi";
import { backendRequest } from "@/api/backendApi";

vi.mock("@/api/backendApi", () => ({ backendRequest: vi.fn() }));

describe("clearance application batch requests", () => {
  it("returns backend batch fields without per-item HTTP lookups", async () => {
    const data = { items: [{ id: "one", item_id: "123", display_product_name: "Product" }], total: 1, page: 1, page_size: 100 };
    vi.mocked(backendRequest).mockResolvedValueOnce({ data, success: true, error: null, meta: null, request_id: "test" });
    expect(await listClearanceApplications(1, 100, undefined, false)).toEqual(data);
    expect(backendRequest).toHaveBeenCalledTimes(1);
    expect(vi.mocked(backendRequest).mock.calls[0][0]).toContain("include_live=false");
  });
});
