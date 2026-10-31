import { useMemo, useState } from "react";
import {
 Button, Card, Checkbox, DatePicker, Divider, Drawer, Form, Input, InputNumber,
 Modal, Progress, Select, Space, Switch, Table, Tag, Timeline, Typography, message,
} from "antd";
import dayjs from "dayjs";
import type { ColumnsType } from "antd/es/table";
import {
 CLEARANCE_PRODUCTS, DEFAULT_RULES, METHODS, REASONS, STATUS_NAMES, activeTaskFor,
 chinaToday, coverage, evaluateProduct, findProduct,
 taskCost, taskProgress, taskQty, taskRemoved, taskRisk, taskSold, taskStore, validateRules,
 type ClearanceProduct, type ClearanceRules, type ClearanceTask, type ClearanceTaskLine,
 type RulesHistory, type StoredClearance,
} from "./clearanceModel";
import { integer, money, percent, RiskTag, StatusTag } from "./clearanceUi";

const ruleNumbers: {key:keyof ClearanceRules;label:string;unit:string}[]=[
 {key:"highCoverage",label:"高风险：预计售罄≥",unit:"天"},
 {key:"mediumCoverage",label:"中风险：预计售罄≥",unit:"天"},
 {key:"assistCoverage",label:"辅助准入：预计售罄≥",unit:"天"},
 {key:"mediumAge",label:"中风险：平均库龄≥",unit:"天"},
 {key:"agedLotDays",label:"高风险：库龄批次超过",unit:"天"},
 {key:"agedLotMin",label:"高风险：超龄库存至少",unit:"件"},
 {key:"minListingDays",label:"至少在售",unit:"天"},
 {key:"minBusinessSignals",label:"至少满足经营异常",unit:"项"},
 {key:"salesDropPercent",label:"近7天相比前7天下滑≥",unit:"%"},
 {key:"adRateIncrease",label:"广告占比上升≥",unit:"百分点"},
 {key:"returnRate",label:"30天退货率≥",unit:"%"},
 {key:"ratingThreshold",label:"评分低于",unit:"分"},
];
const ruleBools:{key:keyof ClearanceRules;label:string}[]=[
 {key:"enableCoverage",label:"按售罄天数判断"},
 {key:"enableZero",label:"零销量识别"},
 {key:"enableAged",label:"超龄库存批次"},
 {key:"enableAverageAge",label:"按平均库龄判断"},
 {key:"enableAssisted",label:"库存 + 经营辅助准入"},
 {key:"enableProfit",label:"持续亏损信号"},
 {key:"enableDecline",label:"销售下滑信号"},
 {key:"enableAd",label:"广告占比异常信号"},
 {key:"enableReturns",label:"高退货率信号"},
 {key:"enableRating",label:"低评分信号"},
];
const deepCopy=<T,>(x:T):T=>JSON.parse(JSON.stringify(x)) as T;
const counts=(products:ClearanceProduct[],rules:ClearanceRules)=>products.filter(x=>evaluateProduct(x,rules).auto).length;
interface Props {data:StoredClearance;onChange:(data:StoredClearance)=>void;role:string}
export function ClearanceRulesPanel({data,onChange,role}:Props){
 const [draft,setDraft]=useState<ClearanceRules>(()=>({...data.rules}));
 const [showHistory,setShowHistory]=useState(false);
 const error=validateRules(draft);
 const diff=useMemo(()=>CLEARANCE_PRODUCTS.flatMap(x=>{
  const before=evaluateProduct(x,data.rules),after=evaluateProduct(x,draft);
  if(before.auto===after.auto&&before.level===after.level)return [];
  return [{id:x.id,sku:x.sku,before,after,kind:!before.auto&&after.auto?"新入池":before.auto&&!after.auto?"退出":"等级变化"}];
 }),[data.rules,draft]);
 const apply=()=>{
  const invalid=validateRules(draft);if(invalid){void message.error(invalid);return;}
  const changes=Object.keys(draft).filter(k=>draft[k as keyof ClearanceRules]!==data.rules[k as keyof ClearanceRules]);
  if(!changes.length){void message.info("规则未发生变化");return;}
  const version=data.ruleVersion+1;
  const row:RulesHistory={version,actor:role,at:chinaToday(),summary:changes.join("、")+"；新增 "+diff.filter(x=>x.kind==="新入池").length+"、退出 "+diff.filter(x=>x.kind==="退出").length+"、等级变化 "+diff.filter(x=>x.kind==="等级变化").length};
  onChange({...data,rules:deepCopy(draft),ruleVersion:version,ruleHistory:[row,...data.ruleHistory].slice(0,20)});
  void message.success("规则 V"+version+" 已保存并应用（仅本地 Mock）");
 };
 return <div className="clearance-rule-page">
  <div className="clearance-rule-intro"><div><Typography.Title level={4}>清货规则配置</Typography.Title><Typography.Text type="secondary">统一维护自动识别规则 · 生效版本 V{data.ruleVersion} · 影响预览确认后才保存</Typography.Text></div><Space><Tag>1 修改阈值</Tag><Tag>2 预览命中</Tag><Tag color="processing">3 保存应用</Tag></Space></div>
  <div className="clearance-rule-overview">
   <Card size="small"><Typography.Text type="secondary">识别模式</Typography.Text><strong>库存准入</strong><Typography.Text type="secondary">经营风险辅助，不单独入池</Typography.Text></Card>
   <Card size="small"><Typography.Text type="secondary">当前规则版本</Typography.Text><strong>V{data.ruleVersion}</strong><Typography.Text type="secondary">本地模拟版本记录</Typography.Text></Card>
   <Card size="small"><Typography.Text type="secondary">全量分析 SKU</Typography.Text><strong>{CLEARANCE_PRODUCTS.length}</strong><Typography.Text type="secondary">包含全部 Mock 商品</Typography.Text></Card>
   <Card size="small"><Typography.Text type="secondary">生效范围</Typography.Text><strong>全店铺</strong><Typography.Text type="secondary">当前采用一套全局规则</Typography.Text></Card>
  </div>
  <div className="clearance-rule-body">
  <Card title="自动识别条件" size="small" extra={<Typography.Text type="secondary">仅演示 · 正式版需要授权</Typography.Text>}>
   <Typography.Text strong>01 · 库存风险阈值</Typography.Text>
   <div className="clearance-rule-fields">{ruleNumbers.slice(0,6).map(f=><label key={f.key} className="clearance-rule-field"><span>{f.label}</span><Space.Compact block><InputNumber style={{width:"100%"}} value={Number(draft[f.key])} onChange={n=>setDraft(old=>({...old,[f.key]:n??NaN}))}/><Button disabled>{f.unit}</Button></Space.Compact></label>)}</div>
   <Divider/><Typography.Text strong>02 · 滞销及新品保护</Typography.Text>
   <div className="clearance-rule-fields"><label className="clearance-rule-field"><span>零销量观察窗口</span><Select value={draft.zeroLookback} options={[7,14,30].map(n=>({value:n,label:"最近 "+n+" 天"}))} onChange={n=>setDraft(old=>({...old,zeroLookback:n as 7|14|30}))}/></label>{ruleNumbers.slice(6,7).map(f=><label className="clearance-rule-field" key={f.key}><span>{f.label}</span><InputNumber style={{width:"100%"}} value={Number(draft[f.key])} onChange={n=>setDraft(old=>({...old,[f.key]:n??NaN}))}/></label>)}</div>
   <Divider/><Typography.Text strong>03 · 经营风险辅助（不单独入池）</Typography.Text>
   <div className="clearance-rule-fields">{ruleNumbers.slice(7).map(f=><label key={f.key} className="clearance-rule-field"><span>{f.label}</span><Space.Compact block><InputNumber style={{width:"100%"}} value={Number(draft[f.key])} onChange={n=>setDraft(old=>({...old,[f.key]:n??NaN}))}/><Button disabled>{f.unit}</Button></Space.Compact></label>)}</div>
   <Divider/><Typography.Text strong>04 · 识别条件开关</Typography.Text>
   <div className="clearance-rule-toggles">{ruleBools.map(f=><label key={f.key}><Switch size="small" checked={Boolean(draft[f.key])} onChange={v=>setDraft(old=>({...old,[f.key]:v}))}/>{f.label}</label>)}</div>
   <Divider/><Space wrap><Button onClick={()=>setDraft({...data.rules})}>放弃修改</Button><Button onClick={()=>setDraft({...DEFAULT_RULES})}>载入默认值</Button><Button type="primary" disabled={Boolean(error)||JSON.stringify(draft)===JSON.stringify(data.rules)} onClick={apply}>保存并应用</Button></Space>
   {error&&<Typography.Text type="danger" className="clearance-block">{error}</Typography.Text>}
  </Card>
  <Card title="规则调整影响预览" size="small" extra={<Tag color={JSON.stringify(draft)===JSON.stringify(data.rules)?"success":"warning"}>{JSON.stringify(draft)===JSON.stringify(data.rules)?"已应用配置":"未保存草稿"}</Tag>}>
   <div className="clearance-impact"><div>当前自动入池<strong>{counts(CLEARANCE_PRODUCTS,data.rules)}</strong></div><div>预览自动入池<strong>{counts(CLEARANCE_PRODUCTS,draft)}</strong></div><div>人工申请 SKU<strong>{data.manual.length}</strong></div></div>
   <div className="clearance-impact"><div>新增识别<strong>+{diff.filter(x=>x.kind==="新入池").length}</strong></div><div>退出候选<strong>{diff.filter(x=>x.kind==="退出").length}</strong></div><div>风险等级变化<strong>{diff.filter(x=>x.kind==="等级变化").length}</strong></div></div>
   <Table size="small" rowKey="id" pagination={{pageSize:8}} dataSource={diff} columns={[{title:"SKU",dataIndex:"sku"},{title:"原风险",render:(_,r)=><RiskTag level={r.before.level}/>},{title:"预览风险",render:(_,r)=><RiskTag level={r.after.level}/>},{title:"变化",dataIndex:"kind"}]}/>
   <Typography.Paragraph type="secondary">规则变化不删除人工申请、有效任务和审批历史，也不会触发调价、库存移除、弃置或自动审批。</Typography.Paragraph>
   <Divider/><Button type="link" onClick={()=>setShowHistory(true)}>查看规则版本与操作留痕（{data.ruleHistory.length}）</Button>
  </Card></div>
  <Drawer title="规则版本与操作留痕（Mock）" open={showHistory} onClose={()=>setShowHistory(false)}><Timeline items={data.ruleHistory.map(h=>({children:<><strong>V{h.version} · {h.actor} · {h.at}</strong><p>{h.summary}</p></>}))}/></Drawer>
 </div>;
}

interface ApplyDraft {ids:string[];editId?:string;source:"auto"|"manual"}
interface ApplyValues {reason:string;methods:string[];due:dayjs.Dayjs;remark:string;quantities:Record<string,number>}
interface ModalsProps extends Props {
 applicant:string|null;setApplicant:(x:string|null)=>void;
 manualOpen:boolean;setManualOpen:(x:boolean)=>void;
 taskId:string|null;setTaskId:(x:string|null)=>void;
 apply:ApplyDraft|null;setApply:(x:ApplyDraft|null)=>void;
}
const productColumns:ColumnsType<ClearanceProduct>=[
 {title:"SKU / 商品",render:(_,x)=><><strong>{x.sku}</strong><div className="clearance-subline">{x.name}</div></>},
 {title:"店铺",dataIndex:"store"},{title:"负责人",dataIndex:"owner"},
 {title:"风险",render:()=>null},{title:"WFS可售",dataIndex:"avail"},
];
export function ClearanceDialogs({data,onChange,role,applicant,setApplicant,manualOpen,setManualOpen,taskId,setTaskId,apply,setApply}:ModalsProps){
 const [manualSelection,setManualSelection]=useState<string[]>([]);
 const [manualSearch,setManualSearch]=useState("");
 const [manualStore,setManualStore]=useState("all");
 const [removeTarget,setRemoveTarget]=useState<string|null>(null);
 const [removeNote,setRemoveNote]=useState("");
 const [form]=Form.useForm<ApplyValues>();
 const [progressForm]=Form.useForm<{lines:Record<string,{sold:number;removed:number;disposed:number}>}>();
 const product=applicant?findProduct(applicant):undefined;
 const task=taskId?data.tasks.find(t=>t.id===taskId):undefined;
 const change=(patch:Partial<StoredClearance>)=>onChange({...data,...patch});
 const begin=(ids:string[],source:"auto"|"manual",editId?:string)=>{
  if(!ids.length)return;
  const ps=ids.map(findProduct);
  if(ps.some(x=>!x||x.owner!==role||x.avail<=0||(!editId&&activeTaskFor(data.tasks,x.id)))){void message.error("SKU 无权限、无库存或已有有效申请");return;}
  if(new Set(ps.map(x=>x?.store)).size!==1){void message.error("同一清货申请仅允许同一店铺的 SKU");return;}
  setManualSelection([]);setApply({ids,source,editId});setApplicant(null);setTaskId(null);
 };
 const closeApply=()=>{setApply(null);form.resetFields();};
 const old=apply?.editId?data.tasks.find(x=>x.id===apply.editId):undefined;
 const applyProducts=apply?.ids.map(findProduct).filter((x):x is ClearanceProduct=>Boolean(x))??[];
 const submit=(values:ApplyValues)=>{
  if(!apply)return;
  const quantities=values.quantities||{};
  if(applyProducts.some(x=>x.owner!==role||x.avail<=0)||(!old&&applyProducts.some(x=>activeTaskFor(data.tasks,x.id)))||new Set(applyProducts.map(x=>x.store)).size!==1){void message.error("SKU 权限、库存、重复申请或店铺校验失败");return;}
  if(applyProducts.some(x=>!Number.isInteger(quantities[x.id])||quantities[x.id]<1||quantities[x.id]>x.avail)){void message.error("每个 SKU 的申请数量必须为正整数且不超过可售库存");return;}
  const now=chinaToday();
  if(!values.remark.trim()){void message.error("申请说明不能为空");return;}
  if(values.due.format("YYYY-MM-DD")<now){void message.error("计划完成日期不得早于今天");return;}
  const lines:ClearanceTaskLine[]=applyProducts.map(x=>({id:x.id,qty:quantities[x.id],sold:old?.lines.find(l=>l.id===x.id)?.sold??0,removed:old?.lines.find(l=>l.id===x.id)?.removed??0,disposed:old?.lines.find(l=>l.id===x.id)?.disposed??0}));
  const nextTasks=deepCopy(data.tasks);
  if(old){
   const pos=nextTasks.findIndex(t=>t.id===old.id);
   if(!["supplement","rejected"].includes(old.status)){void message.error("当前状态不允许重提");return;}
   nextTasks[pos]={...old,lines,status:"pending",reason:values.reason,methods:values.methods,due:values.due.format("YYYY-MM-DD"),remark:values.remark.trim(),version:old.version+1,ruleVersion:data.ruleVersion,submitted:now+" 18:52",history:[...old.history,{at:now+" 18:52",who:role,text:"补充资料并重新提交审批"}]};
   nextTasks[pos].riskAtSubmission=taskRisk(nextTasks[pos],data.rules);
  }else{
   const n=Math.max(6,...nextTasks.map(t=>Number(t.id.split("-").pop())||0))+1;
   const fresh:ClearanceTask={id:"CH-1024-"+String(n).padStart(3,"0"),lines,status:"pending",reason:values.reason,methods:values.methods,owner:role,requester:role,approver:"李主管",date:now,due:values.due.format("YYYY-MM-DD"),submitted:now+" 18:52",remark:values.remark.trim(),source:apply.source,version:1,ruleVersion:data.ruleVersion,riskAtSubmission:"low",history:[{at:now+" 18:52",who:role,text:"提交清货申请至统一审批工作台（本地演示）"}]};
   fresh.riskAtSubmission=taskRisk(fresh,data.rules);nextTasks.unshift(fresh);
  }
  change({tasks:nextTasks,manual:apply.source==="manual"?[...new Set([...data.manual,...apply.ids])]:data.manual});
  closeApply();void message.success("申请已加入清货管理（仅本地 Mock，不会发送真实审批）");
 };
 const updateStatus=(t:ClearanceTask,command:"start"|"pause"|"resume"|"withdraw"|"finish")=>{
  const transitions={start:["ready","running"],pause:["running","paused"],resume:["paused","running"],withdraw:["pending","cancelled"],finish:["running","done"]} as const;
  const [from,to]=transitions[command];
  if(t.owner!==role||t.status!==from||(command==="finish"&&taskProgress(t)!==100)){void message.error("当前身份或任务状态不允许此操作");return;}
  const tasks=data.tasks.map(row=>row.id!==t.id?row:{...row,status:to,history:[...row.history,{at:chinaToday(),who:role,text:"状态更新："+STATUS_NAMES[to]}]});
  change({tasks});void message.success("已更新模拟任务状态");
 };
 const taskProgressSave=(values:{lines:Record<string,{sold:number;removed:number;disposed:number}>})=>{
  if(!task||task.status!=="running"||task.owner!==role)return;
  const lines=task.lines.map(row=>({...row,...values.lines?.[row.id]}));
  for(const line of lines){
   const before=task.lines.find(x=>x.id===line.id)!;
   const nums=[line.sold,line.removed,line.disposed];
   if(nums.some((n,i)=>!Number.isInteger(n)||n<[before.sold,before.removed,before.disposed][i])||nums.reduce((a,b)=>a+b,0)>line.qty){void message.error("累计进度不得倒退、不得超过目标量，必须为整数");return;}
  }
  change({tasks:data.tasks.map(x=>x.id===task.id?{...x,lines,history:[...x.history,{at:chinaToday(),who:role,text:"更新累计执行进度"}]}:x)});
  setProgressOpen(false);void message.success("执行进度已保存（Mock）");
 };
 const [progressOpen,setProgressOpen]=useState(false);
 const selectables=CLEARANCE_PRODUCTS.filter(x=>(manualStore==="all"||x.store===manualStore)&&[x.name,x.sku,x.item,x.msku].some(v=>v.toLowerCase().includes(manualSearch.toLowerCase())));
 const selected=manualSelection.map(findProduct).filter((x):x is ClearanceProduct=>Boolean(x));
 const eligible=(x:ClearanceProduct)=>x.avail>0&&x.owner===role&&!activeTaskFor(data.tasks,x.id);
 return <>
  <Drawer title={product?product.name+" · SKU 深度分析":"SKU 详情"} size="large" open={Boolean(product)} onClose={()=>setApplicant(null)} extra={product&&eligible(product)?<Button type="primary" onClick={()=>begin([product.id],data.manual.includes(product.id)?"manual":"auto")}>申请清货</Button>:null}>
  {product&&<><div className="clearance-detail-grid">{[["商品ID",product.item],["SKU",product.sku],["MSKU",product.msku],["店铺",product.store],["负责人",product.owner],["当前售价",money(product.price)],["可售库存",integer(product.avail)],["售罄天数",coverage(product)==null?"无法估算":coverage(product)+"天"],["库存成本",money(product.avail*product.cost)],["平均库龄",product.age+"天"],["评分",product.rating+" / 5"],["30天退货",product.returns+" 次"]].map(([label,value])=><Card key={label} size="small"><Typography.Text type="secondary">{label}</Typography.Text><strong>{value}</strong></Card>)}</div>
  <Divider orientation="left">7 / 14 / 30 天经营指标对比</Divider>
  <Table rowKey="key" size="small" pagination={false} dataSource={([["units","销量"],["daily","日均销量"],["revenue","销售额"],["ads","广告费"],["adRate","广告占比"],["profit","利润"],["profitRate","利润率"]] as const).map(([key,label])=>({key,label}))} columns={[{title:"指标",dataIndex:"label"},...[7,14,30].map(days=>({title:days+"天",render:(_:unknown,row:{key:string})=>{const x=product.per[days as 7|14|30];return row.key==="units"?integer(x.units):row.key==="daily"?(x.units/days).toFixed(2):row.key==="revenue"?money(x.revenue):row.key==="ads"?money(x.ads):row.key==="adRate"?percent(x.adRate):row.key==="profit"?money(x.profit):percent(x.margin);}}))]}/>
  <Divider orientation="left">风险决策依据</Divider>{data.manual.includes(product.id)&&eligible(product)&&<Button danger size="small" onClick={()=>setRemoveTarget(product.id)}>移出人工清货候选</Button>}<RiskTag level={evaluateProduct(product,data.rules).level}/>{evaluateProduct(product,data.rules).reasons.map(x=><Typography.Paragraph key={x}>• {x}</Typography.Paragraph>)}{evaluateProduct(product,data.rules).business.map(x=><Tag color="warning" key={x}>{x}</Tag>)}
  </>}</Drawer>
  <Modal title="运营主动申请清货" width={900} open={manualOpen} onCancel={()=>setManualOpen(false)} onOk={()=>{begin(manualSelection,"manual");setManualOpen(false);}} okText="下一步 · 填写申请" okButtonProps={{disabled:!selected.length||new Set(selected.map(x=>x.store)).size!==1||!selected.every(eligible)}} destroyOnHidden>
   <Typography.Paragraph type="secondary">可搜索全部 WFS Mock 商品，包括未触发风险的正常 SKU。只能选择本人负责、同店铺且没有有效申请的商品。</Typography.Paragraph>
   <Space wrap><Input.Search placeholder="搜索 SKU / MSKU / 商品ID / 品名" value={manualSearch} onChange={e=>setManualSearch(e.target.value)}/><Select value={manualStore} onChange={setManualStore} options={[{value:"all",label:"全部店铺"},...Array.from(new Set(CLEARANCE_PRODUCTS.map(x=>x.store))).map(x=>({value:x,label:x}))]}/></Space>
   <Table rowKey="id" size="small" className="clearance-chooser-table" dataSource={selectables} rowSelection={{selectedRowKeys:manualSelection,onChange:keys=>setManualSelection(keys.map(String)),getCheckboxProps:x=>({disabled:!eligible(x)})}} columns={productColumns.map(c=>c.title==="风险"?{...c,render:(_:unknown,x:ClearanceProduct)=><RiskTag level={evaluateProduct(x,data.rules).level}/>} as typeof c:c)} pagination={{pageSize:8}}/>
  </Modal>
  <Modal title={old?"补充资料并重新提交":"提交 WFS 清货申请"} width={900} open={Boolean(apply)} onCancel={closeApply} onOk={()=>form.submit()} okText={old?"重新提交审批":"提交申请"} destroyOnHidden>
   <Typography.Paragraph type="secondary">模拟申请不会调用真实审批、调价、广告或 WFS 接口。</Typography.Paragraph>
   <Form form={form} layout="vertical" onFinish={submit} key={apply?.ids.join(",")+":"+(old?.id??"new")} initialValues={{reason:old?.reason,methods:old?.methods??[],remark:old?.remark??"",due:dayjs(old?.due??chinaToday()),quantities:Object.fromEntries(applyProducts.map(x=>[x.id,old?.lines.find(l=>l.id===x.id)?.qty??Math.max(1,Math.floor(x.avail*.5))]))}}>
   <Table size="small" rowKey="id" pagination={false} dataSource={applyProducts} columns={[{title:"SKU / 商品",render:(_,x)=><><strong>{x.sku}</strong><div>{x.name}</div></>},{title:"WFS可售",dataIndex:"avail"},{title:"计划数量",render:(_,x)=><Form.Item name={["quantities",x.id]} rules={[{required:true,message:"必填"}]} noStyle><InputNumber min={1} max={x.avail} precision={0}/></Form.Item>},{title:"目标库存成本",render:(_,x)=>money(x.cost*(Number(form.getFieldValue(["quantities",x.id]))||0))}]}/>
   <div className="clearance-form-grid"><Form.Item name="reason" label="清货原因" rules={[{required:true,message:"请选择原因"}]}><Select options={REASONS.map(x=>({label:x,value:x}))}/></Form.Item>
   <Form.Item name="due" label="计划完成日期" rules={[{required:true,message:"请选择日期"}]}><DatePicker style={{width:"100%"}} format="YYYY-MM-DD"/></Form.Item></div>
   <Form.Item name="methods" label="清货方式" rules={[{required:true,type:"array",min:1,message:"请选择至少一种"}]}><Checkbox.Group options={METHODS}/></Form.Item>
   <Form.Item name="remark" label="申请说明" rules={[{required:true,whitespace:true,message:"请输入申请说明"}]}><Input.TextArea maxLength={500} rows={3} showCount/></Form.Item>
   </Form>
  </Modal>
  <Drawer title={task?"清货申请 · "+task.id:"清货任务"} size="large" open={Boolean(task)} onClose={()=>setTaskId(null)}>
   {task&&<><div className="clearance-detail-grid">{[["目标清货量",taskQty(task)+"件"],["已销售",taskSold(task)+"件"],["移除/弃置",taskRemoved(task)+"件"],["库存成本",money(taskCost(task))]].map(([k,v])=><Card key={k} size="small"><Typography.Text type="secondary">{k}</Typography.Text><strong>{v}</strong></Card>)}</div>
   <Divider/><Space><StatusTag status={task.status}/><Tag>{task.source==="manual"?"运营主动申请":"系统风险识别"}</Tag><Typography.Text type="secondary">规则 V{task.ruleVersion}</Typography.Text></Space>
   <Progress percent={taskProgress(task)}/>
   <Table size="small" pagination={false} rowKey="id" dataSource={task.lines} columns={[{title:"SKU",render:(_,l)=><Button type="link" onClick={()=>{setTaskId(null);setApplicant(l.id);}}>{findProduct(l.id)?.sku}</Button>},{title:"目标",dataIndex:"qty"},{title:"已销售",dataIndex:"sold"},{title:"移除",dataIndex:"removed"},{title:"弃置",dataIndex:"disposed"}]}/>
   <Divider orientation="left">申请方案</Divider><Typography.Paragraph>店铺：{taskStore(task)} · 申请人：{task.requester} · 审批人：{task.approver}</Typography.Paragraph><Typography.Paragraph>原因：{task.reason} · 方式：{task.methods.join("、")}</Typography.Paragraph><Typography.Paragraph>计划截止：{task.due} · 申请时间：{task.submitted}</Typography.Paragraph><Typography.Paragraph style={{whiteSpace:"pre-wrap"}}>{task.remark}</Typography.Paragraph>
   <Divider orientation="left">操作留痕</Divider><Timeline items={task.history.slice().reverse().map(h=>({children:<>{h.text}<div className="clearance-subline">{h.at} · {h.who}</div></>}))}/>
   <Divider orientation="left">清货执行（模拟）</Divider><Typography.Paragraph type="secondary">审批在独立工作台处理；此处仅演示已存在的审批结果。执行进度不会修改真实库存。</Typography.Paragraph>
   <Space wrap>{task.status==="ready"&&<Button type="primary" disabled={task.owner!==role} onClick={()=>updateStatus(task,"start")}>开始执行</Button>}
   {task.status==="running"&&<><Button type="primary" disabled={task.owner!==role} onClick={()=>{progressForm.setFieldsValue({lines:Object.fromEntries(task.lines.map(x=>[x.id,{sold:x.sold,removed:x.removed,disposed:x.disposed}]))});setProgressOpen(true);}}>更新进度</Button><Button disabled={task.owner!==role} onClick={()=>updateStatus(task,"pause")}>暂停执行</Button><Button disabled={task.owner!==role||taskProgress(task)!==100} onClick={()=>updateStatus(task,"finish")}>确认完成</Button></>}
   {task.status==="paused"&&<Button disabled={task.owner!==role} type="primary" onClick={()=>updateStatus(task,"resume")}>恢复执行</Button>}
   {task.status==="pending"&&<Button danger disabled={task.owner!==role} onClick={()=>updateStatus(task,"withdraw")}>撤回申请</Button>}
   {["supplement","rejected"].includes(task.status)&&<Button type="primary" disabled={task.owner!==role} onClick={()=>begin(task.lines.map(l=>l.id),task.source,task.id)}>补充资料并重新提交</Button>}</Space>
   </>}
  </Drawer>
  <Modal title="更新累计清货执行进度" width={800} open={progressOpen} onCancel={()=>setProgressOpen(false)} onOk={()=>progressForm.submit()} okText="保存执行进度" destroyOnHidden>
   <Typography.Paragraph type="secondary">只记录 Mock 进度；各 SKU 的销售、移除、弃置总和不可超过目标，累计数值不得回退。</Typography.Paragraph>
   <Form form={progressForm} onFinish={taskProgressSave} layout="vertical">{task?.lines.map(l=><Card size="small" key={l.id} title={findProduct(l.id)?.sku+" · 目标 "+l.qty+"件"}><div className="clearance-progress-fields">{(["sold","removed","disposed"] as const).map((k,i)=><Form.Item key={k} label={["已销售","已移除","已弃置"][i]} name={["lines",l.id,k]}><InputNumber min={l[k]} max={l.qty} precision={0}/></Form.Item>)}</div></Card>)}</Form>
  </Modal>
  <Modal title="移出人工清货候选" open={Boolean(removeTarget)} onCancel={()=>{setRemoveTarget(null);setRemoveNote("");}} okText="确认移出" okButtonProps={{danger:true}} onOk={()=>{
    const x=removeTarget?findProduct(removeTarget):undefined;
    if(!x||!removeNote.trim()||x.owner!==role||activeTaskFor(data.tasks,x.id)){
      void message.error("原因必填，且只能移出本人无有效任务的 SKU");return;
    }
    change({manual:data.manual.filter(id=>id!==removeTarget)});
    setRemoveTarget(null);setRemoveNote("");void message.success("已移出人工候选（仅 Mock，不删除申请历史）");
  }}><Typography.Paragraph type="secondary">不会删除申请历史或改变库存；有有效清货任务的 SKU 不可移出。</Typography.Paragraph><Input.TextArea value={removeNote} onChange={e=>setRemoveNote(e.target.value)} placeholder="请填写移出原因" rows={3}/></Modal>
 </>;
}