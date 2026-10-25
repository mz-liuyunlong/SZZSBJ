import { describe, expect, it, vi, beforeEach } from "vitest";

const backendRequestMock = vi.hoisted(() => vi.fn());
vi.mock("@/api/backendApi", () => ({ backendRequest: backendRequestMock }));

import { fetchListingGradeRule, fetchListingGradeRuleHistory, saveListingGradeRule } from "@/pages/products/listingRuleConfigApi";

const config = {
  short_days: 7, medium_days: 14,
  short_weight_percent: 60, medium_weight_percent: 40,
  short_min_valid_days: 4, medium_min_valid_days: 8,
  c_min_percent: "5", b_min_percent: "10", a_above_percent: "15",
  included_stages: ["打品期" as const, "启动期" as const],
};

describe("Listing 评级配置 API", () => {
  beforeEach(() => backendRequestMock.mockReset());

  it("loads a versioned global configuration", async () => {
    backendRequestMock.mockResolvedValue({ data: { version: 0, config, can_edit: false } });
    expect((await fetchListingGradeRule()).version).toBe(0);
    expect(backendRequestMock).toHaveBeenCalledWith("/api/listings/rule-config");
  });

  it("sends expected version and reason when creating an immutable version", async () => {
    backendRequestMock.mockResolvedValue({ data: { version: 1, config } });
    await saveListingGradeRule(config, 0, "变更参数");
    expect(backendRequestMock).toHaveBeenCalledWith("/api/listings/rule-config", {
      method: "PUT", body: JSON.stringify({ config, expected_version: 0, change_reason: "变更参数" }),
    });
  });

  it("reads history without mutating data", async () => {
    backendRequestMock.mockResolvedValue({ data: { total: 0, items: [] } });
    expect((await fetchListingGradeRuleHistory()).items).toEqual([]);
    expect(backendRequestMock).toHaveBeenCalledWith("/api/listings/rule-config/history?limit=20");
  });
});
