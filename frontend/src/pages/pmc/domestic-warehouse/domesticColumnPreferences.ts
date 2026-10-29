import { readUserPreference, writeUserPreference } from "@/shared/preferences/userPreferenceCache";
import { defaultColumnKeys, defaultColumnWidths } from "./domesticWarehouseTypes";

export interface DomesticColumnSettings { keys: string[]; widths: Record<string, number> }
export const domesticColumnPreferenceKey = "pmc-domestic-inbound-board:columns";
export const domesticColumnPreferenceVersion = 3;

export function readDomesticColumns(scope: string): DomesticColumnSettings {
  const current = readUserPreference<DomesticColumnSettings>(scope, domesticColumnPreferenceKey, domesticColumnPreferenceVersion);
  const savedV2 = current ? undefined : readUserPreference<DomesticColumnSettings>(scope, domesticColumnPreferenceKey, 2);
  const savedV1 = current || savedV2 ? undefined : readUserPreference<DomesticColumnSettings>(scope, domesticColumnPreferenceKey, 1);
  const stored = current ?? savedV2 ?? savedV1;
  const allowed = new Set(defaultColumnKeys);
  const keys = ["arrival", ...new Set((stored?.keys ?? defaultColumnKeys).filter((key) => key !== "arrival" && allowed.has(key)))];
  if (savedV1) {
    const added = ["item", "gtin", "owner"].filter((key) => !keys.includes(key));
    const anchor = keys.indexOf("store");
    keys.splice(anchor < 0 ? keys.length : anchor + 1, 0, ...added);
  }
  if (!current && !keys.includes("draft")) {
    const anchor = keys.indexOf("arrival");
    keys.splice(anchor < 0 ? 1 : anchor + 1, 0, "draft");
  }
  const settings = { keys, widths: { ...defaultColumnWidths, ...stored?.widths } };
  if (!current && (savedV1 || savedV2)) writeUserPreference(scope, domesticColumnPreferenceKey, domesticColumnPreferenceVersion, settings);
  return settings;
}
