import { describe, expect, it } from "vitest";
import { apiDocModules } from "@/pages/data-center/apiDocsMockData";
import { filterApiDocs, flattenApiDocs, getApiCount } from "@/pages/data-center/apiDocsTypes";

describe("apiDocsTypes", () => {
  it("flattens the API documentation matrix", () => {
    const apis = flattenApiDocs(apiDocModules);

    expect(apiDocModules.length).toBeGreaterThanOrEqual(4);
    expect(apis.length).toBeGreaterThanOrEqual(6);
    expect(getApiCount(apiDocModules[0])).toBe(apiDocModules[0].levels.reduce((total, level) => total + level.apis.length, 0));
  });

  it("searches modules, secondary levels, interface titles and paths", () => {
    const filtered = filterApiDocs(apiDocModules, "wfs-fee-alerts");
    const apis = flattenApiDocs(filtered);

    expect(filtered).toHaveLength(1);
    expect(filtered[0].key).toBe("warehouse");
    expect(apis.map((api) => api.path)).toContain("/api/v1/warehouse/wfs-fee-alerts");
  });
});
