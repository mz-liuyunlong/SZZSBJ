import {useState} from 'react';
import './newProductManualRisk.css';

export type ManualRiskCode =
  | '无' | '资金占用率高' | '广告数据骤变' | '季节性（一般）' | '低价依赖'
  | 'ROI低（Pass）' | 'ROI低（评级上限）' | '季节性（强）' | '侵权风险' | '合规风险'
  | '供应链风险' | '质量风险' | '价格风险' | '退货风险' | '平台风险';

type Item = {id:ManualRiskCode;label:string;severe:boolean;basis:string;result:string};
const riskItems:Item[] = [
  {id:'无',label:'无',severe:false,basis:'人工确认没有以下其他风险条件',result:'不增加人工风险标记'},
  {id:'资金占用率高',label:'资金占用率高',severe:false,basis:'订货周期 > 20 天',result:'人工复核（原配置普通扣分）'},
  {id:'广告数据骤变',label:'广告数据骤变',severe:false,basis:'需人工核对广告指标变化原因；原配置未给出量化阈值',result:'人工复核'},
  {id:'季节性（一般）',label:'季节性（一般）',severe:false,basis:'淡季销量明显低于旺季',result:'人工复核（原配置普通扣分）'},
  {id:'低价依赖',label:'低价依赖',severe:false,basis:'同质化严重，依赖极低售价',result:'人工复核（原配置普通扣分）'},
  {id:'ROI低（Pass）',label:'ROI低',severe:true,basis:'复核后 ROI < 0.5',result:'Pass'},
  {id:'ROI低（评级上限）',label:'ROI低',severe:true,basis:'0.5 ≤ ROI < 0.8',result:'最多 B 级'},
  {id:'季节性（强）',label:'季节性（强）',severe:true,basis:'淡季销量不足旺季30%，持续超过3个月',result:'Pass'},
  {id:'侵权风险',label:'侵权风险',severe:true,basis:'品牌词 / 专利 / 版权风险无法解决',result:'Pass'},
  {id:'合规风险',label:'合规风险',severe:true,basis:'认证、禁售或敏感类目风险无法解决',result:'Pass'},
  {id:'供应链风险',label:'供应链风险',severe:true,basis:'仅有单一货源',result:'最多 B 级'},
  {id:'质量风险',label:'质量风险',severe:true,basis:'10单内出现明显质量投诉',result:'Pass'},
  {id:'价格风险',label:'价格风险',severe:true,basis:'恢复正常售价后无竞争力',result:'最多 C 级'},
  {id:'退货风险',label:'退货风险',severe:true,basis:'天然高退货产品',result:'最多 B 级'},
  {id:'平台风险',label:'平台风险',severe:true,basis:'容易触发审核、下架或违规',result:'最多 C 级'},
];

interface Props {onChange:(selected:ManualRiskCode[])=>void; disabled?:boolean}
export default function NewProductManualRisk({onChange,disabled=false}:Props){
  const [selected,setSelected]=useState<ManualRiskCode[]>([]);
  const [hover,setHover]=useState<ManualRiskCode|null>(null);
  const active=riskItems.find(x=>x.id===(hover??selected[selected.length-1]));
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
      <div className="np-manual-risk-legend"><i className="normal"/>普通扣分 <i className="severe"/>高风险</div>
    </header>
    <div className="np-manual-risk-grid" role="group" aria-label="人工风险条件（必填）">
      {riskItems.map(x=><button type="button" key={x.id}
        role="checkbox" aria-checked={selected.includes(x.id)}
        aria-label={x.label+(x.label==='ROI低'?'：'+x.result:'')}
        disabled={disabled}
        className={'np-manual-risk-choice'+(selected.includes(x.id)?' checked':'')}
        onClick={()=>choose(x.id)} onMouseEnter={()=>setHover(x.id)}
        onMouseLeave={()=>setHover(null)} onFocus={()=>setHover(x.id)} onBlur={()=>setHover(null)}>
        <span className="np-manual-risk-checkbox" aria-hidden="true">{selected.includes(x.id)?'✓':''}</span>
        <span className="np-manual-risk-name">{x.label}</span>
        {x.id!=='无'&&<i className={x.severe?'severe':'normal'} aria-hidden="true"/>}
      </button>)}
    </div>
    <div className="np-manual-risk-description" aria-live="polite">
      {active? <><b className={active.severe?'severe':''}>{active.label}</b>
        <span>{active.basis}</span><strong>{active.result}</strong></>
       : <span className="np-manual-risk-help">将鼠标移至上方风险条件，查看对应的判断依据及处理结果。</span>}
    </div>
  </section>;
}
