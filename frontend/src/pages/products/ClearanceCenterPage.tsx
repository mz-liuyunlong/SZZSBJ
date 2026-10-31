/** WFS clearance center: native React/AntD mock acceptance, no production API. */
import { useMemo, useState, type ReactNode } from "react";
import { Alert, Button, Card, Select, Space, Tabs, Typography, message } from "antd";
import {
  DownloadOutlined, EyeInvisibleOutlined, EyeOutlined, FileAddOutlined,
  FilterOutlined, ReloadOutlined, SettingOutlined,
  ClockCircleOutlined, FileTextOutlined, LineChartOutlined,
  CheckCircleOutlined, InboxOutlined, WarningOutlined, DollarCircleOutlined,
} from "@ant-design/icons";
import PageShell from "@/components/page/PageShell";
import ConnectedSearch from "@/components/report-table/ConnectedSearch";
import ManagementStatCards, { type ManagementStatCardItem } from "@/components/report-table/ManagementStatCards";
import RuntimeColumnConfigDrawer from "@/components/report-table/RuntimeColumnConfigDrawer";
import type { NavigationPage } from "@/config/navigation";
import {
  ANALYSIS_FIELDS, MANAGEMENT_FIELDS, ClearanceAnalysisTable, ClearanceManagementTable, money, type TableState,
} from "./clearance/clearanceUi";
import {
  CLEARANCE_PRODUCTS, activeTaskFor, chinaToday, coverage, evaluateProduct,
  initialClearance, persistClearance, taskCost, taskProgress, taskQty,
  taskRemoved, taskSold, taskStore, toCsv,
  type RiskLevel, type StoredClearance,
} from "./clearance/clearanceModel";
import { ClearanceDialogs, ClearanceRulesPanel } from "./clearance/clearanceDialogs";
import "./ClearanceCenterPage.css";

type Tab="analysis"|"management"|"rules";
type FilterState={store:string;owner:string;risk:string;status:string;quick:string;sort:string;query:string};
const blankFilters:FilterState={store:"all",owner:"all",risk:"all",status:"all",quick:"all",sort:"risk",query:""};
const statIcons={clock:<ClockCircleOutlined/>,file:<FileTextOutlined/>,chart:<LineChartOutlined/>,check:<CheckCircleOutlined/>,package:<InboxOutlined/>,alert:<WarningOutlined/>,money:<DollarCircleOutlined/>};
const STAT_ICONS:Record<string,ReactNode>=statIcons;
const analysisDefaults=ANALYSIS_FIELDS.map(([key])=>key);
const managementDefaults=MANAGEMENT_FIELDS.map(([key])=>key);
const stores=Array.from(new Set(CLEARANCE_PRODUCTS.map(x=>x.store)));
const owners=Array.from(new Set(CLEARANCE_PRODUCTS.map(x=>x.owner)));
function csvDownload(filename:string,text:string){
 const blob=new Blob([text],{type:"text/csv;charset=utf-8"});
 const href=URL.createObjectURL(blob);
 const a=document.createElement("a");a.href=href;a.download=filename;document.body.appendChild(a);a.click();a.remove();
 window.setTimeout(()=>URL.revokeObjectURL(href),1000);
}
export default function ClearanceCenterPage({page}:{page:NavigationPage}){
 const [data,setData]=useState<StoredClearance>(initialClearance);
 const update=(next:StoredClearance)=>{setData(next);persistClearance(next);};
 const [tab,setTab]=useState<Tab>("analysis");
 const [role,setRole]=useState("刘运营");
 const [filters,setFilters]=useState<FilterState>({...blankFilters});
 const [searchDraft,setSearchDraft]=useState("");
 const [searchType,setSearchType]=useState("all");
 const [showStats,setShowStats]=useState(true);
 const [activeStat,setActiveStat]=useState("");
 const [tables,setTables]=useState<Record<"analysis"|"management",TableState>>({
  analysis:{page:1,pageSize:50,columns:analysisDefaults},
  management:{page:1,pageSize:50,columns:managementDefaults},
 });
 const [columnDrawer,setColumnDrawer]=useState(false);
 const [manualOpen,setManualOpen]=useState(false);
 const [applicant,setApplicant]=useState<string|null>(null);
 const [taskId,setTaskId]=useState<string|null>(null);
 const [apply,setApply]=useState<{ids:string[];editId?:string;source:"auto"|"manual"}|null>(null);
 const managedIds=useMemo(()=>new Set([
  ...CLEARANCE_PRODUCTS.filter(x=>evaluateProduct(x,data.rules).auto&&!data.ignored.includes(x.id)).map(x=>x.id),
  ...data.manual,
  ...data.tasks.filter(t=>["pending","supplement","ready","running","paused"].includes(t.status)).flatMap(t=>t.lines.map(l=>l.id)),
 ]),[data]);
 const candidates=useMemo(()=>CLEARANCE_PRODUCTS.filter(x=>managedIds.has(x.id)&&x.avail>0),[managedIds]);
 const analysisRows=useMemo(()=>{
  const q=filters.query.trim().toLowerCase();
  return candidates.filter(x=>{
   const risk=evaluateProduct(x,data.rules),active=activeTaskFor(data.tasks,x.id),cov=coverage(x);
   if(filters.store!=="all"&&x.store!==filters.store)return false;
   if(filters.owner!=="all"&&x.owner!==filters.owner)return false;
   if(filters.risk!=="all"&&risk.level!==filters.risk)return false;
   if(filters.quick==="manual"&&!data.manual.includes(x.id))return false;
   if(filters.quick==="untreated"&&active)return false;
   if(filters.quick==="auto"&&!risk.auto)return false;
   if(filters.quick==="age"&&x.age<data.rules.mediumAge)return false;
   if(filters.quick==="coverage"&&(cov===null||cov<data.rules.highCoverage))return false;
   if(filters.quick==="decline"&&!risk.business.some(s=>s.includes("下滑")))return false;
   if(!q)return true;
   const searchFields:Record<string,string>={sku:x.sku,msku:x.msku,item:x.item,name:x.name};
   return searchType==="all"?[x.sku,x.msku,x.item,x.name,x.store,x.owner].some(v=>v.toLowerCase().includes(q)):(searchFields[searchType]??"").toLowerCase().includes(q);
  }).sort((a,b)=>{
   if(filters.sort==="age")return b.age-a.age;
   if(filters.sort==="value")return b.avail*b.cost-a.avail*a.cost;
   if(filters.sort==="sales")return a.per[30].units-b.per[30].units;
   const ranks:Record<RiskLevel,number>={high:3,medium:2,low:1};
   return ranks[evaluateProduct(b,data.rules).level]-ranks[evaluateProduct(a,data.rules).level]||b.avail*b.cost-a.avail*a.cost;
  });
 },[candidates,filters,data,searchType]);
 const managementRows=useMemo(()=>data.tasks.filter(t=>{
   const q=filters.query.trim().toLowerCase();
   if(filters.store!=="all"&&taskStore(t)!==filters.store)return false;
   if(filters.owner!=="all"&&t.owner!==filters.owner)return false;
   if(filters.status!=="all"&&t.status!==filters.status)return false;
   if(!q)return true;
   const products=t.lines.map(l=>CLEARANCE_PRODUCTS.find(x=>x.id===l.id));
   if(searchType==="sku"||searchType==="msku"||searchType==="item"||searchType==="name")return products.some(x=>(String(x?.[searchType]??"")).toLowerCase().includes(q));
   return [t.id,t.reason,t.remark,t.requester,...products.map(x=>x?.sku??"")].some(v=>v.toLowerCase().includes(q));
 }).sort((a,b)=>b.submitted.localeCompare(a.submitted)),[data.tasks,filters]);
 const metrics=useMemo(():ManagementStatCardItem<string>[]=>{
  const rows=tab==="management"?[
   {key:"pending",title:"待审批申请",value:data.tasks.filter(t=>t.status==="pending").length,subtitle:"审批由独立工作台处理",icon:STAT_ICONS.clock},
   {key:"ready",title:"待执行计划",value:data.tasks.filter(t=>t.status==="ready").length,subtitle:"已通过，尚未启动",icon:STAT_ICONS.file},
   {key:"running",title:"执行中计划",value:data.tasks.filter(t=>t.status==="running").length,subtitle:"按批准范围执行",icon:STAT_ICONS.chart},
   {key:"done",title:"已完成计划",value:data.tasks.filter(t=>t.status==="done").length,subtitle:"目标数量处理完成",icon:STAT_ICONS.check},
  ]:[
   {key:"untreated",title:"待评估 SKU",value:candidates.filter(x=>!activeTaskFor(data.tasks,x.id)).length,subtitle:"风险与人工申请候选",icon:STAT_ICONS.package},
   {key:"high",title:"高风险 SKU",value:candidates.filter(x=>evaluateProduct(x,data.rules).level==="high").length,subtitle:"库存压力达到高风险条件",icon:STAT_ICONS.alert},
   {key:"manual",title:"人工申请 SKU",value:candidates.filter(x=>data.manual.includes(x.id)).length,subtitle:"运营发起，保留独立来源",icon:STAT_ICONS.file},
   {key:"value",title:"风险库存成本",value:money(candidates.filter(x=>evaluateProduct(x,data.rules).level!=="low").reduce((sum,x)=>sum+x.avail*x.cost,0)),subtitle:"高中风险 WFS 可售库存成本",icon:STAT_ICONS.money},
  ];
  return rows.map(x=>({...x,tone:(x.key==="high"?"danger":x.key==="pending"?"warning":"normal") as ManagementStatCardItem["tone"]}));
 },[tab,candidates,data]);
 const changeFilter=(patch:Partial<FilterState>)=>{setFilters(old=>({...old,...patch}));setTables(old=>({...old,[tab==="rules"?"analysis":tab]:{...old[tab==="rules"?"analysis":tab],page:1}}));};
 const selectTab=(key:string)=>{
  if(!["analysis","management","rules"].includes(key))return;
  setTab(key as Tab);setFilters({...blankFilters});setSearchDraft("");setSearchType("all");setActiveStat("");
 };
 const onStat=(key:string)=>{
  setActiveStat(old=>old===key?"":key);
  if(tab==="management")changeFilter({status:activeStat===key?"all":key});
  else changeFilter({quick:key==="value"?"all":activeStat===key?"all":key,risk:key==="high"&&activeStat!==key?"high":"all"});
 };
 const state=tab==="management"?tables.management:tables.analysis;
 const setTableState=(patch:Partial<TableState>)=>{
  const current=tab==="management"?"management":"analysis";
  setTables(old=>({...old,[current]:{...old[current],...patch}}));
 };
 const fields=tab==="management"?MANAGEMENT_FIELDS:ANALYSIS_FIELDS;
 const fixed=tab==="management"?["id","item"]:["identity","sku"];
 const orderedColumns=(keys:string[])=>[...fixed,...keys.filter(k=>!fixed.includes(k)&&k!=="action"),"action"];
 const exportCsv=()=>{
  let csv:string;
  if(tab==="analysis"){
   const headers=["商品ID","品名","SKU","MSKU","店铺","负责人","风险","来源","WFS可售","库龄","售罄天数","库存成本","售价",...[7,14,30].flatMap(n=>[n+"天日均销量",n+"天销售额",n+"天广告费",n+"天广告占比",n+"天利润",n+"天利润率",n+"天销量"]),"30天退货率","评分"];
   const rows=analysisRows.map(x=>[x.item,x.name,x.sku,x.msku,x.store,x.owner,evaluateProduct(x,data.rules).level,data.manual.includes(x.id)?"运营主动申请":"系统识别",x.avail,x.age,coverage(x)??"",x.avail*x.cost,x.price,...([7,14,30] as const).flatMap(n=>{const p=x.per[n];return [Number((p.units/n).toFixed(2)),p.revenue,p.ads,p.adRate??"",p.profit,p.margin??"",p.units]}),x.per[30].units>0?x.returns/x.per[30].units*100:"",x.rating]);
   csv=toCsv(headers,rows);
  }else{
   const headers=["单号","店铺","申请人","申请来源","清货原因","方式","SKU数量","目标件数","已销售","移除弃置","完成率","库存成本","状态","申请说明"];
   csv=toCsv(headers,managementRows.map(t=>[t.id,taskStore(t),t.requester,t.source,t.reason,t.methods.join("/"),t.lines.length,taskQty(t),taskSold(t),taskRemoved(t),taskProgress(t)+"%",taskCost(t),t.status,t.remark]));
  }
  csvDownload("WFS清货"+(tab==="analysis"?"分析":"管理")+"_Demo_"+chinaToday()+".csv",csv);
  void message.success("已导出当前筛选数据（Mock）");
 };
 return <PageShell page={page}>
  <div className="clearance-center">
   <div className="clearance-heading"><div><Typography.Title level={4}>WFS 清货中心</Typography.Title><Typography.Text type="secondary">WFS 库存风险识别与主动清货申请 · 申请通过统一审批工作台审核</Typography.Text></div><Space><Tag color="processing">仅 Mock 数据</Tag><Select aria-label="演示运营身份" value={role} style={{width:115}} options={owners.map(x=>({value:x,label:x}))} onChange={setRole}/></Space></div>
   <Alert className="clearance-demo-alert" type="info" showIcon message="清货中心演示模式：模拟 SKU、规则和审批记录；不会修改真实库存、发起审批或执行 Walmart 操作。" banner/>
   <Card size="small" className="clearance-main-card">
    <div className="clearance-tabs"><Tabs activeKey={tab} onChange={selectTab} items={[{key:"analysis",label:"清货分析 "+candidates.length},{key:"management",label:"清货管理 "+data.tasks.length}]} tabBarExtraContent={<Space><Button type="text" size="small" icon={showStats?<EyeInvisibleOutlined/>:<EyeOutlined/>} onClick={()=>setShowStats(x=>!x)}>{showStats?"隐藏统计":"显示统计"}</Button><Button type={tab==="rules"?"primary":"text"} icon={<SettingOutlined/>} onClick={()=>selectTab("rules")}>规则配置</Button></Space>}/></div>
    {tab==="rules"?<ClearanceRulesPanel data={data} onChange={update} role={role}/>:<>
     {showStats&&<ManagementStatCards ariaLabel={tab==="analysis"?"清货分析统计":"清货管理统计"} cards={metrics} activeKey={activeStat} onCardClick={onStat}/>}
     <div className="clearance-toolbar">
      <Select aria-label="选择店铺" value={filters.store} onChange={v=>changeFilter({store:v})} options={[{value:"all",label:"全部店铺"},...stores.map(x=>({value:x,label:x}))]}/>
      <Select aria-label="选择负责人" value={filters.owner} onChange={v=>changeFilter({owner:v})} options={[{value:"all",label:"全部负责人"},...owners.map(x=>({value:x,label:x}))]}/>
      {tab==="analysis"?<><Select aria-label="风险等级" value={filters.risk} onChange={v=>changeFilter({risk:v})} options={[{value:"all",label:"全部风险"},{value:"high",label:"高风险"},{value:"medium",label:"中风险"},{value:"low",label:"低风险"}]}/><Select aria-label="排序方式" value={filters.sort} onChange={v=>changeFilter({sort:v})} options={[{value:"risk",label:"风险优先"},{value:"age",label:"库龄最高"},{value:"value",label:"库存成本最高"},{value:"sales",label:"销量最低"}]}/></>:<Select aria-label="清货状态" value={filters.status} onChange={v=>changeFilter({status:v})} options={[{value:"all",label:"全部状态"},...Object.entries({pending:"待审批",supplement:"待补资料",ready:"待执行",running:"执行中",paused:"已暂停",done:"已完成",rejected:"已驳回",cancelled:"已撤回"}).map(([value,label])=>({value,label}))]}/>}
      <ConnectedSearch typeAriaLabel="清货搜索范围" typeOptions={[{value:"all",label:"全部"},{value:"sku",label:"SKU"},{value:"msku",label:"MSKU"},{value:"item",label:"商品 ID"},{value:"name",label:"品名"}]} typeValue={searchType} onTypeChange={value=>{setSearchType(value);changeFilter({query:searchDraft});}} inputAriaLabel="搜索清货记录" inputPlaceholder={tab==="analysis"?"搜索 SKU / MSKU / 商品ID / 品名":"搜索清货单号 / SKU / 申请说明"} inputValue={searchDraft} onInputChange={setSearchDraft} onSearch={()=>changeFilter({query:searchDraft})}/>
      <Button type="primary" icon={<FileAddOutlined/>} onClick={()=>setManualOpen(true)}>申请 SKU</Button>
      <Button icon={<ReloadOutlined/>} onClick={()=>{setSearchDraft("");setSearchType("all");setFilters({...blankFilters});setActiveStat("");setTableState({page:1});void message.info("已刷新 Mock 视图");}}>刷新</Button>
     </div>
     {tab==="analysis"&&<div className="clearance-quick"><Typography.Text type="secondary">快速定位</Typography.Text>{[
      ["all","全部风险"],["untreated","待评估"],["auto","系统识别"],["manual","人工申请"],["age","库龄 ≥"+data.rules.mediumAge+"天"],["coverage","售罄 ≥"+data.rules.highCoverage+"天"],["decline","近期销量下滑"],
     ].map(([key,title])=><Button size="small" key={key} type={filters.quick===key?"primary":"default"} onClick={()=>changeFilter({quick:key})}>{title}</Button>)}</div>}
     <div className="clearance-table-tools"><Typography.Text type="secondary">{tab==="analysis"?"风险优先 · 经营风险辅助，不独立入池":"全部审批决策由独立审批工作台处理"}</Typography.Text><Space><Button size="small" icon={<FilterOutlined/>} onClick={()=>setColumnDrawer(true)}>列配置</Button><Button size="small" icon={<DownloadOutlined/>} onClick={exportCsv}>导出</Button></Space></div>
     {tab==="analysis"?<ClearanceAnalysisTable rows={analysisRows} rules={data.rules} tasks={data.tasks} manual={data.manual} state={tables.analysis} onPage={(page,pageSize)=>setTableState({page,pageSize})} onInspect={setApplicant} onApply={id=>{const p=CLEARANCE_PRODUCTS.find(x=>x.id===id);if(!p||p.owner!==role||p.avail<=0||activeTaskFor(data.tasks,id)){void message.error("当前 SKU 不能申请清货");return;}setApply({ids:[id],source:data.manual.includes(id)?"manual":"auto"});}} onTask={setTaskId}/>:<ClearanceManagementTable rows={managementRows} state={tables.management} onPage={(page,pageSize)=>setTableState({page,pageSize})} onTask={setTaskId}/>}
     <Typography.Paragraph className="clearance-footer-hint" type="secondary">所有商品、指标、申请及规则均为 Mock 演示数据。风险统计不代表真实经营数据。</Typography.Paragraph>
     <RuntimeColumnConfigDrawer open={columnDrawer} groups={[{title:"显示字段",fields:fields.map(([key,title])=>({key,title}))}]} fixedKeys={fixed} defaultKeys={[...fields.map(([key])=>key)]} appliedKeys={state.columns} onApply={columns=>setTableState({columns:orderedColumns(columns)})} onClose={()=>setColumnDrawer(false)} onSaveTemplate={()=>{void message.info("Mock 模式不保存云端模板");}}/>
    </>}
   </Card>
  </div>
  <ClearanceDialogs data={data} onChange={update} role={role} applicant={applicant} setApplicant={setApplicant} manualOpen={manualOpen} setManualOpen={setManualOpen} taskId={taskId} setTaskId={setTaskId} apply={apply} setApply={setApply}/>
 </PageShell>;
}
