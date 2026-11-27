/** Original clearance wizard look/steps with real scoped Listing data and API-backed submit. */
import { Button, Card, Checkbox, Divider, Form, Input, InputNumber, Modal, Progress, Select, Space, Spin, Table } from "antd";
import type { FormInstance } from "antd";
import type { ClearanceListing } from "./clearanceApi";

export interface LiveClearanceApplyFields { reason: string; methods: string[]; qty: number; note: string }
interface Props {
  openManual: boolean;
  openApply: boolean;
  manualFlow: boolean;
  selectedManual?: ClearanceListing;
  manualItems: ClearanceListing[];
  manualLoading: boolean;
  manualKeyword: string;
  onKeyword(value: string): void;
  onSearch(): void;
  onSelect(value: ClearanceListing): void;
  onNext(): void;
  onPrevious(): void;
  onClose(): void;
  onSubmit(): void;
  submitting: boolean;
  target?: ClearanceListing;
  form: FormInstance<LiveClearanceApplyFields>;
  onFinish(fields:LiveClearanceApplyFields):void;
}
const money=(v:unknown)=>{
  if(v===null||v===undefined||v==="")return "—";
  const n=Number(v);
  return Number.isFinite(n)?`$${n.toLocaleString("en-US",{minimumFractionDigits:2,maximumFractionDigits:2})}`:"—";
};
const integer=(n:number)=>n.toLocaleString("en-US",{maximumFractionDigits:0});
const reasons=["长期滞销","库存积压","持续亏损","利润过低","仓储成本压力","季节性商品过季","市场需求下降","竞争加剧","质量或售后问题","商品计划停售","其他原因"];
const methods=["降价","广告清货"];
export default function ClearanceLiveApplicationWizard({
  openManual,openApply,manualFlow,selectedManual,manualItems,manualLoading,manualKeyword,
  onKeyword,onSearch,onSelect,onNext,onPrevious,onClose,onSubmit,submitting,target,form,onFinish,
}:Props){
  const watchedQty=Form.useWatch("qty",form);
  const available=target?.available??0;
  const planned=typeof watchedQty==="number"&&Number.isInteger(watchedQty)?watchedQty:0;
  const percent=available>0?Math.max(0,Math.min(100,Math.round(planned/available*100))):0;
  const unitCost=target?.metrics.unit_inventory_cost_usd;
  const costNumber=unitCost===null||unitCost===undefined?null:Number(unitCost);
  const validCost=costNumber!==null&&Number.isFinite(costNumber)?costNumber:null;
  const suggestedRaw=target?.metrics.suggested_clearance_qty;
  const suggestedValue=suggestedRaw===null||suggestedRaw===undefined?null:Number(suggestedRaw);
  const recommended=suggestedValue!==null&&Number.isInteger(suggestedValue)&&suggestedValue>0
    ?Math.min(available,suggestedValue):null;
  return <Modal
    rootClassName={manualFlow?"clearance-apply-modal clearance-wizard-modal":"clearance-apply-modal"}
    title={manualFlow?<div className="clearance-apply-modal-title clearance-wizard-title">
      <span>CLEARANCE APPLICATION</span><strong>主动申请 SKU</strong>
      <small>选择一个商品，填写清货申请信息</small>
      <div className="clearance-wizard-steps">
        <div className={openManual?"clearance-wizard-step active":"clearance-wizard-step done"}><b>1</b>选择商品</div>
        <div className={!openManual?"clearance-wizard-step active":"clearance-wizard-step"}><b>2</b>填写申请</div>
      </div>
    </div>:<div className="clearance-apply-modal-title">
      <span>WFS CLEARANCE REQUEST</span><strong>提交 WFS 清货申请</strong>
      <small>核对库存、清货方式及目标数量后提交统一审批</small>
    </div>}
    width={manualFlow?1072:"min(1280px, 92vw)"}
    open={openManual||openApply} centered destroyOnHidden onCancel={onClose}
    styles={{body:{padding:0,display:"flex",flexDirection:"column",minHeight:0}}}
    footer={manualFlow?<div className="clearance-wizard-actions">
      <Button onClick={onClose}>取消</Button>
      {openManual?<Button type="primary" disabled={!selectedManual||selectedManual.available<=0} onClick={onNext}>下一步</Button>
        :<><Button onClick={onPrevious}>上一步</Button><Button type="primary" loading={submitting} onClick={onSubmit}>提交申请</Button></>}
    </div>:null}
  >
    {manualFlow&&<div className="clearance-wizard-pane" style={{display:openManual?"flex":"none"}}>
      <div className="clearance-wizard-rowtitle"><strong>选择清货商品</strong><small>一次仅能申请一个 SKU</small></div>
      <div className="clearance-wizard-search">
        <Input.Search allowClear placeholder="搜索商品名称、SKU、MSKU 或 Item ID"
          value={manualKeyword} onChange={event=>onKeyword(event.target.value)} onSearch={onSearch}/>
        <small>支持模糊搜索</small>
      </div>
      <Spin spinning={manualLoading}>
        <Table<ClearanceListing> rowKey={row=>`${row.source_account_ref}:${row.store_id}:${row.item_id}`}
          className="clearance-wizard-table" showHeader={false} size="small" tableLayout="fixed"
          dataSource={manualItems} pagination={false} scroll={{y:400}}
          rowClassName={row=>selectedManual?.item_id===row.item_id&&selectedManual.store_id===row.store_id&&selectedManual.source_account_ref===row.source_account_ref?"clearance-wizard-chosen":row.available<=0?"clearance-wizard-ineligible":""}
          columns={[
            {title:"商品",render:(_,row)=><div className="clearance-wizard-product">
              <span className="clearance-wizard-thumb">▦</span><div className="clearance-wizard-product-text">
                <strong>{row.title||row.item_id}</strong>
                <span>{row.sku||"—"} · {row.msku||"—"}</span>
                <small>{row.store_name||row.store_id} · {row.item_id}</small>
              </div></div>},
            {title:"WFS可售",width:120,render:(_,row)=><div className="clearance-wizard-meta"><small>WFS 可售</small><strong>{integer(row.available)} 件</strong></div>},
            {title:"当前售价",width:120,render:(_,row)=><div className="clearance-wizard-meta"><small>当前售价</small><strong>{money(row.price_amount)}</strong></div>},
            {title:"选择",width:90,render:(_,row)=><Button size="small" disabled={row.available<=0}
              className={selectedManual?.item_id===row.item_id&&selectedManual.store_id===row.store_id&&selectedManual.source_account_ref===row.source_account_ref?"clearance-wizard-select is-selected":"clearance-wizard-select"}
              onClick={()=>onSelect(row)}>{selectedManual?.item_id===row.item_id&&selectedManual.store_id===row.store_id&&selectedManual.source_account_ref===row.source_account_ref?"已选择":"选择"}</Button>},
          ]}/>
      </Spin>
    </div>}
    <div className="clearance-wizard-existing-form" style={{display:openManual?"none":"flex"}}>
      {openApply&&target&&<div className="clearance-apply-body">
        <div className="clearance-apply-content">
          <div className="clearance-apply-product-summary">
            <div className="clearance-apply-product-identity"><div className="clearance-apply-product-icon">▧</div>
              <div><strong>{target.title||target.item_id}</strong>
                <span>SKU：{target.sku||"—"}{"\u3000"}MSKU：{target.msku||"—"}</span>
              </div></div>
            <div className="clearance-apply-summary-metric"><span>WFS 可售</span><strong>{integer(available)} 件</strong></div>
            <div className="clearance-apply-summary-metric"><span>单件库存成本</span><strong>{money(unitCost)}</strong></div>
            <div className="clearance-apply-summary-metric"><span>系统建议数量</span><strong>{recommended===null?"待评估":`${integer(recommended)} 件`}</strong></div>
          </div>
          <Form<LiveClearanceApplyFields> form={form} layout="vertical" className="clearance-apply-form" onFinish={onFinish}>
            <div className="clearance-apply-layout">
              <Card className="clearance-apply-plan-card" title="清货计划" extra={<span>带 * 的项目为必填</span>}>
                <div className="clearance-apply-fields">
                  <Form.Item name="reason" label="清货原因" rules={[{required:true,message:"请选择清货原因"}]}>
                    <Select options={reasons.map(value=>({label:value,value}))} size="large" placeholder="请选择清货原因"/>
                  </Form.Item>
                  <Form.Item name="methods" label="清货方式（可多选）" rules={[{required:true,type:"array",min:1,message:"请选择清货方式"}]}>
                    <Checkbox.Group className="clearance-apply-methods" options={methods.map(value=>({label:value,value}))}/>
                  </Form.Item>
                </div>
                <div className="clearance-apply-quantity-section">
                  <div className="clearance-apply-section-label"><span className="required-mark">*</span>目标清货数量</div>
                  <div className="clearance-apply-quantity-row">
                    <div className="clearance-apply-quantity-controls">
                      <Button htmlType="button" onClick={()=>form.setFieldValue("qty",Math.max(1,planned-1))}>−</Button>
                      <Form.Item name="qty" noStyle rules={[{required:true,message:"请输入清货数量"},{type:"number",min:1,max:available,message:"数量不能超过WFS可售库存"}]}>
                        <InputNumber size="large" controls={false} min={1} max={available} precision={0} style={{width:"100%"}}/>
                      </Form.Item>
                      <Button htmlType="button" onClick={()=>form.setFieldValue("qty",Math.min(available,planned+1))}>+</Button>
                    </div>
                    <Button htmlType="button" className="clearance-apply-recommended" disabled={recommended===null}
                      onClick={()=>{if(recommended!==null)form.setFieldValue("qty",recommended);}}>使用建议数量</Button>
                    <div className="clearance-apply-field-hint">可手动调整，不超过 WFS 可售库存 {integer(available)} 件</div>
                  </div>
                </div>
                <Divider/>
                <Form.Item name="note" label="申请说明（选填）">
                  <Input.TextArea rows={4} maxLength={4000} style={{resize:"none"}} placeholder="填写清货原因及执行安排"/>
                </Form.Item>
              </Card>
              <Card className="clearance-apply-preview-card" title="库存影响预览" extra={<span>随计划清货数量自动更新</span>}>
                <div className="clearance-apply-cost-highlight">
                  <span>目标库存成本</span><strong>{validCost===null?"—":money(planned*validCost)}</strong>
                  <small>计划清货数量 × 可核实的单件库存成本</small>
                </div>
                <div className="clearance-apply-preview-row"><span>计划清货数量</span><strong>{integer(planned)} 件</strong></div>
                <div className="clearance-apply-preview-row"><span>清货覆盖比例</span><strong>{percent}%</strong></div>
                <div className="clearance-apply-preview-row"><span>清货后可售库存</span>
                  <strong className="clearance-apply-remaining">{integer(Math.max(0,available-planned))} 件</strong></div>
                <Progress percent={percent} showInfo={false} strokeColor="#1677ff" trailColor="#e7edf6"/>
                <div className="clearance-apply-progress-labels"><span>计划清货</span><span>剩余库存</span></div>
                <div className="clearance-apply-measure-note"><strong>测算说明</strong>
                  <p>清货计划只提交人工审批；不自动修改 Walmart 价格或广告。</p></div>
              </Card>
            </div>
          </Form>
        </div>
        <div className="clearance-apply-footer"><span>请核对商品、数量及清货方式</span>
          <Space size={12}><Button size="large" onClick={onClose}>取消</Button>
            <Button size="large" type="primary" loading={submitting} onClick={onSubmit}>提交申请</Button></Space></div>
      </div>}
    </div>
  </Modal>;
}
