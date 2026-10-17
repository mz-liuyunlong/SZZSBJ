import { Alert, Button, Drawer, InputNumber, Space, Switch, Table, message } from "antd";
import { useEffect, useState } from "react";
import { fetchApprovalRules, updateApprovalRule, type ApprovalRule } from "../approvalWorkflowApi";

interface Props { open: boolean; onClose(): void }
export default function ApprovalRulesDrawer({ open, onClose }: Props) {
 const [data, setData] = useState<ApprovalRule[]>([]);
 const [loading, setLoading] = useState(false);
 const [saving, setSaving] = useState<string>();
 const [api, holder] = message.useMessage();
 useEffect(() => {
  if (!open) return;
  let live = true;
  void fetchApprovalRules().then((list) => { if (live) setData(list); })
   .catch(() => { if (live) void api.error("审批规则读取失败"); });
  return () => { live = false; };
 }, [open, api]);
 const patch = (key: string, values: Partial<ApprovalRule>) =>
  setData((current) => current.map((r) => r.approval_type === key ? {...r, ...values} : r));
 const save = async (row: ApprovalRule) => {
  setSaving(row.approval_type);
  try {
   await updateApprovalRule(row.approval_type, row, {
    required_steps:row.required_steps,
    due_hours:row.due_hours,
    allows_bulk:row.allows_bulk,
   });
   setData(await fetchApprovalRules());
   void api.success("规则已保存，历史申请继续沿用其提交时快照");
  } catch {
   void api.error("规则保存失败：版本已变化或没有管理权限");
  } finally { setSaving(undefined); }
 };
 return <>
  {holder}
  <Drawer title="审批规则管理" open={open} onClose={onClose} width={860}
   extra={<Button onClick={() => void fetchApprovalRules().then(setData)}>刷新</Button>}>
   <Alert type="info" showIcon style={{marginBottom:16}} message="配置影响未来申请"
    description="每一份新申请保存提交时规则快照；WFS 放弃跟进始终禁止批量审批。任何规则调整都由服务端保留版本和审计。" />
   <Table<ApprovalRule> size="small" rowKey="approval_type" pagination={false}
    dataSource={data} loading={loading} columns={[
     {title:"业务类型",dataIndex:"title",width:160},
     {title:"审批级数",width:130,render:(_,r) =>
      <InputNumber min={1} max={5} style={{width:90}} value={r.required_steps}
       onChange={(v) => patch(r.approval_type,{required_steps:v || 1})}/>},
     {title:"提醒时限(小时)",width:145,render:(_,r) =>
      <InputNumber min={1} max={8760} style={{width:100}} value={r.due_hours}
       onChange={(v) => patch(r.approval_type,{due_hours:v || 1})}/>},
     {title:"允许批量",width:110,render:(_,r) =>
      <Switch checked={r.allows_bulk} disabled={r.approval_type==="wfs_case_abandon"}
       onChange={(v) => patch(r.approval_type,{allows_bulk:v})}/>},
     {title:"操作",render:(_,r) =>
      <Button type="link" loading={saving===r.approval_type} onClick={() => void save(r)}>保存</Button>},
    ]}/>
   <Space style={{marginTop:16}}>规则变更必须由具备角色权限管理授权的用户执行。</Space>
  </Drawer>
 </>;
}
