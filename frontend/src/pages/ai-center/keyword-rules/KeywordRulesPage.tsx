import {useMemo,useState} from 'react';
import {useNavigate} from 'react-router-dom';
import {Alert,Button,Card,Descriptions,Form,Input,InputNumber,Modal,Space,Switch,Tabs,Tag,Typography,message} from 'antd';
import {ArrowLeftOutlined,DiffOutlined} from '@ant-design/icons';
import PageShell from '@/components/page/PageShell';
import type {NavigationPage} from '@/config/navigation';
import {analyzeKeyword,initialRules,ruleErrors} from '@/features/keyword-planning/model';
import {useKeywordStore} from '@/features/keyword-planning/store';
import type {RuleConfig} from '@/features/keyword-planning/types';
import './KeywordRulesPage.css';
const {Text}=Typography;
type Group='weights'|'thresholds'|'limits'|'asin'|'bid'|'naming'|'listing'|'export';
const labels:Record<Group,string>={weights:'评分权重',thresholds:'分级阈值',limits:'投放名额',asin:'Amazon 参考',bid:'出价预算',naming:'Campaign 命名',listing:'Listing 规则',export:'Excel 配置'};
const fields:Record<Group,Array<{key:string;label:string;description?:string;step?:number}>>={
  weights:[{key:'match',label:'商品相关性权重'},{key:'intent',label:'搜索意图权重'},{key:'coverage',label:'竞品 ASIN 覆盖权重'},{key:'root',label:'核心词根权重'},{key:'market',label:'市场参考数据权重'}],
  thresholds:[{key:'p0',label:'P0 最低分'},{key:'p1',label:'P1 最低分'},{key:'p2',label:'P2 最低分'}],
  limits:[{key:'p0',label:'P0 词数'},{key:'p1',label:'P1 词数'},{key:'p2',label:'P2 候选词数'},{key:'exact',label:'Exact 最大投放数'},{key:'broad',label:'Broad 最大投放数'},{key:'roots',label:'Broad 最大词根数'}],
  asin:[{key:'min',label:'最少不同 ASIN 数'},{key:'recommend',label:'建议不同 ASIN 数'},{key:'max',label:'推荐最多 ASIN 数'},{key:'titleWeight',label:'Title 命中权重',step:0.1},{key:'featuresWeight',label:'Key Features 命中权重',step:0.1}],
  bid:[{key:'exact',label:'模拟 Exact Bid (USD)',step:0.01},{key:'broad',label:'模拟 Broad Bid (USD)',step:0.01},{key:'auto',label:'模拟 Auto Bid (USD)',step:0.01},{key:'dailyBudget',label:'模拟每日预算 (USD)',step:0.5}],
  naming:[{key:'manual',label:'手动广告名称模板'},{key:'auto',label:'自动广告名称模板'}],
  listing:[{key:'features',label:'Key Features 条数'},{key:'titleMax',label:'Title 字数上限'}],
  export:[{key:'sheetNames',label:'导出 Sheet 名称（每行一个）'},{key:'columnNames',label:'资产表列标题（逗号分隔）'}],
};
function editField(rule:RuleConfig,group:Group,key:string,value:string|number):RuleConfig{
  const updated=structuredClone(rule);
  const target=updated[group] as unknown as Record<string,string|number|boolean>;
  target[key]=value;
  return updated;
}
export default function KeywordRulesPage({page}:{page:NavigationPage}){
 const navigate=useNavigate();
 const {rules,draft,history,startDraft,changeDraft,publishDraft,resetDraft,rollback,keywords,skus}=useKeywordStore();
 const [tab,setTab]=useState('scoring');const [compare,setCompare]=useState(false);const [testOpen,setTestOpen]=useState(false);
 const shown=draft||rules;
 const errors=useMemo(()=>ruleErrors(shown),[shown]);
 const computed=useMemo(()=>{
  const keys=Object.values(keywords).slice(0,300);const sku=skus[0];
  const stats=(r:RuleConfig)=>keys.reduce<Record<string,number>>((acc,k)=>{const grade=analyzeKeyword(k,sku,r).grade;acc[grade]=(acc[grade]||0)+1;return acc},{}) ;
  return {sample:keys.length,before:stats(rules),after:stats(shown)};
 },[keywords,rules,shown,skus]);
 const group=(g:Group)=>{
  const obj=shown[g] as unknown as Record<string,string|number|boolean>;
  return <Card size="small" title={labels[g]} key={g}><div className="keyword-rules__fields">{fields[g].map(x=>{
   const value=obj[x.key];const isText=typeof value==='string';const area=isText&&String(value).includes('\n')||x.key==='sheetNames'||x.key==='columnNames';
   return <Form.Item key={x.key} label={x.label} className={area?'keyword-rules__wide':''}>
      {area?<Input.TextArea rows={4} disabled={!draft} value={String(value)} onChange={e=>draft&&changeDraft(editField(draft,g,x.key,e.target.value))}/>:isText?<Input disabled={!draft} value={String(value)} onChange={e=>draft&&changeDraft(editField(draft,g,x.key,e.target.value))}/>:<InputNumber style={{width:'100%'}} disabled={!draft} step={x.step||1} value={Number(value)} min={0} onChange={n=>draft&&changeDraft(editField(draft,g,x.key,n??0))}/>}
   </Form.Item>})}</div></Card>
 };
 const confirmPublish=()=>{if(!draft)return message.warning('请先创建草稿');if(errors.length)return message.error('请先处理规则校验错误');
  let reason='运营规则调整';Modal.confirm({title:'发布模拟规则新版本',content:<><Alert type="warning" message="这是浏览器内 mock_only 发布，不会更改数据库、历史分析或 Walmart 广告。"/><Input style={{marginTop:12}} placeholder="修改原因" defaultValue={reason} onChange={e=>{reason=e.target.value}}/></>,okText:'发布演示版本',onOk:()=>{const err=publishDraft(reason);if(err)message.error(err);else message.success('规则演示版本已发布，已有分析结果不会自动重算')}})};
 return <PageShell page={page} headerActions={<Space><Tag color="orange">mock_only</Tag><Button icon={<ArrowLeftOutlined/>} onClick={()=>navigate('/ai-center/keyword-launch')}>返回关键词投放</Button></Space>}>
   <div className="keyword-rules">
     <Alert showIcon type="info" message={`当前发布版本：MOCK-v${rules.version}。所有业务参数均可修改；规则只影响新分析，已有 SKU 的历史等级不自动覆盖。`}/>
     <Space wrap><Button type="primary" onClick={()=>{startDraft();message.success('已创建独立草稿')}}>{draft?'重新从当前版本创建草稿':'创建规则草稿'}</Button><Button disabled={!draft} onClick={()=>setCompare(true)} icon={<DiffOutlined/>}>比较修改</Button><Button disabled={!draft} onClick={()=>setTestOpen(true)}>模拟回测</Button><Button disabled={!draft} onClick={()=>{if(!draft)return;changeDraft({...structuredClone(initialRules),version:rules.version});message.info('已将默认参数载入草稿')}}>草稿恢复默认</Button><Button disabled={!draft} onClick={resetDraft}>放弃草稿</Button><Button type="primary" disabled={!draft||errors.length>0} onClick={confirmPublish}>发布模拟版本</Button></Space>
     {errors.length?<Alert type="error" message="规则校验未通过" description={errors.join('；')} showIcon/>:draft?<Alert type="success" message="草稿校验通过，可以模拟回测。" showIcon/>:<Alert type="warning" message="当前为只读已发布版本。要修改请先创建草稿。"/>}
     <Tabs activeKey={tab} onChange={setTab} items={[{key:'scoring',label:'评分与分级'},{key:'targeting',label:'投放与 ASIN'},{key:'listing',label:'Listing 与导出'},{key:'history',label:'历史版本'}]}/>
     {tab==='scoring'?<>{group('weights')}{group('thresholds')}<Card title="品牌、材质与风险词策略" size="small"><Form.Item label="风险词规则（每行一个；示例仅供演示）"><Input.TextArea rows={6} disabled={!draft} value={shown.riskWords} onChange={e=>draft&&changeDraft({...draft,riskWords:e.target.value})}/></Form.Item></Card></>:null}
     {tab==='targeting'?<>{group('limits')}{group('asin')}{group('bid')}{group('naming')}</>:null}
     {tab==='listing'?<>{group('listing')}<Card size="small" title="Listing Description"><Form.Item label="是否允许生成演示 Description"><Switch disabled={!draft} checked={shown.listing.description} onChange={checked=>draft&&changeDraft({...draft,listing:{...draft.listing,description:checked}})}/></Form.Item></Card>{group('export')}<Alert type="warning" message="字段配置可以存为草稿，但不表示与 Walmart 官方 Bulk 模板兼容。正式上传文件生成不在此版本范围内。"/></>:null}
     {tab==='history'?<Card size="small" title="规则版本（只保存在当前会话）"><Descriptions bordered column={1} items={history.map(h=>({key:h.version,label:`MOCK-v${h.version}`,children:<Space><Text>{h.at} · {h.reason}</Text><Button type="link" onClick={()=>{rollback(h.version);message.info('已复制历史规则到可编辑草稿，并未覆盖生效版本')}}>恢复为草稿</Button></Space>}))}/></Card>:null}
     <Modal title="草稿与当前版本差异" open={compare} onCancel={()=>setCompare(false)} footer={<Button onClick={()=>setCompare(false)}>关闭</Button>} width={820}>
       <Alert showIcon type="info" message="完整业务规则快照对照（演示）"/><div className="keyword-rules__diff"><pre>{JSON.stringify(rules,null,2)}</pre><pre>{JSON.stringify(shown,null,2)}</pre></div>
     </Modal>
     <Modal title="模拟回测（最多前 300 个演示/导入关键词）" open={testOpen} onCancel={()=>setTestOpen(false)} footer={<Button onClick={()=>setTestOpen(false)}>关闭</Button>}>
      <Alert showIcon type="warning" message={`仅使用 ${computed.sample} 个现有词的本地演示评分，不包含真实广告表现或模型推理。`}/>
      <Descriptions bordered column={3} style={{marginTop:15}} items={(['P0','P1','P2','复查','不投放'] as const).flatMap(g=>[{key:g+'-before',label:g+' 原版本',children:computed.before[g]||0},{key:g+'-after',label:'草稿预览',children:computed.after[g]||0}])}/>
     </Modal>
   </div>
 </PageShell>;
}