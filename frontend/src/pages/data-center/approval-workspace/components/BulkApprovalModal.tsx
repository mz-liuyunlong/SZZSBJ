import { Alert, Form, Input, Modal, message } from "antd";
import { useState } from "react";
import { approveLowRiskBatch } from "../approvalWorkflowApi";
import type { ApprovalItem } from "../approvalTypes";

interface Props { rows:ApprovalItem[]; onCancel():void; onUpdated():void }
export default function BulkApprovalModal({rows,onCancel,onUpdated}:Props) {
 const [note,setNote]=useState("");
 const [saving,setSaving]=useState(false);
 const [api,holder]=message.useMessage();
 const save=async()=>{
  if(note.trim().length<5){void api.warning("至少填写5个字的审批意见");return;}
  if(rows.some(r=>r.approval_type!=="operations_plan_ack"||r.risk_level!=="low"||!r.can_review)){
   void api.error("选中包含非白名单或没有权限的申请");return;
  }
  setSaving(true);
  try{
   const n=await approveLowRiskBatch(rows.map(r=>({id:r.id,version:r.version})),note.trim());
   void api.success("已完成 "+n+" 条低风险审批");
   setNote(""); onCancel();onUpdated();
  }catch{void api.error("批量审核失败：数据已变化或权限不足，本次操作未被接受");}
  finally{setSaving(false);}
 };
 return <>
  {holder}
  <Modal title={"批量通过低风险申请（"+rows.length+"条）"} open={rows.length>0}
   onCancel={onCancel} onOk={()=>void save()} okText="确认批量审批"
   okButtonProps={{loading:saving}}>
   <Alert type="warning" showIcon style={{marginBottom:16}}
    message="仅允许运营计划低风险事项"
    description="服务端会再次检查全部审批单版本、业务快照和审批权限。WFS 放弃跟进、采购、财务和权限变更均不允许批量通过。" />
   <Form layout="vertical">
    <Form.Item label="批量审批理由（必填）">
     <Input.TextArea rows={4} maxLength={4000} showCount value={note}
      onChange={e=>setNote(e.target.value)}/>
    </Form.Item>
   </Form>
  </Modal>
 </>;
}
