import { useMemo, useState } from "react";
import { readUserPreference, writeUserPreference } from "@/shared/preferences/userPreferenceCache";
import { CheckCircleOutlined, AppstoreOutlined, HourglassOutlined } from "@ant-design/icons";
import { Button, Card, DatePicker, Drawer, Form, Input, InputNumber, Modal, Select, Space, Tabs, Tag, Typography, message } from "antd";
import dayjs from "dayjs";
import { ProTable, type ProColumns } from "@ant-design/pro-components";
import ReactECharts from "echarts-for-react";
import PageShell from "@/components/page/PageShell";
import ReportTableShell from "@/components/report-table/ReportTableShell";
import ManagementStatCards from "@/components/report-table/ManagementStatCards";
import ConnectedSearch from "@/components/report-table/ConnectedSearch";
import ReportFacetSelect from "@/shared/report-filters";
import ResetButton from "@/components/report-table/ResetButton";
import RuntimeColumnConfigDrawer from "@/components/report-table/RuntimeColumnConfigDrawer";
import { REPORT_TABLE_PAGE_SIZE_OPTIONS } from "@/components/report-table/pagination";
import { CopyableTextCell, ImageCell, StatusTagCell, PercentCell, MoneyCell } from "@/components/report-table/cells";
import ResizableColumnTitle from "@/components/report-table/ResizableColumnTitle";
import type { NavigationPage } from "@/config/navigation";
import { useNewProductStore, completedScore, daysSince, gradePass, percentage, dimensions, getNewProductWorkflowTab, trackedProduct, trackingWorkflow, periodSales, getPeriodMetrics, evaluateTrack, productScore, type TrackingWorkflowTab, type TrackState, type ProductWorkflowTab,
 type ProductSample, type NewProductConfig, type Grade, type Dimension } from "./newProductModel";
import "./NewProductPages.css";
type Mode="performance"|"tracking";
type Filter={category:string[];developer:string[];operator:string[];field:"sku"|"name"|"itemId";query:string};
const empty=():Filter=>({category:[],developer:[],operator:[],field:"sku",query:""});
const opts=(a:string[])=>[...new Set(a)].map(x=>({label:x,value:x}));
const tone:Record<Grade,string>={S:"purple",A:"blue",B:"green",C:"orange",D:"red",Pass:"default"};
function DashboardCards({mode,products,c,onSelect,activeKey}:{mode:Mode;products:ProductSample[];c:NewProductConfig;onSelect:(key:string)=>void;activeKey:string}) {
  const pool=mode==="performance"?products:products.filter(trackedProduct);
  const assessed=mode==="performance"?pool.filter(p=>p.market!==null):pool.filter(p=>["达标","未达标"].includes(evaluateTrack(p,c)));
  const passed=assessed.filter(p=>mode==="performance"?gradePass(completedScore(p,c)?.grade):evaluateTrack(p,c)==="达标");
  const cards=[
    {key:"total",title:mode==="performance"?"新品总数":"打品池产品",value:pool.length,subtitle:"当前筛选范围",tone:"normal" as const,icon:<AppstoreOutlined/>},
    {key:"pass",title:mode==="performance"?"评估通过率":"打品成功率",value:percentage(passed.length,assessed.length),subtitle:`成功 ${passed.length} / 有效 ${assessed.length}`,tone:"success" as const,icon:<CheckCircleOutlined/>},
    {key:"categories",title:"成功类目",value:new Set(passed.map(p=>p.category)).size,subtitle:"点击只看成功类目",tone:"normal" as const,icon:<AppstoreOutlined/>},
    {key:"pending",title:mode==="performance"?"待市场评分":"待复盘",value:mode==="performance"?pool.filter(p=>p.market===null&&daysSince(p.listedAt)>=c.remindDays).length:
      pool.filter(p=>trackingWorkflow(p,c)==="review").length,subtitle:"需要处理的商品",tone:"warning" as const,icon:<HourglassOutlined/>},
  ];
  return <ManagementStatCards ariaLabel={mode==="performance"?"新品表现指标":"打品跟踪指标"} cards={cards} activeKey={activeKey} onCardClick={onSelect}/>;
}
function DataTable<T extends object>({title,data,columns}:{title:string;data:T[];columns:ProColumns<T>[]}){return <div className="npd-panel"><strong>{title}</strong><ReportTableShell label={title}><ProTable<T> rowKey={r=>String((r as {id?:string;sku?:string}).id??(r as {sku?:string}).sku??"unknown")}
 search={false} options={false} toolBarRender={false} dataSource={data} columns={columns} bordered size="small" scroll={{x:"max-content",y:350}}
 pagination={{defaultPageSize:50,pageSizeOptions:REPORT_TABLE_PAGE_SIZE_OPTIONS.map(String),showSizeChanger:true,showTotal:n=>"共 "+n+" 条数据"}}/></ReportTableShell></div>;}
function group(products:ProductSample[],c:NewProductConfig,key:"category"|"developer"|"operator",launch:boolean){
 const pool=launch?products.filter(trackedProduct):products;
 return [...new Set(pool.map(p=>p[key]))].map(name=>{const list=pool.filter(p=>p[key]===name);
 const valid=launch?list.filter(p=>evaluateTrack(p,c)==="达标"||evaluateTrack(p,c)==="未达标"):list.filter(p=>p.market!==null);
 const ok=valid.filter(p=>launch?evaluateTrack(p,c)==="达标":gradePass(productScore(p,c)?.grade));
 return {id:name,name,total:list.length,valid:valid.length,passed:ok.length,rate:percentage(ok.length,valid.length),
 suggestion:valid.length<3?"样本不足":ok.length/valid.length>=.5?"重点拓展":"深入分析"};});
}
function Board({mode,products,c,onMarket,onCardSelect}:{mode:Mode;products:ProductSample[];c:NewProductConfig;onMarket:(p:ProductSample)=>void;onCardSelect:(key:string)=>void}){
 const pool=mode==="tracking"?products.filter(trackedProduct):products;
 const valid=mode==="tracking"?pool.filter(p=>["达标","未达标"].includes(evaluateTrack(p,c))):pool.filter(p=>p.market!==null);
 const passed=valid.filter(p=>mode==="tracking"?evaluateTrack(p,c)==="达标":gradePass(productScore(p,c)?.grade));
 const grades:Grade[]=["S","A","B","C","D","Pass"];const graded=pool.filter(p=>productScore(p,c)!==null);const data=grades.map(g=>graded.length?Math.round(graded.filter(p=>productScore(p,c)?.grade===g).length/graded.length*100):0);
 const grouped:ProColumns<ReturnType<typeof group>[number]>[]=[{key:"name",dataIndex:"name",title:"名称"},{key:"total",dataIndex:"total",title:"产品数"},{key:"valid",dataIndex:"valid",title:"有效评估"},{key:"passed",dataIndex:"passed",title:"通过数"},{key:"rate",dataIndex:"rate",title:"通过率"},{key:"suggestion",dataIndex:"suggestion",title:"建议"}];
 const cards=[{key:"total",title:mode==="performance"?"测品总数":"进入打品池",value:pool.length,subtitle:"当前筛选范围",tone:"normal" as const,icon:<span>▤</span>},
 {key:"pass",title:mode==="performance"?"测评通过率":"打品成功率",value:percentage(passed.length,valid.length),subtitle:"通过 "+passed.length+" / 有效 "+valid.length,tone:"success" as const,icon:<span>✓</span>},
 {key:"categories",title:"通过类目数",value:new Set(passed.map(p=>p.category)).size,subtitle:"至少有一款成功",tone:"normal" as const,icon:<span>▦</span>},
 {key:"due",title:mode==="performance"?"满30天待评分":"待审批采购",value:mode==="performance"?products.filter(p=>p.market===null&&daysSince(p.listedAt)>=c.remindDays).length:products.filter(p=>p.approval==="pending").length,subtitle:"待处理任务",tone:"warning" as const,icon:<span>◷</span>}];
 return <div className="npd-board"><ManagementStatCards ariaLabel="看板统计" cards={cards} activeKey="total" onCardClick={key=>onCardSelect(key==="due"?"pending":key)}/>
 <div className="npd-two"><Card title={mode==="performance"?"测评等级分布":"初始评级分布"} size="small"><ReactECharts style={{height:210}} option={{grid:{left:110,right:38,top:8,bottom:14},xAxis:{type:"value",min:0,max:100},yAxis:{type:"category",inverse:true,data:grades},series:[{type:"bar",data,barWidth:14,itemStyle:{color:"#1677ff"}}]}}/></Card>
 <Card size="small" title={mode==="performance"?"失败维度参考（示意）":"采购推进进度"}><ReactECharts style={{height:210}} option={{grid:{left:120,right:35,top:8,bottom:14},xAxis:{type:"value",min:0,max:100},
 yAxis:{type:"category",inverse:true,data:mode==="performance"?["出单速度","广告","利润","数据完整度"]:["待审核","待到货","观察中","成功","失败"]},
 series:[{type:"bar",barWidth:14,itemStyle:{color:"#1677ff"},data:mode==="performance"?["order","ads","profit","trust"].map(k=>{const rated=products.filter(p=>p.market!==null);return rated.length?Math.round(100*rated.filter(p=>p.system[k as "order"|"ads"|"profit"|"trust"]<=5).length/rated.length):0;}):["pending","等待到货","观察中","打品成功","打品失败"].map((v,i)=>Math.round(products.filter(p=>i===0?p.approval==="pending":p.tracking===v).length/Math.max(1,products.length)*100))}]}}/></Card></div>
 {mode==="performance"?<div className="npd-two">
 <Card size="small" title="高等级新品占比">
 {(()=>{const rated=products.filter(p=>productScore(p,c)!==null);const high=rated.filter(p=>["S","A"].includes(productScore(p,c)?.grade??""));return <Space direction="vertical">
 <Typography.Title level={3} style={{margin:0}}>{percentage(high.length,rated.length)}</Typography.Title>
 <Typography.Text type="secondary">S/A级 {high.length} 款 / 已完成测评 {rated.length} 款</Typography.Text>
 </Space>})()}</Card>
 <DataTable title="开发人员等级分布" data={[...new Set(products.map(p=>p.developer))].map(name=>{
 const list=products.filter(p=>p.developer===name&&p.market!==null);
 return {id:name,name,total:list.length,...Object.fromEntries((["S","A","B","C","D","Pass"] as Grade[]).map(g=>[g,list.filter(p=>productScore(p,c)?.grade===g).length]))};
 })} columns={[{key:"name",title:"开发人员",dataIndex:"name"},{key:"total",title:"有效测评",dataIndex:"total"},...(["S","A","B","C","D","Pass"] as Grade[]).map(g=>({key:g,title:g+"级",dataIndex:g}))]}/>
 </div>:<div className="npd-two">
 <DataTable title="初始评级 × 打品成功率" data={(["S","A","B","C","D","Pass"] as Grade[]).map(g=>{
 const list=pool.filter(p=>completedScore(p,c)?.grade===g);const valid=list.filter(p=>["达标","未达标"].includes(evaluateTrack(p,c)));
 const ok=valid.filter(p=>evaluateTrack(p,c)==="达标");
 return {id:g,grade:g,tracked:list.length,valid:valid.length,success:ok.length,rate:percentage(ok.length,valid.length)};
 })} columns={[{key:"grade",title:"初始评级",dataIndex:"grade"},{key:"tracked",title:"打品池",dataIndex:"tracked"},
 {key:"valid",title:"有效样本",dataIndex:"valid"},{key:"success",title:"成功量",dataIndex:"success"},{key:"rate",title:"成功率",dataIndex:"rate"}]}/>
 <DataTable title="采购建议准确性复盘" data={pool.map(p=>({id:p.id,sku:p.sku,suggest:productScore(p,c)?.suggested??0,request:p.requestQty??0,approved:p.approvedQty??0,actual:p.actualPurchaseQty??0,sold:periodSales(p,c.successWindow),remaining:p.inventory}))}
 columns={[{key:"sku",title:"SKU",dataIndex:"sku"},{key:"suggest",title:"建议",dataIndex:"suggest"},{key:"request",title:"申请",dataIndex:"request"},
 {key:"approved",title:"批准",dataIndex:"approved"},{key:"actual",title:"实际采购",dataIndex:"actual"},{key:"sold",title:c.successWindow+"天销量",dataIndex:"sold"},{key:"remaining",title:"剩余库存",dataIndex:"remaining"}]}/>
 </div>}
 <div className="npd-two"><DataTable title={mode==="performance"?"类目测评表现":"类目打品表现与深挖建议"} data={group(products,c,"category",mode==="tracking")} columns={grouped}/>
 <DataTable title={mode==="performance"?"新品开发人员成功率":"运营人员打品成功率"} data={group(products,c,mode==="performance"?"developer":"operator",mode==="tracking")} columns={grouped}/></div>
 {mode==="performance"?<DataTable title="上架满30天待市场评分" data={products.filter(p=>p.market===null&&daysSince(p.listedAt)>=c.remindDays)} columns={[
 {key:"name",title:"商品",render:(_,p)=><Space><ImageCell image={p.image} label="商品图片"/><Space direction="vertical" size={0}><CopyableTextCell text={p.sku} label="SKU"/><CopyableTextCell text={p.name} label="品名"/></Space></Space>},
 {key:"operator",dataIndex:"operator",title:"运营"},{key:"listedAt",dataIndex:"listedAt",title:"上架日期"},{key:"days",title:"上架天数",render:(_,p)=>daysSince(p.listedAt)},
 {key:"action",title:"操作",render:(_,p)=><Button type="link" onClick={()=>onMarket(p)}>填写评分</Button>}]}/>:
 <DataTable title="采购进度与打品明细" data={pool} columns={[
 {key:"name",title:"商品",render:(_,p)=><Space><ImageCell image={p.image} label="商品图片"/><Space direction="vertical" size={0}><CopyableTextCell text={p.sku} label="SKU"/><CopyableTextCell text={p.name} label="品名"/></Space></Space>},
 {key:"grade",title:"初始评级",render:(_,p)=>completedScore(p,c)?.grade??"—"},{key:"approvedQty",dataIndex:"approvedQty",title:"批准量"},
 {key:"salesPeriod",title:c.successWindow+"天销量",render:(_,p)=>periodSales(p,c.successWindow)},{key:"inventory",dataIndex:"inventory",title:"库存"},
 {key:"tracking",dataIndex:"tracking",title:"打品结果"}]}/>}
 </div>;
}

function ConfigPanel({mode,visible,onClose,canManage,username}:{mode:Mode;visible:boolean;onClose:()=>void;canManage:boolean;username:string}){
 const c=useNewProductStore(s=>s.config);
 const canConfigure=canManage;
 const version=useNewProductStore(s=>s.ruleVersion);
 const history=useNewProductStore(s=>s.ruleHistory);
 const save=useNewProductStore(s=>s.saveConfig);
 const [form]=Form.useForm();
 const [changeReason,setChangeReason]=useState("");
 const [api,holder]=message.useMessage();
 const initial={...c.weights,remindDays:c.remindDays,successWindow:c.successWindow,successSales:c.successSales,
 minProfit:c.minProfit,maxAcos:c.maxAcos,...Object.fromEntries(c.rules.flatMap(g=>[
 [g.grade+"_min",g.min],[g.grade+"_low",g.qtyMin],[g.grade+"_high",g.qtyMax]]))};
 const submit=()=>{void form.validateFields().then((v:Record<string,number>)=>{
 try{
  if(changeReason.trim().length<5)throw Error("调整规则必须填写至少5字原因");
  const next=structuredClone(c);
  if(mode==="performance"){
    next.remindDays=v.remindDays;
    (Object.keys(dimensions) as Dimension[]).forEach(k=>{next.weights[k]=v[k];});
    next.rules=next.rules.map(g=>({
      ...g,min:v[g.grade+"_min"]??g.min,
      qtyMin:v[g.grade+"_low"]??g.qtyMin,
      qtyMax:v[g.grade+"_high"]??g.qtyMax,
    }));
  }else{
    next.successWindow=v.successWindow as 30|60|90;
    next.successSales=v.successSales;next.minProfit=v.minProfit;next.maxAcos=v.maxAcos;
  }
  save(next,canConfigure,username,changeReason);api.success("配置已保存");onClose();
 }catch(err){api.error((err as Error).message);}
 }).catch(()=>undefined);};
 return <Drawer title={mode==="performance"?"新品表现配置":"打品跟踪配置"} width={780} open={visible} onClose={onClose} destroyOnHidden
  footer={<Space style={{justifyContent:"space-between",width:"100%"}}>
   <Typography.Text type="secondary">规则版本 V{version}</Typography.Text>
   <Space><Button onClick={onClose}>关闭</Button><Button type="primary" disabled={!canConfigure} onClick={submit}>保存配置</Button></Space>
  </Space>}>
  {holder}<Typography.Paragraph type="secondary">规则配置由授权人员维护，保存前需填写变更原因。</Typography.Paragraph>
  <Form form={form} layout="vertical" initialValues={initial}>
  {mode==="performance"?<Tabs items={[
   {key:"weight",label:"评分权重",children:<div className="npd-config-grid">
    {(Object.keys(dimensions) as Dimension[]).map(k=><Form.Item key={k} name={k} label={dimensions[k]+"权重（%）"} rules={[{required:true}]}>
      <InputNumber style={{width:"100%"}} min={0} max={100} precision={0}/></Form.Item>)}
    <Typography.Text type="secondary">权重之和必须为100%。市场竞争提交前不生成正式评分。</Typography.Text>
    </div>},
   {key:"grades",label:"评级与采购数量",children:<div className="npd-config-grade">{c.rules.map(g=>
    <div key={g.grade} className="npd-grade-rule"><strong>{g.grade} 级</strong>
      <Form.Item label="最低分" name={g.grade+"_min"}><InputNumber min={-1} max={10} disabled={g.grade==="Pass"}/></Form.Item>
      <Form.Item label="采购下限" name={g.grade+"_low"}><InputNumber min={0} precision={0}/></Form.Item>
      <Form.Item label="采购上限" name={g.grade+"_high"}><InputNumber min={0} precision={0}/></Form.Item>
    </div>)}</div>},
   {key:"reminder",label:"评分提醒",children:<Form.Item label="Listing 上架后提醒天数" name="remindDays" rules={[{required:true}]}>
      <InputNumber min={1} max={365} precision={0}/></Form.Item>},
   {key:"rules",label:"扣分与修正",children:<Typography.Paragraph>系统评分项可申请修正且需说明原因，主管审核生效；审批中不覆盖原分。ROI 小于 0.5 或利润率低于 10%：Pass；ROI 小于0.8最高 B 级。正式版本将对接审批与版本快照。</Typography.Paragraph>},
  ]}/>:<Tabs items={[
   {key:"success",label:"打品成功标准",children:<div className="npd-config-grid">
    <Form.Item label="观察周期" name="successWindow"><Select options={[30,60,90].map(x=>({label:x+"天",value:x}))}/></Form.Item>
    <Form.Item label="最低销量" name="successSales"><InputNumber min={1} precision={0}/></Form.Item>
    <Form.Item label="最低利润率（%）" name="minProfit"><InputNumber min={-100} max={100}/></Form.Item>
    <Form.Item label="最高 ACOS（%）" name="maxAcos"><InputNumber min={0} max={100}/></Form.Item></div>},
   {key:"samples",label:"有效样本",children:<Typography.Paragraph>观察期从到货且 Listing 可售后计算。周期未完成、缺货或数据不足不作为失败；成功率应同时展示有效评估样本。</Typography.Paragraph>},
   {key:"review",label:"采购与复盘",children:<Typography.Paragraph>对比建议采购量、运营申请量、批准数量、实际采购量及30/60/90天经营结果。</Typography.Paragraph>},
  ]}/>}
  <Card size="small" title="规则变更历史" style={{marginBottom:12}}>{history.map(h=><Typography.Paragraph key={h.version} style={{marginBottom:4}}>V{h.version} · {h.changedBy} · {h.changedAt.slice(0,10)} · {h.reason}</Typography.Paragraph>)}</Card>
  <Form.Item label="规则修改原因" required><Input.TextArea value={changeReason} onChange={e=>setChangeReason(e.target.value)} placeholder="请填写至少5字的修改原因" rows={3}/></Form.Item>
  </Form>
 </Drawer>;
}

export default function NewProductPages({page,mode,canManage=false,canConfigure=false,username="未知用户"}:{page:NavigationPage;mode:Mode;canManage?:boolean;canConfigure?:boolean;username?:string}){
 const state=useNewProductStore(),c=state.config;
 const preferenceKey=mode==="performance"?"products:new-product:columns":"products:launch-tracking:columns";
 const stored=useMemo(()=>readUserPreference<{keys:string[];widths:Record<string,number>}>(username,preferenceKey,1),[username,preferenceKey]);
 const [widths,setWidths]=useState<Record<string,number>>(stored?.widths??{}),[cardKey,setCardKey]=useState("total"),[tab,setTab]=useState("list"),[trackingTab,setTrackingTab]=useState<TrackingWorkflowTab>("all"),[period,setPeriod]=useState<30|60|90>(60),[reviewProduct,setReviewProduct]=useState<ProductSample|null>(null),[reviewState,setReviewState]=useState<TrackState>("观察中"),[reviewDate,setReviewDate]=useState(""),[workflowTab,setWorkflowTab]=useState<ProductWorkflowTab>("all"),[filter,setFilter]=useState(empty),[field,setField]=useState<Filter["field"]>("sku"),[query,setQuery]=useState("");
 const [setting,setSetting]=useState(false),[columnsOpen,setColumnsOpen]=useState(false),[detail,setDetail]=useState<ProductSample|null>(null);
 const [market,setMarket]=useState<ProductSample|null>(null),[purchase,setPurchase]=useState<ProductSample|null>(null);
 const [correction,setCorrection]=useState<{p:ProductSample;d:Exclude<Dimension,"market">}|null>(null);
 const [review,setReview]=useState<string|null>(null),[approval,setApproval]=useState<ProductSample|null>(null);
 const [score,setScore]=useState<number|null>(null),[quantity,setQuantity]=useState<number|null>(null),[reason,setReason]=useState("");
 const [keys,setKeys]=useState(stored?.keys??["name","category","developer","operator","days","market","score","suggested","approval","tracking","salesWindow","orders","clicks","adSpend","acos","margin","profit","requested","approved","inventory","action"]);
 const [api,holder]=message.useMessage();
 const act=(fn:()=>void,done:()=>void)=>{try{fn();done();api.success("操作已更新");}catch(e){api.error((e as Error).message);}};
 const rows=useMemo(()=>state.products.filter(p=>(!filter.category.length||filter.category.includes(p.category))&&
 (!filter.developer.length||filter.developer.includes(p.developer))&&(!filter.operator.length||filter.operator.includes(p.operator))&&
 (!filter.query||String(p[filter.field]).toLowerCase().includes(filter.query.toLowerCase()))),[state.products,filter]);
 const primary=mode==="performance"?rows.filter(p=>workflowTab==="all"||getNewProductWorkflowTab(p,c)===workflowTab):rows.filter(p=>trackedProduct(p)&&(trackingTab==="all"||trackingWorkflow(p,{...c,successWindow:period})===trackingTab));
 const view=primary.filter(p=>cardKey==="total"||(cardKey==="pass"||cardKey==="categories"?(mode==="performance"?gradePass(productScore(p,c)?.grade):evaluateTrack(p,c,period)==="达标"):mode==="performance"?p.market===null&&daysSince(p.listedAt)>=c.remindDays:trackingWorkflow(p,{...c,successWindow:period})==="review"));
 const allCols:ProColumns<ProductSample>[]=[
 {key:"name",title:"SKU / 商品",width:250,fixed:"left",render:(_,p)=><Space><ImageCell label="商品图片" image={p.image} /><Space direction="vertical" size={0}><CopyableTextCell label="SKU" text={p.sku}/><CopyableTextCell label="产品名称" text={p.name}/></Space></Space>},
 {key:"category",title:"类目",dataIndex:"category",width:130},
 {key:"developer",title:"开发人员",dataIndex:"developer",width:120},
 {key:"operator",title:"运营人员",dataIndex:"operator",width:120},
 {key:"days",title:"上架天数",width:100,render:(_,p)=>daysSince(p.listedAt)+" 天"},
 {key:"score",title:"总分 / 评级",width:140,render:(_,p)=>{const s=productScore(p,c);return s?<Space><strong>{s.score.toFixed(2)}</strong><Tag color={tone[s.grade]}>{s.grade}</Tag></Space>:"待评分";}},
 {key:"suggested",title:"建议量",width:115,render:(_,p)=>completedScore(p,c)?.suggested??"—"},
 {key:"approval",title:"采购状态",width:115,render:(_,p)=><StatusTagCell label={p.approval==="none"?"未提交":p.approval==="pending"?"审核中":p.approval==="approved"?"已批准":"已驳回"} color={p.approval==="approved"?"success":p.approval==="rejected"?"error":"warning"}/>},
 {key:"tracking",title:"打品结果",width:125,render:(_,p)=><StatusTagCell label={p.tracking} color={p.tracking==="打品成功"?"success":p.tracking==="打品失败"?"error":"processing"}/>},
 {key:"market",title:"市场竞争",width:100,render:(_,p)=>p.market===null?"待确认":p.market+"分"},
 {key:"clicks",title:period+"天点击量",width:100,render:(_,p)=>getPeriodMetrics(p,period).clicks},
 {key:"orders",title:period+"天订单量",width:100,render:(_,p)=>getPeriodMetrics(p,period).orders},
 {key:"salesWindow",title:period+"天销量",width:115,render:(_,p)=>periodSales(p,period)},
 {key:"adSpend",title:period+"天广告费",width:105,render:(_,p)=><MoneyCell value={getPeriodMetrics(p,period).adSpend}/>},
 {key:"acos",title:period+"天ACOS",width:90,render:(_,p)=><PercentCell value={getPeriodMetrics(p,period).acos}/>},
 {key:"margin",title:period+"天利润率",width:100,render:(_,p)=><PercentCell value={getPeriodMetrics(p,period).margin}/>},
 {key:"profit",title:period+"天利润",width:105,render:(_,p)=><MoneyCell value={getPeriodMetrics(p,period).profit}/>},
 {key:"requested",title:"申请数量",dataIndex:"requestQty",width:110},
 {key:"approved",title:"批准数量",dataIndex:"approvedQty",width:110},
 {key:"actual",title:"实际采购",dataIndex:"actualPurchaseQty",width:110},
 {key:"inventory",title:"剩余库存",dataIndex:"inventory",width:110},
 {key:"action",title:"操作",fixed:"right",width:170,render:(_,p)=><Space size={4}><Button type="link" onClick={()=>setDetail(p)}>详情</Button>
 {mode==="performance"&&p.market===null&&<Button type="link" onClick={()=>{setMarket(p);setScore(null);setReason("");}}>市场评分</Button>}
 {mode==="tracking"&&<Button type="link" onClick={()=>{setReviewProduct(p);setReviewState(p.tracking);setReason(p.reviewReason??"");setReviewDate(p.reviewDueAt??"");}}>复盘</Button>}
 {mode==="performance"&&p.market!==null&&p.approval!=="approved"&&<Button type="link" onClick={()=>{setPurchase(p);setQuantity(completedScore(p,c)?.suggested??null);setReason("");}}>采购确认</Button>}</Space>}
 ];

 return <PageShell page={page}>{holder}<div className="npd-page">
 <div className="npd-header"><div><Typography.Title level={4}>{mode==="performance"?"新品表现":"打品跟踪"}</Typography.Title>
 <Typography.Text type="secondary">{mode==="performance"?"测品评分 · 采购建议 · 开发人员表现":"采购后追踪 · 类目深挖 · 运营人员表现"}</Typography.Text></div>
 <Space><Typography.Text type="secondary">新品测评与采购跟踪</Typography.Text></Space></div>
 <Tabs activeKey={tab} onChange={setTab} items={[{key:"list",label:mode==="performance"?"新品表现":"打品跟踪"},{key:"board",label:mode==="performance"?"新品表现看板":"打品跟踪看板"}]}/>
 <div className="npd-toolbar">
 <ReportFacetSelect mode="multiple" ariaLabel="类目" placeholder="全部类目" value={filter.category} options={opts(state.products.map(p=>p.category))} onChange={v=>setFilter(f=>({...f,category:Array.isArray(v)?v:[]}))}/>
 <ReportFacetSelect mode="multiple" ariaLabel="开发人员" placeholder="开发人员" value={filter.developer} options={opts(state.products.map(p=>p.developer))} onChange={v=>setFilter(f=>({...f,developer:Array.isArray(v)?v:[]}))}/>
 <ReportFacetSelect mode="multiple" ariaLabel="运营人员" placeholder="运营人员" value={filter.operator} options={opts(state.products.map(p=>p.operator))} onChange={v=>setFilter(f=>({...f,operator:Array.isArray(v)?v:[]}))}/>
 <div className="npd-search"><ConnectedSearch typeAriaLabel="搜索类型" inputAriaLabel="搜索新品" typeOptions={[{label:"SKU",value:"sku"},{label:"Item ID",value:"itemId"},{label:"品名",value:"name"}]}
 typeValue={field} inputValue={query} inputPlaceholder="SKU / Item ID / 品名" onTypeChange={v=>setField(v as Filter["field"])} onInputChange={setQuery}
 onSearch={()=>setFilter(f=>({...f,query:query.trim(),field}))}/></div>
 <ResetButton onClick={()=>{setFilter(empty());setQuery("");setField("sku");}}/>
 <div className="npd-actions"><Space>{mode==="tracking"&&<Select value={period} onChange={setPeriod} style={{width:115}} options={[30,60,90].map(n=>({value:n,label:n+"天观察"}))}/>}<Button onClick={()=>{setCardKey("total");setWorkflowTab("all");setTrackingTab("all");setFilter(empty());setQuery("");api.success("已刷新当前筛选视图");}}>刷新</Button><Button onClick={()=>setColumnsOpen(true)}>列配置</Button>
 <Button type="primary" onClick={()=>setSetting(true)}>{mode==="performance"?"新品表现配置":"打品跟踪配置"}</Button></Space></div></div>
 {tab==="board"?<Board mode={mode} products={rows} c={mode==="tracking"?{...c,successWindow:period}:c} onCardSelect={key=>{setCardKey(key);setTab("list");}} onMarket={p=>{setMarket(p);setScore(null);setReason("");}}/>:
 <><div className="npd-board"><DashboardCards mode={mode} products={rows} c={{...c,successWindow:period}} activeKey={cardKey} onSelect={setCardKey}/></div>
 {mode==="performance"&&<Tabs className="npd-workflow-tabs" activeKey={workflowTab} onChange={x=>setWorkflowTab(x as ProductWorkflowTab)} items={[
 {key:"all",label:"全部新品 ("+rows.length+")"},
 {key:"market",label:"待市场评分 ("+rows.filter(p=>getNewProductWorkflowTab(p,c)==="market").length+")"},
 {key:"purchase",label:"待确认采购 ("+rows.filter(p=>getNewProductWorkflowTab(p,c)==="purchase").length+")"},
 {key:"approval",label:"审核中 ("+rows.filter(p=>getNewProductWorkflowTab(p,c)==="approval").length+")"},
 {key:"approved",label:"已批准 ("+rows.filter(p=>getNewProductWorkflowTab(p,c)==="approved").length+")"},
 {key:"stopped",label:"停止推进 ("+rows.filter(p=>getNewProductWorkflowTab(p,c)==="stopped").length+")"}
 ]}/>}
 {mode==="tracking"&&<div className="npd-tracking-controls">
 <Tabs className="npd-workflow-tabs" activeKey={trackingTab} onChange={v=>setTrackingTab(v as TrackingWorkflowTab)}
 items={[["all","全部追踪"],["ready","待开售"],["observe","观察中"],["review","待复盘"],["optimize","需要优化"],["done","已完成"]].map(([key,label])=>({
 key,label:label+" ("+rows.filter(p=>trackedProduct(p)&&(key==="all"||trackingWorkflow(p,{...c,successWindow:period})===key)).length+")"
 }))}/>
 </div>}
 <DataTable title={mode==="performance"?"新品表现明细":"打品跟踪明细"} data={view} columns={keys.map(key=>allCols.find(col=>String(col.key)===key)).filter((col):col is ProColumns<ProductSample>=>!!col).map(col=>({...col,width:widths[String(col.key)]??col.width,title:<ResizableColumnTitle label={String(col.title)} minWidth={90} width={widths[String(col.key)]??Number(col.width??120)} onWidthChange={width=>setWidths(w=>({...w,[String(col.key)]:width}))}/> }))}/>
 {mode==="performance"&&<>
 <DataTable title="系统评分修正申请" data={state.corrections} columns={[
 {key:"id",title:"申请编号",dataIndex:"id"},{key:"productId",title:"SKU",dataIndex:"productId"},
 {key:"dimension",title:"维度",render:(_,r)=>dimensions[r.dimension]},{key:"from",title:"原分",dataIndex:"from"},{key:"to",title:"申请分",dataIndex:"to"},
 {key:"reason",title:"申请原因",dataIndex:"reason",width:240},{key:"status",title:"状态",dataIndex:"status"},
 {key:"action",title:"操作",render:(_,r)=>r.status==="pending"?<Button type="link" onClick={()=>{setReview(r.id);setReason("");}}>审核</Button>:"—"}]}/>
 <DataTable title="新品采购审核" data={state.products.filter(p=>p.approval!=="none")} columns={[
 {key:"sku",title:"SKU",dataIndex:"sku"},{key:"requested",title:"申请数量",dataIndex:"requestQty"},
 {key:"suggestion",title:"建议数量",render:(_,p)=>completedScore(p,c)?.suggested??"—"},
 ...(canManage?[{key:"amount",title:"采购金额",render:(_:unknown,p:ProductSample)=>"¥"+((p.requestQty??0)*p.unitCost).toFixed(2)}]:[]),
 {key:"status",title:"审批状态",dataIndex:"approval"},
 {key:"action",title:"操作",render:(_,p)=>p.approval==="pending"?<Button type="link" onClick={()=>{setApproval(p);setReason("");}}>审核</Button>:"—"}]}/>
 <DataTable title="正式采购计划" data={state.plans} columns={[
 {key:"id",title:"计划编号",dataIndex:"id"},{key:"productId",title:"SKU",dataIndex:"productId"},
 {key:"grade",title:"评级",dataIndex:"grade"},{key:"suggestedQty",title:"建议量",dataIndex:"suggestedQty"},
 {key:"approvedQty",title:"批准量",dataIndex:"approvedQty"}]}/></>}</>}
 <Drawer title={reviewProduct?"打品复盘 · "+reviewProduct.sku:"打品复盘"} width={680} open={!!reviewProduct} onClose={()=>setReviewProduct(null)}
 footer={<Space><Button onClick={()=>setReviewProduct(null)}>取消</Button><Button type="primary" onClick={()=>act(()=>state.updateTrack(reviewProduct!.id,reviewState,reason,reviewDate),()=>setReviewProduct(null))}>保存复盘</Button></Space>}>
 {reviewProduct&&<><Typography.Paragraph>{reviewProduct.name} · 运营：{reviewProduct.operator} · 初始评级：{completedScore(reviewProduct,c)?.grade??"—"}</Typography.Paragraph>
 <div className="npd-review-summary"><div>系统建议：{completedScore(reviewProduct,c)?.suggested??"—"} 件</div><div>运营申请：{reviewProduct.requestQty??"—"} 件</div><div>批准数量：{reviewProduct.approvedQty??"—"} 件</div>
 <div>{period}天销量：{periodSales(reviewProduct,period)}</div><div>点击：{getPeriodMetrics(reviewProduct,period).clicks}</div><div>订单：{getPeriodMetrics(reviewProduct,period).orders}</div><div>广告费：{getPeriodMetrics(reviewProduct,period).adSpend}</div><div>利润：{getPeriodMetrics(reviewProduct,period).profit}</div><div>利润率：{getPeriodMetrics(reviewProduct,period).margin.toFixed(1)}%</div><div>ACOS：{getPeriodMetrics(reviewProduct,period).acos.toFixed(1)}%</div><div>库存：{reviewProduct.inventory}</div></div>
 <Typography.Paragraph>复盘结果</Typography.Paragraph><Select value={reviewState} onChange={setReviewState} style={{width:"100%"}} options={["观察中","需要优化","打品成功","打品失败"].map(v=>({label:v,value:v}))}/>
 {reviewState==="需要优化"&&<><Typography.Paragraph style={{marginTop:12}}>下次复核日期（必填）</Typography.Paragraph><DatePicker value={reviewDate?dayjs(reviewDate):null} onChange={value=>setReviewDate(value?.format("YYYY-MM-DD")??"")} format="YYYY-MM-DD" style={{width:"100%"}}/></>}
 <Typography.Paragraph style={{marginTop:12}}>复盘说明（必填，至少5字）</Typography.Paragraph><Input.TextArea rows={4} value={reason} onChange={e=>setReason(e.target.value)}/></>}
 </Drawer>
 <ConfigPanel mode={mode} visible={setting} canManage={canConfigure} username={username} onClose={()=>setSetting(false)}/>
 <RuntimeColumnConfigDrawer open={columnsOpen} onClose={()=>setColumnsOpen(false)} fixedKeys={["name","action"]}
 appliedKeys={keys} defaultKeys={allCols.map(x=>String(x.key))} onApply={next=>{setKeys(next);writeUserPreference(username,preferenceKey,1,{keys:next,widths});}} onSaveTemplate={()=>{writeUserPreference(username,preferenceKey,1,{keys,widths});api.success("列模板已保存在当前浏览器的账号偏好中");}}
 groups={[{title:"新品明细",fields:allCols.map(x=>({key:String(x.key),title:String(x.title)}))}]}/>
 <Drawer title={detail?.name??"新品详情"} open={!!detail} onClose={()=>setDetail(null)} width={700}>{detail&&<>
 <Typography.Paragraph>SKU：{detail.sku} · 类目：{detail.category} · 运营：{detail.operator}</Typography.Paragraph>
 <Typography.Paragraph>上架：{detail.listedAt} · 已上架 {daysSince(detail.listedAt)} 天</Typography.Paragraph>
 {(Object.keys(dimensions) as Dimension[]).map(d=><div className="npd-dimension" key={d}><b>{dimensions[d]}</b>
 <span>{d==="market"?detail.market??"待运营确认":detail.overrides[d]??detail.system[d]}</span>
 {d!=="market"&&detail.market!==null&&detail.approval!=="approved"&&<Button type="link" onClick={()=>{setCorrection({p:detail,d});setScore(detail.overrides[d]??detail.system[d]);setReason("");setDetail(null);}}>申请修正</Button>}</div>)}
 <Typography.Paragraph>最终得分：{productScore(detail,c)?.score??"待市场评分"} · 评级：{productScore(detail,c)?.grade??"—"}</Typography.Paragraph>
 <Typography.Paragraph>点击 {detail.clicks} · 订单 {detail.orders} · 利润率 {detail.margin}% · ACOS {detail.acos}%</Typography.Paragraph>
 {canManage&&<Typography.Paragraph>采购单价 ¥{detail.unitCost}</Typography.Paragraph>}</>}</Drawer>
 <Modal open={!!market} title="运营确认市场竞争评分" onCancel={()=>setMarket(null)} onOk={()=>act(()=>state.setMarket(market!.id,score!,reason),()=>setMarket(null))}>
 <Typography.Paragraph>市场竞争确认后，系统才生成总分、评级与采购建议。</Typography.Paragraph>
 <InputNumber min={0} max={10} precision={0} value={score} onChange={setScore} style={{width:"100%",marginBottom:12}}/>
 <Input.TextArea rows={3} value={reason} placeholder="市场竞争评分依据" onChange={e=>setReason(e.target.value)}/></Modal>
 <Modal open={!!correction} title="系统评分修正申请" onCancel={()=>setCorrection(null)}
 onOk={()=>act(()=>state.submitCorrection(correction!.p.id,correction!.d,score!,reason),()=>setCorrection(null))}>
 <Typography.Paragraph>{correction?.p.sku} · {correction&&dimensions[correction.d]}</Typography.Paragraph>
 <InputNumber min={0} max={10} precision={0} value={score} onChange={setScore} style={{width:"100%",marginBottom:12}}/>
 <Input.TextArea value={reason} rows={3} placeholder="说明修正原因，至少5字" onChange={e=>setReason(e.target.value)}/></Modal>
 <Modal open={!!review} title="评分修正审核" onCancel={()=>setReview(null)} footer={canManage?<Space>
 <Button onClick={()=>act(()=>state.decideCorrection(review!,"rejected",reason,canManage,username),()=>setReview(null))}>驳回</Button>
 <Button type="primary" onClick={()=>act(()=>state.decideCorrection(review!,"approved",reason,canManage,username),()=>setReview(null))}>批准</Button></Space>:<Typography.Text>领导视角方可审批</Typography.Text>}>
 <Typography.Paragraph>申请编号：{review}</Typography.Paragraph><Input.TextArea rows={3} value={reason} onChange={e=>setReason(e.target.value)} placeholder="审批说明"/></Modal>
 <Modal open={!!purchase} title="确认采购数量" onCancel={()=>setPurchase(null)} onOk={()=>act(()=>state.applyPurchase(purchase!.id,quantity!,reason),()=>setPurchase(null))}>
 <Typography.Paragraph>系统建议：{purchase?completedScore(purchase,c)?.suggested:"—"} 件</Typography.Paragraph>
 <InputNumber min={1} precision={0} value={quantity} onChange={setQuantity} style={{width:"100%",marginBottom:12}}/>
 {purchase&&quantity!==null&&quantity>(completedScore(purchase,c)?.rule?.qtyMax??0)&&<Tag color="warning">超出等级采购区间</Tag>}
 <Input.TextArea rows={3} value={reason} onChange={e=>setReason(e.target.value)} placeholder="修改数量必须说明原因"/></Modal>
 <Modal open={!!approval} title="新品采购审核" onCancel={()=>setApproval(null)} footer={canManage?<Space>
 <Button onClick={()=>act(()=>state.decidePurchase(approval!.id,"rejected",reason,canManage,username),()=>setApproval(null))}>驳回</Button>
 <Button type="primary" onClick={()=>act(()=>state.decidePurchase(approval!.id,"approved",reason,canManage,username),()=>setApproval(null))}>审核通过并生成计划</Button></Space>:<Typography.Text>领导视角方可审批</Typography.Text>}>
 <Typography.Paragraph>商品：{approval?.sku} · 申请数量：{approval?.requestQty}</Typography.Paragraph>
 <Typography.Paragraph>原因：{approval?.requestReason}</Typography.Paragraph>
 {canManage&&approval&&<Typography.Paragraph>金额：¥{((approval.requestQty??0)*approval.unitCost).toFixed(2)}</Typography.Paragraph>}
 <Input.TextArea rows={3} value={reason} placeholder="审核理由" onChange={e=>setReason(e.target.value)}/></Modal>
 </div></PageShell>;
}
