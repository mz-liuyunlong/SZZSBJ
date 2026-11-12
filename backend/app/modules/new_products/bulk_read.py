"""Bounded set-based list snapshot; never alters business metrics or persists data.

The /listings path must not make per-item queries: 200 rows previously needed
>1000 database round trips. Detail/score endpoints retain their original path.
Only the current scoped page is materialized. All identity values are bound JSON.
"""

from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

from sqlalchemy import select, text, tuple_
from sqlalchemy.orm import Session

from .models import MarketScore, PurchaseApplication, TrackingDecision

Key = tuple[str, str, str]


@dataclass(frozen=True)
class ReadSnapshot:
    first: dict[Key, dict[str, Any]]
    orders: dict[Key, dict[str, Any]]
    daily: dict[Key, list[dict[str, Any]]]
    ads: dict[Key, dict[str, Any]]
    recent_orders: dict[Key, int] = field(default_factory=dict)


@dataclass(frozen=True)
class DecisionSnapshot:
    markets: dict[Key, MarketScore]
    tracking: dict[Key, TrackingDecision]
    purchases: dict[Key, PurchaseApplication]


def key_of(record: Any) -> Key:
    return (str(record.source_account_ref), str(record.store_id), str(record.item_id))


def _json_keys(keys: list[Key]) -> str:
    return json.dumps(
        [{"account": a, "store": s, "item": i} for a, s, i in keys],
        ensure_ascii=True,
        separators=(",", ":"),
    )


def _json_windows(windows: list[dict[str, str]]) -> str:
    return json.dumps(windows, ensure_ascii=True, separators=(",", ":"))


def _as_key(record: dict[str, Any]) -> Key:
    return str(record["account"]), str(record["store"]), str(record["item"])


_FIRST_SQL = text("""
WITH wanted AS (
    SELECT account, store, item
    FROM jsonb_to_recordset(CAST(:wanted AS jsonb)) AS j(account text,store text,item text)
)
SELECT w.account,w.store,w.item, l.first_wfs_available_date_la AS day,l.date_source
FROM wanted w
LEFT JOIN listing_wfs_first_stock_la_locked l
  ON l.source_account_ref=w.account AND l.store_id=w.store AND l.item_id=w.item
""")

_ORDERS_SQL = text("""
WITH wanted AS (
    SELECT account,store,item,start_date,end_date
    FROM jsonb_to_recordset(CAST(:windows AS jsonb))
      AS j(account text,store text,item text,start_date date,end_date date)
), order_groups AS (
    SELECT w.account,w.store,w.item,g.order_ref,g.first_date,g.units,g.unknown_lines
    FROM wanted w
    JOIN LATERAL (
        SELECT f.source_order_id AS order_ref,
               min(f.business_date_la) AS first_date,
               sum(f.quantity) AS units,
               count(*) FILTER (
                   WHERE f.quantity IS NULL OR f.business_date_la IS NULL
               ) AS unknown_lines
        FROM fact_walmart_order_items f
        WHERE f.store_id=w.store
          AND f.item_id=w.item
          AND f.source_account_ref=w.account
          AND f.is_identity_current IS TRUE
          AND f.is_sample_order IS FALSE
          AND f.business_date_la BETWEEN w.start_date AND w.end_date
          AND UPPER(COALESCE(f.order_status_raw,'')) NOT IN (
              'CANCELED','CANCELLED','CANCEL','VOID'
          )
        GROUP BY f.source_order_id
    ) g ON TRUE
)
SELECT account,store,item,count(*) AS order_count,sum(units) AS units,
       count(*) FILTER (WHERE units = 1) AS single_orders,
       min(first_date) AS first_order_date,
       coalesce(sum(unknown_lines),0) AS unknown_lines
FROM order_groups GROUP BY account,store,item
""")

_DAILY_SQL = text("""
WITH wanted AS (
    SELECT account,store,item,start_date,end_date
    FROM jsonb_to_recordset(CAST(:windows AS jsonb))
      AS j(account text,store text,item text,start_date date,end_date date)
)
SELECT w.account,w.store,w.item,d.business_date_la AS day,
       d.sales_qty,d.order_count,d.sales_amount,d.gross_profit_amount,d.cost_status,
       d.sales_currency_code,d.gross_profit_currency_code,
       d.roi,d.gross_margin,d.ad_spend_amount,d.purchase_cost_total_usd,
       d.first_leg_cost_total_usd,d.missing_cost_codes_json,d.calculated_at
FROM wanted w JOIN mart_daily_sales_item_day d
  ON d.source_account_ref=w.account AND d.store_id=w.store AND d.item_id=w.item
WHERE d.business_date_la BETWEEN w.start_date AND w.end_date
ORDER BY w.account,w.store,w.item,d.business_date_la
""")

_ADS_SQL = text("""
WITH wanted AS (
    SELECT account,store,item,start_date,end_date
    FROM jsonb_to_recordset(CAST(:windows AS jsonb))
      AS j(account text,store text,item text,start_date date,end_date date)
)
SELECT w.account,w.store,w.item,count(*) AS n,
       count(*) FILTER (WHERE a.ad_spend_amount IS NULL OR a.num_ads_clicks IS NULL
           OR a.attributed_orders IS NULL OR a.attributed_sales_amount IS NULL
           OR a.ad_spend_currency_code IS DISTINCT FROM 'USD'
           OR a.attributed_sales_currency_code IS DISTINCT FROM 'USD') AS incomplete,
       count(*) FILTER (WHERE a.ad_spend_amount IS NULL
             OR a.ad_spend_currency_code IS DISTINCT FROM 'USD') AS spend_missing,
       count(*) FILTER (WHERE a.num_ads_clicks IS NULL) AS clicks_missing,
       sum(a.ad_spend_amount) FILTER (WHERE a.ad_spend_currency_code = 'USD') AS spend,
       sum(a.num_ads_clicks) AS clicks,
       sum(a.attributed_orders) AS orders,sum(a.attributed_sales_amount) AS revenue,
       max(a.synced_at) AS latest_sync
FROM wanted w JOIN fact_walmart_ad_item_sp_daily a
  ON a.source_account_ref=w.account AND a.store_id=w.store AND a.item_id=w.item
WHERE a.business_date_la BETWEEN w.start_date AND w.end_date
GROUP BY w.account,w.store,w.item
""")

EMPTY_ORDERS: dict[str, Any] = {
    "order_count": 0,
    "units": None,
    "single_orders": 0,
    "first_order_date": None,
    "unknown_lines": 0,
}
EMPTY_ADS: dict[str, Any] = {
    "n": 0,
    "incomplete": 0,
    "spend": None,
    "clicks": None,
    "orders": None,
    "revenue": None,
    "latest_sync": None,
    "spend_missing": 0,
    "clicks_missing": 0,
}


_RECENT_ORDERS_SQL = text("""
WITH wanted AS (
    SELECT account,store,item FROM jsonb_to_recordset(CAST(:wanted AS jsonb))
      AS j(account text,store text,item text)
)
SELECT w.account,w.store,w.item,coalesce(sum(d.order_count),0) AS orders_7d
FROM wanted w LEFT JOIN mart_daily_sales_item_day d
  ON d.source_account_ref=w.account AND d.store_id=w.store AND d.item_id=w.item
 AND d.business_date_la BETWEEN :since AND :through
GROUP BY w.account,w.store,w.item
""")


def load_read_snapshot(
    session: Session, keys: Iterable[Key], today: date, *, preview_since_first: bool = False
) -> ReadSnapshot:
    requested = list(dict.fromkeys(keys))
    if not requested:
        return ReadSnapshot({}, {}, {}, {})
    if len(requested) > 200:
        raise ValueError("List batch cannot exceed 200 identities")
    first: dict[Key, dict[str, Any]] = {}
    for row in session.execute(_FIRST_SQL, {"wanted": _json_keys(requested)}).mappings():
        record = dict(row)
        first[_as_key(record)] = record

    # The existing 14-day observation is preserved for each Listing independently.
    # Date-window predicates are applied inside PostgreSQL, not in the frontend.
    windows = []
    for a, s, i in requested:
        first_day = first.get((a, s, i), {}).get("day")
        if first_day is None or first_day > today:
            continue
        windows.append(
            {
                "account": a,
                "store": s,
                "item": i,
                "start_date": first_day.isoformat(),
                "end_date": min(first_day + timedelta(days=13), today).isoformat(),
            }
        )
    if not windows:
        return ReadSnapshot(first, {}, {}, {})
    params = {"windows": _json_windows(windows)}
    orders = {
        _as_key(record): record
        for row in session.execute(_ORDERS_SQL, params).mappings()
        if (record := dict(row))
    }
    daily: dict[Key, list[dict[str, Any]]] = defaultdict(list)
    for row in session.execute(_DAILY_SQL, params).mappings():
        record = dict(row)
        daily[_as_key(record)].append(record)
    ad_windows = (
        [{**w, "end_date": today.isoformat()} for w in windows] if preview_since_first else windows
    )
    ads = {
        _as_key(record): record
        for row in session.execute(_ADS_SQL, {"windows": _json_windows(ad_windows)}).mappings()
        if (record := dict(row))
    }
    recent = {}
    if preview_since_first:
        # Last seven *complete* Los Angeles business dates, independent of the
        # product's 14-day evaluation window and its cumulative ad window.
        recent = {
            _as_key(r): int(r["orders_7d"])
            for r in session.execute(
                _RECENT_ORDERS_SQL,
                {
                    "wanted": _json_keys(requested),
                    "since": today - timedelta(days=7),
                    "through": today - timedelta(days=1),
                },
            ).mappings()
        }
    return ReadSnapshot(first, orders, dict(daily), ads, recent)


def load_decision_snapshot(session: Session, keys: Iterable[Key]) -> DecisionSnapshot:
    requested = list(dict.fromkeys(keys))
    if not requested:
        return DecisionSnapshot({}, {}, {})
    if len(requested) > 200:
        raise ValueError("Decision batch cannot exceed 200 identities")

    def scoped(model):
        return tuple_(
            model.source_account_ref,
            model.store_id,
            model.item_id,
        ).in_(requested)

    markets = {
        key_of(row): row
        for row in session.scalars(
            select(MarketScore).where(scoped(MarketScore)),
        ).all()
    }
    tracking = {
        key_of(row): row
        for row in session.scalars(
            select(TrackingDecision).where(scoped(TrackingDecision)),
        ).all()
    }
    purchases = {
        key_of(row): row
        for row in session.scalars(
            select(PurchaseApplication).where(
                scoped(PurchaseApplication),
                PurchaseApplication.status == "submitted",
            ),
        ).all()
    }
    return DecisionSnapshot(markets, tracking, purchases)
