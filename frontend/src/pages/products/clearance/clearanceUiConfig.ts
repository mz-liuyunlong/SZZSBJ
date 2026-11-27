import type { ClearanceProduct, PeriodDays } from "./clearanceModel";

export const ANALYSIS_FIELDS = [
  ["identity","商品 ID / 品名",187],["sku","SKU / MSKU",153],["store","店铺 / 负责人",127],
  ["risk","风险等级",95],["source","识别来源",91],["wfs","WFS 可售",86],["age","库龄",66],
  ["coverage","售罄天数",83],["stockCost","库存成本",106],["price","售价",73],
  ["daily","日均销量",100],["revenue","销售额",118],
  ["ads","广告费",108],["adRate","广告占比",108],
  ["profit","利润",118],["profitRate","利润率",108],
  ["returns","30 天退货率",106],["rating","评分",86],["units","销量",90],
  ["status","进度 / 状态",114],["action","操作",136],
] as const;
export const MANAGEMENT_FIELDS = [
  ["identity", "商品 ID / 品名", 205],
  ["sku", "SKU / MSKU", 165],
  ["store", "店铺 / 负责人", 140],
  ["source", "申请来源", 100],
  ["reason", "清货原因", 122],
  ["method", "清货方式", 158],
  ["goal", "目标清货量", 112],
  ["sold", "已销售", 90],
  ["revenue", "总销售额", 116],
  ["progress", "清货进度", 136],
  ["cost", "目标库存成本", 132],
  ["plannedStart", "计划开始", 116],
  ["due", "计划截止", 116],
  ["status", "任务状态", 108],
  ["submitted", "提交时间", 147],
  ["action", "操作", 104],
] as const;
export const PERIODS:PeriodDays[]=[7,14,30];
export const money=(n:number|null|undefined)=>(n==null||!Number.isFinite(n))?"—":(n<0?"−":"")+"$"+Math.abs(n).toLocaleString("en-US",{minimumFractionDigits:2,maximumFractionDigits:2});
export const integer=(n:number)=>Number.isFinite(n)?n.toLocaleString("en-US",{maximumFractionDigits:0}):"—";
export const percent=(n:number|null|undefined)=>(n==null||!Number.isFinite(n))?"—":n.toFixed(1)+"%";

/** Display period does not change the fixed-window WFS risk calculations. */
export function getClearancePeriodMetrics(product:ClearanceProduct,period:PeriodDays){
 const p=product.per[period];
 return {units:p.units,daily:p.units/period,revenue:p.revenue,ads:p.ads,adRate:p.adRate,profit:p.profit,profitRate:p.margin};
}
