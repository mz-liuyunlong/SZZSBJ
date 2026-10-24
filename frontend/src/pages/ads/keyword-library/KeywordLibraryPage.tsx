import {useEffect,useState} from 'react';
import {useLocation,useNavigate} from 'react-router-dom';
import {Alert,Button,Card,Descriptions,Drawer,Empty,Form,Input,InputNumber,Modal,Select,Space,Tabs,Tag,Typography,Upload,message} from 'antd';
import {PlusOutlined,TranslationOutlined,UploadOutlined} from '@ant-design/icons';
import {ProTable,type ProColumns} from '@ant-design/pro-components';
import PageShell from '@/components/page/PageShell';
import ReportTableShell from '@/components/report-table/ReportTableShell';
import ConnectedSearch from '@/components/report-table/ConnectedSearch';
import ResetButton from '@/components/report-table/ResetButton';
import {MoneyCell,PercentCell} from '@/components/report-table/cells';
import type {NavigationPage} from '@/config/navigation';
import {KeywordTextCell} from '@/features/keyword-planning/components/KeywordTextCell';
import {countText,normalizeTerm} from '@/features/keyword-planning/model';
import {parseSellerSprite} from '@/features/keyword-planning/importWorkbook';
import {useKeywordStore} from '@/features/keyword-planning/store';
import type {AdRecord,MarketKeyword,MatchType,SkuKeyword} from '@/features/keyword-planning/types';
import {addManualKeywordWords,downloadKeywordInternalWorkbook,getKeywordSourceState,listGlobalKeywordLibrary,listKeywordLibrary,listKeywordRuns,loadAllRunKeywords,updateKeywordTranslation,uploadKeywordSourceXlsx} from '@/api/keywordPlanningV11Api';
import {canonicalSku,preloadProductSkuOptions,searchListingsForSku,searchProductsBySku} from '@/features/keyword-planning/keywordProductLookup';
import '../../ai-center/keyword-launch/KeywordLaunchPage.css';
import './KeywordLibraryPage.css';
const {Text}=Typography;
type Mode='sku'|'global';
type Tab='all'|'todo'|'execution'|'performance'|'history';
type LibraryRow={key:string;keyword:MarketKeyword;associated:SkuKeyword[];current:SkuKeyword|null;mockAds:AdRecord[]};
interface FormData {skuId:string;term:string;store:string;match:MatchType;bid:number;campaign:string}
const performance=(ads:AdRecord[])=>{
  const included=ads.filter(x=>x.clicks!==null&&x.spend!==null&&x.orders!==null);
  if(!included.length)return null;
  const sum=(field:'clicks'|'spend'|'orders'|'sales'|'impressions')=>included.reduce((n,a)=>n+(a[field]||0),0);
  const clicks=sum('clicks'),spend=sum('spend'),orders=sum('orders'),sales=sum('sales');
  return {clicks,spend,orders,sales,cpc:clicks>0?spend/clicks:null,cvr:clicks>0?orders/clicks*100:null,acos:sales>0?spend/sales*100:null,roas:spend>0?sales/spend:null};
};
function editTranslation(k:MarketKeyword,change:(id:string,value:string)=>Promise<void>){let value=k.translation||'';Modal.confirm({title:`修改中文翻译 · ${k.term}`,content:<Input.TextArea rows={3} defaultValue={value} onChange={e=>{value=e.target.value}}/>,okText:'保存翻译',onOk:()=>change(k.id,value)})}
export default function KeywordLibraryPage({page}:{page:NavigationPage}){
 const navigate=useNavigate(),location=useLocation();const startSku=(location.state as {skuId?:string}|null)?.skuId;
 const {skus,entries,ads,analyses,updateTranslation,addManual,assignManual,upsertProductSku,installServerRun,installServerLibrary}=useKeywordStore();
 const [skuId,setSkuId]=useState(()=>{
   if(startSku)return startSku;
   try{return (JSON.parse(sessionStorage.getItem('keyword-planning:selected-product')||'{}') as {id?:string}).id||skus[0]?.id||''}
   catch{return skus[0]?.id||''}
 });
 const [mode,setMode]=useState<Mode>('sku'),[tab,setTab]=useState<Tab>('all');
 const [searchType,setSearchType]=useState('keyword'),[searchInput,setSearchInput]=useState(''),[query,setQuery]=useState('');
 const [grade,setGrade]=useState('all');const [sourceFilter,setSourceFilter]=useState('all');const [addWordOpen,setAddWordOpen]=useState(false);const [wordForm]=Form.useForm<{term:string;meaning:string}>();const [compare,setCompare]=useState<MarketKeyword|null>(null);
 const [manualOpen,setManualOpen]=useState(false),[manualForm]=Form.useForm<FormData>();
 const [busy,setBusy]=useState(false);const sku=skus.find(s=>s.id===skuId)||skus[0]||{id:'',sku:'',name:'',material:'',uses:[],storeIds:[],hasLibrary:false};
 const [sourceAccountRef,setSourceAccountRef]=useState<string|null>(null);
 const [itemId,setItemId]=useState<string|null>(null);
 const [libraryTotal,setLibraryTotal]=useState(0);
 const [globalTotal,setGlobalTotal]=useState(0);
 const [globalRows,setGlobalRows]=useState<LibraryRow[]>([]);
 const [skuRows,setSkuRows]=useState<LibraryRow[]>([]);
 const [libraryPage,setLibraryPage]=useState(1);
 const [runTotal,setRunTotal]=useState(0);
 const [latestRunId,setLatestRunId]=useState<string|null>(null);
 useEffect(()=>{
   const saved=sessionStorage.getItem('keyword-planning:selected-product');
   if(saved){
     try{const value=JSON.parse(saved) as {id:string;sku:string};
       if(value.id&&value.sku){upsertProductSku({id:value.id,sku:value.sku,name:value.sku,
         material:'',uses:[],storeIds:[],hasLibrary:false});}
     }catch{/* invalid session hint is ignored */}
   }
   void preloadProductSkuOptions().then(items=>items.forEach(row=>{
     if(row.id&&row.sku)upsertProductSku({id:row.id,sku:row.sku,name:row.productName||row.sku,
       material:row.materialEn||'',uses:[],storeIds:[],hasLibrary:false});
   })).catch(()=>message.error('产品列表加载失败'));
 },[upsertProductSku]);
 useEffect(()=>{
   if(!sku.id||!sku.sku)return;
   let live=true;
   void searchListingsForSku(sku.sku).then(async found=>{
     if(!live)return;
     const remembered=sessionStorage.getItem('keyword-planning:selected-listing');
     const selected=found.candidates.find(candidate=>candidate.listing.id===remembered)
       ??(found.candidates.length===1?found.candidates[0]:null);
     if(!selected?.listing.sourceAccountRef){setSourceAccountRef(null);return;}
     setSourceAccountRef(selected.listing.sourceAccountRef);setItemId(selected.listing.productId);
   }).catch(()=>{if(live)setSourceAccountRef(null)});
   return()=>{live=false};
 },[sku.id,sku.sku]);
 const refreshLibrary=async(pageNumber=libraryPage,search=query)=>{
   if(!sku.id||!sourceAccountRef)return;
   const read=await listKeywordLibrary(sku.id,sourceAccountRef,{q:search,
     source:sourceFilter==='manual'?'operator_manual':sourceFilter,
     grade,limit:50,offset:(pageNumber-1)*50});
   installServerLibrary(sku.id,read.items);
   const saved=useKeywordStore.getState();
   setSkuRows(read.items.flatMap(item=>{
     const keyword=saved.keywords[item.term_id];
     const current=saved.entries.find(entry=>entry.skuId===sku.id&&entry.keywordId===item.term_id);
     return keyword?[{key:item.term_id,keyword,associated:current?[current]:[],current:current??null,
       mockAds:saved.ads.filter(ad=>ad.skuId===sku.id&&ad.keywordId===item.term_id)}]:[];
   }));
   setLibraryTotal(read.total);setLibraryPage(pageNumber);
   setLatestRunId(read.latest_run_id);
 };
 const refreshGlobalLibrary=async(pageNumber=libraryPage,search=query,filterSource=sourceFilter,filterGrade=grade)=>{
   if(!sourceAccountRef)return;
   const read=await listGlobalKeywordLibrary(sourceAccountRef,{
     q:search,source:filterSource==='manual'?'operator_manual':filterSource,
     grade:filterGrade,limit:50,offset:(pageNumber-1)*50,
   });
   setGlobalTotal(read.total);setLibraryPage(pageNumber);
   setGlobalRows(read.items.map(item=>{
     item.associations.forEach(link=>upsertProductSku({id:link.product_id,sku:link.sku,
       name:link.sku,material:'',uses:[],storeIds:[],hasLibrary:true}));
     const keyword:MarketKeyword={id:item.term_id,term:item.keyword,normalized:normalizeTerm(item.keyword),
       originalTranslation:item.translation,translation:item.translation,
       translationSource:item.translation?'manual':'missing',monthlySearches:null,
       monthlyPurchases:null,marketPurchaseRate:null,amazonPpc:null,bidRange:null,
       trafficType:null,relatedAsins:[],sponsoredCompetitors:null,listingCount:null,
       root:'',source:item.source_kinds.includes('operator_manual')?'manual':'excel',sourceRow:0};
     const associated:SkuKeyword[]=item.associations.map(link=>({skuId:link.product_id,
       keywordId:item.term_id,grade:link.grade as SkuKeyword['grade']||'复查',
       score:link.score,reason:'后端词库',exact:link.exact_selected,broad:link.broad_selected,
       status:link.status==='review'?'待测试':'已计划',analysisVersion:'后端分析'}));
     return {key:item.term_id,keyword,associated,current:associated[0]??null,mockAds:[]};
   }));
 };
 const submitSearch=async()=>{
   const value=searchInput.trim();
   if(searchType!=='sku'){
     setQuery(value);await (mode==='global'?refreshGlobalLibrary(1,value):refreshLibrary(1,value));return;
   }
   if(!value){setQuery('');await refreshLibrary(1,'');return;}
   try{
     const found=await searchProductsBySku(value);
     for(const row of found){
       if(!row.id||!row.sku)continue;
       upsertProductSku({id:row.id,sku:row.sku,name:row.productName||row.sku,
         material:row.materialEn||'',uses:[],storeIds:[],hasLibrary:false});
     }
     const exact=found.filter(row=>canonicalSku(row.sku)===canonicalSku(value));
     if(exact.length===1){
       setQuery('');setSkuId(exact[0].id);setMode('sku');
       if(exact[0].id===sku.id)await refreshLibrary(1,'');
     }else{
       message.warning(found.length?'已加载匹配的 SKU，请在当前 SKU 下拉框中选择':'未找到匹配的 SKU');
     }
   }catch{message.error('SKU 查询失败，请检查产品管理接口');}
 };
 useEffect(()=>{
   if(!sku.id||!sourceAccountRef)return;
   let live=true;
   void listKeywordRuns(sku.id,sourceAccountRef,1,0).then(async history=>{
     if(live)setRunTotal(history.total);
     if(history.items[0]){
       const results=await loadAllRunKeywords(history.items[0].run_id,sourceAccountRef);
       if(live)installServerRun(sku.id,history.items[0],results);
     }
     if(live)await refreshLibrary(1);
   }).catch(()=>{if(live)message.error('已保存词库加载失败')});
   return()=>{live=false};
 // Account and product changes re-read the backend; UI filters remain local.
 // eslint-disable-next-line react-hooks/exhaustive-deps
 },[sku.id,sourceAccountRef,installServerRun,installServerLibrary]);
 useEffect(()=>{
   if(mode!=='global'||!sourceAccountRef)return;
   queueMicrotask(()=>{void refreshGlobalLibrary(1,query,sourceFilter,grade).catch(()=>message.error('跨 SKU 词库加载失败'))});
 // The active account and filter selection are the complete server query key.
 // eslint-disable-next-line react-hooks/exhaustive-deps
 },[mode,sourceAccountRef,query,sourceFilter,grade]);
 useEffect(()=>{
   if(mode!=='sku'||!sku.id||!sourceAccountRef)return;
   queueMicrotask(()=>{void refreshLibrary(1,query).catch(()=>message.error('已保存词库筛选失败'))});
 // Filter changes must be applied before backend pagination.
 // eslint-disable-next-line react-hooks/exhaustive-deps
 },[mode,sourceFilter,grade]);
 const visible=(mode==='global'?globalRows:skuRows).filter(r=>{
   if(mode==='global'){
     if(tab==='todo')return r.associated.some(x=>x.status==='待测试'||x.status==='风险复查');
     if(tab==='execution')return r.associated.some(x=>x.exact||x.broad);
     return true;
   }
    if(sourceFilter!=='all'&&r.keyword.source!==sourceFilter)return false;
   const q=normalizeTerm(query);const found=!q||(searchType==='sku'?r.associated.some(x=>skus.find(s=>s.id===x.skuId)?.sku.toLowerCase().includes(q)):(r.keyword.term+' '+(r.keyword.translation||'')).toLowerCase().includes(q));
   if(!found||(grade!=='all'&&r.current?.grade!==grade&&!(grade==='复查'&&r.current?.grade==='候选复查')))return false;
   if(tab==='todo')return r.current?.status==='待测试'||r.current?.status==='风险复查';
   if(tab==='execution')return Boolean(r.current?.exact||r.current?.broad||r.mockAds.length);
   if(tab==='performance')return Boolean(performance(r.mockAds));
   return true;
 });
 const unmapped=ads.filter(a=>!a.skuId);
 const edit=(k:MarketKeyword)=>editTranslation(k,async(id,value)=>{
   if(!sourceAccountRef||!itemId)throw new Error('请先选择账户与 Listing');
   try{
     const result=await updateKeywordTranslation(sku.id,id,sourceAccountRef,itemId,value);
     updateTranslation(id,result.translation??'');await refreshLibrary(libraryPage);message.success('翻译已保存');
   }catch(error){message.error(error instanceof Error?error.message:'翻译保存失败');throw error;}
 });
 const commonColumns:ProColumns<LibraryRow>[]=[
  {title:'关键词 / 中文翻译',key:'term',width:275,render:(_,r)=><KeywordTextCell keyword={r.keyword} onEdit={edit}/>},
  {title:mode==='sku'?'词质等级':'关联 SKU',key:'grade',width:125,render:(_,r)=>mode==='sku'?<Tag color={r.current?.grade==='P0'?'green':r.current?.grade==='不投放'?'red':'blue'}>{r.current?.grade||'未分析'}</Tag>:<Button type="link" size="small" onClick={()=>setCompare(r.keyword)}>{r.associated.length} 个 SKU</Button>},
  {title:'来源 / 规则',key:'source',width:180,render:(_,r)=><><Tag>{r.keyword.source==='excel'?'Excel':r.keyword.source==='manual'?'人工补录':'本地样本'}</Tag><div className="keyword-planning__small">{r.current?.analysisVersion||'—'}</div></>},
  {title:'模拟投放计划',key:'plan',width:145,render:(_,r)=><Space size={2}>{r.current?.exact?<Tag color="blue">Exact</Tag>:null}{r.current?.broad?<Tag color="cyan">Broad</Tag>:null}{!r.current?.exact&&!r.current?.broad?'未推荐':null}</Space>},
  {title:'账户配置状态',key:'actual',width:170,render:(_,r)=>r.mockAds.length?<><Tag color={r.mockAds.some(a=>a.source==='manual')?'purple':'orange'}>{r.mockAds.some(a=>a.source==='manual')?'人工补录':'本地配置'}</Tag><div className="keyword-planning__small">真实 API 未同步</div></>:<Text type="secondary">未同步验证</Text>},
  {title:'月搜索量（Amazon）',key:'vol',width:155,render:(_,r)=>countText(r.keyword.monthlySearches)},
  {title:'分析 / 关联',key:'action',width:115,render:(_,r)=><Button type="link" onClick={()=>setCompare(r.keyword)}>对比 SKU</Button>},
 ];
 const executionColumns:ProColumns<LibraryRow>[]=[commonColumns[0],commonColumns[1],commonColumns[3],commonColumns[4],{title:'对账结论',key:'compare',width:230,render:(_,r)=>{
  if(!r.mockAds.length)return <Tag>待 API 同步验证</Tag>;
  if(r.mockAds.some(a=>a.source==='manual')&&!r.current?.exact&&!r.current?.broad)return <Tag color="purple">计划外新增 · 人工录入</Tag>;
  if(r.mockAds.some(a=>a.match==='Exact'&&r.current?.exact||a.match==='Broad'&&r.current?.broad))return <Tag color="green">匹配方式一致（本地）</Tag>;
  return <Tag color="orange">匹配方式不同（本地）</Tag>;
 }},commonColumns[6]];
 const performanceColumns:ProColumns<LibraryRow>[]=[commonColumns[0],{title:'SKU',key:'sku',width:140,render:(_,r)=>mode==='sku'?sku.sku:r.associated.map(a=>skus.find(s=>s.id===a.skuId)?.sku).join('、')},{title:'点击',key:'clicks',render:(_,r)=>countText(performance(r.mockAds)?.clicks??null)},{title:'花费',key:'spend',render:(_,r)=><MoneyCell value={performance(r.mockAds)?.spend??null}/>},{title:'订单',key:'orders',render:(_,r)=>countText(performance(r.mockAds)?.orders??null)},{title:'CPC',key:'cpc',render:(_,r)=><MoneyCell value={performance(r.mockAds)?.cpc??null}/>},{title:'CVR',key:'cvr',render:(_,r)=><PercentCell value={performance(r.mockAds)?.cvr??null}/>},{title:'ACOS',key:'acos',render:(_,r)=><PercentCell value={performance(r.mockAds)?.acos??null}/>},{title:'ROAS',key:'roas',render:(_,r)=>performance(r.mockAds)?.roas?.toFixed(2)||'—'}];
 const historyColumns:ProColumns<LibraryRow>[]=[commonColumns[0],commonColumns[1],{title:'分析分数',key:'score',render:(_,r)=>r.current?.score??'—'},{title:'历史分析版本',key:'version',render:(_,r)=>r.current?.analysisVersion||'—'},commonColumns[6]];
 const download=()=>{
   if(!latestRunId||!sourceAccountRef)return message.warning('该 SKU 尚无已保存分析批次');
   void downloadKeywordInternalWorkbook(latestRunId,sourceAccountRef).catch(()=>message.error('导出失败'));
 };
 const supplemental=async(file:File)=>{setBusy(true);try{
   if(!/\.xlsx$/i.test(file.name))throw new Error('后端原始文件归档仅支持 xlsx，请先保存为 xlsx');
   await parseSellerSprite(file);
   if(!sourceAccountRef)throw new Error('请选择账户归属明确的 Listing');
   const source=await getKeywordSourceState(sku.id,sourceAccountRef);
   if(!source.latest_confirmed_fact_id||source.item_id!==itemId)throw new Error('请先在关键词投放页确认商品事实');
   const receipt=await uploadKeywordSourceXlsx(file,sourceAccountRef,sku.id,source.latest_confirmed_fact_id);
   if(receipt.status!=='parsed')throw new Error('Excel 来源需要人工复核');
   await refreshLibrary(1);message.success(`已保存 ${receipt.source_rows} 行原始来源，新增词待分析`);
 }catch(e){message.error(e instanceof Error?e.message:'导入失败')}finally{setBusy(false)}};
 const submitManual=async()=>{try{const values=await manualForm.validateFields();
   if(!sourceAccountRef||!itemId||values.skuId!==sku.id)throw new Error('只能保存当前已确认账户与 SKU 的人工关键词');
   await addManualKeywordWords(sku.id,{source_account_ref:sourceAccountRef,item_id:itemId,
     request_key:crypto.randomUUID(),words:[{keyword:values.term}]});
   addManual({...values,skuId:sku.id});await refreshLibrary(1);
   setManualOpen(false);manualForm.resetFields();message.success('关键词已保存；广告配置仅在当前会话记录，未经平台验证');
 }catch(error){message.error(error instanceof Error?error.message:'保存失败')}};
 const addKeyword=async()=>{try{const value=await wordForm.validateFields();
   if(!sourceAccountRef||!itemId)throw new Error('请选择账户归属明确的 Listing');
   await addManualKeywordWords(sku.id,{source_account_ref:sourceAccountRef,item_id:itemId,
     request_key:crypto.randomUUID(),words:[{keyword:value.term,translation:value.meaning||undefined}]});
   await refreshLibrary(1);setAddWordOpen(false);wordForm.resetFields();
   message.success('关键词已保存，状态为待分析');
 }catch(error){message.error(error instanceof Error?error.message:'保存失败')}};
 return <PageShell page={page} headerActions={<Space><Button onClick={()=>setAddWordOpen(true)}>＋ 添加关键词</Button><Button onClick={()=>navigate('/ai-center/keyword-launch')}>去关键词投放</Button></Space>}>
   <div className="keyword-planning keyword-library kw-v2-library">
    <Alert type="info" showIcon message="全局关键词可关联多个 SKU，但每个 SKU 的评级与投放记录独立。平台广告配置尚未同步；没有同步广告实绩；仅展示你自己导入及手工补录的记录。"/>
    <div className="kw-v2-library-sku"><Text strong>当前 SKU（唯一商品维度）</Text><Space wrap><Select showSearch optionFilterProp="label" value={sku.id} style={{minWidth:320}} disabled={mode==='global'} onChange={setSkuId} options={skus.map(s=>({label:s.sku+' · '+s.name,value:s.id}))}/><Tag color="blue">{sku.sku}</Tag><Tag>{sku.storeIds.length} 个已关联店铺</Tag><Tag color="green">词库不按店铺拆分</Tag></Space></div>
    <Card size="small"><Space wrap><Button type={mode==='sku'?'primary':'default'} onClick={()=>setMode('sku')}>按 SKU 查看</Button><Button type={mode==='global'?'primary':'default'} onClick={()=>setMode('global')}>跨 SKU 关键词</Button><Tag>{mode==='sku'?libraryTotal:globalTotal} 个关键词</Tag><Tag color="blue">待认领广告关键词 {unmapped.length}</Tag></Space></Card>
    <div className="kw-v2-library-stats"><div><small>SKU 关键词总数</small><strong>{mode==='sku'?libraryTotal:globalTotal}</strong><span>去重后</span></div><div><small>Excel 来源</small><strong>{visible.filter(r=>r.keyword.source==='excel').length}</strong><span>当前页</span></div><div><small>Amazon 发现词</small><strong>0</strong><span>正文提取 API 未接入</span></div><div><small>待复核</small><strong>{visible.filter(r=>r.current?.grade==='复查'||r.current?.grade==='候选复查'||r.current?.grade==='不投放').length}</strong><span>当前页</span></div></div>
    <Alert type="info" message="词库归属规则：同一关键词在每个 SKU 下只保留一条主记录；同词可关联多个 SKU，但每个 SKU 独立评分和管理投放历史。"/>
    <Card size="small"><div className="kw-v2-library-actions"><Space wrap><Button type="primary" onClick={()=>setAddWordOpen(true)}>＋ 添加关键词</Button><Button onClick={()=>{message.warning('请在新品关键词投放页上传数据并重新分析；现有 SKU 不能直接覆盖历史分析')}}>重新分析当前 SKU</Button></Space></div><Space wrap><ConnectedSearch typeAriaLabel="选择搜索维度" typeOptions={[{label:'关键词',value:'keyword'},{label:'SKU',value:'sku'}]} typeValue={searchType} inputAriaLabel="输入关键词或SKU" inputPlaceholder="搜索关键词 / 中文意思" inputValue={searchInput} onTypeChange={setSearchType} onInputChange={setSearchInput} onSearch={()=>{void submitSearch()}}/><Space size={4} wrap>{[{id:'all',label:'全部来源'},{id:'excel',label:'Excel'},{id:'manual',label:'人工新增'}].map(x=><Button key={x.id} size="small" type={sourceFilter===x.id?'primary':'default'} onClick={()=>setSourceFilter(x.id)}>{x.label}</Button>)}</Space><Select value={grade} style={{width:125}} onChange={setGrade} options={['all','P0','P1','P2','复查','不投放'].map(v=>({label:v==='all'?'全部等级':v,value:v}))}/><ResetButton onClick={()=>{setQuery('');setSearchInput('');setGrade('all');setSearchType('keyword');setSourceFilter('all');void refreshLibrary(1,'')}}/><Button icon={<TranslationOutlined/>} disabled title="自动翻译接口未接入；可逐条编辑中文">批量翻译（待接入）</Button><Button icon={<PlusOutlined/>} onClick={()=>{manualForm.setFieldsValue({skuId:skuId,match:'Exact'});setManualOpen(true)}}>记录后台新增词</Button><Upload accept=".xlsx" showUploadList={false} beforeUpload={file=>{void supplemental(file);return false}}><Button loading={busy} icon={<UploadOutlined/>}>补充 Excel</Button></Upload><Button onClick={download}>导出当前词库</Button></Space></Card>
    <Card size="small" title="关键词资产与投放情况" extra={<Tag>{mode==='global'?'后端跨 SKU 分页':'仅当前 SKU'}</Tag>}>
      <Tabs activeKey={tab} onChange={v=>setTab(v as Tab)} items={[{key:'all',label:'全部关键词'},{key:'todo',label:'待测试 / 复查'},{key:'execution',label:'计划与实际投放'},{key:'history',label:'分析记录'}]}/>
      {tab==='execution'?<Alert style={{marginBottom:12}} type="warning" message="仅能比较本地计划与人工配置。没有真实 API 时「未同步」绝不等于「未投放」。"/>:null}
      {tab==='performance'?<Alert style={{marginBottom:12}} type="warning" message="以下花费、点击、订单、CPC、CVR、ACOS 均为合成 mock 数据。Amazon PPC 参考值不参与这些计算。"/>:null}
      {tab==='history'?<Alert style={{marginBottom:12}} type="info" message={`已保存的分析记录 ${mode==='sku'?runTotal:analyses.length} 次；新规则发布不会自动覆盖旧分析。`}/>:null}
      <ReportTableShell label="SKU 关键词词库明细"><ProTable<LibraryRow> rowKey="key" options={false} search={false} toolBarRender={false} columns={tab==='execution'?executionColumns:tab==='performance'?performanceColumns:tab==='history'?historyColumns:commonColumns} dataSource={visible} locale={{emptyText:'暂无关键词。请先到关键词投放录入 SKU 并上传你自己的 Excel'}} pagination={{current:libraryPage,pageSize:50,total:mode==='global'?globalTotal:libraryTotal,onChange:pageNumber=>{void (mode==='global'?refreshGlobalLibrary(pageNumber):refreshLibrary(pageNumber))}}} scroll={{x:tab==='performance'?1300:1200,y:440}}/></ReportTableShell>
    </Card>
    {tab==='execution'?<Card size="small" title={`未归属广告关键词 · ${unmapped.length} 条（本地）`}><Space direction="vertical" style={{width:'100%'}}>{unmapped.map(a=><Space wrap key={a.id}><Text strong>{a.term}</Text><Tag>{a.store}</Tag><Tag>{a.match}</Tag><Select style={{width:210}} placeholder="选择归属 SKU" options={skus.map(s=>({label:s.sku,value:s.id}))} onChange={value=>{assignManual(a.id,value);message.success('已在当前会话完成本地归属')}}/></Space>)}{!unmapped.length?<Empty description="当前没有待认领词"/>:null}</Space></Card>:null}
   </div>
   <Drawer open={!!compare} onClose={()=>setCompare(null)} title={`跨 SKU 关键词对比 · ${compare?.term||''}`} width={620}>
    <Alert type="warning" message="同一个词在不同 SKU 中的匹配分与广告表现分别计算。所有广告数据均为 未同步。"/>
    {compare?<ProTable rowKey="skuId" search={false} options={false} toolBarRender={false} pagination={false} columns={[{title:'SKU',dataIndex:'skuId',render:(_,r)=>skus.find(s=>s.id===r.skuId)?.sku},{title:'匹配等级',dataIndex:'grade'},{title:'潜力分',dataIndex:'score'},{title:'ACOS（API待接入）',render:(_,r)=>{const p=performance(ads.filter(a=>a.skuId===r.skuId&&a.keywordId===compare.id));return p?.acos!=null?p.acos.toFixed(1)+'%':'—'}},{title:'投放来源',render:(_,r)=>ads.some(a=>a.skuId===r.skuId&&a.keywordId===compare.id)?'人工':'未同步'}]} dataSource={mode==='global'?globalRows.find(r=>r.key===compare.id)?.associated??[]:entries.filter(e=>e.keywordId===compare.id)}/>:null}
    {compare?<Descriptions column={1} bordered size="small" items={[{key:'original',label:'原始翻译',children:compare.originalTranslation||'—'},{key:'effective',label:'当前中文',children:compare.translation||'待翻译'},{key:'source',label:'翻译来源',children:compare.translationSource}]} />:null}
   </Drawer>
   <Modal open={addWordOpen} title="添加关键词到当前 SKU 词库" okText="添加到词库" onCancel={()=>setAddWordOpen(false)} onOk={()=>{void addKeyword()}}><Form layout="vertical" form={wordForm}><Form.Item name="term" label="英文关键词" rules={[{required:true,message:'请输入英文关键词'}]}><Input placeholder="drawer organizer"/></Form.Item><Form.Item name="meaning" label="中文意思（可选）"><Input placeholder="抽屉收纳用品"/></Form.Item><Alert type="info" message="人工添加仅加入词库，不会自动建立真实广告投放。"/></Form></Modal>
   <Modal open={manualOpen} title="记录 Walmart 后台新增关键词（人工补录）" okText="保存人工记录" onOk={()=>{void submitManual()}} onCancel={()=>setManualOpen(false)}>
     <Alert type="info" message="人工补录不代表 API 已经校验；请选择 SKU 或进入待认领队列。" style={{marginBottom:12}}/>
     <Form layout="vertical" form={manualForm}>
      <Form.Item name="skuId" label="对应 SKU" rules={[{required:true}]}><Select options={[...skus.map(s=>({label:s.sku,value:s.id})),{label:'暂无法归属 · 待认领',value:'unassigned'}]}/></Form.Item>
      <Form.Item name="term" label="英文投放关键词" rules={[{required:true,message:'请输入关键词'}]}><Input/></Form.Item>
      <Form.Item name="store" label="店铺" rules={[{required:true}]}><Input/></Form.Item>
      <Form.Item name="campaign" label="Campaign" rules={[{required:true}]}><Input/></Form.Item>
      <Form.Item name="match" label="投放方式" rules={[{required:true}]}><Select options={[{label:'Exact',value:'Exact'},{label:'Broad',value:'Broad'}]}/></Form.Item>
      <Form.Item name="bid" label="人工录入 Bid（USD）" rules={[{required:true}]}><InputNumber min={0} step={0.01} style={{width:'100%'}}/></Form.Item>
     </Form>
   </Modal>
 </PageShell>;
}
