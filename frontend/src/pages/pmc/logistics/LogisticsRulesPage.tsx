/** 时效与阈值设置（8088 pmc-logistics TabSettings），一期只读：显示物流各页正在用的规则值。
 * 修改入口待 Rocky 定（建议在 PMC 设置里做版本化维护）；8088 的通知渠道映射是示例，不展示。 */
import { QuestionCircleOutlined } from "@ant-design/icons";
import { Alert, Button, Card, Descriptions, Table, Tag, Typography } from "antd";
import { useQuery } from "@tanstack/react-query";
import PageShell from "@/components/page/PageShell";
import type { NavigationPage } from "@/config/navigation";
import { getRules, type RulesView } from "./logisticsApi";
import { logisticsError, logisticsKey } from "./logisticsQueries";
import "./logistics.css";

const { Text } = Typography;
type Cycle = RulesView["cycles"][number];
type Contract = RulesView["contracts"][number];
type Fc = RulesView["fcs"][number];

export default function LogisticsRulesPage({ page, scope }: { page: NavigationPage; scope: string }) {
  const q = useQuery({ queryKey: logisticsKey(scope, "rules"), queryFn: ({ signal }) => getRules(signal), retry: false });
  const d = q.data?.data;
  return (
    <PageShell page={page} headerActions={<Button href="/help/pmc-logistics.html" target="_blank" rel="noreferrer" icon={<QuestionCircleOutlined />}>帮助</Button>}>
      <div className="logi-rules">
        {q.error && <Alert type="error" showIcon message={logisticsError(q.error)} style={{ marginBottom: 12 }} />}
        {d && <Alert type="info" showIcon style={{ marginBottom: 12 }} message={`数据日 ${d.today} · ${d.edit_hint}`} />}
        <Card size="small" title="全局阈值" loading={q.isLoading}>
          <Descriptions size="small" bordered column={1} items={(d?.thresholds ?? []).map((t) => ({
            key: t.key, label: t.label, children: <b>{t.value} {t.unit}</b>,
          }))} />
          <p style={{ marginTop: 8 }}>
            <Text type="secondary">无任何轨迹时的兜底（发货日 + 目的仓地区天数）：</Text>
            {Object.entries(d?.region_total ?? {}).map(([k, v]) => <Tag key={k} bordered={false}>{k} {v} 天</Tag>)}
          </p>
        </Card>
        <Card size="small" title="渠道分段时效" extra={<Text type="secondary">提货→开船 / 开船→到港 / 到港→到货；未单独设的渠道按目的仓地区兜底</Text>}>
          <Table<Cycle> size="small" pagination={false} rowKey="channel_id" dataSource={d?.cycles ?? []} columns={[
            { title: "物流商", dataIndex: "provider", width: 160 },
            { title: "渠道", width: 260, render: (_, c) => <span>{c.channel || "—"}<br /><Text type="secondary">ID {c.channel_id} · {c.method || "—"}</Text></span> },
            { title: "可去地区", width: 160, render: (_, c) => c.regions.map((r) => <Tag key={r} bordered={false}>{r}</Tag>) },
            { title: "提货→开船（天）", dataIndex: "toSail", width: 130, render: (v: number | null) => v ?? <Text type="secondary">地区兜底</Text> },
            { title: "开船→到港（天）", dataIndex: "voyage", width: 130, render: (v: number | null) => v ?? <Text type="secondary">地区兜底</Text> },
            { title: "到港→到货（天）", dataIndex: "days", width: 130, render: (v: number | null) => v ?? <Text type="secondary">地区兜底</Text> },
            { title: "使用中发货单", dataIndex: "sps", width: 110, align: "right" },
          ]} />
        </Card>
        <Card size="small" title="合同时效" extra={<Text type="secondary">物流商 × 渠道 × 目的地区 · 提货次日到签收的约定天数</Text>}>
          <Table<Contract> size="small" pagination={false} rowKey={(c) => `${c.provider_id}|${c.channel_id}|${c.region}`} dataSource={d?.contracts ?? []} columns={[
            { title: "物流商", dataIndex: "provider", width: 180 },
            { title: "渠道", width: 260, render: (_, c) => <span>{c.channel || "—"}<br /><Text type="secondary">ID {c.channel_id}</Text></span> },
            { title: "目的地区", dataIndex: "region", width: 100 },
            { title: "合同时效（天）", dataIndex: "days", width: 130, align: "right" },
            { title: "提前提醒（天）", dataIndex: "remind", width: 130, align: "right" },
            { title: "使用中发货单", dataIndex: "sps", width: 110, align: "right" },
          ]} />
        </Card>
        <Card size="small" title="目的仓 → 地区" extra={<Text type="secondary">与 WFS 共用；来自领星货件地址</Text>}>
          <Table<Fc> size="small" pagination={false} rowKey="fc" dataSource={d?.fcs ?? []} columns={[
            { title: "仓库代码", dataIndex: "fc", width: 100 },
            { title: "地址", dataIndex: "addr" },
            { title: "城市 / 州", width: 200, render: (_, f) => `${f.city}, ${f.state}` },
            { title: "邮编", dataIndex: "zip", width: 90 },
            { title: "地区", dataIndex: "region", width: 90, render: (v: string) => <Tag bordered={false}>{v}</Tag> },
            { title: "发货单数", dataIndex: "n", width: 90, align: "right" },
          ]} />
        </Card>
      </div>
    </PageShell>
  );
}
