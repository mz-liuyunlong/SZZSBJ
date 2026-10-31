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

export const ANALYSIS_FIELDS = [
  ["identity","商品 ID / 品名",187],["sku","SKU / MSKU",153],["store","店铺 / 负责人",127],
  ["risk","风险等级",95],["source","识别来源",91],["wfs","WFS 可售",86],["age","库龄",66],
  ["coverage","售罄天数",83],["stockCost","库存成本",106],["price","售价",73],
  ["daily","7 / 14 / 30 日均销量",145],["revenue","7 / 14 / 30 天销售额",150],
  ["ads","7 / 14 / 30 天广告费",150],["adRate","7 / 14 / 30 天广告占比",145],
  ["profit","7 / 14 / 30 天利润",150],["profitRate","7 / 14 / 30 天利润率",145],
  ["returns","30 天退货率",106],["rating","评分",86],["units","7 / 14 / 30 天销量",130],
  ["status","进度 / 状态",114],["action","操作",136],
] as const;
export const MANAGEMENT_FIELDS = [
  ["id","清货申请单",155],["item","清货对象",212],["store","店铺 / 负责人",140],
  ["source","申请来源",100],["reason","清货原因",110],["method","清货方式",156],
  ["goal","目标清货量",100],["sold","已销售",95],["removed","移除 / 弃置",108],
  ["progress","处理进度",136],["cost","目标库存成本",116],["due","计划截止",118],
  ["status","任务状态",100],["submitted","提交时间",136],["action","操作",128],
] as const;
export const PERIODS:PeriodDays[]=[7,14,30];
export const money=(n:number|null|undefined)=>n==null?"—":(n<0?"−":"")+"$"+Math.abs(n).toLocaleString("en-US",{minimumFractionDigits:2,maximumFractionDigits:2});
export const integer=(n:number)=>n.toLocaleString("en-US",{maximumFractionDigits:0});
export const percent=(n:number|null|undefined)=>n==null?"—":n.toFixed(1)+"%";
export const riskColor:Record<RiskLevel,string>={high:"error",medium:"warning",low:"default"};
export function RiskTag({level}:{level:RiskLevel}){return <Tag color={riskColor[level]}>{RISK_NAMES[level]}</Tag>;}
export function StatusTag({status}:{status:ClearanceTask["status"]}){
  const color:Record<ClearanceTask["status"],string>={pending:"gold",supplement:"orange",ready:"processing",running:"blue",paused:"default",done:"success",rejected:"error",cancelled:"default"};
  return <Tag color={color[status]}>{STATUS_NAMES[status]}</Tag>;
}
export type StackKey="daily"|"revenue"|"ads"|"adRate"|"profit"|"profitRate"|"units";
export function PeriodStack({product,metric}:{product:ClearanceProduct;metric:StackKey}){
  return <div className="clearance-period-stack">{PERIODS.map(days=>{
    const x=product.per[days];
    const value=metric==="daily"?(x.units/days).toFixed(2)
      :metric==="revenue"?money(x.revenue)
      :metric==="ads"?money(x.ads)
      :metric==="adRate"?percent(x.adRate)
      :metric==="profit"?money(x.profit)
      :metric==="profitRate"?percent(x.margin):integer(x.units);
    return <div className="clearance-period-stack__row" key={days}>
      <span>{days}天</span><strong className={(metric==="profit"&&x.profit<0)||(metric==="profitRate"&&x.margin!==null&&x.margin<0)?"is-negative":undefined}>{value}</strong>
    </div>;
  })}</div>;
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
export function ClearanceAnalysisTable({rows,rules,tasks,manual,state,onPage,onInspect,onApply,onTask}:TableCommon&{
  rows:ClearanceProduct[];rules:ClearanceRules;tasks:ClearanceTask[];manual:string[];
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
    case "daily":case "revenue":case "ads":case "adRate":case "profit":case "profitRate":case "units":return <PeriodStack product={x} metric={key}/>;
    case "returns":return <><strong>{percent(x.per[30].units>0?x.returns/x.per[30].units*100:null)}</strong><Typography.Text type="secondary" className="clearance-subline">{x.returns} 次 / {x.per[30].units} 单</Typography.Text></>;
    case "rating":return <><span className="clearance-star">★</span> <strong>{x.rating.toFixed(1)}</strong><Typography.Text type="secondary" className="clearance-subline">{x.reviewCount} 条评价</Typography.Text></>;
    case "status":return active?<StatusTag status={active.status}/>:recent?.status==="done"?<StatusTag status="done"/>:<Tag>待评估</Tag>;
    case "action":return <Space size={3}><Button type="link" onClick={()=>onInspect(x.id)}>详情</Button>{active?<Button type="link" onClick={()=>onTask(active.id)}>任务</Button>:<Button type="link" onClick={()=>onApply(x.id)}>申请清货</Button>}</Space>;
    default:return "—";
    }
  };
  const fields=ANALYSIS_FIELDS.filter(([key])=>state.columns.includes(key));
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
  const fields=MANAGEMENT_FIELDS.filter(([key])=>state.columns.includes(key));
  const columns=fields.map(([key,label,width])=>makeColumn<ClearanceTask>(key,label,width,widths,onWidth,row=>cell(row,key),"management"));
  return <ReportTableShell label="清货管理表格"><ProTable<ClearanceTask>
    rowKey="id" search={false} options={false} toolBarRender={false} dataSource={rows} columns={columns}
    scroll={{x:fields.reduce((n,[key,,w])=>n+(widths["management:"+key]??w),0)}}
    pagination={{current:state.page,pageSize:state.pageSize,total:rows.length,size:"small",showSizeChanger:true,showQuickJumper:true,pageSizeOptions:REPORT_TABLE_PAGE_SIZE_OPTIONS,onChange:onPage}}
    locale={{emptyText:"暂无符合条件的清货申请"}}/>
  </ReportTableShell>;
}
