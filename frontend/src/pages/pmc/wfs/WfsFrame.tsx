/** Shared chrome for the WFS preview pages. */
import { QuestionCircleOutlined } from "@ant-design/icons";
import { Alert, Button, Space, Tag, Typography } from "antd";
import type { ReactNode } from "react";
import PageShell from "@/components/page/PageShell";
import type { NavigationPage } from "@/config/navigation";

export default function WfsFrame({
  page,
  demo = false,
  children,
}: {
  page: NavigationPage;
  demo?: boolean;
  children: ReactNode;
}) {
  return (
    <PageShell
      page={page}
      headerActions={(
        <Button
          href="/help/pmc-wfs.html"
          target="_blank"
          rel="noreferrer"
          icon={<QuestionCircleOutlined />}
        >
          帮助
        </Button>
      )}
    >
      <Space direction="vertical" size={16} style={{ width: "100%" }}>
        <Alert
          showIcon
          type={demo ? "warning" : "info"}
          message={demo ? "演示流程，示例数据" : "前端预览，示例数据"}
          description="这些行只在浏览器里展示，对应已确认的货件流转。页面不请求接口，不写入 Walmart，也不读取领星。"
        />
        <Space size={8} wrap>
          <Typography.Text type="secondary">来源标记</Typography.Text>
          <Tag color="blue">真实口径待接入</Tag>
          <Tag color="gold">当前为示例</Tag>
          {demo && <Tag>不进入正式货件</Tag>}
        </Space>
        {children}
      </Space>
    </PageShell>
  );
}
