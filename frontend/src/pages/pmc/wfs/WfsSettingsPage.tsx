/**
 * PMC 设置 · WFS pages (PRP pmc-wfs-settings S2/S3). Each sidebar leaf renders one section; the
 * sections live in ./settings and compose the shared report / form components.
 */
import type { NavigationPage } from "@/config/navigation";
import FcRegionsSection from "./settings/FcRegionsSection";
import LogisticsChannelsSection from "./settings/LogisticsChannelsSection";
import { StoreSettingsSection } from "./settings/SettingsNoticeSection";
import WfsAlertCenter from "./settings/WfsAlertCenter";
import type { SectionProps } from "./settings/settingsShared";
import { SETTINGS_SECTION_BY_PAGE } from "./settings/settingsShared";

const SECTIONS = {
  rules: (props: SectionProps) => <WfsAlertCenter {...props} initialTab="rules" />,
  fc: FcRegionsSection,
  channels: LogisticsChannelsSection,
  stores: StoreSettingsSection,
  notes: (props: SectionProps) => <WfsAlertCenter {...props} initialTab="notes" />,
};

export default function WfsSettingsPage({
  page, scope = "anonymous", permissions = [],
}: { page: NavigationPage; scope?: string; permissions?: string[] }) {
  const Section = SECTIONS[SETTINGS_SECTION_BY_PAGE[page.key] ?? "rules"];
  return <Section page={page} scope={scope} permissions={permissions} />;
}
