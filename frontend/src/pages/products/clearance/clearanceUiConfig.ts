import type { PeriodDays } from "./clearanceModel";

export const ANALYSIS_FIELDS = [
  ["identity","商品 ID / 品名",187],["sku","SKU / MSKU",153],["store","店铺 / 负责人",127],
  ["risk","风险等级",95],["source","识别来源",91],["wfs","WFS 可售",86],["age","库龄",66],
  ["coverage","售罄天数",83],["stockCost","库存成本",106],["price","售价",73],
  ["daily","7 / 14 / 30 日均销量",145],["revenue","7 / 14 / 30 天销售额",150],
  ["ads","7 / 14 / 30 天广告费",150],["adRate","7 / 14 / 30 天广告占比",145],
  ["profit","7 / 14 / 30 天利润",150],["profitRate","7 / 14 / 30 天利润率",145],
  ["returns","30 天退货率",106],["rating","评分",86],["units","7 / 14 / 30 天销量",130],
  ["status","进度 / 状态",114],["action","操作",136],
] as const;
export const MANAGEMENT_FIELDS = [
  ["id","清货申请单",155],["item","清货对象",212],["store","店铺 / 负责人",140],
  ["source","申请来源",100],["reason","清货原因",110],["method","清货方式",156],
  ["goal","目标清货量",100],["sold","已销售",95],["removed","移除 / 弃置",108],
  ["progress","处理进度",136],["cost","目标库存成本",116],["due","计划截止",118],
  ["status","任务状态",100],["submitted","提交时间",136],["action","操作",128],
] as const;
export const PERIODS:PeriodDays[]=[7,14,30];
export const money=(n:number|null|undefined)=>n==null?"—":(n<0?"−":"")+"$"+Math.abs(n).toLocaleString("en-US",{minimumFractionDigits:2,maximumFractionDigits:2});
export const integer=(n:number)=>n.toLocaleString("en-US",{maximumFractionDigits:0});
export const percent=(n:number|null|undefined)=>n==null?"—":n.toFixed(1)+"%";
