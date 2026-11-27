/** WFS clearance center: native React/AntD mock acceptance, no production API. */
import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { Button, Card, Segmented, Select, Space, Tabs, Typography, message, Drawer } from "antd";
import {
  EyeInvisibleOutlined, EyeOutlined, FileAddOutlined,
  ReloadOutlined, SettingOutlined,
  ClockCircleOutlined, FileTextOutlined, LineChartOutlined,
  CheckCircleOutlined, InboxOutlined, WarningOutlined, DollarCircleOutlined,
} from "@ant-design/icons";
import PageShell from "@/components/page/PageShell";
import ReportFacetSelect from "@/shared/report-filters/ReportFacetSelect";
import ConnectedSearch from "@/components/report-table/ConnectedSearch";
import ManagementStatCards, { type ManagementStatCardItem } from "@/components/report-table/ManagementStatCards";
import type { NavigationPage } from "@/config/navigation";
import {
  ClearanceAnalysisTable, type TableState,
} from "./clearance/clearanceUi";
import { ClearanceLiveManagementTable } from "./clearance/ClearanceLiveTables";
import { ANALYSIS_FIELDS, MANAGEMENT_FIELDS, PERIODS, money } from "./clearance/clearanceUiConfig";
import {
  CLEARANCE_PRODUCTS, DEFAULT_RULES, replaceClearancePreviewProducts, activeTaskFor, coverage, evaluateProduct,
  type RiskLevel, type StoredClearance, type PeriodDays, type ClearanceProduct, type ClearanceTask, type ClearanceRules,
} from "./clearance/clearanceModel";
import { ClearanceDialogs, ClearanceRulesPanel } from "./clearance/clearanceDialogs";
import "./ClearanceCenterPage.css";
import { getClearanceFilterOptions, listClearanceListings, type ClearanceList, type ClearanceFilterOptions } from "./clearance/clearanceApi";
import { fromLiveListing } from "./clearance/clearanceLiveAdapter";
import { listClearanceApplications, getClearanceRules, getClearanceRuleHistory, saveClearanceRules, type RuleResponse, type ClearanceApplication } from "./clearance/clearanceApi";
import { rulesFromServer, fullRulesForSave, ruleChangeReason } from "./clearance/clearanceRulesAdapter";

type Tab="analysis"|"management";
type FilterState={store:string[];owner:string[];risk:string[];status:string;quick:string;sort:string;query:string};
const blankFilters:FilterState={store:[],owner:[],risk:[],status:"all",quick:"all",sort:"risk",query:""};
const statIcons={clock:<ClockCircleOutlined/>,file:<FileTextOutlined/>,chart:<LineChartOutlined/>,check:<CheckCircleOutlined/>,package:<InboxOutlined/>,alert:<WarningOutlined/>,money:<DollarCircleOutlined/>};
const STAT_ICONS:Record<string,ReactNode>=statIcons;
const analysisDefaults=ANALYSIS_FIELDS.map(([key])=>key);
const managementDefaults=MANAGEMENT_FIELDS.map(([key])=>key);

export default function ClearanceCenterPage({page}:{page:NavigationPage}){
 const [data,setData] = useState<StoredClearance>(()=>({
  tasks:(import.meta.env.DEV && import.meta.env.MODE !== "test") ? [{
   id:"DEMO-CLR-001",lines:[{id:"DEMO-CLR-201",qty:120,sold:0,removed:0,disposed:0}],
   status:"pending",reason:"本地验收记录（非真实申请）",methods:["降价"],
   owner:"演示运营A",requester:"演示运营A",approver:"",
   date:"2026-11-07",due:"2026-11-30",submitted:"2026-11-07 09:00",
   remark:"仅用于本机界面验收，不写入数据库",source:"manual",
   history:[{at:"2026-11-07 09:00",who:"演示运营A",text:"本地测试申请"}],
   version:1,ruleVersion:0,riskAtSubmission:"unknown",
  }] : [],manual:[],ignored:[],rules:{...DEFAULT_RULES},ruleVersion:0,ruleHistory:[],
 }));
 // Legacy mock/dialog mutations are unchanged; persisted rule updates use a separate handler.
 const update=(next:StoredClearance)=>{void next;void message.warning("清货规则保存当前阶段未接入；仅展示内存默认规则");};
 const [ruleServer,setRuleServer]=useState<RuleResponse|null>(null);
 const [rulesReady,setRulesReady]=useState(false);
 const savingRules=useRef(false);
 const [liveRows,setLiveRows] = useState<ClearanceProduct[]>([]);
 const requestSerial=useRef(0);
 const listAbort=useRef<AbortController|null>(null);
 const [primaryReady,setPrimaryReady]=useState(false);
 const analysisDirty=useRef(false);
 const [tab,setTab]=useState<Tab>("analysis");
 const [analysisFilters,setAnalysisFilters]=useState<FilterState>({...blankFilters});
 const [managementFilters,setManagementFilters]=useState<FilterState>({...blankFilters});
 const filters=tab==="analysis"?analysisFilters:managementFilters;
 const setFilters=tab==="analysis"?setAnalysisFilters:setManagementFilters;
 const [applicationsLoading,setApplicationsLoading]=useState(true);
 const [loadError,setLoadError] = useState(false);
 const [loading,setLoading] = useState(true);
 const [hasMore,setHasMore] = useState(false);
 const [remotePage,setRemotePage] = useState(1);
 const [remoteSize,setRemoteSize] = useState(50);
 const [remoteTotal,setRemoteTotal] = useState<number|null>(null);
 const [filterOptions,setFilterOptions]=useState<ClearanceFilterOptions>({stores:[],owners:[],risks:[
  {value:"high",label:"高风险"},{value:"medium",label:"中风险"},{value:"low",label:"低风险"},
  {value:"none",label:"无风险"},{value:"unknown",label:"待评估"},
 ]});
 const loadLive=async (pageNumber=1,pageSize=50,keyword="", selected?:Pick<FilterState,"store"|"owner"|"risk">)=>{
  const serial=++requestSerial.current;
  listAbort.current?.abort();
  const controller=new AbortController();
  listAbort.current=controller;
  setLoading(true);
  try {
   const chosen=selected??filters;
   const result:ClearanceList=await listClearanceListings(keyword,pageNumber,true,pageSize,{
     store_refs:chosen.store,owner_names:chosen.owner,risk_levels:chosen.risk,
   },controller.signal);
   if(serial!==requestSerial.current)return;
   const rows=result.items.map(fromLiveListing);
   replaceClearancePreviewProducts(rows);
   setLiveRows(rows);setHasMore(result.has_more);setRemotePage(result.page);setRemoteSize(result.page_size);
   setRemoteTotal(typeof result.total === "number" && ["all_wfs_stock_eligible","filtered_wfs_stock_eligible"].includes(result.total_scope ?? "") ? result.total : null);
   setLoadError(false);
  } catch {
   if(serial!==requestSerial.current)return;
   replaceClearancePreviewProducts([]);
   setLiveRows([]);setLoadError(true);
   void message.error("清货商品读取失败；不会以模拟数据替代");
  } finally {if(serial===requestSerial.current){setLoading(false);setPrimaryReady(true);}}
 };
 // Deferring the mount read by one event turn avoids StrictMode's discarded mount.
 useEffect(()=>{
  const timer=window.setTimeout(()=>{void loadLive(1,50,"",blankFilters);},0);
  return ()=>{window.clearTimeout(timer);requestSerial.current++;listAbort.current?.abort();};
 // The first list request is deliberately independent of auxiliary reads.
 // eslint-disable-next-line react-hooks/exhaustive-deps
 },[]);
 useEffect(()=>{
  if(!primaryReady)return;
  const controller=new AbortController();
  const timer=window.setTimeout(()=>{
   void getClearanceFilterOptions(controller.signal).then(setFilterOptions)
    .catch(()=>{if(!controller.signal.aborted)void message.warning("完整筛选选项加载失败，请检查筛选接口");});
  },0);
  return ()=>{window.clearTimeout(timer);controller.abort();};
 },[primaryReady]);
 const [managementApplications,setManagementApplications]=useState<ClearanceApplication[]>([]);
 const applicationRefresh=useRef<(full:boolean,force?:boolean)=>void>(()=>{});
 useEffect(()=>{
   let mounted=true;
   let running=false;
   let runningFull=false;
   let queued=false;
   let wantsFull=false;
   let completed:"none"|"status"|"full"="none";
   let controller:AbortController|null=null;
   const refresh=(full:boolean,force=false)=>{
     if(!mounted)return;
     if(!full&&!force&&wantsFull){
       if(running||completed!=="none")return;
       wantsFull=false;
     }
     wantsFull=wantsFull||full;
     if(running){if(force||(wantsFull&&!runningFull))queued=true;return;}
     if(!force&&(completed==="full"||(completed==="status"&&!wantsFull)))return;
     running=true;
     runningFull=wantsFull;
     const includeLive=runningFull;
     const request=new AbortController();
     controller=request;
     setApplicationsLoading(true);
     void (async()=>{
       try{
         const pageSize=100;
         const first=await listClearanceApplications(1,pageSize,undefined,includeLive,request.signal);
         const items=[...first.items];
         if(first.total>10000)throw new Error("Clearance list exceeds the safe refresh limit");
         for(let p=2;p<=Math.ceil(first.total/pageSize);p++){
           if(!mounted||request.signal.aborted)return;
           const next=await listClearanceApplications(p,pageSize,undefined,includeLive,request.signal);
           items.push(...next.items);
         }
         if(items.length!==first.total)throw new Error("Clearance list changed during pagination");
         if(mounted&&!request.signal.aborted){
           setManagementApplications(items);
           completed=includeLive?"full":"status";
         }
       }catch(error){
         if(mounted&&!request.signal.aborted){console.error("Clearance application refresh failed",error);void message.warning("清货任务读取失败，请刷新重试");}
       }finally{
         running=false;
         if(mounted){setApplicationsLoading(false);if(queued){queued=false;refresh(wantsFull,true);}}
       }
     })();
   };
   applicationRefresh.current=refresh;
   const onUpdated=()=>refresh(wantsFull,true);
   window.addEventListener("szzsbj-clearance-application-updated",onUpdated);
   return ()=>{mounted=false;controller?.abort();applicationRefresh.current=()=>{};
     window.removeEventListener("szzsbj-clearance-application-updated",onUpdated);};
 },[]);
 // Initial analysis loads lightweight status; entering management upgrades once.
 // Ordinary Tab switching and window focus never discard an already loaded list.
 useEffect(()=>{
   if(!primaryReady&&tab==="analysis")return;
   const timer=window.setTimeout(()=>applicationRefresh.current(tab==="management"),0);
   return ()=>window.clearTimeout(timer);
 },[primaryReady,tab]);
 const realTasks=useMemo<ClearanceTask[]>(()=>managementApplications.map(app=>({
  id:app.id,
  lines:[{id:`${app.source_account_ref}::${app.store_id}::${app.item_id}`,
    qty:app.approved_qty??app.requested_qty,sold:Number(app.sold_qty)||0,removed:0,disposed:0}],
  status:app.status==="pending"?"pending":app.status==="running"?"running":
    app.status==="rejected"?"rejected":app.status==="cancelled"?"cancelled":"done",
  reason:app.reason,methods:app.methods_json,owner:app.owner_ref??"未分配",
  requester:app.applicant_ref,approver:"",date:app.submitted_at?.slice(0,10)??"",
  due:app.planned_completion_date??"",submitted:app.submitted_at??"",remark:app.note,source:"manual" as const,
  history:[],version:app.version,ruleVersion:app.rule_version,
  riskAtSubmission:app.risk_at_submission,
 })),[managementApplications]);
  // PR285_RULES_SIDE_DRAWER_V1
  const [rulesOpen,setRulesOpen]=useState(false);
 useEffect(()=>{
  if(!rulesOpen)return;
  let active=true;
  void getClearanceRules().then(server=>{
   const rules=rulesFromServer(server);
   if(!active)return;
   setRuleServer(server);
   setData(current=>({...current,rules,ruleVersion:server.version,ruleHistory:[]}));
   setRulesReady(true);
   void getClearanceRuleHistory().then(history=>{
    if(active)setData(current=>({...current,ruleHistory:history.map(row=>({
     version:row.version,actor:row.changed_by,at:row.changed_at??"",summary:row.change_reason,
    }))}));
   }).catch(()=>{if(active)void message.error("清货规则历史读取失败");});
  }).catch(()=>{
   if(active){setRuleServer(null);setRulesReady(false);void message.error("清货规则读取失败");}
  });
  return ()=>{active=false;};
 },[rulesOpen]);
 const saveRulesFromPanel=async(draft:ClearanceRules):Promise<void>=>{
  const server=ruleServer;
  if(!rulesReady||!server?.can_edit||savingRules.current)return;
  const config=fullRulesForSave(server,draft);
  const reason=ruleChangeReason(server,draft);
  savingRules.current=true;
  try{
   const saved=await saveClearanceRules(server.version,config,reason);
   if(!Number.isInteger(saved.version)||saved.version<1)throw new Error("Invalid saved rule version");
   const current:RuleResponse={...server,version:saved.version,persisted:true,config};
   const rules=rulesFromServer(current);
   setRuleServer(current);
   setData(previous=>({...previous,rules,ruleVersion:saved.version}));
   analysisDirty.current=true;
   if(tab==="analysis"){
    analysisDirty.current=false;
    void loadLive(remotePage,remoteSize,analysisFilters.query,analysisFilters);
   }
   void message.success("规则保存成功");
   try{
    const history=await getClearanceRuleHistory();
    setData(previous=>({...previous,ruleHistory:history.map(row=>({
     version:row.version,actor:row.changed_by,at:row.changed_at??"",summary:row.change_reason,
    }))}));
   }catch{void message.error("清货规则历史读取失败");}
  }catch(error){
   void message.error("规则保存失败");
   throw error;
  }finally{savingRules.current=false;}
 };

 const [period,setPeriod]=useState<PeriodDays>(30);
 const role="刘运营";
 const [analysisSearchDraft,setAnalysisSearchDraft]=useState("");
 const [managementSearchDraft,setManagementSearchDraft]=useState("");
 const searchDraft=tab==="analysis"?analysisSearchDraft:managementSearchDraft;
 const setSearchDraft=tab==="analysis"?setAnalysisSearchDraft:setManagementSearchDraft;
 const [analysisSearchType,setAnalysisSearchType]=useState("all");
 const [managementSearchType,setManagementSearchType]=useState("all");
 const searchType=tab==="analysis"?analysisSearchType:managementSearchType;
 const setSearchType=tab==="analysis"?setAnalysisSearchType:setManagementSearchType;
 const [showStats,setShowStats]=useState(true);
 const [analysisActiveStat,setAnalysisActiveStat]=useState("");
 const [managementActiveStat,setManagementActiveStat]=useState("");
 const activeStat=tab==="analysis"?analysisActiveStat:managementActiveStat;
 const setActiveStat=tab==="analysis"?setAnalysisActiveStat:setManagementActiveStat;
 const [tables,setTables]=useState<Record<"analysis"|"management",TableState>>({
  analysis:{page:1,pageSize:50,columns:analysisDefaults},
  management:{page:1,pageSize:50,columns:managementDefaults},
 });
 const [manualOpen,setManualOpen]=useState(false);
 const [applicant,setApplicant]=useState<string|null>(null);
 const [taskId,setTaskId]=useState<string|null>(null);
 const [apply,setApply]=useState<{ids:string[];editId?:string;source:"auto"|"manual"}|null>(null);
 const candidates=useMemo(()=>liveRows.filter(x=>x.avail>0),[liveRows]);
 const analysisRows=useMemo(()=>{
  const q=filters.query.trim().toLowerCase();
  return candidates.filter(x=>{
   const risk=evaluateProduct(x,data.rules),active=activeTaskFor(realTasks,x.id),cov=coverage(x);
   if(filters.quick==="manual"&&!data.manual.includes(x.id))return false;
   if(filters.quick==="value"&&risk.level==="low")return false;
   if(filters.quick==="untreated"&&active)return false;
   if(filters.quick==="auto"&&!risk.auto)return false;
   if(filters.quick==="age"&&(!Number.isFinite(x.age)||x.age<data.rules.mediumAge))return false;
   if(filters.quick==="coverage"&&(cov===null||cov<data.rules.highCoverage))return false;
   if(filters.quick==="decline"&&!risk.business.some(s=>s.includes("下滑")))return false;
   if(!q)return true;
   const searchFields:Record<string,string>={sku:x.sku,msku:x.msku,item:x.item,name:x.name};
   return searchType==="all"?[x.sku,x.msku,x.item,x.name,x.store,x.owner].some(v=>v.toLowerCase().includes(q)):(searchFields[searchType]??"").toLowerCase().includes(q);
  }).sort((a,b)=>{
   if(filters.sort==="age")return (Number.isFinite(b.age)?b.age:-1)-(Number.isFinite(a.age)?a.age:-1);
   if(filters.sort==="value")return b.avail*b.cost-a.avail*a.cost;
   if(filters.sort==="sales")return a.per[period].units-b.per[period].units;
   const ranks:Record<RiskLevel,number>={high:4,medium:3,low:2,none:1,unknown:0};
   return ranks[evaluateProduct(b,data.rules).level]-ranks[evaluateProduct(a,data.rules).level]||b.avail*b.cost-a.avail*a.cost;
  });
 },[candidates,filters,data,searchType,period,realTasks]);
 // CLEARANCE_ACTUAL_RENDER_V48: this is the routed page. Management rows
 // come from /api/clearance/applications, not the current Listing preview page.
 // Its registry includes only a page of Listings and cannot resolve every
 // historic Item ID, which is why one product happened to work and another did not.
 const managementDisplayRows=useMemo(()=>managementApplications.filter(app=>{
   if(filters.store.length && !filters.store.includes(`${app.source_account_ref}::${app.store_id}`))return false;
   if(filters.owner.length && !filters.owner.includes(app.owner_ref||"未分配"))return false;
   if(filters.status!=="all" && app.status!==filters.status)return false;
   const q=filters.query.trim().toLowerCase();
   if(!q)return true;
   const fields:Record<string,string>={
     sku:app.local_sku||"",msku:app.msku||"",item:app.item_id,name:app.display_product_name||"",
   };
   if(searchType!=="all")return (fields[searchType]||"").toLowerCase().includes(q);
   return [app.id,app.reason,app.note,app.applicant_ref,app.store_name,app.owner_ref,
     ...Object.values(fields)].some(value=>(value||"").toLowerCase().includes(q));
 }).sort((a,b)=>(b.submitted_at||"").localeCompare(a.submitted_at||"")),
 [managementApplications,filters,searchType]);
const metrics=useMemo(():ManagementStatCardItem<string>[]=>{
  const rows=tab==="management"?[
   {key:"pending",title:"待审批申请",value:realTasks.filter(t=>t.status==="pending").length,subtitle:"审批由独立工作台处理",icon:STAT_ICONS.clock},
   {key:"ready",title:"待执行计划",value:realTasks.filter(t=>t.status==="ready").length,subtitle:"已通过，尚未启动",icon:STAT_ICONS.file},
   {key:"running",title:"执行中计划",value:realTasks.filter(t=>t.status==="running").length,subtitle:"按批准范围执行",icon:STAT_ICONS.chart},
   {key:"done",title:"已完成计划",value:realTasks.filter(t=>t.status==="done").length,subtitle:"目标数量处理完成",icon:STAT_ICONS.check},
  ]:[
   {key:"untreated",title:"待评估 SKU",value:candidates.filter(x=>!activeTaskFor(realTasks,x.id)).length,subtitle:"风险与人工申请候选",icon:STAT_ICONS.package},
   {key:"high",title:"高风险 SKU",value:candidates.filter(x=>evaluateProduct(x,data.rules).level==="high").length,subtitle:"库存压力达到高风险条件",icon:STAT_ICONS.alert},
   {key:"manual",title:"人工申请 SKU",value:candidates.filter(x=>data.manual.includes(x.id)).length,subtitle:"运营发起，保留独立来源",icon:STAT_ICONS.file},
   {key:"value",title:"风险库存成本",value:money(candidates.filter(x=>evaluateProduct(x,data.rules).level!=="low").reduce((sum,x)=>sum+x.avail*x.cost,0)),subtitle:"高中风险 WFS 可售库存成本",icon:STAT_ICONS.money},
  ];
  return rows.map(x=>({...x,tone:(x.key==="high"?"danger":x.key==="pending"?"warning":"normal") as ManagementStatCardItem["tone"]}));
 },[tab,candidates,data,realTasks]);
 const changeFilter=(patch:Partial<FilterState>)=>{
  const next={...filters,...patch};
  setFilters(next);
  setTables(old=>({...old,[tab]:{...old[tab],page:1}}));
  if(tab==="analysis"&&("store" in patch||"owner" in patch||"risk" in patch)){
   void loadLive(1,remoteSize,next.query,next);
  }
 };
 const selectTab=(key:string)=>{
  if(!["analysis","management"].includes(key))return;
  if(key===tab)return;
  setTab(key as Tab);
  if(key==="analysis"&&analysisDirty.current){
   analysisDirty.current=false;
   void loadLive(remotePage,remoteSize,analysisFilters.query,analysisFilters);
  }
 };
 const onStat=(key:string)=>{
  setActiveStat(old=>old===key?"":key);
  if(tab==="management")changeFilter({status:activeStat===key?"all":key});
  else changeFilter({quick:activeStat===key?"all":key==="high"?"all":key,risk:key==="high"&&activeStat!==key?["high"]:[]});
 };
 const setTableState=(patch:Partial<TableState>)=>{
  const current=tab==="management"?"management":"analysis";
  setTables(old=>({...old,[current]:{...old[current],...patch}}));
 };
 return <PageShell page={page}>
  <div className="clearance-center">
   <div className="clearance-heading"><div><Typography.Title level={4}>WFS 清货中心</Typography.Title><Typography.Text type="secondary">WFS 库存风险识别与主动清货申请 · 申请通过统一审批工作台审核</Typography.Text></div></div><Card size="small" className="clearance-main-card">
    <div className="clearance-tabs"><Tabs activeKey={tab} onChange={selectTab} items={[{key:"analysis",label:"清货分析 " + (remoteTotal ?? candidates.length)},{key:"management",label:"清货管理 "+realTasks.reduce((n,t)=>n+t.lines.length,0)}]} tabBarExtraContent={<Space><Button type="text" size="small" icon={showStats?<EyeInvisibleOutlined/>:<EyeOutlined/>} onClick={()=>setShowStats(x=>!x)}>{showStats?"隐藏统计":"显示统计"}</Button><Button type={rulesOpen?"primary":"text"} icon={<SettingOutlined/>} onClick={()=>{if(!rulesOpen){setRulesReady(false);setRulesOpen(true);}}}>规则配置</Button></Space>}/></div>
    <>
     {showStats&&<ManagementStatCards ariaLabel={tab==="analysis"?"清货分析统计":"清货管理统计"} cards={metrics} activeKey={activeStat} onCardClick={onStat}/>}
     <div className="clearance-toolbar">
      <ReportFacetSelect ariaLabel="选择店铺" mode="multiple" placeholder="全部店铺" unit="家店铺" value={filters.store} onChange={v=>changeFilter({store:Array.isArray(v)?v:[]})} options={filterOptions.stores}/>
      <ReportFacetSelect ariaLabel="选择负责人" mode="multiple" placeholder="全部负责人" unit="位负责人" value={filters.owner} onChange={v=>changeFilter({owner:Array.isArray(v)?v:[]})} options={filterOptions.owners}/>
      {tab==="analysis"?<><ReportFacetSelect ariaLabel="风险等级" mode="multiple" placeholder="全部风险" unit="个等级" value={filters.risk} onChange={v=>changeFilter({risk:Array.isArray(v)?v:[]})} options={filterOptions.risks}/><Select aria-label="排序方式" value={filters.sort} onChange={v=>changeFilter({sort:v})} options={[{value:"risk",label:"风险优先"},{value:"age",label:"库龄最高"},{value:"value",label:"库存成本最高"},{value:"sales",label:"销量最低"}]}/></>:<Select aria-label="清货状态" value={filters.status} onChange={v=>changeFilter({status:v})} options={[{value:"all",label:"全部状态"},...Object.entries({pending:"待审批",supplement:"待补资料",ready:"待执行",running:"执行中",paused:"已暂停",done:"已完成",rejected:"已驳回",cancelled:"已撤回"}).map(([value,label])=>({value,label}))]}/>}
      <div className={`clearance-search-row${tab==="analysis"?" clearance-search-row--period":""}`}>
      <ConnectedSearch typeAriaLabel="清货搜索范围" typeOptions={[{value:"all",label:"全部"},{value:"sku",label:"SKU"},{value:"msku",label:"MSKU"},{value:"item",label:"商品 ID"},{value:"name",label:"品名"}]} typeValue={searchType} onTypeChange={value=>{setSearchType(value);changeFilter({query:searchDraft});}} inputAriaLabel="搜索清货记录" inputPlaceholder={tab==="analysis"?"搜索 SKU / MSKU / 商品ID / 品名":"搜索清货单号 / SKU / 申请说明"} inputValue={searchDraft} onInputChange={setSearchDraft} onSearch={()=>{changeFilter({query:searchDraft});if(tab==="analysis")void loadLive(1,remoteSize,searchDraft);}}/>
       {tab==="analysis"&&<div className="clearance-period-control"><span className="clearance-period-label">数据周期：</span><Segmented aria-label="数据周期" className="clearance-period-segmented" value={period} options={PERIODS.map(n=>({label:n+"天",value:n}))} onChange={value=>setPeriod(value as PeriodDays)}/></div>}
      </div>
      <Button type="primary" icon={<FileAddOutlined/>} onClick={()=>setManualOpen(true)}>申请 SKU</Button>
      <Button icon={<ReloadOutlined/>} onClick={()=>{setSearchDraft("");setSearchType("all");setFilters({...blankFilters});setActiveStat("");setTableState({page:1});if(tab==="analysis")void loadLive(1,remoteSize,"",blankFilters);window.dispatchEvent(new Event("szzsbj-clearance-application-updated"));}}>刷新</Button>
     </div>
     {tab==="analysis"&&<div className="clearance-quick"><Typography.Text type="secondary">快速定位</Typography.Text>{[
      ["all","全部风险"],["untreated","待评估"],["auto","系统识别"],["manual","人工申请"],["age","库龄 ≥"+data.rules.mediumAge+"天"],["coverage","售罄 ≥"+data.rules.highCoverage+"天"],["decline","近期销量下滑"],
     ].map(([key,title])=><Button size="small" key={key} type={filters.quick===key?"primary":"default"} onClick={()=>changeFilter({quick:key})}>{title}</Button>)}</div>}
     {tab==="analysis"?<ClearanceAnalysisTable loading={loading} rows={analysisRows} rules={data.rules} tasks={realTasks} manual={data.manual} period={period} state={{...tables.analysis,page:remotePage,pageSize:remoteSize}} total={remoteTotal ?? ((remotePage-1)*remoteSize+candidates.length+(hasMore?1:0))} onPage={(page,pageSize)=>{setTableState({page,pageSize});void loadLive(page,pageSize,filters.query);}} onInspect={setApplicant} onApply={id=>{const p=CLEARANCE_PRODUCTS.find(x=>x.id===id);if(!p){void message.error("未找到商品 ID");return;}setApply({ids:[id],source:data.manual.includes(id)?"manual":"auto"});}} onTask={setTaskId}/>:<ClearanceLiveManagementTable loading={applicationsLoading} rows={managementDisplayRows} state={tables.management} total={managementDisplayRows.length} onPage={(page,pageSize)=>setTableState({page,pageSize})} onTask={setTaskId}/>}
    </>
   </Card>
  </div>

  <Drawer
    rootClassName="clearance-rules-drawer"
    title="规则配置"
    placement="right"
    width="min(760px, 96vw)"
    open={rulesOpen}
    onClose={()=>setRulesOpen(false)}
    destroyOnHidden
  >
    <ClearanceRulesPanel
      key={data.ruleVersion}
      data={data}
      onChange={update}
      role={role}
      readOnly={!rulesReady || !ruleServer?.can_edit}
      onSaveRule={saveRulesFromPanel}
    />
  </Drawer>

  {!loading&&!loadError&&<ClearanceDialogs data={{...data,tasks:realTasks}} onChange={update} role={role} applicant={applicant} setApplicant={setApplicant} manualOpen={manualOpen} setManualOpen={setManualOpen} taskId={taskId} setTaskId={setTaskId} apply={apply} setApply={setApply}/>}
 </PageShell>;
}
