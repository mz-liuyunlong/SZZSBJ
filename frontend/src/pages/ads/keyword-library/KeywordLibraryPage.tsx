import {useMemo,useState} from 'react';
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
import {parseSellerSprite,downloadDemoWorkbook} from '@/features/keyword-planning/importWorkbook';
import {useKeywordStore} from '@/features/keyword-planning/store';
import type {AdRecord,MarketKeyword,MatchType,SkuKeyword} from '@/features/keyword-planning/types';
import '../../ai-center/keyword-launch/KeywordLaunchPage.css';
import './KeywordLibraryPage.css';
const {Text}=Typography;
type Mode='sku'|'global';
type Tab='all'|'todo'|'execution'|'performance'|'history';
type LibraryRow={key:string;keyword:MarketKeyword;associated:SkuKeyword[];current:SkuKeyword|null;mockAds:AdRecord[]};
interface FormData {skuId:string;term:string;store:string;match:MatchType;bid:number;campaign:string}
const performance=(ads:AdRecord[])=>{
  const included=ads.filter(x=>x.source==='mock_only'&&x.clicks!==null&&x.spend!==null);
  if(!included.length)return null;
  const sum=(field:'clicks'|'spend'|'orders'|'sales'|'impressions')=>included.reduce((n,a)=>n+(a[field]||0),0);
  const clicks=sum('clicks'),spend=sum('spend'),orders=sum('orders'),sales=sum('sales');
  return {clicks,spend,orders,sales,cpc:clicks>0?spend/clicks:null,cvr:clicks>0?orders/clicks*100:null,acos:sales>0?spend/sales*100:null,roas:spend>0?sales/spend:null};
};
function editTranslation(k:MarketKeyword,change:(id:string,value:string)=>void){let value=k.translation||'';Modal.confirm({title:`修改中文翻译 · ${k.term}`,content:<Input.TextArea rows={3} defaultValue={value} onChange={e=>{value=e.target.value}}/>,okText:'保存翻译',onOk:()=>change(k.id,value)})}
export default function KeywordLibraryPage({page}:{page:NavigationPage}){
 const navigate=useNavigate(),location=useLocation();const startSku=(location.state as {skuId?:string}|null)?.skuId;
 const {skus,keywords,entries,ads,analyses,updateTranslation,mockTranslate,addManual,assignManual,importSupplement}=useKeywordStore();
 const [skuId,setSkuId]=useState(startSku&&skus.some(x=>x.id===startSku)?startSku:skus[0].id);
 const [mode,setMode]=useState<Mode>('sku'),[tab,setTab]=useState<Tab>('all');
 const [searchType,setSearchType]=useState('keyword'),[searchInput,setSearchInput]=useState(''),[query,setQuery]=useState('');
 const [grade,setGrade]=useState('all');const [compare,setCompare]=useState<MarketKeyword|null>(null);
 const [manualOpen,setManualOpen]=useState(false),[manualForm]=Form.useForm<FormData>();
 const [busy,setBusy]=useState(false);const sku=skus.find(s=>s.id===skuId)||skus[0];
 const records=useMemo<LibraryRow[]>(()=>{
   const grouped=new Map<string,SkuKeyword[]>();for(const entry of entries){if(mode==='sku'&&entry.skuId!==skuId)continue;const list=grouped.get(entry.keywordId)||[];list.push(entry);grouped.set(entry.keywordId,list)}
   return [...grouped.entries()].flatMap(([id,associated])=>{const keyword=keywords[id];if(!keyword)return [];return [{key:id,keyword,associated,current:associated.find(x=>x.skuId===skuId)||associated[0]||null,mockAds:ads.filter(a=>a.keywordId===id&&(mode==='global'||a.skuId===skuId))}]}).sort((a,b)=>(b.current?.score||0)-(a.current?.score||0));
 },[entries,keywords,ads,mode,skuId]);
 const visible=records.filter(r=>{
   const q=normalizeTerm(query);const found=!q||(searchType==='sku'?r.associated.some(x=>skus.find(s=>s.id===x.skuId)?.sku.toLowerCase().includes(q)):(r.keyword.term+' '+(r.keyword.translation||'')).toLowerCase().includes(q));
   if(!found||(grade!=='all'&&r.current?.grade!==grade))return false;
   if(tab==='todo')return r.current?.status==='待测试'||r.current?.status==='风险复查';
   if(tab==='execution')return Boolean(r.current?.exact||r.current?.broad||r.mockAds.length);
   if(tab==='performance')return Boolean(performance(r.mockAds));
   return true;
 });
 const currentAds=ads.filter(a=>mode==='global'||a.skuId===skuId);const unmapped=ads.filter(a=>!a.skuId);
 const edit=(k:MarketKeyword)=>editTranslation(k,updateTranslation);
 const commonColumns:ProColumns<LibraryRow>[]=[
  {title:'关键词 / 中文翻译',key:'term',width:275,render:(_,r)=><KeywordTextCell keyword={r.keyword} onEdit={edit}/>},
  {title:mode==='sku'?'词质等级':'关联 SKU',key:'grade',width:125,render:(_,r)=>mode==='sku'?<Tag color={r.current?.grade==='P0'?'green':r.current?.grade==='不投放'?'red':'blue'}>{r.current?.grade||'未分析'}</Tag>:<Button type="link" size="small" onClick={()=>setCompare(r.keyword)}>{r.associated.length} 个 SKU</Button>},
  {title:'来源 / 规则',key:'source',width:180,render:(_,r)=><><Tag>{r.keyword.source==='excel'?'Excel':r.keyword.source==='manual'?'人工补录':'演示样本'}</Tag><div className="keyword-planning__small">{r.current?.analysisVersion||'—'}</div></>},
  {title:'模拟投放计划',key:'plan',width:145,render:(_,r)=><Space size={2}>{r.current?.exact?<Tag color="blue">Exact</Tag>:null}{r.current?.broad?<Tag color="cyan">Broad</Tag>:null}{!r.current?.exact&&!r.current?.broad?'未推荐':null}</Space>},
  {title:'账户配置状态',key:'actual',width:170,render:(_,r)=>r.mockAds.length?<><Tag color={r.mockAds.some(a=>a.source==='manual')?'purple':'orange'}>{r.mockAds.some(a=>a.source==='manual')?'人工补录':'模拟配置'}</Tag><div className="keyword-planning__small">真实 API 未同步</div></>:<Text type="secondary">未同步验证</Text>},
  {title:'月搜索量（Amazon）',key:'vol',width:155,render:(_,r)=>countText(r.keyword.monthlySearches)},
  {title:'分析 / 关联',key:'action',width:115,render:(_,r)=><Button type="link" onClick={()=>setCompare(r.keyword)}>对比 SKU</Button>},
 ];
 const executionColumns:ProColumns<LibraryRow>[]=[commonColumns[0],commonColumns[1],commonColumns[3],commonColumns[4],{title:'对账结论',key:'compare',width:230,render:(_,r)=>{
  if(!r.mockAds.length)return <Tag>待 API 同步验证</Tag>;
  if(r.mockAds.some(a=>a.source==='manual')&&!r.current?.exact&&!r.current?.broad)return <Tag color="purple">计划外新增 · 人工录入</Tag>;
  if(r.mockAds.some(a=>a.match==='Exact'&&r.current?.exact||a.match==='Broad'&&r.current?.broad))return <Tag color="green">匹配方式一致（演示）</Tag>;
  return <Tag color="orange">匹配方式不同（演示）</Tag>;
 }},commonColumns[6]];
 const performanceColumns:ProColumns<LibraryRow>[]=[commonColumns[0],{title:'SKU',key:'sku',width:140,render:(_,r)=>mode==='sku'?sku.sku:r.associated.map(a=>skus.find(s=>s.id===a.skuId)?.sku).join('、')},{title:'点击',key:'clicks',render:(_,r)=>countText(performance(r.mockAds)?.clicks??null)},{title:'花费',key:'spend',render:(_,r)=><MoneyCell value={performance(r.mockAds)?.spend??null}/>},{title:'订单',key:'orders',render:(_,r)=>countText(performance(r.mockAds)?.orders??null)},{title:'CPC',key:'cpc',render:(_,r)=><MoneyCell value={performance(r.mockAds)?.cpc??null}/>},{title:'CVR',key:'cvr',render:(_,r)=><PercentCell value={performance(r.mockAds)?.cvr??null}/>},{title:'ACOS',key:'acos',render:(_,r)=><PercentCell value={performance(r.mockAds)?.acos??null}/>},{title:'ROAS',key:'roas',render:(_,r)=>performance(r.mockAds)?.roas?.toFixed(2)||'—'}];
 const historyColumns:ProColumns<LibraryRow>[]=[commonColumns[0],commonColumns[1],{title:'分析分数（模拟）',key:'score',render:(_,r)=>r.current?.score??'—'},{title:'历史分析版本',key:'version',render:(_,r)=>r.current?.analysisVersion||'—'},commonColumns[6]];
 const download=()=>downloadDemoWorkbook(sku.sku,['关键词','中文翻译','SKU','等级（演示）','潜力分（演示）','Exact建议','Broad建议','月搜索量（Amazon）','原始PPC（USD）','关联SKU'],visible.map(r=>[r.keyword.term,r.keyword.translation||'',mode==='sku'?sku.sku:r.associated.map(e=>skus.find(s=>s.id===e.skuId)?.sku).join('/'),r.current?.grade||'',r.current?.score??null,r.current?.exact?'Y':'N',r.current?.broad?'Y':'N',r.keyword.monthlySearches,r.keyword.amazonPpc,r.associated.length]));
 const supplemental=async(file:File)=>{setBusy(true);try{const book=await parseSellerSprite(file);const n=importSupplement(sku.id,book);message.success(`补入 ${n} 个未收录词；已有词保留原评分，新增词待分析（mock_only）`)}catch(e){message.error(e instanceof Error?e.message:'导入失败')}finally{setBusy(false)}};
 const submitManual=async()=>{try{const values=await manualForm.validateFields();const assigned=values.skuId==='unassigned'?null:values.skuId;addManual({...values,skuId:assigned});setManualOpen(false);manualForm.resetFields();message.success(assigned?'已记录人工补词（未经平台 API 验证）':'已保存到待认领队列（mock_only）')}catch{/* form validation shown inline */}};
 return <PageShell page={page} headerActions={<Space><Tag color="orange">mock_only · 广告数据为模拟</Tag><Button onClick={()=>navigate('/ai-center/keyword-launch')}>去关键词投放</Button></Space>}>
   <div className="keyword-planning keyword-library">
    <Alert type="info" showIcon message="全局关键词可关联多个 SKU，但每个 SKU 的评级与投放记录独立。平台广告配置尚未同步；模拟指标仅用于交互验收。"/>
    <Card size="small"><Space wrap><Button type={mode==='sku'?'primary':'default'} onClick={()=>setMode('sku')}>按 SKU 查看</Button><Button type={mode==='global'?'primary':'default'} onClick={()=>setMode('global')}>跨 SKU 关键词</Button><Select value={sku.id} style={{minWidth:260}} disabled={mode==='global'} onChange={setSkuId} options={skus.map(s=>({label:s.sku+' · '+s.name,value:s.id}))}/><Tag>{records.length} 个关键词</Tag><Tag color="blue">待认领广告关键词 {unmapped.length}</Tag></Space></Card>
    <Card size="small"><Space wrap><ConnectedSearch typeAriaLabel="选择搜索维度" typeOptions={[{label:'关键词',value:'keyword'},{label:'SKU',value:'sku'}]} typeValue={searchType} inputAriaLabel="输入关键词或SKU" inputPlaceholder="搜索关键词 / 中文意思" inputValue={searchInput} onTypeChange={setSearchType} onInputChange={setSearchInput} onSearch={()=>setQuery(searchInput)}/><Select value={grade} style={{width:125}} onChange={setGrade} options={['all','P0','P1','P2','复查','不投放'].map(v=>({label:v==='all'?'全部等级':v,value:v}))}/><ResetButton onClick={()=>{setQuery('');setSearchInput('');setGrade('all');setSearchType('keyword')}}/><Button icon={<TranslationOutlined/>} onClick={()=>{const n=mockTranslate();message.info(n?`演示词典补翻译 ${n} 条，未命中的仍显示待翻译`:'暂无可使用的模拟翻译词典匹配')}}>批量补翻译</Button><Button icon={<PlusOutlined/>} onClick={()=>{manualForm.setFieldsValue({skuId:skuId,store:'演示店铺A',match:'Exact',bid:0.35,campaign:'Demo-Manual'});setManualOpen(true)}}>记录后台新增词</Button><Upload accept=".xlsx,.xls,.csv,.tsv" showUploadList={false} beforeUpload={file=>{void supplemental(file);return false}}><Button loading={busy} icon={<UploadOutlined/>}>补充 Excel</Button></Upload><Button onClick={download}>下载 DEMO 词库</Button></Space></Card>
    <Card size="small" title="关键词资产与投放情况" extra={<Tag>{mode==='global'?'按关键词汇总全部 SKU':'仅当前 SKU'}</Tag>}>
      <Tabs activeKey={tab} onChange={v=>setTab(v as Tab)} items={[{key:'all',label:'全部关键词'},{key:'todo',label:'待测试 / 复查'},{key:'execution',label:'计划与实际投放'},{key:'performance',label:'广告效果（演示）'},{key:'history',label:'分析记录'}]}/>
      {tab==='execution'?<Alert style={{marginBottom:12}} type="warning" message="仅能比较本地计划与模拟/人工配置。没有真实 API 时「未同步」绝不等于「未投放」。"/>:null}
      {tab==='performance'?<Alert style={{marginBottom:12}} type="warning" message="以下花费、点击、订单、CPC、CVR、ACOS 均为合成 mock 数据。Amazon PPC 参考值不参与这些计算。"/>:null}
      {tab==='history'?<Alert style={{marginBottom:12}} type="info" message={`本地运行记录 ${analyses.filter(a=>mode==='global'||a.skuId===skuId).length} 次；新规则发布不会自动覆盖旧分析。`}/>:null}
      <ReportTableShell label="SKU 关键词词库明细"><ProTable<LibraryRow> rowKey="key" options={false} search={false} toolBarRender={false} columns={tab==='execution'?executionColumns:tab==='performance'?performanceColumns:tab==='history'?historyColumns:commonColumns} dataSource={visible} locale={{emptyText:'暂无关键词；可以在关键词投放页上传新品 Excel'}} pagination={{pageSize:15,showSizeChanger:true,pageSizeOptions:[15,30,50]}} scroll={{x:tab==='performance'?1300:1200,y:440}}/></ReportTableShell>
    </Card>
    {tab==='execution'?<Card size="small" title={`未归属广告关键词 · ${unmapped.length} 条（演示）`}><Space direction="vertical" style={{width:'100%'}}>{unmapped.map(a=><Space wrap key={a.id}><Text strong>{a.term}</Text><Tag>{a.store}</Tag><Tag>{a.match}</Tag><Select style={{width:210}} placeholder="选择归属 SKU" options={skus.map(s=>({label:s.sku,value:s.id}))} onChange={value=>{assignManual(a.id,value);message.success('已在当前会话完成演示归属')}}/></Space>)}{!unmapped.length?<Empty description="当前没有待认领词"/>:null}</Space></Card>:null}
   </div>
   <Drawer open={!!compare} onClose={()=>setCompare(null)} title={`跨 SKU 关键词对比 · ${compare?.term||''}`} width={620}>
    <Alert type="warning" message="同一个词在不同 SKU 中的匹配分与广告表现分别计算。所有广告数据均为 mock_only。"/>
    {compare?<ProTable rowKey="skuId" search={false} options={false} toolBarRender={false} pagination={false} columns={[{title:'SKU',dataIndex:'skuId',render:(_,r)=>skus.find(s=>s.id===r.skuId)?.sku},{title:'匹配等级',dataIndex:'grade'},{title:'潜力分',dataIndex:'score'},{title:'模拟 ACOS',render:(_,r)=>{const p=performance(ads.filter(a=>a.skuId===r.skuId&&a.keywordId===compare.id));return p?.acos!=null?p.acos.toFixed(1)+'%':'—'}},{title:'投放来源',render:(_,r)=>ads.some(a=>a.skuId===r.skuId&&a.keywordId===compare.id)?'模拟/人工':'未同步'}]} dataSource={entries.filter(e=>e.keywordId===compare.id)}/>:null}
    {compare?<Descriptions column={1} bordered size="small" items={[{key:'original',label:'原始翻译',children:compare.originalTranslation||'—'},{key:'effective',label:'当前中文',children:compare.translation||'待翻译'},{key:'source',label:'翻译来源',children:compare.translationSource}]} />:null}
   </Drawer>
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