"""Pure WFS anomaly candidate detection. No database writes."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from app.modules.warehouse_wfs.fee_detection import (
    ResolvedWfsFee,
    is_wfs_overcharge,
)

MONEY = Decimal("0.01")


@dataclass(frozen=True)
class WfsStandardFee:
    source_account_ref: str
    store_id: str
    msku: str
    unit_fee: Decimal
    source: str
    rule_version: str


@dataclass(frozen=True)
class WfsAnomalyCandidate:
    source_account_ref: str
    store_id: str
    msku: str
    actual_unit_fee: Decimal
    standard_unit_fee: Decimal
    unit_overcharge: Decimal
    sample_units: Decimal
    sample_orders: int
    estimated_sample_overcharge: Decimal
    standard_source: str
    rule_version: str


@dataclass(frozen=True)
class WfsDetectionSummary:
    scanned: int
    anomalies: int
    missing_standard: int
    insufficient_samples: int
    normal: int
    candidates: tuple[WfsAnomalyCandidate, ...]


def detect_wfs_anomalies(
    actual_fees: list[ResolvedWfsFee],
    standard_fees: list[WfsStandardFee],
) -> WfsDetectionSummary:
    """Compare resolved actual rates with exact account/store/MSKU standards.

    The estimate uses sample units, not lifetime sales and not verified
    overcharged units. It must not be treated as a claim amount.
    """

    standard_by_key: dict[tuple[str, str, str], WfsStandardFee] = {}

    for standard in standard_fees:
        key = (
            standard.source_account_ref,
            standard.store_id,
            standard.msku,
        )
        if key in standard_by_key:
            raise ValueError("WFS_DUPLICATE_STANDARD_IDENTITY")
        if standard.unit_fee <= 0 or not standard.unit_fee.is_finite():
            raise ValueError("WFS_INVALID_STANDARD_FEE")
        standard_by_key[key] = standard

    seen_actual: set[tuple[str, str, str]] = set()
    candidates: list[WfsAnomalyCandidate] = []
    missing_standard = 0
    insufficient_samples = 0
    normal = 0

    for actual in actual_fees:
        key = (
            actual.source_account_ref,
            actual.store_id,
            actual.msku,
        )
        if key in seen_actual:
            raise ValueError("WFS_DUPLICATE_ACTUAL_IDENTITY")
        seen_actual.add(key)

        if actual.unit_fee is None:
            insufficient_samples += 1
            continue

        standard = standard_by_key.get(key)
        if standard is None:
            missing_standard += 1
            continue

        if not is_wfs_overcharge(
            actual_unit_fee=actual.unit_fee,
            standard_unit_fee=standard.unit_fee,
        ):
            normal += 1
            continue

        diff = actual.unit_fee - standard.unit_fee

        candidates.append(
            WfsAnomalyCandidate(
                source_account_ref=actual.source_account_ref,
                store_id=actual.store_id,
                msku=actual.msku,
                actual_unit_fee=actual.unit_fee,
                standard_unit_fee=standard.unit_fee,
                unit_overcharge=diff,
                sample_units=actual.sample_units,
                sample_orders=actual.fee_orders,
                estimated_sample_overcharge=(diff * actual.sample_units).quantize(
                    MONEY, rounding=ROUND_HALF_UP
                ),
                standard_source=standard.source,
                rule_version=standard.rule_version,
            )
        )

    return WfsDetectionSummary(
        scanned=len(actual_fees),
        anomalies=len(candidates),
        missing_standard=missing_standard,
        insufficient_samples=insufficient_samples,
        normal=normal,
        candidates=tuple(candidates),
    )
