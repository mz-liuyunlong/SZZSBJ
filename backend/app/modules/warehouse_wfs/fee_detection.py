"""WFS settlement fee resolution, independent of transport and persistence."""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

CENT = Decimal("0.01")
MIN_SAMPLE_UNITS = 10
EPSILON = Decimal("0.0001")


@dataclass(frozen=True)
class SettlementFeeRow:
    source_account_ref: str
    store_id: str
    msku: str
    platform_order_no: str
    sales_num: Decimal
    platform_logistics_amount: Decimal
    settlement_date: str
    source_line_ref: str


@dataclass(frozen=True)
class ResolvedWfsFee:
    source_account_ref: str
    store_id: str
    msku: str
    unit_fee: Decimal | None
    sample_units: Decimal
    fee_orders: int
    mode_count: int
    skipped_no_qty: int


def decimal_value(value: object) -> Decimal:
    try:
        result = Decimal(str(value if value is not None else 0))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError("WFS_INVALID_DECIMAL") from exc
    if not result.is_finite():
        raise ValueError("WFS_NONFINITE_DECIMAL")
    return result


def resolve_wfs_fees(
    rows: list[SettlementFeeRow],
    *,
    min_sample_units: int = MIN_SAMPLE_UNITS,
) -> list[ResolvedWfsFee]:
    """Resolve the modal settled unit fee by account, store and MSKU."""

    if min_sample_units < 1:
        raise ValueError("WFS_INVALID_SAMPLE_THRESHOLD")

    grouped: dict[tuple[str, str, str], list[SettlementFeeRow]] = defaultdict(list)

    for row in rows:
        if not row.source_account_ref or not row.store_id or not row.msku:
            raise ValueError("WFS_MISSING_IDENTITY")
        if row.msku.upper().startswith("CS"):
            continue
        grouped[(row.source_account_ref, row.store_id, row.msku)].append(row)

    results: list[ResolvedWfsFee] = []

    for (account, store, msku), group in sorted(grouped.items()):
        by_order: dict[str, list[SettlementFeeRow]] = defaultdict(list)
        seen_lines: set[str] = set()

        for row in group:
            if not row.source_line_ref:
                raise ValueError("WFS_MISSING_SOURCE_LINE_REF")
            if row.source_line_ref in seen_lines:
                raise ValueError("WFS_DUPLICATE_SOURCE_LINE_REF")
            seen_lines.add(row.source_line_ref)

            order_key = row.platform_order_no or f"line:{row.source_line_ref}"
            by_order[order_key].append(row)

        sample_units = sum(
            (row.sales_num for row in group),
            Decimal("0"),
        )

        samples: list[tuple[Decimal, str]] = []
        skipped_no_qty = 0

        for order_rows in by_order.values():
            quantity = sum(
                (row.sales_num for row in order_rows),
                Decimal("0"),
            )
            amount = sum(
                (row.platform_logistics_amount for row in order_rows),
                Decimal("0"),
            )

            if amount == 0:
                continue

            if quantity < 1:
                skipped_no_qty += 1
                continue

            fee = (abs(amount) / quantity).quantize(
                CENT,
                rounding=ROUND_HALF_UP,
            )
            latest_date = max(row.settlement_date for row in order_rows)
            samples.append((fee, latest_date))

        unit_fee: Decimal | None = None
        mode_count = 0

        if sample_units >= min_sample_units and samples:
            counts = Counter(fee for fee, _ in samples)
            latest = {
                fee: max(date for sample_fee, date in samples if sample_fee == fee)
                for fee in counts
            }

            # Tied modes use the most recent settlement date.
            # Numeric order is a deterministic final tie-break.
            selected = max(
                counts,
                key=lambda fee: (counts[fee], latest[fee], fee),
            )
            unit_fee = selected
            mode_count = counts[selected]

        results.append(
            ResolvedWfsFee(
                source_account_ref=account,
                store_id=store,
                msku=msku,
                unit_fee=unit_fee,
                sample_units=sample_units,
                fee_orders=len(samples),
                mode_count=mode_count,
                skipped_no_qty=skipped_no_qty,
            )
        )

    return results


def is_wfs_overcharge(
    *,
    actual_unit_fee: Decimal | None,
    standard_unit_fee: Decimal | None,
) -> bool:
    """Detect a confirmed rate difference without fabricating missing values."""

    if actual_unit_fee is None or standard_unit_fee is None:
        return False
    if actual_unit_fee < 0 or standard_unit_fee <= 0:
        return False

    return actual_unit_fee > standard_unit_fee + EPSILON
