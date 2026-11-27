import { describe, expect, it } from "vitest";
import { CLEARANCE_RULE_SPECS } from "./clearanceRuleCatalog";
import { DEFAULT_RULES } from "./clearanceModel";
import { fullRulesForSave, ruleChangeReason, rulesFromServer, RETIRED_RULE_FIELDS } from "./clearanceRulesAdapter";
import type { RuleResponse } from "./clearanceApi";

const server = (version: number): RuleResponse => ({
  version, persisted: version > 0, can_edit: true, catalog: [],
  config: {
    ...Object.fromEntries(CLEARANCE_RULE_SPECS.map(spec => [spec.key, DEFAULT_RULES[spec.key]])),
    coverageLookback: 14, newProductProtectionDays: 90, minBaselineSales7: 18,
    minSalesDropUnits7: 7, minReturns30: 6, minReturnSales30: 40,
    minReviewCount: 22, enableRepeatBacklog: true,
  },
});
describe("Clearance rule round-trip without changing UI or risk decisions", () => {
  it("keeps real hidden backend values and historical re-backlog flag", () => {
    const source = server(7);
    const draft = rulesFromServer(source);
    expect(draft.enableRepeatBacklog).toBe(true);
    const saved = fullRulesForSave(source, {...draft, highCoverage: 240});
    for (const name of ["coverageLookback", "newProductProtectionDays", "minBaselineSales7",
      "minSalesDropUnits7", "minReturns30", "minReturnSales30", "minReviewCount",
      "enableRepeatBacklog"]) expect(saved[name]).toEqual(source.config[name]);
    expect(saved.highCoverage).toBe(240);
    for (const key of RETIRED_RULE_FIELDS) expect(key in saved).toBe(false);
  });
  it("permits initial save at explicit unsaved version zero", () => {
    const source = server(0);
    expect(rulesFromServer(source).highCoverage).toBe(DEFAULT_RULES.highCoverage);
    expect(ruleChangeReason(source, rulesFromServer(source))).toContain("首次保存");
  });
  it("rejects missing mapped values rather than inventing effective rules", () => {
    const source = server(2);
    delete source.config.highCoverage;
    expect(() => rulesFromServer(source)).toThrow("highCoverage");
  });
});
