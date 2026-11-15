"""Local-only PR337 trust completion from an already verified MART speed view.

The source of sales is still authoritative SaleStat MART. The finalizer only
fills a missing trust dimension when the locked WFS date, existing MART-backed
speed, the 14-day daily orders/units, and the deterministic singles distribution
independently agree. Never updates a persisted row or other module.
"""
from __future__ import annotations

import json
import logging
import os
from collections import defaultdict
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any, Mapping
from zoneinfo import ZoneInfo

from sqlalchemy import text

from .mart_only_v4 import mart_deterministic_evidence
from .rules import DEFAULT_PARAMETERS, DEFAULT_WEIGHTS
from .scoring import evaluate

LOG = logging.getLogger(__name__)
LA = ZoneInfo('America/Los_Angeles')
VERSION = 'PR337_MART_TRUST_FINALIZE_V6_20261115'
MAX_ITEMS = 200
MAX_ROWS = 5000
MART_SPEED_SOURCES = frozenset({
    'MART_SALESTAT_VERIFIED_WINDOW_V3',
    'MART_WITH_VERIFIED_FIRST_DAY',
    'PR337_MART_ONLY_DETERMINISTIC_V4_20261115',
    'PR337_MART_ONLY_DETERMINISTIC_V5_20261115',
})

# Unlike the old V5 gate this query does not require the stale Order-V2-based
# snapshot totals, rebuilt-quality marker or old reconciliation provenance.
# A locked WFS date + independently verified MART-backed speed + actual daily
# SaleStat rows form the read-only proof for this *missing* dimension only.
_DAILY_SQL = text('''
WITH wanted AS (
 SELECT account,store,item FROM jsonb_to_recordset(CAST(:wanted AS jsonb))
   AS j(account text,store text,item text)
)
SELECT w.account,w.store,w.item,
       l.first_wfs_available_date_la AS locked_day,
       d.business_date_la AS day,d.order_count,d.sales_qty
FROM wanted w
JOIN listing_wfs_first_stock_la_locked l
 ON l.source_account_ref=w.account AND l.store_id=w.store AND l.item_id=w.item
JOIN mart_daily_sales_item_day d
 ON d.source_account_ref=w.account AND d.store_id=w.store AND d.item_id=w.item
 AND d.business_date_la BETWEEN l.first_wfs_available_date_la
                            AND l.first_wfs_available_date_la + 13
WHERE l.first_wfs_available_date_la IS NOT NULL
ORDER BY w.account,w.store,w.item,d.business_date_la
LIMIT :limit
''')


def _day(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value)
        except ValueError:
            return None
    return None


def _whole(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        n = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None
    return int(n) if n.is_finite() and n >= 0 and n == n.to_integral_value() else None


def _score(value: Any) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        n = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None
    return n if n.is_finite() and 0 <= n <= 10 else None


def _key(r: Mapping[str, Any]) -> tuple[str, str, str]:
    return tuple(str(r[k]) for k in ('account', 'store', 'item'))


def _candidate(row: Any) -> tuple[str, str, str] | None:
    if not isinstance(row, dict):
        return None
    listing, facts, ev = (row.get(k) for k in ('listing', 'facts', 'evaluation'))
    if not all(isinstance(x, dict) for x in (listing, facts, ev)):
        return None
    if (ev.get('observation_state') != 'automatic_partial'
            or _whole(ev.get('rule_version')) != 0
            or ev.get('total') is not None or ev.get('grade') is not None):
        return None
    dims = ev.get('dimensions')
    if not isinstance(dims, dict) or dims.get('trust') is not None or _score(dims.get('speed')) is None:
        return None
    if (facts.get('speed_evidence_source') not in MART_SPEED_SOURCES
            or facts.get('order_unit_display_source') != 'mart_daily_sales_item_day'):
        return None
    key = tuple(str(listing.get(k) or '').strip() for k in ('source_account_ref', 'store_id', 'item_id'))
    return key if all(key) and all(len(v) <= 200 for v in key) else None


def _reconciles_with_display(row: dict[str, Any], locked: date, proof: Mapping[str, Any]) -> bool:
    """Guard current sale counts, lock, speed and displayed first-order day."""
    listing, facts, ev = row['listing'], row['facts'], row['evaluation']
    if locked + timedelta(days=13) >= datetime.now(LA).date():
        return False
    for v in (listing.get('first_wfs_available_date_la'), facts.get('first_wfs_available_date_la')):
        if v not in (None, '') and _day(v) != locked:
            return False
    if (_whole(facts.get('effective_orders_14d')) != proof['orders']
            or _whole(facts.get('valid_orders_14d')) != proof['orders']
            or _whole(facts.get('valid_units_14d')) != proof['units']):
        return False
    day_no = (proof['first_date'] - locked).days + 1
    if not 1 <= day_no <= 14:
        return False
    if facts.get('first_order_day') not in (None, '') and _whole(facts.get('first_order_day')) != day_no:
        return False
    first_seen = facts.get('observation_first_order_date_la')
    if first_seen not in (None, '') and _day(first_seen) != proof['first_date']:
        return False
    expected = evaluate({
        'elapsed_days': 14,
        'first_order_day': day_no,
        'effective_orders_14d': proof['orders'],
        'market_score': None,
        'ad_status': 'unknown',
    }, {'confirmedScoring': DEFAULT_PARAMETERS, 'weights': DEFAULT_WEIGHTS}, 0)
    numeric = _score(expected['dimensions'].get('speed'))
    existing = _score(ev['dimensions'].get('speed'))
    return numeric is not None and existing is not None and abs(existing - numeric) <= Decimal('0.015')


def _restore_trust(row: dict[str, Any], proof: Mapping[str, Any], locked: date) -> bool:
    if _candidate(row) is None or not _reconciles_with_display(row, locked, proof):
        return False
    ev, facts = row['evaluation'], row['facts']
    numeric = evaluate({
        'market_score': None, 'elapsed_days': 14,
        'first_order_day': (proof['first_date'] - locked).days + 1,
        'effective_orders_14d': proof['orders'],
        'valid_orders_14d': proof['orders'],
        'valid_units_14d': proof['units'],
        'single_unit_orders_14d': proof['singles'],
        'ad_status': 'unknown',
    }, {'confirmedScoring': DEFAULT_PARAMETERS, 'weights': DEFAULT_WEIGHTS}, 0)
    trust = numeric['dimensions'].get('trust')
    if _score(trust) is None:
        return False
    # Apply trust only; speed/ad/profit/market remain byte-for-byte unchanged.
    ev['dimensions']['trust'] = trust
    facts['single_unit_orders_14d'] = proof['singles']
    facts['trust_evidence_source'] = VERSION
    prior = facts.get('order_reconciliation')
    facts['order_reconciliation'] = {
        **(prior if isinstance(prior, dict) else {}),
        'version': VERSION,
        'decision': 'MART_DAILY_UNIQUE_SINGLE_ORDER_DISTRIBUTION',
        'mart_orders': proof['orders'],
        'mart_units': str(proof['units']),
        'verified_orders': proof['orders'],
        'verified_units': proof['units'],
        'verified_singles': proof['singles'],
    }
    weighted = Decimal(0)
    covered = 0
    for name in ('speed', 'ad', 'profit', 'trust'):
        value = _score(ev['dimensions'].get(name))
        if value is not None:
            covered += DEFAULT_WEIGHTS[name]
            weighted += value * Decimal(DEFAULT_WEIGHTS[name]) / 100
    ev['automatic_points'] = str(weighted)
    ev['covered_weight_pct'] = covered
    old = ev.get('missing')
    if isinstance(old, list):
        ev['missing'] = [v for v in old if v not in {
            'FACT\u4e0eMART\u8ba2\u5355\u6570\u6216\u9500\u552e\u4ef6\u6570\u4e0d\u4e00\u81f4\uff0c\u6570\u636e\u53ef\u4fe1\u5ea6\u5f85\u6838\u5b9e',
            '\u9500\u552e\u4ef6\u6570/\u8ba2\u5355\u6570/\u5355\u4ef6\u8ba2\u5355\u5360\u6bd4',
        }]
    return True


def finalize_missing_mart_trust(session: Any, rows: list[dict[str, Any]]) -> None:
    """Last PR337 list pass: 1 bounded MART query, no write operations."""
    if os.getenv('APP_ENV', '').strip().lower() not in {'local', 'dev', 'development'}:
        return
    eligible = {key: row for row in rows if (key := _candidate(row)) is not None}
    if not eligible or len(eligible) > MAX_ITEMS:
        return
    wanted = json.dumps([{'account': a, 'store': s, 'item': i} for a,s,i in eligible], separators=(',', ':'))
    try:
        fetched = list(session.execute(_DAILY_SQL, {'wanted': wanted, 'limit': MAX_ROWS+1}).mappings())
        if len(fetched) > MAX_ROWS:
            LOG.warning('pr337_mart_trust_v6=bounded_limit_reached')
            return
        buckets: dict[tuple[str,str,str], list[dict[str,Any]]] = defaultdict(list)
        locked_days: dict[tuple[str,str,str], set[date]] = defaultdict(set)
        for raw in fetched:
            r = dict(raw)
            key = _key(r)
            if key not in eligible:
                return  # No unscoped rows are accepted.
            d = _day(r.get('locked_day'))
            if d is None:
                return
            locked_days[key].add(d)
            buckets[key].append(r)
        restored = 0
        for key, row in eligible.items():
            days = locked_days.get(key, set())
            if len(days) != 1:
                continue
            locked = next(iter(days))
            proof = mart_deterministic_evidence(
                locked, locked + timedelta(days=13), buckets.get(key, [])
            )
            if proof is not None and _restore_trust(row, proof, locked):
                restored += 1
        LOG.info('pr337_mart_trust_v6 restored=%d candidates=%d', restored, len(eligible))
    except Exception as exc:
        LOG.warning('pr337_mart_trust_v6=read_failed type=%s', type(exc).__name__)
