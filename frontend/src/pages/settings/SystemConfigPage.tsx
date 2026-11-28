import { ApiOutlined, CloudServerOutlined, DatabaseOutlined, SettingOutlined, TruckOutlined } from "@ant-design/icons";
import { Button, Card, Descriptions, Drawer, Space, Table, Tabs, Tag, Typography } from "antd";
import { useState, type ReactNode } from "react";
import PageShell from "@/components/page/PageShell";
import type { NavigationPage } from "@/config/navigation";
import { ApiPolicyPanel, SystemParametersPanel } from "./SystemConfigPolicyPanels";
import WooCommerceIntegrationPanel from "@/pages/settings/WooCommerceIntegrationPanel";

interface SystemConfigPageProps { page: NavigationPage }
interface ConfigGroup {
  key: string;
  name: string;
  purpose: string;
  fields: readonly [string, string][];
}
const sections: Record<string, { icon: ReactNode; description: string; groups: ConfigGroup[] }> = {
  erp: {
    icon: <DatabaseOutlined />,
    description: "统一管理领星 ERP 企业账号及数据接口授权。",
    groups: [{ key: "lingxing", name: "领星 ERP", purpose: "商品、订单、库存及财务数据来源", fields: [
      ["企业账号", "区分企业与授权主体"], ["App ID", "领星应用标识"],
      ["App Secret", "服务端加密管理，不回显"], ["连接状态", "展示实际授权验证结果"],
      ["账号范围", "关联允许读取的店铺及数据范围"],
    ] }],
  },
  logistics: {
    icon: <TruckOutlined />,
    description: "按物流服务商及仓储系统分别管理授权与连接。",
    groups: [
      { key: "carriers", name: "物流服务商", purpose: "运单、轨迹及物流状态接口", fields: [["服务商", "实际接入的物流公司"], ["账号标识", "区分授权账号"], ["接口地址", "服务商正式接口地址"], ["授权凭据", "按服务商认证方式配置"], ["连接状态", "实际验证结果"]] },
      { key: "warehouse", name: "仓储系统", purpose: "仓库、出入库及可售库存接口", fields: [["仓储服务商", "实际接入的仓储系统"], ["仓库映射", "系统仓库与外部仓库标识对应"], ["授权凭据", "按服务商认证方式配置"], ["连接状态", "实际验证结果"]] },
    ],
  },

};

function ConfigSection({ section }: { section: (typeof sections)[string] }) {
  const [selected, setSelected] = useState<ConfigGroup | null>(null);
  return (
    <>
      <Card title={<Space>{section.icon}<span>配置项目</span></Space>} extra={<Tag>设计预览</Tag>}>
        <Typography.Paragraph type="secondary">{section.description} 当前仅供界面验收，尚未接入配置接口。</Typography.Paragraph>
        <Table<ConfigGroup>
          size="middle" rowKey="key" pagination={false} dataSource={section.groups}
          columns={[
            { title: "配置对象", dataIndex: "name", width: 220, render: (name: string) => <Typography.Text strong>{name}</Typography.Text> },
            { title: "管理内容", dataIndex: "purpose" },
            { title: "操作", key: "action", width: 130, render: (_, row) => <Button type="link" onClick={() => setSelected(row)}>查看配置项</Button> },
          ]}
        />
      </Card>
      <Drawer title={selected?.name ?? "配置详情"} width={520} open={selected !== null} onClose={() => setSelected(null)}>
        {selected && <Space direction="vertical" size="large" style={{ width: "100%" }}>
          <Typography.Text type="secondary">字段与交互预览，不读取或保存实际配置。</Typography.Text>
          <Descriptions bordered size="small" column={1} items={selected.fields.map(([label, detail]) => ({ key: label, label, children: detail }))} />
          <Button onClick={() => setSelected(null)}>关闭</Button>
        </Space>}
      </Drawer>
    </>
  );
}

function SystemConfigPage({ page }: SystemConfigPageProps) {
  const [activeKey, setActiveKey] = useState("integrations");
  return (
    <PageShell page={page}>
      <Tabs activeKey={activeKey} onChange={setActiveKey} items={(page.tabs ?? []).map((tab) => ({
        key: tab.key,
        label: <Space>{tab.key === "integrations" ? <CloudServerOutlined /> : tab.key === "api-policy" ? <ApiOutlined /> : tab.key === "parameters" ? <SettingOutlined /> : sections[tab.key]?.icon}{tab.title}</Space>,
        children: tab.key === "integrations" ? <WooCommerceIntegrationPanel /> : tab.key === "api-policy" ? <ApiPolicyPanel /> : tab.key === "parameters" ? <SystemParametersPanel /> : sections[tab.key] ? <ConfigSection key={tab.key} section={sections[tab.key]} /> : null,
      }))} />
    </PageShell>
  );
}

export default SystemConfigPage;
