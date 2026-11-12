/** PR337_NUMERIC_SCORING_PRESETS_V3
 * Measured numeric thresholds. Never infer unavailable first-order/CVR/CPC/order-composition data.
 * Numeric scores are an auditable PREVIEW; historical Demo scores are not overwritten.
 */
import type { Product } from "./nativeData";

export type NumericMetric = "orders7" | "acos" | "roi" | "margin" | "singleOrderRatio";
export type NumericDimension = "speed" | "ad" | "profit" | "trust";
export type NumericAnchors = [number, number, number, number, number, number];
export type NumericRule = { values: NumericAnchors; direction: "higher" | "lower" };
export type NumericRules = Record<NumericMetric, NumericRule>;
export type NumericSource = "available" | "missing";
export interface MetricDefinition {
  metric: NumericMetric;
  label: string;
  unit: string;
  dimension: NumericDimension;
  source: NumericSource;
  note: string;
}

export const anchorScores = [10, 8, 6, 4, 2, 0] as const;
export const metricDefinitions: MetricDefinition[] = [
  {metric:"orders7",label:"近 7 天订单量",unit:"单",dimension:"speed",source:"available",note:"仅能计算销量表现；首单用时、连续订单等尚未接入"},
  {metric:"acos",label:"ACOS",unit:"%",dimension:"ad",source:"available",note:"仅能计算 ACOS；CPC、CVR 和广告成交词尚未接入"},
  {metric:"roi",label:"ROI",unit:"",dimension:"profit",source:"available",note:"与毛利率共同判断，取较低的指标得分"},
  {metric:"margin",label:"毛利率",unit:"%",dimension:"profit",source:"available",note:"与 ROI 共同判断，取较低的指标得分"},
  {metric:"singleOrderRatio",label:"单件订单占比",unit:"%",dimension:"trust",source:"missing",note:"Mock 缺少单件/多件订单数量，暂不能计算"},
];

/** Initial values are DEMO examples, not empirically approved score standards. */
export const initialNumericRules: NumericRules = {
  orders7: {direction:"higher",values:[20,15,10,5,2,0]},
  acos: {direction:"lower",values:[15,20,30,50,70,100]},
  roi: {direction:"higher",values:[1.8,1.5,1.2,0.8,0.6,0]},
  margin: {direction:"higher",values:[30,25,20,15,10,0]},
  singleOrderRatio: {direction:"higher",values:[95,90,80,60,40,0]},
};

export function validateNumericRules(rules: NumericRules): string | null {
  for (const def of metricDefinitions) {
    const rule=rules[def.metric];
    if (!rule || !Array.isArray(rule.values) || rule.values.length!==6) return `${def.label} 数值锚点必须为 6 个`;
    const values=rule.values;
    if (values.some(v=>!Number.isFinite(v)||v<0)) return `${def.label} 阈值必须为非负有效数值`;
    if(def.unit==="%"&&values.some(v=>v>100))return `${def.label} 百分比不得大于 100`;
    for(let i=1;i<values.length;i++){
      if(rule.direction==="higher" && values[i]>=values[i-1])return `${def.label} 阈值必须从高分到低分严格递减`;
      if(rule.direction==="lower" && values[i]<=values[i-1])return `${def.label} 阈值必须从高分到低分严格递增`;
    }
  }
  return null;
}

export function metricValue(p:Product, metric:NumericMetric):number|null {
  const v=metric==="orders7"?p.qty7:metric==="acos"?p.acos:
    metric==="roi"?p.roi:metric==="margin"?p.margin:null;
  return typeof v==="number"&&Number.isFinite(v)?v:null;
}

/** Piecewise linear interpolation on explicit 10, 8, 6, 4, 2, 0 anchors. */
export function numericMetricScore(value:number|null, rule:NumericRule):number|null {
  if(value===null || !Number.isFinite(value))return null;
  const arr=rule.values;
  const at=value;
  if(rule.direction==="higher"){
    if(at>=arr[0])return 10;
    if(at<=arr[5])return 0;
  }else{
    if(at<=arr[0])return 10;
    if(at>=arr[5])return 0;
  }
  for(let i=0;i<5;i++){
    const high=arr[i],low=arr[i+1];
    if((rule.direction==="higher"&&at<=high&&at>=low)||
       (rule.direction==="lower"&&at>=high&&at<=low)){
      const fraction=(at-high)/(low-high);
      return Math.round((anchorScores[i]+(anchorScores[i+1]-anchorScores[i])*fraction)*100)/100;
    }
  }
  return null;
}

export interface DimensionPreview {
  dimension: NumericDimension;
  score:number|null;
  complete:boolean;
  details: Array<{metric:NumericMetric;label:string;value:number|null;score:number|null}>;
  missing:string[];
}
export function previewDimension(p:Product, rules:NumericRules,dimension:NumericDimension):DimensionPreview {
  const defs=metricDefinitions.filter(x=>x.dimension===dimension);
  const details=defs.map(x=>{
    const value=metricValue(p,x.metric);
    return {metric:x.metric,label:x.label,value,score:numericMetricScore(value,rules[x.metric])};
  });
  const available=details.map(x=>x.score).filter((v):v is number=>v!==null);
  const missing=defs.filter((_,i)=>details[i].score===null).map(x=>x.label);
  if(dimension==="speed")missing.push("首单时间 / 连续订单数据");
  if(dimension==="ad")missing.push("CPC / CVR / 成交关键词数据");
  if(dimension==="trust")missing.push("多件订单占比 / 订单分布数据");
  const complete=missing.length===0;
  return {dimension,score:available.length?Math.min(...available):null,complete,details,missing};
}

export function previewNumericScore(p:Product, rules:NumericRules){
  const dimensions=(["speed","ad","profit","trust"] as const).map(d=>previewDimension(p,rules,d));
  return {dimensions, complete:dimensions.every(d=>d.complete)&&p.market!==null&&p.marketReason.trim().length>0};
}
