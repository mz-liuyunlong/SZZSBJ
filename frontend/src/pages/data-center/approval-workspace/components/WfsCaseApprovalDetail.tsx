import { Alert, Descriptions, Divider, Tag, Timeline, Typography } from "antd";
import type { ApprovalDetail } from "../approvalTypes";
import { formatMoney } from "@/shared/formatters/money";

export function parseFollowLog(log: string | null | undefined): string[] {
 return (log ?? "").split(/\r?\n/).map((line) => line.trim()).filter(Boolean);
}
const field = (value: unknown) => value == null || value === "" ? "—" : String(value);
const money = (value: unknown, currency: unknown) => formatMoney(value, { currency: String(currency || "USD") });

export function WfsCaseApprovalDetail({ detail }: { detail: ApprovalDetail }) {
 const item = detail.snapshot;
 const lines = parseFollowLog(item.follow_log);
 const current = detail.current_case || item;
 const fields = [
  ["店铺", item.store_name_snapshot || item.store_id],
  ["运营负责人", item.owner_name_snapshot],
  ["SKU", item.local_sku_snapshot], ["MSKU", item.msku],
  ["Item ID", item.item_id], ["产品名称", item.product_name_snapshot],
  ["人工配送费", money(item.manual_unit_fee, item.currency_code)],
  ["WFS实收费率", money(item.actual_unit_fee, item.currency_code)],
  ["单件多收", money(item.unit_fee_diff, item.currency_code)],
  ["受影响销量", item.affected_units],
  ["预计追回", money(item.estimated_recover_amount, item.currency_code)],
  ["已追回", money(item.recovered_amount, item.currency_code)],
  ["索赔金额", money(item.claim_amount, item.currency_code)],
  ["申请时待追回", money(item.pending_recover_amount, item.currency_code)],
  ["Case编号", item.case_nos], ["提交前状态", item.status],
  ["平台回复", item.walmart_response_summary], ["证据摘要", item.evidence_summary],
 ];
 return <div className="approval-workspace__detail">
  {detail.data_changed && <Alert showIcon type="warning" title="业务数据发生变化" description="申请提交后关键信息发生变化，服务端禁止直接审批。" />}
  <div className="approval-workspace__money">
   <div><span>预计追回</span><strong>{money(item.estimated_recover_amount, item.currency_code)}</strong></div>
   <div><span>申请时待追回</span><strong>{money(item.pending_recover_amount, item.currency_code)}</strong></div>
   <div><span>已追回</span><strong>{money(item.recovered_amount, item.currency_code)}</strong></div>
   <div><span>运营跟进</span><strong>{lines.length} 次</strong></div>
  </div>
  <Typography.Title level={5}>运营放弃原因</Typography.Title>
  <Typography.Paragraph>{detail.reason}</Typography.Paragraph>
  <Typography.Title level={5}>审批业务依据（提交时快照）</Typography.Title>
  <Descriptions bordered size="small" column={2}>
   {fields.map(([label, value]) => <Descriptions.Item key={String(label)} label={String(label)}>{field(value)}</Descriptions.Item>)}
  </Descriptions>
  <Divider />
  <Typography.Title level={5}>完整运营跟进历史 <Tag>{lines.length}条</Tag></Typography.Title>
  <Timeline items={lines.length ? [...lines].reverse().map((line, index) => ({
   color: index === 0 ? "blue" : "gray",
   children: <Typography.Paragraph style={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}>{line}</Typography.Paragraph>,
  })) : [{ children: "暂无历史跟进" }]} />
  <Typography.Title level={5}>实时业务信息</Typography.Title>
  <Typography.Paragraph>当前状态：{field(current.status)}，当前待追回：{money(current.pending_recover_amount, current.currency_code)}</Typography.Paragraph>
 </div>;
}
