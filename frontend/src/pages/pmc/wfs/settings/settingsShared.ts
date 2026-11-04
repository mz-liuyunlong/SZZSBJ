/** Shared constants and helpers for the PMC 设置 pages (page-local to this feature). */
import type { NavigationPage } from "@/config/navigation";
import { SETTINGS_MANAGE_PERMISSION } from "../settingsApi";

export const SAMPLE_TAG = "示例 · 待定";
export const SETTINGS_HELP_URL = "/help/pmc-settings.html";

export type SettingsSection = "rules" | "fc" | "channels" | "stores" | "notes";

/** Navigation page key → section rendered by that sidebar leaf / workspace tab. */
export const SETTINGS_SECTION_BY_PAGE: Record<string, SettingsSection> = {
  pmc_wfs_settings: "rules",
  pmc_wfs_settings_fc: "fc",
  pmc_wfs_settings_channels: "channels",
  pmc_wfs_settings_stores: "stores",
  pmc_wfs_settings_notes: "notes",
};

export const today = () => new Date().toISOString().slice(0, 10);

/** No shared DateTimeText exists yet (UI_COMPONENT_CATALOG lists it as planned); one formatter for these pages. */
export const formatTime = (value?: string | null) =>
  value
    ? new Intl.DateTimeFormat("zh-CN", { timeZone: "Asia/Taipei", dateStyle: "short", timeStyle: "short" }).format(new Date(value))
    : "—";

/** Writes need the manage permission and a page no longer marked read-only in navigation (5173 stays greyed). */
export function settingsAccess(page: NavigationPage, permissions: string[]) {
  const canManage = !page.readOnly && (permissions.includes("*") || permissions.includes(SETTINGS_MANAGE_PERMISSION));
  const writeHint = canManage ? undefined : page.readOnly ? "本页当前只读，写入待正式放行" : "没有 PMC 设置维护权限";
  return { canManage, writeHint };
}

export interface SectionProps {
  page: NavigationPage;
  scope: string;
  permissions: string[];
}
