/** PR337_CONFIRMED_SCORE_RULES_V4 */
/** PR337_NUMERIC_SCORING_PRESETS_V3 rule data; extracted from React module for Fast Refresh. */
import type { Config, Grade } from "./nativeData";
import { initialNumericRules, validateNumericRules, type NumericRules } from "./newProductNumericScoring";
import { confirmedScoringDefaults, validateScoringParameters, type ScoringParameters } from "./NewProductConfirmedScoring";
export type RuleDim = "market" | "speed" | "ad" | "profit" | "trust";
export type RuleTier = Exclude<Grade, "Pass">;
export type RuleAction = "Pass" | "最多 B 级" | "最多 C 级";
export interface RulePenalty { name: string; condition: string; enabled: boolean; deduct: number }
export interface RuleVeto { name: string; condition: string; enabled: boolean; action: RuleAction }
/* PR337 STRUCTURED SCORE CONDITIONS V2 */

/** Structure of a score criterion: descriptions are unchanged human guidance, numbers are editable. */
export type ScoreMetric = "firstOrderDays" | "orders7" | "orders10" | "orders20" | "dailyMaxOrders" |
  "acos" | "cvr" | "cpc" | "roi" | "margin" | "singleOrderRatio" | "multiOrderRatio" |
  "competitorCount" | "competitorReviews";
export type ScoreCompare = "<" | "<=" | ">" | ">=" | "range";
export interface ScorePredicate { metric: ScoreMetric; compare: ScoreCompare; first: number; second?: number }
export interface ScoreTierCondition { join: "all" | "any"; predicates: ScorePredicate[] }
export type ScoreConditions = Record<RuleDim, ScoreTierCondition[]>;
const metricOptions: Array<{label:string;value:ScoreMetric; available:boolean}> = [
  {label:"首单用时（天）",value:"firstOrderDays",available:false},
  {label:"7 天销量（单）",value:"orders7",available:true},
  {label:"10 天订单（单）",value:"orders10",available:false},
  {label:"20 天订单（单）",value:"orders20",available:false},
  {label:"单日最高订单（单）",value:"dailyMaxOrders",available:false},
  {label:"ACOS（%）",value:"acos",available:true},
  {label:"CVR（%）",value:"cvr",available:false},
  {label:"CPC（美元）",value:"cpc",available:false},
  {label:"ROI",value:"roi",available:true},
  {label:"毛利率（%）",value:"margin",available:true},
  {label:"单件订单占比（%）",value:"singleOrderRatio",available:false},
  {label:"多件订单占比（%）",value:"multiOrderRatio",available:false},
  {label:"竞品数量（个）",value:"competitorCount",available:false},
  {label:"竞品评价量（条）",value:"competitorReviews",available:false},
];
const operators: Array<{label:string;value:ScoreCompare}> = [
  {label:"小于",value:"<"}, {label:"小于等于",value:"<="},
  {label:"大于",value:">"}, {label:"大于等于",value:">="},
  {label:"区间",value:"range"},
];
const pred=(metric:ScoreMetric, compare:ScoreCompare, first:number, second?:number):ScorePredicate=>({metric,compare,first,...(second===undefined?{}:{second})});
const tier=(join:"all"|"any",...predicates:ScorePredicate[]):ScoreTierCondition=>({join,predicates});
/** Defaults are transcribed only from explicit numeric thresholds in original Chinese copy. */
export const initialScoreConditions:ScoreConditions = {
  market: [tier("all"),tier("all"),tier("all"),tier("all"),tier("all")],
  speed: [
    tier("all",pred("firstOrderDays","range",1,3),pred("orders7",">=",15)),
    tier("all",pred("firstOrderDays","range",1,3),pred("orders10",">=",15)),
    tier("all",pred("firstOrderDays","range",3,7)),
    tier("all",pred("firstOrderDays","range",7,14)),
    tier("all",pred("firstOrderDays","range",7,14),pred("orders20","<=",5)),
  ],
  ad: [
    tier("all",pred("acos","<",20),pred("cvr",">=",8)),
    tier("all",pred("acos","range",20,30),pred("cvr","range",5,8)),
    tier("all",pred("acos","range",30,50)),
    tier("all",pred("acos","range",50,70)),
    tier("all"),
  ],
  profit: [
    tier("all",pred("roi",">=",1.5),pred("margin",">=",25)),
    tier("all",pred("roi","range",1.2,1.5),pred("margin",">=",20)),
    tier("all",pred("roi","range",0.8,1.2),pred("margin",">=",15)),
    tier("all",pred("roi","range",0.6,0.8),pred("margin",">=",10)),
    tier("any",pred("roi","<",0.6),pred("margin","<",10)),
  ],
  trust: [
    tier("all",pred("singleOrderRatio",">=",90)),
    tier("all",pred("multiOrderRatio","<=",20)),
    tier("all",pred("multiOrderRatio","range",20,40)),
    tier("all",pred("multiOrderRatio",">",40)),
    tier("all"),
  ],
};

export interface RuleDraft {
  weights: Config["weights"];
  remindDays: number;
  scoreCriteria: Record<RuleDim, string[]>;
  scoreConditions: ScoreConditions;
  numericRules: NumericRules;
  confirmedScoring: ScoringParameters;
  gradeBands: Record<RuleTier, [number, number]>;
  quantities: Record<Grade, [number, number]>;
  quantityStrategy: "min" | "mid" | "max";
  penalties: RulePenalty[];
  vetoes: RuleVeto[];
  success: { sales30: number; margin: number; acos: number; needProfitDays: number };
}

export const dimensionNames: Record<RuleDim, string> = {
  market: "市场竞争（人工）",
  speed: "出单速度（自动）",
  ad: "广告有效性（自动）",
  profit: "利润空间（自动）",
  trust: "测品数据可信度（自动）",
};
export const dimensionKeys: RuleDim[] = ["market", "speed", "ad", "profit", "trust"];
export const tierNames: Grade[] = ["S", "A", "B", "C", "D", "Pass"];
export const scoreLabels = ["9–10 分", "7–8 分", "5–6 分", "3–4 分", "0–2 分"];

export function createInitialRuleDraft(config: Config): RuleDraft {
  return {
    weights: { ...config.weights },
    remindDays: config.remindDays,
    scoreCriteria: {
      market: [
        "竞争适中，低 Review 产品也有销量，售价有上升空间和差异化空间",
        "有竞争但不是大品牌垄断，仍有价格 / 套装 / 规格切入空间",
        "竞争较强，售价空间较小，但仍有切入机会",
        "头部评价高、同质化严重，售价空间有限",
        "大品牌垄断、低价严重，低 Review 新品机会很小",
      ],
      speed: [
        "1–3 天出首单，1 周内达到 15–20 单",
        "1–3 天出首单，10 天内达到 15–20 单或单日订单 >3",
        "3–7 天出首单，10 天内有连续订单",
        "7–14 天出首单或只有偶发 1 单",
        "7–14 天出首单且 20 天内总订单 ≤5",
      ],
      ad: [
        "ACOS <20%，CPC 较低，CVR ≥8%，有明确成交关键词",
        "ACOS 20%–30%，CPC 正常，CVR 5%–8%",
        "ACOS 30%–50%，CPC 较高但仍有成交",
        "ACOS 50%–70%，点击多、订单少",
        "广告几乎无成交，CPC 极高或花费失控",
      ],
      profit: [
        "ROI ≥1.5 且毛利率 ≥25%",
        "ROI 1.2–1.5 且毛利率 ≥20%",
        "ROI 0.8–1.2 且毛利率 ≥15%",
        "ROI 0.6–0.8 且毛利率 ≥10%",
        "ROI <0.6 或毛利率低于 10%",
      ],
      trust: [
        "90% 以上订单为单件成交，样本可信度高",
        "多件订单占比 ≤20%",
        "多件订单占比 20%–40%",
        "多件订单占比 >40%",
        "订单高度集中，少量订单贡献大量销量",
      ],
    },
    scoreConditions: JSON.parse(JSON.stringify(initialScoreConditions)) as ScoreConditions,
    numericRules: JSON.parse(JSON.stringify(initialNumericRules)) as NumericRules,
    confirmedScoring: JSON.parse(JSON.stringify(confirmedScoringDefaults)) as ScoringParameters,
    gradeBands: { S: [9, 10], A: [8, 8.99], B: [7, 7.99], C: [6, 6.99], D: [0, 5.99] },
    quantities: { S: [400, 600], A: [300, 500], B: [200, 400], C: [150, 250], D: [0, 0], Pass: [0, 0] },
    quantityStrategy: "mid",
    penalties: [
      { name: "资金占用率高", condition: "订货周期 > 20 天", deduct: 1, enabled: true },
      { name: "广告数据不足", condition: "曝光/点击过少但已有少量订单", deduct: 1, enabled: true },
      { name: "广告占比过高", condition: "广告占比 > 25%", deduct: 1, enabled: true },
      { name: "季节性", condition: "淡季销量明显低于旺季", deduct: 1, enabled: true },
      { name: "低价依赖", condition: "同质化严重，依赖极低售价", deduct: 1, enabled: true },
    ],
    vetoes: [
      { name: "ROI 低（Pass）", condition: "复核后 ROI < 0.5", action: "Pass", enabled: true },
      { name: "ROI 低（评级上限）", condition: "0.5 ≤ ROI < 0.8，最高 B 级", action: "最多 B 级", enabled: true },
      { name: "强季节性", condition: "淡季销量不足旺季 30%，持续超过 3 个月", action: "Pass", enabled: true },
      { name: "侵权风险", condition: "品牌词 / 专利 / 版权风险无法解决", action: "Pass", enabled: true },
      { name: "合规风险", condition: "认证、禁售或敏感类目风险无法解决", action: "Pass", enabled: true },
      { name: "单一货源", condition: "仅有单一货源", action: "最多 B 级", enabled: true },
      { name: "毛利率过低", condition: "测品毛利率 < 10%", action: "Pass", enabled: true },
      { name: "广告失控", condition: "花费明显失控且几乎无成交", action: "最多 C 级", enabled: true },
      { name: "质量风险", condition: "10 单内出现明显质量投诉", action: "Pass", enabled: true },
      { name: "价格风险", condition: "恢复正常售价后无竞争力", action: "最多 C 级", enabled: true },
      { name: "退货风险", condition: "天然高退货产品", action: "最多 B 级", enabled: true },
      { name: "平台风险", condition: "容易触发审核、下架或违规", action: "最多 C 级", enabled: true },
    ],
    success: { sales30: 60, margin: 15, acos: 30, needProfitDays: 7 },
  };
}

export function cloneRuleDraft(value: RuleDraft): RuleDraft {
  return JSON.parse(JSON.stringify(value)) as RuleDraft;
}

export function validateRuleDraft(d: RuleDraft): string | null {
  const confirmedError=validateScoringParameters(d.confirmedScoring);
  if(confirmedError)return confirmedError;
  const numericError=validateNumericRules(d.numericRules);
  if(numericError)return numericError;
  if (Object.values(d.weights).some(v => !Number.isInteger(v) || v < 0 || v > 100)) return "评分权重必须为 0–100 的整数";
  const sum = Object.values(d.weights).reduce((a, b) => a + b, 0);
  if (sum !== 100) return `权重合计必须等于 100%，当前为 ${sum}%`;
  if (!Number.isInteger(d.remindDays) || d.remindDays < 1 || d.remindDays > 180) return "评分提醒天数必须为1–180的整数";
  for (const k of dimensionKeys) if (d.scoreCriteria[k].length !== 5 || d.scoreCriteria[k].some(v => !v.trim())) return `${dimensionNames[k]}的评分标准不能为空`;
  for(const dim of dimensionKeys){
    const tiers=d.scoreConditions[dim];
    if(!Array.isArray(tiers)||tiers.length!==5) return `${dimensionNames[dim]}评分档位数量不合法`;
    for(const row of tiers){
      if(row.join!=="all"&&row.join!=="any") return "评分条件关系不合法";
      for(const rule of row.predicates){
        if(!metricOptions.some(m=>m.value===rule.metric) || !operators.some(o=>o.value===rule.compare)) return "评分条件指标或比较方式不合法";
        if(!Number.isFinite(rule.first)) return "评分条件阈值必须是有效数字";
        if(rule.compare==="range"&&(!Number.isFinite(rule.second)||Number(rule.second)<rule.first))return "评分条件范围上限不得小于下限";
      }
    }
  }
  for (const tier of ["S", "A", "B", "C", "D"] as RuleTier[]) {
    const [lo, hi] = d.gradeBands[tier];
    if (!Number.isFinite(lo) || !Number.isFinite(hi) || lo < 0 || hi > 10 || lo > hi) return `${tier} 级评分区间不合法`;
    const [minimum, maximum] = d.quantities[tier];
    if (!Number.isInteger(minimum) || !Number.isInteger(maximum) || minimum < 0 || maximum < minimum) return `${tier} 级采购范围不合法`;
  }
  const sorted: RuleTier[] = ["D", "C", "B", "A", "S"];
  if (d.gradeBands.D[0] !== 0 || d.gradeBands.S[1] !== 10) return "评级分数区间必须覆盖 0–10 分";
  for (let i = 0; i < sorted.length - 1; i++) {
    const low = sorted[i], high = sorted[i + 1];
    if (Math.round((d.gradeBands[high][0] - d.gradeBands[low][1]) * 100) !== 1) return `${high} / ${low} 级分数区间必须连续且不能重叠`;
  }
  if (d.quantities.D.some(x => x !== 0) || d.quantities.Pass.some(x => x !== 0)) return "D / Pass 不生成采购建议";
  if (d.penalties.some(x => !Number.isFinite(x.deduct) || x.deduct < 0 || x.deduct > 10)) return "通用扣分必须为 0–10 分";
  if (![d.success.sales30, d.success.margin, d.success.acos, d.success.needProfitDays].every(Number.isFinite)) return "打品成功目标必须填写有效数值";
  return null;
}

export function validateTrackingRuleDraft(success:RuleDraft["success"]):string|null{
  if(!Number.isInteger(success.sales30)||success.sales30<0)return "30 天累计销量必须为非负整数";
  if(!Number.isFinite(success.margin)||success.margin<0||success.margin>100)return "利润率必须在 0–100% 之间";
  if(!Number.isFinite(success.acos)||success.acos<0||success.acos>100)return "ACOS 必须在 0–100% 之间";
  if(!Number.isInteger(success.needProfitDays)||success.needProfitDays<1||success.needProfitDays>90)return "持续盈利天数必须为 1–90 的整数";
  return null;
}
