import { Button, Progress, Space, Tag, Typography } from "antd";
import { ProTable, type ProColumns } from "@ant-design/pro-components";
import { useState, type ReactNode } from "react";
import ReportTableShell from "@/components/report-table/ReportTableShell";
import ResizableColumnTitle from "@/components/report-table/ResizableColumnTitle";
import { REPORT_TABLE_PAGE_SIZE_OPTIONS } from "@/components/report-table/pagination";
import {
  activeTaskFor, coverage, evaluateProduct, findProduct, latestTaskFor,
  RISK_NAMES, STATUS_NAMES, taskCost, taskProgress, taskQty, taskRemoved, taskSold, taskStore,
  type ClearanceProduct, type ClearanceRules, type ClearanceTask, type RiskLevel, type PeriodDays,
} from "./clearanceModel";

import { ANALYSIS_FIELDS, MANAGEMENT_FIELDS, getClearancePeriodMetrics, money, integer, percent } from "./clearanceUiConfig";
const riskColor:Record<RiskLevel,string>={high:"error",medium:"warning",low:"default"};
export function RiskTag({level}:{level:RiskLevel}){return <Tag color={riskColor[level]}>{RISK_NAMES[level]}</Tag>;}
export function StatusTag({status}:{status:ClearanceTask["status"]}){
  const color:Record<ClearanceTask["status"],string>={pending:"gold",supplement:"orange",ready:"processing",running:"blue",paused:"default",done:"success",rejected:"error",cancelled:"default"};
  return <Tag color={color[status]}>{STATUS_NAMES[status]}</Tag>;
}
export interface TableState {page:number;pageSize:number;columns:string[]}
interface TableCommon {
  state:TableState; onPage:(page:number,pageSize:number)=>void;
}
function makeColumn<T>(
  key:string,label:string,initialWidth:number,widths:Record<string,number>,
  onWidth:(key:string,value:number)=>void,render:(row:T)=>ReactNode,tab:string,
):ProColumns<T>{
  const width=widths[tab+":"+key]??initialWidth;
  return {
    key,dataIndex:key,
    title:<ResizableColumnTitle label={label} width={width} minWidth={Math.min(width,110)} onWidthChange={n=>onWidth(tab+":"+key,n)}/>,
    width,ellipsis:false,
    fixed:key==="identity"||key==="id"?"left":key==="action"?"right":undefined,
    onHeaderCell:()=>({className:"report-table-resizable-header-cell"}),
    render:(_,row)=>render(row),
  };
}
export function ClearanceAnalysisTable({rows,rules,tasks,manual,period,state,onPage,onInspect,onApply,onTask}:TableCommon&{
  rows:ClearanceProduct[];rules:ClearanceRules;tasks:ClearanceTask[];manual:string[];period:PeriodDays;
  onInspect:(id:string)=>void;onApply:(id:string)=>void;onTask:(id:string)=>void;
}){
  const [widths,setWidths]=useState<Record<string,number>>({});
  const onWidth=(key:string,value:number)=>setWidths(old=>({...old,[key]:value}));
  const cell=(x:ClearanceProduct,key:string):ReactNode=>{
    const risk=evaluateProduct(x,rules),active=activeTaskFor(tasks,x.id),recent=latestTaskFor(tasks,x.id);
    switch(key){
    case "identity":return <><Button type="link" className="clearance-table-link" onClick={()=>onInspect(x.id)}>{x.name}</Button><Typography.Text className="clearance-subline" type="secondary">{x.item}</Typography.Text></>;
    case "sku":return <><strong>{x.sku}</strong><Typography.Text className="clearance-subline" type="secondary">{x.msku}</Typography.Text></>;
    case "store":return <>{x.store}<Typography.Text className="clearance-subline" type="secondary">{x.owner}</Typography.Text></>;
    case "risk":return <><RiskTag level={risk.level}/><Typography.Text type="secondary" className="clearance-subline">{risk.business.length?"含经营异常":"库存条件触发"}</Typography.Text></>;
    case "source":return <Tag color={manual.includes(x.id)?"purple":"blue"}>{manual.includes(x.id)?(risk.auto?"人工申请 + 风险":"运营主动申请"):"系统识别"}</Tag>;
    case "wfs":return <strong>{integer(x.avail)} 件</strong>;
    case "age":return x.age+"天";
    case "coverage":return coverage(x)==null?"无法估算":integer(coverage(x)??0)+"天";
    case "stockCost":return <strong>{money(x.avail*x.cost)}</strong>;
    case "price":return money(x.price);
    case "daily":case "revenue":case "ads":case "adRate":case "profit":case "profitRate":case "units":{
      const m=getClearancePeriodMetrics(x,period);
      const value=key==="daily"?m.daily.toFixed(2)
        :key==="revenue"?money(m.revenue)
        :key==="ads"?money(m.ads)
        :key==="adRate"?percent(m.adRate)
        :key==="profit"?money(m.profit)
        :key==="profitRate"?percent(m.profitRate):integer(m.units);
      const negative=(key==="profit"&&m.profit<0)||(key==="profitRate"&&m.profitRate!==null&&m.profitRate<0);
      return <strong className={negative?"clearance-period-value is-negative":"clearance-period-value"}>{value}</strong>;
    }
    case "returns":return <><strong>{percent(x.per[30].units>0?x.returns/x.per[30].units*100:null)}</strong><Typography.Text type="secondary" className="clearance-subline">{x.returns} 次 / {x.per[30].units} 单</Typography.Text></>;
    case "rating":return <><span className="clearance-star">★</span> <strong>{x.rating.toFixed(1)}</strong><Typography.Text type="secondary" className="clearance-subline">{x.reviewCount} 条评价</Typography.Text></>;
    case "status":return active?<StatusTag status={active.status}/>:recent?.status==="done"?<StatusTag status="done"/>:<Tag>待评估</Tag>;
    case "action":return <Space size={3}><Button type="link" onClick={()=>onInspect(x.id)}>详情</Button>{active?<Button type="link" onClick={()=>onTask(active.id)}>任务</Button>:<Button type="link" onClick={()=>onApply(x.id)}>申请清货</Button>}</Space>;
    default:return "—";
    }
  };
  const fields=state.columns.flatMap(key=>ANALYSIS_FIELDS.filter(([name])=>name===key));
  const columns=fields.map(([key,label,width])=>makeColumn<ClearanceProduct>(key,label,width,widths,onWidth,row=>cell(row,key),"analysis"));
  return <ReportTableShell label="清货分析表格"><ProTable<ClearanceProduct>
    rowKey="id" search={false} options={false} toolBarRender={false} columns={columns} dataSource={rows}
    scroll={{x:fields.reduce((n,[key,,w])=>n+(widths["analysis:"+key]??w),0)}}
    pagination={{current:state.page,pageSize:state.pageSize,total:rows.length,size:"small",showSizeChanger:true,showQuickJumper:true,pageSizeOptions:REPORT_TABLE_PAGE_SIZE_OPTIONS,onChange:onPage}}
    locale={{emptyText:"暂无符合条件的清货商品，正常 SKU 可以通过申请 SKU 搜索"}}/>
  </ReportTableShell>;
}
export function ClearanceManagementTable({rows,state,onPage,onTask}:TableCommon&{
  rows:ClearanceTask[];onTask:(id:string)=>void;
}){
  const [widths,setWidths]=useState<Record<string,number>>({});
  const onWidth=(key:string,value:number)=>setWidths(old=>({...old,[key]:value}));
  const cell=(t:ClearanceTask,key:string):ReactNode=>{
    const first=findProduct(t.lines[0]?.id);
    switch(key){
    case "id":return <><Button type="link" className="clearance-table-link" onClick={()=>onTask(t.id)}>{t.id}</Button><Typography.Text className="clearance-subline" type="secondary">{t.lines.length} 个 SKU</Typography.Text></>;
    case "item":return <><strong>{first?.name??"—"}</strong><Typography.Text className="clearance-subline" type="secondary">{first?.sku}{t.lines.length>1?" 等":""}</Typography.Text></>;
    case "store":return <>{taskStore(t)}<Typography.Text className="clearance-subline" type="secondary">{t.owner}</Typography.Text></>;
    case "source":return <Tag color={t.source==="manual"?"purple":"blue"}>{t.source==="manual"?"运营主动":"系统识别"}</Tag>;
    case "reason":return t.reason;
    case "method":return t.methods.join(" / ");
    case "goal":return <strong>{integer(taskQty(t))} 件</strong>;
    case "sold":return integer(taskSold(t))+" 件";
    case "removed":return integer(taskRemoved(t))+" 件";
    case "progress":return <div className="clearance-progress"><strong>{taskProgress(t)}%</strong><Progress percent={taskProgress(t)} showInfo={false} size="small"/></div>;
    case "cost":return <strong>{money(taskCost(t))}</strong>;
    case "due":return t.due;
    case "status":return <StatusTag status={t.status}/>;
    case "submitted":return t.submitted;
    case "action":return <Button type="link" onClick={()=>onTask(t.id)}>任务详情</Button>;
    default:return "—";
    }
  };
  const fields=state.columns.flatMap(key=>MANAGEMENT_FIELDS.filter(([name])=>name===key));
  const columns=fields.map(([key,label,width])=>makeColumn<ClearanceTask>(key,label,width,widths,onWidth,row=>cell(row,key),"management"));
  return <ReportTableShell label="清货管理表格"><ProTable<ClearanceTask>
    rowKey="id" search={false} options={false} toolBarRender={false} dataSource={rows} columns={columns}
    scroll={{x:fields.reduce((n,[key,,w])=>n+(widths["management:"+key]??w),0)}}
    pagination={{current:state.page,pageSize:state.pageSize,total:rows.length,size:"small",showSizeChanger:true,showQuickJumper:true,pageSizeOptions:REPORT_TABLE_PAGE_SIZE_OPTIONS,onChange:onPage}}
    locale={{emptyText:"暂无符合条件的清货申请"}}/>
  </ReportTableShell>;
}
