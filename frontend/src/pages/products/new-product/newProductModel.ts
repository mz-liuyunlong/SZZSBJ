/** New product state backed by mock fixtures while domain APIs are not connected. */
import { create } from "zustand";
import { mockProducts } from "./newProductMockData";

export type Dimension = "market" | "order" | "ads" | "profit" | "trust";
export type Grade = "S" | "A" | "B" | "C" | "D" | "Pass";
export type ApprovalState = "none" | "pending" | "approved" | "rejected";
export type TrackState = "未进入打品池" | "等待到货" | "观察中" | "需要优化" | "打品成功" | "打品失败";
export interface ProductSample {
  id: string; sku: string; itemId: string; image?: string; name: string; category: string;
  developer: string; operator: string; listedAt: string;
  market: number | null; marketReason: string;
  system: Record<Exclude<Dimension, "market">, number>;
  overrides: Partial<Record<Exclude<Dimension, "market">, number>>;
  roi: number; margin: number; acos: number; clicks: number; orders: number;
  sales30: number; sales60: number; sales90: number; adSpend: number;
  inventory: number; unitCost: number; demand: number;
  approval: ApprovalState; requestQty: number | null; requestReason: string;
  approvedQty: number | null; arrivedAt: string | null; sellableAt: string | null;
  tracking: TrackState; progress: string; failureReason: string;
  reviewDueAt?: string | null; reviewedAt?: string | null; reviewReason?: string;
}
export interface GradeRule { grade: Grade; min: number; qtyMin: number; qtyMax: number }
export interface NewProductConfig {
  weights: Record<Dimension, number>;
  rules: GradeRule[];
  remindDays: number;
  successWindow: 30 | 60 | 90;
  successSales: number;
  minProfit: number;
  maxAcos: number;
}
export interface Correction {
  id: string; productId: string; dimension: Exclude<Dimension, "market">;
  from: number; to: number; reason: string; status: "pending" | "approved" | "rejected";
  note: string;
}
export interface PurchasePlan {
  id: string; productId: string; grade: Grade; score: number;
  suggestedQty: number; approvedQty: number; originalReason: string; createdAt: string;
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
export function completedScore(p: ProductSample, config: NewProductConfig) {
  if (p.market === null) return null;
  const w = config.weights;
  const raw = (p.market * w.market +
    systemDimensions.reduce((sum,d) => sum + (p.overrides[d] ?? p.system[d]) * w[d], 0)) / 100;
  const score = Math.round(raw * 100) / 100;
  let grade: Grade = config.rules.find(r => r.grade !== "Pass" && score >= r.min)?.grade ?? "D";
  if (p.roi < .5 || p.margin < 10) grade = "Pass";
  else if (p.roi < .8 && ["S","A"].includes(grade)) grade = "B";
  const rule = config.rules.find(r=>r.grade===grade);
  const suggested = grade === "D" || grade === "Pass" || !rule ? 0 :
    Math.round(Math.max(rule.qtyMin, Math.min(rule.qtyMax, p.demand)));
  return { score, grade, suggested, rule };
}
/** Workflow status for the business tabs in the New Product performance page. */
export type ProductWorkflowTab = "all" | "market" | "purchase" | "approval" | "approved" | "stopped";
export function getNewProductWorkflowTab(p: ProductSample, config: NewProductConfig): Exclude<ProductWorkflowTab, "all"> {
  if (p.approval === "pending") return "approval";
  if (p.approval === "approved") return "approved";
  if (p.market === null) return "market";
  const result = completedScore(p, config);
  if (!result || result.suggested <= 0) return "stopped";
  return "purchase";
}
export function gradePass(grade: Grade | undefined) {
  return !!grade && ["S","A","B","C"].includes(grade);
}
export function evaluatedTrack(p: ProductSample, c: NewProductConfig) {
  if (!p.arrivedAt || !p.sellableAt) return "未开始";
  const start = p.arrivedAt > p.sellableAt ? p.arrivedAt : p.sellableAt;
  const days = daysSince(start);
  if (days < c.successWindow) return "观察中";
  const sold = c.successWindow === 30 ? p.sales30 : c.successWindow === 60 ? p.sales60 : p.sales90;
  if (!Number.isFinite(sold)) return "数据不足";
  return sold >= c.successSales && p.margin >= c.minProfit && p.acos <= c.maxAcos ? "达标" : "未达标";
}
export type TrackingWorkflowTab = "all" | "ready" | "observe" | "review" | "optimize" | "done";
export function trackedProduct(p: ProductSample): boolean {
 return p.approval === "approved" || p.tracking !== "未进入打品池";
}
export function trackingWorkflow(p: ProductSample, config: NewProductConfig): Exclude<TrackingWorkflowTab,"all"> {
 if (p.tracking==="打品成功" || p.tracking==="打品失败") return "done";
 if (p.tracking==="需要优化") return "optimize";
 if (!p.arrivedAt || !p.sellableAt) return "ready";
 if (daysSince(p.arrivedAt>p.sellableAt?p.arrivedAt:p.sellableAt) >= config.successWindow) return "review";
 return "observe";
}
export function periodSales(p: ProductSample, days: 30|60|90):number {
 return days===30?p.sales30:days===60?p.sales60:p.sales90;
}
export function percentage(a: number, b: number): string { return b ? (100*a/b).toFixed(1)+"%" : "—"; }
type SystemDimension = Exclude<Dimension, "market">;
interface NewProductState {
  products: ProductSample[]; corrections: Correction[]; plans: PurchasePlan[];
  config: NewProductConfig; ruleVersion: number;
  setMarket: (id: string, value: number, reason: string) => void;
  applyPurchase: (id: string, qty: number, reason: string) => void;
  decidePurchase: (id: string, decision: "approved"|"rejected", note: string, canApprove: boolean) => void;
  submitCorrection: (id: string, dimension: SystemDimension, score: number, reason: string) => void;
  decideCorrection: (id: string, decision: "approved"|"rejected", note: string, canApprove: boolean) => void;
  saveConfig: (next: NewProductConfig, canConfigure: boolean) => void;
  updateTrack: (id: string, tracking: TrackState, reason: string, nextReview?: string) => void;
  resetMockData: () => void;
}
const initial = () => ({
  products: mockProducts.map(p=>({...p, system:{...p.system}, overrides:{...p.overrides}})),
  corrections: [] as Correction[], plans: [] as PurchasePlan[],
  config: structuredClone(defaultConfig), ruleVersion: 1,
});
export const useNewProductStore = create<NewProductState>((set,get) => ({
  ...initial(),
  setMarket: (id,value,reason) => {
    if (!Number.isInteger(value)||value<0||value>10||reason.trim().length<5) throw Error("市场评分必须为0~10分并填写依据");
    set(s=>({products:s.products.map(p=>p.id===id ? {...p,market:value,marketReason:reason} : p)}));
  },
  applyPurchase: (id,qty,reason) => {
    const p=get().products.find(p=>p.id===id);
    if (!p || p.approval==="approved" || p.approval==="pending") throw Error("当前状态不可申请");
    const result=completedScore(p,get().config);
    if (!result||!result.suggested) throw Error("当前产品不能推进采购");
    if (!Number.isInteger(qty)||qty<=0) throw Error("请填写正确的采购数量");
    if (qty!==result.suggested && reason.trim().length<5) throw Error("修改建议量时需填写至少5字原因");
    if (get().corrections.some(c=>c.productId===id&&c.status==="pending")) throw Error("评分修正尚未审核，暂不能提交采购");
    set(s=>({products:s.products.map(x=>x.id===id?{...x,approval:"pending" as const,requestQty:qty,requestReason:reason}:x)}));
  },
  decidePurchase: (id,decision,note,canApprove) => {
    if(!canApprove) throw Error("当前账号无权审批采购");
    const s=get(), p=s.products.find(x=>x.id===id);
    if(!p||p.approval!=="pending"||!p.requestQty) throw Error("只有待审批申请可以审批");
    if(decision==="rejected"&&!note.trim()) throw Error("驳回必须填写原因");
    const result=completedScore(p,s.config);
    if(!result||!result.suggested) throw Error("评分已失效，禁止批准");
    const plans=decision==="approved"&&!s.plans.some(x=>x.productId===id)
      ? [...s.plans,{id:"NP-PLAN-"+String(s.plans.length+1).padStart(4,"0"),
        productId:id, grade:result.grade,score:result.score,suggestedQty:result.suggested,
        approvedQty:p.requestQty,originalReason:p.requestReason,createdAt:new Date().toISOString()}]
      : s.plans;
    set({plans,products:s.products.map(x=>x.id===id?{...x,approval:decision,
      approvedQty:decision==="approved"?x.requestQty:null,
      tracking:decision==="approved"?"等待到货" as const:x.tracking,
      progress:decision==="approved"?"已批准待采购":"审核驳回"}:x)});
  },
  submitCorrection: (id,dimension,score,reason) => {
    const p=get().products.find(x=>x.id===id);
    if(!p||p.market===null) throw Error("请先确认市场评分");
    if(p.approval==="approved") throw Error("采购已批准，需走独立变更流程");
    if(!Number.isInteger(score)||score<0||score>10) throw Error("申请分数须为0~10整数");
    if(reason.trim().length<5) throw Error("修正原因至少5个字");
    if(get().corrections.some(c=>c.productId===id&&c.dimension===dimension&&c.status==="pending")) throw Error("该维度已有待审核申请");
    const original=p.overrides[dimension]??p.system[dimension];
    if(original===score) throw Error("申请分数与当前分数相同");
    set(s=>({corrections:[...s.corrections,{id:"NP-COR-"+String(s.corrections.length+1).padStart(4,"0"),
      productId:id,dimension,from:original,to:score,reason,status:"pending",note:""}]}));
  },
  decideCorrection: (id,decision,note,canApprove) => {
    if(!canApprove) throw Error("当前账号无权审核评分修正");
    const item=get().corrections.find(c=>c.id===id);
    if(!item||item.status!=="pending") throw Error("申请不是待审核状态");
    if(decision==="rejected"&&!note.trim()) throw Error("驳回必须填写原因");
    set(s=>({
      corrections:s.corrections.map(c=>c.id===id?{...c,status:decision,note}:c),
      products:s.products.map(p=>p.id===item.productId&&decision==="approved"
        ? {...p,overrides:{...p.overrides,[item.dimension]:item.to}} : p),
    }));
  },
  saveConfig: (next,canConfigure) => {
    if(!canConfigure) throw Error("当前账号无权修改规则");
    const sum=Object.values(next.weights).reduce((a,b)=>a+b,0);
    if(sum!==100||Object.values(next.weights).some(n=>n<0||n>100)) throw Error("评分权重合计必须为100%");
    const thresholds=next.rules.filter(r=>r.grade!=="Pass").map(r=>r.min);
    if(thresholds.some((n,i)=>i>0&&n>=thresholds[i-1])) throw Error("等级评分门槛必须严格递减");
    if(next.rules.some(r=>r.qtyMin<0||r.qtyMax<r.qtyMin)) throw Error("采购数量范围不合法");
    if(!Number.isInteger(next.remindDays)||next.remindDays<1||next.successSales<1||
      next.maxAcos<0||next.maxAcos>100) throw Error("提醒及打品目标配置不合法");
    set(s=>({config:structuredClone(next),ruleVersion:s.ruleVersion+1}));
  },
  updateTrack: (id,tracking,reason,nextReview) => {
    if (!get().products.some(p=>p.id===id&&trackedProduct(p))) throw Error("商品未进入打品跟踪");
    if (reason.trim().length<5) throw Error("复盘原因至少填写5字");
    if (tracking==="需要优化"&&!nextReview) throw Error("需要优化时必须填写下次复核日期");
    if (["打品成功","打品失败"].includes(tracking)) {
      const p=get().products.find(x=>x.id===id)!;
      if (!p.arrivedAt || !p.sellableAt || daysSince(p.arrivedAt>p.sellableAt?p.arrivedAt:p.sellableAt)<get().config.successWindow) throw Error("观察期未结束，不允许确认最终打品结果");
    }
    set(s=>({products:s.products.map(p=>p.id===id?
      {...p,tracking,failureReason:reason,reviewReason:reason,reviewedAt:new Date().toISOString(),reviewDueAt:nextReview??null}:p)}));
  },
  resetMockData:()=>set(initial()),
}));
