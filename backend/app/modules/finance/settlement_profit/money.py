"""Decimal helpers: bill month, FX conversion and largest-remainder allocation (PRP §8.2)."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date
from decimal import ROUND_DOWN, ROUND_HALF_UP, Decimal

CENT = Decimal("0.01")
STORE_PRECISION = Decimal("0.0001")
ZERO = Decimal("0")


def month_start(value: date) -> date:
    return value.replace(day=1)


def bill_month_of(report_date: date) -> date:
    """账单日 ≤ 次月 5 号算上月 (PRP §8.2)."""
    if report_date.day > 5:
        return month_start(report_date)
    if report_date.month == 1:
        return date(report_date.year - 1, 12, 1)
    return date(report_date.year, report_date.month - 1, 1)


def q4(value: Decimal) -> Decimal:
    """Normalise to the column precision numeric(18, 4)."""
    return value.quantize(STORE_PRECISION, rounding=ROUND_HALF_UP)


def to_usd(amount_cny: Decimal | None, rate: Decimal | None) -> Decimal | None:
    """¥ → $ with the month rate; no rate means no conversion (no fallback, §8.2)."""
    if amount_cny is None or rate is None:
        return None
    return q4(amount_cny / rate)


def to_cny(amount_usd: Decimal | None, rate: Decimal | None) -> Decimal | None:
    if amount_usd is None or rate is None:
        return None
    return q4(amount_usd * rate)


def allocate[K](total: Decimal, weights: Mapping[K, Decimal]) -> dict[K, Decimal]:
    """Split ``total`` by ``weights`` with the largest-remainder method.

    The parts add up to ``total`` exactly.  Whole-cent totals are split in cents, other
    totals in the column precision (0.0001); negative totals are split by their
    absolute value and the sign is restored.  Keys keep the caller's order; ties go to
    the earlier key.
    Raises ``ValueError`` when all weights are zero (callers decide what that means).
    """
    keys: Sequence[K] = list(weights)
    if not keys:
        raise ValueError("no allocation targets")
    if any(w < 0 for w in weights.values()):
        raise ValueError("negative allocation weight")
    weight_sum = sum(weights.values(), ZERO)
    if weight_sum == 0:
        raise ValueError("all allocation weights are zero")
    unit = CENT if total % CENT == 0 else STORE_PRECISION
    total = q4(total)
    sign = Decimal(-1) if total < 0 else Decimal(1)
    units_total = (abs(total) / unit).to_integral_value(rounding=ROUND_HALF_UP)
    exact = {k: units_total * weights[k] / weight_sum for k in keys}
    floors = {k: exact[k].to_integral_value(rounding=ROUND_DOWN) for k in keys}
    left = int(units_total - sum(floors.values(), ZERO))
    order = sorted(range(len(keys)), key=lambda i: (-(exact[keys[i]] - floors[keys[i]]), i))
    for i in order[:left]:
        floors[keys[i]] += 1
    return {k: sign * floors[k] * unit for k in keys}
