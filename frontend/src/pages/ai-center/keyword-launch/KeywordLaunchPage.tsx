/* KW_SKU_LABEL_ITEMID_LAYOUT_20261022 */
/* KEYWORD_SKU_RESELECT_FIX_20261022 */
/* KEYWORD_SKU_INITIAL_PREFETCH_20261022 */
/* KEYWORD_PRODUCT_LISTING_API_LOCAL_20261022 */
/** V2 workspace aligned with the owner-provided 2026-10-22 interactive prototype.
 * Keyword suggestions are local rule calculations; no ad-performance API is connected; this page does not call external APIs.
 */
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
import {parseSellerSprite} from '@/features/keyword-planning/importWorkbook';
import type {MarketKeyword,SkuKeyword,SkuDefinition} from '@/features/keyword-planning/types';
import type {ProductManagementRow} from '@/pages/products/productManagementTypes';
import type {ListingCandidate} from '@/features/keyword-planning/keywordProductLookup';
import {canonicalSku,getProductFacts,preloadProductSkuOptions,searchListingsForSku,searchProductsBySku} from '@/features/keyword-planning/keywordProductLookup';
import {confirmWalmartFacts,researchAmazonAsins,type AmazonEvidence} from "@/api/decodoApi";
import './KeywordLaunchPage.css';
import {KeywordRulesPanel} from '@/pages/ai-center/keyword-rules/KeywordRulesPage';
import {KeywordV11LiveConsole} from '@/features/keyword-planning/components/KeywordV11LiveConsole';

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
function exportFiveSheets(name:string,records:KeywordRow[],facts:ProductFacts,manualBid:number,autoBid:number){
 const wb=XLSX.utils.book_new();
 const sheets:[string,(string|number|null)[][]][]=[
  ['01_最终投放总表', [['关键词','关键词中文意思','SKU','投放等级','潜力分','手动Exact','手动Broad','参考PPC','建议 Bid（本地规则）','运营判断'],...records.map(({entry:e,keyword:k})=>[k.term,k.translation||'待翻译',name,e.grade,e.score,e.exact?'是':'否',e.broad?'是':'否',k.amazonPpc,e.exact?manualBid:e.broad?autoBid:null,e.reason])]],
  ['02_词根与Broad拓展规则', [['关键词','词根（参考）','Broad','月搜索量','Amazon月购买量'],...records.filter(r=>r.entry.broad).map(({entry:e,keyword:k})=>[k.term,k.root,e.broad?'是':'否',k.monthlySearches,k.monthlyPurchases])]],
  ['03_风险词与不投放词', [['关键词','等级','风险或复核理由'],...records.filter(r=>r.entry.grade==='不投放'||r.entry.grade==='复查'||r.entry.grade==='候选复查'||r.entry.grade==='品牌等级').map(({entry:e,keyword:k})=>[k.term,e.grade,e.reason])]],
  ['04_投放建议_未执行', [['SKU','匹配方式','关键词','建议竞价（USD）','状态'],...records.filter(r=>r.entry.exact||r.entry.broad).flatMap(({entry:e,keyword:k})=>[...(e.exact?[[name,'Exact',k.term,manualBid,'未执行']]:[]),...(e.broad?[[name,'Broad',k.term,autoBid,'未执行']]:[])])]],
  ['05_Listing优化建议', [['字段','内容'],['Title',facts.title],['商品类型',facts.itemType],['材质',facts.material],['Pack',facts.pack],['用途',facts.use],['提示','根据用户上传文件和本地规则计算；不是 Walmart 官方 Bulk 上传模板']]],
 ];
 for(const [title,rows] of sheets)XLSX.utils.book_append_sheet(wb,XLSX.utils.aoa_to_sheet(rows),title);
 XLSX.writeFile(wb,`${name}_本地初筛五表.xlsx`);
}
function Metric({label,value,hint,symbol}:{label:string;value:string|number;hint:string;symbol:string}){return <div className="kw-v2-stat"><div className="kw-v2-stat-icon">{symbol}</div><div><div className="kw-v2-muted">{label}</div><strong>{value}</strong><div className="kw-v2-muted">{hint}</div></div></div>}

export default function KeywordLaunchPage({page}:{page:NavigationPage}){
 const [showLocalDraft,setShowLocalDraft]=useState(false);
 if (!showLocalDraft) return <PageShell page={page}>
   <Alert type="warning" showIcon message="正式工作区只读取后端持久化数据；D01–D08 未批准，分析仅供内部复核，不可上传 Walmart。" />
   <KeywordV11LiveConsole />
   <Button style={{marginTop:16}} onClick={()=>setShowLocalDraft(true)}>查看旧版本地草稿（不持久化）</Button>
 </PageShell>;
 return <LocalKeywordLaunchPage page={page} />;
}

function LocalKeywordLaunchPage({page}:{page:NavigationPage}){
 const navigate=useNavigate();
 const [panel,setPanel]=useState<'workspace'|'rules'>('workspace');
 const {skus,keywords,entries,staged,rules,analyses,setStaged,analyze,upsertProductSku,updateTranslation,listing,saveListing}=useKeywordStore();
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

 const [pendingSelection,setPendingSelection]=useState<ConfirmedSelection|null>(null);
 const [walmartError,setWalmartError]=useState(false);
 const [walmartEvidence,setWalmartEvidence]=useState<{
   title:string;
   description:string;
   attributes:string;
 }|null>(null);
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
 const [draft,setDraft]=useState<{title:string;features:string;description:string}|null>(null);
 const sku=skus.find(x=>x.id===skuId)||{id:'',sku:'',name:'',material:'',uses:[],storeIds:[],hasLibrary:false};
 const skuEntries=useMemo(()=>entries.filter(e=>e.skuId===sku.id),[entries,sku.id]);
 const rows=useMemo(()=>skuEntries.flatMap(e=>keywords[e.keywordId]?[{entry:e,keyword:keywords[e.keywordId]}]:[]),[skuEntries,keywords]);
 const existing=sku.hasLibrary&&rows.length>0&&!editing;
 const parsedAsins=useMemo(()=>parseAsins(asins),[asins]);
 const listingId=itemManual?null:selectedListing?String(selectedListing.listing.id):null;
 const listingStore=itemManual?null:selectedListing?.listing.store??null;
 const productConfirmed=Boolean(productConfirmation
   && productConfirmation.skuId===sku.id
   && productConfirmation.itemId===itemId
   && productConfirmation.mode===(itemManual?'manual':'listing')
   && productConfirmation.listingId===listingId
   && productConfirmation.store===listingStore);
 const productPending=Boolean(confirmingProduct&&pendingSelection&&pendingSelection.skuId===sku.id&&pendingSelection.itemId===itemId&&pendingSelection.mode===(itemManual?'manual':'listing')&&pendingSelection.listingId===listingId&&pendingSelection.store===listingStore);
 const step02Unlocked=productConfirmed||productPending;
 const canConfirmProduct=Boolean(sku.id)&&/^\d{1,20}$/.test(itemId)&&!listingLoading&&!confirmingProduct&&(itemManual||Boolean(selectedListing));
 // Confirmation of item identity and final analysis parameters are separate gates.
 const inputsComplete=step02Unlocked&&Boolean(staged)&&parsedAsins.invalid.length===0&&parsedAsins.valid.length>=rules.asin.min;
 const ready=productConfirmed&&inputsComplete;
 const rulesDate=rules.bid.startDate??'';
 const validDate=/^\d{4}-\d{2}-\d{2}$/.test(rulesDate)
   &&!Number.isNaN(Date.parse(rulesDate));
 const missingRequired=[
   ...requiredProductFields
     .filter(({key})=>!filledFact(facts[key]))
     .map(({label})=>label),
   ...(!Number.isFinite(rules.bid.exact)||rules.bid.exact<=0
     ?['Manual Bid']:[]),
   ...(!Number.isFinite(rules.bid.auto)||rules.bid.auto<=0
     ?['Auto Bid']:[]),
   ...(!Number.isFinite(rules.bid.dailyBudget)||rules.bid.dailyBudget<=0
     ?['每日预算']:[]),
   ...(!validDate?['Start Date（请在规则配置设置）']:[]),
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
   setPendingSelection(null);setConfirmingProduct(false);setWalmartError(false);setWalmartEvidence(null);

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
 const pickProduct=async(productId:string)=>{
   const row=skuDropdownRows.find(p=>p.id===productId)
     ||initialSkuRef.current.find(p=>p.id===productId)
     ||skuOptions.find(p=>p.id===productId);
   if(!row||!row.sku)return;
   const id=String(row.id),ticket=selectionSeq.current+1;
   const product:SkuDefinition={id,sku:row.sku,name:row.productName||row.sku,material:row.materialEn||row.materialCn||'',uses:[],storeIds:[],hasLibrary:false};
   upsertProductSku(product);switchSku(id);selectionSeq.current=ticket;
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
     if(exact.length===1){setSelectedListing(exact[0]);setItemId(exact[0].listing.productId);}
     // Ambiguous matches and all MSKU candidates must be confirmed by the operator.
     const fromDetail=detail.status==='fulfilled'?detail.value:null;
     upsertProductSku({...product,material:fromDetail?.materialEn||fromDetail?.materialCn||product.material,uses:(fromDetail?.usageEn||'').split(/[,;\n]+/).map(x=>x.trim()).filter(Boolean),storeIds:[...new Set(candidates.filter(x=>x.match==='sku_exact').map(x=>x.listing.store))]});
   }else setListingError('Listing 查询失败：不能认定无关联，请检查 API 或手动填写 Item ID');
   setListingLoading(false);
 };
 const loadFile=async(file:File)=>{
   if(!step02Unlocked){message.warning('请先点击确认商品');return}
   const ticket=confirmationSeq.current;
   setBusy(true);
   try{
     const book=await parseSellerSprite(file);
     if(ticket!==confirmationSeq.current)return; // Discard stale async result.
     setStaged(book);
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

 const openFacts=()=>{if(!productConfirmed)return message.warning('请先在步骤 01 点击确认商品');if(!ready)return message.warning('请先上传 Excel 并满足 ASIN 数量要求');setConsent(false);setFactOpen(true)};
 const doAnalysis=async()=>{
   if(!productConfirmed||!confirmed||!ready||!staged||!parametersComplete)return message.warning('请先确认商品并通过分析前参数核对');
   if(busy)return;
   const ticket=confirmationSeq.current,targetSku=sku.id,asinsForRun=[...parsedAsins.valid];
   setBusy(true);
   try{
     const output=await researchAmazonAsins(asinsForRun,targetSku);
     if(ticket!==confirmationSeq.current)return;
     // Do not silently claim full competitor coverage if any ASIN failed.
     if(output.failures.length||output.items.length!==asinsForRun.length){
       message.error(`Amazon 采集部分失败：${output.failures.join('、')||'数量不一致'}；本次未执行评分。重试后再分析`);return;
     }
     const normalize=(x:string)=>x.toLowerCase().replace(/\s+/g,' ').trim();
     const matched=(term:string,doc:AmazonEvidence)=>{
       const needle=normalize(term);
       return Boolean(needle)&&[doc.title,...doc.bullet_points,doc.description||'']
         .some(part=>normalize(part).includes(needle));
     };
     // Use verified live textual phrase matches, not imported ASIN identifiers,
     // for the existing rule engine's competitor-coverage component.
     setStaged({...staged,keywords:staged.keywords.map(k=>({...k,
       relatedAsins:output.items.filter(doc=>matched(k.term,doc)).map(doc=>doc.asin),
     }))});
     setAmazonEvidence(output.items);
     const n=analyze(targetSku,{facts:{itemType:facts.itemType,brand:facts.brand,material:facts.material,color:facts.color,pack:facts.pack,structure:facts.structure,use:facts.use,forbidden:facts.forbidden},walmart:walmartError?null:walmartEvidence});
     if(!n)return message.error('没有可显示的分析结果');
     setEditing(false);setResultsTab('keywords');setFactOpen(false);
     window.scrollTo({top:0,behavior:'smooth'});
     message.success(`已采集 ${output.completed} 个真实 Amazon 文案，并生成 ${n} 条规则分析结果`);
   }catch{if(ticket===confirmationSeq.current)message.error('Amazon 采集失败；未执行关键词分析，请检查后端和 Decodo 配置');}
   finally{if(ticket===confirmationSeq.current)setBusy(false);}
 };
 const openTranslation=(k:MarketKeyword)=>{let value=k.translation||'';Modal.confirm({title:`修改中文翻译 · ${k.term}`,content:<Input.TextArea rows={3} defaultValue={value} onChange={e=>{value=e.target.value}}/>,okText:'保存',onOk:()=>updateTranslation(k.id,value)})};

 const downloadAll=()=>exportFiveSheets(sku.sku,filtered,facts,rules.bid.exact,rules.bid.auto);
 const makeListing=()=>{if(!analyzed)return message.warning('请先完成关键词分析');const title=`${facts.title}, ${facts.pack} ${facts.material} for ${facts.use}`.replace(/\s+/g,' ').slice(0,180);const features=[`Organization: ${facts.itemType} for ${facts.use}.`,`Material: Made with ${facts.material}, ${facts.color}.`,`Pack: ${facts.pack}, ${facts.structure}.`,`Size: ${facts.size}; check dimensions before purchase.`,`Review compatibility, package contents and product details before ordering.`].join('\n');setDraft({title,features,description:`${facts.title}. ${facts.itemType}. Material: ${facts.material}; pack: ${facts.pack}; purpose: ${facts.use}. Verify all facts before publishing.`});message.info('仅生成待人工核对的模板草稿，非 AI 生成内容；请人工校对英语和商品事实')};
 const keywordCol:ProColumns<KeywordRow>={title:'关键词 / 中文翻译',key:'term',width:260,render:(_,r)=><><KeywordTextCell keyword={r.keyword} onEdit={openTranslation}/><div className="kw-v2-muted">{r.keyword.source==='excel'?'Excel':'人工新增'} · {r.keyword.root}</div></>};

 // 页面承接只使用本轮 Walmart 实际采集到的页面证据
 const suggestedBid=(r:KeywordRow):string=>{
   const grade=r.entry.grade;

   if(grade==='不投放')return '不建议出价';

   const range=(r.keyword.bidRange||'')
     .match(/\$?([0-9]+(?:\.[0-9]+)?)/g)
     ?.map(x=>Number(x.replace('$','')))||[];

   let bid:number;

   if(range.length>=2&&range[0]>0&&range[1]>=range[0]){
     const [low,high]=range;

     bid=grade==='P0'
       ?low+(high-low)*0.25
       :grade==='P1'
       ?low+(high-low)*0.1
       :low;

   }else if(
     r.keyword.amazonPpc!=null&&
     r.keyword.amazonPpc>0
   ){
     const ppc=r.keyword.amazonPpc;

     bid=ppc*(
       grade==='P0'||grade==='P1'?0.8:
       grade==='P2'?0.6:0.5
     );

   }else{
     bid=grade==='P0'?0.35:
       grade==='P1'?0.31:0.30;
   }

   return '$'+Math.max(0.30,bid).toFixed(2);
 };

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
  <div className="kw-v2-pagehead__actions">{panel==='rules'?<Button onClick={()=>setPanel('workspace')}>返回关键词投放</Button>:(<Space size={6} wrap><Tag color="blue">生效规则 V{rules.version}.0</Tag><Button icon={<HistoryOutlined/>} onClick={()=>setHistoryOpen(true)}>分析历史</Button><Button onClick={()=>{const wb=XLSX.utils.book_new();XLSX.utils.book_append_sheet(wb,XLSX.utils.aoa_to_sheet([['关键词','关键词翻译','月搜索量','月购买量','购买率','PPC竞价','相关ASIN']]),'Keyword');XLSX.writeFile(wb,'关键词导入模板.xlsx')}}>下载关键词模板</Button><Button icon={<SettingOutlined/>} onClick={()=>setPanel('rules')}>规则配置</Button></Space>)}</div>
</div>

   {panel==='rules'?<KeywordRulesPanel/>:<>
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
      {skuError?<Alert type="error" showIcon message={skuError} style={{marginTop:8}}/>:null}
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
           if(!found)return;invalidateProductConfirmation();setSelectedListing(found);setItemId(found.listing.productId);setItemManual(false)}}
         options={listingCandidates.map(c=>({value:`${c.listing.id}:${c.listing.productId}`,label:`${c.listing.productId} · ${c.listing.store} · ${c.listing.msku}`}))}/>:<Input
         className="kw-v2-block"
         value={itemId}
         placeholder="请输入数字形式的 Walmart Item ID"
         maxLength={20}
         onChange={e=>{
           invalidateProductConfirmation();
           setItemId(e.target.value.replace(/\D/g,''));
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
      <Upload.Dragger showUploadList={false} accept=".xlsx,.xls,.csv,.tsv" disabled={busy||!step02Unlocked} beforeUpload={file=>{void loadFile(file);return false}}><InboxOutlined className="kw-v2-upload-icon"/><div>导入你的卖家精灵关键词 Excel（真实文件解析）</div><div className="kw-v2-muted">支持 xlsx / xls / csv / tsv · 文件最大 12MB；上传后预览，不直接生成投放结果</div></Upload.Dragger>
      {staged?<><div className="kw-v2-filemeta"><Tag icon={<FileExcelOutlined/>} color="green">{staged.fileName}</Tag>{staged.keywords.length} 个去重词 · 词根 {staged.roots.length} · 待翻译 {staged.keywords.filter(k=>!k.translation).length}</div><ProTable rowKey="id" size="small" search={false} options={false} toolBarRender={false} pagination={false} columns={[{title:'关键词',dataIndex:'term'},{title:'中文释义',dataIndex:'translation',render:(_,r)=>r.translation||'待翻译'},{title:'月搜索量',dataIndex:'monthlySearches'},{title:'PPC',dataIndex:'amazonPpc'}]} dataSource={staged.keywords.slice(0,5)}/>{staged.warnings.length?<Alert type="warning" showIcon message={staged.warnings.join('；')}/>:null}</>:null}
     </>}
   </Card>
   {!existing?<Card size="small" className="kw-v2-preflight"><Space><Button onClick={openFacts} disabled={!ready} loading={waitingForWalmart}>核对商品信息</Button>{waitingForWalmart?<Text type="secondary">正在获取 Walmart 商品资料，完成后自动允许核对</Text>:null}<Button type="primary" disabled={!ready||!confirmed||!parametersComplete||busy} loading={busy} onClick={()=>void doAnalysis()}>开始分析</Button></Space></Card>:null}
   {analyzed&&rows.length?<div className="kw-v2-results">
    <div className="kw-v2-results-toolbar">
      <Space wrap><Tag color="blue">SKU：{sku.sku}</Tag><Text type="secondary">来源：{lastAnalysis?.sourceFile||'当前会话'}</Text><Tag color="orange">市场数据来自 Excel · 评分为本地规则计算（非 AI）· 无广告实绩</Tag></Space>
      <Space wrap><Button onClick={()=>{setEditing(true);setStaged(null);setConfirmed(false);setConsent(false)}}>修改资料 / 重新导入</Button><Button onClick={()=>navigate('/ads/keyword-library',{state:{skuId:sku.id}})}>查看词库</Button></Space>
    </div>
    <div className="kw-v2-stats"><Metric symbol="⌕" label="分析关键词" value={rows.length} hint="SKU 内去重后"/><Metric symbol="✓" label="Exact 精准" value={`${rows.filter(x=>x.entry.exact).length} / ${rules.limits.exact}`} hint="P0 → P1 → P2 补位"/><Metric symbol="⌘" label="Broad 广泛" value={`${rows.filter(x=>x.entry.broad).length} / ${rules.limits.broad}`} hint={`核心词根 ≤${rules.limits.roots}`} /><Metric symbol="!" label="待复核 / 风险" value={rows.filter(x=>['复查','候选复查','不投放','品牌等级'].includes(x.entry.grade)).length} hint="硬风险优先隔离"/></div>
    <Card size="small" className="kw-v2-resultcard">
     <div className="kw-v2-tabhead"><Tabs activeKey={resultsTab} onChange={x=>setResultsTab(x as ResultsTab)} items={[{key:'keywords',label:`关键词筛选 ${rows.length}`},{key:'plan',label:'投放方案'},{key:'listing',label:'Listing 文案'}]}/><Tag color="orange">本地规则初筛 · 非 AI 结果</Tag></div>
     {resultsTab==='keywords'?<>
      <div className="kw-v2-subtabs"><Space><Button type={keywordView==='decision'?'primary':'default'} size="small" onClick={()=>setKeywordView('decision')}>投放决策</Button><Button type={keywordView==='market'?'primary':'default'} size="small" onClick={()=>setKeywordView('market')}>市场与竞品数据</Button></Space></div>
      <div className="kw-v2-filters"><Input.Search placeholder="搜索关键词 / 词根 / 中文" allowClear className="kw-v2-search" value={query} onChange={e=>setQuery(e.target.value)}/><Select value={filter} onChange={setFilter} style={{width:150}} options={['全部','P0','P1','P2','品牌等级','候选复查','复查','不投放'].map(x=>({value:x,label:x}))}/><Select value={placement} onChange={setPlacement} style={{width:150}} options={[{value:'all',label:'全部投放状态'},{value:'exact',label:'进入 Exact'},{value:'broad',label:'进入 Broad'},{value:'none',label:'未进入投放'}]}/><Button onClick={()=>{setQuery('');setFilter('全部');setPlacement('all')}}>重置筛选</Button><Button icon={<TranslationOutlined/>} disabled title="自动翻译服务尚未接入；可在关键词下方点击编辑人工填写中文">批量翻译（待接入）</Button></div>
      <ReportTableShell label="关键词分析结果"><ProTable<KeywordRow> rowKey={r=>r.keyword.id} size="small" search={false} options={false} toolBarRender={false} columns={keywordView==='decision'?decisionCols:marketCols} dataSource={filtered} pagination={{pageSize:10,showSizeChanger:true,pageSizeOptions:[10,20,50]}} scroll={{x:keywordView==='decision'?1580:1460,y:430}}/></ReportTableShell>
     </>:null}
     {resultsTab==='plan'?<>
      <Alert type="warning" showIcon message="下面是本地规则广告方案；不是 Walmart 官方出价，也不会执行广告。"/>
      <div className="kw-v2-plan-stats"><Metric symbol="E" label="Exact 计划词" value={rows.filter(r=>r.entry.exact).length} hint={`上限 ${rules.limits.exact}`}/><Metric symbol="B" label="Broad 计划词" value={rows.filter(r=>r.entry.broad).length} hint={`上限 ${rules.limits.broad}`}/><Metric symbol="$" label="手动 Bid" value={dollarText(rules.bid.exact)} hint="本地规则参数"/><Metric symbol="$" label="自动 Bid" value={dollarText(rules.bid.auto)} hint="本地规则参数"/></div>
      <div className="kw-v2-plan-layout"><Card size="small" title="本次广告执行目标"><Text strong>店铺 / 账号</Text><Select className="kw-v2-block" value={selectedListing?.listing.store} disabled options={selectedListing?[{label:selectedListing.listing.store,value:selectedListing.listing.store}]:[]}/><div className="kw-v2-muted">当前已选择 Item ID：{itemId||'未选择'}{selectedListing?` · ${selectedListing.listing.store}`:''}</div><Divider/><Text strong>手动 Campaign</Text><div>{sku.sku?sku.sku+'-Manual':'—'}</div><Text strong>自动 Campaign</Text><div>{sku.sku?sku.sku+'-Auto':'—'}</div></Card><Card size="small" title="本地广告参数建议（未执行）"><Descriptions size="small" bordered column={1} items={[{key:'bid',label:'手动 Bid',children:dollarText(rules.bid.exact)},{key:'auto',label:'自动 Bid',children:dollarText(rules.bid.auto)},{key:'budget',label:'手动 / 自动每日预算',children:`$${rules.bid.dailyBudget} / $${rules.bid.dailyBudget}`},{key:'start',label:'美国开始日期',children:rulesDate||'未配置'},{key:'rule',label:'规则版本',children:`V${rules.version}.0`} ]}/></Card></div>
      <div className="kw-v2-exportbar"><Button onClick={()=>csvDownload(`${sku.sku}_分析报告.csv`,['关键词','中文','得分','等级','Exact','Broad','市场搜索量'],filtered.map(({entry:e,keyword:k})=>[k.term,k.translation||'',e.score,e.grade,e.exact?'Y':'N',e.broad?'Y':'N',k.monthlySearches]))}>下载分析报告 CSV</Button><Button type="primary" onClick={downloadAll}>下载五表分析 Excel</Button></div>
     </>:null}
     {resultsTab==='listing'?<div className="kw-v2-listing"><div className="kw-v2-listing-main"><Card size="small" title={`Title · ${effectiveDraft.title.length} 字符`} extra={<Button type="link" onClick={()=>void navigator.clipboard.writeText(effectiveDraft.title)}>复制</Button>}><Input.TextArea rows={3} value={effectiveDraft.title} onChange={e=>setDraft({...effectiveDraft,title:e.target.value})}/></Card><Card size="small" title={`Key Features · ${effectiveDraft.features.split('\n').filter(Boolean).length} / 5 条`} extra={<Button type="link" onClick={()=>void navigator.clipboard.writeText(effectiveDraft.features)}>复制</Button>}><Input.TextArea rows={6} value={effectiveDraft.features} onChange={e=>setDraft({...effectiveDraft,features:e.target.value})}/></Card><Card size="small" title={`Description · ${effectiveDraft.description.length} 字符`} extra={<Button type="link" onClick={()=>void navigator.clipboard.writeText(effectiveDraft.description)}>复制</Button>}><Input.TextArea rows={5} value={effectiveDraft.description} onChange={e=>setDraft({...effectiveDraft,description:e.target.value})}/></Card></div><Card size="small" title="Listing 生成依据"><p className="kw-v2-muted">已核对的商品事实、风险词和当前候选关键词。仅根据人工填写的商品资料生成模板，未调用 AI 文案 API。</p><Alert type="warning" message="模板英文文案必须人工核对，不能直接作为正式 Listing 发布"/><Divider/><Space wrap>{rows.filter(x=>x.entry.exact).slice(0,7).map(x=><Tag key={x.keyword.id}>{x.keyword.term}</Tag>)}</Space><Divider/><Button type="primary" block onClick={makeListing}>生成文案草稿</Button><Button block onClick={()=>{saveListing(sku.id,effectiveDraft);message.success('草稿已保存到当前浏览器会话')}}>保存当前草稿</Button><Button block onClick={()=>csvDownload(`${sku.sku}_Listing.csv`,['字段','文案'],[['Title',effectiveDraft.title],['Key Features',effectiveDraft.features],['Description',effectiveDraft.description]])}>导出 Listing 文案 CSV</Button></Card></div>:null}
    </Card>
   </div>:null}
   {!analyzed&&existing?<Empty description="该 SKU 已收录关键词。若需重新分析，请在词库中操作；本页按新品流程设计。"/>:null}
   </>}
  </div>
  <Modal open={factOpen} width={830} onCancel={()=>setFactOpen(false)} title="核对商品信息" okText="确认参数" okButtonProps={{disabled:!ready||!consent||!parametersComplete}} onOk={()=>{
    if(!ready||!consent||!parametersComplete){
      message.warning('请先补齐真实商品资料并完成规则配置');
      return;
    }
    upsertProductSku({
      ...sku,
      material:facts.material,
      uses:facts.use.split(/[,，、;；\n]+/).map(x=>x.trim()).filter(Boolean)
    });
    setConfirmed(true);setFactOpen(false);message.success('商品事实与投放参数已确认，现在可开始分析')}}>

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

  <Drawer open={!!detail} title={`分析依据 · ${detail?.keyword.term||''}`} width={540} onClose={()=>setDetail(null)}><Alert type="warning" showIcon message="该分值是本地规则初筛计算，不是 AI 评估。当前版本未根据 Amazon 正文重新计算关键词覆盖。"/><Descriptions bordered column={1} size="small" style={{marginTop:12}} items={detail?[{key:'score',label:'本地规则分数',children:detail.entry.score??'—'},{key:'grade',label:'投放等级',children:detail.entry.grade},{key:'reason',label:'商品匹配判断',children:detail.entry.reason},{key:'ppc',label:'Amazon PPC',children:dollarText(detail.keyword.amazonPpc)},{key:'purchase',label:'市场购买量',children:countText(detail.keyword.monthlyPurchases)},{key:'source',label:'来源',children:detail.keyword.source},{key:'root',label:'词根（初步）',children:detail.keyword.root},{key:'asins',label:'关联 ASIN（表格）',children:detail.keyword.relatedAsins.join('、')||'—'}]:[]}/></Drawer>
  <Drawer open={!!compare} title={`跨 SKU 关键词 · ${compare?.term||''}`} width={620} onClose={()=>setCompare(null)}><Alert type="info" message="每个 SKU 独立评分；当前结果来自本次上传的数据和本地计算。"/><ProTable rowKey="skuId" pagination={false} search={false} options={false} toolBarRender={false} columns={[{title:'SKU',dataIndex:'skuId',render:(_,r)=>skus.find(s=>s.id===r.skuId)?.sku},{title:'得分',dataIndex:'score'},{title:'等级',dataIndex:'grade'},{title:'Exact',dataIndex:'exact',render:(_,r)=>r.exact?'✓':'—'},{title:'Broad',dataIndex:'broad',render:(_,r)=>r.broad?'✓':'—'}]} dataSource={compare?allAssoc(compare.id):[]}/></Drawer>
  <Drawer open={historyOpen} title="分析历史" width={600} onClose={()=>setHistoryOpen(false)}><Alert type="info" message="分析历史只在当前浏览器会话保存；不写入服务端。"/><ProTable rowKey={r=>`${r.skuId}-${r.at}`} pagination={false} search={false} options={false} toolBarRender={false} dataSource={analyses} columns={[{title:'SKU',dataIndex:'skuId',render:(_,r)=>skus.find(s=>s.id===r.skuId)?.sku},{title:'日期',dataIndex:'at'},{title:'规则版本',dataIndex:'version'},{title:'关键词数',dataIndex:'rows'},{title:'来源文件',dataIndex:'sourceFile'}]}/></Drawer>
 </PageShell>;
}
