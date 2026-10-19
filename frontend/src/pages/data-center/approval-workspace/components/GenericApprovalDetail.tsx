import { Alert, Descriptions, Divider, Typography } from "antd";
import type { ApprovalDetail } from "../approvalTypes";

const names:Record<string,string>={
 purchase_exception:"采购异常处理",
 finance_exception:"财务例外处理",
 access_change:"权限变更",
};
export default function GenericApprovalDetail({detail}:{detail:ApprovalDetail}) {
 const raw=detail.snapshot as Record<string, unknown>;
 const fields=raw.source && typeof raw.source==="object"
  ? Object.entries(raw.source as Record<string,unknown>) : [];
 const policy=raw.approval_policy as {required_steps?:number} | undefined;
 return <>
  <Alert showIcon type="info" message={(names[detail.approval_type]||"业务申请")+" · 审批与执行分离"}
   description="本审批只形成管理结论、审批轨迹与来源快照。业务记录不会因审核通过而自动改动。" />
  <Typography.Title level={5}>申请理由</Typography.Title>
  <Typography.Paragraph style={{whiteSpace:"pre-wrap"}}>{detail.reason}</Typography.Paragraph>
  <Typography.Title level={5}>申请证据</Typography.Title>
  <Typography.Paragraph style={{whiteSpace:"pre-wrap"}}>{detail.evidence||"未附证据"}</Typography.Paragraph>
  <Divider/>
  <Typography.Title level={5}>原业务记录（提交时快照）</Typography.Title>
  <Descriptions size="small" column={1} bordered>
   {fields.map(([key,value])=><Descriptions.Item key={key} label={key}>
    {value===null?"—":String(value)}</Descriptions.Item>)}
   <Descriptions.Item label="审批级数">{policy?.required_steps||1}</Descriptions.Item>
   <Descriptions.Item label="实际业务执行">尚未执行，需单独授权操作</Descriptions.Item>
  </Descriptions>
 </>;
}
