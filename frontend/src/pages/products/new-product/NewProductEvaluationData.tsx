import { useState } from "react";
import type { Product } from "./nativeData";
import "./newProductEvaluationData.css";

// PR337_EVALUATION_DATA_V1 — rendering only. Uses the already-loaded /listings facts.
// No mock values, new requests, source scans or score recalculation.
type View = "operations" | "ads";
type AdKind = "total" | "auto" | "manual";
type OptionalNumber = number | null;
type FactRecord = Record<string, unknown>;
type AdMetrics = {
  spend: OptionalNumber;
  orders: OptionalNumber;
  share: OptionalNumber;
  cpc: OptionalNumber;
  cpa: OptionalNumber;
  cvr: OptionalNumber;
  impressions: OptionalNumber;
  clicks: OptionalNumber;
  ctr: OptionalNumber;
};

function finite(value: unknown): OptionalNumber {
  if (value === null || value === undefined || value === "" || typeof value === "boolean") return null;
  if (typeof value !== "number" && typeof value !== "string") return null;
  const number = typeof value === "string" ? Number(value.replace(/,/g, "")) : value;
  return Number.isFinite(number) ? number : null;
}

function read(f: FactRecord, ...keys: string[]): OptionalNumber {
  for (const key of keys) {
    const n = finite(f[key]);
    if (n !== null) return n;
  }
  return null;
}

function divide(numerator: OptionalNumber, denominator: OptionalNumber, multiplier = 1): OptionalNumber {
  return numerator !== null && denominator !== null && denominator > 0
    ? numerator / denominator * multiplier : null;
}

function dollars(value: OptionalNumber): string {
  return value === null ? "—" : `$${value.toLocaleString("en-US", {minimumFractionDigits:2,maximumFractionDigits:2})}`;
}
function decimal(value: OptionalNumber, places = 2): string {
  return value === null ? "—" : value.toLocaleString("en-US", {minimumFractionDigits:places,maximumFractionDigits:places});
}
function integer(value: OptionalNumber, unit = ""): string {
  return value === null ? "—" : `${Math.round(value).toLocaleString("en-US")}${unit}`;
}
function percent(value: OptionalNumber): string {
  return value === null ? "—" : `${decimal(value)}%`;
}
function dateValue(value: unknown): string {
  return typeof value === "string" && /^\d{4}-\d{2}-\d{2}/.test(value) ? value.slice(0,10) : "—";
}

// All split-ad fields are optional: the existing listing API does not currently
// guarantee auto/manual breakdown. Never clone the total as either component.
function adFacts(f: FactRecord, kind: AdKind): AdMetrics {
  const prefix = kind === "auto" ? "auto" : "manual";
  const total = kind === "total";
  const spend = total
    ? read(f, "ad_total_spend_usd", "ad_spend_usd")
    : read(f, `${prefix}_ad_spend_usd`, `ad_${prefix}_spend_usd`);
  const orders = total
    ? read(f, "ad_total_orders", "ad_orders", "ad_attributed_orders")
    : read(f, `${prefix}_ad_orders`, `ad_${prefix}_orders`);
  const clicks = total
    ? read(f, "ad_total_clicks", "ad_clicks")
    : read(f, `${prefix}_ad_clicks`, `ad_${prefix}_clicks`);
  const impressions = total
    ? read(f, "ad_total_impressions", "ad_impressions")
    : read(f, `${prefix}_ad_impressions`, `ad_${prefix}_impressions`);
  const share = total
    ? read(f, "ad_total_spend_ratio_pct", "ad_spend_ratio_pct", "ad_spend_share_pct")
    : read(f, `${prefix}_ad_spend_ratio_pct`, `ad_${prefix}_spend_share_pct`);
  const savedTotal = total && finite(f.ad_total_spend_usd) !== null;
  return {
    spend, orders, clicks, impressions, share,
    cpc: total ? (savedTotal ? divide(spend, clicks) : read(f, "ad_cpc_usd") ?? divide(spend, clicks))
      : read(f, `${prefix}_ad_cpc_usd`) ?? divide(spend, clicks),
    cpa: total ? (savedTotal ? divide(spend, orders) : read(f, "ad_cpa_usd") ?? divide(spend, orders))
      : read(f, `${prefix}_ad_cpa_usd`) ?? divide(spend, orders),
    cvr: total ? (savedTotal ? divide(orders, clicks, 100) : read(f, "ad_cvr_pct") ?? divide(orders, clicks, 100))
      : read(f, `${prefix}_ad_cvr_pct`) ?? divide(orders, clicks, 100),
    ctr: total ? (savedTotal ? divide(clicks, impressions, 100) : read(f, "ad_ctr_pct") ?? divide(clicks, impressions, 100))
      : read(f, `${prefix}_ad_ctr_pct`) ?? divide(clicks, impressions, 100),
  };
}

function Metric({label,value}: {label:string;value:string}) {
  return <div className="np-ed-metric"><span className="np-ed-label">{label}</span><strong title={value}>{value}</strong></div>;
}
function Heading({title,count}: {title:string;count:string}) {
  return <div className="np-ed-section-heading"><span className="np-ed-accent"/>
    <b>{title}</b><small>{count}</small></div>;
}

export default function NewProductEvaluationData({product}: {product: Product}) {
  const [view,setView] = useState<View>("operations");
  const [adKind,setAdKind] = useState<AdKind>("total");
  const [compare,setCompare] = useState(false);
  const backend = product.backend as (NonNullable<Product["backend"]> & {scoringFacts?: FactRecord}) | undefined;
  const facts = backend?.scoringFacts ?? {};
  const qty14 = read(facts,"valid_units_14d");
  const orders14 = read(facts,"valid_orders_14d");
  const revenue = read(facts,"sales_amount_usd");
  const profit = read(facts,"profit_usd");
  const margin = read(facts,"gross_margin_pct");
  const roi = read(facts,"roi");
  const firstOrder = dateValue(facts.first_order_date ?? backend?.firstOrderDate);
  // Count only days observed, with a maximum 14-day scoring window.
  const days = read(facts, "elapsed_days");
  const daily = divide(orders14, days === null ? null : Math.min(14, Math.max(1, days)));
  const averagePrice = divide(revenue, qty14);
  const totalAds = adFacts(facts,"total");
  const autoAds = adFacts(facts,"auto");
  const manualAds = adFacts(facts,"manual");
  const adsByKind: Record<AdKind,AdMetrics> = {total:totalAds,auto:autoAds,manual:manualAds};
  const active = adsByKind[adKind];
  const comparisons: Array<[string,(m:AdMetrics)=>string]> = [
    ["广告花费",m=>dollars(m.spend)],
    ["广告占比",m=>percent(m.share)],
    ["广告订单数",m=>integer(m.orders,"单")],
    ["CPC",m=>dollars(m.cpc)],
    ["CPA",m=>dollars(m.cpa)],
    ["CVR",m=>percent(m.cvr)],
    ["曝光",m=>integer(m.impressions)],
    ["总点击",m=>integer(m.clicks)],
    ["CTR",m=>percent(m.ctr)],
  ];
  return <section className="np-ed" aria-label="测评数据">
    <header className="np-ed-header">
      <div className="np-ed-title"><span className="np-ed-symbol" aria-hidden="true">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><path d="M4 19V11M10 19V5M16 19v-9M3 20h17"/></svg>
      </span><b>测评数据</b></div>
      <div className="np-ed-mode" role="group" aria-label="测评数据分类">
        <button type="button" className={view==="operations"?"active":""} aria-pressed={view==="operations"} onClick={()=>setView("operations")}>经营数据</button>
        <button type="button" className={view==="ads"?"active":""} aria-pressed={view==="ads"} onClick={()=>setView("ads")}>广告数据</button>
      </div>
    </header>
    {view==="operations" ? <div className="np-ed-main np-ed-operation">
      <div className="np-ed-context"><span className="np-ed-dot"/> <b>经营表现总览</b><small>近14天</small><span className="np-ed-count">9 项指标</span></div>
      <div className="np-ed-highlight np-ed-three">
        <Metric label="销售额" value={dollars(revenue)}/>
        <Metric label="订单利润" value={dollars(profit)}/>
        <Metric label="利润率" value={percent(margin)}/>
      </div>
      <Heading title="经营明细" count="6 项指标"/>
      <div className="np-ed-details np-ed-three np-ed-six">
        <Metric label="近14天销量 / 订单量" value={`${integer(qty14,"件")} / ${integer(orders14,"单")}`}/>
        <Metric label="平均售价" value={dollars(averagePrice)}/>
        <Metric label="日均单量" value={daily===null?"—":`${decimal(daily,1)} 单`}/>
        <Metric label="ROI" value={decimal(roi)}/>
        <Metric label="上架时间" value={dateValue(facts.first_wfs_available_date_la ?? backend?.firstWfsDate)}/>
        <Metric label="首单日期" value={firstOrder}/>
      </div>
    </div> : <div className="np-ed-main np-ed-advertising">
      <div className="np-ed-ad-toolbar">
        <div className="np-ed-ad-tabs" role="group" aria-label="广告类型">
          {([['total','广告总计'],['auto','自动广告'],['manual','手动广告']] as const).map(([key,label])=><button
            type="button" key={key} aria-pressed={adKind===key}
            className={!compare && adKind===key?'active':''} onClick={()=>{setAdKind(key);setCompare(false);}}>{label}</button>)}
        </div>
        <button type="button" className={'np-ed-compare-button'+(compare?' on':'')}
          aria-pressed={compare} onClick={()=>setCompare(v=>!v)}>
          <span aria-hidden="true">▥</span> {compare?'收起对比':'三类对比'}
        </button>
      </div>
      {compare ? <div className="np-ed-comparison">
        <div className="np-ed-compare-caption"><Heading title="三类广告对比" count="CTR 位于最后"/></div>
        <div className="np-ed-tablehead np-ed-four-col"><span>指标</span><b>总计</b><b>自动</b><b>手动</b></div>
        <div className="np-ed-tablebody" tabIndex={0} aria-label="三类广告对比明细（可滚动）">
          {comparisons.map(([label,format])=><div className="np-ed-tableline np-ed-four-col" key={label}>
            <span>{label}</span><strong>{format(totalAds)}</strong><span>{format(autoAds)}</span><span>{format(manualAds)}</span>
          </div>)}
        </div>
      </div> : <div className="np-ed-ad-content">
        <div className="np-ed-highlight np-ed-three">
          <Metric label="广告花费" value={dollars(active.spend)}/>
          <Metric label="广告订单数" value={integer(active.orders,"单")}/>
          <Metric label="广告占比" value={percent(active.share)}/>
        </div>
        <Heading title="广告效率明细" count="6 项指标"/>
        <div className="np-ed-details np-ed-three np-ed-six">
          <Metric label="CPC" value={dollars(active.cpc)}/>
          <Metric label="CPA" value={dollars(active.cpa)}/>
          <Metric label="CVR" value={percent(active.cvr)}/>
          <Metric label="曝光" value={integer(active.impressions)}/>
          <Metric label="总点击" value={integer(active.clicks)}/>
          <Metric label="CTR" value={percent(active.ctr)}/>
        </div>
      </div>}
    </div>}
  </section>;
}
