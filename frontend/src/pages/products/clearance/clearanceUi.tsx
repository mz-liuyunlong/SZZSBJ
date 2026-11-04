import {
  Button, Progress, Space, Tag, Typography } from "antd";
import { FundOutlined, NotificationOutlined, DollarCircleOutlined } from "@ant-design/icons";
import { ProTable, type ProColumns } from "@ant-design/pro-components";
import { useState, type ReactNode } from "react";
import ReportTableShell from "@/components/report-table/ReportTableShell";
import ResizableColumnTitle from "@/components/report-table/ResizableColumnTitle";
import { REPORT_TABLE_PAGE_SIZE_OPTIONS } from "@/components/report-table/pagination";
import {
  activeTaskFor, coverage, evaluateProduct, findProduct, latestTaskFor, RISK_NAMES, STATUS_NAMES, type ClearanceProduct, type ClearanceRules, type ClearanceTask, type RiskLevel, type PeriodDays
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
  const tone=tab==="analysis"?metricTone(key):null;
  return {
    key,dataIndex:key,
    title:<ResizableColumnTitle label={label} width={width} minWidth={Math.min(width,110)} onWidthChange={n=>onWidth(tab+":"+key,n)}/>,
    width,ellipsis:false,
    className:tone?`clearance-metric-cell clearance-metric-cell--${tone}`:undefined,
    fixed:key==="action"?"right":(tab==="analysis"&&(key==="identity"||key==="sku"))||(tab==="management"&&(key==="id"||key==="item"))?"left":undefined,
    onHeaderCell:()=>({className:"report-table-resizable-header-cell"+(tone?` clearance-metric-child-header clearance-metric-child-header--${tone}`:"")}),
    render:(_,row)=>render(row),
  };
}

// PR285_SIX_METRIC_GROUPS
function metricTone(key:string):"sales"|"ads"|"profit"|null {
  if(key==="revenue"||key==="daily")return "sales";
  if(key==="ads"||key==="adRate")return "ads";
  if(key==="profit"||key==="profitRate")return "profit";
  return null;
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

      return <div className="clearance-metric-content">
        <strong className={negative
          ?"clearance-period-value is-negative"
          :"clearance-period-value"}>{value}</strong>
      </div>;

    }
    case "returns":return <><strong>{percent(x.per[30].units>0?x.returns/x.per[30].units*100:null)}</strong><Typography.Text type="secondary" className="clearance-subline">{x.returns} 次 / {x.per[30].units} 单</Typography.Text></>;
    case "rating":return <><span className="clearance-star">★</span> <strong>{x.rating.toFixed(1)}</strong><Typography.Text type="secondary" className="clearance-subline">{x.reviewCount} 条评价</Typography.Text></>;
    case "status":return active?<StatusTag status={active.status}/>:recent?.status==="done"?<StatusTag status="done"/>:<Tag>待评估</Tag>;
    case "action":return <Space size={3}><Button type="link" onClick={()=>onInspect(x.id)}>详情</Button>{active?<Button type="link" onClick={()=>onTask(active.id)}>任务</Button>:<Button type="link" onClick={()=>onApply(x.id)}>申请清货</Button>}</Space>;
    default:return "—";
    }
  };
  const fields=state.columns.flatMap(key=>ANALYSIS_FIELDS.filter(([name])=>name===key));
  const leafColumns=fields.map(([key,label,width])=>makeColumn<ClearanceProduct>(key,label,width,widths,onWidth,row=>cell(row,key),"analysis"));

  const groups=[
    {id:"sales",name:"销售表现",keys:["revenue","daily"]},
    {id:"ads",name:"广告表现",keys:["ads","adRate"]},
    {id:"profit",name:"利润表现",keys:["profit","profitRate"]},
  ] as const;

  const columns:ProColumns<ClearanceProduct>[]=[];
  const added=new Set<string>();

  fields.forEach(([key],index)=>{
    const group=groups.find(g=>g.keys.some(k=>k===key));
    if(!group){
      columns.push(leafColumns[index]);
      return;
    }
    if(added.has(group.id))return;
    added.add(group.id);

    const children=group.keys.map(k=>{
      const i=fields.findIndex(([name])=>name===k);
      return i>=0?leafColumns[i]:undefined;
    }).filter((c):c is ProColumns<ClearanceProduct>=>c!==undefined);

    const icon=group.id==="sales"?<FundOutlined/>
      :group.id==="ads"?<NotificationOutlined/>
      :<DollarCircleOutlined/>;

    columns.push({
      key:"metric-"+group.id,
      title:<span className={`clearance-metric-group-title clearance-metric-group-title--${group.id}`}>
        <span className="clearance-metric-group-icon">{icon}</span>
        {group.name}
      </span>,
      children,
      onHeaderCell:()=>({
        className:`clearance-metric-group-header clearance-metric-group-header--${group.id}`
      }),
    });
  });
  return <ReportTableShell label="清货分析表格"><ProTable<ClearanceProduct>
    rowKey="id" search={false} options={false} toolBarRender={false} columns={columns} dataSource={rows}
    scroll={{x:fields.reduce((n,[key,,w])=>n+(widths["analysis:"+key]??w),0),y:"100%"}}
    pagination={{current:state.page,pageSize:state.pageSize,total:rows.length,size:"small",showSizeChanger:true,showQuickJumper:true,pageSizeOptions:REPORT_TABLE_PAGE_SIZE_OPTIONS,onChange:onPage}}
    locale={{emptyText:"暂无符合条件的清货商品，正常 SKU 可以通过申请 SKU 搜索"}}/>
  </ReportTableShell>;
}



// PR285_MANAGEMENT_16_COLUMNS_SALES_ONLY_V1
/**
 * 每个 SKU 单独展示一行；同一申请单的公共状态、原因和日期保持关联。
 * 清货进度仅统计实际已销售件数，不把移除或弃置计入百分比。
 */
type Pr285ClearanceManagementSkuRow = {
  task: ClearanceTask;
  line: ClearanceTask["lines"][number];
};

export function ClearanceManagementTable({ rows, state, onPage, onTask }: TableCommon & {
  rows: Array<ClearanceTask | Pr285ClearanceManagementSkuRow>;
  onTask: (id: string) => void;
}) {
  const [widths, setWidths] = useState<Record<string, number>>({});
  const onWidth = (key: string, value: number) =>
    setWidths(old => ({ ...old, [key]: value }));

  // Compatible with both original task rows and previously flattened SKU rows.
  const skuRows: Pr285ClearanceManagementSkuRow[] = rows.flatMap(entry => {
    if ("task" in entry && "line" in entry) {
      return [{ task: entry.task, line: entry.line }];
    }
    return entry.lines.map(line => ({ task: entry, line }));
  });

  const cell = (row: Pr285ClearanceManagementSkuRow, key: string): ReactNode => {
    const { task, line } = row;
    const product = findProduct(line.id);
    switch (key) {
      case "identity":
        return <>
          <strong>{product?.name ?? "—"}</strong>
          <Typography.Text className="clearance-subline" type="secondary">
            {product?.item ?? line.id}
          </Typography.Text>
        </>;
      case "sku":
        return <>
          <strong>{product?.sku ?? "—"}</strong>
          <Typography.Text className="clearance-subline" type="secondary">
            {product?.msku ?? "—"}
          </Typography.Text>
        </>;
      case "store":
        return <>
          {product?.store ?? "—"}
          <Typography.Text className="clearance-subline" type="secondary">
            {product?.owner ?? task.owner}
          </Typography.Text>
        </>;
      case "source":
        return <Tag color={task.source === "manual" ? "purple" : "blue"}>
          {task.source === "manual" ? "运营主动" : "系统识别"}
        </Tag>;
      case "reason":
        return task.reason;
      case "method":
        return task.methods.join(" / ");
      case "goal":
        return <strong>{integer(line.qty)} 件</strong>;
      case "sold":
        return integer(line.sold) + " 件";
      case "revenue": {
        // Only genuine recorded transaction revenue may appear here.
        // The current Mock task model does not contain a revenue field.
        // Never calculate sold * current listing price (prices may change).
        const recorded = line as typeof line & {
          actualSalesAmount?: number | null;
        };
        return typeof recorded.actualSalesAmount === "number" &&
          Number.isFinite(recorded.actualSalesAmount)
          ? <strong>{money(recorded.actualSalesAmount)}</strong>
          : <span title="当前任务尚无实际成交金额记录；不会使用当前售价估算">—</span>;
      }
      case "progress": {
        const soldPct = line.qty > 0
          ? Math.max(0, Math.min(100, Math.floor(line.sold * 100 / line.qty)))
          : 0;
        return <div
          className="clearance-progress"
          title={`仅统计销售进度：已销售 ${line.sold} 件 / 目标 ${line.qty} 件；移除和弃置不计入`}
        >
          <strong>{soldPct}%</strong>
          <Progress percent={soldPct} showInfo={false} size="small" />
        </div>;
      }
      case "cost": {
        // Original Mock only provides product unit cost, not an application-time snapshot.
        // Keep the existing estimated-cost behavior until snapshot data is available.
        const stored = line as typeof line & { unitCostAtApplication?: number | null };
        const unitCost = typeof stored.unitCostAtApplication === "number" &&
          Number.isFinite(stored.unitCostAtApplication)
          ? stored.unitCostAtApplication
          : product?.cost;
        return unitCost == null
          ? "—"
          : <strong>{money(line.qty * unitCost)}</strong>;
      }
      case "plannedStart": {
        const dated = task as ClearanceTask & { plannedStart?: string | null };
        return dated.plannedStart
          ? dated.plannedStart
          : <span title="当前任务没有保存计划开始日期，不能拿提交时间代替">—</span>;
      }
      case "due":
        return task.due || "—";
      case "status":
        return <StatusTag status={task.status} />;
      case "submitted":
        return task.submitted || "—";
      case "action":
        return <Button type="link" onClick={() => onTask(task.id)}>任务详情</Button>;
      default:
        return "—";
    }
  };

  // Always show the exact 16 agreed columns, including in worktrees with old
  // persisted column-key preferences (id/item/removed) from previous versions.
  const fields = MANAGEMENT_FIELDS;
  const columns = fields.map(([key, label, width]) => ({
    ...makeColumn<Pr285ClearanceManagementSkuRow>(
      key, label, width, widths, onWidth,
      row => cell(row, key), "management",
    ),
    fixed: key === "action" ? "right" as const
      : (key === "identity" || key === "sku") ? "left" as const
      : undefined,
  }));
  const totalWidth = fields.reduce(
    (n, [key, , width]) => n + (widths["management:" + key] ?? width), 0,
  );

  return <ReportTableShell label="清货管理表格">
    <ProTable<Pr285ClearanceManagementSkuRow>
      rowKey={row => row.task.id + ":" + row.line.id}
      search={false}
      options={false}
      toolBarRender={false}
      dataSource={skuRows}
      columns={columns}
      scroll={{ x: totalWidth, y: "100%" }}
      pagination={{
        current: state.page, pageSize: state.pageSize, total: skuRows.length,
        size: "small", showSizeChanger: true, showQuickJumper: true,
        pageSizeOptions: REPORT_TABLE_PAGE_SIZE_OPTIONS,
        onChange: onPage,
      }}
      locale={{ emptyText: "暂无符合条件的清货申请" }}
    />
  </ReportTableShell>;
}
