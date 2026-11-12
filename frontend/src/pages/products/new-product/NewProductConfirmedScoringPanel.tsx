/** PR337_CONFIRMED_SCORE_RULES_V4 - preset, directly editable business thresholds */
import { Alert, InputNumber, Select, Tabs, Tag, Tooltip } from "antd";
import { useState } from "react";
import type { ReactNode } from "react";
import type { Product } from "./nativeData";
import type { RuleDraft } from "./NewProductRulesModel";
import { calculateConfirmedScore, confirmedOverallWeights, demoFactsFromProduct, validateScoringParameters,
  type ScoringFacts, type ScoringParameters, type DimensionResult, type Dimension } from "./NewProductConfirmedScoring";

interface Props {draft:RuleDraft;onChange:(draft:RuleDraft)=>void;products:Product[]}
const fmt=(v:number|null)=>v===null?'待接数据':v.toFixed(2);
const examples:{value:string;label:string;facts:ScoringFacts}[]=[
  {value:'sample',label:'完整模拟样本（只用于演示公式）',facts:{
    firstOrderDay:2,elapsedDays:14,ordersInWindow:14,adStatus:'active',adClicks:50,adSpend:29,adOrders:4,adRevenue:100,
    roi:1,grossMarginPct:17.5,validSoldUnits:20,validOrders:14,singleUnitOrders:12,marketScore:7}},
  {value:'organic',label:'模拟：未投广告但有自然订单',facts:{
    firstOrderDay:2,elapsedDays:14,ordersInWindow:12,adStatus:'not_run',adClicks:null,adSpend:null,adOrders:null,adRevenue:null,
    roi:1.2,grossMarginPct:22,validSoldUnits:14,validOrders:12,singleUnitOrders:11,marketScore:8}},
  {value:'no-orders',label:'模拟：14天未投广告、无订单',facts:{
    firstOrderDay:null,elapsedDays:14,ordersInWindow:0,adStatus:'not_run',adClicks:null,adSpend:null,adOrders:null,adRevenue:null,
    roi:null,grossMarginPct:null,validSoldUnits:0,validOrders:0,singleUnitOrders:0,marketScore:7}},
];
function Field({label,tip,example,unit,value,min=0,max,step=1,onChange}:{label:string;tip:string;example:string;unit?:string;
  value:number;min?:number;max?:number;step?:number;onChange:(value:number)=>void}){
  return <label className="np-confirm-field"><span className="np-confirm-field-label">{label}
    <Tooltip title={<div>{tip}<div style={{marginTop:6,opacity:.9}}>举个例子：{example}</div></div>} placement="top">
      <span tabIndex={0} role="img" aria-label={`${label}说明`} className="np-confirm-help">?</span>
    </Tooltip></span>
    <InputNumber aria-label={label} value={value} min={min} max={max} step={step} controls={false} addonAfter={unit} style={{width:'100%'}}
      onChange={next=>{if(next!==null)onChange(next)}}/>
  </label>;
}
function Group({title,description,children}:{title:string;description?:string;children:ReactNode}){
  return <section className="np-confirm-group"><h3>{title}</h3>{description&&<p>{description}</p>}<div className="np-confirm-field-grid">{children}</div></section>;
}
function SourceCopy({label,lines}:{label:string;lines:string[]}){
  return <details className="np-confirm-origin"><summary>{label}（原始中文说明，仅供对照）</summary>
    {lines.map((line,index)=><p key={`${index}-${line}`}>{['9–10 分','7–8 分','5–6 分','3–4 分','0–2 分'][index]}：{line}</p>)}
  </details>;
}
function DimensionPreview({title,row}:{title:string;row:DimensionResult}){
  return <div className="np-confirm-preview-card"><div className="np-confirm-preview-heading"><strong>{title}</strong>
    <b>{fmt(row.score)}{row.score!==null?' / 10':''}</b></div>
    {row.details.map(d=><div key={d.name} className="np-confirm-preview-line"><span>{d.name}：{d.raw}</span><b>{fmt(d.score)}</b></div>)}
    {row.missing.length>0&&<p className="np-confirm-missing">缺失：{row.missing.join('、')}</p>}
    {row.note&&<p className="np-confirm-note">{row.note}</p>}
  </div>;
}
export default function NewProductConfirmedScoringPanel({draft,onChange,products}:Props){
  const p=draft.confirmedScoring;
  const [previewType,setPreviewType]=useState('sample');
  const [productId,setProductId]=useState(products[0]?.id??'');
  const selected=products.find(x=>x.id===productId)??products[0];
  const facts=previewType==='current'&&selected?demoFactsFromProduct(selected):
    examples.find(x=>x.value===previewType)?.facts??examples[0].facts;
  const evaluation=calculateConfirmedScore(facts,p,draft.weights??confirmedOverallWeights,
    {penalties:draft.penalties,vetoes:draft.vetoes,confirmedRiskNames:[]});
  const setValue=<K extends keyof ScoringParameters>(section:K,key:keyof ScoringParameters[K],value:number)=>{
    const next={...p,[section]:{...p[section],[key]:value}};
    onChange({...draft,confirmedScoring:next});
  };
  const field=<K extends keyof ScoringParameters,>(section:K,key:keyof ScoringParameters[K],label:string,tip:string,example:string,unit?:string,step?:number)=>
    <Field key={`${section}-${String(key)}`} label={label} tip={tip} example={example} unit={unit}
      value={p[section][key] as number} step={step??1} onChange={v=>setValue(section,key,v)}/>;
  const market=<div className="np-confirm-tab"><Alert type="info" showIcon message="市场竞争维度仍由运营人工填写 0–10 分，原来的中文标准不自动转成计算公式。"/>
    <Group title="市场竞争（人工）" description="评分时综合判断竞品、价格、Review 和差异化空间；必须填写评分依据。">
      <div className="np-confirm-market-copy">{draft.scoreCriteria.market.map((line,i)=><p key={i}><b>{['9–10 分','7–8 分','5–6 分','3–4 分','0–2 分'][i]}</b>{line}</p>)}</div>
    </Group></div>;
  const speed=<div className="np-confirm-tab">
    <Group title="首单速度（40%）" description="从首次 WFS 可售起算自然日。未出单时显示暂定 0 分；第 14 天仍未出首单就是 0 分。">
      {field('speed','firstFullDays','首单满分天数','在这段时间内出第一单，就拿首单速度的 10 分。','设置3天，第2天和第3天出首单都得10分。','天')}
      {field('speed','firstZeroDays','首单零分天数','到了这一天才出第一单，首单速度得 0 分；中间按比例计算小数。','设置14天，第7天出首单约6.36分。','天')}
      {field('speed','firstWeight','首单速度内部权重','首单快慢占整个出单速度的多少，不是总评分的百分比。','填40，首单子项得8分时贡献3.2分。','%')}
    </Group>
    <Group title="观察期有效订单量（60%）" description="正常按14个自然日计，不因分批入库或断货延长。实时计算，观察结束保留14天窗口。">
      {field('speed','observationDays','订单观察周期','从首次可售开始，往后数多少天的有效订单。','设置14天，只统计首次可售起14天内的有效订单。','天')}
      {field('speed','targetOrders','订单满分目标','观察期内有多少笔不同的有效成交订单，订单子项就得10分；不是卖了多少件。','设置20单，当前12单时订单子项得6分。','单')}
      {field('speed','ordersWeight','订单量内部权重','订单量好不好，占整个出单速度得分的多少。','填60，订单子项得6分时贡献3.6分。','%')}
    </Group><SourceCopy label="出单速度" lines={draft.scoreCriteria.speed}/></div>;
  const ad=<div className="np-confirm-tab">
    <Group title="ACOS（40%）" description="ACOS越低越好：广告花费除以广告归因销售额。">
      {field('ad','acosFull','ACOS满分阈值','ACOS低于或等于这个百分比，该项得10分。','20%及以下得10分；29%得8.20分。','%',.1)}
      {field('ad','acosZero','ACOS零分阈值','ACOS达到或超过这个百分比，该项得0分。','设置70%，70%以上得0分。','%',.1)}
      {field('ad','acosWeight','ACOS内部权重','在广告有效性里，ACOS占多少分量。','ACOS得8.2分，权重40%，贡献3.28分。','%')}
    </Group>
    <Group title="CPC（20%）" description="CPC越低越好：广告花费除以广告点击次数，单位美元。">
      {field('ad','cpcFull','CPC满分阈值','一次广告点击花费不超过多少美元，就得10分。','设置$0.80，CPC $0.75 得10分。','$',.01)}
      {field('ad','cpcZero','CPC零分阈值','一次点击花费到多少美元，该项就得0分。','设置$2.00，CPC $1.00 得8.33分。','$',.01)}
      {field('ad','cpcWeight','CPC内部权重','CPC只是辅助项，占广告有效性的比例。','填20，CPC得5分时贡献1分。','%')}
    </Group>
    <Group title="CVR（40%）" description="CVR越高越好：广告归因订单数除以广告点击数。">
      {field('ad','cvrZero','CVR零分阈值','转化率低于或等于这个值，CVR这项就是0分。','设置2%，100次点击只有1单，CVR 1%得0分。','%',.1)}
      {field('ad','cvrFull','CVR满分阈值','转化率达到或超过这个值，CVR这项就是10分。','设置8%，100次点击成交8单，得10分。','%',.1)}
      {field('ad','cvrWeight','CVR内部权重','CVR占广告有效性内部的分量。','填40，CVR得5分时贡献2分。','%')}
    </Group>
    <Group title="点击样本" description="点击量不够仍参与评分，只提醒样本偏少。">
      {field('ad','minClicks','最低有效点击量','达到多少次广告点击，才能不再提示样本不足；不影响得分。','设20次，只有12次点击也计算广告分，但提示样本不足。','次')}
    </Group><Alert type="info" showIcon message="有点击和花费但没有广告归因成交：ACOS与CVR各0分，CPC正常计分。确认未投广告：排除广告20%并将其他维度重新归一化。数据没同步不等于未投广告。"/>
    <SourceCopy label="广告有效性" lines={draft.scoreCriteria.ad}/></div>;
  const profit=<div className="np-confirm-tab">
    <Group title="ROI（60%）" description="ROI数值采用系统既有财务口径，开发接数据前必须核验公式和成本来源。">
      {field('profit','roiZero','ROI零分阈值','ROI低于或等于多少，ROI评分就是0分。','设置0.5，ROI只有0.4得0分。',undefined,.01)}
      {field('profit','roiFull','ROI满分阈值','ROI达到或超过多少，ROI评分就是10分。','设置1.5，ROI=1.0得5分。',undefined,.01)}
      {field('profit','roiWeight','ROI内部权重','ROI占利润空间得分的比例。','填60，ROI得5分贡献3分。','%')}
    </Group>
    <Group title="毛利率（40%）" description="毛利率用现有财务定义；不要把广告ROAS当作ROI。">
      {field('profit','marginZero','毛利率零分阈值','毛利率低于或等于多少，毛利率子项为0分。','设置10%，毛利率8%得0分。','%',.1)}
      {field('profit','marginFull','毛利率满分阈值','毛利率达到多少，毛利率子项为10分。','设置25%，毛利率17.5%得5分。','%',.1)}
      {field('profit','marginWeight','毛利率内部权重','毛利率占利润空间得分的比例。','填40，毛利率得5分贡献2分。','%')}
    </Group><SourceCopy label="利润空间" lines={draft.scoreCriteria.profit}/></div>;
  const trust=<div className="np-confirm-tab">
    <Group title="有效销售件数（60%）" description="按实际销售件数统计；不是订单笔数。一单买5件，就是5件、1单。">
      {field('trust','targetUnits','满分有效销售件数','卖出多少件，有效销售件数子项得10分。','设置20件，卖出10件就是5分。','件')}
      {field('trust','unitsWeight','件数内部权重','销售件数占数据可信度的多少。','填60，件数得5分贡献3分。','%')}
    </Group>
    <Group title="单件订单占比（40%）" description="有效订单里，恰好只买本商品1件的订单占比。">
      {field('trust','singleRatioZero','占比零分阈值','单件成交订单太少时，占比子项得0分。','10单里只有3单是单件订单，占比30%，得0分。','%',.1)}
      {field('trust','singleRatioFull','占比满分阈值','单件订单占比达到多少，得10分。','10单里9单都只买1件，占比90%，得10分。','%',.1)}
      {field('trust','singleRatioWeight','占比内部权重','单件订单占比占可信度的多少。','填40，占比得5分贡献2分。','%')}
    </Group><SourceCopy label="数据可信度" lines={draft.scoreCriteria.trust}/></div>;
  const names:Record<Dimension,string>={market:'市场竞争',speed:'出单速度',ad:'广告有效性',profit:'利润空间',trust:'数据可信度'};
  const preview=<div className="np-confirm-tab"><h3>评分计算预览</h3>
    <p>可以先用完整模拟样本验证公式；选择本地商品时只使用来源明确的数据，缺首单日期、广告归因或订单结构就显示待接数据，不会编造满分。</p>
    <Select style={{width:'100%',marginBottom:10}} value={previewType} onChange={setPreviewType} options={[
      ...examples.map(x=>({value:x.value,label:x.label})),{value:'current',label:'查看当前商品实际可用字段（部分缺失）'}]}/>
    {previewType==='current'&&<Select style={{width:'100%',marginBottom:10}} value={selected?.id} onChange={setProductId}
      options={products.map(x=>({value:x.id,label:`${x.sku} · ${x.name}`}))}/>}
    <div className="np-confirm-preview-grid">{(Object.keys(names) as Dimension[]).map(key=><DimensionPreview key={key} title={names[key]} row={evaluation.dimensions[key]}/>)}</div>
    <div className="np-confirm-result"><span>综合得分</span><b>{fmt(evaluation.total)} / 10</b>
      <span>最终评级：{evaluation.grade??'待数据完整'}</span>
      {evaluation.adExcluded&&<Tag color="blue">确认未投广告 · 重新分配权重</Tag>}
      {evaluation.status==='continue_observation'&&<Tag color="orange">14天无广告无订单 · 继续观察</Tag>}</div>
    {evaluation.reasons.length>0&&<Alert type="warning" showIcon message="未形成正式评级" description={evaluation.reasons.join('；')}/>}
    {evaluation.appliedVetoes.length>0&&<Alert type="error" showIcon message={`评级限制：${evaluation.appliedVetoes.join('、')}`}/>}
    <p className="np-confirm-note">此处为前端计算预览。未接入的真实指标不会参与正式计算；已提交审批、已批准的历史记录不得重新覆盖。</p>
  </div>;
  const warning=validateScoringParameters(p);
  return <div className="np-rule-panel np-confirmed-scoring">
    <div className="np-rule-intro"><h2>评分标准</h2><p>市场人工评分、四个自动评分维度分开配置。所有阈值预置，直接改数字即可；鼠标放在问号上可以查看大白话例子。</p></div>
    {warning&&<Alert type="error" showIcon message={`当前参数不能保存：${warning}`} style={{marginBottom:10}}/>}
    <Tabs className="np-confirm-tabs" type="card" defaultActiveKey="speed" items={[
      {key:'market',label:'市场竞争（人工）',children:market},
      {key:'speed',label:'出单速度',children:speed},
      {key:'ad',label:'广告有效性',children:ad},
      {key:'profit',label:'利润空间',children:profit},
      {key:'trust',label:'数据可信度',children:trust},
      {key:'preview',label:'计算预览',children:preview},
    ]}/>
    <Alert type="info" showIcon message="修改评分标准不改写已提交审批或已批准的历史评分；规则正式生效后，只对允许重算的未冻结测评使用。"/>
  </div>;
}
