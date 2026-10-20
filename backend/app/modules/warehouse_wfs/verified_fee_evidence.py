"""WFS settlement evidence and recovery estimates.

Pure calculation layer. No database writes or provider requests.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any

CENT = Decimal("0.01")


@dataclass(frozen=True)
class FeeEvidence:
    actual_fee: Decimal | None
    standard_fee: Decimal
    unit_difference: Decimal | None
    historical_units: int | None
    settlement_units: int
    settlement_orders: int
    fee_distribution: dict[str, int]
    latest_settlement_date: date | None
    legacy_estimate: Decimal | None
    evidenced_overcharge: Decimal
    evidenced_net_difference: Decimal
    status: str
    warnings: tuple[str, ...]


def decimal_value(value: Any) -> Decimal:
    if value is None or value == "":
        return Decimal("0")
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError("INVALID_NUMERIC_VALUE") from exc
    if not result.is_finite():
        raise ValueError("NONFINITE_NUMERIC_VALUE")
    return result


def settlement_date(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if not value:
        return None
    try:
        return datetime.fromisoformat(
            str(value).replace("Z", "+00:00")
        ).date()
    except ValueError:
        return None


def analyze_wfs_evidence(
    rows: Iterable[Mapping[str, Any]],
    *,
    msku: str,
    standard_fee: Decimal,
    historical_units: int | None = None,
    as_of: date | None = None,
    max_age_days: int = 14,
    min_sample_units: int = 10,
    recent_window_days: int = 30,
) -> FeeEvidence:
    """Evaluate WFS fee evidence without writing any data."""
    if standard_fee < 0:
        raise ValueError("INVALID_STANDARD_FEE")
    if historical_units is not None and historical_units < 0:
        raise ValueError("INVALID_HISTORICAL_UNITS")
    if recent_window_days <= 0 or min_sample_units <= 0:
        raise ValueError("INVALID_WINDOW")

    today = as_of or date.today()
    groups: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    seen: set[tuple[str, str]] = set()
    warnings: set[str] = set()

    for row in rows:
        if str(row.get("msku") or "").strip() != msku:
            continue

        order = str(row.get("platformOrderNo") or "").strip()
        uid = row.get("uniqueId")
        index = row.get("rowIndex")

        if not order or uid is None or index is None:
            warnings.add("INCOMPLETE_ROW_IDENTITY")
            continue

        line_key = (str(uid), str(index))
        if line_key in seen:
            warnings.add("DUPLICATE_SETTLEMENT_LINE")
            continue

        seen.add(line_key)
        groups[order].append(row)

    order_evidence = []

    for group in groups.values():
        try:
            sales = sum(
                (
                    decimal_value(row.get("salesNum"))
                    for row in group
                    if decimal_value(row.get("salesNum")) > 0
                ),
                Decimal("0"),
            )
            fee = sum(
                (
                    decimal_value(row.get("platformLogisticsAmount"))
                    for row in group
                ),
                Decimal("0"),
            )
        except ValueError:
            warnings.add("INVALID_SETTLEMENT_AMOUNT")
            continue

        if sales <= 0 or fee == 0:
            warnings.add("UNPAIRED_SETTLEMENT")
            continue

        if sales != sales.to_integral_value():
            warnings.add("NONINTEGER_SALES_QUANTITY")
            continue

        dates = [
            day
            for row in group
            if (day := settlement_date(row.get("settlementDate")))
        ]
        if not dates:
            warnings.add("MISSING_SETTLEMENT_DATE")
            continue

        day = max(dates)
        units = int(sales)
        rate = (abs(fee) / sales).quantize(
            CENT, rounding=ROUND_HALF_UP
        )

        order_evidence.append((day, rate, units))

    if not order_evidence:
        return FeeEvidence(
            actual_fee=None,
            standard_fee=standard_fee,
            unit_difference=None,
            historical_units=historical_units,
            settlement_units=0,
            settlement_orders=0,
            fee_distribution={},
            latest_settlement_date=None,
            legacy_estimate=None,
            evidenced_overcharge=Decimal("0"),
            evidenced_net_difference=Decimal("0"),
            status="INSUFFICIENT_EVIDENCE",
            warnings=tuple(sorted(warnings)),
        )

    latest = max(day for day, _, _ in order_evidence)
    cutoff = latest - timedelta(days=recent_window_days - 1)

    recent = [
        (day, rate, units)
        for day, rate, units in order_evidence
        if cutoff <= day <= latest
    ]

    distribution = Counter()
    latest_for_rate: dict[Decimal, date] = {}

    for day, rate, units in recent:
        distribution[rate] += units
        latest_for_rate[rate] = max(
            day, latest_for_rate.get(rate, day)
        )

    recent_units = sum(distribution.values())
    actual_fee = None

    if recent_units >= min_sample_units:
        actual_fee = max(
            distribution,
            key=lambda rate: (
                distribution[rate],
                latest_for_rate[rate],
                rate,
            ),
        )
    else:
        warnings.add("INSUFFICIENT_RECENT_SAMPLE")

    if latest > today:
        warnings.add("FUTURE_SETTLEMENT_DATE")
    elif (today - latest).days > max_age_days:
        warnings.add("STALE_SETTLEMENT_DATA")

    if len(distribution) > 1:
        warnings.add("MULTIPLE_ACTUAL_FEE_RATES")

    legacy_estimate = None
    difference = None

    if actual_fee is not None:
        difference = actual_fee - standard_fee
        if historical_units is not None:
            legacy_estimate = (
                max(difference, Decimal("0"))
                * historical_units
            ).quantize(CENT)

    evidenced_overcharge = sum(
        (
            max(rate - standard_fee, Decimal("0")) * units
            for _, rate, units in order_evidence
        ),
        Decimal("0"),
    ).quantize(CENT)

    net_difference = sum(
        (
            (rate - standard_fee) * units
            for _, rate, units in order_evidence
        ),
        Decimal("0"),
    ).quantize(CENT)

    if actual_fee is None:
        status = "INSUFFICIENT_EVIDENCE"
    elif "FUTURE_SETTLEMENT_DATE" in warnings:
        status = "REVIEW_REQUIRED"
    elif "STALE_SETTLEMENT_DATA" in warnings:
        status = "STALE"
    elif warnings.intersection({
        "DUPLICATE_SETTLEMENT_LINE",
        "INCOMPLETE_ROW_IDENTITY",
        "INVALID_SETTLEMENT_AMOUNT",
        "UNPAIRED_SETTLEMENT",
        "NONINTEGER_SALES_QUANTITY",
        "MISSING_SETTLEMENT_DATE",
    }):
        status = "REVIEW_REQUIRED"
    elif difference is not None and difference > 0:
        status = "OVERCHARGE_CANDIDATE"
    else:
        status = "NO_OVERCHARGE"

    return FeeEvidence(
        actual_fee=actual_fee,
        standard_fee=standard_fee,
        unit_difference=difference,
        historical_units=historical_units,
        settlement_units=sum(
            units for _, _, units in order_evidence
        ),
        settlement_orders=len(order_evidence),
        fee_distribution={
            str(rate): units
            for rate, units in sorted(distribution.items())
        },
        latest_settlement_date=latest,
        legacy_estimate=legacy_estimate,
        evidenced_overcharge=evidenced_overcharge,
        evidenced_net_difference=net_difference,
        status=status,
        warnings=tuple(sorted(warnings)),
    )
