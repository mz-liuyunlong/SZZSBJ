import { useEffect, useRef, useState, type CSSProperties, type Key } from "react";
import dayjs from "dayjs";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Alert, Button, Form, Input, InputNumber, Modal, Pagination, Popover, Segmented, Tooltip, message, theme } from "antd";
import { ProTable, type ProColumns } from "@ant-design/pro-components";
import { EditOutlined, ShoppingCartOutlined } from "@ant-design/icons";
import ReportTableShell from "@/components/report-table/ReportTableShell";
import { CopyableTextCell, ImageCell, MoneyCell, WalmartProductIdCell } from "@/components/report-table/cells";
import ManagementStatCards, { type ManagementStatCardItem } from "@/components/report-table/ManagementStatCards";
import ResizableColumnTitle from "@/components/report-table/ResizableColumnTitle";
import ReportFacetSelect from "@/shared/report-filters";
import ReportDateRangePicker from "@/shared/date/ReportDateRangePicker";
import CommittedSearch from "@/components/report-table/CommittedSearch";
import ResetButton from "@/components/report-table/ResetButton";
import { emptyListing, loadSkuProgress, loadProgressSummary, loadProgressFacets, submitSkuPurchase, submitSkuPurchaseBatch, saveSkuProgress, batchPurchaseKey, type BatchPurchaseResult, type BatchPurchaseTarget, type ProgressCode, type ListingProgress, type SkuProgressRow, type Facet, type Filters, type Card, type Sort, type Criteria } from "./skuProgressApi";
import "./skuProgress.css";

type Flat={key:string;r:SkuProgressRow;l:ListingProgress;span:number};
const moreKeys:Facet[]=["strike","plan","site","ad","proc","ship","progress"];
function mergeMoreFilters(committed:Filters,draft:Filters):Filters {
  const result={...committed};
  for(const key of moreKeys){
    if(draft[key]?.length) result[key]=[...draft[key]!];
    else delete result[key];
  }
  return result;
}
function moreDraftFrom(filters:Filters):Filters {
  return Object.fromEntries(moreKeys.map(k=>[k,[...(filters[k]??[])]]));
}
const emptyRows:SkuProgressRow[]=[];
type SkuProgressDialog={kind:"purchase";row:SkuProgressRow;listing:ListingProgress}|{kind:"remark";row:SkuProgressRow};
const remarkReasons=["采购起批量过高","专利 / 侵权风险","平台上架限制","采购成本过高","供应商问题","产品质量问题","市场竞争过大","暂无合适店铺","其他原因"];
// Form state is local to the dialog, so typing does not rerender the whole table.
// Only a confirmed provider receipt is treated as purchase success.
function SkuProgressEditDialog({dialog,onClose,onPurchaseSettled}:{dialog:SkuProgressDialog;onClose:()=>void;onPurchaseSettled:()=>Promise<void>}){
  const purchase=dialog.kind==="purchase";
  const row=dialog.row;
  const targetKey=dialog.kind==="purchase"?dialog.listing.key:undefined;
  const chosen=targetKey?row.ls.find(l=>l.key===targetKey&&l.candidate):undefined;
  const submittingRef=useRef(false);
  const [submitting,setSubmitting]=useState(false);
  const [attempted,setAttempted]=useState(false);
  const submit=async()=>{
    if(!chosen||submittingRef.current||attempted)return;
    submittingRef.current=true;setSubmitting(true);setAttempted(true);
    try{
      const result=await submitSkuPurchase(row,chosen);
      void message.success(`采购计划已提交：${result.lingxing_plan_sn}`);
      onClose();
    }catch(e){void message.error(e instanceof Error?e.message:"采购结果未确认，请核实领星，禁止重复提交");}
    finally{submittingRef.current=false;setSubmitting(false);await onPurchaseSettled();}
  };
  const qty=20;
  const labels:Record<ProgressCode,string>={in_progress:row.progressCode==="paused"?"恢复推进":"正常推进",paused:"暂停推进",terminated:"终止推进",completed:"已完成"};
  const [mode,setMode]=useState<ProgressCode>(row.progressCode);
  const [reason,setReason]=useState<string|undefined>(row.reasonType||undefined);
  const [note,setNote]=useState(row.remark);
  const requiresReason=mode==="paused"||mode==="terminated";
  const canSave=row.canEditProgress&&!!note.trim()&&(!requiresReason||!!reason)&&!submitting;
  const save=async()=>{
    if(!canSave||submittingRef.current)return;
    submittingRef.current=true;setSubmitting(true);
    try{await saveSkuProgress(row,mode,reason,note);void message.success("推进状态及备注已保存");onClose();}
    catch(e){void message.error(e instanceof Error?e.message:"保存失败，请刷新核对");}
    finally{submittingRef.current=false;setSubmitting(false);await onPurchaseSettled();}
  };
  const [noteTouched,setNoteTouched]=useState(false);
  const footer=<div style={{display:"flex",justifyContent:"flex-end",gap:8}}>
    <Button onClick={onClose} disabled={submitting}>取消</Button>
    <Tooltip title={purchase?(attempted?"已发送请求，请核对刷新后的采购状态":!chosen?"当前 Listing 不符合采购条件":undefined):!row.canEditProgress?"当前环境或账号不可保存":!canSave?"请填写必填项":undefined}><span><Button type="primary" disabled={purchase?(!chosen||attempted):!canSave} loading={submitting} onClick={()=>void (purchase?submit():save())}>{purchase?"提交采购计划":"保存"}</Button></span></Tooltip>
  </div>;
  return <Modal open title={purchase?"提交采购计划":"修改推进状态 / 备注"} width={460} onCancel={()=>{if(!submitting)onClose();}} footer={footer} maskClosable={false}>
    <div style={{display:"flex",alignItems:"baseline",gap:8,marginBottom:16,overflow:"hidden"}}>
      <strong style={{flexShrink:0}}>{row.sku||"—"}</strong><span title={row.name} style={{overflow:"hidden",textOverflow:"ellipsis",whiteSpace:"nowrap"}}>{row.name}</span>
    </div>
    <Form layout="vertical" component="div" requiredMark>
      {purchase?<div style={{display:"grid",gridTemplateColumns:"minmax(0,1fr) minmax(0,1fr)",gap:12}}>
        <Form.Item label="采购店铺" style={{minWidth:0,marginBottom:12}}><Input aria-label="采购店铺" disabled value={chosen?.store||"—"}/></Form.Item>
        <Form.Item label="Item ID" style={{minWidth:0,marginBottom:12}}><Input aria-label="Item ID" disabled value={chosen?.id||"—"}/></Form.Item>
        <Form.Item label="MSKU" style={{minWidth:0,marginBottom:12}}><Input aria-label="MSKU" disabled value={chosen?.msku||"—"}/></Form.Item>
        <Form.Item label="采购数量" required style={{minWidth:0,marginBottom:12}}>
          <InputNumber aria-label="采购数量" disabled controls={false} value={qty} addonAfter="件" style={{width:"100%"}}/>
        </Form.Item>
      </div>:<>
        <Form.Item label="推进状态" style={{marginBottom:12}}><Segmented block value={mode} disabled={submitting||!row.canEditProgress} options={(Object.keys(labels) as ProgressCode[]).map(value=>({value,label:labels[value],disabled:["completed","terminated"].includes(row.progressCode)&&value!==row.progressCode}))} onChange={v=>{setMode(v as ProgressCode);setReason(undefined);}}/></Form.Item>
        {requiresReason&&<Form.Item label="原因类型" required style={{marginBottom:12}}>
          <div style={{display:"block",minWidth:0}}><ReportFacetSelect ariaLabel="原因类型" placeholder="请选择原因类型" triggerWidth="100%" options={[...new Set([...remarkReasons,...(reason?[reason]:[])])].map(value=>({value,label:value}))} value={reason} onChange={v=>{if(!submitting&&row.canEditProgress)setReason(typeof v==="string"?v:undefined);}}/></div>
        </Form.Item>}
        <Form.Item label="备注说明" required style={{marginBottom:16}} validateStatus={noteTouched&&!note.trim()?"error":undefined} help={noteTouched&&!note.trim()?"请填写备注说明":undefined}>
          <Input.TextArea aria-label="备注说明" disabled={submitting||!row.canEditProgress} rows={3} maxLength={500} showCount placeholder="请输入具体说明" value={note} onChange={e=>setNote(e.target.value)} onBlur={()=>setNoteTouched(true)}/>
        </Form.Item>
      </>}
    </Form>
    <Alert type="info" showIcon message={purchase?"采购数量固定20件，提交后请勿重复操作。":"备注必填，暂停或终止推进时必须选择原因。"}/>
  </Modal>;
}
function BatchPurchaseDialog({rows,onClose,onSettled}:{rows:BatchPurchaseTarget[];onClose:()=>void;onSettled:()=>Promise<void>}){
  const [results,setResults]=useState<BatchPurchaseResult[]>([]);
  const [busy,setBusy]=useState(false);
  const attempted=useRef(false);
  const [hasAttempted,setHasAttempted]=useState(false);
  const mounted=useRef(true);
  useEffect(()=>{mounted.current=true;return ()=>{mounted.current=false;};},[]);
  const valid=rows.length>0&&rows.length<=100&&rows.every(({row,listing})=>row.ls.some(l=>l.key===listing.key&&l.candidate));
  const submit=async()=>{
    if(attempted.current||!valid)return;
    attempted.current=true;setHasAttempted(true);setBusy(true);
    try{await submitSkuPurchaseBatch(rows,r=>{if(mounted.current)setResults(old=>[...old,r]);},()=>mounted.current);}
    catch(e){void message.error(e instanceof Error?e.message:"批量采购异常");}
    finally{setBusy(false);await onSettled();}
  };
  return <Modal open title="批量提交采购计划" width={460} maskClosable={false} closable={!busy} onCancel={()=>{if(!busy)onClose();}} footer={<><Button disabled={busy} onClick={onClose}>{hasAttempted?"关闭":"取消"}</Button><Button type="primary" loading={busy} disabled={hasAttempted||!valid} onClick={()=>void submit()}>提交采购计划</Button></>}>
    <Alert type="info" showIcon message={`共 ${rows.length} 个 Listing，每个固定20件，合计 ${rows.length*20} 件；逐个提交，不自动重试。`}/>
    {!valid&&<Alert type="warning" showIcon message="请选择1至100个符合采购条件的 Listing"/>}
    <div style={{maxHeight:380,overflowY:"auto"}}><Form layout="vertical" component="div">{rows.map(target=>{const {row,listing}=target,key=batchPurchaseKey(target),result=results.find(r=>r.key===key);return <Form.Item key={key} label={`${row.sku} / ${row.name}`}>
      <div>{listing.store} · {listing.id} · {listing.msku||"—"}</div>
      {result&&<Alert type={result.ok?"success":"warning"} message={result.ok?`已提交：${result.detail}`:`未确认或失败：${result.detail}`}/>}
    </Form.Item>;})}</Form></div>
  </Modal>;
}
// Keep non-USD/CNY source currencies unchanged rather than falsely relabeling.
function renderMoney(text:string) {
  const match=/^([$¥])(\d+(?:\.\d+)?)$/.exec(text);
  if (!match) return <span className="report-table-metric">{text || "—"}</span>;
  return <MoneyCell value={Number(match[2])} currency={match[1]==="¥"?"¥":"$"}/>;
}
const columnMin:Record<string,number>={product:200,progress:100,date:108,dev:90,listing:105,identity:150,store:168,plan:110,proc:100,ship:90,site:86,strike:100,price:90,note:160};
export default function NewProductSkuProgressPage(){
  const {token}=theme.useToken();
  const queryClient=useQueryClient();
  const [dialog,setDialog]=useState<SkuProgressDialog|null>(null);
  const [selectedKeys,setSelectedKeys]=useState<Key[]>([]);
  const [batchRows,setBatchRows]=useState<BatchPurchaseTarget[]|null>(null);
  const [filters,setFilters]=useState<Filters>({});
  const [keyword,setKeyword]=useState("");
  const [searchField,setSearchField]=useState("all");
  const [searchRev,setSearchRev]=useState(0);
  const [moreOpen,setMoreOpen]=useState(false);
  const [moreDraft,setMoreDraft]=useState<Filters>({});
  const moreCount=moreKeys.filter(k=>filters[k]?.length).length;
  const moreDraftCount=moreKeys.filter(k=>moreDraft[k]?.length).length;
  const changeMoreOpen=(next:boolean)=>{
    if(next) setMoreDraft(moreDraftFrom(filters));
    setMoreOpen(next);
  };
  const applyMoreSearch=()=>{
    setFilters(previous=>mergeMoreFilters(previous,moreDraft));
    setPage(1);
    setMoreOpen(false);
  };
  const [page,setPage]=useState(1);
  const [pageSize,setPageSize]=useState(20);
  const [card,setCard]=useState<Card>("all");
  const [dateRange,setDateRange]=useState<[string,string]|null>(null);
  const [sort,setSort]=useState<Sort>({key:"date",order:"desc"});
  const [widths,setWidths]=useState<Record<string,number>>({});
  const reset=()=>{setFilters({});setMoreDraft({});setMoreOpen(false);setKeyword("");setSearchField("all");setSearchRev(x=>x+1);setPage(1);setCard("all");setDateRange(null);setSort({key:"date",order:"desc"});};
  const setFilter=(k:Facet,v:string[])=>{setFilters(old=>({...old,[k]:v}));setPage(1);};
  const criteria:Criteria={filters,keyword,searchField,card,dateRange};
  const draftCriteria:Criteria={...criteria,filters:mergeMoreFilters(filters,moreDraft)};
  const query=useQuery({queryKey:["np-sku-progress","list",criteria,page,pageSize,sort],queryFn:({signal})=>loadSkuProgress(criteria,page,pageSize,sort,signal),staleTime:15000,retry:false,refetchInterval:60000,refetchOnWindowFocus:false});
  const summaryQuery=useQuery({queryKey:["np-sku-progress","summary",{...criteria,card:"all"}],queryFn:({signal})=>loadProgressSummary(criteria,signal),staleTime:15000,retry:false,refetchInterval:60000,refetchOnWindowFocus:false});
  const facetQuery=useQuery({queryKey:["np-sku-progress","facets",criteria],queryFn:({signal})=>loadProgressFacets(criteria,signal),staleTime:15000,retry:false,refetchInterval:60000,refetchOnWindowFocus:false});
  const draftQuery=useQuery({queryKey:["np-sku-progress","facets",draftCriteria],queryFn:({signal})=>loadProgressFacets(draftCriteria,signal),enabled:moreOpen,staleTime:15000,retry:false,refetchOnWindowFocus:false});
  const rows=query.data?.rows??emptyRows;
  const total=query.data?.total??0;
  const lastPage=Math.max(1,Math.ceil(total/pageSize));
  useEffect(()=>{if(query.data&&page>lastPage)setPage(lastPage);},[query.data,page,lastPage]);
  const facetOptions=facetQuery.data?.facets;
  const moreOptions=draftQuery.data?.facets;
  const stats=summaryQuery.isError?undefined:summaryQuery.data;
  const dates=facetQuery.data?.date_range;
  const flat:Flat[]=rows.flatMap(r=>{const ls=r.ls.length?r.ls:[emptyListing(r)];return ls.map((l,i)=>({key:JSON.stringify([r.key,l.key]),r,l,span:i===0?ls.length:0}));});
  const selectionScope=JSON.stringify([criteria,page,pageSize,sort]);
  const [previousSelectionScope,setPreviousSelectionScope]=useState(selectionScope);
  if(previousSelectionScope!==selectionScope){
    setPreviousSelectionScope(selectionScope);
    setSelectedKeys([]);
  }
  const selectedRows=flat.filter(f=>selectedKeys.includes(f.key)&&f.l.candidate).map(f=>({row:f.r,listing:f.l}));
  const refreshAfterPurchase=async()=>{setSelectedKeys([]);await queryClient.invalidateQueries({queryKey:["np-sku-progress"]});};
  const color=(s:string)=>["已上架","已生效","已提交"].includes(s)?token.colorSuccess:["未上架","未生效","未提交"].includes(s)?token.colorError:token.colorTextSecondary;
  const status=(s:string)=><span style={{color:color(s),fontWeight:s?500:400,whiteSpace:"nowrap"}}>{s||"—"}</span>;
  const sub=(s:string)=>s?<div className="sku-p-sub" title={s}>{s}</div>:null;
  const blank=()=>status("");
  const shared=(row:Flat)=>({rowSpan:row.span});
  const baseColumns:ProColumns<Flat>[]=[
    {title:"产品信息",key:"product",width:250,fixed:"left",onCell:shared,render:(_,x)=><div className="sku-p-product"><ImageCell image={x.r.image||undefined} previewSrc={x.r.previewImage||undefined} alt={x.r.name||"商品图片"} thumbnailSize={48}/><div className="sku-p-producttext">{x.r.sku?<CopyableTextCell text={x.r.sku} label="SKU" className="sku-p-sku"/>:blank()}{x.r.name&&<CopyableTextCell text={x.r.name} label="品名" className="sku-p-product-name"/>}{x.r.ls.length>1&&sub(`${x.r.ls.length} 个 Listing`)}</div></div>},
    {title:"开发人员",key:"dev",width:100,onCell:shared,render:(_,x)=><div className="sku-p-ellipsis" title={x.r.dev}>{x.r.dev||"—"}</div>},
    {title:"开品时间",key:"date",width:120,onCell:shared,render:(_,x)=>x.r.developmentDate||"—"},
    {title:"Item ID / MSKU",key:"identity",width:186,render:(_,x)=><div className="sku-p-identity">{x.l.id?<WalmartProductIdCell productId={x.l.id} containerStyle={{width:"100%",maxWidth:"100%"}}/>:blank()}{x.l.msku&&<CopyableTextCell text={x.l.msku} label="MSKU" className="sku-p-msku"/>}</div>},
    {title:"店铺 / 负责人",key:"store",width:220,render:(_,x)=><><div className="sku-p-ellipsis sku-p-store" title={x.l.store}>{x.l.store||"—"}</div>{sub(x.l.id?x.l.owner:x.r.owner)}</>},
    {title:"上架状态",key:"listing",width:115,render:(_,x)=>status(x.l.listing)},
    {title:"采购计划",key:"plan",width:120,render:(_,x)=><span style={{display:"inline-flex",alignItems:"center",gap:6,whiteSpace:"nowrap"}}>{status(x.l.purchasePlan)}{x.l.purchasePlan==="未提交"&&<Button type="link" size="small" aria-label={`提交采购计划 ${x.l.id||x.r.sku}`} title={x.l.candidate?"提交采购计划":"未上架、未满足采购校验或已有采购记录"} icon={<ShoppingCartOutlined aria-hidden="true" style={{fontSize:18}}/>} style={{display:"inline-flex",alignItems:"center",justifyContent:"center",width:24,minWidth:24,height:24,minHeight:24,padding:0}} disabled={!x.l.candidate} onClick={()=>setDialog({kind:"purchase",row:x.r,listing:x.l})}/>}</span>},
    {title:"采购进度",key:"proc",width:105,render:(_,x)=>status(x.l.purchaseProgress)},
    {title:"国内发货",key:"ship",width:96,render:(_,x)=>status(x.l.shipping)},
    {title:"独立站",key:"site",width:90,render:(_,x)=>status(x.l.site)},
    {title:"划线价",key:"strike",width:112,render:(_,x)=><div className="sku-p-money">{renderMoney(x.l.strike)}{x.l.effect&&<div>{status(x.l.effect)}</div>}</div>},
    {title:"售价",key:"price",width:100,render:(_,x)=><div className="sku-p-money">{renderMoney(x.l.price)}</div>},
    {title:"备注",key:"note",width:230,onCell:shared,render:(_,x)=> <div className="sku-p-note"><div className="sku-p-notetext" title={x.r.remark}>{x.r.remark||"—"}</div><Button type="text" size="small" aria-label={`编辑备注 ${x.r.sku}`} icon={<EditOutlined/>} onClick={()=>setDialog({kind:"remark",row:x.r})}/></div>},
    {title:"推进状态",key:"progress",width:108,onCell:shared,render:(_,x)=>status(x.r.progress)},
  ];
  const columns:ProColumns<Flat>[]=baseColumns.map(c=>{
    const key=String(c.key), width=widths[key]??Number(c.width), label=String(c.title);
    return {...c,width,...(["product","dev","date","listing","progress"].includes(key)?{sorter:true,sortOrder:sort.key===key?(sort.order==="asc"?"ascend" as const:"descend" as const):null}:{}),title:<ResizableColumnTitle label={label} minWidth={columnMin[key]??90} width={width} onWidthChange={next=>setWidths(old=>({...old,[key]:next}))}/>};
  });
  const scrollWidth=44+columns.reduce((sum,c)=>sum+Number(c.width),0);
  const select=(k:Facet,label:string)=><ReportFacetSelect mode="multiple" ariaLabel={label} placeholder={label} unit={k==="developer"||k==="owner"?"人":k==="store"?"家":"项"} triggerWidth={k==="owner"?148:k==="store"?168:132} popupWidth={k==="store"?400:360} value={filters[k]??[]} onChange={v=>setFilter(k,Array.isArray(v)?v:[])} options={facetOptions?.[k]??[]} optionsReady={!!facetOptions&&!facetQuery.isError} loading={facetQuery.isFetching}/>;
  const ready=!!query.data&&!query.isError;
  const renderMoreFacet=(key:Facet,label:string)=>{
    const facetReady=!!moreOptions&&!draftQuery.isError;
    const options=moreOptions?.[key]??[];
    return <div className="sku-p-more-item"><span className="sku-p-more-title">{label}</span>
      <div className="sku-p-more-control"><ReportFacetSelect mode="multiple" immediateMultiple ariaLabel={label} placeholder={`全部${label}`} triggerWidth="100%" popupWidth={248} showSearch={false} value={moreDraft[key]??[]} options={options} optionsReady={facetReady} loading={draftQuery.isFetching} onChange={v=>setMoreDraft(old=>({...old,[key]:Array.isArray(v)?v:[]}))}/></div>
    </div>;
  };
  return <div className="sku-p" style={{color:token.colorText,background:token.colorBgContainer,"--sku-border":token.colorBorderSecondary,"--sku-muted":token.colorTextSecondary,"--sku-primary":token.colorPrimary,"--sku-hover":token.colorPrimaryBg} as CSSProperties}>
    {query.isError&&<Alert type="error" showIcon message="真实 SKU 数据读取失败" description={query.error instanceof Error?query.error.message:"请检查登录及数据权限"}/>}
    {(summaryQuery.isError||facetQuery.isError||draftQuery.isError&&moreOpen)&&<Alert type="warning" showIcon message="统计或筛选选项读取失败，请刷新重试"/>}
    <ManagementStatCards ariaLabel="SKU推进统计" className="sku-p-stats" activeKey={card}
      cards={[
        {key:"all",title:"全部SKU",subtitle:"当前筛选范围",value:stats?.total??"—",tone:"normal",icon:<span>▦</span>},
        {key:"active",title:"推进中",subtitle:"当前筛选范围",value:stats?.in_progress??"—",tone:"normal",icon:<span>◷</span>},
        {key:"done",title:"已完成",subtitle:"当前筛选范围",value:stats?.completed??"—",tone:"success",icon:<span>✓</span>},
        {key:"paused",title:"暂停推进",subtitle:"当前筛选范围",value:stats?.paused??"—",tone:"warning",icon:<span>Ⅱ</span>},
        {key:"terminated",title:"终止推进",subtitle:"当前筛选范围",value:stats?.terminated??"—",tone:"normal",icon:<span>⊘</span>},
      ] satisfies ManagementStatCardItem[]}
      onCardClick={key=>{setCard(key as Card);setPage(1);}}/>
    <div className="sku-p-filters">
      {select("listing","上架状态")}{select("store","店铺")}{select("owner","负责人")}{select("developer","开发人员")}
      <Tooltip title={dates?.min&&dates?.max?`可选日期：${dates.min} ~ ${dates.max}`:"暂无已确认开发日期"}><span><ReportDateRangePicker aria-label="开品时间范围" disabled={facetQuery.isError||!dates?.min&&!dateRange} placeholder={["开品开始日期","开品结束日期"]} value={dateRange?[dayjs(dateRange[0]),dayjs(dateRange[1])]:null} minDate={dates?.min?dayjs(dates.min):undefined} maxDate={dates?.max?dayjs(dates.max):undefined} onChange={(_,values)=>{setDateRange(values[0]&&values[1]?[values[0],values[1]]:null);setPage(1);}} style={{width:290,flex:"0 0 auto"}}/></span></Tooltip>
      <CommittedSearch key={searchRev} typeAriaLabel="搜索类型" typeOptions={[{label:"全部",value:"all"},{label:"SKU",value:"sku"},{label:"品名",value:"name"},{label:"ID / MSKU",value:"item"}]} typeValue={searchField} inputAriaLabel="搜索 SKU、品名、Item ID、MSKU" inputPlaceholder="搜索 SKU、品名、Item ID、MSKU" inputValue={keyword} onCommit={({searchField,keyword})=>{setSearchField(searchField);setKeyword(keyword);setPage(1);}}/>
      <Popover trigger="click" placement="bottomRight" open={moreOpen}
        onOpenChange={next=>{if(!next)changeMoreOpen(false);}} destroyOnHidden
        content={<section className="sku-p-more-filters" aria-label="更多筛选">
          <div className="sku-p-more-grid">
            {renderMoreFacet("plan","采购计划")}
            {renderMoreFacet("site","独立站")}
            {renderMoreFacet("ad","广告状态")}
            {renderMoreFacet("strike","划线价")}
            {renderMoreFacet("proc","采购进度")}
            {renderMoreFacet("ship","国内发货")}
            {renderMoreFacet("progress","推进状态")}
          </div>
          <div className="sku-p-more-actions">
            <Button size="small" disabled={!moreDraftCount} onClick={()=>setMoreDraft({})}>清空更多筛选</Button>
            <Button size="small" onClick={()=>changeMoreOpen(false)}>关闭</Button>
            <Button size="small" type="primary" onClick={applyMoreSearch}>搜索</Button>
          </div>
        </section>}>
        <Button aria-expanded={moreOpen} onClick={()=>changeMoreOpen(!moreOpen)}>更多筛选{moreCount>0?` (${moreCount})`:""}</Button>
      </Popover>
      <ResetButton onClick={reset}/>
    </div>
    <ReportTableShell label="新品管理表格" className="sku-p-table">
      <ProTable<Flat> className="sku-p-protable" rowKey="key" size="middle" bordered tableLayout="fixed"
        columns={columns} dataSource={query.isError?[]:flat} loading={query.isPending} onChange={(_,__,sorter)=>{const next=Array.isArray(sorter)?sorter[0]:sorter;const key=String(next?.columnKey??"");if(["product","dev","date","listing","progress"].includes(key)&&next?.order)setSort({key:key as Sort["key"],order:next.order==="ascend"?"asc":"desc"});else setSort({key:"date",order:"desc"});setPage(1);}}
        search={false} options={false} toolBarRender={false} pagination={false}
        rowSelection={{selectedRowKeys:selectedKeys,onChange:keys=>setSelectedKeys(keys),getCheckboxProps:r=>({disabled:!r.l.candidate}),columnWidth:44,fixed:true}}
        scroll={{x:scrollWidth,y:"100%"}} locale={{emptyText:query.isError?"读取失败，请重新进入新品管理":"暂无符合条件的真实 SKU"}}/>
      <div className="sku-p-footer"><span><Button size="small" disabled={!ready||!selectedRows.length||selectedRows.length>100} onClick={()=>setBatchRows(selectedRows)}>批量采购{selectedRows.length?` (${selectedRows.length})`:""}</Button> {ready?`共 ${total} 个 SKU · ${query.data?.listing_count??0} 个匹配 Listing`:"—"}</span><Pagination current={page} pageSize={pageSize} total={ready?total:0} showSizeChanger pageSizeOptions={[10,20,50,100]} onChange={(p,s)=>{setPageSize(s);setPage(s!==pageSize?1:p);}}/></div>
    </ReportTableShell>
    {batchRows&&<BatchPurchaseDialog rows={batchRows} onClose={()=>setBatchRows(null)} onSettled={refreshAfterPurchase}/>}
    {dialog&&<SkuProgressEditDialog key={JSON.stringify([dialog.kind,dialog.row.key,dialog.kind==="purchase"?dialog.listing.key:null])} dialog={dialog} onClose={()=>setDialog(null)} onPurchaseSettled={refreshAfterPurchase}/>}
  </div>;
}
