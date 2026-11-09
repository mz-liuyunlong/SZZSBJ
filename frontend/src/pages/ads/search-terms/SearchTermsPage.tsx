import { useCallback, useEffect, useMemo, useState } from "react";
import { Alert, Button, Card, Col, DatePicker, Descriptions, Drawer, Empty, Input, message, Row, Segmented, Select, Space, Statistic, Table, Tag, Typography } from "antd";
import { ReloadOutlined, SearchOutlined, EyeOutlined, PlusOutlined, StopOutlined } from "@ant-design/icons";
import dayjs, { type Dayjs } from "dayjs";
import PageShell from "@/components/page/PageShell";
import type { NavigationPage } from "@/config/navigation";
import { completeSearchTermAction, createSearchTermAction, getSearchTermSummary, listSearchTermActions, listSearchTerms, type SearchTermAction, type SearchTermQuery, type SearchTermRow, type SearchTermSummary } from "./searchTermsApi";
import "./SearchTermsPage.css";

const { RangePicker } = DatePicker;
const money=(v:string|null|undefined)=>v==null?"—":`$${Number(v).toFixed(2)}`;
const number=(v:number|null|undefined)=>v==null?"—":new Intl.NumberFormat("en-US").format(v);
const percent=(v:string|null|undefined)=>v==null?"—":`${Number(v).toFixed(2)}%`;

export default function SearchTermsPage({page}:{page:NavigationPage}){
 const [range,setRange]=useState<[Dayjs,Dayjs]>([dayjs().subtract(13,"day"),dayjs().subtract(1,"day")]);
 const [type,setType]=useState<"all"|"auto"|"manual">("all");
 const [conversion,setConversion]=useState<"all"|"orders"|"no_orders">("all");
 const [search,setSearch]=useState("");
 const [committedSearch,setCommittedSearch]=useState("");
 const [view,setView]=useState<"summary"|"detail">("detail");
 const [rows,setRows]=useState<SearchTermRow[]>([]);
 const [summary,setSummary]=useState<SearchTermSummary|null>(null);
 const [actions,setActions]=useState<SearchTermAction[]>([]);
 const [total,setTotal]=useState(0);
 const [loading,setLoading]=useState(false);
 const [syncError,setSyncError]=useState<string|null>(null);
 const [selected,setSelected]=useState<SearchTermRow|null>(null);
 const [actionBusy,setActionBusy]=useState(false);
 const [pageNo,setPageNo]=useState(1);
 const query=useMemo<SearchTermQuery>(()=>({
  start_date:range[0].format("YYYY-MM-DD"),end_date:range[1].format("YYYY-MM-DD"),
  targeting_type:type,conversion_state:conversion,query:committedSearch,page:pageNo,page_size:50,
 }),[range,type,conversion,committedSearch,pageNo]);
 const refresh=useCallback(async()=>{
  setLoading(true);setSyncError(null);
  try{
   const [list,stats,tasks]=await Promise.all([listSearchTerms(query),getSearchTermSummary(query),listSearchTermActions()]);
   setRows(list.items);setTotal(list.total);setSummary(stats);setActions(tasks.items);
  }catch(e){
   setSyncError(e instanceof Error?e.message:"搜索词数据读取失败");
   setRows([]);setTotal(0);setSummary(null);
  }finally{setLoading(false);}
 },[query]);
 useEffect(()=>{void Promise.resolve().then(refresh);},[refresh]);
 const handleAction=async(row:SearchTermRow,actionType:"add_keyword"|"add_negative_keyword")=>{
  setActionBusy(true);
  try{
   await createSearchTermAction({
    source_account_ref:row.source_account_ref,source_fact_id:row.id,action_type:actionType,
    search_term:row.searched_keyword,
    target_scope:{advertiser_id:row.advertiser_id,campaign_id:row.campaign_id,store_id:row.store_id,item_id:row.item_id,listing_mapping_status:row.listing_mapping_status},
    reason:"搜索词工作台人工处理任务；外部领星写入未接通",
   });
   message.success("已创建内部处理任务；尚未修改领星广告");
   await refresh();
  }catch(e){message.error(e instanceof Error?e.message:"创建处理任务失败");}
  finally{setActionBusy(false);}
 };
 const finishAction=async(item:SearchTermAction)=>{
  setActionBusy(true);
  try{await completeSearchTermAction(item.id,"已由运营在领星后台人工处理");message.success("已记录人工完成，未执行 API 写入");await refresh();}
  catch(e){message.error(e instanceof Error?e.message:"更新处理状态失败");}
  finally{setActionBusy(false);}
 };
 const columns=[
  {title:"搜索词",dataIndex:"searched_keyword",fixed:"left" as const,width:210,render:(v:string)=><Typography.Text strong>{v}</Typography.Text>},
  {title:"广告类型",dataIndex:"targeting_type",width:100,render:(v:string)=><Tag color={v==="auto"?"blue":"default"}>{v==="auto"?"自动":"手动"}</Tag>},
  {title:"店铺",dataIndex:"mp_seller_name",width:180,render:(v:string|null)=>v||"—"},
  {title:"广告活动",dataIndex:"campaign_name",width:220,render:(v:string|null,r:SearchTermRow)=><div><div>{v||"—"}</div><Typography.Text type="secondary" copyable>{r.campaign_id}</Typography.Text></div>},
  {title:"曝光",dataIndex:"num_ads_shown",align:"right" as const,width:90,render:number},
  {title:"点击",dataIndex:"num_ads_clicks",align:"right" as const,width:80,render:number},
  {title:"花费",dataIndex:"ad_spend_amount",align:"right" as const,width:100,render:money},
  {title:"订单",dataIndex:"attributed_orders",align:"right" as const,width:80,render:(v:string|null)=>v??"—"},
  {title:"直接销售额",dataIndex:"advertised_sku_sales_amount",align:"right" as const,width:120,render:money},
  {title:"关联销售额",dataIndex:"other_sku_sales_amount",align:"right" as const,width:120,render:money},
  {title:"CTR",dataIndex:"ctr",align:"right" as const,width:90,render:percent},
  {title:"CVR",dataIndex:"cvr",align:"right" as const,width:90,render:percent},
  {title:"来源映射",dataIndex:"listing_mapping_status",width:120,render:(v:string)=><Tag color={v==="unique"?"success":"warning"}>{v==="unique"?"Listing 已确认":"Listing 待确认"}</Tag>},
  {title:"操作",key:"action",fixed:"right" as const,width:130,render:(_:unknown,r:SearchTermRow)=><Button type="link" icon={<EyeOutlined/>} onClick={()=>setSelected(r)}>详情</Button>},
 ];
 return <PageShell page={page}>
  <div className="search-terms-page">
   <div className="search-terms-toolbar">
    <Space wrap>
     <Segmented value={type} onChange={v=>{setType(v as typeof type);setPageNo(1);}} options={[{label:"全部 SP",value:"all"},{label:"自动广告",value:"auto"},{label:"手动广告",value:"manual"}]}/>
     <Segmented value={view} onChange={v=>setView(v as typeof view)} options={[{label:"活动明细",value:"detail"},{label:"搜索词汇总",value:"summary"}]}/>
    </Space>
    <Space wrap>
     <RangePicker value={range} allowClear={false} onChange={v=>{if(v?.[0]&&v[1]){setRange([v[0],v[1]]);setPageNo(1);}}}/>
     <Button icon={<ReloadOutlined/>} onClick={()=>void refresh()} loading={loading}>刷新</Button>
    </Space>
   </div>
   <div className="search-terms-filters">
    <Select value={conversion} onChange={v=>{setConversion(v);setPageNo(1);}} options={[{label:"全部状态",value:"all"},{label:"已出单",value:"orders"},{label:"未出单",value:"no_orders"}]} style={{width:130}}/>
    <Input value={search} onChange={e=>setSearch(e.target.value)} onPressEnter={()=>{setCommittedSearch(search.trim());setPageNo(1);}} allowClear placeholder="搜索买家实际搜索词" prefix={<SearchOutlined/>} style={{width:260}}/>
    <Button onClick={()=>{setCommittedSearch(search.trim());setPageNo(1);}}>查询</Button>
    <Typography.Text type="secondary">不按负责人过滤；数据范围仍受账号权限控制</Typography.Text>
   </div>
   {syncError?<Alert type="warning" showIcon message="搜索词数据暂不可用" description={syncError} />:null}
   <Row gutter={[12,12]} className="search-terms-stats">
    <Col xs={12} md={8} xl={4}><Card><Statistic title="搜索词数量" value={summary?.total_terms??"—"}/></Card></Col>
    <Col xs={12} md={8} xl={4}><Card><Statistic title="有出单搜索词" value={summary?.converting_terms??"—"}/></Card></Col>
    <Col xs={12} md={8} xl={4}><Card><Statistic title="自动出单待覆盖" value={summary?.auto_converting_not_manually_covered??"—"}/></Card></Col>
    <Col xs={12} md={8} xl={4}><Card><Statistic title="花费无订单" value={summary?.no_order_terms_with_spend??"—"}/></Card></Col>
    <Col xs={12} md={8} xl={4}><Card><Statistic title="广告花费" prefix="$" value={summary?Number(summary.ad_spend_total):"—"} precision={2}/></Card></Col>
    <Col xs={12} md={8} xl={4}><Card><Statistic title="广告订单" value={summary?Number(summary.attributed_orders_total):"—"}/></Card></Col>
   </Row>
   <Alert type="info" showIcon message="来源仅展示领星实际返回的店铺、广告账户、活动及自动/手动类型。Listing 仅在唯一关联得到事实数据证明时显示。" />
   <Card className="search-terms-table-card" title={view==="detail"?"搜索词活动明细":"搜索词汇总"} extra={<Typography.Text type="secondary">共 {total} 条 · 无导出功能</Typography.Text>}>
    <Table rowKey="id" columns={columns} dataSource={rows} loading={loading} size="middle" scroll={{x:1600,y:"calc(100vh - 440px)"}} pagination={{current:pageNo,pageSize:50,total,showSizeChanger:false,onChange:setPageNo}} locale={{emptyText:<Empty description={syncError?"数据读取失败":"当前日期范围暂无已同步数据"}/>}}/>
   </Card>
   <Card title="处理任务" size="small">
    {actions.length===0?<Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无搜索词处理任务"/>:
     <Table rowKey="id" size="small" pagination={{pageSize:5}} dataSource={actions} columns={[
      {title:"搜索词",dataIndex:"search_term"},
      {title:"处理类型",dataIndex:"action_type",render:(v:string)=>v==="add_keyword"?"建议加入手动广告":"建议加入否定词"},
      {title:"状态",dataIndex:"status",render:(v:string)=><Tag color={v==="pending_manual"?"processing":"success"}>{v==="pending_manual"?"待人工执行":"已人工完成"}</Tag>},
      {title:"创建人",dataIndex:"created_by"},
      {title:"操作",render:(_:unknown,r:SearchTermAction)=>r.status==="pending_manual"?<Button size="small" disabled={actionBusy} onClick={()=>void finishAction(r)}>记录人工完成</Button>:"—"},
     ]}/>}
   </Card>
   <Drawer title="搜索词详情" width={560} open={!!selected} onClose={()=>setSelected(null)} extra={selected?<Space><Button icon={<PlusOutlined/>} loading={actionBusy} onClick={()=>void handleAction(selected,"add_keyword")}>加入词处理</Button><Button danger icon={<StopOutlined/>} loading={actionBusy} onClick={()=>void handleAction(selected,"add_negative_keyword")}>否词处理</Button></Space>:null}>
    {selected?<Descriptions bordered column={1} size="small">
     <Descriptions.Item label="买家搜索词">{selected.searched_keyword}</Descriptions.Item>
     <Descriptions.Item label="广告类型">{selected.targeting_type==="auto"?"自动广告":"手动广告"}</Descriptions.Item>
     <Descriptions.Item label="店铺">{selected.mp_seller_name||"—"}</Descriptions.Item>
     <Descriptions.Item label="广告账户">{selected.mp_advertiser_name||selected.advertiser_id}</Descriptions.Item>
     <Descriptions.Item label="广告活动">{selected.campaign_name||selected.campaign_id}</Descriptions.Item>
     <Descriptions.Item label="Listing">{selected.listing_mapping_status==="unique"?selected.item_id:"无法唯一确认，不推断"}</Descriptions.Item>
     <Descriptions.Item label="曝光 / 点击">{number(selected.num_ads_shown)} / {number(selected.num_ads_clicks)}</Descriptions.Item>
     <Descriptions.Item label="广告花费">{money(selected.ad_spend_amount)}</Descriptions.Item>
     <Descriptions.Item label="广告订单">{selected.attributed_orders??"—"}</Descriptions.Item>
     <Descriptions.Item label="直接销售额">{money(selected.advertised_sku_sales_amount)}</Descriptions.Item>
     <Descriptions.Item label="关联销售额">{money(selected.other_sku_sales_amount)}</Descriptions.Item>
     <Descriptions.Item label="归因窗口">{selected.attribution_days} 天</Descriptions.Item>
    </Descriptions>:null}
   </Drawer>
  </div>
 </PageShell>;
}
