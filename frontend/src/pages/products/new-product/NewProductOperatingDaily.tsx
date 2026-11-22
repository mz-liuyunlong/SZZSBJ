/** Daily operating data: SAME independent refund/sample-aware testing-profit engine.
 * Read-only single Item ID detail GET. This panel never calculates a profit formula.
 */
import {useEffect, useState} from "react";
import type {Product} from "./nativeData";
import {getCachedNewProductDetail} from "./newProductBusinessApi";
import "./newProductOperatingDaily.css";

type RecordValue = Record<string,unknown>;
type N = number | null;
type DayRow = {
  date: string; units: N; orders: N; sales: N; ad: N;
  profit: N; investment: N; margin: N; roi: N; adShare: N; averagePrice: N;
};
type State = {
  state: "loading" | "ready" | "error";
  rows: DayRow[];
  totals?: RecordValue;
  cutoff?: string;
  completeDays?: boolean;
  scoreComparison?: string;
  frozenOverview?: RecordValue | null;
  error?: string;
};

function num(value: unknown): N {
  if (typeof value !== "string" && typeof value !== "number") return null;
  if (typeof value === "string" && !value.trim()) return null;
  const n = Number(value);
  return Number.isFinite(n) ? n : null;
}
function day(value: unknown): string | null {
  return typeof value === "string" && /^\d{4}-\d{2}-\d{2}$/.test(value) ? value : null;
}
function qty(value: N): string {
  return value === null ? "—" : value.toLocaleString("en-US", {maximumFractionDigits:2});
}
function usd(value: N): string {
  return value === null ? "—" : `${value < 0 ? "-" : ""}$${Math.abs(value).toLocaleString("en-US", {minimumFractionDigits:2,maximumFractionDigits:2})}`;
}
function pct(value: N): string {return value === null ? "—" : `${value.toFixed(2)}%`;}
function decimal(value: N): string {return value === null ? "—" : value.toFixed(2);}
function red(value: N): string {return value !== null && value < 0 ? "np-od-neg" : "";}
function asRecord(v: unknown): RecordValue | null {
  return v !== null && typeof v === "object" && !Array.isArray(v)
    ? v as RecordValue : null;
}
// WFS start is already present in the loaded listing; no detail request for age.
function listedDays(first: string | null): N {
  if (!first) return null;
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone: "America/Los_Angeles", year: "numeric", month: "2-digit", day: "2-digit",
  }).formatToParts(new Date());
  const part = (kind: "year" | "month" | "day") =>
    parts.find(p => p.type === kind)?.value ?? "";
  const today = `${part("year")}-${part("month")}-${part("day")}`;
  const days = (Date.parse(`${today}T00:00:00Z`) - Date.parse(`${first}T00:00:00Z`)) / 86400000 + 1;
  return Number.isInteger(days) && days > 0 ? days : null;
}

// NP_VERIFIED_LISTING_END_V2
function publishedGradeDay(value: unknown): string | null {
  if (typeof value !== "string" ||
      !/T.*(?:Z|[+-]\d{2}:\d{2})$/i.test(value)) return null;

  const at = new Date(value);
  if (!Number.isFinite(at.getTime())) return null;

  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone: "America/Los_Angeles",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).formatToParts(at);

  const part = (kind: "year" | "month" | "day") =>
    parts.find(p => p.type === kind)?.value ?? "";

  return day(`${part("year")}-${part("month")}-${part("day")}`);
}

function verifiedListingDays(
  first: string | null,
  facts: RecordValue | undefined,
  grade: unknown,
  tracking: string,
): N {
  if (!first) return null;

  const sold = facts?.sold_out_evidence_status === "verified"
    ? day(facts.first_batch_sold_out_date_la)
    : null;

  const graded = grade != null && grade !== ""
    ? publishedGradeDay(facts?.evaluation_grade_published_at)
    : null;

  const ends = [sold, graded]
    .filter((value): value is string =>
      value !== null && value >= first)
    .sort();

  if (ends.length > 0) {
    const count = (
      Date.parse(`${ends[0]}T00:00:00Z`) -
      Date.parse(`${first}T00:00:00Z`)
    ) / 86400000 + 1;

    return Number.isInteger(count) && count > 0
      ? count : null;
  }

  const closed = grade != null && grade !== "" ||
    tracking === "打品成功" ||
    tracking === "打品失败";

  return closed ? null : listedDays(first);
}

function parseRows(v: unknown): DayRow[] | null {
  if (!Array.isArray(v)) return null;
  const parsed: DayRow[] = [];
  for (const item of v) {
    const row = asRecord(item);
    const date = day(row?.date);
    if (!row || !date || typeof row.has_mart_evidence !== "boolean") return null;
    const hasMart = row.has_mart_evidence;
    const actualAd = num(row.ad_spend_usd);
    const actualProfit = num(row.profit_usd);
    parsed.push({
      date, units:num(row.sales_units), orders:num(row.sales_orders),
      sales:num(row.sales_amount_usd),
      ad:hasMart || (actualAd !== null && actualAd > 0) ? actualAd : null,
      profit:hasMart || (actualProfit !== null && actualProfit < 0) ? actualProfit : null,
      investment:num(row.invested_usd),
      margin:num(row.margin_pct), roi:num(row.roi), adShare:num(row.ad_share_pct),
      averagePrice:num(row.average_price_usd),
    });
  }
  if (new Set(parsed.map(r => r.date)).size !== parsed.length) return null;
  return parsed.sort((a,b) => b.date.localeCompare(a.date));
}
// PURCHASE_DETAIL_SYNCHRONIZED_V1: warm, already-authorized operating detail.
// The original new-product page provides no preload and keeps its existing behavior.
function warmOperatingState(raw: unknown): State {
  const detail = asRecord(raw);
  const rows = parseRows(detail?.rows);
  const totals = asRecord(detail?.totals);
  if (!detail || detail.status !== "scored" || !rows || !totals ||
      detail.source !== "new_products_testing_profit_full_history_v2" ||
      detail.policy !== "returns_ignored_samples_excluded_sample_ads_included") {
    return {state:"error",rows:[],error:"申请关联的每日测评证据未核实"};
  }
  return {
    state:"ready", rows, totals,
    cutoff:day(detail.cutoff_la) ?? undefined,
    completeDays:detail.complete_calendar_days === true,
    scoreComparison:typeof detail.score_comparison === "string" ? detail.score_comparison : undefined,
  };
}
function NewProductOperatingDailyView({product,initialOperatingDaily}:{product:Product;initialOperatingDaily?:unknown}) {
  const backend = product.backend;
  const identity = backend?.identity;
  const account = identity?.source_account_ref;
  const store = identity?.store_id;
  const item = identity?.item_id;
  const first = day(backend?.firstWfsDate);
  const firstPaid = day(backend?.firstOrderDate);
  const listFacts = (backend as (NonNullable<Product["backend"]> &
    {scoringFacts?: RecordValue}) | undefined)?.scoringFacts;
  const paidDaysRaw = num(listFacts?.order_days_count);
  const paidDays = paidDaysRaw !== null && Number.isInteger(paidDaysRaw) &&
    paidDaysRaw >= 0 ? paidDaysRaw : null;
  const [rawLoaded,setLoaded] = useState<State>(() => initialOperatingDaily === undefined ? {state:"loading",rows:[]} : warmOperatingState(initialOperatingDaily));
  const loaded: State = !account || !store || !item
    ? {state:"error",rows:[],error:"商品身份未核实"} : rawLoaded;
  const ageDays = verifiedListingDays(
    first,
    listFacts,
    backend?.evaluation?.grade,
    product.tracking
  );

  useEffect(() => {
    if (initialOperatingDaily !== undefined) return;
    if (!account || !store || !item) return;
    let live = true;
    getCachedNewProductDetail({source_account_ref:account,store_id:store,item_id:item}).then(data => {
      if (!live) return;
      const detail = asRecord(data.evaluation_operating_daily);
      if (!detail) {
        setLoaded({state:"error",rows:[],error:"详情接口未返回同源每日测评利润，请先更新本地后端"});return;
      }
      const rows = parseRows(detail.rows);
      const totals = asRecord(detail.totals);
      if (detail.status !== "scored" || !rows || !totals) {
        const missing = Array.isArray(detail.missing)
          ? detail.missing.filter((v):v is string => typeof v === "string").slice(0,3).join("、") : "";
        setLoaded({state:"error",rows:[],error:`同源利润未核实：${String(detail.reason ?? missing ?? "未知原因")}`});return;
      }
      if (detail.source !== "new_products_testing_profit_full_history_v2"
        || detail.policy !== "returns_ignored_samples_excluded_sample_ads_included") {
        setLoaded({state:"error",rows:[],error:"利润来源或退款送样口径不匹配"});return;
      }
      setLoaded({
        state:"ready",rows,totals,
        cutoff:day(detail.cutoff_la) ?? undefined,
        completeDays:detail.complete_calendar_days === true,
        scoreComparison:typeof detail.score_comparison === "string" ? detail.score_comparison : undefined,
        frozenOverview:asRecord(detail.frozen_overview),
      });
    }).catch(err => {
      if (live) setLoaded({state:"error",rows:[],error:err instanceof Error?err.message:"真实经营数据读取失败"});
    });
    return () => {live = false;};
  },[account,store,item,initialOperatingDaily]);

  const rows = loaded.rows;
  // Show only dates with verified sales evidence or actual non-zero costs.
  // Do not fabricate zero-order days from ad-only zero snapshots.
  const visibleRows = rows.filter(r =>
    r.units !== null || r.orders !== null || r.sales !== null ||
    r.ad !== null || r.profit !== null
  );
  const totals = loaded.totals;
  const firstOrder = loaded.frozenOverview
    ? day(loaded.frozenOverview.first_order) : firstPaid;
  const shownFirst = loaded.frozenOverview
    ? day(loaded.frozenOverview.first_wfs) : first;
  const shownPaidDays = loaded.frozenOverview
    ? num(loaded.frozenOverview.paid_days) : paidDays;
  const n = (key:string): N => num(totals?.[key]);
  const totalUnits=n("sales_units"), totalSales=n("sales_amount_usd"), totalAds=n("ad_spend_usd");
  const totalProfit=n("profit_usd"), totalInvest=n("invested_usd");
  const totalAverage = totalUnits !== null && totalUnits>0 && totalSales !== null
    ? totalSales/totalUnits : null;
  const totalAdShare = totalSales !== null && totalSales>0 && totalAds !== null
    ? totalAds/totalSales*100 : null;
  return <div className="np-ed-main np-od-root">
    <div className="np-ed-context"><span className="np-ed-dot"/><b>经营数据总览</b></div>
    <div className="np-ed-highlight np-od-overview">
      <div><span>上架日期</span><strong>{shownFirst ?? "—"}</strong></div>
      <div><span>首单日期</span><strong>{firstOrder ?? "—"}</strong></div>
      <div><span>出单天数</span><strong>{shownPaidDays === null ? "—" : `${qty(shownPaidDays)} 天`}</strong></div>
      <div><span>上架天数</span><strong>{ageDays === null ? "—" : `${qty(ageDays)} 天`}</strong></div>
    </div>
    <div className="np-ed-section-heading np-od-heading"><span className="np-ed-accent"/><b>每日经营明细</b><small>九列同屏 · 上下滚动</small></div>
    <div className="np-od-table" aria-label="每日经营明细">
      <div className="np-od-grid np-od-head" aria-hidden="true">
        {['日期','销量','订单量','平均售价','广告费','广告占比','利润','利润率','ROI'].map(x=><span key={x}>{x}</span>)}
      </div>
      <div className="np-od-body" tabIndex={0} aria-label="可上下滚动的每日经营数据">
        {loaded.state === "loading" ? <div className="np-od-empty">正在读取同源测评经营数据…</div> :
         loaded.state === "error" ? <div className="np-od-empty">{loaded.error}</div> :
         !visibleRows.length ? <div className="np-od-empty">暂无已核实的每日明细</div> :
         visibleRows.map(r=><div className="np-od-grid np-od-row" key={r.date}>
           <span title={r.date}>{r.date}</span><span>{qty(r.units)}</span><span>{qty(r.orders)}</span>
           <span title={usd(r.averagePrice)}>{usd(r.averagePrice)}</span>
           <span title={usd(r.ad)}>{usd(r.ad)}</span><span>{pct(r.adShare)}</span>
           <span className={red(r.profit)} title={usd(r.profit)}>{usd(r.profit)}</span>
           <span className={red(r.margin)}>{pct(r.margin)}</span>
           <span className={red(r.roi)}>{decimal(r.roi)}</span>
         </div>)}
      </div>
      <div className="np-od-grid np-od-total">
        <b>合计</b><b>{qty(n("sales_units"))}</b><b>{qty(n("sales_orders"))}</b>
        <b>{usd(totalAverage)}</b><b>{usd(totalAds)}</b><b>{pct(totalAdShare)}</b>
        <b className={red(totalProfit)}>{usd(totalProfit)}</b>
        <b className={red(n("margin_pct"))}>{pct(n("margin_pct"))}</b>
        <b className={red(n("roi"))}>{decimal(n("roi"))}</b>
      </div>
    </div>
    {loaded.state === "ready" && <small className="np-od-truncated">
      与自动评分使用同一利润计算函数；退款不冲减付费收入，送样收入及成本排除，广告 SP＋SEM。
      {loaded.cutoff ? ` 数据截止 ${loaded.cutoff}（洛杉矶）。` : ""}
      {!loaded.completeDays ? "部分业务日缺少销售源记录：每日明细仅显示已核实的日期。" : ""}
      {loaded.scoreComparison !== "saved_score_reconciled" ? "本次同源实时计算与已保存评分日期可能不同。" : ""}
      {totalInvest === null ? "投入成本未核实。" : ""}
    </small>}
  </div>;
}

// Keyed state scope: a different account/store/Item ID starts a fresh read.
export default function NewProductOperatingDaily({product,initialOperatingDaily}:{product:Product;initialOperatingDaily?:unknown}) {
  const identity = product.backend?.identity;
  const identityKey = JSON.stringify([
    identity?.source_account_ref, identity?.store_id, identity?.item_id,
  ]);
  return <NewProductOperatingDailyView key={identityKey} product={product} initialOperatingDaily={initialOperatingDaily}/>;
}

// PURCHASE_DETAIL_SYNCHRONIZED_V1: no changes to existing native product-page loading behavior.
