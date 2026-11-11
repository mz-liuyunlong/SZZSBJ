/** PR337 confirmed business scoring V4. Pure computation: no API, DOM, or data writes. */
export interface ScoringParameters {
  speed: { firstFullDays:number; firstZeroDays:number; observationDays:number; targetOrders:number; firstWeight:number; ordersWeight:number };
  ad: { acosFull:number; acosZero:number; cpcFull:number; cpcZero:number; cvrZero:number; cvrFull:number; minClicks:number; acosWeight:number; cpcWeight:number; cvrWeight:number };
  profit: { roiZero:number; roiFull:number; marginZero:number; marginFull:number; roiWeight:number; marginWeight:number };
  trust: { targetUnits:number; singleRatioZero:number; singleRatioFull:number; unitsWeight:number; singleRatioWeight:number };
}
export const confirmedScoringDefaults:ScoringParameters={
  speed:{firstFullDays:3,firstZeroDays:14,observationDays:14,targetOrders:20,firstWeight:40,ordersWeight:60},
  ad:{acosFull:20,acosZero:70,cpcFull:.8,cpcZero:2,cvrZero:2,cvrFull:8,minClicks:20,acosWeight:40,cpcWeight:20,cvrWeight:40},
  profit:{roiZero:.5,roiFull:1.5,marginZero:10,marginFull:25,roiWeight:60,marginWeight:40},
  trust:{targetUnits:20,singleRatioZero:40,singleRatioFull:90,unitsWeight:60,singleRatioWeight:40},
};
export type Dimension='market'|'speed'|'ad'|'profit'|'trust';
export type DataStatus='not_run'|'active'|'unknown';
export interface ScoringFacts {
  /** 1-based natural day from first WFS available date. Must be sourced and time-zone normalized. */
  firstOrderDay:number|null;
  /** Elapsed natural days from first WFS available date, 0 before available. */
  elapsedDays:number|null;
  /** Effective distinct orders within the FIRST observationDays natural days. */
  ordersInWindow:number|null;
  /** Explicit business distinction; never derive no-ad status just from missing rows. */
  adStatus:DataStatus;
  adClicks:number|null;
  adSpend:number|null;
  adOrders:number|null;
  adRevenue:number|null;
  roi:number|null;
  grossMarginPct:number|null;
  validSoldUnits:number|null;
  validOrders:number|null;
  singleUnitOrders:number|null;
  marketScore:number|null;
}
export interface DimensionResult { score:number|null; missing:string[]; details:Array<{name:string;raw:string;score:number|null}>; note?:string }
export interface ScoringResult {
  dimensions:Record<Dimension,DimensionResult>;
  total:number|null;
  grade:'S'|'A'|'B'|'C'|'D'|'Pass'|null;
  preliminaryGrade:'S'|'A'|'B'|'C'|'D'|null;
  adExcluded:boolean;
  adSampleInsufficient:boolean;
  status:'scored'|'preview'|'continue_observation'|'needs_market';
  reasons:string[];
  appliedVetoes:string[];
}
export type Weights=Record<Dimension,number>;
export const confirmedOverallWeights:Weights={market:15,speed:30,ad:20,profit:25,trust:10};
export const clamp=(v:number,min=0,max=10)=>Math.max(min,Math.min(max,v));
export function lowerBetter(value:number,full:number,zero:number):number{
  if(!Number.isFinite(value)||!Number.isFinite(full)||!Number.isFinite(zero)||full>=zero)throw new Error('Invalid low-better scoring inputs');
  return clamp((zero-value)/(zero-full)*10);
}
export function higherBetter(value:number,zero:number,full:number):number{
  if(!Number.isFinite(value)||!Number.isFinite(full)||!Number.isFinite(zero)||zero>=full)throw new Error('Invalid high-better scoring inputs');
  return clamp((value-zero)/(full-zero)*10);
}
const finite=(x:number|null):x is number=>x!==null&&Number.isFinite(x);
const nonnegative=(x:number|null):x is number=>finite(x)&&x>=0;
const detail=(name:string,raw:string,score:number|null)=>({name,raw,score});
const missing=(...keys:string[]):DimensionResult=>({score:null,details:[],missing:keys});
export function validateScoringParameters(p:ScoringParameters):string|null {
  const rows=[...Object.values(p.speed),...Object.values(p.ad),...Object.values(p.profit),...Object.values(p.trust)];
  if(rows.some(v=>!Number.isFinite(v)||v<0))return '评分参数必须为有效非负数字';
  if(!Number.isInteger(p.speed.firstFullDays)||p.speed.firstFullDays<1||
    !Number.isInteger(p.speed.firstZeroDays)||p.speed.firstZeroDays<=p.speed.firstFullDays||
    !Number.isInteger(p.speed.observationDays)||p.speed.observationDays<1||p.speed.observationDays>180||
    !Number.isInteger(p.speed.targetOrders)||p.speed.targetOrders<1)return '出单速度的天数、订单目标必须为有效正整数，零分天数要大于满分天数';
  if(!Number.isInteger(p.ad.minClicks)||p.ad.minClicks<1)return '最低广告点击量必须为正整数';
  if(!Number.isInteger(p.trust.targetUnits)||p.trust.targetUnits<1)return '满分销售件数必须为正整数';
  if(p.ad.acosZero<=p.ad.acosFull||p.ad.cpcZero<=p.ad.cpcFull||p.ad.cvrFull<=p.ad.cvrZero||
    p.profit.roiFull<=p.profit.roiZero||p.profit.marginFull<=p.profit.marginZero||
    p.trust.singleRatioFull<=p.trust.singleRatioZero)return '满分阈值与零分阈值顺序错误';
  if([p.ad.acosFull,p.ad.acosZero,p.ad.cvrZero,p.ad.cvrFull,p.profit.marginZero,p.profit.marginFull,p.trust.singleRatioZero,p.trust.singleRatioFull].some(x=>x>100))return '百分比阈值不可超过 100%';
  if(p.speed.firstWeight+p.speed.ordersWeight!==100||p.ad.acosWeight+p.ad.cpcWeight+p.ad.cvrWeight!==100||
    p.profit.roiWeight+p.profit.marginWeight!==100||p.trust.unitsWeight+p.trust.singleRatioWeight!==100)return '维度内部权重合计必须为100%';
  return null;
}
export function speedResult(f:ScoringFacts,p:ScoringParameters):DimensionResult {
  const s=p.speed;
  if(!nonnegative(f.elapsedDays)||!nonnegative(f.ordersInWindow))return missing('首次可售后的自然日天数','14天内有效订单数');
  if(f.firstOrderDay!==null&&(!Number.isInteger(f.firstOrderDay)||f.firstOrderDay<1))return missing('首单天数数据异常');
  if(f.firstOrderDay===null&&f.ordersInWindow>0)return missing('已有订单但首单日期缺失');
  const first=f.firstOrderDay===null?0:lowerBetter(f.firstOrderDay,s.firstFullDays,s.firstZeroDays);
  const orders=clamp(f.ordersInWindow/s.targetOrders*10);
  return {score:(first*s.firstWeight+orders*s.ordersWeight)/100,missing:[],details:[
    detail('首单天数',f.firstOrderDay===null?'尚未出单':`第${f.firstOrderDay}天`,first),
    detail(`${s.observationDays}天有效订单`,`${f.ordersInWindow}单`,orders)],
    note:f.elapsedDays<s.observationDays?'观察中·实时暂定分':'标准观察窗口评分'};
}
export function adResult(f:ScoringFacts,p:ScoringParameters):DimensionResult {
  if(f.adStatus==='not_run')return {...missing(),note:'确认未投放广告；广告维度不参与综合评分'};
  if(f.adStatus==='unknown')return missing('无法确认是未投放还是数据尚未同步');
  const {adClicks:clicks,adSpend:spend,adOrders:orders,adRevenue:revenue}=f;
  if(!nonnegative(clicks)||!nonnegative(spend)||!nonnegative(orders)||!nonnegative(revenue))return missing('广告点击、花费、归因订单或销售额缺失');
  if(clicks===0||spend===0)return missing('广告数据无有效点击或花费，请核查同步口径');
  if((orders>0&&revenue===0)||(orders===0&&revenue>0))return missing('归因订单与广告销售额不一致');
  if(orders>clicks)return missing('归因订单数大于点击数，请核查统计口径');
  const acos=orders===0?0:lowerBetter(spend/revenue*100,p.ad.acosFull,p.ad.acosZero);
  const cpc=lowerBetter(spend/clicks,p.ad.cpcFull,p.ad.cpcZero);
  const cvr=higherBetter(orders/clicks*100,p.ad.cvrZero,p.ad.cvrFull);
  return {score:(acos*p.ad.acosWeight+cpc*p.ad.cpcWeight+cvr*p.ad.cvrWeight)/100,missing:[],details:[
    detail('ACOS',orders===0?'有花费无归因成交':`${(spend/revenue*100).toFixed(2)}%`,acos),
    detail('CPC',`$${(spend/clicks).toFixed(3)}`,cpc),
    detail('CVR',`${(orders/clicks*100).toFixed(2)}%`,cvr)],
    note:clicks<p.ad.minClicks?`样本不足：${clicks}/${p.ad.minClicks}次点击（仍参与总分）`:'广告样本已达门槛'};
}
export function profitResult(f:ScoringFacts,p:ScoringParameters):DimensionResult {
  if(!finite(f.roi)||!finite(f.grossMarginPct))return missing('按系统财务口径核实的 ROI','按系统财务口径核实的毛利率');
  const roi=higherBetter(f.roi,p.profit.roiZero,p.profit.roiFull);
  const margin=higherBetter(f.grossMarginPct,p.profit.marginZero,p.profit.marginFull);
  return {score:(roi*p.profit.roiWeight+margin*p.profit.marginWeight)/100,missing:[],details:[
    detail('ROI',String(f.roi),roi),detail('毛利率',`${f.grossMarginPct}%`,margin)]};
}
export function trustResult(f:ScoringFacts,p:ScoringParameters):DimensionResult {
  if(!nonnegative(f.validSoldUnits)||!nonnegative(f.validOrders)||!nonnegative(f.singleUnitOrders))return missing('有效销售件数','有效订单笔数','单件订单笔数');
  if(!Number.isInteger(f.validSoldUnits)||!Number.isInteger(f.validOrders)||!Number.isInteger(f.singleUnitOrders)||f.singleUnitOrders>f.validOrders)return missing('订单与件数口径异常');
  if(f.validOrders===0)return {...missing('没有有效订单，单件订单占比不可计算'),details:[detail('有效销售件数',`${f.validSoldUnits}件`,0)]};
  const units=clamp(f.validSoldUnits/p.trust.targetUnits*10);
  const ratio=f.singleUnitOrders/f.validOrders*100;
  const ratioScore=higherBetter(ratio,p.trust.singleRatioZero,p.trust.singleRatioFull);
  return {score:(units*p.trust.unitsWeight+ratioScore*p.trust.singleRatioWeight)/100,missing:[],details:[
    detail('有效销售件数',`${f.validSoldUnits}件`,units),detail('单件订单占比',`${ratio.toFixed(2)}%`,ratioScore)]};
}
export interface RiskRules {
  penalties?:Array<{name:string;enabled:boolean;deduct:number}>;
  vetoes?:Array<{name:string;enabled:boolean;action:string}>;
  /** Human-verified risk names; never guess the condition from prose. */
  confirmedRiskNames?:string[];
}
function gradeFor(score:number):'S'|'A'|'B'|'C'|'D'{return score>=9?'S':score>=8?'A':score>=7?'B':score>=6?'C':'D'}
export function calculateConfirmedScore(f:ScoringFacts,p:ScoringParameters,weights:Weights=confirmedOverallWeights,risks?:RiskRules):ScoringResult {
  const market:DimensionResult=finite(f.marketScore)&&f.marketScore>=0&&f.marketScore<=10?
    {score:f.marketScore,missing:[],details:[detail('人工市场分',`${f.marketScore}/10`,f.marketScore)]}:missing('人工市场竞争评分');
  const dimensions={market,speed:speedResult(f,p),ad:adResult(f,p),profit:profitResult(f,p),trust:trustResult(f,p)};
  const adExcluded=f.adStatus==='not_run';
  const adSampleInsufficient=f.adStatus==='active'&&nonnegative(f.adClicks)&&f.adClicks<p.ad.minClicks;
  const reasons=Object.entries(dimensions).flatMap(([k,v])=>v.score===null&&!(k==='ad'&&adExcluded)?v.missing:[]);
  const validWeights=Object.values(weights).every(x=>Number.isFinite(x)&&x>=0)&&Object.values(weights).reduce((a,b)=>a+b,0)===100;
  if(!validWeights)reasons.push('综合权重之和必须是100%');
  const noOrders=f.adStatus==='not_run'&&f.ordersInWindow===0&&f.validOrders===0;
  const state:ScoringResult['status']=noOrders&&nonnegative(f.elapsedDays)&&f.elapsedDays>=p.speed.observationDays?'continue_observation':
    market.score===null?'needs_market':reasons.length?'preview':'scored';
  if(noOrders&&state==='continue_observation')reasons.push('14天无广告无订单：允许运营继续观察，不自动判失败或Pass');
  let total:number|null=null;
  let grade:ScoringResult['grade']=null;
  let preliminaryGrade:ScoringResult['preliminaryGrade']=null;
  const appliedVetoes:string[]=[];
  if(reasons.length===0){
    const applicable=(Object.keys(dimensions) as Dimension[]).filter(k=>!(k==='ad'&&adExcluded));
    const denom=applicable.reduce((acc,k)=>acc+weights[k],0);
    if(denom>0){
      const base=applicable.reduce((acc,k)=>acc+(dimensions[k].score??0)*weights[k],0)/denom;
      const verified=new Set(risks?.confirmedRiskNames??[]);
      const deducted=(risks?.penalties??[]).filter(r=>r.enabled&&verified.has(r.name)).reduce((acc,r)=>acc+r.deduct,0);
      total=clamp(base-deducted);
      preliminaryGrade=gradeFor(total);
      grade=preliminaryGrade;
      const applicableVetoes=(risks?.vetoes??[]).filter(v=>v.enabled&&(
        (v.name==='ROI 低（Pass）'&&finite(f.roi)&&f.roi<.5)||
        (v.name==='ROI 低（评级上限）'&&finite(f.roi)&&f.roi>=.5&&f.roi<.8)||
        (v.name==='毛利率过低'&&finite(f.grossMarginPct)&&f.grossMarginPct<10)||
        verified.has(v.name)));
      for(const rule of applicableVetoes){
        appliedVetoes.push(rule.name);
        if(rule.action==='Pass'){grade='Pass';break;}
        if(rule.action==='最多 B 级'&&(grade==='S'||grade==='A'))grade='B';
        if(rule.action==='最多 C 级'&&(grade==='S'||grade==='A'||grade==='B'))grade='C';
      }
    }
  }
  return {dimensions,total,grade,preliminaryGrade,adExcluded,adSampleInsufficient,status:state,reasons,appliedVetoes};
}
/** A frozen copy of the evaluated data and rule version, not a persisted database record. */
export function createScoreSnapshot(version:string,f:ScoringFacts,result:ScoringResult){
  return JSON.parse(JSON.stringify({version,sourceFacts:f,result})) as {version:string;sourceFacts:ScoringFacts;result:ScoringResult};
}
/** Demo adapter: only map columns with known semantics. Never infer first-sale day, 14-day orders, ad attribution, or single-order ratio. */
export function demoFactsFromProduct(p:{market:number|null;roi:number;margin:number;acos:number;clicks:number;spend:number}):ScoringFacts{
  return {firstOrderDay:null,elapsedDays:null,ordersInWindow:null,adStatus:p.spend>0?'active':'unknown',
    adClicks:Number.isFinite(p.clicks)?p.clicks:null,adSpend:Number.isFinite(p.spend)?p.spend:null,
    adOrders:null,adRevenue:null,roi:Number.isFinite(p.roi)?p.roi:null,
    grossMarginPct:Number.isFinite(p.margin)?p.margin:null,validSoldUnits:null,validOrders:null,
    singleUnitOrders:null,marketScore:p.market};
}
