/** Frame for the non-table PMC 设置 pages: PageShell → page card (title + source) → content. */
import { QuestionCircleOutlined } from "@ant-design/icons";
import { Button, Card, Typography, theme } from "antd";
import type { CSSProperties, ReactNode } from "react";
import PageShell from "@/components/page/PageShell";
import RequestLoadingOverlay from "@/components/page/RequestLoadingOverlay";
import type { NavigationPage } from "@/config/navigation";
import { SETTINGS_HELP_URL } from "./settingsShared";
import "../WfsSettingsPage.css";

export default function SettingsFormLayout({
  page, source, loading = false, children,
}: { page: NavigationPage; source: string; loading?: boolean; children: ReactNode }) {
  const { token } = theme.useToken();
  const vars = {
    "--ant-color-border-secondary": token.colorBorderSecondary,
    "--ant-border-radius-lg": `${token.borderRadiusLG}px`,
  } as CSSProperties;
  return (
    <PageShell
      page={page}
      headerActions={<Button href={SETTINGS_HELP_URL} target="_blank" rel="noopener noreferrer" icon={<QuestionCircleOutlined />}>帮助</Button>}
    >
      <div className="pmc-settings" style={vars}>
        <Card size="small" className="pmc-settings__page-card pmc-settings__form-card">
          <RequestLoadingOverlay spinning={loading} label={`正在加载${page.title}，请稍候`} />
          <div className="pmc-settings__title-row">
            <Typography.Title level={3}>{page.title}</Typography.Title>
            <Typography.Text type="secondary">{source}</Typography.Text>
          </div>
          {children}
        </Card>
      </div>
    </PageShell>
  );
}
