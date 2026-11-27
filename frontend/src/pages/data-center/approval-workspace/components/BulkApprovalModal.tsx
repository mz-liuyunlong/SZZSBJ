import { Alert, Form, Input, Modal, message } from "antd";
import { useRef, useState } from "react";
import { reviewClearanceApplication } from
 "@/pages/products/clearance/clearanceApi";
import { approveLowRiskBatch } from "../approvalWorkflowApi";
import type { ApprovalItem } from "../approvalTypes";

interface Props { rows:ApprovalItem[]; onCancel():void; onUpdated():void }
export default function BulkApprovalModal({rows,onCancel,onUpdated}:Props) {
 const [note,setNote]=useState("");
 const [saving,setSaving]=useState(false);
 const [api,holder]=message.useMessage();
 const savingRef=useRef(false);
 const [resultModal,resultHolder]=Modal.useModal();

 const clearanceBatch=rows.length>0 &&
   rows.every(r=>r.approval_type==="clearance_request");

 const save=async()=>{
  if(savingRef.current || !rows.length)return;
  if(note.trim().length<5){void api.warning("至少填写5个字的审批意见");return;}
  if(rows.some(r=>
    !r.can_review ||
    r.status!=="submitted" ||
    r.case_review ||
    (clearanceBatch
      ? r.approval_type!=="clearance_request"
      : r.approval_type!=="operations_plan_ack" ||
        r.risk_level!=="low")
  )){
   void api.error("选中包含非白名单或没有权限的申请");return;
  }
  savingRef.current=true;
  setSaving(true);

  try{
   if(clearanceBatch){
    let approved=0;
    let closed=0;
    const unconfirmed:string[]=[];

    for(const row of rows){
     try{
      const result=await reviewClearanceApplication(
       row.id,row.version,"approved",note.trim()
      );

      if(result.status==="running"){
       approved++;
      }else if(result.status==="stock_closed"){
       closed++;
      }else{
       unconfirmed.push(row.title+" ("+row.business_ref+")");
      }
     }catch{
      unconfirmed.push(row.title+" ("+row.business_ref+")");
     }
    }

    window.dispatchEvent(
     new Event("szzsbj-clearance-application-updated")
    );

    const summary=
     "审批通过 "+approved+" 条，"+
     "库存售罄关闭 "+closed+" 条，"+
     "结果未确认 "+unconfirmed.length+" 条";

    setNote("");
    onCancel();
    onUpdated();

    if(unconfirmed.length){
     resultModal.info({
      title:"批量审批结果",
      content:<div>
       <p>{summary}</p>
       <p>以下申请请刷新后核实最新状态：</p>
       <ul>{unconfirmed.map((value,index)=>
        <li key={index}>{value}</li>
       )}</ul>
      </div>,
     });
    }else{
     void api.success(summary);
    }
    return;
   }

   const n=await approveLowRiskBatch(rows.map(r=>({id:r.id,version:r.version})),note.trim());
   void api.success("已完成 "+n+" 条低风险审批");
   setNote(""); onCancel();onUpdated();
  }catch{void api.error("批量审核失败：数据已变化或权限不足，本次操作未被接受");}
  finally{savingRef.current=false;setSaving(false);}
 };
 return <>
  {holder}
  {resultHolder}
  <Modal title={(clearanceBatch?"批量清货审批（":"批量通过低风险申请（")+rows.length+"条）"} open={rows.length>0}
   onCancel={()=>{if(!savingRef.current)onCancel();}}
   closable={!saving}
   keyboard={!saving}
   maskClosable={!saving}
   cancelButtonProps={{disabled:saving}}
   onOk={()=>void save()} okText="确认批量审批"
   okButtonProps={{loading:saving}}>
   <Alert type="warning" showIcon style={{marginBottom:16}}
    message={clearanceBatch?"批量通过清货申请":"仅允许运营计划低风险事项"}
    description={clearanceBatch
      ?"逐条核实最新库存、申请版本和审批权限。库存已售罄的申请将关闭，各申请独立提交并记录结果。"
      :"服务端会再次检查全部审批单版本、业务快照和审批权限。WFS 放弃跟进、采购、财务和权限变更均不允许批量通过。"} />
   <Form layout="vertical">
    <Form.Item label="批量审批理由（必填）">
     <Input.TextArea rows={4} maxLength={4000} showCount value={note}
      onChange={e=>setNote(e.target.value)}/>
    </Form.Item>
   </Form>
  </Modal>
 </>;
}
