/** Live-data renderers that retain the pre-existing Clearance Center ProTable headers.
 * These components consume real backend data ONLY; never import demo products/tasks.
 */
import { useState, type ReactNode } from "react";
import { Button, Progress, Tag, Typography } from "antd";
import { FundOutlined, NotificationOutlined, DollarCircleOutlined } from "@ant-design/icons";
import { ProTable, type ProColumns } from "@ant-design/pro-components";
import ReportTableShell from "@/components/report-table/ReportTableShell";
import ResizableColumnTitle from "@/components/report-table/ResizableColumnTitle";
import { ClearanceRiskPopover, type RiskDetailPayload } from "./ClearanceRiskPopover";
import { REPORT_TABLE_PAGE_SIZE_OPTIONS } from "@/components/report-table/pagination";
import { ANALYSIS_FIELDS, MANAGEMENT_FIELDS, money, percent } from "./clearanceUiConfig";
import type { PeriodDays } from "./clearanceModel";
import type { ClearanceApplication, ClearanceListing } from "./clearanceApi";

export interface LiveTableState { page: number; pageSize: number; columns: string[] }
interface BaseProps { state: LiveTableState; onPage(page: number, pageSize: number): void; total: number }
const number = (value: unknown): number | null => {
  if (typeof value === "number") return Number.isFinite(value) ? value : null;
  if (typeof value === "string" && value.trim() !== "") {
    const parsed = Number(value); return Number.isFinite(parsed) ? parsed : null;
  }
  return null;
};
const count = (value: unknown) => { const n = number(value); return n === null ? "—" : n.toLocaleString("en-US", {maximumFractionDigits: 0}); };
const amount = (value: unknown) => { const n = number(value); return n === null ? "—" : money(n); };
const statusLabel: Record<string,string> = {pending:"待审批",running:"执行中",done:"已完成",rejected:"已驳回",cancelled:"已撤回",stock_closed:"库存归零关闭"};
const statusColor: Record<string,string> = {pending:"gold",running:"blue",done:"default",rejected:"error",cancelled:"default",stock_closed:"default"};
const metricTone = (key:string): "sales"|"ads"|"profit"|null => {
  if (key === "revenue" || key === "daily") return "sales";
  if (key === "ads" || key === "adRate") return "ads";
  if (key === "profit" || key === "profitRate") return "profit";
  return null;
};
function makeColumn<T>(key:string,label:string,width:number,widths:Record<string,number>,onWidth:(key:string,n:number)=>void,
    cell:(row:T)=>ReactNode,kind:"analysis"|"management"):ProColumns<T> {
  const currentWidth = widths[kind+":"+key] ?? width;
  const tone = kind==="analysis" ? metricTone(key) : null;
  return {
    key, dataIndex:key,
    title:<ResizableColumnTitle label={label} width={currentWidth} minWidth={Math.min(currentWidth,110)} onWidthChange={n=>onWidth(kind+":"+key,n)} />,
    width:currentWidth, ellipsis:false,
    className:tone?`clearance-metric-cell clearance-metric-cell--${tone}`:undefined,
    fixed:key==="action"?"right":(kind==="analysis"&&(key==="identity"||key==="sku"))||(kind==="management"&&(key==="identity"||key==="sku"))?"left":undefined,
    onHeaderCell:()=>({className:"report-table-resizable-header-cell"+(tone?` clearance-metric-child-header clearance-metric-child-header--${tone}`:"")}),
    render:(_,row)=>cell(row),
  };
}
const metric=(row:ClearanceListing,key:string) => number(row.metrics[key]);
// Calendar-day arithmetic in the same LA timezone as submitted-at display.
// UTC +24 hours is NOT sufficient at daylight-saving boundaries.
const v50PlannedStart = (submitted: string | null | undefined): string | null => {
  if (!submitted) return null;
  const instant = new Date(submitted);
  if (!Number.isFinite(instant.getTime())) return null;
  const pieces = new Intl.DateTimeFormat("en-US", {
    timeZone: "America/Los_Angeles",year:"numeric",month:"2-digit",day:"2-digit"
  }).formatToParts(instant);
  const part = (key: string) => pieces.find(piece => piece.type === key)?.value;
  const year = Number(part("year"));
  const month = Number(part("month"));
  const day = Number(part("day"));
  if (!year || !month || !day) return null;
  return new Date(Date.UTC(year,month-1,day+1)).toISOString().slice(0,10);
};
const v50DisplayDate = (date: string | null | undefined): string =>
  date && /^\d{4}-\d{2}-\d{2}$/.test(date) ? date.replace(/-/g,"/") : "—";


export function ClearanceLiveAnalysisTable({rows,period,state,total,onPage,onInspect,onApply}:BaseProps&{
  rows: ClearanceListing[];period:PeriodDays;onInspect(row:ClearanceListing):void;onApply(row:ClearanceListing):void;
}) {
  const [widths,setWidths]=useState<Record<string,number>>({});
  const onWidth=(key:string,value:number)=>setWidths(old=>({...old,[key]:value}));
  const cell=(row:ClearanceListing,key:string):ReactNode=>{
    const units=metric(row,`sales_${period}d`);
    const observed=metric(row,"listing_days");
    const denominator=observed===null ? period : Math.max(1,Math.min(observed,period));
    switch(key){
      case "identity":return <><Button type="link" className="clearance-table-link" onClick={()=>onInspect(row)}>{row.title||row.item_id}</Button>
        <Typography.Text className="clearance-subline" type="secondary">{row.item_id}</Typography.Text></>;
      case "sku":return <><strong>{row.sku||"—"}</strong><Typography.Text className="clearance-subline" type="secondary">{row.msku||"—"}</Typography.Text></>;
      case "store":return <>{row.store_name||row.store_id}<Typography.Text className="clearance-subline" type="secondary">{row.owner||"—"}</Typography.Text></>;
      case "risk":return <><ClearanceRiskPopover itemId={row.item_id} payload={row as unknown as RiskDetailPayload} fallbackLevel={row.risk} productName={row.title} sku={row.sku} storeName={row.store_name}/>
        <Typography.Text className="clearance-subline" type="secondary">{row.risk==="unknown"?"资料不足待评估":row.signals.length?"含经营异常":"库存风险识别"}</Typography.Text></>;
      case "source":return row.risk==="unknown"?<Tag>待评估</Tag>:<Tag color="blue">规则计算</Tag>;
      case "wfs":return <strong>{count(row.available)} 件</strong>;
      // Never substitute Listing age for unsupported batch-based stock age.
      case "age":return <span title="WFS批次库龄未获取；不可用Listing首次入仓天数冒充">—</span>;
      case "coverage":return metric(row,"sellout_days")===null?"暂无法预计":`${count(metric(row,"sellout_days"))}天`;
      case "stockCost":return <strong>{amount(row.metrics.capital_at_cost_usd)}</strong>;
      case "price":return amount(row.price_amount);
      case "daily":return units===null?"—":<span className="clearance-period-value">{(units/denominator).toFixed(2)}</span>;
      case "revenue":case "ads":return <span title="当前读模型尚无可核实的本周期金额，不生成估算值">—</span>;
      case "adRate":return period===14?"—":percent(metric(row,`ad_ratio_${period}d_percent`));
      case "profit":return amount(row.metrics[`profit_${period}d_usd`]);
      case "profitRate":return period===30?percent(metric(row,"margin_30d_percent")):"—";
      case "returns":{
        const returned=metric(row,"returns_30d"), sold=metric(row,"sales_30d");
        return returned===null||sold===null||sold<=0?"—":percent(returned/sold*100);
      }
      case "rating":return metric(row,"rating")===null?"—":<span className="clearance-star">★ {metric(row,"rating")?.toFixed(1)}</span>;
      case "units":return count(units);
      case "status":return <span title="任务状态仅以真实申请记录为准">—</span>;
      case "action":return <><Button type="link" size="small" onClick={()=>onInspect(row)}>详情</Button>
        <Button type="link" size="small" onClick={()=>onApply(row)}>申请清货</Button></>;
      default:return "—";
    }
  };
  const fields = state.columns.flatMap(key=>ANALYSIS_FIELDS.filter(([name])=>name===key));
  const leaves=fields.map(([key,label,width])=>makeColumn<ClearanceListing>(key,label,width,widths,onWidth,row=>cell(row,key),"analysis"));
  const groups=[
    {id:"sales",name:"销售表现",keys:["revenue","daily"]},
    {id:"ads",name:"广告表现",keys:["ads","adRate"]},
    {id:"profit",name:"利润表现",keys:["profit","profitRate"]},
  ] as const;
  const columns:ProColumns<ClearanceListing>[]=[];
  const seen=new Set<string>();
  fields.forEach(([key],index)=>{
    const group=groups.find(g=>g.keys.some(k=>k===key));
    if(!group){columns.push(leaves[index]);return;}
    if(seen.has(group.id))return;
    seen.add(group.id);
    const children=group.keys.map(k=>{
      const i=fields.findIndex(([name])=>name===k);
      return i>=0?leaves[i]:undefined;
    }).filter((x):x is ProColumns<ClearanceListing>=>x!==undefined);
    const icon=group.id==="sales"?<FundOutlined/>:group.id==="ads"?<NotificationOutlined/>:<DollarCircleOutlined/>;
    columns.push({key:"metric-"+group.id,
      title:<span className={`clearance-metric-group-title clearance-metric-group-title--${group.id}`}>
        <span className="clearance-metric-group-icon">{icon}</span>{group.name}</span>,
      children,
      onHeaderCell:()=>({className:`clearance-metric-group-header clearance-metric-group-header--${group.id}`}),
    });
  });
  return <ReportTableShell label="清货分析表格"><ProTable<ClearanceListing>
    rowKey={row=>`${row.source_account_ref}:${row.store_id}:${row.item_id}`}
    search={false} options={false} toolBarRender={false} columns={columns} dataSource={rows}
    scroll={{x:fields.reduce((sum,[key,,width])=>sum+(widths["analysis:"+key]??width),0),y:"100%"}}
    pagination={{current:state.page,pageSize:state.pageSize,total,size:"small",showSizeChanger:true,
      showQuickJumper:true,pageSizeOptions:REPORT_TABLE_PAGE_SIZE_OPTIONS,onChange:onPage}}
    locale={{emptyText:"暂无符合条件的清货商品；其他WFS商品仍可通过申请SKU搜索"}} />
  </ReportTableShell>;
}

export function ClearanceLiveManagementTable({rows,state,onPage,total,onTask}:BaseProps&{
  rows:ClearanceApplication[];onTask(id:string):void;
}){
  const [widths,setWidths]=useState<Record<string,number>>({});
  const onWidth=(key:string,value:number)=>setWidths(old=>({...old,[key]:value}));
  const cell=(row:ClearanceApplication,key:string):ReactNode=>{
    const target=row.approved_qty??row.requested_qty;
    const sold=number(row.sold_qty);
    const progress=sold!==null&&target>0?Math.max(0,Math.min(100,Math.floor(sold*100/target))):null;
    switch(key){
      case "identity":return <><strong>{row.display_product_name||row.title||row.item_id}</strong><Typography.Text className="clearance-subline" type="secondary">{row.item_id}</Typography.Text></>;
      case "sku":return <><strong>{row.local_sku||"—"}</strong><Typography.Text className="clearance-subline" type="secondary">{row.msku||"—"}</Typography.Text></>;
      case "store":return <>{row.store_name||row.store_id}<Typography.Text className="clearance-subline" type="secondary">{row.display_owner_name||row.owner_ref||"—"}</Typography.Text></>;
      case "source":return <Tag color="purple">运营主动申请</Tag>;
      case "reason":return row.reason;
      case "method":return row.methods_json.join(" / ");
      case "goal":return <strong>{count(target)} 件</strong>;
      case "sold":return sold===null?"—":`${count(sold)} 件`;
      case "revenue":return <span title="未获得此清货任务的真实成交金额，不使用当前售价估算">—</span>;
      case "progress":return progress===null?"—":<div className="clearance-progress" title={`实际销售 ${sold} 件 / 批准目标 ${target} 件`}>
        <strong>{progress}%</strong><Progress percent={progress} showInfo={false} size="small"/></div>;
      // CLEARANCE_TARGET_COST_FALLBACK_V44
      case "cost":{
        const live=number(row.v44_current_target_cost_usd);
        const saved=number(row.target_inventory_cost_usd);
        if(live!==null && live>=0)return <span title="当前已核实的采购成本加头程 × 本任务目标数量；不包含WFS配送费、佣金">{money(live)}</span>;
        if(saved!==null && saved>=0)return <span title="申请时保存的采购成本加头程 × 本任务目标数量；历史申请快照，非当前成本">{money(saved)}</span>;
        return <span title="当前和申请快照均缺少可核实的采购+头程成本，未生成估算金额">—</span>;
      }
      case "plannedStart":return <span title="按申请提交时的美国洛杉矶日期，默认次日开始；非独立保存的计划日期">{v50DisplayDate(v50PlannedStart(row.submitted_at))}</span>;
      case "due":return <span title={row.planned_completion_date?"申请时保存的计划完成日期":"申请列表及详情未返回已保存的计划完成日期；需检查后端持久化"}>{v50DisplayDate(row.planned_completion_date)}</span>;
      case "status":return <Tag color={statusColor[row.status]||"default"}>{statusLabel[row.status]||row.status}</Tag>;
      case "submitted":return row.submitted_at
        ? new Date(row.submitted_at).toLocaleString("zh-CN",{timeZone:"America/Los_Angeles",year:"numeric",month:"2-digit",day:"2-digit",hour:"2-digit",minute:"2-digit"})
        : "—";
      case "action":return <Button type="link" onClick={()=>onTask(row.id)}>任务详情</Button>;
      default:return "—";
    }
  };
  const columns=MANAGEMENT_FIELDS.map(([key,label,width])=>makeColumn<ClearanceApplication>(key,label,width,widths,onWidth,row=>cell(row,key),"management"));
  const totalWidth=MANAGEMENT_FIELDS.reduce((sum,[key,,w])=>sum+(widths["management:"+key]??w),0);
  return <ReportTableShell label="清货管理表格"><ProTable<ClearanceApplication>
    rowKey="id" search={false} options={false} toolBarRender={false} dataSource={rows} columns={columns}
    scroll={{x:totalWidth,y:"100%"}}
    pagination={{current:state.page,pageSize:state.pageSize,total,size:"small",showSizeChanger:true,
      showQuickJumper:true,pageSizeOptions:REPORT_TABLE_PAGE_SIZE_OPTIONS,onChange:onPage}}
    locale={{emptyText:"暂无符合条件的清货申请"}}/>
  </ReportTableShell>;
}
