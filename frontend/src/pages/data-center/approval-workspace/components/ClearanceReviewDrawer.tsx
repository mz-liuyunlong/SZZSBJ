/** Only clearance-specific approval UI is affected; other approval types remain unchanged. */
import { useEffect, useState } from "react";
import { Button, Descriptions, Drawer, Input, List, Modal, Space, Spin, Tag, Typography, message } from "antd";
import type { ApprovalItem } from "../approvalTypes";
import { getClearanceApplication, reviewClearanceApplication, type ApplicationDetail } from "@/pages/products/clearance/clearanceApi";

interface Props {
  selected?: ApprovalItem;
  canReview: boolean;
  directAction?: "approved" | "rejected";
  onClose(): void;
  onUpdated(): void;
}
const riskName: Record<string,string>={high:"高风险",medium:"中风险",low:"低风险",unknown:"待评估"};
const time=(v:string|null|undefined)=>v?new Date(v).toLocaleString("zh-CN"):"—";

// CLEARANCE_HOOKS_V4_REVIEW: remount per approval/intent; no prop-driven setState effect.
export default function ClearanceReviewDrawer(props: Props) {
  return <ClearanceReviewDrawerInner
    key={`${props.selected?.id ?? "closed"}:${props.directAction ?? "detail"}`}
    {...props}
  />;
}
function ClearanceReviewDrawerInner({selected,canReview,directAction,onClose,onUpdated}:Props){
  const [data,setData]=useState<ApplicationDetail>();
  const [loading,setLoading]=useState(Boolean(selected));
  const [saving,setSaving]=useState(false);
  const [action,setAction]=useState<"approved" | "rejected" | undefined>(directAction);
  const [note,setNote]=useState("");
  const [messageApi,holder]=message.useMessage();
  useEffect(()=>{
    if(!selected)return;
    let active=true;
    void getClearanceApplication(selected.id).then(d=>{if(active)setData(d);}).catch(()=>{if(active)void messageApi.error("清货审批详情加载失败");})
      .finally(()=>{if(active)setLoading(false);});
    return()=>{active=false;};
  },[selected,messageApi]);
  const apply=async()=>{
    if(!data||!action||saving||!canReview||data.application.status!=="pending")return;
    if(action==="rejected"&&!note.trim()){void messageApi.warning("驳回原因必填");return;}
    setSaving(true);
    try {
      const result=await reviewClearanceApplication(data.application.id,data.application.version,action,note.trim());
      void messageApi.success(result.status==="stock_closed"?"WFS库存已归零，申请自动关闭":action==="approved"?"审批通过，清货任务已进入执行中":"申请已驳回");
      onClose();onUpdated();
    }catch{void messageApi.error("审批失败：请核对最新库存、申请状态、版本或权限");}
    finally{setSaving(false);}
  };
  const current=data?.current;
  const record=data?.application;
  return <>{holder}
    <Drawer title="清货审批详情 · 最新数据" width={740} open={Boolean(selected&&!directAction)} onClose={onClose} destroyOnHidden>
      {loading?<Spin/>:record&&current?<>
        <Typography.Title level={5}>{current.title||record.item_id}</Typography.Title>
        <Typography.Text type="secondary">Item ID：{record.item_id} · {current.sku||"—"} · {record.store_name||record.store_id}</Typography.Text>
        <Descriptions bordered size="small" column={2} style={{marginTop:16}} items={[
          {key:"risk-submission",label:"申请时风险",children:<Tag>{riskName[record.risk_at_submission]}</Tag>},
          {key:"risk-current",label:"当前风险",children:<Tag>{riskName[current.risk]}</Tag>},
          {key:"qty",label:"申请数量",children:`${record.requested_qty} 件`},
          {key:"stock",label:"WFS最新可售",children:`${current.available} 件`},
          {key:"owner",label:"负责人",children:current.owner||"—"},
          {key:"applicant",label:"申请人",children:record.applicant_ref},
          {key:"method",label:"清货方式",children:record.methods_json.join("、")},
          {key:"reason",label:"清货原因",children:record.reason},
          {key:"note",label:"申请说明",children:record.note||"—"},
          {key:"time",label:"提交时间",children:time(record.submitted_at)},
          {key:"rule",label:"申请时规则版本",children:`V${record.rule_version}`},
          {key:"sold",label:"已销售",children:Number(record.sold_qty).toLocaleString()},
        ]}/>
        <Typography.Title level={5} style={{marginTop:18}}>经营分析与库存风险</Typography.Title>
        <Descriptions size="small" bordered column={2} items={[
          {key:"sales",label:"近30天销量",children:current.metrics.sales_30d??"—"},
          {key:"profit",label:"近30天利润",children:current.metrics.profit_30d_usd??"—"},
          {key:"stockcost",label:"可售库存成本",children:current.metrics.capital_at_cost_usd??"—"},
          {key:"sellout",label:"预计售罄天数",children:current.metrics.sellout_days??"暂无法预计"},
          {key:"rating",label:"Listing评分",children:current.metrics.rating??"—"},
          {key:"margin",label:"单件毛利空间",children:current.metrics.unit_margin_usd??"—"},
        ]}/>
        <List size="small" dataSource={current.reasons} renderItem={item=><List.Item>{item}</List.Item>}/>
        <Space style={{width:"100%",justifyContent:"center",marginTop:18}}>
          <Button onClick={onClose}>关闭</Button>
          {canReview&&record.status==="pending"&&<>
            <Button onClick={()=>{setAction("rejected");setNote("");}}>驳回</Button>
            <Button type="primary" onClick={()=>{setAction("approved");setNote("");}}>审批通过</Button>
          </>}
        </Space>
      </>:<Typography.Text type="secondary">暂无可用审批详情</Typography.Text>}
    </Drawer>
    <Modal title={action==="approved"?"审批通过":"驳回申请"} open={Boolean(selected&&action)}
      centered width={420} okText={action==="approved"?"确认通过":"确认驳回"}
      okButtonProps={{loading:saving,disabled:!data||!canReview}}
      onOk={()=>void apply()} onCancel={()=>{setAction(undefined);if(directAction)onClose();}} destroyOnHidden>
      <Typography.Text>{action==="approved"?"审批意见（选填）":"驳回原因（必填）"}</Typography.Text>
      <Input.TextArea value={note} onChange={e=>setNote(e.target.value)}
        placeholder={action==="approved"?"审批意见（选填）":"请输入驳回原因"}
        rows={4} style={{resize:"none",marginTop:8}}/>
    </Modal>
  </>;
}
