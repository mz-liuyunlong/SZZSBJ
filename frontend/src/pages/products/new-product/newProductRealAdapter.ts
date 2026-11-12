/** The ONLY conversion from persisted PR337 backend records to the accepted UI model.
 * Numeric compatibility fields are not evidence of valid observations. All
 * business scoring, grade and purchase recommendation come from `evaluation`.
 */
import type { Product } from './nativeData';
import type { NewProductListing, Identity, RealScore } from './newProductBusinessApi';

export type PersistedProduct = Product & {
  backend: {
    identity: Identity;
    marketVersion: number;
    ruleVersion: number;
    evaluation: RealScore;
    suggestedQty: number | null;
    available: Record<string, boolean>;
    firstWfsDate: string | null;
    firstOrderDate: string | null;
  };
  imageUrl?: string | null;
  msku?: string | null;
  storeName?: string | null;
};

const finite = (value: unknown): number | null => {
  if (value === null || value === undefined || value === '') return null;
  const number = Number(value);
  return Number.isFinite(number) ? number : null;
};
const numberOrZero = (value: number | null) => value ?? 0;
const datePart = (value: unknown): string =>
  typeof value === 'string' && /^\d{4}-\d{2}-\d{2}/.test(value) ? value.slice(0,10) : '';

export function toPersistedProduct(row: NewProductListing): PersistedProduct {
  const listing = row.listing;
  const f = row.facts || {};
  const e = row.evaluation;
  const identity:Identity = {
    source_account_ref:listing.source_account_ref,
    store_id:listing.store_id,
    item_id:listing.item_id,
  };
  const market = finite(f.market_score);
  const dimensions = e.dimensions;
  const speed = finite(dimensions.speed), ad = finite(dimensions.ad);
  const profit = finite(dimensions.profit), trust = finite(dimensions.trust);
  const roi = finite(f.roi), margin = finite(f.gross_margin_pct);
  const spend = finite(f.ad_spend_usd), clicks = finite(f.ad_clicks);
  // The source Listing sales_7d is units, not order count.
  const qty7 = finite(f.orders_7d), sales30 = finite(listing.sales_30d);
  const inventory = finite(listing.wfs_available_quantity);
  const price = finite(listing.sale_price_amount);
  const attributedRevenue = finite(f.ad_revenue_usd);
  const acos = spend!==null && attributedRevenue!==null && attributedRevenue>0 ? spend/attributedRevenue*100:null;
  const day = datePart(f.first_wfs_available_date_la);
  const awaitingCalculation = e.observation_state === 'not_calculated';
  const state = awaitingCalculation ? '待计算'
    : row.purchase_status === 'submitted' ? '审核中'
    : market === null ? '待市场评分'
    : e.grade === null ? '数据待评估'
    : e.grade === 'D' || e.grade === 'Pass' ? '测评停止'
    : '待采购确认';
  const tracking = awaitingCalculation ? '未判定' : (row.tracking_decision ?? (day ? '未判定' : '等待开售'));
  return {
    id:`${identity.source_account_ref}::${identity.store_id}::${identity.item_id}`,
    sku:listing.local_sku || '—',
    name:listing.local_name || listing.title || '品名待同步',
    item:listing.item_id,
    owner:listing.owner_name || '—',
    days:finite(f.elapsed_days) ?? 0,
    market,
    marketReason:row.market_reason ?? '',
    scores:{speed:numberOrZero(speed),ad:numberOrZero(ad),profit:numberOrZero(profit),trust:numberOrZero(trust)},
    penalties:0,penaltyFlags:[],
    roi:numberOrZero(roi),margin:numberOrZero(margin),
    acos:numberOrZero(acos),
    clicks:numberOrZero(clicks),orders:numberOrZero(finite(f.valid_orders_14d)),
    qty7:numberOrZero(qty7),sales30:numberOrZero(sales30),
    spend:numberOrZero(spend),unitCost:0,price:numberOrZero(price),
    inventory:numberOrZero(inventory),
    risk:awaitingCalculation?'尚未执行后台计算':e.missing.length?`数据待评估：${e.missing.join('、')}`:(row.system_recommendation?.reasons || []).join('、'),
    status:state,suggested:row.suggested_qty,requestQty:null,requestReason:'',
    tracking, sales60:0,sales90:0,margin60:0,acos60:0,
    launch:datePart(listing.launch_date_cn),arrival:day,
    sold30:numberOrZero(sales30),sold60:0,sold90:0,
    actualQty:0,reasonFailure:row.tracking_reason ?? '',
    category:listing.category || undefined,
    developer:listing.product_developer_name || undefined,
    operator:listing.owner_name || undefined,
    imageUrl:listing.picture_url,msku:listing.msku,storeName:listing.store_name,
    backend:{identity,marketVersion:row.market_version??0,ruleVersion:row.evaluation.rule_version,
      evaluation:e,suggestedQty:row.suggested_qty ?? null,firstWfsDate:day || null,
      firstOrderDate:datePart(f.first_order_date) || null,
      available:{elapsedDays:finite(f.elapsed_days)!==null,speed:speed!==null,ad:ad!==null,profit:profit!==null,trust:trust!==null,
        roi:roi!==null,margin:margin!==null,orders14:finite(f.valid_orders_14d)!==null,
        qty7:qty7!==null,sales30:sales30!==null,
        spend:spend!==null,inventory:inventory!==null,price:price!==null,clicks:clicks!==null,acos:acos!==null}},
  };
}
