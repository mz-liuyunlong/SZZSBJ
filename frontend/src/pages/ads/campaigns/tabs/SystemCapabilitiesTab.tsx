import { ProTable, type ProColumns } from "@ant-design/pro-components";
import { Button, Card, Space, Tag, Typography, message } from "antd";
import ReportTableShell from "@/components/report-table/ReportTableShell";
import {
  recommendationRows,
  snapshotRows,
} from "@/pages/ads/campaigns/adsCampaignMockData";
import type {
  RecommendationRow,
  SnapshotRow,
} from "@/pages/ads/campaigns/adsCampaignTypes";

const recommendationColumns: ProColumns<RecommendationRow>[] = [
  { title: "推荐类型", dataIndex: "type", width: 110 },
  { title: "对象", dataIndex: "target", width: 190 },
  { title: "原因", dataIndex: "reason", width: 220 },
  { title: "建议动作", dataIndex: "action", width: 140 },
  { title: "预计影响", dataIndex: "impact", width: 120 },
  {
    title: "操作",
    valueType: "option",
    width: 100,
    render: (_, row) => (
      <Button type="link">
        查看{row.type}
      </Button>
    ),
  },
];

const snapshotColumns: ProColumns<SnapshotRow>[] = [
  { title: "Snapshot ID", dataIndex: "id", width: 130 },
  { title: "类型", dataIndex: "type", width: 170 },
  { title: "实体", dataIndex: "entity", width: 230 },
  {
    title: "状态",
    dataIndex: "status",
    width: 100,
    render: (_, row) => <Tag color={row.status === "completed" ? "success" : "processing"}>{row.status === "completed" ? "完成" : "运行中"}</Tag>,
  },
  { title: "创建时间", dataIndex: "createdAt", width: 170 },
  {
    title: "操作",
    valueType: "option",
    width: 100,
    render: () => <Button type="link">详情</Button>,
  },
];

function SystemCapabilitiesTab() {
  const [messageApi, messageContextHolder] = message.useMessage();

  return (
    <div className="ads-campaigns-system">
      {messageContextHolder}
      <section className="ads-campaigns-preview-grid">
        <Card size="small"><Typography.Text type="secondary">关键词机会</Typography.Text><strong>23</strong><span>高转化词待添加</span></Card>
        <Card size="small"><Typography.Text type="secondary">否定词建议</Typography.Text><strong>14</strong><span>高花费无转化</span></Card>
        <Card size="small"><Typography.Text type="secondary">预算建议</Typography.Text><strong>6</strong><span>预算不足活动</span></Card>
        <Card size="small"><Typography.Text type="secondary">竞价建议</Typography.Text><strong>31</strong><span>出价上调/下调</span></Card>
      </section>

      <ReportTableShell label="推荐清单" className="ads-campaigns-table-shell">
        <div className="ads-campaigns-table-head">
          <Typography.Text strong>推荐清单</Typography.Text>
          <Button type="primary" onClick={() => void messageApi.success("推荐操作计划已生成")}>
            生成操作计划
          </Button>
        </div>
        <ProTable<RecommendationRow>
          rowKey="id"
          size="small"
          search={false}
          options={false}
          columns={recommendationColumns}
          dataSource={recommendationRows}
          pagination={false}
          scroll={{ x: 880 }}
        />
      </ReportTableShell>

      <Card size="small" className="ads-campaigns-toolbar">
        <Space wrap>
          <Button type="primary" onClick={() => void messageApi.success("快照任务已提交")}>
            提交快照任务
          </Button>
          <Typography.Text type="secondary">
            用于广告实体审计、异步同步和推荐生成。
          </Typography.Text>
        </Space>
      </Card>

      <ReportTableShell label="快照任务" className="ads-campaigns-table-shell">
        <div className="ads-campaigns-table-head">
          <Typography.Text strong>快照任务</Typography.Text>
        </div>
        <ProTable<SnapshotRow>
          rowKey="id"
          size="small"
          search={false}
          options={false}
          columns={snapshotColumns}
          dataSource={snapshotRows}
          pagination={false}
          scroll={{ x: 780 }}
        />
      </ReportTableShell>

      <section className="ads-campaigns-preview-grid">
        <Card size="small"><Typography.Text type="secondary">今日调用</Typography.Text><strong>1,284</strong><span>API Activity</span></Card>
        <Card size="small"><Typography.Text type="secondary">成功率</Typography.Text><strong>99.2%</strong><span>请求稳定</span></Card>
        <Card size="small"><Typography.Text type="secondary">平均耗时</Typography.Text><strong>214ms</strong><span>接口响应</span></Card>
        <Card size="small"><Typography.Text type="secondary">剩余额度</Typography.Text><strong>72%</strong><span>调用预算</span></Card>
      </section>
    </div>
  );
}

export default SystemCapabilitiesTab;
