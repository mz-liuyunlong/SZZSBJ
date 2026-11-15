"""PR337 deterministic rolling observation; read MART, never Order V2 as sales authority.

Does not read or write a DB. Missing source evidence is NULL, not zero. Daily
single-unit orders are inferred only when the integer partition is unique.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any, Mapping, Sequence

from .rules import DEFAULT_PARAMETERS, DEFAULT_WEIGHTS
from .scoring import evaluate

VERSION = 'PR337_DAILY_PERSIST_V1'
WEIGHTED = ('speed', 'ad', 'profit', 'trust')


def natural(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        n = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None
    if n.is_finite() and n >= 0 and n == n.to_integral_value():
        return int(n)
    return None


def numeric(value: Any) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        n = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None
    return n if n.is_finite() else None


def to_date(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value[:10])
        except ValueError:
            return None
    return None


def window(first_wfs: date, cutoff: date) -> tuple[date, date]:
    if not isinstance(first_wfs, date) or not isinstance(cutoff, date) or first_wfs > cutoff:
        raise ValueError('NO_MATURE_WFS_WINDOW')
    return first_wfs, min(first_wfs + timedelta(days=13), cutoff)


def daily_partition(orders: int, units: int) -> int | None:
    """An order must contain >=1 unit. Derive singles only if unique.

    Examples: (3,3)->3, (3,4)->2, (3,5)->ambiguous, (1,5)->0.
    """
    if orders < 0 or units < orders or (orders == 0 and units != 0):
        raise ValueError('INVALID_DAILY_TOTALS')
    if orders == 0:
        return 0
    if orders == units:
        return orders
    if orders == 1:
        return 0
    if units == orders + 1:
        return orders - 1
    return None


def compute(
    *, first_wfs: date, cutoff: date, mart: Sequence[Mapping[str, Any]],
    ads: Sequence[Mapping[str, Any]], config: dict | None = None, rule_version: int = 0,
) -> dict[str, Any]:
    start, end = window(first_wfs, cutoff)
    params = config or {'confirmedScoring': DEFAULT_PARAMETERS, 'weights': DEFAULT_WEIGHTS}
    mart_seen: set[date] = set()
    orders = units = singles = 0
    all_singles_known = True
    first_order = None
    revenue = Decimal(0)
    profit = Decimal(0)
    cost = Decimal(0)
    revenue_ok = profit_ok = True
    invalid_rows = 0
    daily_out = []
    for raw in mart:
        day = to_date(raw.get('day'))
        n, q = natural(raw.get('orders')), natural(raw.get('units'))
        bad = natural(raw.get('bad_rows'))
        if (day is None or not start <= day <= end or day in mart_seen or
                n is None or q is None or bad is None or bad or q < n or (n == 0 and q != 0)):
            raise ValueError('INVALID_OR_DUPLICATE_MART_DAY')
        mart_seen.add(day)
        orders += n
        units += q
        if n > 0:
            first_order = min(first_order, day) if first_order else day
        unique = daily_partition(n, q)
        if unique is None:
            all_singles_known = False
        else:
            singles += unique
        sales, gross, purchase, freight = (
            numeric(raw.get(k)) for k in ('revenue','profit','purchase','freight')
        )
        if sales is None or raw.get('revenue_bad') or sales < 0:
            revenue_ok = False
        else:
            revenue += sales
        if (gross is None or purchase is None or freight is None or
                raw.get('profit_bad') or purchase < 0 or freight < 0):
            profit_ok = False
        else:
            profit += gross
            cost += purchase + freight
        daily_out.append({'day': day.isoformat(), 'orders': n, 'units': q,
                          'single_orders': unique})
    if not mart_seen:
        raise ValueError('MART_ROWS_UNAVAILABLE')  # Never turn absent rows into zero.
    if units < orders or (orders and first_order is None):
        raise ValueError('MART_TOTALS_INVALID')

    ad_spend = ad_clicks = ad_orders = ad_sales = None
    ad_status = 'unknown'
    if ads:
        spend, clicks, ad_n, amount = (Decimal(0), 0, 0, Decimal(0))
        bad = False
        for r in ads:
            d = to_date(r.get('day'))
            s, c, o, v = (numeric(r.get('spend')), natural(r.get('clicks')),
                           natural(r.get('orders')), numeric(r.get('sales')))
            if (d is None or not start <= d <= end or r.get('bad_rows') or
                    s is None or c is None or o is None or v is None or s < 0 or v < 0):
                bad = True
                break
            spend += s
            clicks += c
            ad_n += o
            amount += v
        if not bad:
            ad_spend, ad_clicks, ad_orders, ad_sales = spend, clicks, ad_n, amount
            if spend > 0 and clicks > 0 and ad_n <= clicks and (
                (ad_n == 0 and amount == 0) or (ad_n > 0 and amount > 0)
            ):
                ad_status = 'active'
            # Explicit zero-ad rows are not evidence that ads did not run.
    roi = profit / cost if profit_ok and revenue_ok and cost > 0 else None
    margin = profit / revenue * 100 if roi is not None and revenue > 0 else None
    first_order_day = (first_order-start).days + 1 if first_order else None
    facts = {
        'first_order_day': first_order_day,
        'effective_orders_14d': orders,
        'elapsed_days': (end-start).days + 1,
        'valid_orders_14d': orders if orders > 0 and all_singles_known else None,
        'valid_units_14d': units if orders > 0 and all_singles_known else None,
        'single_unit_orders_14d': singles if orders > 0 and all_singles_known else None,
        'ad_status': ad_status,
        'ad_spend_usd': ad_spend if ad_status == 'active' else None,
        'ad_clicks': ad_clicks if ad_status == 'active' else None,
        'ad_orders': ad_orders if ad_status == 'active' else None,
        'ad_revenue_usd': ad_sales if ad_status == 'active' else None,
        'roi': roi, 'gross_margin_pct': margin,
        'market_score': None,
    }
    ev = evaluate(facts, params, rule_version)
    dims = ev['dimensions']
    if dims['speed'] is None:
        raise ValueError('MART_SPEED_NOT_CALCULABLE')
    if orders > 0 and all_singles_known and dims['trust'] is None:
        raise ValueError('MART_TRUST_NOT_CALCULABLE')
    weights = params['weights']
    points = sum((Decimal(dims[k]) * Decimal(str(weights[k])) / 100
                  for k in WEIGHTED if dims[k] is not None), Decimal(0))
    covered = sum((Decimal(str(weights[k])) for k in WEIGHTED if dims[k] is not None), Decimal(0))
    return {
        'window_start_la': start.isoformat(), 'window_end_la': end.isoformat(),
        'cutoff_la': cutoff.isoformat(), 'window_days': (end-start).days+1,
        'observation_complete': end == start + timedelta(days=13),
        'orders': orders, 'units': units, 'singles': singles if all_singles_known and orders > 0 else None,
        'trust_proven': all_singles_known and orders > 0,
        'first_order_date': first_order.isoformat() if first_order else None,
        'first_order_day': first_order_day,
        'mart_rows': len(mart_seen), 'daily': daily_out,
        'sales_amount_usd': str(revenue) if revenue_ok else None,
        'profit_usd': str(profit) if roi is not None else None,
        'roi': str(roi) if roi is not None else None,
        'margin_pct': str(margin) if margin is not None else None,
        'ad_spend_usd': str(ad_spend) if ad_spend is not None else None,
        'ad_clicks': ad_clicks, 'ad_orders': ad_orders,
        'ad_sales_usd': str(ad_sales) if ad_sales is not None else None,
        'ad_status': ad_status,
        'dimensions': dims, 'automatic_points': str(points),
        'covered_weight_pct': str(covered), 'rule_version': rule_version,
        'version': VERSION,
    }
