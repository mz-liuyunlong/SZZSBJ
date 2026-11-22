// NP_PURCHASE_REAPPLY_SELF_CONTAINED_V5
import {useRef,useState} from "react";
import {Button, Input, InputNumber, Modal, message} from "antd";
import {useQueryClient} from "@tanstack/react-query";
import type {Product} from "./nativeData";
import {submitNewProductPurchase} from "./newProductBusinessApi";

export default function PurchaseReapplyButton({product}:{product:Product}) {
  const queryClient=useQueryClient();
  const [open,setOpen]=useState(false);
  const [quantity,setQuantity]=useState<number|null>(null);
  const [reason,setReason]=useState("");
  const latestReason=useRef("");
  const [saving,setSaving]=useState(false);
  const backend=product.backend;
  const suggested=backend?.suggestedQty??null;
  const grade=backend?.evaluation.grade??null;
  const eligible=Boolean(backend && backend.evaluation.total!==null &&
    grade!==null && ["S","A","B","C"].includes(grade));
  const submit=async()=>{
    if(!backend || saving) return;
    const submittedReason=latestReason.current.trim();
    const nonBlankCount=Array.from(
      submittedReason.replace(/\s/gu,"")
    ).length;
    if(!eligible){message.error("当前缺少有效正式评级，不能重新申请");return;}
    if(!Number.isSafeInteger(quantity) || quantity===null || quantity<1 || quantity>100000){
      message.error("请输入1至100000之间的整数采购数量");return;
    }
    if((suggested===null || quantity!==suggested) && nonBlankCount<10){
      message.error(`申请说明至少需要10个非空白字符，当前${nonBlankCount}个`);
      return;
    }
    setSaving(true);
    try{
      await submitNewProductPurchase(backend.identity,quantity,submittedReason,backend.ruleVersion);
      setOpen(false);
      message.success("新采购申请已提交，原驳回记录保留");
      await Promise.all([
        queryClient.invalidateQueries({queryKey:["np-performance"]}),
        queryClient.invalidateQueries({queryKey:["np-board"]}),
      ]);
    }catch(error){
      const detail=error instanceof Error
        ?error.message:"重新申请失败，请核实当前评分与采购规则";
      if(nonBlankCount>=10 &&
         /NEW_PRODUCT_PURCHASE_REASON_REQUIRED|至少10个非空白字符/.test(detail)){
        message.error(`本地已有${nonBlankCount}个非空白字符，但服务端仍拒绝。需检查请求Payload及服务端校验。`);
      }else{
        message.error(detail);
      }
    }finally{setSaving(false);}
  };
  return <>
    <Button size="small" type="primary" onClick={()=>{
      setQuantity(suggested??product.requestQty??null);
      latestReason.current="";
      setReason("");
      setOpen(true);
    }}>重新申请</Button>
    {open && <Modal open title="重新申请采购" okText="重新提交审核"
      okButtonProps={{loading:saving}} cancelText="取消" onOk={()=>{void submit();}}
      onCancel={()=>{if(!saving)setOpen(false);}} destroyOnHidden>
      <div style={{display:"grid",gap:12}}>
        <div>上次驳回原因：{backend?.purchaseReviewReason||"历史记录未提供驳回原因"}</div>
        {backend?.purchaseReviewedAt && <div>驳回时间：{backend.purchaseReviewedAt.slice(0,19).replace("T"," ")}</div>}
        <div>当前评级：{grade??"—"}　系统建议：{suggested===null?"未核实":`${suggested} 件`}</div>
        <label>本次申请数量</label>
        <InputNumber style={{width:"100%"}} min={1} max={100000} precision={0}
          value={quantity} onChange={setQuantity}/>
        <label>重新申请说明（数量与系统建议不同或建议未核实时必填，至少10个非空白字符）</label>
        <Input.TextArea rows={3} value={reason}
          onChange={e=>{
            latestReason.current=e.target.value;
            setReason(e.target.value);
          }}/>
        <div aria-live="polite">
          已输入 {Array.from(reason.replace(/\s/gu,"")).length} 个非空白字符
        </div>
        <div style={{color:"#667085"}}>重新提交将创建新的采购申请，原驳回记录不会被覆盖。</div>
      </div>
    </Modal>}
  </>;
}

// NP_REAPPLY_REASON_10_NONBLANK_V6
