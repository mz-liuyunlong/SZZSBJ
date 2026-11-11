// PR337_BOARD_TO_DETAIL_V5
// PR337_TRACKING_SINGLE_SOURCE_V4: one source, no data switch
import { useLayoutEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { Button, DatePicker, Empty, Table, Tooltip } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import {
  AppstoreOutlined, CloseCircleOutlined, BellOutlined, CheckOutlined, InfoCircleOutlined, RightOutlined, UnorderedListOutlined,
} from '@ant-design/icons';
import dayjs, { type Dayjs } from 'dayjs';
import { type Config, type Product } from './nativeData';
import { withTrackingVisualSamples } from './trackingBoardVisualSamples';
import { daysBetween } from './trackingBoardMetrics';
import type { TrackingDrillFilter, TrackingDrillKind } from './trackingBoardDrilldown';
import {
  buildTrackingView, rateText, type TrackingCategoryRow,
  type TrackingOwnerRow, type TrackingObservationRow,
} from './trackingBoardMetrics';
import './performanceBoardRedesign.css'; // Reuse the completed New Product overview styles.
import './trackingDashboard.css';

type Props = {
  products: Product[];
  config: Config;
  onDrill:(filter:TrackingDrillFilter)=>void;
};

const gradeColors:Record<string,string>={S:'#7c3aed',A:'#1677ff',B:'#16a34a',C:'#fb923c',D:'#ef4444',Pass:'#94a3b8','待评分':'#cbd5e1'};
function Meter({value,color='#1677ff'}:{value:number|null;color?:string}){
  return <div className="np-track-meter" title={value===null?'缺少已完成结果，不能计算比例':rateText(value)}>
    <span className="np-track-meter-track"><span style={{width:`${Math.max(0,Math.min(100,value??0))}%`,background:color}}/></span>
    <b>{rateText(value)}</b>
  </div>;
}
function Block({title,sub,action,children,className=''}:{title:string;sub?:string;action?:ReactNode;children:ReactNode;className?:string}){
  return <section className={`np-track-panel ${className}`}>
    <div className="np-track-panel-header">
      <div className="np-track-panel-heading"><strong>{title}</strong>{sub&&<span>{sub}</span>}</div>
      {action&&<div className="np-track-panel-action">{action}</div>}
    </div>
    <div className="np-track-panel-content">{children}</div>
  </section>;
}
function PrimaryMetric({label,number,description,icon,tone}:{label:string;number:string|number;description:string;icon:ReactNode;tone:string}){
  // Identical metric DOM/classes to PerformanceBoardRedesign; tracking keeps its own business actions.
  return <div className={`np-pb-metric np-pb-metric-${tone}`}
    aria-label={`${label}：${number}，${description}`}>
    <div className="np-pb-metric-head"><span className="np-pb-metric-icon">{icon}</span><b>{label}</b></div>
    <strong>{number}</strong><span>{description}</span>
  </div>;
}
function EmptyContent({text}:{text:string}){
  return <div className="np-track-empty"><Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={text}/></div>;
}
const tableDefaults={pagination:false as const,size:'small' as const,tableLayout:'fixed' as const};
export default function TrackingDashboard({products,config,onDrill}:Props){
  // Same measured-viewport approach as the accepted PerformanceBoardRedesign.
  const viewportRef=useRef<HTMLDivElement>(null);
  useLayoutEffect(()=>{
    const element=viewportRef.current;
    if(!element)return;
    const fit=()=>{
      const top=Math.max(0,element.getBoundingClientRect().top);
      const available=Math.max(0,window.innerHeight-top-16);
      element.style.setProperty('--np-track-viewport-height',`${Math.floor(available)}px`);
    };
    fit();
    window.addEventListener('resize',fit);
    return ()=>window.removeEventListener('resize',fit);
  },[]);
  const [dateRange,setDateRange]=useState<[Dayjs,Dayjs]>(()=>[dayjs().subtract(59,'day'),dayjs()]);
  // ONE Product[] path. Add layout fixtures only while the parent still supplies
  // the seven known original PR337 Mock products. Real API rows are never padded.
  const sampleAnchor=useMemo(()=>dayjs().format('YYYY-MM-DD'),[]);
  const visibleProducts=useMemo(()=>withTrackingVisualSamples(products,sampleAnchor),[products,sampleAnchor]);

  const from=dateRange[0].format('YYYY-MM-DD');
  const through=dateRange[1].format('YYYY-MM-DD');
  const data=useMemo(()=>buildTrackingView(visibleProducts,config,from,through),[visibleProducts,config,from,through]);
  const drill=(kind:TrackingDrillKind,label:string,value?:string,parentCategory?:string)=>
    onDrill({kind,label,value,parentCategory,from,to:through});
  const gradeMax=Math.max(1,...data.grades.map(g=>g.total));
  const hasStoredInitialGrade=visibleProducts.some(p=>typeof (p as Product & {initialGrade?:string}).initialGrade==='string');
  const ownerColumns:ColumnsType<TrackingOwnerRow>=[
    {title:'人员',dataIndex:'name',key:'name',width:94,ellipsis:true,render:(v:string)=><span className="np-track-owner"><span className="np-track-avatar">{v.slice(0,1)}</span>{v}</span>},
    {title:'测评数',dataIndex:'total',key:'total',width:67,align:'center'},
    {title:'不通过数',dataIndex:'failed',key:'failed',width:75,align:'center'},
    {title:'通过数',dataIndex:'success',key:'success',width:67,align:'center'},
    {title:<Tooltip title="通过率 = 打品成功数 ÷（成功数 + 失败数）；继续观察不算失败。">通过率 <InfoCircleOutlined/></Tooltip>,key:'rate',width:145,render:(_,row)=><Meter value={row.rate}/>},
    {title:'操作',key:'action',width:88,align:'center',render:(_,row)=><Button size="small" onClick={()=>drill('owner',`${row.name} · 打品商品`,row.name)}>查看商品</Button>},
  ];
  const categoryColumns:ColumnsType<TrackingCategoryRow>=[
    {title:'一级类目',dataIndex:'category',key:'category',ellipsis:true,width:130,render:(v:string)=><button className="np-track-text-action" onClick={()=>drill('category',`${v} · 一级类目`,v)}>{v}</button>},
    {title:'测品数',dataIndex:'total',key:'total',align:'center',width:62},
    {title:'通过',dataIndex:'success',key:'success',align:'center',width:57},
    {title:'不通过',dataIndex:'failed',key:'failed',align:'center',width:63},
    {title:'通过率',key:'rate',width:135,render:(_,row)=><Meter value={row.rate}/>},
    {title:<Tooltip title="当前规则未定义类目方向建议阈值，不自动编造决策。">方向建议 <InfoCircleOutlined/></Tooltip>,key:'recommendation',width:87,align:'center',render:(_,row)=><span className="np-track-neutral-tag">{row.recommendation}</span>},
  ];
  const secondaryColumns:ColumnsType<TrackingCategoryRow>=[
    {title:'一级类目',key:'parent',width:116,ellipsis:true,render:(_,row)=>row.products[0]?.category||'未分类'},
    {title:'二级类目',dataIndex:'category',key:'category',width:148,ellipsis:true,render:(v:string,row)=><button className="np-track-text-action" onClick={()=>drill('secondary',`${v} · 二级类目`,v,row.products[0]?.category)}>{v}</button>},
    {title:'样本',dataIndex:'total',key:'total',width:55,align:'center'},
    {title:'通过',dataIndex:'success',key:'success',width:55,align:'center'},
    {title:'不通过',dataIndex:'failed',key:'failed',width:65,align:'center'},
    {title:'成功率',key:'rate',width:135,render:(_,row)=><Meter value={row.rate}/>},
  ];
  const observationColumns:ColumnsType<TrackingObservationRow>=[
    {title:'到货后天数',dataIndex:'label',key:'label',width:102},
    {title:'样本',dataIndex:'total',key:'total',width:55,align:'center'},
    {title:'成功',dataIndex:'success',key:'success',width:55,align:'center'},
    {title:'淘汰',dataIndex:'failed',key:'failed',width:55,align:'center'},
    {title:'稳定',dataIndex:'stable',key:'stable',width:55,align:'center'},
    {title:'待定',dataIndex:'pending',key:'pending',width:55,align:'center'},
    {title:<Tooltip title="成功率仅使用已有明确结果的样本。缺少完成结果时显示横杠。">判定率 <InfoCircleOutlined/></Tooltip>,key:'rate',width:126,render:(_,row)=><button className="np-track-inline-rate" onClick={()=>drill('observation',`${row.label} · 跟踪明细`,row.label)}>{rateText(row.rate)}</button>},
  ];
  const successPct=data.successRate===null?'—':`${data.successRate.toFixed(1)}%`;
  return <div ref={viewportRef} className="np-tracking-dashboard" data-pr337-tracking="viewport-single-source-v4">
    <div className="np-track-date-bar">
      <div className="np-track-date-control"><strong>日期范围</strong>
        <DatePicker.RangePicker value={dateRange} allowClear={false} format="YYYY-MM-DD"
          onChange={v=>{if(v?.[0]&&v[1])setDateRange([v[0],v[1]])}}/>
      </div>

    </div>
    <div className="np-track-main">
      <aside className="np-pb-overview np-track-overview-unified" aria-label="核心指标总览">
        <div className="np-pb-overview-title"><AppstoreOutlined/><h2>核心指标总览</h2></div>
        <div className="np-pb-metrics">
          <PrimaryMetric label="进入打品池" number={data.pool.length} description="采购批准后进入追踪" icon={<UnorderedListOutlined/>} tone="blue" />
          <PrimaryMetric label="打品成功率" number={successPct} description={`成功 ${data.success.length} / 入池 ${data.pool.length}`} icon={<CheckOutlined/>} tone="green" />
          <PrimaryMetric label="打品不通过数" number={data.failed.length} description="已确认打品失败的商品" icon={<CloseCircleOutlined/>} tone="red"/>
          <PrimaryMetric label="打品不通过类目数" number={data.categories.filter(row=>row.failed>0 && row.category!=='未分类').length} description="存在失败商品的一级类目" icon={<AppstoreOutlined/>} tone="orange"/>
        </div>
        <section className="np-pb-reminders np-track-reminder-unified" aria-label="待复盘提醒">
          <div className="np-pb-reminder-title">
            <BellOutlined/>
            <div><h3>待复盘提醒</h3><p>到货可售超过45天，仍未形成最终打品结论</p>
              <span className="np-track-reminder-counter">当前范围 {data.due.length} 个待人工判定商品</span>
            </div>
          </div>
          <div className="np-pb-reminder-table-wrap">
            <table className="np-pb-reminder-table">
              <thead><tr><th>商品</th><th>运营负责人</th><th>到货后天数</th><th>操作</th></tr></thead>
              <tbody>
                {data.due.map(p=><tr key={p.id}>
                  <td><strong>{p.sku}</strong><small title={p.name}>{p.name}</small></td>
                  <td>{p.operator?.trim()||p.owner||'—'}</td>
                  <td><span className="np-pb-days">{daysBetween(p.arrival,through)??"—"} 天</span></td>
                  <td><button type="button" className="np-pb-mini-button"
                    onClick={()=>drill('item',`${p.sku} · 待人工判定`,p.item||p.sku)}>
                    去判定
                  </button></td>
                </tr>)}
                {data.due.length===0&&<tr><td colSpan={4} className="np-track-no-reminders">当前日期范围没有超过45天的待人工判定商品</td></tr>}
              </tbody>
            </table>
          </div>
        </section>
      </aside>
      <div className="np-track-analytics">
        <div className="np-track-analytics-top">
          <Block title="初始评级与打品结果" sub="已完成测评" className="np-track-rating-panel"
            action={<Button type="link" size="small" onClick={()=>drill('all','初始评级与打品结果')}>查看等级明细 <RightOutlined/></Button>}>
            <div className="np-track-grades">{data.grades.map(row=><button className="np-track-grade-row" key={row.key} onClick={()=>drill('grade',`${row.grade} · 跟踪商品`,row.grade)}>
              <span>{row.grade==='待评分'?'待评分':row.grade==='Pass'?'Pass':`${row.grade}级`}</span>
              <span className="np-track-grade-rail"><span style={{width:`${row.total/gradeMax*100}%`,background:gradeColors[row.grade]}}/></span>
              <strong>{row.total}</strong>
            </button>)}</div>
            <div className="np-track-rating-foot">{hasStoredInitialGrade?'按已存初始评级统计':'当前 Mock 无初始评级快照：暂按现有评分展示，不能当正式历史评级'}</div>
          </Block>
          <Block title="运营人员打品表现" sub="完成度与有效评估统计" className="np-track-operators-panel">
            <Table<TrackingOwnerRow> {...tableDefaults} columns={ownerColumns} dataSource={data.owners} rowKey="key" locale={{emptyText:'暂无运营人员追踪数据'}}/>
          </Block>
        </div>
        <div className="np-track-analytics-bottom">
          <Block title="一级类目表现" className="np-track-category-panel">
            <Table<TrackingCategoryRow> {...tableDefaults} columns={categoryColumns} dataSource={data.categories} rowKey="key"
              locale={{emptyText:'所选日期内暂无类目测评数据'}}/>
          </Block>
          <div className="np-track-analytics-stack">
            <Block title="二级类目分析" className="np-track-secondary-panel">
              {data.secondary.length?<Table<TrackingCategoryRow> {...tableDefaults} columns={secondaryColumns} dataSource={data.secondary} rowKey="key"/>:
                <EmptyContent text="当前商品缺少二级类目字段，暂不编造类目数据"/>}
              {data.noSecondary>0&&<div className="np-track-panel-foot">{data.noSecondary} 个商品暂无二级类目映射；映射补齐后自动展示。</div>}
            </Block>
            <Block title="观察期分析" className="np-track-observation-panel">
              <Table<TrackingObservationRow> {...tableDefaults} columns={observationColumns} dataSource={data.observations} rowKey="key"/>
              <p className="np-track-panel-foot">观察期按到货后自然日分组；不含真实历史快照。成功率仅在出现明确成功或失败结果后计算。</p>
            </Block>
          </div>
        </div>
      </div>
    </div>

  </div>;
}
