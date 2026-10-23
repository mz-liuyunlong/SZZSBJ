import {useMemo,useState} from 'react';
import {useNavigate} from 'react-router-dom';
import {Alert,Button,Card,Descriptions,Divider,Drawer,Input,Modal,Select,Space,Spin,Statistic,Tabs,Tag,Typography,Upload,message,Empty} from 'antd';
import {InboxOutlined,SettingOutlined,FileExcelOutlined,TranslationOutlined} from '@ant-design/icons';
import {ProTable,type ProColumns} from '@ant-design/pro-components';
import PageShell from '@/components/page/PageShell';
import ReportTableShell from '@/components/report-table/ReportTableShell';
import {MoneyCell,PercentCell} from '@/components/report-table/cells';
import type {NavigationPage} from '@/config/navigation';
import {KeywordTextCell} from '@/features/keyword-planning/components/KeywordTextCell';
import {useKeywordStore} from '@/features/keyword-planning/store';
import {countText,dollarText,parseAsins,percentText} from '@/features/keyword-planning/model';
import {downloadDemoWorkbook,parseSellerSprite} from '@/features/keyword-planning/importWorkbook';
import type {MarketKeyword,SkuKeyword} from '@/features/keyword-planning/types';
import './KeywordLaunchPage.css';

const {Text}=Typography;
type View='decision'|'market'|'plan'|'listing';
function translationEditor(keyword:MarketKeyword,change:(id:string,value:string)=>void){
  let next=keyword.translation||'';
  Modal.confirm({title:`修改翻译：${keyword.term}`,content:<Input.TextArea defaultValue={next} rows={3} onChange={e=>{next=e.target.value}} placeholder="输入中文翻译"/>,okText:'保存到共用词库',cancelText:'取消',onOk:()=>change(keyword.id,next)});
}
const sourceTag=(kw:MarketKeyword)=><Tag color={kw.source==='excel'?'green':'default'}>{kw.source==='excel'?'Excel参考':kw.source==='manual'?'人工补录':'演示来源'}</Tag>;
export default function KeywordLaunchPage({page}:{page:NavigationPage}){
  const navigate=useNavigate();
  const {skus,keywords,entries,staged,rules,setStaged,analyze,updateTranslation,mockTranslate,listing,saveListing}=useKeywordStore();
  const [skuId,setSkuId]=useState('demo-product-3');
  const [asins,setAsins]=useState('');
  const [view,setView]=useState<View>('decision');
  const [keywordQuery,setKeywordQuery]=useState('');
  const [busy,setBusy]=useState(false);
  const [detail,setDetail]=useState<MarketKeyword|null>(null);
  const [listingDraft,setListingDraft]=useState<{title:string;features:string;description:string}|null>(null);
  const sku=skus.find(x=>x.id===skuId)||skus[0];
  const skuEntries=useMemo(()=>entries.filter(x=>x.skuId===sku.id),[entries,sku.id]);
  const isExisting=sku.hasLibrary;
  const parsedAsins=parseAsins(asins);
  const validAsins=parsedAsins.valid;
  const importCount=staged?.keywords.length||0;
  const existingKeywords=skuEntries.map(e=>({entry:e,keyword:keywords[e.keywordId]})).filter((x):x is {entry:SkuKeyword;keyword:MarketKeyword}=>!!x.keyword);
  const filtered=existingKeywords.filter(x=>(x.keyword.term+' '+(x.keyword.translation||'')).toLowerCase().includes(keywordQuery.toLowerCase()));
  const rowsForPlan=filtered.filter(x=>x.entry.exact||x.entry.broad);
  const displayCols:ProColumns<{entry:SkuKeyword;keyword:MarketKeyword}>[]=[
    {title:'关键词 / 中文',key:'term',width:265,render:(_,r)=><KeywordTextCell keyword={r.keyword} onEdit={k=>translationEditor(k,updateTranslation)}/>},
    {title:'商品匹配 / 页面承接',key:'fit',width:200,render:(_,r)=><div><Tag color={r.entry.grade==='不投放'?'red':r.entry.grade==='P0'?'green':'blue'}>{r.entry.grade==='不投放'?'风险复查':'待核对 Listing'}</Tag><div className="keyword-planning__small">{r.entry.reason}</div></div>},
    {title:'ASIN参考覆盖',key:'asins',width:128,render:(_,r)=><span>{r.keyword.relatedAsins.length} 个关联 ASIN</span>},
    {title:'月搜索量',key:'volume',width:110,render:(_,r)=>countText(r.keyword.monthlySearches)},
    {title:'月购买量',key:'purchase',width:110,render:(_,r)=>countText(r.keyword.monthlyPurchases)},
    {title:'Amazon PPC',key:'ppc',width:130,render:(_,r)=><MoneyCell value={r.keyword.amazonPpc}/>},
    {title:'潜力分 / 等级',key:'grade',width:135,render:(_,r)=><Space><Text strong>{r.entry.score??'—'}</Text><Tag color={r.entry.grade==='P0'?'green':r.entry.grade==='不投放'?'red':'blue'}>{r.entry.grade}</Tag></Space>},
    {title:'模拟投放建议',key:'match',width:140,render:(_,r)=><Space size={3}>{r.entry.exact?<Tag color="blue">Exact</Tag>:null}{r.entry.broad?<Tag color="cyan">Broad</Tag>:null}{!r.entry.exact&&!r.entry.broad?'暂缓测试':null}</Space>},
    {title:'分析依据',key:'action',width:90,render:(_,r)=><Button type="link" size="small" onClick={()=>setDetail(r.keyword)}>查看</Button>},
  ];
  const marketCols:ProColumns<{entry:SkuKeyword;keyword:MarketKeyword}>[]=[
    displayCols[0],{title:'来源',key:'source',width:140,render:(_,r)=>sourceTag(r.keyword)},
    {title:'搜索量/月',key:'v',width:130,render:(_,r)=>countText(r.keyword.monthlySearches)},
    {title:'购买量/月',key:'b',width:130,render:(_,r)=>countText(r.keyword.monthlyPurchases)},
    {title:'市场购买率',key:'rate',width:130,render:(_,r)=><PercentCell value={r.keyword.marketPurchaseRate==null?null:r.keyword.marketPurchaseRate*100}/>},
    {title:'Amazon PPC',key:'ppc',width:130,render:(_,r)=><MoneyCell value={r.keyword.amazonPpc}/>},
    {title:'竞价范围（原表）',key:'range',width:155,render:(_,r)=>r.keyword.bidRange||'—'},
    {title:'广告竞品数',key:'sponsored',width:120,render:(_,r)=>countText(r.keyword.sponsoredCompetitors)},
    {title:'关联ASIN',key:'asins',width:180,render:(_,r)=>r.keyword.relatedAsins.length||'—'},displayCols[8],
  ];
  const switchSku=(next:string)=>{setSkuId(next);setView('decision');setAsins('');setStaged(null);setKeywordQuery('');setListingDraft(null)};
  const loadFile=async(file:File)=>{
    setBusy(true);try{const parsed=await parseSellerSprite(file);setStaged(parsed);setAsins(parsed.asins.join('\n'));message.success(`已解析 ${parsed.keywords.length} 个关键词，来源保留原始市场指标`)}catch(e){message.error(e instanceof Error?e.message:'解析失败')}finally{setBusy(false)}
  };
  const performAnalysis=()=>{
    if(!staged)return message.warning('请先上传卖家精灵 Excel');
    if(parsedAsins.invalid.length)return message.warning('请检查 ASIN 格式：'+parsedAsins.invalid.join('、'));
    if(validAsins.length<rules.asin.min)return message.warning(`至少提供 ${rules.asin.min} 个不同的有效 ASIN`);
    Modal.confirm({title:'确认生成本地演示分析？',width:570,content:<div><p>当前 SKU：{sku.sku}；关键词 {staged.keywords.length} 条；有效 ASIN {validAsins.length} 个。</p><Alert type="warning" showIcon message="仅以商品演示事实和 Excel 参考值模拟评分。ASIN 只有编号，没有获取真实 Title / 五点 / 描述；不可用于真实广告执行。"/></div>,okText:'确认生成',cancelText:'取消',onOk:()=>{const n=analyze(sku.id);message.success(`已生成 ${n} 条 mock_only 分析结果`);setView('decision')}});
  };
  const selectedListing=listingDraft||listing[sku.id]||{title:`${sku.name} – ${sku.material} Organizer`,features:['收纳分类','家庭与工作空间','简易整理','日常使用','使用场景'].join('\n'),description:'[MOCK_ONLY] 请根据实际商品信息审核编辑 Listing 文案。'};
  const download=()=>downloadDemoWorkbook(sku.sku,['英文关键词','中文翻译','SKU','演示分数','潜力等级','建议 Exact','建议 Broad','市场月搜索量','Amazon PPC(USD)','人工复核说明'],filtered.map(x=>[x.keyword.term,x.keyword.translation||'',sku.sku,x.entry.score,x.entry.grade,x.entry.exact?'Y':'N',x.entry.broad?'Y':'N',x.keyword.monthlySearches,x.keyword.amazonPpc,x.entry.reason]));
  return <PageShell page={page} headerActions={<Space><Tag color="orange">mock_only · 不执行广告</Tag><Button icon={<SettingOutlined/>} onClick={()=>navigate('/ai-center/keyword-launch/rules')}>规则配置</Button></Space>}>
    <div className="keyword-planning">
      <Alert type="info" showIcon banner message="新品冷启动演示：Excel 市场指标保留真实上传值；评分、出价方案、Amazon 文案和广告数据均非实际投放结果。"/>
      <Card size="small" title="第一步 · 选择商品 SKU" extra={<Tag color="blue">商品资料为演示样本</Tag>}>
        <Space wrap><Select style={{minWidth:290}} value={sku.id} onChange={switchSku} options={skus.map(s=>({label:`${s.sku} · ${s.name}`,value:s.id}))}/><Text type="secondary">{sku.name} · {sku.material}</Text></Space>
        {isExisting?<Alert style={{marginTop:12}} type="success" showIcon message="该 SKU 已有词库，建议直接查看词库和下载，避免重复分析。" action={<Button type="primary" onClick={()=>navigate('/ads/keyword-library',{state:{skuId:sku.id}})}>查看 SKU 词库</Button>}/>:null}
      </Card>
      {!isExisting?<Card size="small" title="第二步 · 竞品 ASIN 与关键词 Excel" extra={<Text type="secondary">真实文件解析 / 模拟资料确认</Text>}>
        <div className="keyword-planning__form-grid">
          <div><Text strong>Amazon 参考 ASIN（每行一个）</Text><Input.TextArea rows={5} value={asins} placeholder="B012345678\nB012345679\nB012345670" onChange={e=>setAsins(e.target.value)}/><div className="keyword-planning__small">有效 {validAsins.length} 个 · 至少 {rules.asin.min} 个，建议 {rules.asin.recommend}–{rules.asin.max} 个。{parsedAsins.invalid.length?<Text type="danger"> 无效：{parsedAsins.invalid.join('、')}</Text>:null}</div><Alert type="warning" showIcon message="ASIN 仅校验编号；真实竞品文案和商品属性尚未接入。"/></div>
          <div><Text strong>上传卖家精灵关键词文件</Text><Upload.Dragger multiple={false} accept=".xlsx,.xls,.csv,.tsv" showUploadList={false} beforeUpload={(file)=>{void loadFile(file);return false}}><p><InboxOutlined style={{fontSize:24}}/></p><p>上传 XLSX / CSV / TSV</p><Text type="secondary">识别关键词、翻译、Unique Words 与 Asin Sheet</Text></Upload.Dragger>{busy?<Spin style={{marginTop:10}}/>:null}{staged?<div className="keyword-planning__file-summary"><Tag icon={<FileExcelOutlined/>} color="green">{staged.fileName}</Tag><Text>{importCount} 个关键词 / {staged.roots.length} 个词根 / {staged.asins.length} 个 ASIN</Text><Text type="secondary">含翻译 {staged.keywords.filter(k=>k.translation).length} · 待翻译 {staged.keywords.filter(k=>!k.translation).length}</Text>{staged.warnings.length?<Alert type="warning" message={staged.warnings.join('；')}/>:null}</div>:null}</div>
        </div>
        <div className="keyword-planning__footer"><Button type="primary" onClick={performAnalysis} disabled={!staged||busy}>确认并模拟分析</Button><Text type="secondary">仅在当前浏览器会话内保存，刷新页面后重置</Text></div>
      </Card>:null}
      {existingKeywords.length?<Card size="small" title="关键词分析结果" extra={<Space><Tag>分析规则版本：{skuEntries[0]?.analysisVersion||'—'}</Tag><Button icon={<TranslationOutlined/>} onClick={()=>{const n=mockTranslate();message.info(n?`演示词典补充 ${n} 个翻译；其他未命中词仍待翻译`:'无演示词典可补的关键词')}}>批量补翻译（模拟）</Button><Button onClick={download}>下载 DEMO</Button></Space>}>
        <Tabs size="small" activeKey={view} onChange={key=>setView(key as View)} items={[{key:'decision',label:'投放决策'},{key:'market',label:'市场与竞品数据'},{key:'plan',label:'投放方案'},{key:'listing',label:'Listing 文案'}]}/>
        {(view==='decision'||view==='market')?<><Input.Search allowClear style={{width:300,marginBottom:10}} placeholder="搜索英文关键词或中文翻译" value={keywordQuery} onChange={e=>setKeywordQuery(e.target.value)}/><ReportTableShell label="新品关键词分析表"><ProTable<{entry:SkuKeyword;keyword:MarketKeyword}> rowKey={r=>r.keyword.id} options={false} search={false} toolBarRender={false} columns={view==='decision'?displayCols:marketCols} dataSource={filtered} pagination={{pageSize:15,showSizeChanger:true,pageSizeOptions:[15,30,50]}} scroll={{x:view==='decision'?1460:1540,y:440}}/></ReportTableShell></>:null}
        {view==='plan'?<><Alert type="warning" message="下面是模拟 Manual Exact/Broad 计划，Bid 取规则模拟默认值，不是 Walmart 竞价建议。"/><Space style={{margin:'12px 0'}}><Statistic title="Exact 计划词数" value={rowsForPlan.filter(x=>x.entry.exact).length}/><Divider type="vertical"/><Statistic title="Broad 计划词数" value={rowsForPlan.filter(x=>x.entry.broad).length}/></Space><ReportTableShell label="模拟投放方案"><ProTable rowKey={r=>r.keyword.id} options={false} search={false} toolBarRender={false} columns={[displayCols[0],{title:'Exact',key:'exact',render:(_,r)=>r.entry.exact?'✓':'—'},{title:'Broad',key:'broad',render:(_,r)=>r.entry.broad?'✓':'—'},{title:'模拟 Exact Bid',key:'bid',render:(_,r)=>r.entry.exact?dollarText(rules.bid.exact):'—'},{title:'模拟 Broad Bid',key:'bid2',render:(_,r)=>r.entry.broad?dollarText(rules.bid.broad):'—'}]} dataSource={rowsForPlan} pagination={{pageSize:15}} scroll={{x:1000,y:400}}/></ReportTableShell></>:null}
        {view==='listing'?<><Alert type="info" message="Listing 文案为模拟草稿，请与真实商品属性、Walmart 规则和关键词承接核对后使用。"/><div className="keyword-planning__listing"><Text strong>Title</Text><Input value={selectedListing.title} onChange={e=>setListingDraft({...selectedListing,title:e.target.value})} maxLength={rules.listing.titleMax}/><Text strong>Key Features（每行一条）</Text><Input.TextArea rows={6} value={selectedListing.features} onChange={e=>setListingDraft({...selectedListing,features:e.target.value})}/><Text strong>Description</Text><Input.TextArea rows={5} value={selectedListing.description} onChange={e=>setListingDraft({...selectedListing,description:e.target.value})}/><Button type="primary" onClick={()=>{saveListing(sku.id,selectedListing);message.success('当前会话中的文案草稿已更新（mock_only）')}}>保存演示草稿</Button></div></>:null}
      </Card>:isExisting?<Empty description="没有可显示的词库行，请前往词库核查"/>:null}
    </div>
    <Drawer title={`分析依据 · ${detail?.term||''}`} width={520} open={!!detail} onClose={()=>setDetail(null)}><Alert type="warning" message="分析分数为本地启发式演示；未获取 Amazon 竞品正文，不代表 AI 已验证。"/><Descriptions bordered column={1} size="small" style={{marginTop:12}} items={detail?[{key:'source',label:'来源',children:sourceTag(detail)},{key:'search',label:'月搜索量',children:countText(detail.monthlySearches)},{key:'purchase',label:'月购买量',children:countText(detail.monthlyPurchases)},{key:'cvr',label:'Amazon 市场参考购买率',children:percentText(detail.marketPurchaseRate)},{key:'ppc',label:'参考 PPC',children:dollarText(detail.amazonPpc)},{key:'range',label:'卖家精灵竞价范围',children:detail.bidRange||'—'},{key:'asins',label:'关联 ASIN',children:detail.relatedAsins.join('、')||'—'},{key:'root',label:'词根（初步分词）',children:detail.root}]:[]}/></Drawer>
  </PageShell>;
}