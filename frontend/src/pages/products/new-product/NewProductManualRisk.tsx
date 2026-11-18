import {useState} from 'react';
import type {RiskConditionRule} from './NewProductRulesModel';
import type {SystemRiskDisplay} from './newProductBusinessApi';
import './newProductManualRisk.css';

export type ManualRiskCode =
  | '无' | '资金占用率高' | '季节性（一般）' | '低价依赖'
  | 'ROI低（Pass）' | 'ROI低（评级上限）' | '季节性（强）' | '侵权风险' | '合规风险'
  | '供应链风险' | '质量风险' | '价格风险' | '退货风险' | '平台风险';

type Item = {id:ManualRiskCode;label:string;severe:boolean;basis:string;result:string};
const riskItems:Item[] = [
  {id:'无',label:'无',severe:false,basis:'人工确认没有以下其他风险条件',result:'不增加人工风险标记'},
  {id:'资金占用率高',label:'资金占用率高',severe:false,basis:'订货周期 > 20 天',result:'人工复核'},
  {id:'季节性（一般）',label:'季节性（一般）',severe:false,basis:'淡季销量明显低于旺季',result:'人工复核'},
  {id:'低价依赖',label:'低价依赖',severe:false,basis:'同质化严重，依赖极低售价',result:'人工复核'},
  {id:'ROI低（Pass）',label:'ROI严重偏低',severe:true,basis:'复核后 ROI < 0.5',result:'Pass'},
  {id:'ROI低（评级上限）',label:'ROI偏低',severe:true,basis:'0.5 ≤ ROI < 0.8',result:'最多 B 级'},
  {id:'季节性（强）',label:'季节性（强）',severe:true,basis:'淡季销量不足旺季30%，持续超过3个月',result:'Pass'},
  {id:'侵权风险',label:'侵权风险',severe:true,basis:'品牌词 / 专利 / 版权风险无法解决',result:'Pass'},
  {id:'合规风险',label:'合规风险',severe:true,basis:'认证、禁售或敏感类目风险无法解决',result:'Pass'},
  {id:'供应链风险',label:'供应链风险',severe:true,basis:'仅有单一货源',result:'最多 B 级'},
  {id:'质量风险',label:'质量风险',severe:true,basis:'10单内出现明显质量投诉',result:'Pass'},
  {id:'价格风险',label:'价格风险',severe:true,basis:'恢复正常售价后无竞争力',result:'最多 C 级'},
  {id:'退货风险',label:'退货风险',severe:true,basis:'天然高退货产品',result:'最多 B 级'},
  {id:'平台风险',label:'平台风险',severe:true,basis:'容易触发审核、下架或违规',result:'最多 C 级'},
];

interface Props {
  onChange:(selected:ManualRiskCode[])=>void;
  disabled?:boolean;
  systemRiskRules:RiskConditionRule[];
  systemRiskDisplay?:SystemRiskDisplay|null;
  riskVersion:number;
  riskLoaded:boolean;
}
export default function NewProductManualRisk({
  onChange,disabled=false,systemRiskRules,systemRiskDisplay,riskVersion,riskLoaded
}:Props){
  const [selected,setSelected]=useState<ManualRiskCode[]>([]);
  const [hover,setHover]=useState<string|null>(null);
  const systemItems=systemRiskRules
    .filter(x=>x.source==="system")
    .map(x=>{
      const verified=systemRiskDisplay?.rules.find(r=>r.code===x.code);
      // Fail closed on missing or mismatched server/config evidence.
      const status=riskLoaded && verified &&
        systemRiskDisplay?.rule_version===riskVersion &&
        verified.enabled===x.enabled
        ?verified.status:"unverified";
      const hit=status==="hit";
      const state=status==="hit"?"系统已命中"
        :status==="clear"?"系统未命中"
        :status==="disabled"?"规则未启用":"待核实";
      const basis=verified?.basis && status!=="unverified"
        ?verified.basis
        :status==="unverified"
        ?verified?.basis || "真实累计广告/利润证据尚未核实"
        :state;
      const cutoff=verified?.cutoff_la ? `；截止 ${verified.cutoff_la}（洛杉矶）`:"";
      const result=hit
        ?`最高 ${x.limit} 级（已命中；正式评级限制尚未发布）`
        :status==="clear"?"未命中，不限制等级"
        :status==="disabled"?"未启用，不限制等级"
        :"待核实，不自动限制等级";
      return {id:x.code,label:x.name,severe:true,basis:`${state}：${basis}${cutoff}`,
        result,hit};
    });
  const focusId=hover??systemItems.find(x=>x.hit)?.id??selected[selected.length-1];
  const active=[...riskItems,...systemItems]
    .find(x=>x.id===focusId);
  const choose=(id:ManualRiskCode)=>{
    if(disabled)return;
    let next:ManualRiskCode[];
    if(id==='无')next=selected.length===1 && selected[0]==='无'?[]:['无'];
    else if(selected.includes(id))next=selected.filter(x=>x!==id);
    else next=[...selected.filter(x=>x!=='无'),id];
    setSelected(next);
    onChange(next);
  };
  return <section className="np-manual-risk" aria-label="风险条件">
    <header className="np-manual-risk-header">
      <strong>风险条件 <span aria-hidden="true">*</span></strong>
      <div className="np-manual-risk-legend"><i className="normal"/>一般风险 <i className="severe"/>高风险</div>
    </header>
    <div className="np-manual-risk-grid" role="group" aria-label="人工风险条件（必填）">
      {riskItems.map(x=><button type="button" key={x.id}
        role="checkbox" aria-checked={selected.includes(x.id)}
        aria-label={x.label+(x.id.startsWith('ROI低')?'：'+x.result:'')}
        disabled={disabled}
        className={'np-manual-risk-choice'+(selected.includes(x.id)?' checked':'')}
        onClick={()=>choose(x.id)} onMouseEnter={()=>setHover(x.id)}
        onMouseLeave={()=>setHover(null)} onFocus={()=>setHover(x.id)} onBlur={()=>setHover(null)}>
        <span className="np-manual-risk-checkbox" aria-hidden="true">{selected.includes(x.id)?'✓':''}</span>
        <span className="np-manual-risk-name">{x.label}</span>
        {x.id!=='无'&&<i className={x.severe?'severe':'normal'} aria-hidden="true"/>}
      </button>)}
      {systemItems.map(x=><div key={x.id}
        className="np-manual-risk-choice"
        role="checkbox"
        aria-checked={x.hit}
        aria-readonly="true"
        tabIndex={0}
        aria-label={`${x.label}：${x.basis}；${x.result}`}
        style={{cursor:"default"}}
        onMouseEnter={()=>setHover(x.id)}
        onMouseLeave={()=>setHover(null)}
        onFocus={()=>setHover(x.id)}
        onBlur={()=>setHover(null)}>
        <span className="np-manual-risk-checkbox" aria-hidden="true"
          style={{backgroundColor:x.hit?"#d1d5db":"#eef0f3",borderColor:"#aeb6c4",color:"#4b5563"}}>{x.hit?"✓":""}</span>
        <span className="np-manual-risk-name">{x.label}</span>
        <i className="severe" aria-hidden="true"/>
      </div>)}
    </div>
    <div className="np-manual-risk-description" aria-live="polite">
      {active? <><b className={active.severe?'severe':''}>{active.label}</b>
        <span>{active.basis}</span><strong>{active.result}</strong></>
       : <span className="np-manual-risk-help">将鼠标移至上方风险条件，查看对应的判断依据及处理结果。</span>}
    </div>
  </section>;
}
