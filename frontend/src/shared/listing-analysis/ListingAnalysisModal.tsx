import { useEffect, useState } from "react";
import type { EChartsOption } from "echarts";
import ReactECharts from "echarts-for-react";
import type {
  ListingAnalysisPanel,
  ListingAnalysisPeriod,
} from "./listingAnalysisTypes";
import "./ListingAnalysisModal.css";

type Tone = "up" | "down" | "warn" | "";
type MetricKey = "sales" | "revenue" | "price" | "profit" | "ads" | "refund";
type CompareMode = "yesterday" | "avg7" | "lastweek";
type AdScope = "all" | "auto" | "manual";
type AdMetric = "spend" | "clicks" | "orders" | "sales" | "acos";
type KeywordSource = "all" | "manual" | "auto";
type KeywordSort = "clicks" | "spend" | "orders" | "rank" | "waste";
type EventType = "all" | "price" | "ad" | "review" | "buybox" | "hijack" | "listing" | "promo";
type EventSource = "all" | "manual" | "auto";

interface ListingAnalysisSourceLike {
  title?: string;
  productName?: string;
  itemName?: string;
  productId?: string | number;
  sku?: string;
  msku?: string;
  date?: string;
  platform?: string;
  store?: string;
  status?: string;
}

interface ListingAnalysisModalProps {
  open: boolean;
  onClose: () => void;
  source?: ListingAnalysisSourceLike;
  initialPanel?: ListingAnalysisPanel;
}


interface Trend { title: string; sub: string; unit?: string; current: number[]; previous: number[] }
interface Kpi { key?: MetricKey; label: string; value: string; foot: string; tone?: Tone }
interface KeywordRow {
  term: string; source: "manual" | "auto"; match: string; organicRank: number; organicDelta: number;
  sponsoredRank: number; impressions: number; clicks: number; spend: number; orders: number;
  cpc: number; cpa: number | null; cvr: number; roas: number; bid: number;
}
interface EventRow {
  id: string; date: string; time: string; type: Exclude<EventType, "all">; source: Exclude<EventSource, "all">;
  sourceName: string; operator: string; title: string; change: string; label: string; note: string;
  beforeSales: string; afterSales: string; delta: string;
}
interface RiskItem {
  key: string; name: string; value: string; sub: string; state: "normal" | "attention" | "serious"; detail: string; tip: string;
}
interface PeriodData {
  labels: string[];
  overview: {
    kpis: Kpi[];
    trends: Record<MetricKey, Trend>;
    diagnosis: Array<{ icon: string; title: string; sub: string; value: string; detail: string; tone?: Tone }>;
    order: { natural: number; ads: number; impressions: string; visits: string; cvr: string };
    labels?: string[];
  };
  compare: Record<CompareMode, {
    label: string;
    result: Array<[string, string, string, string, Tone]>;
    traffic: Array<[string, string, string, Tone]>;
    ads: Array<[string, string, string, Tone]>;
    quality: Array<[string, string, string, Tone]>;
    rates: Array<[string, string, string]>;
  }>;
  price: {
    labels?: string[];
    kpis: Array<[string, string, string]>;
    sales: number[];
    price: number[];
    competitor: number[];
    competitorId: string;
    events: Array<[string, string, string, string, string, string, Tone]>;
  };
  ads: {
    kpis: Array<{ label: string; value: string; sideLabel: string; sideValue: string }>;
    trend: Record<AdScope, Record<AdMetric, number[]>>;
    modes: Record<"auto" | "manual", { name: string; share: string; spend: string; result: string; cpc: string; cvr: string; acos: string }>;
    keywords: KeywordRow[];
    alert: string;
  };
  profit: {
    kpis: Array<[string, string, string, Tone]>;
    revenue: number[];
    profit: number[];
    adRate: number[];
    margin: number[];
    cost: Array<[string, number, string]>;
  };
  stock: {
    kpis: Array<[string, string, string, Tone]>;
    baseDaily: number; sellable: number; inbound: number; targetDays: number;
    labels: string[]; current: number[]; planned: number[]; safety: number[];
    decision: { qty: number; window: string; latest: string; note: string };
  };
  risk: { score: number; summary: Array<[string, string, Tone]>; items: RiskItem[] };
  timeline: { events: EventRow[]; sales: number[]; orders: number[] };
}

const panels: Array<{ key: ListingAnalysisPanel; label: string }> = [
  { key: "overview", label: "经营概览" },
  { key: "compare", label: "指标对比" },
  { key: "price", label: "售价分析" },
  { key: "adsAnalysis", label: "广告分析" },
  { key: "profit", label: "利润质量" },
  { key: "stock", label: "库存补货" },
  { key: "risk", label: "Listing风险" },
  { key: "timeline", label: "经营事件" },
];

const adMetricMeta: Record<AdMetric, { label: string; color: string }> = {
  spend: { label: "广告费", color: "#1677ff" },
  clicks: { label: "点击", color: "#13a8a8" },
  orders: { label: "订单", color: "#f5a623" },
  sales: { label: "销售额", color: "#7b61ff" },
  acos: { label: "ACOS", color: "#8a95a6" },
};

const money = (value: number) => `$${value.toLocaleString("en-US", { maximumFractionDigits: value % 1 === 0 ? 0 : 2 })}`;
const num = (value: number) => value.toLocaleString("en-US");
const cls = (tone?: Tone) => tone || "";

function kw(term: string, source: "manual" | "auto", match: string, organicRank: number, organicDelta: number, sponsoredRank: number, impressions: number, clicks: number, spend: number, orders: number, bid: number): KeywordRow {
  const cpc = spend / Math.max(clicks, 1);
  const cpa = orders > 0 ? spend / orders : null;
  const cvr = orders / Math.max(clicks, 1) * 100;
  const roas = orders > 0 ? orders * 27 / spend : 0;
  return { term, source, match, organicRank, organicDelta, sponsoredRank, impressions, clicks, spend, orders, cpc, cpa, cvr, roas, bid };
}

const baseKeywords = [
  kw("under sink organizer", "manual", "Exact", 8, 4, 3, 8650, 186, 48.2, 8, 0.82),
  kw("kitchen organizer", "manual", "Phrase", 17, -3, 5, 7280, 142, 37.8, 3, 0.76),
  kw("cabinet organizer", "manual", "Broad", 6, 2, 4, 5120, 97, 26.4, 5, 0.68),
  kw("sink storage", "manual", "Phrase", 21, 3, 8, 4480, 83, 21.1, 1, 0.61),
  kw("bathroom storage", "auto", "Auto", 42, 8, 12, 3980, 61, 18.4, 0, 0.55),
  kw("sink organizer rack", "auto", "Auto", 35, -4, 10, 3720, 58, 18.1, 0, 0.58),
  kw("under sink shelf", "auto", "Auto", 29, 5, 9, 3100, 49, 11.6, 0, 0.49),
  kw("kitchen sink organizer", "auto", "Auto", 14, 8, 6, 2890, 48, 11.2, 4, 0.62),
  kw("under cabinet storage", "manual", "Exact", 11, 2, 4, 2580, 47, 10.9, 3, 0.74),
  kw("organizer for sink", "manual", "Broad", 26, -1, 11, 2460, 43, 10.2, 1, 0.57),
];

function scaleKeywords(mult: number): KeywordRow[] {
  return baseKeywords.map((item, index) => {
    const orders = item.orders === 0 ? (mult > 3 ? (index % 2 === 0 ? 2 : 1) : index % 3 === 0 ? 1 : 0) : Math.max(1, Math.round(item.orders * mult * 0.96));
    const spend = Number((item.spend * mult).toFixed(2));
    const clicks = Math.round(item.clicks * mult);
    return kw(item.term, item.source, item.match, item.organicRank, item.organicDelta + (mult > 3 ? index % 3 - 1 : 0), item.sponsoredRank, Math.round(item.impressions * mult), clicks, spend, orders, item.bid);
  });
}

const events7: EventRow[] = [
  { id: "e1", date: "2026-09-17", time: "13:40", type: "price", source: "manual", sourceName: "Walmart后台", operator: "运营 A", title: "售价调整", change: "$27.99 → $27.00 · 降价 $0.99 · -3.5%", label: "$", note: "日常售价调整。", beforeSales: "7.3", afterSales: "—", delta: "数据不足" },
  { id: "e2", date: "2026-09-17", time: "09:18", type: "ad", source: "manual", sourceName: "领星", operator: "运营 A", title: "广告预算调整", change: "$50 / 天 → $60 / 天 · 预算 +20%", label: "AD", note: "提升预算观察核心词流量。", beforeSales: "8.0", afterSales: "12.0", delta: "+50.0%" },
  { id: "e3", date: "2026-09-16", time: "14:38", type: "buybox", source: "auto", sourceName: "系统检测", operator: "自动", title: "Buy Box 恢复", change: "62% → 97% · 恢复至正常区间", label: "BB", note: "Buy Box 恢复。", beforeSales: "6.0", afterSales: "10.0", delta: "+66.7%" },
  { id: "e4", date: "2026-09-16", time: "11:20", type: "buybox", source: "auto", sourceName: "系统检测", operator: "自动", title: "Buy Box 丢失", change: "98% → 62% · 持续约 3h 18m", label: "BB", note: "系统检测到 Buy Box 短时丢失。", beforeSales: "11.0", afterSales: "6.0", delta: "-45.5%" },
  { id: "e5", date: "2026-09-16", time: "07:48", type: "review", source: "auto", sourceName: "Walmart", operator: "自动", title: "新增 1 星 Review", change: "评分 4.4 → 4.3 · Review 128 → 129", label: "★", note: "新增低星 Review。", beforeSales: "12.0", afterSales: "10.0", delta: "-16.7%" },
  { id: "e6", date: "2026-09-15", time: "16:05", type: "ad", source: "manual", sourceName: "领星", operator: "运营 A", title: "关键词 Bid 调整", change: "$0.88 → $0.82 · Bid -6.8%", label: "AD", note: "控制 CPC。", beforeSales: "10.7", afterSales: "10.0", delta: "-6.5%" },
  { id: "e7", date: "2026-09-15", time: "10:30", type: "promo", source: "manual", sourceName: "Walmart后台", operator: "运营 A", title: "Promotion 开始", change: "普通售价 → Promotion · 活动开始", label: "P", note: "促销开始。", beforeSales: "8.0", afterSales: "10.0", delta: "+25.0%" },
  { id: "e8", date: "2026-09-14", time: "18:12", type: "hijack", source: "auto", sourceName: "系统检测", operator: "自动", title: "发现疑似跟卖", change: "0 → 1 个卖家 · 新增疑似跟卖", label: "跟", note: "发现疑似跟卖。", beforeSales: "9.0", afterSales: "8.0", delta: "-11.1%" },
  { id: "e9", date: "2026-09-14", time: "09:12", type: "listing", source: "manual", sourceName: "Walmart后台", operator: "运营 A", title: "主图更新", change: "旧主图 → 新主图 · 图片版本更新", label: "L", note: "主图更新。", beforeSales: "8.3", afterSales: "9.0", delta: "+8.4%" },
  { id: "e10", date: "2026-09-13", time: "10:42", type: "price", source: "manual", sourceName: "Walmart后台", operator: "运营 A", title: "售价调整", change: "$28.99 → $26.99 · 降价 $2.00 · -6.9%", label: "$", note: "价格测试。", beforeSales: "17", afterSales: "8", delta: "-52.9%" },
  { id: "e11", date: "2026-09-12", time: "14:22", type: "ad", source: "manual", sourceName: "领星", operator: "运营 A", title: "广告 Bid 调整", change: "$0.82 → $0.94 · Bid +14.6%", label: "AD", note: "提高核心词竞争力。", beforeSales: "9.3", afterSales: "11.0", delta: "+18.3%" },
  { id: "e12", date: "2026-09-11", time: "08:55", type: "review", source: "auto", sourceName: "Walmart", operator: "自动", title: "新增 5 星 Review", change: "Review 127 → 128 · 评分维持 4.4", label: "★", note: "新增好评。", beforeSales: "8.0", afterSales: "11.0", delta: "+37.5%" },
];

const extraEvents: EventRow[] = [
  { id: "e13", date: "2026-09-10", time: "10:24", type: "ad", source: "manual", sourceName: "领星", operator: "运营 A", title: "自动广告否词", change: "新增否定词 2 个 · 控制无效点击", label: "AD", note: "清理无效搜索词。", beforeSales: "9.0", afterSales: "11.0", delta: "+22.2%" },
  { id: "e14", date: "2026-09-08", time: "15:30", type: "listing", source: "manual", sourceName: "Walmart后台", operator: "运营 A", title: "五点描述优化", change: "补充尺寸卖点 · 提高转化表达", label: "L", note: "内容优化。", beforeSales: "8.0", afterSales: "10.0", delta: "+25.0%" },
  { id: "e15", date: "2026-09-05", time: "11:16", type: "price", source: "manual", sourceName: "Walmart后台", operator: "运营 A", title: "促销价结束", change: "$26.49 → $28.99 · 恢复常规价", label: "$", note: "促销结束。", beforeSales: "13.0", afterSales: "9.0", delta: "-30.8%" },
  { id: "e16", date: "2026-09-01", time: "09:20", type: "review", source: "auto", sourceName: "Walmart", operator: "自动", title: "新增 4 星 Review", change: "Review 123 → 124 · 评分维持 4.4", label: "★", note: "新增好评。", beforeSales: "8.0", afterSales: "10.0", delta: "+25.0%" },
  { id: "e17", date: "2026-08-28", time: "18:02", type: "ad", source: "manual", sourceName: "领星", operator: "运营 A", title: "手动广告扩词", change: "新增关键词 6 个 · Phrase/Exact", label: "AD", note: "扩展核心词覆盖。", beforeSales: "7.0", afterSales: "9.0", delta: "+28.6%" },
];

const riskBase: RiskItem[] = [
  { key: "sellable", name: "可售状态", value: "在售", sub: "—", state: "normal", detail: "当前 Listing 正常在售，未检测到下架、Suppressed 或不可售状态。", tip: "当前无需处理。" },
  { key: "buybox", name: "Buy Box", value: "98%", sub: "最低62%", state: "normal", detail: "Buy Box 已恢复到正常区间，周期内曾短时波动。", tip: "继续观察价格和跟卖变化。" },
  { key: "rating", name: "评分", value: "4.3", sub: "↓0.1", state: "normal", detail: "评分较上期下降 0.1，但仍在可接受范围。", tip: "关注新增低星 Review 的原因。" },
  { key: "lowreview", name: "低星 Review", value: "1条", sub: "+1", state: "attention", detail: "周期内新增低星 Review，可能影响转化。", tip: "查看 Review 内容并判断是否需要客服跟进。" },
  { key: "hijack", name: "跟卖", value: "0", sub: "曾出现1次", state: "normal", detail: "当前未检测到跟卖，但周期内曾出现 1 次。", tip: "继续保持监控。" },
  { key: "traffic", name: "流量异常", value: "+5.0%", sub: "vs均值", state: "normal", detail: "曝光较周期均值上升，流量没有明显下滑。", tip: "重点观察转化是否同步改善。" },
  { key: "conversion", name: "转化异常", value: "2.37%", sub: "↓0.16pp", state: "attention", detail: "CVR 低于周期均值。", tip: "结合售价、Review、Buy Box 和广告词质量排查。" },
  { key: "keyword", name: "核心词排名", value: "3词下降", sub: "最大↓4位", state: "attention", detail: "核心词自然排名出现下降。", tip: "查看关键词广告投入和竞品价格。" },
  { key: "stock", name: "断货风险", value: "29天", sub: "可售356", state: "normal", detail: "当前可售库存预计覆盖 29 天。", tip: "结合补货计划确认采购窗口。" },
  { key: "refund", name: "退款异常", value: "7.4%", sub: "+4.1pp", state: "attention", detail: "退款率高于周期均值，需确认退款原因。", tip: "联动售后模块查看退款订单。" },
];

const compare7 = {
  yesterday: {
    label: "昨日",
    result: [["销量", "12", "+20.0%", "昨日 10", "up"], ["销售额", "$324", "+19.1%", "昨日 $272", "up"], ["利润", "$72", "+18.0%", "昨日 $61", "up"], ["利润率", "22.2%", "-0.2pct", "昨日 22.4%", "down"]],
    traffic: [["曝光", "8.4K", "+18.3%", "up"], ["点击", "615", "+16.5%", "up"], ["访问", "507", "+16.3%", "up"], ["订单", "12", "+20.0%", "up"]],
    ads: [["广告费", "$52", "+18.2%", "warn"], ["广告销售额", "$168", "+15.1%", "up"], ["广告订单", "5", "+25.0%", "up"], ["ACOS", "31.0%", "+0.9pct", "down"]],
    quality: [["退款金额", "$24", "昨日 +$24", "down"], ["退款率", "7.4%", "昨日 +7.4pct", "down"], ["评分", "4.3", "昨日 -0.1", "down"], ["Buy Box", "98%", "昨日 +6pct", "up"]],
    rates: [["CTR", "7.3%", "昨日 7.4% · -0.1pct"], ["点击→访问", "82.4%", "昨日 82.6% · -0.2pct"], ["CVR", "2.37%", "昨日 2.29% · +0.08pct"]],
  },
  avg7: {
    label: "7日均值",
    result: [["销量", "12", "-2.4%", "7日均 12.3", "down"], ["销售额", "$324", "+1.9%", "7日均 $318", "up"], ["利润", "$72", "+6.5%", "7日均 $67.6", "up"], ["利润率", "22.2%", "-1.8pct", "7日均 24.0%", "down"]],
    traffic: [["曝光", "8.4K", "+5.0%", "up"], ["点击", "615", "+2.7%", "up"], ["访问", "507", "+2.0%", "up"], ["订单", "12", "-2.4%", "down"]],
    ads: [["广告费", "$52", "+8.7%", "warn"], ["广告销售额", "$168", "+4.8%", "up"], ["广告订单", "5", "+6.4%", "up"], ["ACOS", "31.0%", "+1.1pct", "down"]],
    quality: [["退款金额", "$24", "+$11", "down"], ["退款率", "7.4%", "+4.1pct", "down"], ["评分", "4.3", "-0.1", "down"], ["Buy Box", "98%", "+3pct", "up"]],
    rates: [["CTR", "7.3%", "7日均 7.5% · -0.2pct"], ["点击→访问", "82.4%", "7日均 82.9% · -0.5pct"], ["CVR", "2.37%", "7日均 2.53% · -0.16pct"]],
  },
  lastweek: {
    label: "上周同日",
    result: [["销量", "12", "+9.1%", "上周同日 11", "up"], ["销售额", "$324", "+12.5%", "上周同日 $288", "up"], ["利润", "$72", "+10.8%", "上周同日 $65", "up"], ["利润率", "22.2%", "-0.4pct", "上周同日 22.6%", "down"]],
    traffic: [["曝光", "8.4K", "+11.0%", "up"], ["点击", "615", "+8.6%", "up"], ["访问", "507", "+8.1%", "up"], ["订单", "12", "+9.1%", "up"]],
    ads: [["广告费", "$52", "+16.0%", "warn"], ["广告销售额", "$168", "+11.2%", "up"], ["广告订单", "5", "+25.0%", "up"], ["ACOS", "31.0%", "+1.3pct", "down"]],
    quality: [["退款金额", "$24", "+$24", "down"], ["退款率", "7.4%", "+7.4pct", "down"], ["评分", "4.3", "-0.1", "down"], ["Buy Box", "98%", "+1pct", "up"]],
    rates: [["CTR", "7.3%", "上周同日 7.5% · -0.2pct"], ["点击→访问", "82.4%", "上周同日 82.8% · -0.4pct"], ["CVR", "2.37%", "上周同日 2.34% · +0.03pct"]],
  },
} satisfies PeriodData["compare"];

function buildPeriodData(): Record<ListingAnalysisPeriod, PeriodData> {
  return {
    7: {
      labels: ["09-11", "09-12", "09-13", "09-14", "09-15", "09-16", "09-17"],
      overview: {
        kpis: [
          { key: "sales", label: "销量", value: "12", foot: "↑20.0% 较昨日 · 7日均12.3", tone: "up" },
          { key: "revenue", label: "销售额", value: "$324", foot: "↑19.1% 较昨日", tone: "up" },
          { key: "price", label: "平均售价", value: "$27.00", foot: "↓2.1% 较7日均值", tone: "down" },
          { key: "profit", label: "利润", value: "$72", foot: "利润率22.2% · ↓1.8pct", tone: "down" },
          { key: "ads", label: "广告费", value: "$52", foot: "广告占比16.0% · ↑2.8pct", tone: "warn" },
          { key: "refund", label: "退款", value: "$24", foot: "1单 · 退款率7.4%" },
        ],
        trends: {
          sales: { title: "销量趋势", sub: "每日数值固定展示 · 上期对比为浅灰实线", current: [11, 14, 8, 9, 10, 6, 12], previous: [9, 11, 10, 8, 12, 11, 10] },
          revenue: { title: "销售额趋势", sub: "销售额变化与上期对比", unit: "$", current: [292, 356, 216, 248, 270, 162, 324], previous: [248, 301, 276, 220, 312, 285, 272] },
          price: { title: "平均售价趋势", sub: "售价变化与销量联动", unit: "$", current: [28.99, 28.99, 26.99, 26.99, 26.99, 27, 27], previous: [27.99, 27.99, 28.49, 28.49, 28.99, 28.99, 28.99] },
          profit: { title: "利润趋势", sub: "利润与利润率同步观察", unit: "$", current: [64, 83, 42, 46, 58, 31, 72], previous: [52, 68, 61, 49, 67, 62, 61] },
          ads: { title: "广告费趋势", sub: "广告花费和销售结果对照", unit: "$", current: [44, 51, 39, 41, 55, 50, 52], previous: [36, 45, 42, 40, 44, 47, 44] },
          refund: { title: "退款趋势", sub: "退款金额和退款单量", unit: "$", current: [0, 0, 18, 0, 0, 0, 24], previous: [0, 12, 0, 0, 16, 0, 0] },
        },
        diagnosis: [
          { icon: "AD", title: "订单结构", sub: "自然 / 广告订单", value: "58 / 42%", detail: "广告订单5，自然订单7；广告订单占比42%。" },
          { icon: "$", title: "售价", sub: "较近7日均值", value: "-2.1%", detail: "平均售价 $27.00，低于近7日均值约2.1%。", tone: "down" },
          { icon: "CVR", title: "流量转化", sub: "曝光 / 访问 / CVR", value: "6.9%", detail: "曝光8.4K，访问612，CVR 6.9%。" },
          { icon: "L", title: "Listing状态", sub: "Buy Box / 跟卖 / 划线价", value: "正常", detail: "Buy Box 98%，无跟卖，划线价有效。", tone: "up" },
        ],
        order: { natural: 7, ads: 5, impressions: "8.4K", visits: "612", cvr: "6.9%" },
      },
      compare: compare7,
      price: {
        kpis: [["当前售价", "$27.00", "今日 Listing 售价"], ["7日最高", "$28.99", "09-11 ~ 09-12"], ["7日最低", "$26.99", "09-13 ~ 09-15"], ["调价次数", "2次", "1次降价 · 1次涨价"], ["竞争ID", "5个", "点击可叠加价格趋势"]],
        sales: [11, 14, 8, 9, 10, 6, 12], price: [28.99, 28.99, 26.99, 26.99, 26.99, 27, 27], competitor: [25, 25, 25, 25.5, 25.5, 25, 25], competitorId: "WM-C784521",
        events: [["09-13", "降价 $28.99 → $26.99", "-$2.00", "17", "8", "-52.9%", "down"], ["09-16", "涨价 $26.99 → $27.00", "+$0.01", "8", "12", "+50.0%", "up"]],
      },
      ads: {
        kpis: [{ label: "广告花费", value: "$332", sideLabel: "ACOS", sideValue: "31.8%" }, { label: "点击", value: "1,336", sideLabel: "CPC", sideValue: "$0.25" }, { label: "广告订单", value: "33", sideLabel: "CVR", sideValue: "2.47%" }, { label: "广告销售额", value: "$1,044", sideLabel: "每单广告成本", sideValue: "$10.06" }],
        trend: {
          all: { spend: [44, 51, 39, 41, 55, 50, 52], clicks: [172, 205, 149, 158, 221, 194, 237], orders: [4, 5, 3, 4, 6, 4, 7], sales: [132, 156, 98, 126, 188, 144, 200], acos: [33, 32.7, 39.8, 32.5, 29.2, 34.7, 26] },
          auto: { spend: [16, 18, 13, 14, 19, 17, 18], clicks: [71, 83, 59, 64, 93, 76, 87], orders: [1, 2, 1, 1, 2, 2, 2], sales: [38, 52, 26, 32, 58, 55, 40], acos: [42, 34.6, 50, 43.8, 32.8, 30.9, 45] },
          manual: { spend: [28, 33, 26, 27, 36, 33, 34], clicks: [101, 122, 90, 94, 128, 118, 150], orders: [3, 3, 2, 3, 4, 2, 5], sales: [94, 104, 72, 94, 130, 89, 160], acos: [29.8, 31.7, 36.1, 28.7, 27.7, 37.1, 21.3] },
        },
        modes: { auto: { name: "自动广告", share: "35% 花费", spend: "$115", result: "533 点击 · 11 单", cpc: "$0.22", cvr: "2.06%", acos: "38.1%" }, manual: { name: "手动广告", share: "65% 花费", spend: "$217", result: "803 点击 · 22 单", cpc: "$0.27", cvr: "2.74%", acos: "29.2%" } },
        keywords: baseKeywords, alert: "高花费无单 3词 · $48.10",
      },
      profit: {
        kpis: [["今日利润", "$72", "+18.0% 较昨日", "up"], ["利润率", "22.2%", "-1.8pct 较7日均值", "down"], ["单件利润", "$6.00", "-$0.84 较7日均值", "down"], ["广告费率", "16.0%", "+2.8pct", "warn"], ["退款损耗", "$24", "今日1单", ""]],
        revenue: [292, 356, 216, 248, 270, 162, 324], profit: [64, 83, 42, 46, 58, 31, 72], adRate: [14, 14.3, 18.1, 16.5, 20.4, 30.9, 16], margin: [21.9, 23.3, 19.4, 18.5, 21.5, 19.1, 22.2],
        cost: [["采购成本", 96, "$96"], ["平台佣金", 49, "$49"], ["履约/WFS", 31, "$31"], ["广告费", 52, "$52"], ["退款损耗", 24, "$24"], ["净利润", 72, "$72"]],
      },
      stock: {
        kpis: [["可售库存", "356", "当前可销售", ""], ["已有在途", "180", "预计 09-25 到仓", ""], ["预测日均", "12.3", "近7日均 · 件/天", ""], ["含在途覆盖", "43天", "可售 + 已有在途", ""], ["建议采购量", "480件", "目标覆盖 45 天", "up"], ["最晚采购", "09-28", "剩 11 天", "warn"]],
        baseDaily: 12.3, sellable: 356, inbound: 180, targetDays: 45, labels: ["今天", "+6天", "+12天", "+18天", "+24天", "+30天", "+36天", "+42天", "+48天"], current: [356, 276, 440, 318, 230, 170, 92, 0, 0], planned: [356, 276, 440, 318, 230, 170, 560, 480, 380], safety: [170, 170, 170, 170, 170, 170, 170, 170, 170],
        decision: { qty: 480, window: "09-25 ~ 09-28", latest: "09-28", note: "按当前销量速度计算：采购到国内仓约 12 天，但真正补到可售库存还需要国内处理 2 天、头程 9 天、WFS 入仓 3 天；再预留 7 天安全缓冲。建议最晚 09-28 前下单。" },
      },
      risk: { score: 84, summary: [["12", "监控项", ""], ["8", "正常", "up"], ["4", "关注", "warn"], ["0", "严重", ""], ["2", "24h新增", "warn"]], items: riskBase },
      timeline: { events: events7, sales: [11, 14, 8, 9, 10, 6, 12], orders: [12, 13, 10, 12, 13, 12, 13] },
    },
    14: makePeriod(14),
    30: makePeriod(30),
  };
}

function makePeriod(period: 14 | 30): PeriodData {
  const is30 = period === 30;
  const labels = is30 ? ["08-19", "08-24", "08-29", "09-03", "09-08", "09-13", "09-17"] : ["09-04", "09-06", "09-08", "09-10", "09-12", "09-15", "09-17"];
  const sales = is30 ? [47, 54, 48, 52, 63, 49, 58] : [22, 25, 23, 24, 29, 21, 29];
  const revenue = sales.map((v) => v * 27);
  const adsSpend = is30 ? [182, 201, 176, 190, 238, 212, 192] : [94, 101, 88, 96, 122, 104, 116];
  const profit = is30 ? [276, 324, 255, 288, 372, 264, 367] : [132, 158, 125, 139, 174, 121, 161];
  const totalSales = is30 ? "371" : "173";
  const totalRevenue = is30 ? "$10,017" : "$4,671";
  const totalProfit = is30 ? "$2,146" : "$1,010";
  const totalAds = is30 ? "$1,391" : "$721";
  const orderNatural = is30 ? 235 : 96;
  const orderAds = is30 ? 136 : 77;
  const events = is30 ? [...events7, ...extraEvents] : [...events7, ...extraEvents.slice(0, 3)];
  const keywords = scaleKeywords(is30 ? 4.19 : 1.88);
  const adKpis = is30
    ? [{ label: "广告花费", value: "$1,391", sideLabel: "ACOS", sideValue: "32.3%" }, { label: "点击", value: "5,560", sideLabel: "CPC", sideValue: "$0.25" }, { label: "广告订单", value: "136", sideLabel: "CVR", sideValue: "2.45%" }, { label: "广告销售额", value: "$4,304", sideLabel: "每单广告成本", sideValue: "$10.23" }]
    : [{ label: "广告花费", value: "$721", sideLabel: "ACOS", sideValue: "32.6%" }, { label: "点击", value: "2,872", sideLabel: "CPC", sideValue: "$0.25" }, { label: "广告订单", value: "68", sideLabel: "CVR", sideValue: "2.37%" }, { label: "广告销售额", value: "$2,210", sideLabel: "每单广告成本", sideValue: "$10.60" }];

  return {
    labels,
    overview: {
      kpis: [
        { key: "sales", label: "销量", value: totalSales, foot: `↑${is30 ? "12.4" : "8.1"}% 较上期 · 日均12.4`, tone: "up" },
        { key: "revenue", label: "销售额", value: totalRevenue, foot: `↑${is30 ? "13.1" : "7.4"}% 较上期`, tone: "up" },
        { key: "price", label: "平均售价", value: "$27.00", foot: `↓${is30 ? "1.9" : "1.6"}% 较${period}日均值`, tone: "down" },
        { key: "profit", label: "利润", value: totalProfit, foot: `利润率21.${is30 ? "4" : "6"}% · ↓1.${is30 ? "3" : "1"}pct`, tone: "down" },
        { key: "ads", label: "广告费", value: totalAds, foot: `广告占比${is30 ? "13.9" : "15.4"}% · ↑1.${is30 ? "5" : "7"}pct`, tone: "warn" },
        { key: "refund", label: "退款", value: is30 ? "$168" : "$71", foot: `${is30 ? "7" : "3"}单 · 退款率${is30 ? "4.5" : "4.1"}%` },
      ],
      trends: {
        sales: { title: "销量趋势", sub: `${period}天按区间聚合展示 · 上期对比为浅灰实线`, current: sales, previous: sales.map((v) => Math.round(v * 0.9)) },
        revenue: { title: "销售额趋势", sub: "销售额变化与上期对比", unit: "$", current: revenue, previous: revenue.map((v) => Math.round(v * 0.9)) },
        price: { title: "平均售价趋势", sub: "售价变化与销量联动", unit: "$", current: is30 ? [28.99, 27.99, 27.49, 26.99, 26.99, 27, 27] : [27.99, 27.49, 26.99, 26.99, 27, 27, 27], previous: [28.49, 28.49, 28.99, 28.99, 27.99, 27.99, 27.99] },
        profit: { title: "利润趋势", sub: "利润与利润率同步观察", unit: "$", current: profit, previous: profit.map((v) => Math.round(v * 0.9)) },
        ads: { title: "广告费趋势", sub: "广告花费和销售结果对照", unit: "$", current: adsSpend, previous: adsSpend.map((v) => Math.round(v * 0.88)) },
        refund: { title: "退款趋势", sub: "退款金额和退款单量", unit: "$", current: is30 ? [24, 18, 36, 24, 29, 13, 24] : [0, 18, 0, 24, 0, 0, 29], previous: [12, 0, 0, 16, 0, 0, 0] },
      },
      diagnosis: [
        { icon: "AD", title: "订单结构", sub: "自然 / 广告订单", value: `${Math.round(orderNatural / (orderNatural + orderAds) * 100)} / ${Math.round(orderAds / (orderNatural + orderAds) * 100)}%`, detail: `${period}天广告订单${orderAds}，自然订单${orderNatural}。` },
        { icon: "$", title: "售价", sub: `较近${period}日均值`, value: is30 ? "-1.9%" : "-1.6%", detail: "当前售价略低于周期均值。", tone: "down" },
        { icon: "CVR", title: "流量转化", sub: "曝光 / 访问 / CVR", value: is30 ? "6.8%" : "6.6%", detail: is30 ? "曝光36.4K，访问2,510，CVR 6.8%。" : "曝光17.1K，访问1,228，CVR 6.6%。" },
        { icon: "L", title: "Listing状态", sub: "Buy Box / 跟卖 / 划线价", value: is30 ? "关注" : "正常", detail: "Buy Box 恢复正常，低星 Review 需关注。", tone: is30 ? "warn" : "up" },
      ],
      order: { natural: orderNatural, ads: orderAds, impressions: is30 ? "36.4K" : "17.1K", visits: is30 ? "2,510" : "1,228", cvr: is30 ? "6.8%" : "6.6%" },
    },
    compare: compare7,
    price: {
      kpis: [["当前售价", "$27.00", "今日 Listing 售价"], [`${period}日最高`, "$28.99", is30 ? "08-19 ~ 09-12" : "09-04 ~ 09-12"], [`${period}日最低`, is30 ? "$26.49" : "$26.99", is30 ? "09-01 ~ 09-04" : "09-13 ~ 09-15"], ["调价次数", is30 ? "7次" : "4次", is30 ? "3次降价 · 4次涨价" : "2次降价 · 2次涨价"], ["竞争ID", "5个", "点击可叠加价格趋势"]],
      sales, price: is30 ? [28.99, 27.99, 27.49, 26.99, 26.99, 27, 27] : [27.99, 27.49, 26.99, 26.99, 27, 27, 27], competitor: is30 ? [25.8, 25.5, 25.2, 25.4, 25.6, 25.1, 25] : [25.5, 25.2, 25.2, 25.5, 25.6, 25.1, 25], competitorId: "WM-C784521",
      events: is30 ? [["08-28", "手动广告扩词后观察价格", "观察", "38", "44", "+15.8%", "up"], ["09-05", "恢复 $26.49 → $28.99", "+$2.50", "26", "18", "-30.8%", "down"], ["09-13", "降价 $28.99 → $26.99", "-$2.00", "17", "8", "-52.9%", "down"], ["09-16", "涨价 $26.99 → $27.00", "+$0.01", "8", "12", "+50.0%", "up"]] : [["09-05", "恢复 $26.49 → $28.99", "+$2.50", "26", "18", "-30.8%", "down"], ["09-13", "降价 $28.99 → $26.99", "-$2.00", "17", "8", "-52.9%", "down"], ["09-16", "涨价 $26.99 → $27.00", "+$0.01", "8", "12", "+50.0%", "up"]],
    },
    ads: {
      kpis: adKpis,
      trend: {
        all: { spend: adsSpend, clicks: is30 ? [724, 808, 696, 761, 946, 842, 783] : [352, 401, 329, 374, 486, 418, 512], orders: is30 ? [16, 18, 16, 18, 24, 21, 23] : [8, 9, 7, 8, 12, 10, 14], sales: revenue.map((v) => Math.round(v * 0.42)), acos: [35.6, 34.4, 35.8, 33.5, 31.5, 33.1, 25.5] },
        auto: { spend: adsSpend.map((v) => Math.round(v * 0.35)), clicks: is30 ? [289, 322, 260, 292, 390, 336, 337] : [142, 162, 123, 139, 188, 160, 188], orders: is30 ? [5, 6, 5, 6, 8, 7, 8] : [2, 3, 2, 2, 4, 3, 5], sales: revenue.map((v) => Math.round(v * 0.15)), acos: [42.7, 40, 43.5, 40.4, 36.4, 37.1, 27.6] },
        manual: { spend: adsSpend.map((v) => Math.round(v * 0.65)), clicks: is30 ? [435, 486, 436, 469, 556, 506, 446] : [210, 239, 206, 235, 298, 258, 324], orders: is30 ? [11, 12, 11, 12, 16, 14, 15] : [6, 6, 5, 6, 8, 7, 9], sales: revenue.map((v) => Math.round(v * 0.27)), acos: [32.7, 31.9, 32.9, 30.6, 29.2, 31.2, 24.6] },
      },
      modes: is30 ? { auto: { name: "自动广告", share: "35% 花费", spend: "$486", result: "2,226 点击 · 45 单", cpc: "$0.22", cvr: "2.02%", acos: "38.4%" }, manual: { name: "手动广告", share: "65% 花费", spend: "$905", result: "3,334 点击 · 91 单", cpc: "$0.27", cvr: "2.73%", acos: "29.2%" } } : { auto: { name: "自动广告", share: "36% 花费", spend: "$255", result: "1,102 点击 · 21 单", cpc: "$0.23", cvr: "1.91%", acos: "39.4%" }, manual: { name: "手动广告", share: "64% 花费", spend: "$466", result: "1,770 点击 · 47 单", cpc: "$0.26", cvr: "2.66%", acos: "28.9%" } },
      keywords, alert: is30 ? "高花费无单 8词 · $211.60" : "高花费无单 5词 · $92.40",
    },
    profit: {
      kpis: [[is30 ? "周期利润" : "周期利润", totalProfit, `+${is30 ? "14.6" : "9.4"}% 较上期`, "up"], ["利润率", is30 ? "21.4%" : "21.6%", `-1.${is30 ? "3" : "1"}pct 较${period}日均值`, "down"], ["单件利润", is30 ? "$5.79" : "$5.84", "-$0.38 较均值", "down"], ["广告费率", is30 ? "13.9%" : "15.4%", "+1.5pct", "warn"], ["退款损耗", is30 ? "$168" : "$71", `周期${is30 ? "7" : "3"}单`, ""]],
      revenue, profit, adRate: is30 ? [14.3, 13.8, 13.6, 13.5, 14, 16, 12.3] : [15.8, 15, 14.2, 14.8, 15.6, 18.3, 14.8], margin: is30 ? [21.7, 22.2, 19.7, 20.5, 21.9, 20, 23.4] : [22.2, 23.4, 20.1, 21.5, 22.2, 21.3, 20.6],
      cost: is30 ? [["采购成本", 2968, "$2,968"], ["平台佣金", 1512, "$1,512"], ["履约/WFS", 956, "$956"], ["广告费", 1391, "$1,391"], ["退款损耗", 168, "$168"], ["净利润", 2146, "$2,146"]] : [["采购成本", 1385, "$1,385"], ["平台佣金", 706, "$706"], ["履约/WFS", 448, "$448"], ["广告费", 721, "$721"], ["退款损耗", 71, "$71"], ["净利润", 1010, "$1,010"]],
    },
    stock: {
      kpis: [["可售库存", "356", "当前可销售", ""], ["已有在途", "180", "预计 09-25 到仓", ""], ["预测日均", "12.4", `近${period}日均 · 件/天`, ""], ["含在途覆盖", "43天", "可售 + 已有在途", ""], ["建议采购量", is30 ? "490件" : "480件", "目标覆盖 45 天", "up"], ["最晚采购", is30 ? "09-26" : "09-27", is30 ? "剩 9 天" : "剩 10 天", "warn"]],
      baseDaily: 12.4, sellable: 356, inbound: 180, targetDays: 45, labels: ["今天", "+6天", "+12天", "+18天", "+24天", "+30天", "+36天", "+42天", "+48天"], current: [356, 282, 436, 324, 242, 176, 98, 0, 0], planned: is30 ? [356, 282, 436, 324, 242, 176, 566, 492, 396] : [356, 282, 436, 324, 242, 176, 558, 486, 392], safety: [172, 172, 172, 172, 172, 172, 172, 172, 172],
      decision: { qty: is30 ? 490 : 480, window: is30 ? "09-24 ~ 09-26" : "09-24 ~ 09-27", latest: is30 ? "09-26" : "09-27", note: is30 ? "按近30日均销测算，最晚采购窗口提前到 09-26；若广告继续放量，建议一次采购 490 件并优先确认供应商交期。" : "按近14日销量速度计算，最晚 09-27 前下单更稳；若销量继续上升，建议采购量不低于 480 件。" },
    },
    risk: { score: is30 ? 80 : 82, summary: [["12", "监控项", ""], ["7", "正常", "up"], ["5", "关注", "warn"], ["0", "严重", ""], [is30 ? "4" : "3", is30 ? "30天新增" : "24h新增", "warn"]], items: riskBase.map((item) => item.key === "keyword" ? { ...item, value: is30 ? "8词下降" : "5词下降", sub: is30 ? "最大↓9位" : "最大↓6位" } : item) },
    timeline: { events, sales, orders: sales.map((v) => Math.round(v * 1.02)) },
  };
}

const periodData = buildPeriodData();


/* price daily bars patch start */
const priceDailyLabels14 = [
  "09-04", "09-05", "09-06", "09-07", "09-08", "09-09", "09-10",
  "09-11", "09-12", "09-13", "09-14", "09-15", "09-16", "09-17",
];

const priceDailySales14 = [16, 13, 14, 16, 17, 17, 7, 10, 7, 13, 12, 10, 10, 11];

const priceDailyLabels30 = [
  "08-19", "08-20", "08-21", "08-22", "08-23", "08-24", "08-25", "08-26", "08-27", "08-28",
  "08-29", "08-30", "08-31", "09-01", "09-02", "09-03", "09-04", "09-05", "09-06", "09-07",
  "09-08", "09-09", "09-10", "09-11", "09-12", "09-13", "09-14", "09-15", "09-16", "09-17",
];

const priceDailySales30 = [
  11, 12, 12, 14, 15, 10, 16, 12, 13, 17,
  12, 15, 11, 12, 14, 11, 16, 13, 14, 16,
  17, 17, 6, 9, 6, 12, 11, 9, 9, 9,
];

function buildDailyPriceSeries(period: 14 | 30, labels: string[]) {
  return labels.map((_, index) => {
    if (period === 30) {
      if (index <= 4) return 28.99;
      if (index <= 10) return 27.99;
      if (index <= 22) return 26.99;
      return 27;
    }
    if (index <= 3) return 27.99;
    if (index <= 8) return 26.99;
    return 27;
  });
}

function buildDailyCompetitorSeries(labels: string[]) {
  const base = [25.8, 25.6, 25.5, 25.3, 25.2, 25.4, 25.6, 25.1, 25, 25.2];
  return labels.map((_, index) => base[index % base.length]);
}

function applyPriceDailyBars(period: 14 | 30, labels: string[], sales: number[]) {
  const target = periodData[period].price;

  target.labels = labels;
  target.sales = sales;
  target.price = buildDailyPriceSeries(period, labels);
  target.competitor = buildDailyCompetitorSeries(labels);

  target.kpis = [
    ["当前售价", "$27.00", "今日 Listing 售价"],
    [`${period}日最高`, "$28.99", period === 30 ? "08-19 ~ 09-12" : "09-04 ~ 09-12"],
    [`${period}日最低`, "$26.99", "09-13 ~ 09-15"],
    ["调价次数", period === 30 ? "4次" : "3次", "按每日价格轨迹展示"],
    ["竞争ID", "5个", "点击可叠加价格趋势"],
  ];

  target.events = period === 30
    ? [
        ["08-24", "售价 $28.99 → $27.99", "-$1.00", "14", "12", "-14.3%", "down"],
        ["09-03", "售价 $27.99 → $26.99", "-$1.00", "15", "11", "-26.7%", "down"],
        ["09-13", "低价期后观察销量", "观察", "17", "6", "-64.7%", "down"],
        ["09-16", "售价 $26.99 → $27.00", "+$0.01", "9", "12", "+33.3%", "up"],
      ]
    : [
        ["09-08", "售价 $27.99 → $26.99", "-$1.00", "17", "7", "-58.8%", "down"],
        ["09-13", "低价期后观察销量", "观察", "13", "7", "-46.2%", "down"],
        ["09-16", "售价 $26.99 → $27.00", "+$0.01", "10", "11", "+10.0%", "up"],
      ];
}

applyPriceDailyBars(14, priceDailyLabels14, priceDailySales14);
applyPriceDailyBars(30, priceDailyLabels30, priceDailySales30);
/* price daily bars patch end */



/* overview daily trend points patch start */
const overviewDailyLabels14 = [
  "09-04", "09-05", "09-06", "09-07", "09-08", "09-09", "09-10",
  "09-11", "09-12", "09-13", "09-14", "09-15", "09-16", "09-17",
];

const overviewDailySales14 = [16, 13, 14, 16, 17, 17, 7, 10, 7, 13, 12, 10, 10, 11];

const overviewDailyLabels30 = [
  "08-19", "08-20", "08-21", "08-22", "08-23", "08-24", "08-25", "08-26", "08-27", "08-28",
  "08-29", "08-30", "08-31", "09-01", "09-02", "09-03", "09-04", "09-05", "09-06", "09-07",
  "09-08", "09-09", "09-10", "09-11", "09-12", "09-13", "09-14", "09-15", "09-16", "09-17",
];

const overviewDailySales30 = [
  11, 12, 12, 14, 15, 10, 16, 12, 13, 17,
  12, 15, 11, 12, 14, 11, 16, 13, 14, 16,
  17, 17, 6, 9, 6, 12, 11, 9, 9, 9,
];

function applyOverviewDailyTrend(period: 14 | 30, labels: string[], sales: number[]) {
  const target = periodData[period].overview;
  const revenue = sales.map((value) => value * 27);
  const price = labels.map((_, index) => {
    if (period === 30) {
      if (index <= 4) return 28.99;
      if (index <= 10) return 27.99;
      if (index <= 22) return 26.99;
      return 27;
    }
    if (index <= 3) return 27.99;
    if (index <= 8) return 26.99;
    return 27;
  });
  const profit = sales.map((value, index) => Math.max(18, Math.round(value * 5.7 - (index % 3) * 2)));
  const ads = sales.map((value, index) => Math.max(16, Math.round(value * 3.2 + (index % 4) * 2)));
  const refund = labels.map((_, index) => {
    if (period === 30) return [2, 9, 14, 23, 24, 27].includes(index) ? [18, 24, 16, 29, 13, 24][[2, 9, 14, 23, 24, 27].indexOf(index)] : 0;
    return [3, 8, 12].includes(index) ? [18, 24, 29][[3, 8, 12].indexOf(index)] : 0;
  });

  // 按右侧原版：顶部 KPI / 今日诊断 / 订单结构仍然是当前日快照，不显示 30 天累计
  target.kpis = periodData[7].overview.kpis;
  target.diagnosis = periodData[7].overview.diagnosis;
  target.order = periodData[7].overview.order;

  // 只有趋势窗口跟随 14 / 30 天，且每天一个点，不再做 7 段聚合
  target.labels = labels;
  target.trends.sales.current = sales;
  target.trends.sales.previous = sales.map((value, index) => Math.max(0, value - (index % 5 === 0 ? 2 : 1)));
  target.trends.sales.sub = `${period}天每日销量，不做区间聚合`;

  target.trends.revenue.current = revenue;
  target.trends.revenue.previous = revenue.map((value, index) => Math.max(0, value - (index % 5 === 0 ? 54 : 27)));
  target.trends.revenue.sub = `${period}天每日销售额`;

  target.trends.price.current = price;
  target.trends.price.previous = price.map((value) => Number((value + 0.5).toFixed(2)));
  target.trends.price.sub = `${period}天每日售价`;

  target.trends.profit.current = profit;
  target.trends.profit.previous = profit.map((value, index) => Math.max(0, value - (index % 4 === 0 ? 8 : 5)));
  target.trends.profit.sub = `${period}天每日利润`;

  target.trends.ads.current = ads;
  target.trends.ads.previous = ads.map((value, index) => Math.max(0, value - (index % 4 === 0 ? 8 : 5)));
  target.trends.ads.sub = `${period}天每日广告费`;

  target.trends.refund.current = refund;
  target.trends.refund.previous = refund.map((value) => Math.max(0, value - 6));
  target.trends.refund.sub = `${period}天每日退款金额`;
}

applyOverviewDailyTrend(14, overviewDailyLabels14, overviewDailySales14);
applyOverviewDailyTrend(30, overviewDailyLabels30, overviewDailySales30);
/* overview daily trend points patch end */


function Chart({ option, className, onEvents }: { option: EChartsOption; className: string; onEvents?: Record<string, (params: unknown) => void> }) {
  return <div className={className}><ReactECharts option={option} notMerge lazyUpdate onEvents={onEvents} style={{ width: "100%", height: "100%" }} /></div>;
}


type MutableEchartsPart = Record<string, unknown>;

function toOptionArray(value: unknown): MutableEchartsPart[] {
  if (!value) return [];
  return Array.isArray(value) ? value as MutableEchartsPart[] : [value as MutableEchartsPart];
}

function boostOverviewTrendOption(option: EChartsOption): EChartsOption {
  const mutable = option as MutableEchartsPart;

  mutable.grid = {
    left: 38,
    right: 20,
    top: 54,
    bottom: 34,
    containLabel: true,
  };

  const tooltip = (mutable.tooltip || {}) as MutableEchartsPart;
  tooltip.textStyle = {
    ...((tooltip.textStyle || {}) as MutableEchartsPart),
    fontSize: 12,
    lineHeight: 18,
  };
  mutable.tooltip = tooltip;

  toOptionArray(mutable.xAxis).forEach((axis) => {
    axis.axisLabel = {
      ...((axis.axisLabel || {}) as MutableEchartsPart),
      fontSize: 11,
      margin: 12,
      color: "#8a95a6",
    };
    axis.axisLine = {
      ...((axis.axisLine || {}) as MutableEchartsPart),
      lineStyle: { color: "#e4edf7" },
    };
  });

  toOptionArray(mutable.yAxis).forEach((axis) => {
    axis.axisLabel = {
      ...((axis.axisLabel || {}) as MutableEchartsPart),
      fontSize: 11,
      margin: 10,
      color: "#8a95a6",
    };
    axis.nameTextStyle = {
      ...((axis.nameTextStyle || {}) as MutableEchartsPart),
      fontSize: 10,
      color: "#8a95a6",
    };
  });

  toOptionArray(mutable.series).forEach((series) => {
    const name = String(series.name || "");
    series.symbolSize = name === "当前周期" ? 8 : 6;
    series.lineStyle = {
      ...((series.lineStyle || {}) as MutableEchartsPart),
      width: name === "当前周期" ? 3 : 2.2,
    };

    if (series.label) {
      series.label = {
        ...((series.label || {}) as MutableEchartsPart),
        show: true,
        position: "top",
        distance: 10,
        fontSize: 12,
        lineHeight: 14,
        fontWeight: 800,
        color: "#1677ff",
      };
    }
  });

  return mutable as EChartsOption;
}


function lineOption(labels: string[], series: Array<{ name: string; data: number[]; color: string; dashed?: boolean; bar?: boolean; yAxisIndex?: number; showLabel?: boolean }>, yName?: string): EChartsOption {
  return {
    animationDuration: 240,
    color: series.map((item) => item.color),
    grid: { left: 34, right: 18, top: 24, bottom: 28 },
    tooltip: { trigger: "axis", backgroundColor: "#172033", borderWidth: 0, textStyle: { color: "#fff", fontSize: 7 } },
    xAxis: { type: "category", data: labels, boundaryGap: series.some((item) => item.bar), axisTick: { show: false }, axisLine: { lineStyle: { color: "#e4edf7" } }, axisLabel: { color: "#7c8798", fontSize: 8 } },
    yAxis: { type: "value", name: yName, nameTextStyle: { color: "#8a95a6", fontSize: 8 }, splitLine: { lineStyle: { color: "#eef3f8" } }, axisLabel: { color: "#8a95a6", fontSize: 8 } },
    series: series.map((item) => ({ name: item.name, type: item.bar ? "bar" : "line", smooth: true, symbolSize: item.bar ? 0 : 6, barWidth: item.bar ? 14 : undefined, data: item.data, yAxisIndex: item.yAxisIndex, lineStyle: item.dashed ? { type: "dashed", width: 2 } : { width: 2.4 }, itemStyle: { color: item.color, borderRadius: item.bar ? [4, 4, 0, 0] : undefined }, label: item.showLabel ? { show: true, position: "top", color: item.color, fontSize: 7, fontWeight: 800, formatter: (params: { value: number | string }) => `${params.value}` } : undefined, areaStyle: item.bar || item.dashed ? undefined : { color: { type: "linear", x: 0, y: 0, x2: 0, y2: 1, colorStops: [{ offset: 0, color: `${item.color}25` }, { offset: 1, color: `${item.color}00` }] } } })),
  } as EChartsOption;
}

export function ListingAnalysisModal({ open, onClose, source, initialPanel = "overview" }: ListingAnalysisModalProps) {
  const [period, setPeriod] = useState<ListingAnalysisPeriod>(7);
  const [activePanel, setActivePanel] = useState<ListingAnalysisPanel>(initialPanel);

  useEffect(() => {
    if (!open) return;

    let active = true;

    queueMicrotask(() => {
      if (active) setActivePanel(initialPanel);
    });

    return () => {
      active = false;
    };
  }, [initialPanel, open]);

  useEffect(() => {
    if (!open) return;
    const previousOverflow = document.body.style.overflow;
    const onKeyDown = (event: KeyboardEvent) => { if (event.key === "Escape") onClose(); };
    document.body.style.overflow = "hidden";
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.body.style.overflow = previousOverflow;
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [onClose, open]);

  if (!open) return null;

  const data = periodData[period];
  const titleName = source?.title || source?.productName || source?.itemName || "Multipurpose Storage Bags";
  const id = source?.productId || source?.sku || "AX1042";
  const meta = [source?.sku ? `SKU ${source.sku}` : "SKU AX1042", source?.msku ? `MSKU ${source.msku}` : "", source?.date || "2026-09-17", source?.platform || "Walmart US", source?.store || ""].filter(Boolean);

  return (
    <div className="listing-analysis-layer show entered">
      <button className="modal-mask" type="button" aria-label="关闭分析弹框" onClick={onClose} />
      <section className="modal" role="dialog" aria-modal="true" aria-label="Listing经营分析中心">
        <header className="m-head">
          <div className="listing-main"><div className="listing-icon">LST</div><div className="listing-copy"><div className="listing-title">Listing #{id} · {titleName}</div><div className="listing-meta">{meta.map((item, index) => <span className="listing-meta-fragment" key={`${item}-${index}`}>{index > 0 && <i className="meta-dot" />}<span>{item}</span></span>)}<i className="meta-dot" /><span className="badge green">{source?.status || "正常在售"}</span></div></div></div>
          <div className="head-right"><div className="period">{([7, 14, 30] as ListingAnalysisPeriod[]).map((value) => <button key={value} type="button" className={period === value ? "active" : ""} onClick={() => setPeriod(value)}>{value}天</button>)}</div><button className="close-btn" type="button" onClick={onClose} aria-label="关闭"><svg viewBox="0 0 24 24"><path d="M6 6l12 12M18 6 6 18" /></svg></button></div>
        </header>
        <nav className="tabs">{panels.map((panel) => <button key={panel.key} type="button" className={activePanel === panel.key ? "active" : ""} onClick={() => setActivePanel(panel.key)}>{panel.label}</button>)}</nav>
        <div className="content">
          {activePanel === "overview" && <OverviewPanel period={period} data={data} />}
          {activePanel === "compare" && <ComparePanel period={period} data={data} />}
          {activePanel === "price" && <PricePanel period={period} data={data} />}
          {activePanel === "adsAnalysis" && <AdsPanel period={period} data={data} />}
          {activePanel === "profit" && <ProfitPanel period={period} data={data} />}
          {activePanel === "stock" && <StockPanel period={period} data={data} />}
          {activePanel === "risk" && <RiskPanel period={period} data={data} />}
          {activePanel === "timeline" && <TimelinePanel period={period} data={data} />}
        </div>
      </section>
    </div>
  );
}

function OverviewPanel({ period, data }: { period: ListingAnalysisPeriod; data: PeriodData }) {
  const [metric, setMetric] = useState<MetricKey>("sales");
  const [compareEnabled, setCompareEnabled] = useState(true);
  const [diagnosis, setDiagnosis] = useState(data.overview.diagnosis[0].detail);
  const [orderSegment, setOrderSegment] = useState<"natural" | "ads">("natural");
  const trend = data.overview.trends[metric];
  const overviewLabels = data.overview.labels ?? data.labels;
  const total = data.overview.order.natural + data.overview.order.ads;
  const naturalPct = Math.round(data.overview.order.natural / total * 100);
  const adsPct = 100 - naturalPct;
  const trendOption = boostOverviewTrendOption(lineOption(overviewLabels, [...(compareEnabled ? [{ name: "上期", data: trend.previous, color: "#c3ccd8", dashed: true }] : []), { name: "当前周期", data: trend.current, color: "#1677ff", showLabel: true }], trend.unit));
  const structureOption = { animationDuration: 240, tooltip: {
      trigger: "item",
      formatter: "{b}<br/>{c} 单 · {d}%",
      renderMode: "html",
      appendToBody: true,
      confine: false,
      backgroundColor: "#172033",
      borderWidth: 0,
      padding: [8, 10],
      extraCssText: "z-index:99999;box-shadow:0 8px 24px rgba(15,23,42,.22);border-radius:8px;pointer-events:none;",
      textStyle: { color: "#fff", fontSize: 12, lineHeight: 18 },
    }, graphic: [{ type: "text", left: "center", top: "39%", style: { text: `${total}`, fill: "#172033", fontSize: 24, fontWeight: 900, textAlign: "center" } }, { type: "text", left: "center", top: "57%", style: { text: "订单", fill: "#7b8799", fontSize: 11, fontWeight: 700, textAlign: "center" } }], series: [{ type: "pie", radius: ["62%", "82%"], center: ["50%", "50%"], selectedMode: "single", selectedOffset: 3, label: { show: false }, labelLine: { show: false }, itemStyle: { borderColor: "#fff", borderWidth: 2 }, data: [{ name: "自然订单", value: data.overview.order.natural, selected: orderSegment === "natural", itemStyle: { color: "#1677ff" } }, { name: "广告订单", value: data.overview.order.ads, selected: orderSegment === "ads", itemStyle: { color: "#13a8a8" } }] }] } as EChartsOption;
  const onPie = (params: unknown) => {
    const name = typeof params === "object" && params !== null && "name" in params ? String((params as { name?: unknown }).name) : "";
    if (name === "自然订单") setOrderSegment("natural");
    if (name === "广告订单") setOrderSegment("ads");
  };
  return (
    <div className="panel active" id="overview">
      <div className="kpis">{data.overview.kpis.map((item) => <button key={item.label} type="button" className={`kpi ${metric === item.key ? "active" : ""}`} onClick={() => item.key && setMetric(item.key)}><div className="kpi-label">{item.label}</div><div className="kpi-value">{item.value}</div><div className={`kpi-foot ${cls(item.tone)}`}>{item.foot}</div></button>)}</div>
      <div className="overview-grid">
        <section className="surface trend-card"><div className="card-head"><div><div className="section-title">{trend.title}</div><div className="section-sub">{period}天 · {trend.sub}</div></div><div className="trend-actions"><div className="metric-tabs">{data.overview.kpis.filter((item) => item.key).map((item) => <button key={item.key} type="button" className={metric === item.key ? "active" : ""} onClick={() => item.key && setMetric(item.key)}>{item.label}</button>)}</div><button className={`primary-toggle ${compareEnabled ? "active" : ""}`} type="button" onClick={() => setCompareEnabled((v) => !v)}>上期对比</button></div></div><Chart option={trendOption} className="trend-chart" /></section>
        <div className="overview-side">
          <section className="surface diagnosis"><div className="side-head"><div><div className="section-title">今日诊断</div><div className="section-sub">仅展示可直接拿到的数据</div></div><span className="badge blue">Listing</span></div><div className="diag-list">{data.overview.diagnosis.map((item) => <button key={item.title} type="button" className="diag-item" onClick={() => setDiagnosis(item.detail)}><span className="diag-icon">{item.icon}</span><span><b>{item.title}</b><small>{item.sub}</small></span><strong className={cls(item.tone)}>{item.value}</strong></button>)}</div><div className="diag-detail">{diagnosis}</div></section>
          <section className="surface structure"><Chart option={structureOption} className="structure-chart" onEvents={{ mouseover: onPie }} /><div className="structure-body"><div className="section-title">订单结构</div><button type="button" className={orderSegment === "natural" ? "structure-row active" : "structure-row"} onMouseEnter={() => setOrderSegment("natural")}><span>自然订单</span><b>{data.overview.order.natural} · {naturalPct}%</b></button><button type="button" className={orderSegment === "ads" ? "structure-row active" : "structure-row"} onMouseEnter={() => setOrderSegment("ads")}><span>广告订单</span><b>{data.overview.order.ads} · {adsPct}%</b></button><div className="traffic-inline"><div className="traffic-cell"><div className="l">曝光</div><div className="v">{data.overview.order.impressions}</div></div><div className="traffic-cell"><div className="l">访问</div><div className="v">{data.overview.order.visits}</div></div><div className="traffic-cell"><div className="l">CVR</div><div className="v">{data.overview.order.cvr}</div></div></div></div></section>
        </div>
      </div>
    </div>
  );
}

function ComparePanel({ period, data }: { period: ListingAnalysisPeriod; data: PeriodData }) {
  const [mode, setMode] = useState<CompareMode>("yesterday");
  const current = data.compare[mode];
  const cards = [
    ["经营结果", "今天最终卖得怎么样、赚得怎么样", "结果", current.result],
    ["流量与转化", "曝光 → 点击 → 访问 → 订单", "漏斗", current.traffic],
    ["广告摘要", "整体效率；自动/手动拆分放到广告分析", "广告", current.ads],
    ["经营质量", "退款、Review、Buy Box 与库存风险", "质量", current.quality],
  ] as const;
  return <div className="panel active" id="compare"><div className="panel-title-row"><div><h3>经营指标对比</h3><p>{period}天周期 · 结果、流量转化、广告摘要和经营质量统一查看</p></div><div className="cmp-tabs">{([["yesterday", "今日 vs 昨日"], ["avg7", "今日 vs 7日均值"], ["lastweek", "今日 vs 上周同日"]] as Array<[CompareMode, string]>).map(([key, label]) => <button key={key} type="button" className={mode === key ? "active" : ""} onClick={() => setMode(key)}>{label}</button>)}</div></div><div className="cmp4-grid">{cards.map(([title, sub, badge, list]) => <section className="surface cmp4-card" key={title}><div className="section-head-line"><div><div className="section-title">{title}</div><div className="section-sub">{sub}</div></div><span className="badge blue">{badge}</span></div><div className="metric-grid">{list.map((item) => <div className="metric-box" key={item[0]}><span>{item[0]}</span><b>{item[1]}</b><small className={cls(item[3] as Tone)}>{item[2]}</small><i>{item[3] === "up" ? "良好" : item[3] === "warn" ? "关注" : item[3] === "down" ? "下降" : ""}</i></div>)}</div></section>)}</div></div>;
}

function PricePanel({ period, data }: { period: ListingAnalysisPeriod; data: PeriodData }) {
  const [showCompetitor, setShowCompetitor] = useState(true);
  const [side, setSide] = useState<"adjust" | "competitor">("adjust");
  const priceLabels = data.price.labels ?? data.labels;

  const option = {
    animationDuration: 240,
    color: ["#d5eaff", "#1677ff", "#b7c6d9"],
    grid: {
      left: 42,
      right: 48,
      top: 42,
      bottom: 34,
      containLabel: true,
    },
    tooltip: {
      trigger: "axis",
      axisPointer: { type: "line" },
      backgroundColor: "#172033",
      borderWidth: 0,
      padding: [8, 10],
      textStyle: {
        color: "#fff",
        fontSize: 12,
        lineHeight: 18,
      },
      valueFormatter: (value: number | string) => String(value),
    },
    legend: {
      top: 8,
      right: 10,
      itemWidth: 14,
      itemHeight: 8,
      textStyle: {
        color: "#65748a",
        fontSize: 10,
      },
    },
    xAxis: {
      type: "category",
      data: priceLabels,
      axisTick: { show: false },
      axisLine: { lineStyle: { color: "#e4edf7" } },
      axisLabel: {
        color: "#7c8798",
        fontSize: 10,
        interval: priceLabels.length > 14 ? 1 : 0,
        margin: 10,
      },
    },
    yAxis: [
      {
        type: "value",
        name: "销量",
        min: 0,
        splitLine: { lineStyle: { color: "#eef3f8" } },
        axisLabel: {
          color: "#8a95a6",
          fontSize: 10,
        },
      },
      {
        type: "value",
        name: "$",
        min: 23,
        max: 31,
        splitLine: { show: false },
        axisLabel: {
          color: "#8a95a6",
          fontSize: 10,
          formatter: "${value}",
        },
      },
    ],
    series: [
      {
        name: "销量",
        type: "bar",
        barWidth: priceLabels.length > 14 ? 8 : 16,
        data: data.price.sales,
        itemStyle: {
          color: "#d2e7ff",
          borderRadius: [5, 5, 0, 0],
        },
        label: {
          show: true,
          position: "top",
          color: "#1677ff",
          fontSize: 10,
          fontWeight: 800,
        },
      },
      {
        name: "当前售价",
        type: "line",
        yAxisIndex: 1,
        data: data.price.price,
        smooth: true,
        symbolSize: 7,
        lineStyle: {
          width: 2.4,
          color: "#1677ff",
        },
        itemStyle: {
          color: "#1677ff",
        },
        label: {
          show: false,
        },
      },
      {
        name: `${data.price.competitorId} 竞价`,
        type: "line",
        yAxisIndex: 1,
        data: showCompetitor ? data.price.competitor : [],
        smooth: true,
        symbolSize: 0,
        lineStyle: {
          width: 1.8,
          color: "#b7c6d9",
        },
        itemStyle: {
          color: "#b7c6d9",
        },
        label: {
          show: false,
        },
      },
    ],
  } as EChartsOption;

  return (
    <div className="panel active" id="price">
      <div className="small-kpis">
        {data.price.kpis.map(([label, value, sub]) => (
          <div className="small-kpi" key={label}>
            <div className="l">{label}</div>
            <div className="v">{value}</div>
            <small>{sub}</small>
          </div>
        ))}
      </div>

      <div className="price-grid">
        <section className="surface price-chart-card">
          <div className="section-head-line">
            <div>
              <div className="section-title">售价 × 销量联动</div>
              <div className="section-sub">{period}天 · 鼠标移入查看每日售价 / 销量 / 竞品价</div>
            </div>
            <div className="price-actions">
              <span className="chip">竞品：{data.price.competitorId}</span>
              <button type="button" onClick={() => setShowCompetitor((value) => !value)}>
                {showCompetitor ? "隐藏竞品价格" : "显示竞品价格"}
              </button>
            </div>
          </div>

          <Chart option={option} className="price-chart" />
        </section>

        <aside className="surface price-side">
          <div className="side-head">
            <div>
              <div className="section-title">售价分析</div>
              <div className="section-sub">调价记录与竞争ID统一查看</div>
            </div>
            <span className="badge blue">Listing</span>
          </div>

          <div className="price-switch">
            <button type="button" className={side === "adjust" ? "active" : ""} onClick={() => setSide("adjust")}>
              调价前后
            </button>
            <button type="button" className={side === "competitor" ? "active" : ""} onClick={() => setSide("competitor")}>
              竞争ID
            </button>
          </div>

          {side === "adjust" ? (
            <div className="price-events">
              {data.price.events.map(([date, title, delta, before, after, change, tone]) => (
                <div className="price-event" key={`${date}-${title}`}>
                  <div>
                    <small>{date}</small>
                    <b>{title}</b>
                  </div>
                  <span className={cls(tone)}>{delta}</span>
                  <div className="price-event-grid">
                    <p>
                      <small>调价前</small>
                      <b>{before}</b>
                    </p>
                    <p>
                      <small>调价后</small>
                      <b>{after}</b>
                    </p>
                    <p>
                      <small>销量变化</small>
                      <b className={cls(tone)}>{change}</b>
                    </p>
                  </div>
                </div>
              ))}
              <div className="price-note">
                售价线不常驻显示价格，避免 30 天时文字拥挤；鼠标移入图表可查看每日售价、销量和竞品价。
              </div>
            </div>
          ) : (
            <div className="competitor-list">
              {["WM-C784521", "WM-C631208", "WM-C187433", "WM-C902144"].map((id, index) => (
                <button type="button" key={id} className={index === 0 ? "active" : ""}>
                  <span>{id}</span>
                  <b>{index === 0 ? "$25.00" : index === 1 ? "$26.49" : "$28.49"}</b>
                </button>
              ))}
            </div>
          )}
        </aside>
      </div>
    </div>
  );
}

function AdsPanel({ period, data }: { period: ListingAnalysisPeriod; data: PeriodData }) {
  const [scope, setScope] = useState<AdScope>("auto");
  const [metrics, setMetrics] = useState<AdMetric[]>(["spend", "orders"]);
  const [mode, setMode] = useState<"auto" | "manual">("auto");
  const [source, setSource] = useState<KeywordSource>("all");
  const [sort, setSort] = useState<KeywordSort>("clicks");
  const [drawerKeyword, setDrawerKeyword] = useState<KeywordRow | null>(null);
  const [campaignOpen, setCampaignOpen] = useState(false);
  const toggleMetric = (metric: AdMetric) => setMetrics((current) => current.includes(metric) ? current.length === 1 ? current : current.filter((item) => item !== metric) : [...current, metric]);
  const selectAdScope = (nextScope: AdScope) => {
    setScope(nextScope);
    if (nextScope === "auto" || nextScope === "manual") {
      setMode(nextScope);
    }
  };

  const selectAdMode = (nextMode: "auto" | "manual") => {
    setMode(nextMode);
    setScope(nextMode);
  };

  const visibleKeywords = [...data.ads.keywords].filter((item) => source === "all" || item.source === source).sort((a, b) => {
    if (sort === "spend") return b.spend - a.spend;
    if (sort === "orders") return b.orders - a.orders;
    if (sort === "rank") return Math.abs(b.organicDelta) - Math.abs(a.organicDelta);
    if (sort === "waste") return (a.orders === 0 ? -a.spend : 0) - (b.orders === 0 ? -b.spend : 0);
    return b.clicks - a.clicks;
  });
  const option = { animationDuration: 240, color: metrics.map((item) => adMetricMeta[item].color), grid: { left: 42, right: 36, top: 28, bottom: 48, containLabel: true }, tooltip: { trigger: "axis", backgroundColor: "#172033", borderWidth: 0, textStyle: { color: "#fff", fontSize: 7 } }, xAxis: { type: "category", data: data.labels, boundaryGap: false, axisTick: { show: false }, axisLine: { lineStyle: { color: "#e4edf7" } }, axisLabel: { color: "#7c8798", fontSize: 10, margin: 12, interval: data.labels.length > 14 ? 1 : 0 } }, yAxis: [{ type: "value", axisLabel: { color: "#8a95a6", fontSize: 10, formatter: "${value}" }, splitLine: { lineStyle: { color: "#eef3f8" } } }, { type: "value", axisLabel: { color: "#8a95a6", fontSize: 10 }, splitLine: { show: false } }], series: metrics.map((key) => ({ name: adMetricMeta[key].label, type: "line", yAxisIndex: ["clicks", "orders", "acos"].includes(key) ? 1 : 0, data: data.ads.trend[scope][key], smooth: true, symbolSize: 6, lineStyle: { width: 2.4, color: adMetricMeta[key].color }, itemStyle: { color: adMetricMeta[key].color }, areaStyle: key === "spend" || key === "sales" ? { color: { type: "linear", x: 0, y: 0, x2: 0, y2: 1, colorStops: [{ offset: 0, color: `${adMetricMeta[key].color}20` }, { offset: 1, color: `${adMetricMeta[key].color}00` }] } } : undefined })) } as EChartsOption;
  return <div className="panel active" id="adsAnalysis"><div className="adv5-kpis">{data.ads.kpis.map((item) => <div className="adv5-kpi" key={item.label}><div className="adv5-kpi-main"><div className="adv5-kpi-label">{item.label}</div><div className="adv5-kpi-value">{item.value}</div></div><div className="adv5-kpi-period">近{period}天</div><div className="adv5-kpi-side"><span>{item.sideLabel}</span><b>{item.sideValue}</b></div></div>)}</div><div className="adv5-workspace"><div className="adv5-upper"><section className="surface adv5-chart-card"><div className="adv5-chart-top"><div><div className="adv5-title">广告趋势</div><div className="adv5-sub">最近{period}天 · {scope === "all" ? "全部广告" : scope === "auto" ? "自动广告" : "手动广告"} · 已选 {metrics.map((key) => adMetricMeta[key].label).join(" / ")}</div></div><div className="adv5-metric-checks">{(["spend", "clicks", "orders", "sales", "acos"] as AdMetric[]).map((key) => <button key={key} type="button" className={metrics.includes(key) ? "active" : ""} onClick={() => toggleMetric(key)}>{adMetricMeta[key].label}</button>)}</div></div><div className="adv5-chart-tools"><div className="adv5-seg">{([["all", "全部"], ["auto", "自动"], ["manual", "手动"]] as Array<[AdScope, string]>).map(([key, label]) => <button key={key} type="button" className={scope === key ? "active" : ""} onClick={() => selectAdScope(key)}>{label}</button>)}</div></div><Chart option={option} className="ad-trend-chart" /></section><section className="surface adv5-side-card"><div className="adv5-side-head"><div><div className="adv5-title">自动 vs 手动</div><div className="adv5-sub">看钱主要花在哪，订单主要从哪来</div></div><span className="badge blue">{period}天</span></div><div className="adv5-mode-list">{(["auto", "manual"] as Array<"auto" | "manual">).map((key) => { const item = data.ads.modes[key]; return <button key={key} type="button" className={`adv5-mode ${scope === key ? "active" : ""}`} onClick={() => selectAdMode(key)}><div className="adv5-mode-head"><b><i className={key} />{item.name}</b><span>{item.share}</span></div><div className="adv5-mode-row"><strong>{item.spend}</strong><small>{item.result}</small></div><div className="adv5-mode-eff"><span>CPC<b>{item.cpc}</b></span><span>CVR<b>{item.cvr}</b></span><span>ACOS<b>{item.acos}</b></span></div></button>; })}<button type="button" className="adv5-campaign-link" onClick={() => setCampaignOpen(true)}>查看 Campaign 明细</button></div></section></div><section className="surface adv5-keyword-card"><div className="adv-layout-keybar"><div className="adv-layout-key-title"><div className="adv5-title">关键词 / 搜索词重点</div><div className="adv5-sub">从曝光、点击、花费、订单到排名与竞价，快速找到需要处理的词</div></div><div className="adv-layout-group"><span>查看</span><div className="adv5-seg">{([["all", "全部"], ["manual", "手动关键词"], ["auto", "自动搜索词"]] as Array<[KeywordSource, string]>).map(([key, label]) => <button key={key} type="button" className={source === key ? "active" : ""} onClick={() => setSource(key)}>{label}</button>)}</div></div><div className="adv-layout-group"><span>排序</span><div className="adv5-seg">{([["clicks", "点击最多"], ["spend", "花费最多"], ["orders", "订单最多"], ["rank", "排名变化"], ["waste", "高花费无单"]] as Array<[KeywordSort, string]>).map(([key, label]) => <button key={key} type="button" className={sort === key ? "active" : ""} onClick={() => setSort(key)}>{label}</button>)}</div></div><span className="adv5-alert-chip">{data.ads.alert}</span></div><div className="adv5-keyword-table"><div className="adv5-keyrow header"><span>关键词 / 搜索词</span><span>匹配</span><span>当前位置</span><span>曝光</span><span>点击</span><span>花费</span><span>订单</span><span>CPC</span><span>CPA</span><span>CVR</span><span>ROAS</span><span>当前竞价</span></div>{visibleKeywords.map((row) => <button key={`${row.term}-${row.source}`} type="button" className="adv5-keyrow" onClick={() => setDrawerKeyword(row)}><span className="adv5-keyword"><b>{row.term}</b><small>{row.source === "manual" ? "手动关键词" : "自动搜索词"}</small></span><span className={`adv5-match ${row.match.toLowerCase()}`}>{row.match}</span><span className="adv5-pos"><b>自然 #{row.organicRank} <i className={row.organicDelta >= 0 ? "up" : "down"}>{row.organicDelta >= 0 ? `↑ ${row.organicDelta}` : `↓ ${Math.abs(row.organicDelta)}`}</i></b><small>Sponsored #{row.sponsoredRank}</small></span><span>{num(row.impressions)}</span><span>{num(row.clicks)}</span><span>{money(row.spend)}</span><span className={row.orders === 0 ? "down" : ""}>{row.orders}</span><span>{money(row.cpc)}</span><span>{row.cpa == null ? "—" : money(row.cpa)}</span><span>{row.cvr.toFixed(2)}%</span><span>{row.roas.toFixed(2)}</span><span><b className="adv5-bid-pill">{money(row.bid)}</b></span></button>)}</div></section></div>{campaignOpen && (
        <CampaignDetailDrawer
          period={period}
          mode={mode}
          data={data.ads}
          labels={data.labels}
          onClose={() => setCampaignOpen(false)}
        />
      )}
      {drawerKeyword && <KeywordDrawer keyword={drawerKeyword} labels={data.labels} onClose={() => setDrawerKeyword(null)} />}</div>;
}


function CampaignDetailDrawer({
  period,
  mode,
  data,
  labels,
  onClose,
}: {
  period: ListingAnalysisPeriod;
  mode: "auto" | "manual";
  data: PeriodData["ads"];
  labels: string[];
  onClose: () => void;
}) {
  const selected = data.modes[mode];
  const trend = data.trend[mode];

  const rows = labels.map((date, index) => ({
    date,
    spend: trend.spend[index] ?? 0,
    clicks: trend.clicks[index] ?? 0,
    orders: trend.orders[index] ?? 0,
    sales: trend.sales[index] ?? 0,
    acos: trend.acos[index] ?? 0,
  }));

  const chartOption = lineOption(
    labels,
    [
      { name: "广告费", data: trend.spend, color: "#1677ff" },
      { name: "订单", data: trend.orders, color: "#f5a623" },
      { name: "销售额", data: trend.sales, color: "#13a8a8" },
    ],
    "$",
  );

  return (
    <div className="adv5-campaign-mask" role="presentation" onMouseDown={onClose}>
      <aside className="adv5-campaign-drawer" role="dialog" aria-modal="true" onMouseDown={(event) => event.stopPropagation()}>
        <div className="campaign-drawer-head">
          <div>
            <small>{period}天 · {selected.name}</small>
            <h3>Campaign 明细</h3>
          </div>
          <button type="button" onClick={onClose}>关闭</button>
        </div>

        <div className="campaign-summary">
          <div>
            <span>广告花费</span>
            <b>{selected.spend}</b>
          </div>
          <div>
            <span>点击 / 订单</span>
            <b>{selected.result}</b>
          </div>
          <div>
            <span>CPC</span>
            <b>{selected.cpc}</b>
          </div>
          <div>
            <span>CVR</span>
            <b>{selected.cvr}</b>
          </div>
          <div>
            <span>ACOS</span>
            <b>{selected.acos}</b>
          </div>
        </div>

        <Chart option={chartOption} className="campaign-drawer-chart" />

        <div className="campaign-table">
          <div className="campaign-row header">
            <span>日期</span>
            <span>广告费</span>
            <span>点击</span>
            <span>订单</span>
            <span>销售额</span>
            <span>ACOS</span>
          </div>
          {rows.map((row) => (
            <div className="campaign-row" key={row.date}>
              <span>{row.date}</span>
              <span>{money(row.spend)}</span>
              <span>{num(row.clicks)}</span>
              <span>{row.orders}</span>
              <span>{money(row.sales)}</span>
              <span>{row.acos.toFixed(1)}%</span>
            </div>
          ))}
        </div>

        <div className="campaign-note">
          这里先展示 {selected.name} 的每日花费、点击、订单、广告销售额和 ACOS；后续接真实 Campaign 后，可以展开到 Campaign / Ad Group / Keyword 三层。
        </div>
      </aside>
    </div>
  );
}

function KeywordDrawer({ keyword, labels, onClose }: { keyword: KeywordRow; labels: string[]; onClose: () => void }) {
  const option = lineOption(labels, [{ name: "点击", data: [18, 21, 16, 19, 24, 22, Math.max(12, Math.round(keyword.clicks / 7))], color: "#1677ff" }, { name: "花费", data: [8, 9, 7, 8, 10, 9, Math.max(6, Math.round(keyword.spend / 4))], color: "#13a8a8" }], "点击");
  return <div className="adv5-drawer-mask" role="presentation" onMouseDown={onClose}><aside className="adv5-drawer" role="dialog" aria-modal="true" onMouseDown={(event) => event.stopPropagation()}><div className="adv5-drawer-head"><div><small>{keyword.source === "manual" ? "手动关键词" : "自动搜索词"}</small><h3>{keyword.term}</h3></div><button type="button" onClick={onClose}>关闭</button></div><div className="drawer-kpi-grid">{[["曝光", num(keyword.impressions)], ["点击", num(keyword.clicks)], ["花费", money(keyword.spend)], ["订单", `${keyword.orders}`], ["CVR", `${keyword.cvr.toFixed(2)}%`], ["ROAS", keyword.roas.toFixed(2)]].map(([label, value]) => <div className="drawer-kpi" key={label}><span>{label}</span><b>{value}</b></div>)}</div><Chart option={option} className="keyword-drawer-chart" /><div className="drawer-note">当前竞价 {money(keyword.bid)}，自然排名 #{keyword.organicRank}，广告位 #{keyword.sponsoredRank}。</div></aside></div>;
}

function ProfitPanel({ period, data }: { period: ListingAnalysisPeriod; data: PeriodData }) {
  const [mode, setMode] = useState<"amount" | "rate">("amount");
  const option = { animationDuration: 240, color: ["#d8eaff", "#13a866", "#7b61ff"], grid: { left: 42, right: 44, top: 38, bottom: 32 }, tooltip: { trigger: "axis", backgroundColor: "#172033", borderWidth: 0, textStyle: { color: "#fff", fontSize: 7 } }, legend: { top: 8, right: 8, itemWidth: 14, itemHeight: 8, textStyle: { color: "#65748a", fontSize: 8 } }, xAxis: { type: "category", data: data.labels, axisTick: { show: false }, axisLine: { lineStyle: { color: "#e4edf7" } }, axisLabel: { color: "#7c8798", fontSize: 8 } }, yAxis: [{ type: "value", axisLabel: { color: "#8a95a6", fontSize: 8 }, splitLine: { lineStyle: { color: "#eef3f8" } } }, { type: "value", axisLabel: { color: "#8a95a6", fontSize: 8 }, splitLine: { show: false } }], series: mode === "amount" ? [{ name: "销售额", type: "bar", barWidth: 16, data: data.profit.revenue, itemStyle: { color: "#d8eaff", borderRadius: [4, 4, 0, 0] } }, { name: "利润", type: "line", yAxisIndex: 1, data: data.profit.profit, smooth: true, symbolSize: 6, lineStyle: { width: 2.4, color: "#13a866" }, itemStyle: { color: "#13a866" } }, { name: "广告费率", type: "line", yAxisIndex: 1, data: data.profit.adRate, smooth: true, symbolSize: 5, lineStyle: { width: 2, color: "#7b61ff" }, itemStyle: { color: "#7b61ff" } }] : [{ name: "利润率", type: "line", data: data.profit.margin, smooth: true, symbolSize: 6, lineStyle: { width: 2.4, color: "#13a866" }, itemStyle: { color: "#13a866" } }, { name: "广告费率", type: "line", data: data.profit.adRate, smooth: true, symbolSize: 6, lineStyle: { width: 2.4, color: "#7b61ff" }, itemStyle: { color: "#7b61ff" } }] } as EChartsOption;
  const costOption = { tooltip: { trigger: "item", backgroundColor: "#172033", borderWidth: 0, textStyle: { color: "#fff", fontSize: 7 } }, color: ["#69a8ff", "#7bd4c8", "#7b61ff", "#ff8a8a", "#ffc75f", "#5cc58a"], series: [{ type: "pie", radius: ["52%", "76%"], center: ["50%", "50%"], label: { show: false }, labelLine: { show: false }, itemStyle: { borderColor: "#fff", borderWidth: 2 }, data: data.profit.cost.map(([name, value]) => ({ name, value })) }] } as EChartsOption;
  return <div className="panel active" id="profit"><div className="small-kpis">{data.profit.kpis.map(([label, value, sub, tone]) => <div className="small-kpi" key={label}><div className="l">{label}</div><div className="v">{value}</div><small className={cls(tone)}>{sub}</small></div>)}</div><div className="profit-grid"><section className="surface profit-chart-card"><div className="section-head-line"><div><div className="section-title">利润与销售质量趋势</div><div className="section-sub">{period}天 · 金额 / 费率自由切换</div></div><div className="seg"><button type="button" className={mode === "amount" ? "active" : ""} onClick={() => setMode("amount")}>金额</button><button type="button" className={mode === "rate" ? "active" : ""} onClick={() => setMode("rate")}>费率</button></div></div><Chart option={option} className="profit-chart" /></section><aside className="surface cost-card"><div className="section-title">成本结构</div><div className="section-sub">{period}天 Listing 单品成本拆解</div><Chart option={costOption} className="cost-chart" /><div className="cost-list">{data.profit.cost.map(([name, , value]) => <div key={name}><span>{name}</span><b>{value}</b></div>)}</div></aside></div></div>;
}

function StockPanel({ period, data }: { period: ListingAnalysisPeriod; data: PeriodData }) {
  const [factor, setFactor] = useState<1 | 1.2 | 1.4>(1);
  const [includePlan, setIncludePlan] = useState(true);
  const [showLeadEditor, setShowLeadEditor] = useState(false);

  const dayOffsets = [0, 6, 12, 18, 24, 30, 36, 42, 48];
  const existingInboundDay = 8;
  const purchaseAvailableDay = 36;
  const safetyStock = data.stock.safety[0] ?? 170;
  const daily = Number((data.stock.baseDaily * factor).toFixed(1));

  const stockWithoutPlan = dayOffsets.map((day) => {
    const inbound = day >= existingInboundDay ? data.stock.inbound : 0;
    return Math.max(0, Math.round(data.stock.sellable + inbound - daily * day));
  });

  const availableBeforePurchase = Math.max(
    0,
    data.stock.sellable + data.stock.inbound - daily * purchaseAvailableDay,
  );
  const targetStock = Math.ceil(daily * data.stock.targetDays);
  const recommendedQty = Math.max(
    data.stock.decision.qty,
    Math.ceil((targetStock - availableBeforePurchase) / 10) * 10,
  );

  const stockWithPlan = dayOffsets.map((day) => {
    const inbound = day >= existingInboundDay ? data.stock.inbound : 0;
    const planned = includePlan && day >= purchaseAvailableDay ? recommendedQty : 0;
    return Math.max(0, Math.round(data.stock.sellable + inbound + planned - daily * day));
  });

  const coverage = Math.floor((data.stock.sellable + data.stock.inbound) / daily);
  const maxStock = Math.max(...stockWithoutPlan, ...stockWithPlan, safetyStock);
  const yMax = Math.ceil((maxStock * 1.15) / 100) * 100;

  const option = {
    animationDuration: 240,
    color: ["#1677ff", "#6ea8ff", "#f5a623"],
    grid: {
      left: 42,
      right: 28,
      top: 54,
      bottom: 42,
      containLabel: true,
    },
    tooltip: {
      trigger: "axis",
      axisPointer: { type: "line" },
      backgroundColor: "#172033",
      borderWidth: 0,
      padding: [8, 10],
      textStyle: {
        color: "#fff",
        fontSize: 12,
        lineHeight: 18,
      },
    },
    legend: {
      top: 8,
      right: 8,
      itemWidth: 14,
      itemHeight: 8,
      textStyle: {
        color: "#65748a",
        fontSize: 10,
      },
    },
    xAxis: {
      type: "category",
      data: data.stock.labels,
      axisTick: { show: false },
      axisLine: { lineStyle: { color: "#e4edf7" } },
      axisLabel: {
        color: "#7c8798",
        fontSize: 10,
        margin: 12,
      },
    },
    yAxis: {
      type: "value",
      min: 0,
      max: yMax,
      axisLabel: {
        color: "#8a95a6",
        fontSize: 10,
      },
      splitLine: {
        lineStyle: { color: "#eef3f8" },
      },
    },
    series: [
      {
        name: "现有库存",
        type: "line",
        smooth: true,
        symbolSize: 7,
        data: stockWithoutPlan,
        lineStyle: {
          width: 2.8,
          color: "#1677ff",
        },
        itemStyle: {
          color: "#1677ff",
        },
        areaStyle: {
          color: "rgba(22,119,255,.10)",
        },
        label: { show: false },
      },
      {
        name: "含建议采购",
        type: "line",
        smooth: false,
        symbolSize: 8,
        data: stockWithPlan,
        lineStyle: {
          width: 2.6,
          color: "#6ea8ff",
        },
        itemStyle: {
          color: "#6ea8ff",
        },
        label: {
          show: true,
          position: "top",
          distance: 10,
          color: "#1677ff",
          fontSize: 10,
          fontWeight: 850,
          formatter: (params: { value: number | string; dataIndex?: number }) => {
            const index = Number(params.dataIndex ?? 0);
            if (index === 2) return `已有在途 +${data.stock.inbound}`;
            if (includePlan && index === 6) return `建议采购 +${recommendedQty}`;
            return "";
          },
        },
      },
      {
        name: "14天安全库存",
        type: "line",
        symbolSize: 0,
        data: dayOffsets.map(() => safetyStock),
        lineStyle: {
          width: 2,
          type: "solid",
          color: "#f5a623",
        },
        itemStyle: {
          color: "#f5a623",
        },
        label: {
          show: false,
        },
      },
    ],
  } as EChartsOption;

  return (
    <div className="panel active" id="stock">
      <div className="small-kpis stock-kpis">
        {data.stock.kpis.map(([label, value, sub, tone]) => (
          <div className={`small-kpi ${tone === "warn" ? "warning" : tone === "up" ? "active" : ""}`} key={label}>
            <div className="l">{label}</div>
            <div className="v">
              {label === "建议采购量" ? `${recommendedQty}件` : value}
            </div>
            <small>
              {label === "预测日均" ? `近${period}日均 · ${daily}件/天` : sub}
            </small>
          </div>
        ))}
      </div>

      <div className="stock-grid">
        <section className="surface stock-main-box">
          <div className="section-head-line">
            <div>
              <div className="section-title">库存与补货时间线</div>
              <div className="section-sub">把库存消耗、已有在途、采购、国内仓、头程和 WFS 可售放在一条线上</div>
            </div>
            <div className="stock-actions">
              <div className="seg">
                {([[1, "基准"], [1.2, "销量 +20%"], [1.4, "销量 +40%"]] as Array<[1 | 1.2 | 1.4, string]>).map(([value, label]) => (
                  <button key={value} type="button" className={factor === value ? "active" : ""} onClick={() => setFactor(value)}>
                    {label}
                  </button>
                ))}
              </div>
              <button type="button" className={includePlan ? "primary-toggle active" : "primary-toggle"} onClick={() => setIncludePlan((value) => !value)}>
                {includePlan ? "已含建议采购" : "含建议采购"}
              </button>
            </div>
          </div>

          <Chart option={option} className="stock-chart" />

          <div className="supply-timeline">
            <span>09-17<br />今天</span>
            <span>09-25<br />已有在途到仓</span>
            <span>{data.stock.decision.window}<br />建议采购窗口</span>
            <span>10-10<br />预计国内仓到货</span>
            <span>10-24<br />预计 WFS 可售</span>
            <span>10-31<br />预计库存耗尽</span>
          </div>
        </section>

        <aside className="surface purchase-card">
          <div className="side-head">
            <div>
              <div className="section-title">采购决策</div>
              <div className="section-sub">按完整补货周期倒推，不只看采购到国内仓</div>
            </div>
            <span className="badge blue">建议采购</span>
          </div>

          <div className="purchase-decision">
            <div>
              <span>建议采购量</span>
              <b>{recommendedQty}<small>件</small></b>
              <p>目标库存约 {targetStock} 件 · 当前含在途覆盖 {coverage} 天</p>
            </div>
            <div>
              <span>建议采购窗口</span>
              <b>{data.stock.decision.window}</b>
              <p>最晚 {data.stock.decision.latest}</p>
            </div>
          </div>

          <div className="lead-config">
            <div className="section-title">补货周期参数</div>
            <button type="button" onClick={() => setShowLeadEditor((value) => !value)}>调整参数</button>
          </div>

          <div className="lead-pills">
            {["采购交期 12天", "国内处理 2天", "头程运输 9天", "WFS入仓 3天", "安全缓冲 7天"].map((item) => (
              <span className="lead-pill" key={item}>{item}</span>
            ))}
          </div>

          {showLeadEditor && (
            <div className="lead-editor">
              {["采购交期", "国内处理", "头程运输", "WFS入仓", "安全缓冲", "目标覆盖"].map((label, index) => (
                <div className="lead-input" key={label}>
                  <label>{label}</label>
                  <input type="number" defaultValue={[12, 2, 9, 3, 7, data.stock.targetDays][index]} />
                </div>
              ))}
            </div>
          )}

          <div className="purchase-note-v2">
            按当前销量系数计算：日均 {daily} 件，建议采购量 {recommendedQty} 件。切换“销量 +20% / +40%”后，库存消耗线、建议采购节点和采购量会同步重算。
          </div>
        </aside>
      </div>
    </div>
  );
}

function RiskPanel({ period, data }: { period: ListingAnalysisPeriod; data: PeriodData }) {
  const alerts = data.risk.items.filter((item) => item.state !== "normal");
  const [selectedRisk, setSelectedRisk] = useState(alerts[0]?.key || data.risk.items[0].key);
  const selected = data.risk.items.find((item) => item.key === selectedRisk) || data.risk.items[0];
  const scoreOption = { tooltip: { show: false }, color: ["#1677ff", "#eaf3ff"], graphic: [{ type: "text", left: "center", top: "center", style: { text: `${data.risk.score}`, fontSize: 18, fontWeight: 900, fill: "#172033" } }], series: [{ type: "pie", radius: ["68%", "82%"], center: ["50%", "50%"], label: { show: false }, labelLine: { show: false }, data: [{ value: data.risk.score, itemStyle: { color: "#1677ff" } }, { value: 100 - data.risk.score, itemStyle: { color: "#eaf3ff" } }] }] } as EChartsOption;
  return <div className="panel active" id="risk"><div className="riskA-wrap"><section className="surface riskA-summary"><Chart option={scoreOption} className="risk-score-chart" /><div><div className="section-title">Listing 风险</div><div className="section-sub">{period}天 · 异常优先，先处理问题，再查看全部监控</div></div>{data.risk.summary.map(([value, label, tone]) => <div className="risk-stat" key={label}><b className={cls(tone)}>{value}</b><span>{label}</span></div>)}</section><div className="riskA-title">当前需关注 <span>{alerts.length} 项</span></div><div className="riskA-alerts">{alerts.map((item) => <button type="button" key={item.key} className="riskA-alert" onClick={() => setSelectedRisk(item.key)}><div><b>{item.name}</b><strong>{item.value}</strong><small>{item.sub}</small></div><span>关注</span></button>)}</div><div className="riskA-lower"><section className="surface riskA-list"><div className="section-head-line"><div className="section-title">全部风险监控</div><span>点击查看详情</span></div><div className="risk-table">{data.risk.items.map((risk) => <button key={risk.key} type="button" className={`risk-item riskA-row ${risk.state} ${selectedRisk === risk.key ? "active" : ""}`} onClick={() => setSelectedRisk(risk.key)}><span className="riskA-state">{risk.state === "normal" ? "✓" : "!"}</span><span className="riskA-name">{risk.name}</span><b>{risk.value}</b><small>{risk.sub}</small><span className={`badge ${risk.state === "normal" ? "green" : "orange"}`}>{risk.state === "normal" ? "正常" : "关注"}</span></button>)}</div></section><aside className="surface risk-detail"><div className="side-head"><div><div className="section-title">{selected.name}</div></div><span className={`badge ${selected.state === "normal" ? "green" : "orange"}`}>{selected.state === "normal" ? "正常" : "关注"}</span></div><div className="risk-detail-text">{selected.detail}</div><div className="risk-detail-tip">{selected.tip}</div></aside></div></div></div>;
}

function TimelinePanel({ period, data }: { period: ListingAnalysisPeriod; data: PeriodData }) {
  void period;

  const [type, setType] = useState<EventType>("all");
  const [source, setSource] = useState<EventSource>("all");
  const [eventRange, setEventRange] = useState<7 | 30 | 90>(7);
  const [selectedId, setSelectedId] = useState(data.timeline.events[0]?.id ?? "");

  const typeTabs: Array<[EventType, string]> = [
    ["all", "全部"],
    ["price", "售价"],
    ["ad", "广告"],
    ["review", "Review"],
    ["buybox", "Buy Box"],
    ["hijack", "跟卖"],
    ["listing", "Listing"],
    ["promo", "促销"],
  ];

  const sourceTabs: Array<[EventSource, string]> = [
    ["all", "全部来源"],
    ["manual", "人工操作"],
    ["auto", "自动事件"],
  ];

  const filtered = data.timeline.events.filter((event) => (
    (type === "all" || event.type === type) &&
    (source === "all" || event.source === source)
  ));

  const selected =
    data.timeline.events.find((event) => event.id === selectedId) ??
    filtered[0] ??
    data.timeline.events[0];

  const chartLabels =
    eventRange === 7
      ? ["09-11", "09-12", "09-13", "09-14", "09-15", "09-16", "09-17"]
      : data.labels;

  const chartSales =
    eventRange === 7
      ? [17, 18, 18, 6, 10, 6, 14]
      : data.timeline.sales;

  if (!selected) {
    return (
      <div className="panel active timeline-target-v2" id="timeline">
        <div className="timeline-empty">暂无经营事件</div>
      </div>
    );
  }

  const eventColor = (eventType: Exclude<EventType, "all">) => {
    const colors: Record<Exclude<EventType, "all">, string> = {
      price: "#e5484d",
      ad: "#1677ff",
      review: "#f04438",
      buybox: "#7b61ff",
      hijack: "#f5a623",
      listing: "#13a8a8",
      promo: "#12b76a",
    };
    return colors[eventType];
  };

  const eventTypeName = (eventType: Exclude<EventType, "all">) => {
    const names: Record<Exclude<EventType, "all">, string> = {
      price: "售价",
      ad: "广告",
      review: "Review",
      buybox: "Buy Box",
      hijack: "跟卖",
      listing: "Listing",
      promo: "促销",
    };
    return names[eventType];
  };

  const eventChartLabel = (event: EventRow) => {
    if (event.type === "price") return "$";
    if (event.type === "ad") return "AD";
    if (event.type === "review") return "评";
    if (event.type === "buybox") return "BB";
    if (event.type === "hijack") return "跟";
    if (event.type === "listing") return "L";
    return "促";
  };

  const extractEventId = (params: unknown) => {
    if (typeof params !== "object" || params === null || !("data" in params)) return null;
    const rawData = (params as { data?: unknown }).data;
    if (typeof rawData !== "object" || rawData === null || !("eventId" in rawData)) return null;
    const eventId = (rawData as { eventId?: unknown }).eventId;
    return typeof eventId === "string" ? eventId : null;
  };

  const dateOccurrence = new Map<string, number>();

  const markerData = filtered.map((event, fallbackIndex) => {
    const shortDate = event.date.slice(5);
    const matchedIndex = chartLabels.findIndex((label) => label === shortDate);
    const index = matchedIndex >= 0 ? matchedIndex : Math.min(fallbackIndex, chartLabels.length - 1);
    const occurrence = dateOccurrence.get(shortDate) ?? 0;
    dateOccurrence.set(shortDate, occurrence + 1);

    return {
      value: [
        index,
        Math.min(20.6, (chartSales[index] ?? chartSales[chartSales.length - 1] ?? 8) + 2.1 + occurrence * 1.1),
      ],
      eventId: event.id,
      name: eventChartLabel(event),
      itemStyle: {
        color: eventColor(event.type),
        borderColor: "#ffffff",
        borderWidth: 1,
      },
    };
  });

  const option = {
    animationDuration: 240,
    grid: {
      left: 34,
      right: 18,
      top: 38,
      bottom: 26,
      containLabel: true,
    },
    tooltip: {
      trigger: "item",
      renderMode: "html",
      appendToBody: true,
      confine: false,
      backgroundColor: "#172033",
      borderWidth: 0,
      padding: [8, 10],
      extraCssText: "z-index:99999;box-shadow:0 8px 24px rgba(15,23,42,.22);border-radius:8px;pointer-events:none;",
      textStyle: {
        color: "#fff",
        fontSize: 12,
        lineHeight: 18,
      },
      formatter: (params: unknown) => {
        const eventId = extractEventId(params);
        if (!eventId) return "";
        const event = data.timeline.events.find((item) => item.id === eventId);
        if (!event) return "";
        return `
          <div style="font-weight:800;margin-bottom:4px;">${event.title}</div>
          <div>${event.date} ${event.time}</div>
          <div>${event.change}</div>
        `;
      },
    },
    xAxis: {
      type: "category",
      data: chartLabels,
      axisTick: { show: false },
      axisLine: { lineStyle: { color: "#e4edf7" } },
      axisLabel: {
        color: "#7c8798",
        fontSize: 10,
        margin: 8,
        interval: chartLabels.length > 14 ? 1 : 0,
      },
    },
    yAxis: {
      type: "value",
      min: 0,
      max: 21,
      interval: 3,
      splitLine: { lineStyle: { color: "#eef3f8" } },
      axisLabel: {
        color: "#8a95a6",
        fontSize: 10,
      },
    },
    series: [
      {
        name: "销量",
        type: "line",
        smooth: true,
        symbolSize: 5,
        data: chartSales,
        lineStyle: {
          width: 2.8,
          color: "#1677ff",
        },
        itemStyle: {
          color: "#1677ff",
        },
        areaStyle: {
          color: "rgba(22,119,255,.10)",
        },
        label: { show: false },
      },
      {
        name: "事件",
        type: "scatter",
        symbol: "pin",
        symbolSize: 34,
        z: 10,
        data: markerData,
        label: {
          show: true,
          position: "inside",
          color: "#fff",
          fontSize: 9,
          fontWeight: 900,
          formatter: (params: { name?: string }) => params.name ?? "",
        },
      },
    ],
  } as EChartsOption;

  const openEventDetail = (eventId: string) => {
    setSelectedId(eventId);
  };

  const onChartClick = (params: unknown) => {
    const eventId = extractEventId(params);
    if (eventId) openEventDetail(eventId);
  };

  return (
    <div className="panel active timeline-target-v2" id="timeline">
      <div className="le-toolbar">
        <div className="le-category-row">
          {typeTabs.map(([key, label]) => (
            <button
              key={key}
              type="button"
              className={`le-filter-btn ${type === key ? "active" : ""}`}
              onClick={() => setType(key)}
            >
              {label}
              <span className="le-count">
                {key === "all" ? data.timeline.events.length : data.timeline.events.filter((event) => event.type === key).length}
              </span>
            </button>
          ))}
        </div>

        <div className="le-toolbar-right">
          {sourceTabs.map(([key, label]) => (
            <button
              key={key}
              type="button"
              className={`le-filter-btn ${source === key ? "active" : ""}`}
              onClick={() => setSource(key)}
            >
              {label}
            </button>
          ))}

          {([7, 30, 90] as Array<7 | 30 | 90>).map((value) => (
            <button
              key={value}
              type="button"
              className={`le-filter-btn event-range ${eventRange === value ? "active" : ""}`}
              onClick={() => setEventRange(value)}
            >
              {value}天
            </button>
          ))}
        </div>
      </div>

      <div className="timeline-target-grid">
        <div className="timeline-target-left">
          <section className="surface timeline-target-chart-card">
            <div className="timeline-target-chart-head">
              <div>
                <div className="section-title">Listing 事件轨迹</div>
                <div className="section-sub">销量趋势只用于定位事件，点击事件点可直接查看记录</div>
              </div>
              <span className="badge blue">{filtered.length} 条事件</span>
            </div>

            <Chart option={option} className="timeline-target-chart" onEvents={{ click: onChartClick }} />
          </section>

          <section className="surface timeline-target-list-card">
            <div className="timeline-target-list">
              {filtered.map((event, index) => (
                <div className="timeline-target-group" key={event.id}>
                  {(index === 0 || filtered[index - 1]?.date !== event.date) && (
                    <div className="timeline-target-date">{event.date}</div>
                  )}

                  <button
                    type="button"
                    className={`timeline-target-row ${selected.id === event.id ? "active" : ""}`}
                    onClick={() => openEventDetail(event.id)}
                  >
                    <span className="timeline-target-time">{event.time}</span>
                    <span
                      className="timeline-target-icon"
                      style={{
                        backgroundColor: `${eventColor(event.type)}14`,
                        color: eventColor(event.type),
                      }}
                    >
                      {eventChartLabel(event)}
                    </span>
                    <span className="timeline-target-main">
                      <b>{event.title}</b>
                      <small>{event.change}</small>
                    </span>
                    <span className="timeline-target-source">
                      <b>{event.sourceName}</b>
                      <small>{event.operator}</small>
                    </span>
                  </button>
                </div>
              ))}
            </div>
          </section>
        </div>

        <aside className="surface timeline-target-detail">
          <div className="timeline-target-detail-head">
            <div>
              <div className="timeline-target-detail-date">{selected.date} {selected.time}</div>
              <div className="timeline-target-detail-title">{selected.title}</div>
            </div>
            <span className="timeline-target-tag">{selected.source === "manual" ? "人工操作" : "自动事件"}</span>
          </div>

          <div className="timeline-target-change">
            <span>售价变化</span>
            <b>{selected.change.split("·")[0]}</b>
            <small>{selected.change.split("·").slice(1).join("·")}</small>
          </div>

          <div className="timeline-target-meta">
            <div>
              <span>事件类型</span>
              <b>{eventTypeName(selected.type)}</b>
            </div>
            <div>
              <span>来源</span>
              <b>{selected.sourceName}</b>
            </div>
            <div>
              <span>操作人 / 触发方</span>
              <b>{selected.operator}</b>
            </div>
            <div>
              <span>Listing</span>
              <b>AX1042</b>
            </div>
          </div>

          <div className="timeline-target-note">
            <b>备注</b>
            <p>{selected.note}</p>
          </div>

          <div className="timeline-target-observe">
            <div className="timeline-target-observe-head">
              <b>后续观察</b>
              <button type="button">展开</button>
            </div>
            <div className="timeline-target-observe-box">
              <span>调整前销量 <strong>{selected.beforeSales}</strong></span>
              <span>调整后销量 <strong>{selected.afterSales}</strong></span>
              <span>变化 <strong>{selected.delta}</strong></span>
            </div>
          </div>
        </aside>
      </div>
    </div>
  );
}

export default ListingAnalysisModal;
