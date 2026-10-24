import {useMemo,useState} from 'react';
import {Alert,Button,Card,Descriptions,Form,Input,InputNumber,Modal,Space,Switch,Tag,message} from 'antd';
import {DiffOutlined} from '@ant-design/icons';
import {ProTable} from '@ant-design/pro-components';
import {analyzeKeyword,initialRules,ruleErrors} from '@/features/keyword-planning/model';
import {useKeywordStore} from '@/features/keyword-planning/store';
import type {RuleConfig,RuleHistory} from '@/features/keyword-planning/types';
import './KeywordRulesPage.css';
type Group='weights'|'thresholds'|'limits'|'asin'|'bid'|'naming'|'listing'|'export';
const labels:Record<Group,string>={weights:'评分权重',thresholds:'分级阈值',limits:'投放名额',asin:'Amazon 参考',bid:'出价预算',naming:'Campaign 命名',listing:'Listing 规则',export:'Excel 配置'};
const fields:Record<Group,Array<{key:string;label:string;description?:string;step?:number}>>={
  weights:[{key:'match',label:'商品相关性权重'},{key:'intent',label:'搜索意图权重'},{key:'coverage',label:'竞品 ASIN 覆盖权重'},{key:'root',label:'核心词根权重'},{key:'market',label:'市场参考数据权重'}],
  thresholds:[{key:'p0',label:'P0 最低分'},{key:'p1',label:'P1 最低分'},{key:'p2',label:'P2 最低分'}],
  limits:[{key:'p0',label:'P0 词数'},{key:'p1',label:'P1 词数'},{key:'p2',label:'P2 候选词数'},{key:'exact',label:'Exact 最大投放数'},{key:'broad',label:'Broad 最大投放数'},{key:'roots',label:'Broad 最大词根数'}],
  asin:[{key:'min',label:'最少不同 ASIN 数'},{key:'recommend',label:'建议不同 ASIN 数'},{key:'max',label:'推荐最多 ASIN 数'},{key:'titleWeight',label:'Title 命中权重',step:0.1},{key:'featuresWeight',label:'Key Features 命中权重',step:0.1}],
  bid:[{key:'exact',label:'模拟 Exact Bid (USD)',step:0.01},{key:'broad',label:'模拟 Broad Bid (USD)',step:0.01},{key:'auto',label:'模拟 Auto Bid (USD)',step:0.01},{key:'dailyBudget',label:'模拟每日预算 (USD)',step:0.5},{key:'startDate',label:'美国开始日期'}],
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
export function KeywordRulesPanel(){
 const {rules,draft,history,startDraft,changeDraft,publishDraft,resetDraft,rollback,keywords,skus}=useKeywordStore();
 const [tab,setTab]=useState('score');const [compare,setCompare]=useState(false);const [testOpen,setTestOpen]=useState(false);
 const shown=draft||rules;
 const errors=useMemo(()=>ruleErrors(shown),[shown]);
 const computed=useMemo(()=>{
  const keys=Object.values(keywords).slice(0,300);const sku=skus[0];
  const stats=(r:RuleConfig)=>keys.reduce<Record<string,number>>((acc,k)=>{if(!sku)return acc;const grade=analyzeKeyword(k,sku,r).grade;acc[grade]=(acc[grade]||0)+1;return acc},{}) ;
  return {sample:keys.length,before:stats(rules),after:stats(shown)};
 },[keywords,rules,shown,skus]);
 const group=(g:Group)=>{
  const obj=shown[g] as unknown as Record<string,string|number|boolean>;
  return <Card size="small" title={labels[g]} key={g}><div className="keyword-rules__fields">{fields[g].map(x=>{
   const value=obj[x.key];const isText=typeof value==='string';const area=isText&&String(value).includes('\n')||x.key==='sheetNames'||x.key==='columnNames';
   return <Form.Item key={x.key} label={x.label} className={area?'keyword-rules__wide':''}>
      {area?<Input.TextArea rows={4} disabled={!draft} value={String(value)} onChange={e=>draft&&changeDraft(editField(draft,g,x.key,e.target.value))}/>:isText?<Input type={x.key==='startDate'?'date':undefined} disabled={!draft} value={String(value??'')} onChange={e=>draft&&changeDraft(editField(draft,g,x.key,e.target.value))}/>:<InputNumber style={{width:'100%'}} disabled={!draft} step={x.step||1} value={Number(value)} min={0} onChange={n=>draft&&changeDraft(editField(draft,g,x.key,n??0))}/>}
   </Form.Item>})}</div></Card>
 };
 const confirmPublish=()=>{if(!draft)return message.warning('请先创建草稿');if(errors.length)return message.error('请先处理规则校验错误');
  let reason='运营规则调整';Modal.confirm({title:'发布本地规则版本',content:<><Alert type="warning" message="这是浏览器内 仅本地 发布，不会更改数据库、历史分析或 Walmart 广告。"/><Input style={{marginTop:12}} placeholder="修改原因" defaultValue={reason} onChange={e=>{reason=e.target.value}}/></>,okText:'发布本地规则版本',onOk:()=>{const err=publishDraft(reason);if(err)message.error(err);else message.success('本地规则版本已发布，已有分析结果不会自动重算')}})};
 return <>
   <div className="keyword-rules kw-v2-rules">
     <Alert showIcon type="info" message={`当前发布版本：V${rules.version}。所有业务参数均可修改；规则只影响新分析，已有 SKU 的历史等级不自动覆盖。`}/>
     <div className="kw-v2-rule-actions"><Space wrap><Button type="primary" onClick={()=>{startDraft();message.success('已创建独立草稿')}}>{draft?'重新从当前版本创建草稿':'创建规则草稿'}</Button><Button disabled={!draft} onClick={()=>setCompare(true)} icon={<DiffOutlined/>}>比较修改</Button><Button disabled={!draft} onClick={()=>setTestOpen(true)}>规则预览</Button><Button disabled={!draft} onClick={()=>{if(!draft)return;changeDraft({...structuredClone(initialRules),version:rules.version});message.info('已将默认参数载入草稿')}}>草稿恢复默认</Button><Button disabled={!draft} onClick={resetDraft}>放弃草稿</Button><Button type="primary" disabled={!draft||errors.length>0} onClick={confirmPublish}>发布本地版本</Button><Button disabled={!draft} onClick={()=>message.success("规则草稿已保存在当前会话（仅本地）")}>保存草稿</Button></Space></div>
     {errors.length?<Alert type="error" message="规则校验未通过" description={errors.join('；')} showIcon/>:draft?<Alert type="success" message="草稿校验通过，可以规则预览。" showIcon/>:<Alert type="warning" message="当前为只读已发布版本。要修改请先创建草稿。"/>}
     <div className="kw-v2-rule-layout">
      <nav className="kw-v2-rule-nav" aria-label="规则业务分组">
       {[['score','▦ 评分与分级'],['amazon','⌕ Amazon 竞品埋词'],['limits','⊞ 投放名额与结构'],['risk','⚠ 风险与品牌隔离'],['defaults','$ 广告执行默认值'],['listing','T Listing 文案规则'],['governance','▣ 版本与权限']].map(([value,label])=><Button key={value} block type={tab===value?'primary':'text'} onClick={()=>setTab(value)}>{label}</Button>)}
      </nav>
      <main className="kw-v2-rule-main">
       <div className="kw-v2-rule-banner"><div><strong>{draft?'当前正在编辑规则草稿':`当前生效规则 V${rules.version}.0`}</strong><p>{draft?'草稿待回测与确认；发布只影响新分析':'已发布版本只读；请先创建草稿，再编辑并回测'}</p></div><Tag color={draft?'gold':'green'}>{draft?'待发布草稿':'已发布'}</Tag></div>
       {tab==='score'?<>{group('weights')}{group('thresholds')}<Alert type="info" message="评分权重总和必须为 100；历史关键词分数保持原版本，不自动重算。"/></>:null}
       {tab==='amazon'?<>{group('asin')}<Alert type="warning" message="ASIN 覆盖需要标题、五点、描述文本；未接入 Amazon API 时，只允许人工或人工提供的文案。"/></>:null}
       {tab==='limits'?<>{group('limits')}<Card title="投放结构说明" size="small"><Descriptions column={1} bordered size="small" items={[{key:'exact',label:'Exact',children:'按等级优先级选取；不允许硬风险与品牌词自动投放'},{key:'broad',label:'Broad',children:'需区分核心词根与安全长尾，超额词保留候选'},{key:'export',label:'五表导出',children:'正式 Walmart Bulk 模板待接入，不等同本地导出'}]}/></Card></>:null}
       {tab==='risk'?<Card title="风险与品牌隔离" size="small"><Form.Item label="风险词（每行一个）"><Input.TextArea rows={9} disabled={!draft} value={shown.riskWords} onChange={e=>draft&&changeDraft({...draft,riskWords:e.target.value})}/></Form.Item><Alert type="info" message="硬风险与品牌识别为本地规则，人工可检查，不应未经审核直接上传真实关键词。"/></Card>:null}
       {tab==='defaults'?<>{group('bid')}{group('naming')}</>:null}
       {tab==='listing'?<>{group('listing')}<Card title="Listing 内容配置" size="small"><Form.Item label="允许生成 Description 草稿"><Switch checked={shown.listing.description} disabled={!draft} onChange={checked=>draft&&changeDraft({...draft,listing:{...draft.listing,description:checked}})}/></Form.Item></Card>{group('export')}<Alert type="warning" message="这里只配置本地导出字段，不声明与 Walmart 官方批量上传模板兼容。"/></>:null}
       {tab==='governance'?<Card title="版本与权限" size="small"><Descriptions column={1} bordered size="small" items={[{key:'version',label:'当前版本',children:`V${rules.version}.0`},{key:'draft',label:'编辑权限',children:'本地本地会话允许编辑；真实权限由后端 RBAC 管理'},{key:'history',label:'历史结果',children:'已分析的 SKU 结果不随新版本自动覆盖'}]}/></Card>:null}
       <Card size="small" className="kw-v2-rule-history" title="规则版本历史" extra={<Tag color="blue">{history.length} 条</Tag>}><ProTable<RuleHistory>
        rowKey="version"
        search={false} options={false} toolBarRender={false}
        pagination={false} size="small" scroll={{x:680}}
        dataSource={history}
        columns={[
          {title:'版本',dataIndex:'version',width:95,render:(_,h)=>`V${h.version}.0`},
          {title:'时间',dataIndex:'at',width:180},
          {title:'修改原因',dataIndex:'reason'},
          {title:'操作',key:'action',width:120,render:(_,h)=><Button type="link" onClick={()=>{rollback(h.version);message.info('旧版本已复制到草稿，未修改已发布版本')}}>复制为草稿</Button>}
        ]}
      /></Card>
      </main>
     </div>
     <Modal title="草稿与当前版本差异" open={compare} onCancel={()=>setCompare(false)} footer={<Button onClick={()=>setCompare(false)}>关闭</Button>} width={820}>
       <Alert showIcon type="info" message="完整业务规则快照对照（本地）"/><div className="keyword-rules__diff"><pre>{JSON.stringify(rules,null,2)}</pre><pre>{JSON.stringify(shown,null,2)}</pre></div>
     </Modal>
     <Modal title="规则预览（最多前 300 个已导入关键词）" open={testOpen} onCancel={()=>setTestOpen(false)} footer={<Button onClick={()=>setTestOpen(false)}>关闭</Button>}>
      <Alert showIcon type="warning" message={`使用当前导入的 ${computed.sample} 个关键词进行规则预览；不包含真实广告表现或 AI 模型推理。`}/>
      <Descriptions bordered column={3} style={{marginTop:15}} items={(['P0','P1','P2','复查','不投放'] as const).flatMap(g=>[{key:g+'-before',label:g+' 原版本',children:computed.before[g]||0},{key:g+'-after',label:'草稿预览',children:computed.after[g]||0}])}/>
     </Modal>
   </div>
 </>;
}
