/** Tracking range uses the existing list contract, not a second data request. */
import { describe, expect, it, vi } from "vitest";
import { backendRequest } from "@/api/backendApi";
import { listTrackingProducts, type TrackingListParams } from "./newProductBusinessApi";

vi.mock("@/api/backendApi", () => ({ backendRequest: vi.fn(), backendDownload: vi.fn() }));
const base: TrackingListParams = {
  page: 1, page_size: 50, keyword: "", owners: "", grades: "", outcome: "all", period: 30,
};
const requested = () => new URL(vi.mocked(backendRequest).mock.calls.at(-1)![0], "https://test.invalid");

describe("tracking date range API", () => {
  it("sends both inclusive date endpoints with other filters in one request", async () => {
    vi.mocked(backendRequest).mockClear().mockResolvedValue({ data: { items: [] } } as never);
    await listTrackingProducts({ ...base, from: "2026-11-01", to: "2026-11-25", drill_kind: "category", drill_value: "Kitchen" });
    const url = requested();
    expect(url.pathname).toBe("/api/new-products/tracking/listings");
    expect(url.searchParams.get("from")).toBe("2026-11-01");
    expect(url.searchParams.get("to")).toBe("2026-11-25");
    expect(url.searchParams.get("period")).toBe("30");
    expect(url.searchParams.get("drill_value")).toBe("Kitchen");
    expect(backendRequest).toHaveBeenCalledTimes(1);
  });
  it("omits dates when the range is cleared", async () => {
    vi.mocked(backendRequest).mockClear().mockResolvedValue({ data: { items: [] } } as never);
    await listTrackingProducts({ ...base, from: undefined, to: undefined });
    expect(requested().searchParams.has("from")).toBe(false);
    expect(requested().searchParams.has("to")).toBe(false);
    expect(backendRequest).toHaveBeenCalledTimes(1);
  });
});
