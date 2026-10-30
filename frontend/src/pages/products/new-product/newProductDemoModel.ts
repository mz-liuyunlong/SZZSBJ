/** Isolated, in-memory demonstration data. No production API, ledger or purchase writes. */
import { create } from "zustand";

export type Dimension = "market" | "order" | "ads" | "profit" | "trust";
export type Grade = "S" | "A" | "B" | "C" | "D" | "Pass";
export type ApprovalState = "none" | "pending" | "approved" | "rejected";
export type TrackState = "未进入打品池" | "等待到货" | "观察中" | "打品成功" | "打品失败";
export interface ProductSample {
  id: string; sku: string; itemId: string; name: string; category: string;
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
}
export interface GradeRule { grade: Grade; min: number; qtyMin: number; qtyMax: number }
export interface DemoConfig {
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
export const defaultConfig: DemoConfig = {
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
const row = (sku: string, name: string, category: string, developer: string, operator: string,
  listedAt: string, market: number | null, system: ProductSample["system"],
  roi: number, demand: number, approval: ApprovalState, tracking: TrackState,
  sales30: number, sales60: number, sales90: number, approvedQty: number | null,
  progress: string, requestQty: number | null = null): ProductSample => ({
  id: sku, sku, itemId: "18420" + sku.replace(/\D/g, "").padStart(7, "0"),
  name, category, developer, operator, listedAt, market,
  marketReason: market === null ? "" : "竞品价格与 Review 分布已人工核对；有一定差异化空间。",
  system, overrides: {}, roi, margin: roi < .7 ? 15.3 : roi * 15 + 8,
  acos: Math.max(12, 42 - system.ads * 3), clicks: Math.round(20 + system.order * 17),
  orders: Math.round(system.order * 2.2), sales30, sales60, sales90,
  adSpend: 30 + system.ads * 12, inventory: approvedQty === null ? 0 : Math.max(0, approvedQty - sales90),
  unitCost: roi < .7 ? 9 : 6.8, demand, approval,
  requestQty, requestReason: requestQty === null ? "" : "结合实际出单表现，申请调整采购数量。",
  approvedQty, arrivedAt: ["观察中", "打品成功", "打品失败"].includes(tracking) ? "2026-08-10" : null,
  sellableAt: ["观察中", "打品成功", "打品失败"].includes(tracking) ? "2026-08-12" : null,
  tracking, progress, failureReason: tracking === "打品失败" ? "广告转化不足、库存消化慢" : "",
});
export const demoProducts: ProductSample[] = [
  row("YC00738","0.6×3m 双层隔热膜","家居耗材","王宁","陈佳","2026-09-21",null,{order:8,ads:10,profit:3,trust:6},.5,280,"none","未进入打品池",0,0,0,null,"待测评"),
  row("YC00752","抽屉分隔收纳盒","收纳用品","林晓","王宁","2026-09-23",null,{order:9,ads:8,profit:8,trust:9},1.32,460,"none","未进入打品池",0,0,0,null,"待测评"),
  row("YC00761","厨房保鲜分装盒","厨房用品","赵敏","李倩","2026-10-17",null,{order:7,ads:7,profit:7,trust:6},.96,250,"none","未进入打品池",0,0,0,null,"测评中"),
  row("YC00806","厨房水槽滤网套装","厨房用品","王宁","李倩","2026-09-15",8,{order:8,ads:7,profit:7,trust:8},1.16,330,"none","未进入打品池",0,0,0,null,"待运营确认"),
  row("YC00831","办公打包标签纸","办公打包","赵敏","陈佳","2026-09-01",7,{order:7,ads:6,profit:8,trust:8},1.25,220,"pending","等待到货",0,0,0,null,"待领导审核",260),
  row("YC00872","硅胶防滑垫","厨房用品","陈佳","李倩","2026-08-24",9,{order:9,ads:8,profit:9,trust:9},1.42,520,"approved","观察中",162,283,370,500,"采购到货"),
  row("YC00901","真空压缩收纳袋","收纳用品","林晓","王宁","2026-07-28",8,{order:8,ads:7,profit:7,trust:8},1.08,360,"approved","打品成功",245,422,508,400,"采购到货"),
  row("YC00914","厨房保鲜袋收纳架","厨房用品","赵敏","陈佳","2026-07-31",6,{order:5,ads:4,profit:6,trust:7},.72,180,"none","打品失败",39,71,86,350,"打品复盘"),
  row("YC00930","可重复使用打包袋","办公打包","王宁","李倩","2026-08-15",8,{order:8,ads:8,profit:7,trust:8},1.18,310,"approved","观察中",128,190,250,310,"采购到货"),
  row("YC00955","多用途挂钩组合","家居耗材","林晓","陈佳","2026-08-05",9,{order:9,ads:9,profit:8,trust:9},1.55,560,"approved","打品成功",260,480,620,550,"采购到货"),
  row("YC01015","办公桌理线夹","办公打包","陈佳","王宁","2026-08-02",5,{order:4,ads:3,profit:5,trust:6},.67,180,"none","未进入打品池",0,0,0,null,"停止推进"),
  row("YC01067","可折叠收纳篮","收纳用品","王宁","陈佳","2026-09-18",8,{order:9,ads:7,profit:9,trust:8},1.4,420,"pending","等待到货",0,0,0,null,"待领导审核",460),
];
export function daysSince(iso: string, now = new Date()): number {
  if (!iso) return 0;
  const day = Date.parse(iso + "T00:00:00Z");
  return Number.isFinite(day) ? Math.max(0, Math.floor((now.getTime() - day) / 86400000)) : 0;
}
export function completedScore(p: ProductSample, config: DemoConfig) {
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
export function gradePass(grade: Grade | undefined) {
  return !!grade && ["S","A","B","C"].includes(grade);
}
export function evaluatedTrack(p: ProductSample, c: DemoConfig) {
  if (!p.arrivedAt || !p.sellableAt) return "未开始";
  const start = p.arrivedAt > p.sellableAt ? p.arrivedAt : p.sellableAt;
  const days = daysSince(start);
  if (days < c.successWindow) return "观察中";
  const sold = c.successWindow === 30 ? p.sales30 : c.successWindow === 60 ? p.sales60 : p.sales90;
  if (!Number.isFinite(sold)) return "数据不足";
  return sold >= c.successSales && p.margin >= c.minProfit && p.acos <= c.maxAcos ? "达标" : "未达标";
}
export function percentage(a: number, b: number): string { return b ? (100*a/b).toFixed(1)+"%" : "—"; }
type SystemDimension = Exclude<Dimension, "market">;
interface DemoState {
  products: ProductSample[]; corrections: Correction[]; plans: PurchasePlan[];
  config: DemoConfig; demoRole: "operator" | "leader"; ruleVersion: number;
  setDemoRole: (role: "operator"|"leader") => void;
  setMarket: (id: string, value: number, reason: string) => void;
  applyPurchase: (id: string, qty: number, reason: string) => void;
  decidePurchase: (id: string, decision: "approved"|"rejected", note: string) => void;
  submitCorrection: (id: string, dimension: SystemDimension, score: number, reason: string) => void;
  decideCorrection: (id: string, decision: "approved"|"rejected", note: string) => void;
  saveConfig: (next: DemoConfig) => void;
  updateTrack: (id: string, tracking: TrackState, reason: string) => void;
  resetDemo: () => void;
}
const initial = () => ({
  products: demoProducts.map(p=>({...p, system:{...p.system}, overrides:{...p.overrides}})),
  corrections: [] as Correction[], plans: [] as PurchasePlan[],
  config: structuredClone(defaultConfig), demoRole: "operator" as const, ruleVersion: 1,
});
export const useNewProductDemoStore = create<DemoState>((set,get) => ({
  ...initial(),
  setDemoRole: demoRole => set({demoRole}),
  setMarket: (id,value,reason) => {
    if (!Number.isInteger(value)||value<0||value>10||!reason.trim()) throw Error("市场评分必须为0~10分并填写依据");
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
  decidePurchase: (id,decision,note) => {
    if(get().demoRole!=="leader") throw Error("请切换领导演示视角");
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
  decideCorrection: (id,decision,note) => {
    if(get().demoRole!=="leader") throw Error("请切换领导演示视角");
    const item=get().corrections.find(c=>c.id===id);
    if(!item||item.status!=="pending") throw Error("申请不是待审核状态");
    if(decision==="rejected"&&!note.trim()) throw Error("驳回必须填写原因");
    set(s=>({
      corrections:s.corrections.map(c=>c.id===id?{...c,status:decision,note}:c),
      products:s.products.map(p=>p.id===item.productId&&decision==="approved"
        ? {...p,overrides:{...p.overrides,[item.dimension]:item.to}} : p),
    }));
  },
  saveConfig: next => {
    if(get().demoRole!=="leader") throw Error("仅领导演示视角可修改规则");
    const sum=Object.values(next.weights).reduce((a,b)=>a+b,0);
    if(sum!==100||Object.values(next.weights).some(n=>n<0||n>100)) throw Error("评分权重合计必须为100%");
    const thresholds=next.rules.filter(r=>r.grade!=="Pass").map(r=>r.min);
    if(thresholds.some((n,i)=>i>0&&n>=thresholds[i-1])) throw Error("等级评分门槛必须严格递减");
    if(next.rules.some(r=>r.qtyMin<0||r.qtyMax<r.qtyMin)) throw Error("采购数量范围不合法");
    if(!Number.isInteger(next.remindDays)||next.remindDays<1||next.successSales<1||
      next.maxAcos<0||next.maxAcos>100) throw Error("提醒及打品目标配置不合法");
    set(s=>({config:structuredClone(next),ruleVersion:s.ruleVersion+1}));
  },
  updateTrack: (id,tracking,reason) => set(s=>({products:s.products.map(p=>p.id===id?
    {...p,tracking,failureReason:reason} : p)})),
  resetDemo:()=>set(initial()),
}));
