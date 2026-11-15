"""Advertising evidence used *inside* the unified PR337 performance publisher.

No scheduler, writer, startup hook or HTTP reader.  Campaign classification is
established from original Lingxing payloads, never inferred from campaignType.
"""
from __future__ import annotations

import json
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any, Iterable, Mapping

from sqlalchemy import text
from sqlalchemy.orm import Session

from .testing_profit import keys_json

Key = tuple[str, str, str]
D = Decimal

# Aggregate at campaign identity, not item/day: multiple ad groups belong to one
# campaign, and the same campaign ID may occur under different advertisers.
_AD_CAMPAIGNS_SQL = text("""
WITH wanted AS (
 SELECT account,store,item,first_day FROM jsonb_to_recordset(CAST(:wanted AS jsonb))
 AS j(account text,store text,item text,first_day date)
)
SELECT w.account,w.store,w.item,
       a.advertiser_id::text AS advertiser_id,a.campaign_id::text AS campaign_id,
       COUNT(*) AS source_rows,
       COUNT(*) FILTER (WHERE a.ad_spend_amount IS NULL
         OR a.ad_spend_amount < 0 OR a.ad_spend_currency_code IS DISTINCT FROM 'USD'
         OR a.num_ads_clicks IS NULL OR a.num_ads_clicks < 0
         OR a.num_ads_shown IS NULL OR a.num_ads_shown < 0
         OR a.attributed_orders IS NULL OR a.attributed_orders < 0
         OR a.attributed_sales_amount IS NULL OR a.attributed_sales_amount < 0
         OR (a.attributed_sales_amount > 0 AND
           COALESCE(NULLIF(BTRIM(a.attributed_sales_currency_code),''),
             a.ad_spend_currency_code) IS DISTINCT FROM 'USD')) AS invalid_rows,
       SUM(a.ad_spend_amount) AS spend,
       SUM(a.num_ads_clicks) AS clicks,
       SUM(a.num_ads_shown) AS impressions,
       SUM(a.attributed_orders) AS orders,
       SUM(a.attributed_sales_amount) AS attributed_sales
FROM wanted w JOIN fact_walmart_ad_item_sp_daily a
 ON a.source_account_ref=w.account AND a.store_id=w.store AND a.item_id=w.item
WHERE w.first_day IS NOT NULL AND a.business_date_la BETWEEN w.first_day AND :cutoff
GROUP BY w.account,w.store,w.item,a.advertiser_id,a.campaign_id
""")

# The numerator and denominator must refer to the same cumulative window.
_AD_REVENUE_SQL = text("""
WITH wanted AS (
 SELECT account,store,item,first_day FROM jsonb_to_recordset(CAST(:wanted AS jsonb))
 AS j(account text,store text,item text,first_day date)
)
SELECT w.account,w.store,w.item,COUNT(d.business_date_la) AS n,
       COUNT(d.business_date_la) FILTER (WHERE d.sales_amount IS NULL
             OR d.sales_amount < 0 OR d.sales_currency_code IS DISTINCT FROM 'USD') AS invalid,
       SUM(d.sales_amount) AS revenue
FROM wanted w LEFT JOIN mart_daily_sales_item_day d
 ON d.source_account_ref=w.account AND d.store_id=w.store AND d.item_id=w.item
 AND d.business_date_la BETWEEN w.first_day AND :cutoff
GROUP BY w.account,w.store,w.item
""")

# Bounded historical lookup: one scan per *publication*, never one per listing.
# The upper limit is an uncertainty guard, not evidence that all campaigns exist.
_RAW_CAMPAIGNS_SQL = text("""
SELECT payload_json FROM ods_api_raw_blobs
WHERE payload_json IS NOT NULL AND created_at >= :since
 AND payload_json::text LIKE '%campaignAndTargetingType%'
ORDER BY created_at DESC LIMIT :limit
""")


def decimal(value: Any) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        n = D(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None
    return n if n.is_finite() and n >= 0 else None


def integer(value: Any) -> int | None:
    n = decimal(value)
    return int(n) if n is not None and n == n.to_integral_value() else None


def campaign_kind(label: Any) -> str | None:
    if not isinstance(label, str):
        return None
    normalized = label.strip().lower().replace('-', '+').replace('_', '+')
    if normalized in {'sponsoredproducts+auto'}:
        return 'auto'
    if normalized in {'sponsoredproducts+manual', 'video+manual'}:
        return 'manual'
    return None


def campaign_pairs(payload: Any) -> Iterable[tuple[tuple[str, str], str]]:
    """Walk nested API envelopes; a parent advertiser ID may be inherited."""
    def walk(obj: Any, advertiser: str | None = None):
        if isinstance(obj, list):
            for child in obj:
                yield from walk(child, advertiser)
        elif isinstance(obj, dict):
            candidate = obj.get('advertiserId', obj.get('advertiser_id', advertiser))
            owner = str(candidate) if candidate is not None else advertiser
            campaign = obj.get('campaignId', obj.get('campaign_id'))
            kind = campaign_kind(obj.get('campaignAndTargetingType'))
            if owner and campaign is not None and kind:
                yield (owner, str(campaign)), kind
            for child in obj.values():
                if isinstance(child, (dict, list)):
                    yield from walk(child, owner)
    return walk(payload)


def verified_campaign_map(payloads: Iterable[Any]) -> tuple[dict[tuple[str,str],str], set[tuple[str,str]]]:
    mapping: dict[tuple[str,str],str] = {}
    conflicts: set[tuple[str,str]] = set()
    for payload in payloads:
        for key, kind in campaign_pairs(payload):
            prior = mapping.get(key)
            if prior is not None and prior != kind:
                conflicts.add(key)
            mapping[key] = kind
    for key in conflicts:
        mapping.pop(key, None)
    return mapping, conflicts


def _metric_fields(group: Mapping[str, Decimal], sales: Decimal | None) -> dict[str,str | None]:
    spend, orders, clicks, impressions = (group[k] for k in ('spend','orders','clicks','impressions'))
    def ratio(a: Decimal, b: Decimal, mult: int = 1) -> str | None:
        return str(a / b * mult) if b > 0 else None
    return {
        'spend_usd': str(spend), 'orders': str(orders), 'clicks': str(clicks),
        'impressions': str(impressions),
        'spend_ratio_pct': ratio(spend, sales, 100) if sales is not None else None,
    }


def ad_snapshot(
    rows: Iterable[Mapping[str, Any]],
    classification: Mapping[tuple[str,str],str],
    *, first: date | None, cutoff: date,
    sales_revenue: Decimal | None,
    mapping_truncated: bool = False,
) -> dict[str, Any]:
    """Never publish a split amount for unclassified/invalid campaign rows.

    A complete classification permits the arithmetic identity total=auto+manual.
    Null means absent evidence; zero requires an observed, verified campaign group.
    """
    snapshot: dict[str, Any] = {
        'version': 1, 'source': 'fact_walmart_ad_item_sp_daily',
        'window_start_la': first.isoformat() if first else None,
        'window_end_la': cutoff.isoformat(), 'status': 'missing_wfs_date',
        'facts': {}, 'unclassified_campaigns': 0,
    }
    if first is None or first > cutoff:
        return snapshot
    data = list(rows)
    snapshot['source_campaigns'] = len(data)
    if not data:
        snapshot['status'] = 'no_source_rows_unverified'
        return snapshot
    if mapping_truncated:
        snapshot['status'] = 'campaign_mapping_truncated'
        return snapshot
    groups = {key: defaultdict(lambda: D('0')) for key in ('total','auto','manual')}
    invalid = 0
    unmatched = 0
    for record in data:
        owner, campaign = record.get('advertiser_id'), record.get('campaign_id')
        kind = classification.get((str(owner), str(campaign)))
        nums = {name: decimal(record.get(name)) for name in (
            'spend','clicks','impressions','orders','attributed_sales')}
        if (
            integer(record.get('invalid_rows')) != 0 or not all(v is not None for v in nums.values())
            or nums['clicks'] > nums['impressions']
            or nums['orders'] > nums['clicks']
            or any(nums[k] != nums[k].to_integral_value() for k in ('clicks','orders','impressions'))
        ):
            invalid += 1
            continue
        if kind is None:
            unmatched += 1
        for name in ('spend','orders','clicks','impressions'):
            groups['total'][name] += nums[name]
            if kind:
                groups[kind][name] += nums[name]
    snapshot['unclassified_campaigns'] = unmatched
    snapshot['invalid_campaigns'] = invalid
    if invalid:
        snapshot['status'] = 'invalid_source_currency_or_metrics'
        return snapshot
    # Show a verified grand total even if category classification is partial.
    for name, val in _metric_fields(groups['total'], sales_revenue).items():
        snapshot['facts']['ad_total_' + name] = val
    if unmatched:
        snapshot['status'] = 'classification_incomplete'
        return snapshot
    for kind in ('auto','manual'):
        for name, val in _metric_fields(groups[kind], sales_revenue).items():
            snapshot['facts'][kind + '_ad_' + name] = val
    snapshot['status'] = 'complete'
    return snapshot


def load_ad_snapshots(
    source: Session, requested: list[Key], first_dates: Mapping[Key,date|None],
    cutoff: date, *, campaign_limit: int = 3000,
    campaign_catalog: tuple[dict[tuple[str,str],str],bool] | None = None,
) -> dict[Key,dict[str,Any]]:
    if not requested:
        return {}
    if len(requested) > 50:
        raise ValueError('Unified publisher batch limit is 50')
    if campaign_catalog is None:
        campaign_catalog = load_campaign_catalog(source, cutoff, limit=campaign_limit)
    mapping, truncated = campaign_catalog
    wanted = json.dumps([
        {'account':a,'store':s,'item':i,'first_day':first_dates.get((a,s,i)).isoformat()
          if isinstance(first_dates.get((a,s,i)),date) else None}
        for a,s,i in requested
    ])
    params = {'wanted': wanted, 'cutoff': cutoff}
    grouped: dict[Key,list[dict[str,Any]]] = defaultdict(list)
    for row in source.execute(_AD_CAMPAIGNS_SQL, params).mappings():
        item = dict(row)
        grouped[(item['account'],item['store'],item['item'])].append(item)
    revenues = {
        (row['account'],row['store'],row['item']):
           decimal(row['revenue']) if integer(row['invalid'])==0 and integer(row['n']) not in (None,0) else None
        for row in source.execute(_AD_REVENUE_SQL, params).mappings()
    }
    return {
        key: ad_snapshot(grouped.get(key,[]), mapping, first=first_dates.get(key),
            cutoff=cutoff,sales_revenue=revenues.get(key), mapping_truncated=truncated)
        for key in requested
    }


def load_campaign_catalog(source: Session, cutoff: date, *, limit: int = 3000) -> tuple[dict[tuple[str,str],str],bool]:
    """One bounded lookup per publisher run; conflicts and overflow fail closed."""
    since = cutoff - timedelta(days=180)
    raw = list(source.execute(_RAW_CAMPAIGNS_SQL, {
        'since': since, 'limit': limit + 1,
    }).mappings())
    mapping, _ = verified_campaign_map(x['payload_json'] for x in raw)
    return mapping, len(raw) > limit
