"""Read-only SaleStat-first scoring evidence for new-product observation windows.

SaleStat MART owns paid-sale order/quantity totals. Canonical FACT rows
supply the single-unit distribution only when their totals reconcile.
Historical non-current physical observations are deliberately not promoted
into canonical rows: doing so could double-count superseded order lines.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any


@dataclass(frozen=True)
class OrderEvidence:
    effective_orders: int | None
    first_order_day: int | None
    valid_orders: int | None
    valid_units: Decimal | None
    single_orders: int | None
    fact_reconciled: bool
    reason: str


def _natural(value: object, *, allow_fraction: bool = False) -> Decimal:
    if value is None or isinstance(value, bool):
        raise ValueError("missing or boolean metric")
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError("invalid numeric metric") from exc
    if not number.is_finite() or number < 0:
        raise ValueError("negative or non-finite metric")
    if not allow_fraction and number != number.to_integral_value():
        raise ValueError("fractional order metric")
    return number


def reconcile_sale_stat_order_evidence(
    *,
    first_wfs_day: date | None,
    daily_rows: Sequence[Mapping[str, Any]],
    canonical_orders: Mapping[str, Any] | None,
) -> OrderEvidence:
    """Use paid SaleStat orders for speed and reconciled current FACT for trust.

    No MART evidence => no order score, never an inferred zero.
    FACT disagreement (even FACT > MART) MUST NOT erase authoritative paid
    SaleStat orders/first day: speed is independently known. Only trust stays
    unavailable until a verified order-line sample is available.
    """
    empty = OrderEvidence(None, None, None, None, None, False, "missing_mart_evidence")
    if first_wfs_day is None or not daily_rows:
        return empty

    try:
        total_orders = Decimal(0)
        total_units = Decimal(0)
        positive_dates: list[date] = []
        end_day = first_wfs_day + timedelta(days=13)
        for row in daily_rows:
            day = row.get("day")
            if not isinstance(day, date) or not first_wfs_day <= day <= end_day:
                raise ValueError("invalid business day")
            count = _natural(row.get("order_count"))
            units = _natural(row.get("sales_qty"), allow_fraction=True)
            total_orders += count
            total_units += units
            if count > 0:
                positive_dates.append(day)
        if total_orders > 0 and not positive_dates:
            raise ValueError("missing first order date")
    except (ValueError, TypeError):
        return OrderEvidence(None, None, None, None, None, False, "invalid_mart_evidence")

    first_order_day = (min(positive_dates) - first_wfs_day).days + 1 if positive_dates else None
    count = int(total_orders)

    # FACT is not the sale authority. A conflict can block trust, NEVER speed.
    fact_count: int | None = None
    fact_units: Decimal | None = None
    fact_singles: int | None = None
    incomplete = False
    if canonical_orders is not None:
        try:
            fact_count = int(_natural(canonical_orders.get("order_count")))
            units_raw = canonical_orders.get("units")
            fact_units = _natural(units_raw, allow_fraction=True) if units_raw is not None else None
            fact_singles = int(_natural(canonical_orders.get("single_orders")))
            incomplete = bool(_natural(canonical_orders.get("unknown_lines", 0)))
        except (TypeError, ValueError):
            incomplete = True
            fact_count = None
            fact_units = None
            fact_singles = None

    match = (
        fact_count == count
        and fact_units == total_units
        and fact_singles is not None
        and fact_singles <= count
        and not incomplete
    )
    return OrderEvidence(
        effective_orders=count,
        first_order_day=first_order_day,
        valid_orders=count if match else None,
        valid_units=fact_units if match else None,
        single_orders=fact_singles if match else None,
        fact_reconciled=match,
        reason=(
            "matched"
            if match
            else "fact_orders_exceed_mart"
            if fact_count is not None and fact_count > count
            else "fact_units_exceed_mart"
            if fact_units is not None and fact_units > total_units
            else "fact_mart_disagree"
        ),
    )
