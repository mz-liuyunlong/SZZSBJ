/* KW_SKU_LABEL_ITEMID_LAYOUT_20261022 */
/* KEYWORD_SKU_RESELECT_FIX_20261022 */
/* KEYWORD_SKU_INITIAL_PREFETCH_20261022 */
/* KEYWORD_PRODUCT_LISTING_API_LOCAL_20261022 */
/** Owner-approved workspace; persisted V1.1 results are read from the backend. */
import {useEffect,useMemo,useRef,useState} from 'react';
import {useNavigate} from 'react-router-dom';
import {Alert,Button,Card,Checkbox,Descriptions,Divider,Drawer,Empty,Input,InputNumber,Modal,Select,Space,Steps,Tabs,Tag,Typography,Upload,message} from 'antd';
import {FileExcelOutlined,HistoryOutlined,InboxOutlined,SettingOutlined,TranslationOutlined} from '@ant-design/icons';
import {ProTable,type ProColumns} from '@ant-design/pro-components';
import * as XLSX from 'xlsx';
import PageShell from '@/components/page/PageShell';
import ReportTableShell from '@/components/report-table/ReportTableShell';
import {MoneyCell,PercentCell} from '@/components/report-table/cells';
import type {NavigationPage} from '@/config/navigation';
import {KeywordTextCell} from '@/features/keyword-planning/components/KeywordTextCell';
import {useKeywordStore} from '@/features/keyword-planning/store';
import {countText,dollarText,parseAsins} from '@/features/keyword-planning/model';
import {displayRule,loadEffectiveRule} from '@/features/keyword-planning/effectiveRule';
import {parseSellerSprite} from '@/features/keyword-planning/importWorkbook';
import type {MarketKeyword,SkuKeyword,SkuDefinition} from '@/features/keyword-planning/types';
import type {ProductManagementRow} from '@/pages/products/productManagementTypes';
import type {ListingCandidate} from '@/features/keyword-planning/keywordProductLookup';
import {canonicalSku,getProductFacts,preloadProductSkuOptions,searchListingsForSku,searchProductsBySku} from '@/features/keyword-planning/keywordProductLookup';
import {confirmWalmartFacts,researchAmazonAsins,type AmazonEvidence,type WalmartFacts} from "@/api/decodoApi";
import {confirmStoredKeywordFacts,submitKeywordAiJob,listKeywordAiJobs,cancelKeywordAiJob,downloadKeywordInternalWorkbook,getKeywordRun,getKeywordSourceState,importStoredAsin,listKeywordRuns,loadAllRunKeywords,preflightKeywordAnalysis,updateKeywordTranslation,uploadKeywordSourceXlsx,type KeywordRun,type KeywordAiJob} from '@/api/keywordPlanningV11Api';
import {BackendRequestError,backendRequest} from '@/api/backendApi';
import './KeywordLaunchPage.css';
import {KeywordRulesPanel} from '@/pages/ai-center/keyword-rules/KeywordRulesPage';

const {Text}=Typography;
type KeywordRow={entry:SkuKeyword;keyword:MarketKeyword};
type ResultsTab='keywords'|'plan'|'listing';
type KeywordView='decision'|'market';
type ProductFacts={title:string;itemType:string;owner:string;brand:string;material:string;color:string;pack:string;size:string;structure:string;use:string;forbidden:string;manualBid:number;autoBid:number;manualBudget:number;autoBudget:number;startDate:string};
// First-stage local selection confirmation. Scraped Walmart facts will be added later.
type ConfirmedSelection={skuId:string;itemId:string;mode:'listing'|'manual';listingId:string|null;store:string|null};
function initialFacts(_skuId:string,_skuName:string,_material:string,ruleBid:{exact:number;auto:number;dailyBudget:number;startDate?:string}):ProductFacts{
 void _skuId;void _skuName;void _material;
 return {
  title:'',itemType:'',owner:'',brand:'',material:'',
  color:'',pack:'',size:'',structure:'',use:'',
  forbidden:'',
  manualBid:ruleBid.exact,
  autoBid:ruleBid.auto,
  manualBudget:ruleBid.dailyBudget,
  autoBudget:ruleBid.dailyBudget,
  startDate:ruleBid.startDate??''
 };
}
const requiredProductFields=[
 {key:'title',label:'商品标题'},
 {key:'itemType',label:'商品真实类型'},
 {key:'brand',label:'品牌'},
 {key:'material',label:'材质'},
 {key:'color',label:'颜色'},
 {key:'pack',label:'Pack / 数量'},
 {key:'size',label:'尺寸 / 容量'},
 {key:'structure',label:'商品结构 / 配件'},
 {key:'use',label:'核心用途'},
 {key:'owner',label:'运营负责人'},

] as const;
const filledFact=(value:string)=>
 Boolean(value.trim())&&!/^(待核对|待采集|暂无|未知|无数据|unknown|n\/a|--)$/i.test(value.trim());
function csvDownload(name:string,headers:string[],rows:(string|number|null|undefined)[][]){
 const safe=(v:string|number|null|undefined)=>{const raw=String(v??'');const s=/^[\s]*[=+@-]/.test(raw)?"'"+raw:raw;return '"'+s.replace(/"/g,'""')+'"'};
 const file=[headers,...rows].map(row=>row.map(safe).join(',')).join('\r\n');
 const url=URL.createObjectURL(new Blob(['\uFEFF'+file],{type:'text/csv;charset=utf-8'}));const a=document.createElement('a');a.href=url;a.download=name;a.click();URL.revokeObjectURL(url);
}
function Metric({label,value,hint,symbol}:{label:string;value:string|number;hint:string;symbol:string}){return <div className="kw-v2-stat"><div className="kw-v2-stat-icon">{symbol}</div><div><div className="kw-v2-muted">{label}</div><strong>{value}</strong><div className="kw-v2-muted">{hint}</div></div></div>}

function keywordReadError(kind:'rule'|'source'|'history',error:unknown):string{
 const label={rule:'规则',source:'已保存来源',history:'分析历史'}[kind];
 if(!(error instanceof BackendRequestError))return `${label}读取失败，请检查连接`;
 const trace=error.requestId?`（请求 ID：${error.requestId}）`:'';
 if(error.status===403)return `${label}读取被拒绝：当前账号缺少权限或账户数据范围不匹配${trace}`;
 if(error.status===404){
   if(kind==='source')return `来源接口返回 404：请核对后端版本及商品、Listing SKU 与账户关联；未保存来源应返回空状态${trace}`;
   if(kind==='rule')return `规则接口返回 404：请核对后端部署版本；没有自定义规则时应返回系统默认规则${trace}`;
   return `分析历史接口返回 404：请核对后端部署版本；无历史应返回空列表${trace}`;
 }
 if(error.status>=500)return `${label}服务端异常（HTTP ${error.status}），请按请求 ID 排查${trace}`;
 if(error.kind==='network'||error.kind==='timeout')return `${label}网络或代理连接失败${trace}`;
 return `${label}读取失败（HTTP ${error.status}）${trace}`;
}

export default function KeywordLaunchPage({page}:{page:NavigationPage}){
 const navigate=useNavigate();
 const [panel,setPanel]=useState<'workspace'|'rules'>('workspace');
 const {skus,keywords,entries,staged,rules,analyses,setStaged,installServerRun,upsertProductSku,updateTranslation,listing,saveListing}=useKeywordStore();
 const [skuId,setSkuId]=useState('');
 const [editing,setEditing]=useState(false);
 const [skuSearch,setSkuSearch]=useState('');
 const [skuOptions,setSkuOptions]=useState<ProductManagementRow[]>([]);
 const [skuLoading,setSkuLoading]=useState(false);
 const [skuError,setSkuError]=useState('');
 const [listingCandidates,setListingCandidates]=useState<ListingCandidate[]>([]);
 const [listingLoading,setListingLoading]=useState(false);
 const [listingError,setListingError]=useState('');
 const [itemId,setItemId]=useState('');
 const [itemManual,setItemManual]=useState(false);
 const [selectedListing,setSelectedListing]=useState<ListingCandidate|null>(null);
 const [productConfirmation,setProductConfirmation]=useState<ConfirmedSelection|null>(null);
 const [decodoSnapshotId,setDecodoSnapshotId]=useState<string|null>(null);
 const [factId,setFactId]=useState<string|null>(null);
 const [sourceFile,setSourceFile]=useState<File|null>(null);
 const [storedUpload,setStoredUpload]=useState<{id:string;filename:string;rows:number}|null>(null);
 const [activeRunId,setActiveRunId]=useState<string|null>(null);
 const [serverRuns,setServerRuns]=useState<KeywordRun[]>([]);
 const [historyTotal,setHistoryTotal]=useState(0);
 const [historyPage,setHistoryPage]=useState(1);
 const [sourceError,setSourceError]=useState('');
 const [ruleError,setRuleError]=useState('');
 const [historyError,setHistoryError]=useState('');
 const [currentRuleVersionId,setCurrentRuleVersionId]=useState<string|null>(null);

 const [pendingSelection,setPendingSelection]=useState<ConfirmedSelection|null>(null);
 const [walmartError,setWalmartError]=useState(false);
 const [,setWalmartEvidence]=useState<{
   title:string;
   description:string;
   attributes:string;
 }|null>(null);
 const [walmartSource,setWalmartSource]=useState<WalmartFacts|null>(null);
 const [,setAmazonEvidence]=useState<AmazonEvidence[]>([]);
 const [confirmingProduct,setConfirmingProduct]=useState(false);
 const selectionSeq=useRef(0);
 // Invalidates Excel parsing responses after changing the target SKU or Item ID.
 const confirmationSeq=useRef(0);
 const initialSkuRef=useRef<ProductManagementRow[]>([]);
  const [initialSkuRows,setInitialSkuRows]=useState<ProductManagementRow[]>([]);
 // Invalidates slow responses from an earlier search as soon as the user types.
 const skuQueryRef=useRef('');
 const [asins,setAsins]=useState('');
 const [facts,setFacts]=useState<ProductFacts>(()=>initialFacts('','','',rules.bid));
 const [factOpen,setFactOpen]=useState(false);
 const [confirmed,setConfirmed]=useState(false);
 const [consent,setConsent]=useState(false);
 const [resultsTab,setResultsTab]=useState<ResultsTab>('keywords');
 const [keywordView,setKeywordView]=useState<KeywordView>('decision');
 const [filter,setFilter]=useState('全部');
 const [placement,setPlacement]=useState('all');
 const [query,setQuery]=useState('');
 const [busy,setBusy]=useState(false);
 const [detail,setDetail]=useState<KeywordRow|null>(null);
 const [compare,setCompare]=useState<MarketKeyword|null>(null);
 const [historyOpen,setHistoryOpen]=useState(false);
 const [aiTasksOpen,setAiTasksOpen]=useState(false);
 const [aiTasks,setAiTasks]=useState<KeywordAiJob[]>([]);
 const [aiTasksLoading,setAiTasksLoading]=useState(false);
 const [draft,setDraft]=useState<{title:string;features:string;description:string}|null>(null);
 const sku=skus.find(x=>x.id===skuId)||{id:'',sku:'',name:'',material:'',uses:[],storeIds:[],hasLibrary:false};
 const skuEntries=useMemo(()=>entries.filter(e=>e.skuId===sku.id),[entries,sku.id]);
 const rows=useMemo(()=>skuEntries.flatMap(e=>keywords[e.keywordId]?[{entry:e,keyword:keywords[e.keywordId]}]:[]),[skuEntries,keywords]);
 const existing=sku.hasLibrary&&rows.length>0&&!editing;
 const parsedAsins=useMemo(()=>parseAsins(asins),[asins]);
 const listingId=itemManual?null:selectedListing?String(selectedListing.listing.id):null;
 const listingStore=itemManual?null:selectedListing?.listing.store??null;
 const sourceAccountRef=selectedListing?.listing.sourceAccountRef??null;
 useEffect(()=>{
   let live=true;
   queueMicrotask(()=>{if(live){setCurrentRuleVersionId(null);setRuleError('')}});
   if(sourceAccountRef)void loadEffectiveRule(sourceAccountRef).then(current=>{
     if(!live)return;
     const parsed=current?displayRule(current.version):null;
     if(!parsed){setCurrentRuleVersionId(null);setRuleError('当前账户没有可用的后端规则版本');return;}
     useKeywordStore.setState({rules:parsed});
     setCurrentRuleVersionId(current.version.version_id);
     setRuleError('');
   }).catch(error=>{if(live){setCurrentRuleVersionId(null);setRuleError(keywordReadError('rule',error))}});
   return()=>{live=false};
 },[sourceAccountRef]);
 const productConfirmed=Boolean(productConfirmation
   && productConfirmation.skuId===sku.id
   && productConfirmation.itemId===itemId
   && productConfirmation.mode===(itemManual?'manual':'listing')
   && productConfirmation.listingId===listingId
   && productConfirmation.store===listingStore);
 const productPending=Boolean(confirmingProduct&&pendingSelection&&pendingSelection.skuId===sku.id&&pendingSelection.itemId===itemId&&pendingSelection.mode===(itemManual?'manual':'listing')&&pendingSelection.listingId===listingId&&pendingSelection.store===listingStore);
 const step02Unlocked=productConfirmed||productPending;
 const canConfirmProduct=Boolean(sku.id&&sourceAccountRef)&&/^\d{1,20}$/.test(itemId)&&!listingLoading&&!confirmingProduct&&Boolean(selectedListing);
 // Confirmation of item identity and final analysis parameters are separate gates.
 const inputsComplete=step02Unlocked&&Boolean(staged)&&Boolean(currentRuleVersionId)&&parsedAsins.invalid.length===0&&parsedAsins.valid.length>=rules.asin.min;
 const ready=productConfirmed&&inputsComplete;
 const rulesDate=rules.bid.startDate??'';
 const missingRequired=[
   ...requiredProductFields
     .filter(({key})=>!filledFact(facts[key]))
     .map(({label})=>label),
 ];
 const parametersComplete=missingRequired.length===0;
 const waitingForWalmart=productPending&&inputsComplete;
 useEffect(()=>{if(productPending)document.querySelector<HTMLTextAreaElement>('.kw-v2-asin-input')?.focus()},[productPending]);
 const hasAnalysis=Boolean(skuEntries.length&&analyses.some(a=>a.skuId===sku.id));
 const analyzed=hasAnalysis&&!editing;
 const lastAnalysis=[...analyses].reverse().find(a=>a.skuId===sku.id);
 const filtered=rows.filter(({entry:e,keyword:k})=>(filter==='全部'||e.grade===filter)&&(placement==='all'||(placement==='exact'&&e.exact)||(placement==='broad'&&e.broad)||(placement==='none'&&!e.exact&&!e.broad))&&(k.term+' '+(k.translation||'')+' '+k.root).toLowerCase().includes(query.toLowerCase()));
 const allAssoc=(keywordId:string)=>entries.filter(e=>e.keywordId===keywordId);
 const effectiveDraft=draft||listing[sku.id]||{title:facts.title,features:'',description:''};
 const invalidateProductConfirmation=()=>{
   confirmationSeq.current+=1;
   setProductConfirmation(null);
   setDecodoSnapshotId(null);setFactId(null);setSourceFile(null);setStoredUpload(null);setActiveRunId(null);
   setServerRuns([]);setHistoryTotal(0);setHistoryPage(1);
   setSourceError('');setHistoryError('');
   setPendingSelection(null);setConfirmingProduct(false);setWalmartError(false);setWalmartEvidence(null);setWalmartSource(null);

   setFacts(old=>({
     ...initialFacts('','','',rules.bid),
     owner:old.owner
   }));
   setAmazonEvidence([]);
   setConfirmed(false);
   setConsent(false);
   setFactOpen(false);
   setAsins('');

   setBusy(false);
 };
 useEffect(()=>{
   if(!sku.id||!sourceAccountRef||!itemId||!selectedListing)return;
   let live=true;
   const ticket=confirmationSeq.current;
   void getKeywordSourceState(sku.id,sourceAccountRef)
     .then(source=>{
       if(!live||ticket!==confirmationSeq.current)return;
       setSourceError('');
       if(source.item_id===itemId&&source.latest_confirmed_fact_id){
         setFactId(source.latest_confirmed_fact_id);
         setConfirmed(true);
         setAsins(source.asin_references.join('\n'));
         setStoredUpload(source.latest_upload_id?{
           id:source.latest_upload_id,filename:source.latest_upload_filename??'已保存的 Excel',
           rows:source.latest_upload_rows,
         }:null);
         setFacts(old=>({...old,
           title:source.confirmed_fields.title??old.title,
           itemType:source.confirmed_fields.item_type??old.itemType,
           brand:source.confirmed_fields.brand??old.brand,
           material:source.confirmed_fields.material??old.material,
           color:source.confirmed_fields.color??old.color,
           pack:source.confirmed_fields.pack??old.pack,
           size:source.confirmed_fields.size??old.size,
           structure:source.confirmed_fields.structure??old.structure,
           use:source.confirmed_fields.use??old.use,
           owner:source.confirmed_fields.owner??old.owner,
         }));
         setProductConfirmation({skuId:sku.id,itemId,mode:itemManual?'manual':'listing',
           listingId,store:listingStore});
       }
     }).catch(error=>{if(live&&ticket===confirmationSeq.current)setSourceError(keywordReadError('source',error))});
   void listKeywordRuns(sku.id,sourceAccountRef,20,0)
     .then(async history=>{
       if(!live||ticket!==confirmationSeq.current)return;
       setServerRuns(history.items);setHistoryTotal(history.total);setHistoryError('');
       if(history.items[0]){
         const latest=history.items[0];
         const results=await loadAllRunKeywords(latest.run_id,sourceAccountRef);
         if(live&&ticket===confirmationSeq.current){
           installServerRun(sku.id,latest,results);setActiveRunId(latest.run_id);
         }
       }
     }).catch(error=>{if(live&&ticket===confirmationSeq.current)setHistoryError(keywordReadError('history',error))});
   return()=>{live=false};
 },[sku.id,sourceAccountRef,itemId,selectedListing,itemManual,listingId,listingStore,installServerRun]);
 const confirmProduct=async()=>{
   if(!canConfirmProduct)return message.warning('请先选择真实 SKU 和有效的 Walmart Item ID');
   if(!itemManual&&selectedListing?.listing.productId!==itemId)return message.error('Listing 与 Item ID 不一致，请重新选择');
   const ticket=confirmationSeq.current;
   const targetSku=sku.id,targetItem=itemId;
   setConfirmingProduct(true);
   setPendingSelection({skuId:targetSku,itemId:targetItem,mode:itemManual?'manual':'listing',listingId,store:listingStore});
   setWalmartError(false);setWalmartEvidence(null);
   setProductConfirmation(null);

   try {
     const doc=await confirmWalmartFacts(targetSku,targetItem);
     if(ticket!==confirmationSeq.current)return;
     if(doc.item_id!==targetItem||doc.sku_id!==targetSku||!doc.verified)throw new Error('采集商品身份与所选商品不一致');
     if(!doc.snapshot_id)throw new Error('采集来源未保存，无法确认商品事实');
     setDecodoSnapshotId(doc.snapshot_id);setWalmartSource(doc);
     const rawDescription =
       (doc as unknown as {description?:unknown}).description;
     setWalmartEvidence({
       title:doc.title||'',
       description:typeof rawDescription==='string'?rawDescription:'',
       attributes:Object.entries(doc.attributes||{})
         .map(([k,v])=>k+' '+String(v)).join(' ')
     });

     const attr=(...names:string[]):string=>{
       const key=Object.keys(doc.attributes).find(k=>
         names.some(n=>k.trim().toLowerCase()===n.toLowerCase())
       );
       const value=key?doc.attributes[key].trim():'';
       return filledFact(value)?value:'';
     };
     setFacts(old=>({
       ...initialFacts('','','',rules.bid),
       owner:old.owner,
       title:doc.title?.trim()||'',
       itemType:doc.category_path.at(-1)?.trim()||'',
       brand:doc.brand?.trim()||'',
       material:attr('Material'),
       color:attr('Color'),
       size:attr('Dimensions','Product Dimensions','Size'),
       pack:attr('Pack Size','Pack Quantity','Package Quantity'),
       structure:attr('Included Components','Package Contents'),
       use:attr('Recommended Uses','Recommended Uses for Product','Usage','Uses'),
     }));
     // The SKU / store relation comes from the chosen Listing; the Decodo page
     // independently confirms the requested Walmart product identifier.
     setProductConfirmation({skuId:targetSku,itemId:targetItem,mode:itemManual?'manual':'listing',listingId,store:listingStore});
     setConfirmed(false);
     setConsent(false);
     message.success('Walmart 商品资料已采集，Item ID 已验证；可以进入步骤 02');
   } catch {
     if(ticket===confirmationSeq.current){
      setWalmartError(true);

      // Failure is NOT Item ID verification; never unlock subsequent steps.
      setProductConfirmation(null);
      message.error('Walmart Item ID 核验失败，请重试；不能将手工资料冒充已验证');
      setConfirmed(false);
      setConsent(false);
    }
   } finally {
     if(ticket===confirmationSeq.current){setPendingSelection(null);setConfirmingProduct(false);}
   }
 };
 const switchSku=(next:string)=>{const s=useKeywordStore.getState().skus.find(v=>v.id===next);if(!s)return;selectionSeq.current++;invalidateProductConfirmation();setItemId('');setItemManual(false);setSelectedListing(null);setListingCandidates([]);setListingError('');setListingLoading(false);setEditing(false);setSkuId(next);setStaged(null);setFacts(initialFacts(s.id,s.name,s.material,rules.bid));setResultsTab('keywords');setFilter('全部');setPlacement('all');setQuery('');setDraft(null)};
 // Opening the page preloads one bounded page of real SKUs. Typing first
 // filters those rows immediately and then searches the server for other SKUs.
 // Typing a different SKU is an edit, not confirmation of the old product.
 // Clear the old selection and all dependent facts/Item ID immediately.
 const clearSelectedSku=()=>{
   sessionStorage.removeItem('keyword-planning:selected-product');
   sessionStorage.removeItem('keyword-planning:selected-listing');
   selectionSeq.current+=1; // ignore pending product/detail/listing responses
   invalidateProductConfirmation();
   setSkuId('');setItemId('');setItemManual(false);setSelectedListing(null);
   setListingCandidates([]);setListingLoading(false);setListingError('');
   setEditing(false);setStaged(null);setAsins('');
   setFacts(initialFacts('','','',rules.bid));setConfirmed(false);setConsent(false);
   setResultsTab('keywords');setFilter('全部');setPlacement('all');setQuery('');setDraft(null);
 };
 const handleSkuSearch=(value:string)=>{
   const q=canonicalSku(value);
   skuQueryRef.current=q;
   setSkuSearch(value);
   setSkuError('');
   if(q&&sku.id&&q!==canonicalSku(sku.sku))clearSelectedSku();
   // Instant locally filtered results. Never show options from the last query.
   setSkuOptions(q.length<2
     ?initialSkuRef.current
     :initialSkuRef.current.filter(row=>canonicalSku(row.sku).includes(q)).slice(0,50));
 };
 // Exact SKU wins. Only display results corresponding to the current input.
 const skuDropdownRows=useMemo(()=>{
   const q=canonicalSku(skuSearch);
   const map=new Map<string,ProductManagementRow>();
   for(const row of [...skuOptions,...(q.length<2?initialSkuRows:[])]){
     if(row.id&&row.sku&&(!q||canonicalSku(row.sku).includes(q)))map.set(row.id,row);
   }
   // Preserve the selected option's label only when the search box is empty.
   if(!q&&sku.id&&!map.has(sku.id)){
     map.set(sku.id,{id:sku.id,sku:sku.sku,productName:sku.name} as ProductManagementRow);
   }
   const candidates=[...map.values()];
   const exact=q?candidates.filter(row=>canonicalSku(row.sku)===q):[];
   return (exact.length?exact:candidates)
     .sort((a,b)=>Number(canonicalSku(b.sku)===q)-Number(canonicalSku(a.sku)===q)
       ||canonicalSku(a.sku).localeCompare(canonicalSku(b.sku)))
     .slice(0,50);
 },[skuOptions,initialSkuRows,skuSearch,sku.id,sku.sku,sku.name]);
 useEffect(()=>{
   const q=canonicalSku(skuSearch);
   let active=true;
   const timer=window.setTimeout(()=>{
     // A cleared/short search reuses the already prefetched first page.
     if(q.length<2&&initialSkuRef.current.length>0){
       if(active&&skuQueryRef.current===q){
         setSkuOptions(initialSkuRef.current);
         setSkuLoading(false);
       }
       return;
     }
     setSkuLoading(true);
     setSkuError('');
     const request=q.length<2?preloadProductSkuOptions():searchProductsBySku(q);
     void request.then(rows=>{
       if(!active||skuQueryRef.current!==q)return;
       if(q.length<2){
          initialSkuRef.current=rows;
          setInitialSkuRows(rows);
        }
       setSkuOptions(rows);
     }).catch(()=>{
       if(!active||skuQueryRef.current!==q)return;
       setSkuError(q.length<2
         ?'SKU 首批加载失败：请检查登录、产品管理权限或 API 代理'
         :'SKU 搜索失败：请检查网络和产品管理权限');
       // Keep already prefetched rows available after a network failure.
       if(q.length<2)setSkuOptions(initialSkuRef.current);
     }).finally(()=>{if(active&&skuQueryRef.current===q)setSkuLoading(false)});
   },q.length>=2?300:0);
   return ()=>{active=false;window.clearTimeout(timer)};
 },[skuSearch]);
 const pickProduct=async(productId:string,rowOverride?:ProductManagementRow)=>{
   const row=rowOverride??(
     skuDropdownRows.find(p=>p.id===productId)
     ||initialSkuRef.current.find(p=>p.id===productId)
     ||skuOptions.find(p=>p.id===productId)
   );
   if(!row||!row.sku)return;
   const id=String(row.id),ticket=selectionSeq.current+1;
   const product:SkuDefinition={id,sku:row.sku,name:row.productName||row.sku,material:row.materialEn||row.materialCn||'',uses:[],storeIds:[],hasLibrary:false};
   upsertProductSku(product);switchSku(id);selectionSeq.current=ticket;
   sessionStorage.setItem('keyword-planning:selected-product',JSON.stringify({id,sku:row.sku}));
   skuQueryRef.current='';setSkuSearch('');setSkuOptions(initialSkuRef.current);
   setFacts(old=>({...old,owner:row.ownerName||''}));
   setListingLoading(true);setListingError('');
   const results=await Promise.allSettled([getProductFacts(row),searchListingsForSku(row.sku)]);
   if(selectionSeq.current!==ticket)return;
   const detail=results[0];
   if(detail.status==='fulfilled'){
     const d=detail.value;
     setFacts(old=>({...old,owner:d.ownerName||old.owner}));
     upsertProductSku({...product,material:d.materialEn||d.materialCn||product.material,uses:(d.usageEn||'').split(/[,;\n]+/).map(x=>x.trim()).filter(Boolean)});
   }else message.warning('产品详情读取失败：仅展示产品列表中已确认的资料');
   const found=results[1];
   if(found.status==='fulfilled'){
     const candidates=found.value.candidates;
     setListingCandidates(candidates);
     if(found.value.warnings.length)setListingError(found.value.warnings.join('；'));
     const exact=candidates.filter(x=>x.match==='sku_exact');
     const remembered=sessionStorage.getItem('keyword-planning:selected-listing');
     const restored=candidates.find(x=>x.listing.id===remembered);
     if(restored||exact.length===1){const choice=restored??exact[0];setSelectedListing(choice);setItemId(choice.listing.productId);sessionStorage.setItem('keyword-planning:selected-listing',choice.listing.id);}
     // Ambiguous matches and all MSKU candidates must be confirmed by the operator.
     const fromDetail=detail.status==='fulfilled'?detail.value:null;
     upsertProductSku({...product,material:fromDetail?.materialEn||fromDetail?.materialCn||product.material,uses:(fromDetail?.usageEn||'').split(/[,;\n]+/).map(x=>x.trim()).filter(Boolean),storeIds:[...new Set(candidates.filter(x=>x.match==='sku_exact').map(x=>x.listing.store))]});
   }else setListingError('Listing 查询失败：不能认定无关联，请检查 API 或手动填写 Item ID');
   setListingLoading(false);
 };
 useEffect(()=>{
   const saved=sessionStorage.getItem('keyword-planning:selected-product');
   if(!saved)return;
   try{
     const value=JSON.parse(saved) as {id:string;sku:string};
     if(!value.id||!value.sku)return;
     void searchProductsBySku(value.sku).then(found=>{
       const row=found.find(item=>item.id===value.id);
       if(row){setSkuOptions(found);void pickProduct(row.id,row);}
     });
   }catch{sessionStorage.removeItem('keyword-planning:selected-product');}
 // Restore once on mount; product and listing are revalidated by the live APIs.
 // eslint-disable-next-line react-hooks/exhaustive-deps
 },[]);
 const loadFile=async(file:File)=>{
   if(!step02Unlocked){message.warning('请先点击确认商品');return}
   if(!/\.xlsx$/i.test(file.name)){
     message.error('后端原始文件归档仅支持 xlsx，请先保存为 xlsx');return;
   }
   const ticket=confirmationSeq.current;
   setBusy(true);
   try{
     const book=await parseSellerSprite(file);
     if(ticket!==confirmationSeq.current)return; // Discard stale async result.
     setStaged(book);setSourceFile(file);
     setStoredUpload(null);
     setConfirmed(false);
     setAsins(old=>old.trim()?old:book.asins.slice(0,5).join('\n'));
     message.success(`真实 Excel 已导入：${book.keywords.length} 条关键词`);
     if(book.warnings.length)message.warning('部分来源字段缺失，请查看导入摘要');
   }catch(err){
     if(ticket===confirmationSeq.current)message.error(err instanceof Error?err.message:'解析失败');
   }finally{
     if(ticket===confirmationSeq.current)setBusy(false);
   }
 };

 const reloadAiTasks=async()=>{
   if(!sourceAccountRef)return;
   setAiTasksLoading(true);
   try{setAiTasks(await listKeywordAiJobs(sourceAccountRef));}
   catch{message.error('任务状态读取失败，请检查权限和连接');}
   finally{setAiTasksLoading(false);}
 };
 useEffect(()=>{
   if(!sourceAccountRef||!aiTasksOpen)return;
   void reloadAiTasks();
   const timer=window.setInterval(()=>{void listKeywordAiJobs(sourceAccountRef).then(setAiTasks).catch(()=>{})},4000);
   return()=>window.clearInterval(timer);
 },[sourceAccountRef,aiTasksOpen]);
 const openAiTaskResult=async(job:KeywordAiJob,target:'keywords'|'plan'|'listing')=>{
   if(job.product_id!==sku.id){message.info('请先选择对应 SKU，再打开此任务结果');return;}
   if(!job.run_id||!sourceAccountRef){message.warning('分析结果尚未生成');return;}
   try{
     const run=await getKeywordRun(job.run_id,sourceAccountRef);
     const result=await loadAllRunKeywords(job.run_id,sourceAccountRef);
     installServerRun(sku.id,run,result);setActiveRunId(run.run_id);
     setEditing(false);setResultsTab(target);setAiTasksOpen(false);
   }catch{message.error('读取任务结果失败');}
 };
 const openFacts=()=>{if(!productConfirmed)return message.warning('请先在步骤 01 点击确认商品');if(!ready)return message.warning('请先上传 Excel 并满足 ASIN 数量要求');setConsent(false);setFactOpen(true)};
 const confirmParameters=async()=>{
   if(!ready||!consent||!parametersComplete||!sourceAccountRef){
     message.warning('请先补齐商品事实、账户和规则参数');return;
   }
   if(!decodoSnapshotId||!walmartSource){
     if(factId&&sourceFile){
       setBusy(true);
       try{
         const upload=await uploadKeywordSourceXlsx(sourceFile,sourceAccountRef,sku.id,factId);
         if(upload.status!=='parsed')throw new Error('EXCEL_SOURCE_REVIEW_REQUIRED');
         setStoredUpload({id:upload.upload_id,filename:sourceFile.name,rows:upload.source_rows});
         setConfirmed(true);setFactOpen(false);message.success('Excel 原件与商品事实已保存');
       }catch(error){message.error(error instanceof Error?error.message:'Excel 保存失败');}
       finally{setBusy(false);}
       return;
     }
     if(factId){setConfirmed(true);setFactOpen(false);return;}
     message.error('缺少已保存 Walmart 来源快照，无法确认');return;
   }
   const original:Record<string,string>={
     title:walmartSource.title,item_type:walmartSource.category_path.at(-1)??'',
     brand:walmartSource.brand??'',material:'',color:'',pack:'',size:'',structure:'',use:'',owner:'',
   };
   const attr=(...names:string[])=>{
     const key=Object.keys(walmartSource.attributes).find(k=>names.some(n=>k.trim().toLowerCase()===n.toLowerCase()));
     return key?walmartSource.attributes[key].trim():'';
   };
   original.material=attr('Material');original.color=attr('Color');
   original.pack=attr('Pack Size','Pack Quantity','Package Quantity');
   original.size=attr('Dimensions','Product Dimensions','Size');
   original.structure=attr('Included Components','Package Contents');
   original.use=attr('Recommended Uses','Recommended Uses for Product','Usage','Uses');
   const values:Record<string,string>={title:facts.title,item_type:facts.itemType,
     brand:facts.brand,material:facts.material,color:facts.color,pack:facts.pack,
     size:facts.size,structure:facts.structure,use:facts.use,owner:facts.owner};
   let factSaved=false;
   setBusy(true);
   try{
     const receipt=await confirmStoredKeywordFacts({source_account_ref:sourceAccountRef,
       product_id:sku.id,item_id:itemId,decodo_snapshot_id:decodoSnapshotId,
       fields:Object.fromEntries(Object.entries(values).map(([key,value])=>[key,{
         value:value.trim(),source:key!=='owner'&&value.trim()===original[key]?'walmart':'operator',
       }])),
       risk_boundary_mode:facts.forbidden.trim()?'provided':'none',
       risk_boundary_acknowledged:true,semantic_phrases:[]});
     setFactId(receipt.product_fact_snapshot_id);factSaved=true;
     if(sourceFile){
       const upload=await uploadKeywordSourceXlsx(sourceFile,sourceAccountRef,sku.id,receipt.product_fact_snapshot_id);
       if(upload.status!=='parsed')throw new Error('EXCEL_SOURCE_REVIEW_REQUIRED');
       setStoredUpload({id:upload.upload_id,filename:sourceFile.name,rows:upload.source_rows});
     }
     setConfirmed(true);setFactOpen(false);
     message.success('商品事实与 Excel 原件已保存，可开始分析');
   }catch{message.error(factSaved?'商品事实已保存，但 Excel 原件未保存；请重试确认参数':'商品事实未保存；请核对来源、账户权限和必填字段');}
   finally{setBusy(false);}
 };
 const doAnalysis=async()=>{
   if(!productConfirmed||!confirmed||!ready||!staged||!storedUpload||!factId||!sourceAccountRef||!parametersComplete)return message.warning('请先保存商品事实、上传来源文件并完成参数核对');
   if(busy)return;
   const ticket=confirmationSeq.current,targetSku=sku.id,asinsForRun=[...parsedAsins.valid];
   setBusy(true);
   try{
     const source=await getKeywordSourceState(targetSku,sourceAccountRef);
     if(ticket!==confirmationSeq.current)return;
     const stored=new Set(source.item_id===itemId?source.asin_references:[]);
     const missing=asinsForRun.filter(asin=>!stored.has(asin));
     if(missing.length){
       const output=await researchAmazonAsins(missing,targetSku);
       if(ticket!==confirmationSeq.current)return;
       if(output.failures.length||output.items.length!==missing.length){
         message.error(`Amazon 采集部分失败：${output.failures.join('、')||'数量不一致'}；本次未执行评分。重试后再分析`);return;
       }
       if(output.items.some(doc=>!doc.snapshot_id||!doc.verified)){
         message.error('Amazon 来源未保存或未验证，本次未分析');return;
       }
       for(const doc of output.items){
         await importStoredAsin({source_account_ref:sourceAccountRef,product_id:targetSku,
           asin:doc.asin,decodo_snapshot_id:doc.snapshot_id!});
       }
     }
     const published=await loadEffectiveRule(sourceAccountRef);
     if(!published)throw new Error('PUBLISHED_RULE_REQUIRED');
     const serverRule=displayRule(published.version);
     if(!serverRule)throw new Error('RULE_CONFIGURATION_INVALID');
     useKeywordStore.setState({rules:serverRule});
     setCurrentRuleVersionId(published.version.version_id);
     const input={source_account_ref:sourceAccountRef,product_id:targetSku,item_id:itemId,
       product_fact_snapshot_id:factId,rule_version_id:published.version.version_id,
       upload_file_id:storedUpload.id,selected_asins:asinsForRun};
     const preflight=await preflightKeywordAnalysis(input);
     if(!preflight.can_create_review_run)throw new Error(preflight.review_reason_codes.join('、'));
     await submitKeywordAiJob({...input,request_key:crypto.randomUUID()});
     if(ticket!==confirmationSeq.current)return;
     setFactOpen(false);setAiTasksOpen(true);
     message.success('AI 分析任务已提交，可以继续操作其他 SKU');
     void reloadAiTasks();
   }catch(error){if(ticket===confirmationSeq.current)message.error(error instanceof Error?error.message:'分析未完成，请检查来源、规则与权限');}
   finally{if(ticket===confirmationSeq.current)setBusy(false);}
 };
 const openTranslation=(k:MarketKeyword)=>{let value=k.translation||'';Modal.confirm({title:`修改中文翻译 · ${k.term}`,content:<Input.TextArea rows={3} defaultValue={value} onChange={e=>{value=e.target.value}}/>,okText:'保存',onOk:async()=>{
   if(!sourceAccountRef||!itemId)throw new Error('请先选择账户与 Listing');
   try{
     const result=await updateKeywordTranslation(sku.id,k.id,sourceAccountRef,itemId,value);
     updateTranslation(k.id,result.translation??'');message.success('翻译已保存');
   }catch(error){message.error(error instanceof Error?error.message:'翻译保存失败');throw error;}
 }})};

 const downloadAll=()=>{
   if(!activeRunId||!sourceAccountRef)return message.warning('请先加载已保存的分析批次');
   void downloadKeywordInternalWorkbook(activeRunId,sourceAccountRef).catch(()=>message.error('五表下载失败，请检查分析批次和权限'));
 };
 const openRun=async(run:KeywordRun)=>{
   if(!sourceAccountRef)return;
   try{
     const results=await loadAllRunKeywords(run.run_id,sourceAccountRef);
     installServerRun(sku.id,run,results);setActiveRunId(run.run_id);
     setEditing(false);setHistoryOpen(false);
   }catch{message.error('历史分析读取失败，原结果未修改');}
 };
 const loadHistoryPage=async(pageNumber:number)=>{
   if(!sku.id||!sourceAccountRef)return;
   const ticket=confirmationSeq.current;
   try{
     const response=await listKeywordRuns(sku.id,sourceAccountRef,20,(pageNumber-1)*20);
     if(ticket!==confirmationSeq.current)return;
     setServerRuns(response.items);setHistoryTotal(response.total);setHistoryPage(pageNumber);
     setHistoryError('');
   }catch(error){if(ticket===confirmationSeq.current)setHistoryError(keywordReadError('history',error));}
 };
 const makeListing=async()=>{
   if(!analyzed||!activeRunId||!sourceAccountRef)return message.warning('请先加载已保存的分析结果');
   try{
     const response=await backendRequest<{title:string;features:string;description:string}>('/api/ai-runtime/listing/draft',{
       method:'POST',body:JSON.stringify({source_account_ref:sourceAccountRef,run_id:activeRunId}),
     });
     setDraft(response.data);
     message.success('GPT-6 Luna 已生成 Listing 草稿，请核对商品事实后再使用');
   }catch{message.error('AI Listing 生成失败，请检查服务配置、模型额度和该分析版本');}
 };
 const keywordCol:ProColumns<KeywordRow>={title:'关键词 / 中文翻译',key:'term',width:260,render:(_,r)=><><KeywordTextCell keyword={r.keyword} onEdit={openTranslation}/><div className="kw-v2-muted">{r.keyword.source==='excel'?'Excel':'人工新增'} · {r.keyword.root}</div></>};

 const suggestedBid=(r:KeywordRow):string=>r.entry.suggestedBid?`$${r.entry.suggestedBid}`:'—';

 const noSelectionReason=(r:KeywordRow):string=>r.entry.nonSelectionReason||'—';
 const decisionCols:ProColumns<KeywordRow>[]=[
   {
     title:'关键词 / 中文',
     key:'term',
     width:250,
     fixed:'left',
     render:(_,r)=>
       <KeywordTextCell
         keyword={r.keyword}
         onEdit={openTranslation}
       />
   },
   {
     title:'关键词类型',
     key:'keywordType',
     width:135,
     render:(_,r)=>{
       const value=r.entry.keywordType;

       return value
         ?<Text>{value}</Text>
         :<Text type="secondary">待分类</Text>;
     }
   },
   {
     title:'页面承接',
     key:'pageCoverage',
     width:150,
     render:(_,r)=>{
       const value=r.entry.pageCoverage||'页面看不出来';

       return <Text
         type={value==='页面看不出来'?'secondary':undefined}
       >{value}</Text>;
     }
   },
   {
     title:'核心词根',
     key:'root',
     width:130,
     render:(_,r)=>r.entry.coreRoot||'—'
   },
   {
     title:'词质说明',
     key:'reason',
     width:230,
     render:(_,r)=><>
       <div
         className="kw-v2-ellipsis"
         title={r.entry.qualityNote||r.entry.reason}
       >
         {r.entry.qualityNote||r.entry.reason||'待分析'}
       </div>
     </>
   },
   {
     title:'潜力分',
     key:'score',
     width:132,
     render:(_,r)=>{
       const score=r.entry.score;

       if(score==null)
         return <Text type="secondary">—</Text>;

       return <div style={{
         display:'flex',
         alignItems:'center',
         gap:7
       }}>
         <span style={{
           fontWeight:700,
           fontVariantNumeric:'tabular-nums',
           minWidth:26
         }}>
           {score}
         </span>
         <div style={{
           width:70,
           height:5,
           background:'#e8eef6',
           borderRadius:8,
           overflow:'hidden'
         }}>
           <div style={{
             width:`${Math.max(0,Math.min(100,score))}%`,
             height:'100%',
             background:'#1677ff',
             borderRadius:8
           }}/>
         </div>
       </div>;
     }
   },
   {
     title:'投放等级',
     key:'grade',
     width:105,
     align:'center',
     render:(_,r)=><Tag
       style={{margin:0}}
       color={
         r.entry.grade==='P0'?'blue':
         r.entry.grade==='P1'?'cyan':
         r.entry.grade==='P2'?'purple':
         r.entry.grade==='不投放'?'red':'gold'
       }
     >
       {r.entry.grade}
     </Tag>
   },
   {
     title:'Exact',
     key:'exact',
     width:76,
     align:'center',
     render:(_,r)=>r.entry.exact
       ?<span style={{
         color:'#16a34a',
         fontWeight:800,
         fontSize:19
       }}>✓</span>
       :<Text type="secondary">—</Text>
   },
   {
     title:'Broad',
     key:'broad',
     width:76,
     align:'center',
     render:(_,r)=>r.entry.broad
       ?<span style={{
         color:'#16a34a',
         fontWeight:800,
         fontSize:19
       }}>✓</span>
       :<Text type="secondary">—</Text>
   },
   {
     title:'建议出价($)',
     key:'suggestedBid',
     width:120,
     align:'right',
     render:(_,r)=><Text style={{
       fontVariantNumeric:'tabular-nums'
     }}>
       {suggestedBid(r)}
     </Text>
   },
   {
     title:'未入选原因',
     key:'notSelected',
     width:205,
     render:(_,r)=><span title={noSelectionReason(r)}>
       {noSelectionReason(r)}
     </span>
   }
 ];
 const marketCols:ProColumns<KeywordRow>[]=[keywordCol,
  {title:'ASIN 参考关联',key:'asin',width:135,render:(_,r)=>r.keyword.relatedAsins.length||'—'},
  {title:'月搜索量',key:'vol',width:120,render:(_,r)=>countText(r.keyword.monthlySearches)},
  {title:'月购买量',key:'buy',width:120,render:(_,r)=>countText(r.keyword.monthlyPurchases)},
  {title:'购买率（参考）',key:'rate',width:140,render:(_,r)=><PercentCell value={r.keyword.marketPurchaseRate==null?null:r.keyword.marketPurchaseRate*100}/>},
  {title:'PPC 参考',key:'ppc',width:120,render:(_,r)=><MoneyCell value={r.keyword.amazonPpc}/>},
  {title:'建议竞价范围',key:'range',width:150,render:(_,r)=>r.keyword.bidRange||'—'},
  {title:'广告竞品数',key:'sponsored',width:120,render:(_,r)=>countText(r.keyword.sponsoredCompetitors)},
  {title:'关联 SKU',key:'related',width:95,render:(_,r)=><Button type="link" size="small" onClick={()=>setCompare(r.keyword)}>{allAssoc(r.keyword.id).length} SKU</Button>},
  {title:'资料依据',key:'evidence',width:110,render:(_,r)=><Button type="link" size="small" onClick={()=>setDetail(r)}>查看来源与评分</Button>}];
 const completed=existing||analyzed;
 const step=completed?3:!step02Unlocked?0:parsedAsins.valid.length<rules.asin.min?1:!staged?2:3;
 return <PageShell page={page}>
  <div className={`kw-v2-page ${analyzed && panel==='workspace'?'kw-v2-results-only':''}`}>

<div className="kw-v2-pagehead">
  <div className="kw-v2-pagehead__title">
    <h2>{panel==='rules'?'规则配置':'新品关键词投放'}</h2>
    <div className="kw-v2-pagehead__subtitle">
      先选 SKU；已有分析结果可直接查看词库。新品按商品事实、竞品文案及市场数据进行筛选。
    </div>
  </div>
  <div className="kw-v2-pagehead__actions">{panel==='rules'?<Button onClick={()=>setPanel('workspace')}>返回关键词投放</Button>:(<Space size={6} wrap><Tag color="blue">生效规则 V{rules.version}.0</Tag><Button onClick={()=>setAiTasksOpen(true)}>AI 任务</Button><Button icon={<HistoryOutlined/>} onClick={()=>setHistoryOpen(true)}>分析历史</Button><Button onClick={()=>{const wb=XLSX.utils.book_new();XLSX.utils.book_append_sheet(wb,XLSX.utils.aoa_to_sheet([['关键词','关键词翻译','月搜索量','月购买量','购买率','PPC竞价','相关ASIN']]),'Keyword');XLSX.writeFile(wb,'关键词导入模板.xlsx')}}>下载关键词模板</Button><Button icon={<SettingOutlined/>} onClick={()=>setPanel('rules')}>规则配置</Button></Space>)}</div>
</div>

   {panel==='rules'?<KeywordRulesPanel sourceAccountRef={sourceAccountRef}/>:<>
   {editing&&hasAnalysis?<div className="kw-v2-resume"><Button onClick={()=>{setEditing(false);setStaged(null)}}>取消修改，返回上次分析结果</Button></div>:null}
   <Card size="small" className="kw-v2-flow"><Steps size="small" current={step} items={[{title:'选择 SKU'},{title:`参考 ASIN（≥${rules.asin.min}）`},{title:'关键词数据'},{title:'确认并分析'}]}/><Text type="secondary" className="kw-v2-small">SKU 为词库主键；店铺及 Item ID 不拆分词库。</Text></Card>
   <div className="kw-v2-setup">
    <Card size="small" title={<Space><Tag color="blue">01</Tag>选择目标 SKU</Space>} extra={<Space size={6}><Tag color="blue">必填</Tag><Tag color={productConfirmed?(walmartError?'orange':'green'):productPending?'processing':'default'}>{productConfirmed?(walmartError?'人工核对':'已采集确认'):productPending?'正在采集':'待确认'}</Tag></Space>}>
      <Text strong>SKU / 产品名称 *</Text>
      <Select showSearch allowClear filterOption={false} className="kw-v2-block"
        labelInValue value={sku.id?{value:sku.id,label:`${sku.sku} · ${sku.name}`}:undefined} searchValue={skuSearch}
        placeholder="搜索或选择产品管理 SKU" loading={skuLoading} onSearch={handleSkuSearch}
        onClear={()=>{skuQueryRef.current='';clearSelectedSku();setSkuSearch('');setSkuOptions(initialSkuRef.current);setSkuError('')}}
        onChange={choice=>{if(choice?.value)void pickProduct(String(choice.value))}}
        notFoundContent={skuLoading?'搜索中':skuError||'未找到匹配的 SKU'}
        options={skuDropdownRows.map(p=>({value:p.id,label:`${p.sku} · ${p.productName||'未命名'}`}))}/>
      {skuError||ruleError||sourceError||historyError?<Alert type="error" showIcon message={[skuError,ruleError,sourceError,historyError].filter(Boolean).join('；')} style={{marginTop:8}}/>:null}
      <div className="kw-v2-snapshot"><div className="kw-v2-thumb">▦</div><div className="kw-v2-grow"><Text strong>{sku.name}</Text><div className="kw-v2-muted">{sku.sku} · {facts.material} · {facts.pack} · {sku.storeIds.length} 个已关联店铺</div></div><Tag color="blue">来自产品管理</Tag></div>
      <div className="kw-v2-itemid-section">
       <div className="kw-v2-itemid-heading">
         <Text strong>商品事实来源 Walmart Item ID *</Text>
         <Button size="small" disabled={!sku.id} onClick={()=>{
           invalidateProductConfirmation();
           setItemManual(value=>!value);
           setItemId('');
           setSelectedListing(null);
         }}>
           {itemManual?'选择 Listing Item ID':'手动填写 Item ID'}
         </Button>
       </div>
       <div className="kw-v2-itemid-picker">
       {!itemManual?<Select showSearch optionFilterProp="label" className="kw-v2-block" disabled={!sku.id||listingLoading} loading={listingLoading}
         placeholder={listingLoading?'查询 Listing 中':'请选择 Listing 对应的 Item ID'} value={!itemManual&&selectedListing?`${selectedListing.listing.id}:${selectedListing.listing.productId}`:undefined}
         onChange={value=>{const found=listingCandidates.find(x=>`${x.listing.id}:${x.listing.productId}`===value);
           if(!found)return;invalidateProductConfirmation();setSelectedListing(found);setItemId(found.listing.productId);setItemManual(false);sessionStorage.setItem('keyword-planning:selected-listing',found.listing.id)}}
         options={listingCandidates.map(c=>({value:`${c.listing.id}:${c.listing.productId}`,label:`${c.listing.productId} · ${c.listing.store} · ${c.listing.msku}`}))}/>:<Input
         className="kw-v2-block"
         value={itemId}
         placeholder="请输入数字形式的 Walmart Item ID"
         maxLength={20}
         onChange={e=>{
           invalidateProductConfirmation();
           const next=e.target.value.replace(/\D/g,'');
           setItemId(next);
           const matches=listingCandidates.filter(candidate=>candidate.listing.productId===next);
           if(matches.length===1)setSelectedListing(matches[0]);
         }}
       />}

       {listingError?<Alert type="warning" showIcon style={{marginTop:8}} message={listingError}/>:null}
       {!listingLoading&&sku.id&&!listingCandidates.length?<div className="kw-v2-muted">未检索到可确认的 SKU / MSKU Listing；请手动输入并核对 Item ID。</div>:null}
       {listingCandidates.some(x=>x.match!=='sku_exact')?<div className="kw-v2-muted">MSKU 模糊结果仅为候选，请核对店铺、商品及 Item ID 后主动选择。</div>:null}
       </div>

      </div>


      <div style={{display:'flex',justifyContent:'space-between',alignItems:'center',flexWrap:'wrap',gap:12,marginTop:14,paddingTop:12,borderTop:'1px solid #f0f0f0'}}>
        <Text type="secondary" className="kw-v2-small">{productConfirmed?(walmartError?'商品已选择，可以继续操作':'Walmart 已验证，可以继续操作'):productPending?'Walmart 后台采集中，请直接填写 ASIN 和上传 Excel':'确认商品后立即解锁后续步骤，Walmart 在后台采集'}</Text>
        <Button type={productConfirmed?'default':'primary'} disabled={!canConfirmProduct} loading={confirmingProduct} onClick={()=>void confirmProduct()}>{productConfirmed?'重新确认商品':'确认商品'}</Button>
       </div>

     </Card>
     <Card size="small" title={<Space><Tag color="purple">02</Tag>Amazon 参考商品</Space>} extra={<Space size={6}><Tag color="blue">必填</Tag>{!step02Unlocked?<Tag>待步骤 01 确认</Tag>:productPending?<Tag color="processing">Walmart 采集中</Tag>:null}</Space>}>
     <div className="kw-v2-small">每行一个 ASIN，至少 {rules.asin.min} 个有效 ASIN，建议 {rules.asin.recommend}–{rules.asin.max} 个；只使用 Title、Key Features、Description，不分析图片。</div>
     <Input.TextArea className="kw-v2-asin-input" rows={5} disabled={!step02Unlocked} value={asins} onChange={e=>{setAsins(e.target.value);setAmazonEvidence([]);setConfirmed(false)}} placeholder={'B0XXXXXXXX\nB0YYYYYYYY\nB0ZZZZZZZZ'}/>
      {!step02Unlocked?<Alert className="kw-v2-quiet-alert" type="warning" showIcon message="请先点击确认商品"/>:productPending?<Alert className="kw-v2-quiet-alert" type="info" showIcon message="Walmart 正在采集；你可以先填写 ASIN，最终核对会等待数据返回"/>:<Alert className="kw-v2-quiet-alert" type="info" showIcon message="开始分析时将采集 Amazon 文案并执行规则评分"/>}
    </Card>
   </div>
   <Card size="small" className="kw-v2-section" title={<Space><Tag color="blue">03</Tag>关键词数据</Space>} extra={<Tag>{existing?'已有 SKU 词库':'新品 · Excel 上传'}</Tag>}>
    {existing?<Alert showIcon type="info" message="当前 SKU 已有关键词词库" description={`已收录 ${rows.length} 个关键词。建议直接进入词库查看或导出，不重复上传或重建。`} action={<Space wrap><Button onClick={()=>navigate('/ads/keyword-library',{state:{skuId:sku.id}})}>打开词库</Button><Button type="primary" onClick={downloadAll}>直接下载词库</Button><Button onClick={()=>{setEditing(true);setConfirmed(false);setStaged(null)}}>导入新 Excel / 重新分析</Button></Space>}/>:<>
       {!step02Unlocked?<Alert type="warning" showIcon style={{marginBottom:10}} message="请先点击确认商品"/>:null}
      <Upload.Dragger showUploadList={false} accept=".xlsx" disabled={busy||!step02Unlocked} beforeUpload={file=>{void loadFile(file);return false}}><InboxOutlined className="kw-v2-upload-icon"/><div>导入你的卖家精灵关键词 Excel（真实文件解析）</div><div className="kw-v2-muted">支持 xlsx · 文件最大 12MB；上传后预览，不直接生成投放结果</div></Upload.Dragger>
      {staged?<><div className="kw-v2-filemeta"><Tag icon={<FileExcelOutlined/>} color="green">{staged.fileName}</Tag>{staged.keywords.length} 个去重词 · 词根 {staged.roots.length} · 待翻译 {staged.keywords.filter(k=>!k.translation).length}</div><ProTable rowKey="id" size="small" search={false} options={false} toolBarRender={false} pagination={false} columns={[{title:'关键词',dataIndex:'term'},{title:'中文释义',dataIndex:'translation',render:(_,r)=>r.translation||'待翻译'},{title:'月搜索量',dataIndex:'monthlySearches'},{title:'PPC',dataIndex:'amazonPpc'}]} dataSource={staged.keywords.slice(0,5)}/>{staged.warnings.length?<Alert type="warning" showIcon message={staged.warnings.join('；')}/>:null}</>:storedUpload?<div className="kw-v2-filemeta"><Tag icon={<FileExcelOutlined/>} color="green">{storedUpload.filename}</Tag>{storedUpload.rows} 行原始来源已保存；重新分析请重新选择文件</div>:null}
     </>}
   </Card>
   {!existing?<Card size="small" className="kw-v2-preflight"><Space><Button onClick={openFacts} disabled={!ready} loading={waitingForWalmart}>核对商品信息</Button>{waitingForWalmart?<Text type="secondary">正在获取 Walmart 商品资料，完成后自动允许核对</Text>:null}<Button type="primary" disabled={!ready||!confirmed||!parametersComplete||busy} loading={busy} onClick={()=>void doAnalysis()}>开始分析</Button></Space></Card>:null}
   {analyzed&&rows.length?<div className="kw-v2-results">
    <div className="kw-v2-results-toolbar">
      <Space wrap><Tag color="blue">SKU：{sku.sku}</Tag><Text type="secondary">来源：{lastAnalysis?.sourceFile||'已保存来源'}</Text><Tag color="orange">后端冻结分析 · 证据不足的词待人工复核 · 无广告实绩</Tag></Space>
      <Space wrap><Button onClick={()=>{setEditing(true);setStaged(null);setConfirmed(false);setConsent(false)}}>修改资料 / 重新导入</Button><Button onClick={()=>navigate('/ads/keyword-library',{state:{skuId:sku.id}})}>查看词库</Button></Space>
    </div>
    <div className="kw-v2-stats"><Metric symbol="⌕" label="分析关键词" value={rows.length} hint="SKU 内去重后"/><Metric symbol="✓" label="Exact 精准" value={`${rows.filter(x=>x.entry.exact).length} / ${rules.limits.exact}`} hint="P0 → P1 → P2 补位"/><Metric symbol="⌘" label="Broad 广泛" value={`${rows.filter(x=>x.entry.broad).length} / ${rules.limits.broad}`} hint={`核心词根 ≤${rules.limits.roots}`} /><Metric symbol="!" label="待复核 / 风险" value={rows.filter(x=>['复查','候选复查','不投放','品牌等级'].includes(x.entry.grade)).length} hint="硬风险优先隔离"/></div>
    <Card size="small" className="kw-v2-resultcard">
     <div className="kw-v2-tabhead"><Tabs activeKey={resultsTab} onChange={x=>setResultsTab(x as ResultsTab)} items={[{key:'keywords',label:`关键词筛选 ${rows.length}`},{key:'plan',label:'投放方案'},{key:'listing',label:'Listing 文案'}]}/><Tag color="orange">已保存的后端分析 · 非广告执行</Tag></div>
     {resultsTab==='keywords'?<>
      <div className="kw-v2-subtabs"><Space><Button type={keywordView==='decision'?'primary':'default'} size="small" onClick={()=>setKeywordView('decision')}>投放决策</Button><Button type={keywordView==='market'?'primary':'default'} size="small" onClick={()=>setKeywordView('market')}>市场与竞品数据</Button></Space></div>
      <div className="kw-v2-filters"><Input.Search placeholder="搜索关键词 / 词根 / 中文" allowClear className="kw-v2-search" value={query} onChange={e=>setQuery(e.target.value)}/><Select value={filter} onChange={setFilter} style={{width:150}} options={['全部','P0','P1','P2','品牌等级','候选复查','复查','不投放'].map(x=>({value:x,label:x}))}/><Select value={placement} onChange={setPlacement} style={{width:150}} options={[{value:'all',label:'全部投放状态'},{value:'exact',label:'进入 Exact'},{value:'broad',label:'进入 Broad'},{value:'none',label:'未进入投放'}]}/><Button onClick={()=>{setQuery('');setFilter('全部');setPlacement('all')}}>重置筛选</Button><Button icon={<TranslationOutlined/>} disabled title="自动翻译服务尚未接入；可在关键词下方点击编辑人工填写中文">批量翻译（待接入）</Button></div>
      <ReportTableShell label="关键词分析结果"><ProTable<KeywordRow> rowKey={r=>r.keyword.id} size="small" search={false} options={false} toolBarRender={false} columns={keywordView==='decision'?decisionCols:marketCols} dataSource={filtered} pagination={{pageSize:10,showSizeChanger:true,pageSizeOptions:[10,20,50]}} scroll={{x:keywordView==='decision'?1580:1460,y:430}}/></ReportTableShell>
     </>:null}
     {resultsTab==='plan'?<>
      <Alert type="warning" showIcon message="下面是已保存分析的内部投放候选；不是 Walmart 官方出价，也不会执行广告。"/>
      <div className="kw-v2-plan-stats"><Metric symbol="E" label="Exact 计划词" value={rows.filter(r=>r.entry.exact).length} hint="已保存分析"/><Metric symbol="B" label="Broad 计划词" value={rows.filter(r=>r.entry.broad).length} hint="已保存分析"/><Metric symbol="$" label="手动 Bid" value={dollarText(rules.bid.exact)} hint="本地规则参数"/><Metric symbol="$" label="自动 Bid" value={dollarText(rules.bid.auto)} hint="本地规则参数"/></div>
      <div className="kw-v2-plan-layout"><Card size="small" title="本次广告执行目标"><Text strong>店铺 / 账号</Text><Select className="kw-v2-block" value={selectedListing?.listing.store} disabled options={selectedListing?[{label:selectedListing.listing.store,value:selectedListing.listing.store}]:[]}/><div className="kw-v2-muted">当前已选择 Item ID：{itemId||'未选择'}{selectedListing?` · ${selectedListing.listing.store}`:''}</div><Divider/><Text strong>手动 Campaign</Text><div>{sku.sku?sku.sku+'-Manual':'—'}</div><Text strong>自动 Campaign</Text><div>{sku.sku?sku.sku+'-Auto':'—'}</div></Card><Card size="small" title="本地广告参数建议（未执行）"><Descriptions size="small" bordered column={1} items={[{key:'bid',label:'手动 Bid',children:currentRuleVersionId&&rules.bid.exact>0?dollarText(rules.bid.exact):'未配置'},{key:'auto',label:'自动 Bid',children:currentRuleVersionId&&rules.bid.auto>0?dollarText(rules.bid.auto):'未配置'},{key:'budget',label:'手动 / 自动每日预算',children:currentRuleVersionId&&rules.bid.dailyBudget>0?`$${rules.bid.dailyBudget} / $${rules.bid.dailyBudget}`:'未配置'},{key:'start',label:'美国开始日期',children:currentRuleVersionId?rulesDate||'未配置':'未加载'},{key:'rule',label:'分析规则版本',children:lastAnalysis?.ruleVersionId||currentRuleVersionId||'未加载'} ]}/></Card></div>
      <div className="kw-v2-exportbar"><Button onClick={()=>csvDownload(`${sku.sku}_分析报告.csv`,['关键词','中文','得分','等级','Exact','Broad','市场搜索量'],filtered.map(({entry:e,keyword:k})=>[k.term,k.translation||'',e.score,e.grade,e.exact?'Y':'N',e.broad?'Y':'N',k.monthlySearches]))}>下载分析报告 CSV</Button><Button type="primary" onClick={downloadAll}>下载五表分析 Excel</Button></div>
     </>:null}
     {resultsTab==='listing'?<div className="kw-v2-listing"><div className="kw-v2-listing-main"><Card size="small" title={`Title · ${effectiveDraft.title.length} 字符`} extra={<Button type="link" onClick={()=>void navigator.clipboard.writeText(effectiveDraft.title)}>复制</Button>}><Input.TextArea rows={3} value={effectiveDraft.title} onChange={e=>setDraft({...effectiveDraft,title:e.target.value})}/></Card><Card size="small" title={`Key Features · ${effectiveDraft.features.split('\n').filter(Boolean).length} / 5 条`} extra={<Button type="link" onClick={()=>void navigator.clipboard.writeText(effectiveDraft.features)}>复制</Button>}><Input.TextArea rows={6} value={effectiveDraft.features} onChange={e=>setDraft({...effectiveDraft,features:e.target.value})}/></Card><Card size="small" title={`Description · ${effectiveDraft.description.length} 字符`} extra={<Button type="link" onClick={()=>void navigator.clipboard.writeText(effectiveDraft.description)}>复制</Button>}><Input.TextArea rows={5} value={effectiveDraft.description} onChange={e=>setDraft({...effectiveDraft,description:e.target.value})}/></Card></div><Card size="small" title="Listing 生成依据"><p className="kw-v2-muted">已核对的商品事实、风险词和当前候选关键词。根据已保存商品事实和关键词由 GPT-6 Luna 生成；输出需人工核对，不会自动发布。</p><Alert type="warning" message="模板英文文案必须人工核对，不能直接作为正式 Listing 发布"/><Divider/><Space wrap>{rows.filter(x=>x.entry.exact).slice(0,7).map(x=><Tag key={x.keyword.id}>{x.keyword.term}</Tag>)}</Space><Divider/><Button type="primary" block onClick={makeListing}>生成文案草稿</Button><Button block onClick={()=>{saveListing(sku.id,effectiveDraft);message.success('草稿已保存到当前浏览器会话')}}>保存当前草稿</Button><Button block onClick={()=>csvDownload(`${sku.sku}_Listing.csv`,['字段','文案'],[['Title',effectiveDraft.title],['Key Features',effectiveDraft.features],['Description',effectiveDraft.description]])}>导出 Listing 文案 CSV</Button></Card></div>:null}
    </Card>
   </div>:null}
   {!analyzed&&existing?<Empty description="该 SKU 已收录关键词。若需重新分析，请在词库中操作；本页按新品流程设计。"/>:null}
   </>}
  </div>
  <Modal open={factOpen} width={830} onCancel={()=>setFactOpen(false)} title="核对商品信息" okText="确认参数" okButtonProps={{disabled:!ready||!consent||!parametersComplete,loading:busy}} onOk={()=>{void confirmParameters()}}>

   {walmartError?
     <Alert
       type="warning"
       showIcon
       style={{marginBottom:12}}
       message="Walmart 资料获取失败，请核对并补全商品信息。"
     />:null}
   <div style={{
      display:'flex',
      alignItems:'center',
      justifyContent:'space-between',
      flexWrap:'wrap',
      gap:12,
      marginTop:12,
      marginBottom:16,
      width:'100%'
    }}>
      {([
        {label:'SKU',value:sku.sku},
        {label:'Item ID',value:itemId},
        {label:'店铺',value:listingStore||'手动填写'}
      ] as const).map(({label,value})=>(
        <div key={label} style={{
          display:'inline-flex',
          alignItems:'center',
          gap:8,
          padding:'6px 10px',
          border:'1px solid #e5e7eb',
          borderRadius:6,
          background:'#f9fafb',
          fontSize:13,
          maxWidth:'100%'
        }}>
          <span style={{color:'#8c8c8c',whiteSpace:'nowrap'}}>{label}</span>
          <span style={{
            fontWeight:600,
            color:'#262626',
            overflow:'hidden',
            textOverflow:'ellipsis',
            whiteSpace:'nowrap'
          }}>{value}</span>
        </div>
      ))}
      <Tag
        color={walmartError?'orange':'green'}
        style={{
          margin:0,
          padding:'5px 10px',
          borderRadius:6,
          fontSize:12,
          fontWeight:500
        }}
      >
        {walmartError?'人工核对':'✓ Walmart 已采集'}
      </Tag>
    </div>



   {missingRequired.length?<Alert
     showIcon
     type="warning"
     style={{marginBottom:12}}
     message={`还有 ${missingRequired.length} 项必填信息未满足：${missingRequired.join('、')}`}
   />:null}
   <div className="kw-v2-factgrid">
     {requiredProductFields.map(({key,label})=>
       <label key={key}>
         <span>{label} <Text type="danger">*</Text></span>
         <Input
           value={facts[key]}
           status={!filledFact(facts[key])?'error':undefined}
           placeholder={key==='use'?'请输入真实英文用途，多个用途用逗号分隔':`请核对并填写${label}`}
           onChange={e=>{
             setFacts(f=>({...f,[key]:e.target.value}));
             setConfirmed(false);
             setConsent(false);
           }}
         />
       </label>
     )}
     <label>
       <span>
         风险词 / 禁止方向
         <Text type="secondary" style={{fontSize:12}}>（选填）</Text>
       </span>
       <Input
         value={facts.forbidden}
         placeholder="无额外禁止方向可留空"
         onChange={e=>{
           setFacts(f=>({...f,forbidden:e.target.value}));
           setConfirmed(false);
           setConsent(false);
         }}
       />
     </label>
     {([
       {label:'Manual Bid（USD）',value:rules.bid.exact},
       {label:'Auto Bid（USD）',value:rules.bid.auto},
       {label:'手动每日预算',value:rules.bid.dailyBudget},
       {label:'自动每日预算',value:rules.bid.dailyBudget},
     ] as const).map(({label,value})=>
       <label key={label}>
         <span>{label}（规则配置）<Text type="danger">*</Text></span>
         <InputNumber
           className="kw-v2-block"
           disabled
           value={Number.isFinite(value)?value:null}
         />
       </label>
     )}
     <label>
       <span>Start Date（美国日期 · 规则配置）<Text type="danger">*</Text></span>
       <Input type="date" disabled value={rulesDate}/>
     </label>
   </div>
   <Checkbox checked={consent} onChange={e=>setConsent(e.target.checked)} style={{marginTop:14}}>我已核对 SKU、商品资料和至少 {rules.asin.min} 个 ASIN 编号；了解开始分析后会采集真实 Amazon 文案，规则评分仍需人工复核。</Checkbox>
  </Modal>

  <Drawer open={!!detail} title={`分析依据 · ${detail?.keyword.term||''}`} width={540} onClose={()=>setDetail(null)}><Alert type="warning" showIcon message="分数与等级来自已保存的后端分析；缺少可验证证据时保持待复核，不推断广告表现。"/><Descriptions bordered column={1} size="small" style={{marginTop:12}} items={detail?[{key:'score',label:'后端分析分数',children:detail.entry.score??'—'},{key:'grade',label:'投放等级',children:detail.entry.grade},{key:'reason',label:'商品匹配判断',children:detail.entry.reason},{key:'ppc',label:'Amazon PPC',children:dollarText(detail.keyword.amazonPpc)},{key:'purchase',label:'市场购买量',children:countText(detail.keyword.monthlyPurchases)},{key:'source',label:'来源',children:detail.keyword.source},{key:'root',label:'词根',children:detail.keyword.root},{key:'asins',label:'关联 ASIN（表格）',children:detail.keyword.relatedAsins.join('、')||'—'}]:[]}/></Drawer>
  <Drawer open={!!compare} title={`跨 SKU 关键词 · ${compare?.term||''}`} width={620} onClose={()=>setCompare(null)}><Alert type="info" message="每个 SKU 独立分析；这里只比较已加载的后端结果。"/><ProTable rowKey="skuId" pagination={false} search={false} options={false} toolBarRender={false} columns={[{title:'SKU',dataIndex:'skuId',render:(_,r)=>skus.find(s=>s.id===r.skuId)?.sku},{title:'得分',dataIndex:'score'},{title:'等级',dataIndex:'grade'},{title:'Exact',dataIndex:'exact',render:(_,r)=>r.exact?'✓':'—'},{title:'Broad',dataIndex:'broad',render:(_,r)=>r.broad?'✓':'—'}]} dataSource={compare?allAssoc(compare.id):[]}/></Drawer>
  <Drawer open={historyOpen} title="分析历史" width={600} onClose={()=>setHistoryOpen(false)}><Alert type="info" message="分析历史读取已保存批次；点击一行可恢复当时冻结的分析结果。"/><ProTable<KeywordRun> rowKey="run_id" pagination={{current:historyPage,pageSize:20,total:historyTotal,onChange:pageNumber=>{void loadHistoryPage(pageNumber)}}} search={false} options={false} toolBarRender={false} dataSource={serverRuns} onRow={run=>({onClick:()=>{void openRun(run)}})} columns={[{title:'SKU',dataIndex:'product_id',render:()=>sku.sku},{title:'日期',dataIndex:'created_at'},{title:'规则版本',dataIndex:'rule_version_id'},{title:'关键词数',dataIndex:'keyword_count'},{title:'来源文件',render:()=> '已保存来源'}]}/></Drawer>
  <Drawer open={aiTasksOpen} title="AI 分析任务" width={760} onClose={()=>setAiTasksOpen(false)}
    extra={<Button loading={aiTasksLoading} onClick={()=>void reloadAiTasks()}>刷新状态</Button>}>
    <Alert type="info" showIcon message="后台持续分析，无需保持当前 SKU 页面打开；AI 语义结果独立保存，不会改写原有表格评分。"/>
    <ProTable<KeywordAiJob> rowKey="id" search={false} options={false} toolBarRender={false}
      dataSource={aiTasks} pagination={{pageSize:8}} columns={[
        {title:'SKU',dataIndex:'product_id',render:(_,r)=>skus.find(x=>x.id===r.product_id)?.sku||r.product_id.slice(0,8)},
        {title:'提交人',dataIndex:'requested_by'},
        {title:'状态',dataIndex:'status',render:(_,r)=><Tag color={r.status==='succeeded'?'green':r.status==='running'?'blue':r.status==='failed'?'red':'default'}>{r.status}</Tag>},
        {title:'当前阶段',dataIndex:'phase'},
        {title:'AI 进度',render:(_,r)=>r.total?`${r.completed}/${r.total} 批 · ${r.progress}%`:`${r.progress}%`},
        {title:'操作',render:(_,r)=><Space size={4}>
          {r.run_id?<><Button type="link" size="small" onClick={()=>void openAiTaskResult(r,'keywords')}>关键词筛选</Button>
            <Button type="link" size="small" onClick={()=>void openAiTaskResult(r,'plan')}>投放方案</Button>
            <Button type="link" size="small" onClick={()=>void openAiTaskResult(r,'listing')}>Listing 文案</Button></>:null}
          {['queued','running'].includes(r.status)?<Button danger size="small" onClick={()=>void cancelKeywordAiJob(r.id,r.source_account_ref).then(()=>reloadAiTasks())}>取消</Button>:null}
        </Space>},
      ]}/>
  </Drawer>
 </PageShell>;
}
