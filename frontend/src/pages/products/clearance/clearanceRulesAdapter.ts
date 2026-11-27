/** Lossless API adapter: only rendered, approved rules are editable. */
import { DEFAULT_RULES, type ClearanceRules } from "./clearanceModel";
import { CLEARANCE_RULE_SPECS } from "./clearanceRuleCatalog";
import type { RuleResponse } from "./clearanceApi";

type Value = number | boolean;

/** Permanently cancelled batch-age and near-fee rules are never serialized. */
export const RETIRED_RULE_FIELDS = [
  "mediumAge", "agedLotDays", "agedLotMin", "feeAgeDays", "feeWarningDays",
  "agedRatioPercent", "enableAged", "enableAverageAge", "enableNearFee",
  "enableAgedRatio",
] as const;

function assertValue(key: string, value: unknown, baseline: Value): asserts value is Value {
  if (typeof value !== typeof baseline || (typeof value === "number" && !Number.isFinite(value))) {
    throw new Error("Clearance rule mapping mismatch: " + key);
  }
}

export function rulesFromServer(response: RuleResponse): ClearanceRules {
  if (!Number.isInteger(response.version) || response.version < 0 ||
      response.persisted !== (response.version > 0)) {
    throw new Error("Invalid clearance rule version");
  }
  const form: ClearanceRules = { ...DEFAULT_RULES };
  const target = form as unknown as Record<string, Value>;
  for (const spec of CLEARANCE_RULE_SPECS) {
    const value = response.config[spec.key];
    assertValue(spec.key, value, DEFAULT_RULES[spec.key]);
    target[spec.key] = value;
  }
  // The existing re-backlog hint is not a retired inventory-age rule.
  if (typeof response.config.enableRepeatBacklog === "boolean") {
    form.enableRepeatBacklog = response.config.enableRepeatBacklog;
  }
  return form;
}

export function fullRulesForSave(response: RuleResponse, form: ClearanceRules): Record<string, Value> {
  // Preserve every invisible but necessary backend field from the actual server snapshot.
  const result: Record<string, Value> = { ...response.config };
  for (const spec of CLEARANCE_RULE_SPECS) {
    const value = form[spec.key];
    assertValue(spec.key, value, DEFAULT_RULES[spec.key]);
    result[spec.key] = value;
  }
  for (const retired of RETIRED_RULE_FIELDS) delete result[retired];
  return result;
}

export function ruleChangeReason(response: RuleResponse, form: ClearanceRules): string {
  const changed = CLEARANCE_RULE_SPECS.filter(spec =>
    response.config[spec.key] !== form[spec.key]).map(spec => spec.label);
  if (response.version === 0) {
    return ("首次保存清货规则" + (changed.length ? "：" + changed.join("、") : "")).slice(0, 500);
  }
  return ("调整清货规则：" + changed.join("、")).slice(0, 500);
}
