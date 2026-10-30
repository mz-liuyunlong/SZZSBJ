/** New product domain model. Local acceptance uses isolated fixtures until APIs are connected. */
import { create } from "zustand";
import { mockProducts } from "./newProductMockData";

export type Dimension = "market" | "order" | "ads" | "profit" | "trust";
export type Grade = "S" | "A" | "B" | "C" | "D" | "Pass";
export type ApprovalState = "none" | "pending" | "approved" | "rejected";
export type TrackState = "未进入打品池" | "等待到货" | "观察中" | "需要优化" | "打品成功" | "打品失败";
export type ObservationPeriod = 30 | 60 | 90;
export interface PeriodMetrics {
  clicks: number; orders: number; sales: number; adSpend: number;
  acos: number; margin: number; profit: number; dataAvailable: boolean;
}
export interface ScoreBreakdown {
  market: number; order: number; ads: number; profit: number; trust: number;
}
export interface ScoreSnapshot {
  score: number; grade: Grade; suggestedQty: number; rule: GradeRule;
  weights: Record<Dimension, number>; breakdown: ScoreBreakdown; ruleVersion: number;
}
export interface PurchaseSnapshot extends ScoreSnapshot {
  requestQty: number; approvedQty: number; approvedAt: string; approvedBy: string;
  requestReason: string; approvalNote: string;
}
export interface ProductSample {
  id: string; sku: string; itemId: string; image?: string; name: string; category: string;
  developer: string; operator: string; listedAt: string;
  market: number | null; marketReason: string;
  system: Record<Exclude<Dimension, "market">, number>;
  overrides: Partial<Record<Exclude<Dimension, "market">, number>>;
  roi: number; margin: number; acos: number; clicks: number; orders: number;
  sales30: number; sales60: number; sales90: number; adSpend: number;
  periodMetrics: Record<"30" | "60" | "90", PeriodMetrics>;
  inventory: number; unitCost: number; demand: number; actualPurchaseQty: number | null;
  approval: ApprovalState; requestQty: number | null; requestReason: string;
  approvedQty: number | null; arrivedAt: string | null; sellableAt: string | null;
  tracking: TrackState; progress: string; failureReason: string;
  reviewDueAt?: string | null; reviewedAt?: string | null; reviewReason?: string;
  purchaseSnapshot?: PurchaseSnapshot;
}
export interface GradeRule { grade: Grade; min: number; qtyMin: number; qtyMax: number }
export interface NewProductConfig {
  weights: Record<Dimension, number>;
  rules: GradeRule[];
  remindDays: number;
  successWindow: ObservationPeriod;
  successSales: number;
  minProfit: number;
  maxAcos: number;
}
export interface Correction {
  id: string; productId: string; dimension: Exclude<Dimension, "market">;
  from: number; to: number; reason: string; status: "pending" | "approved" | "rejected";
  note: string; submittedAt: string; reviewedAt?: string; reviewedBy?: string;
}
export interface PurchasePlan extends PurchaseSnapshot {
  id: string; productId: string; createdAt: string;
}
export interface RuleHistoryEntry {
  version: number; changedAt: string; changedBy: string; reason: string; config: NewProductConfig;
}
export const dimensions: Record<Dimension, string> = {
  market: "市场竞争", order: "出单速度", ads: "广告有效性",
  profit: "利润空间", trust: "测品数据可信度",
};
export const systemDimensions: Exclude<Dimension, "market">[] = ["order", "ads", "profit", "trust"];
export const defaultConfig: NewProductConfig = {
  weights: { market: 15, order: 30, ads: 20, profit: 25, trust: 10 },
  rules: [
    { grade: "S", min: 9, qtyMin: 400, qtyMax: 600 },
    { grade: "A", min: 8, qtyMin: 300, qtyMax: 500 },
    { grade: "B", min: 7, qtyMin: 200, qtyMax: 400 },
    { grade: "C", min: 6, qtyMin: 150, qtyMax: 250 },
    { grade: "D", min: 0, qtyMin: 0, qtyMax: 0 },
    { grade: "Pass", min: -1, qtyMin: 0, qtyMax: 0 },
  ],
  remindDays: 30, successWindow: 60, successSales: 200, minProfit: 0, maxAcos: 35,
};
export function daysSince(iso: string, now = new Date()): number {
  if (!iso) return 0;
  const day = Date.parse(iso + "T00:00:00Z");
  return Number.isFinite(day) ? Math.max(0, Math.floor((now.getTime() - day) / 86400000)) : 0;
}
export function getPeriodMetrics(p: ProductSample, period: ObservationPeriod): PeriodMetrics {
  const metric = p.periodMetrics?.[String(period) as "30" | "60" | "90"];
  if (metric) return metric;
  return { clicks:p.clicks,orders:p.orders,sales:period===30?p.sales30:period===60?p.sales60:p.sales90,
    adSpend:p.adSpend,acos:p.acos,margin:p.margin,profit:0,dataAvailable:false };
}
export function scoreBreakdown(p: ProductSample): ScoreBreakdown {
  return { market:p.market??0,order:p.overrides.order??p.system.order,ads:p.overrides.ads??p.system.ads,
    profit:p.overrides.profit??p.system.profit,trust:p.overrides.trust??p.system.trust };
}
export function completedScore(p: ProductSample, config: NewProductConfig) {
  if (p.market === null) return null;
  const breakdown=scoreBreakdown(p),w=config.weights;
  const raw=(breakdown.market*w.market+breakdown.order*w.order+breakdown.ads*w.ads+
    breakdown.profit*w.profit+breakdown.trust*w.trust)/100;
  const score=Math.round(raw*100)/100;
  let grade:Grade=config.rules.find(r=>r.grade!=="Pass"&&score>=r.min)?.grade??"D";
  if(p.roi<.5||p.margin<10)grade="Pass";
  else if(p.roi<.8&&["S","A"].includes(grade))grade="B";
  const rule=config.rules.find(r=>r.grade===grade);
  const suggested=grade==="D"||grade==="Pass"||!rule?0:Math.round(Math.max(rule.qtyMin,Math.min(rule.qtyMax,p.demand)));
  return {score,grade,suggested,rule,weights:{...w},breakdown};
}
export function productScore(p:ProductSample,config:NewProductConfig) {
  const snapshot=p.purchaseSnapshot;
  if(snapshot)return {score:snapshot.score,grade:snapshot.grade,suggested:snapshot.suggestedQty,rule:snapshot.rule,
    weights:snapshot.weights,breakdown:snapshot.breakdown};
  return completedScore(p,config);
}
export type ProductWorkflowTab="all"|"market"|"purchase"|"approval"|"approved"|"stopped";
export function getNewProductWorkflowTab(p:ProductSample,config:NewProductConfig):Exclude<ProductWorkflowTab,"all">{
  if(p.approval==="pending")return "approval";
  if(p.approval==="approved")return "approved";
  if(p.market===null)return "market";
  const result=completedScore(p,config);
  if(!result||result.suggested<=0)return "stopped";
  return "purchase";
}
export function gradePass(grade:Grade|undefined){return !!grade&&["S","A","B","C"].includes(grade);}
export function evaluateTrack(p:ProductSample,config:NewProductConfig,period:ObservationPeriod=config.successWindow){
  if(!p.arrivedAt||!p.sellableAt)return "未开始" as const;
  const start=p.arrivedAt>p.sellableAt?p.arrivedAt:p.sellableAt;
  if(daysSince(start)<period)return "观察中" as const;
  const metric=getPeriodMetrics(p,period);
  if(!metric.dataAvailable)return "数据不足" as const;
  return metric.sales>=config.successSales&&metric.margin>=config.minProfit&&metric.acos<=config.maxAcos?"达标" as const:"未达标" as const;
}
export function evaluatedTrack(p:ProductSample,c:NewProductConfig){return evaluateTrack(p,c);}
export type TrackingWorkflowTab="all"|"ready"|"observe"|"review"|"optimize"|"done";
export function trackedProduct(p:ProductSample){return p.approval==="approved";}
export function trackingWorkflow(p:ProductSample,c:NewProductConfig):Exclude<TrackingWorkflowTab,"all">{
  if(p.tracking==="打品成功"||p.tracking==="打品失败")return "done";
  if(p.tracking==="需要优化")return "optimize";
  if(!p.arrivedAt||!p.sellableAt)return "ready";
  if(daysSince(p.arrivedAt>p.sellableAt?p.arrivedAt:p.sellableAt)>=c.successWindow)return "review";
  return "observe";
}
export function periodSales(p:ProductSample,days:ObservationPeriod){return getPeriodMetrics(p,days).sales;}
export function percentage(a:number,b:number){return b?(100*a/b).toFixed(1)+"%":"—";}
type SystemDimension=Exclude<Dimension,"market">;
interface NewProductState{
  products:ProductSample[];corrections:Correction[];plans:PurchasePlan[];config:NewProductConfig;
  ruleVersion:number;ruleHistory:RuleHistoryEntry[];
  setMarket:(id:string,value:number,reason:string)=>void;
  applyPurchase:(id:string,qty:number,reason:string)=>void;
  decidePurchase:(id:string,decision:"approved"|"rejected",note:string,canApprove:boolean,approvedBy:string)=>void;
  submitCorrection:(id:string,dimension:SystemDimension,score:number,reason:string)=>void;
  decideCorrection:(id:string,decision:"approved"|"rejected",note:string,canApprove:boolean,reviewedBy:string)=>void;
  saveConfig:(next:NewProductConfig,canConfigure:boolean,changedBy:string,reason:string)=>void;
  updateTrack:(id:string,tracking:TrackState,reason:string,nextReview?:string)=>void;
  resetMockData:()=>void;
}
const initial=()=>({products:mockProducts.map(p=>({...p,system:{...p.system},overrides:{...p.overrides},periodMetrics:{...p.periodMetrics}})),
  corrections:[] as Correction[],plans:[] as PurchasePlan[],config:structuredClone(defaultConfig),ruleVersion:1,
  ruleHistory:[{version:1,changedAt:"2026-10-30T00:00:00.000Z",changedBy:"系统",reason:"初始规则",config:structuredClone(defaultConfig)}] as RuleHistoryEntry[]});
export const useNewProductStore=create<NewProductState>((set,get)=>({
  ...initial(),
  setMarket:(id,value,reason)=>{
    const p=get().products.find(x=>x.id===id);
    if(!p||p.approval!=="none"||p.market!==null)throw Error("当前产品不处于待市场评分状态");
    if(!Number.isInteger(value)||value<0||value>10||reason.trim().length<5)throw Error("市场评分必须为0~10分并填写至少5字依据");
    set(s=>({products:s.products.map(x=>x.id===id?{...x,market:value,marketReason:reason.trim()}:x)}));
  },
  applyPurchase:(id,qty,reason)=>{
    const p=get().products.find(x=>x.id===id);
    if(!p||p.approval==="approved"||p.approval==="pending")throw Error("当前状态不可申请");
    const result=completedScore(p,get().config);
    if(!result||!result.suggested)throw Error("当前产品不能推进采购");
    if(!Number.isInteger(qty)||qty<=0)throw Error("请填写正确的采购数量");
    if(qty!==result.suggested&&reason.trim().length<5)throw Error("修改建议量时需填写至少5字原因");
    if(get().corrections.some(c=>c.productId===id&&c.status==="pending"))throw Error("评分修正尚未审核，暂不能提交采购");
    set(s=>({products:s.products.map(x=>x.id===id?{...x,approval:"pending",requestQty:qty,requestReason:reason.trim()}:x)}));
  },
  decidePurchase:(id,decision,note,canApprove,approvedBy)=>{
    if(!canApprove)throw Error("当前账号无权审批采购");
    const s=get(),p=s.products.find(x=>x.id===id);
    if(!p||p.approval!=="pending"||!p.requestQty)throw Error("只有待审批申请可以审批");
    if(decision==="rejected"&&note.trim().length<5)throw Error("驳回必须填写至少5字原因");
    const result=completedScore(p,s.config);
    if(!result||!result.suggested)throw Error("评分已失效，禁止批准");
    if(p.requestQty!==result.suggested&&p.requestReason.trim().length<5)throw Error("调整采购数量必须保留原因");
    const now=new Date().toISOString();
    const snapshot:PurchaseSnapshot={score:result.score,grade:result.grade,suggestedQty:result.suggested,rule:result.rule!,
      weights:{...result.weights},breakdown:{...result.breakdown},ruleVersion:s.ruleVersion,requestQty:p.requestQty,
      approvedQty:p.requestQty,approvedAt:now,approvedBy,requestReason:p.requestReason,approvalNote:note};
    const existing=s.plans.find(x=>x.productId===id);
    const plans=decision==="approved"&&!existing?[...s.plans,{...snapshot,id:"NP-PLAN-"+String(s.plans.length+1).padStart(4,"0"),productId:id,createdAt:now}]:s.plans;
    if(decision==="approved"&&existing)throw Error("该 SKU 已生成采购计划，禁止重复生成");
    set({plans,products:s.products.map(x=>x.id===id?{...x,approval:decision,approvedQty:decision==="approved"?x.requestQty:null,
      actualPurchaseQty:decision==="approved"?x.requestQty:x.actualPurchaseQty,
      purchaseSnapshot:decision==="approved"?snapshot:x.purchaseSnapshot,
      tracking:decision==="approved"?"等待到货":x.tracking,progress:decision==="approved"?"已批准待采购":"审核驳回"}:x)});
  },
  submitCorrection:(id,dimension,score,reason)=>{
    const p=get().products.find(x=>x.id===id);
    if(!p||p.market===null)throw Error("请先确认市场评分");
    if(p.approval==="approved")throw Error("采购已批准，需走独立变更流程");
    if(!Number.isInteger(score)||score<0||score>10)throw Error("申请分数须为0~10整数");
    if(reason.trim().length<5)throw Error("修正原因至少5个字");
    if(get().corrections.some(c=>c.productId===id&&c.dimension===dimension&&c.status==="pending"))throw Error("该维度已有待审核申请");
    const original=p.overrides[dimension]??p.system[dimension];
    if(original===score)throw Error("申请分数与当前分数相同");
    set(s=>({corrections:[...s.corrections,{id:"NP-COR-"+String(s.corrections.length+1).padStart(4,"0"),productId:id,dimension,from:original,to:score,
      reason:reason.trim(),status:"pending",note:"",submittedAt:new Date().toISOString()}]}));
  },
  decideCorrection:(id,decision,note,canApprove,reviewedBy)=>{
    if(!canApprove)throw Error("当前账号无权审核评分修正");
    const item=get().corrections.find(c=>c.id===id);
    if(!item||item.status!=="pending")throw Error("申请不是待审核状态");
    if(decision==="rejected"&&note.trim().length<5)throw Error("驳回必须填写至少5字原因");
    const now=new Date().toISOString();
    set(s=>({corrections:s.corrections.map(c=>c.id===id?{...c,status:decision,note:note.trim(),reviewedAt:now,reviewedBy}:c),
      products:s.products.map(p=>p.id===item.productId&&decision==="approved"?{...p,overrides:{...p.overrides,[item.dimension]:item.to}}:p)}));
  },
  saveConfig:(next,canConfigure,changedBy,reason)=>{
    if(!canConfigure)throw Error("当前账号无权修改规则");
    if(reason.trim().length<5)throw Error("规则变更必须填写至少5字原因");
    const sum=Object.values(next.weights).reduce((a,b)=>a+b,0);
    if(sum!==100||Object.values(next.weights).some(n=>!Number.isFinite(n)||n<0||n>100))throw Error("评分权重合计必须为100%");
    const ordered=next.rules.filter(r=>r.grade!=="Pass");
    if(ordered.length!==5||ordered.some((r,i)=>i>0&&r.min>=ordered[i-1].min))throw Error("等级评分门槛必须严格递减且完整");
    if(next.rules.length!==6||new Set(next.rules.map(r=>r.grade)).size!==6)throw Error("必须完整配置 S/A/B/C/D/Pass 六个等级");
    if(next.rules.some(r=>!Number.isInteger(r.qtyMin)||!Number.isInteger(r.qtyMax)||r.qtyMin<0||r.qtyMax<r.qtyMin))throw Error("采购数量范围不合法");
    if(!Number.isInteger(next.remindDays)||next.remindDays<1||!Number.isInteger(next.successSales)||next.successSales<1||
      !Number.isFinite(next.minProfit)||next.maxAcos<0||next.maxAcos>100)throw Error("提醒或打品目标配置不合法");
    const version=get().ruleVersion+1,now=new Date().toISOString(),snapshot=structuredClone(next);
    set(s=>({config:snapshot,ruleVersion:version,ruleHistory:[...s.ruleHistory,{version,changedAt:now,changedBy,reason:reason.trim(),config:structuredClone(snapshot)}]}));
  },
  updateTrack:(id,tracking,reason,nextReview)=>{
    const p=get().products.find(x=>x.id===id);
    if(!p||!trackedProduct(p))throw Error("商品未进入打品跟踪");
    if(reason.trim().length<5)throw Error("复盘原因至少填写5字");
    if(tracking==="需要优化"&&!nextReview)throw Error("需要优化时必须填写下次复核日期");
    if(tracking==="打品成功"||tracking==="打品失败"){
      const result=evaluateTrack(p,get().config);
      if(result==="观察中"||result==="未开始")throw Error("观察期未结束，不允许确认最终打品结果");
      if(result==="数据不足")throw Error("经营数据不完整，暂不能确认最终打品结果");
      if(tracking==="打品成功"&&result!=="达标")throw Error("未达到配置的销量、利润率和 ACOS 标准，不能标记打品成功");
      if(tracking==="打品失败"&&result!=="未达标")throw Error("当前经营指标已达标，不能标记打品失败");
    }
    set(s=>({products:s.products.map(x=>x.id===id?{...x,tracking,failureReason:tracking==="打品失败"?reason.trim():"",reviewReason:reason.trim(),
      reviewedAt:new Date().toISOString(),reviewDueAt:nextReview??null}:x)}));
  },
  resetMockData:()=>set(initial()),
}));
