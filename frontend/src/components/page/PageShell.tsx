/** Renders shared page metadata and content without duplicating MainLayout navigation UI. */
import { QuestionCircleOutlined } from "@ant-design/icons";
import { Button, Tag, Typography } from "antd";
import type { ReactNode } from "react";
import type { NavigationPage, PageStatus } from "../../config/navigation";
import "./PageShell.css";

const statusLabels: Record<PageStatus, string> = {
  planned: "规划中",
  building: "建设中",
  testing: "测试中",
  ready: "已就绪",
  disabled: "已停用",
  hidden: "内部页面",
};

interface PageShellProps {
  page: NavigationPage;
  description?: ReactNode;
  children?: ReactNode;
}

function PageShell({ page, description, children }: PageShellProps) {
  return (
    <section className="page-shell" aria-labelledby={`page-shell-title-${page.key}`}>
      <header className="page-shell__header">
        <div className="page-shell__heading">
          <div className="page-shell__title-row">
            <Typography.Title
              id={`page-shell-title-${page.key}`}
              level={4}
              className="page-shell__title"
              aria-label="当前页面"
            >
              {page.title}
            </Typography.Title>
            <Tag aria-label={`页面状态：${page.status}`}>
              {statusLabels[page.status]}
            </Tag>
          </div>
          {description && (
            <Typography.Paragraph className="page-shell__description" type="secondary">
              {description}
            </Typography.Paragraph>
          )}
        </div>

        {page.help.enabled && (
          <Button
            className="page-shell__help"
            type="link"
            icon={<QuestionCircleOutlined aria-hidden="true" />}
            href={page.help.helpUrl}
            target="_blank"
            rel="noopener noreferrer"
            aria-label={`在新标签页打开${page.help.title}`}
          >
            帮助
          </Button>
        )}
      </header>

      <div className="page-shell__content">{children}</div>
    </section>
  );
}

export default PageShell;
