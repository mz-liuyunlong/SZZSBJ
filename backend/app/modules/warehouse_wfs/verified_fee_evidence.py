"""WFS settlement evidence and recovery estimates.

Pure calculation layer. No database writes or provider requests.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any

from app.modules.warehouse_wfs.fee_detection import (
    SettlementFeeRow,
    calculate_wfs_amounts,
    decimal_value,
    resolve_wfs_fees,
)


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


def settlement_date(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).date()
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
    recent_window_days: int = 60,
) -> FeeEvidence:
    """Evaluate WFS fee evidence without writing any data."""
    if standard_fee < 0:
        raise ValueError("INVALID_STANDARD_FEE")
    if historical_units is not None and historical_units < 0:
        raise ValueError("INVALID_HISTORICAL_UNITS")
    if recent_window_days <= 0 or min_sample_units <= 0:
        raise ValueError("INVALID_WINDOW")

    today = as_of or date.today()
    groups: dict[str, list[tuple[Mapping[str, Any], str]]] = {}
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
        groups.setdefault(order, []).append((row, f"{uid}:{index}"))

    normalized_rows: list[SettlementFeeRow] = []

    for order, group in groups.items():
        try:
            sales = sum(
                (
                    decimal_value(row.get("salesNum"))
                    for row, _ in group
                    if decimal_value(row.get("salesNum")) > 0
                ),
                Decimal("0"),
            )
            fee = sum(
                (decimal_value(row.get("platformLogisticsAmount")) for row, _ in group),
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
            parsed_day
            for row, _ in group
            if (parsed_day := settlement_date(row.get("settlementDate")))
        ]
        if not dates:
            warnings.add("MISSING_SETTLEMENT_DATE")
            continue

        settlement_day = max(dates).isoformat()
        for row, source_line_ref in group:
            normalized_rows.append(
                SettlementFeeRow(
                    source_account_ref="verified-evidence",
                    store_id="verified-evidence",
                    msku=msku,
                    platform_order_no=order,
                    sales_num=decimal_value(row.get("salesNum")),
                    platform_logistics_amount=decimal_value(row.get("platformLogisticsAmount")),
                    settlement_date=settlement_day,
                    source_line_ref=source_line_ref,
                    fee_scope_status="verified_wfs",
                )
            )

    if not normalized_rows:
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

    all_resolved = resolve_wfs_fees(normalized_rows, min_sample_units=1)[0]
    latest = all_resolved.latest_settlement_date
    if latest is None:
        raise ValueError("MISSING_SETTLEMENT_DATE")
    cutoff = latest - timedelta(days=recent_window_days - 1)
    recent_rows = [
        row
        for row in normalized_rows
        if cutoff <= date.fromisoformat(row.settlement_date) <= latest
    ]
    recent_resolved = resolve_wfs_fees(
        recent_rows,
        min_sample_units=min_sample_units,
    )[0]
    actual_fee = recent_resolved.unit_fee
    if actual_fee is None:
        warnings.add("INSUFFICIENT_RECENT_SAMPLE")

    if latest > today:
        warnings.add("FUTURE_SETTLEMENT_DATE")
    elif (today - latest).days > max_age_days:
        warnings.add("STALE_SETTLEMENT_DATA")

    fee_distribution: dict[str, int] = {}
    for sample in recent_resolved.order_samples:
        key = str(sample.unit_fee)
        fee_distribution[key] = fee_distribution.get(key, 0) + int(sample.sales_units)
    if len(fee_distribution) > 1:
        warnings.add("MULTIPLE_ACTUAL_FEE_RATES")

    legacy_estimate = None
    difference = None

    if actual_fee is not None:
        difference = actual_fee - standard_fee
        amounts = calculate_wfs_amounts(
            all_resolved.order_samples,
            standard_unit_fee=standard_fee,
            actual_unit_fee=actual_fee,
            historical_units=historical_units,
        )
        legacy_estimate = amounts.legacy_estimate
        evidenced_overcharge = amounts.theoretical_overcharge
        net_difference = amounts.net_sample_difference
    else:
        evidenced_overcharge = Decimal("0")
        net_difference = Decimal("0")

    if actual_fee is None:
        status = "INSUFFICIENT_EVIDENCE"
    elif "FUTURE_SETTLEMENT_DATE" in warnings:
        status = "REVIEW_REQUIRED"
    elif "STALE_SETTLEMENT_DATA" in warnings:
        status = "STALE"
    elif warnings.intersection(
        {
            "DUPLICATE_SETTLEMENT_LINE",
            "INCOMPLETE_ROW_IDENTITY",
            "INVALID_SETTLEMENT_AMOUNT",
            "UNPAIRED_SETTLEMENT",
            "NONINTEGER_SALES_QUANTITY",
            "MISSING_SETTLEMENT_DATE",
        }
    ):
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
        settlement_units=int(all_resolved.sample_units),
        settlement_orders=all_resolved.fee_orders,
        fee_distribution=dict(sorted(fee_distribution.items())),
        latest_settlement_date=latest,
        legacy_estimate=legacy_estimate,
        evidenced_overcharge=evidenced_overcharge,
        evidenced_net_difference=net_difference,
        status=status,
        warnings=tuple(sorted(warnings)),
    )
