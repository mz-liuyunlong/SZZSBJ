/** V3 business-specific detail body; WFS still uses WfsCaseApprovalDetail unchanged. */
import { Alert, Card, Descriptions, Space, Tag, Timeline, Typography } from "antd";
import type { ApprovalDetail } from "../approvalTypes";
import GenericApprovalDetail from "./GenericApprovalDetail";

const display = (value: unknown): string => {
  if (value === null || value === undefined || value === "") return "—";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
};

const detailSpecs: Record<string, { heading: string; fields: { field: string; label: string }[]; limitation: string }> = {
  purchase_exception: {
    heading: "采购审批 · 采购业务依据",
    fields: [
      { field: "order_sn", label: "采购单号" },
      { field: "status", label: "采购单当前状态（申请快照）" },
      { field: "amount_total", label: "采购总额（申请快照）" },
      { field: "purchase_currency", label: "采购币种" },
    ],
    limitation: "审批通过只形成授权结论，不代表采购单已向供应商下单或付款。",
  },
  finance_exception: {
    heading: "财务调整 · 来源记录",
    fields: [
      { field: "business_date_la", label: "LA 业务日期" },
      { field: "local_sku", label: "SKU" },
    ],
    limitation: "现有来源快照只包含业务日期与 SKU 等身份字段；调整前后金额及费用明细尚未接入，不得推测或展示虚构金额。审批通过不会自动重算或核销财务数据。",
  },
};

export default function BusinessApprovalDetail({ detail }: { detail: ApprovalDetail }) {
  const spec = detailSpecs[detail.approval_type];
  if (!spec) return <GenericApprovalDetail detail={detail} />;
  const raw = detail.snapshot as Record<string, unknown>;
  const source = raw.source && typeof raw.source === "object"
    ? raw.source as Record<string, unknown>
    : {};
  const policy = raw.approval_policy && typeof raw.approval_policy === "object"
    ? raw.approval_policy as Record<string, unknown>
    : {};
  return <div className="approval-workspace__business-detail">
    <Alert type="info" showIcon message={spec.heading} description={spec.limitation} />
    <div className="approval-workspace__business-detail-grid">
      <Card size="small" title="01 / 业务对象与申请快照">
        <Descriptions size="small" bordered column={1}>
          <Descriptions.Item label="业务对象编号">{detail.business_ref}</Descriptions.Item>
          {spec.fields.map(item => <Descriptions.Item key={item.field} label={item.label}>
            {display(source[item.field])}
          </Descriptions.Item>)}
          <Descriptions.Item label="审批级数">{display(policy.required_steps)}</Descriptions.Item>
          <Descriptions.Item label="来源账号">{detail.source_account_ref}</Descriptions.Item>
        </Descriptions>
      </Card>
      <Card size="small" title="02 / 申请依据与说明">
        <Space direction="vertical" size={12} style={{width:"100%"}}>
          <div><Tag color="blue">申请人</Tag>{detail.applicant_id ?? "身份待核实"}</div>
          <Typography.Text strong>申请理由</Typography.Text>
          <Typography.Paragraph style={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}>{detail.reason || "未提供"}</Typography.Paragraph>
          <Typography.Text strong>申请证据</Typography.Text>
          <Typography.Paragraph style={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}>{detail.evidence || "未附证据"}</Typography.Paragraph>
        </Space>
      </Card>
    </div>
    <Card size="small" title="03 / 审批历史与审计">
      {detail.events.length
        ? <Timeline items={detail.events.map(event => ({
          children: <div><strong>{event.event_type}</strong><div>{event.actor_id} · {event.created_at}</div><p style={{whiteSpace:"pre-wrap"}}>{event.note ?? ""}</p></div>,
        }))} />
        : <Typography.Text type="secondary">暂无审批历史事件</Typography.Text>}
    </Card>
  </div>;
}
