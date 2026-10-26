"""Pure WFS anomaly candidate detection. No database writes."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import ROUND_HALF_UP, Decimal

from app.modules.warehouse_wfs.fee_detection import (
    ResolvedWfsFee,
    calculate_wfs_amounts,
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
    calculation_status: str = "ok"
    calculated_at: datetime | None = None
    historical_applicability: str = "current_only"


@dataclass(frozen=True)
class WfsSalesEvidence:
    historical_units: Decimal | None
    sales_start_date: date | None
    sales_end_date: date | None
    coverage_status: str
    coverage_start_date: date | None = None
    coverage_end_date: date | None = None
    coverage_reason: str = "unproven"
    source_watermark: str | None = None


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
    mode_count: int = 0
    historical_units: Decimal | None = None
    sales_start_date: date | None = None
    sales_end_date: date | None = None
    legacy_estimated_overcharge: Decimal | None = None
    theoretical_overcharge: Decimal = Decimal("0")
    net_sample_difference: Decimal = Decimal("0")
    latest_settlement_date: date | None = None
    evidence_status: str = "REVIEW_REQUIRED"
    case_eligible: bool = False
    sales_coverage_status: str = "unknown"
    sales_coverage_reason: str = "unproven"
    sales_coverage_start_date: date | None = None
    sales_coverage_end_date: date | None = None
    sales_source_watermark: str | None = None
    fee_scope_status: str = "unverified"
    evidence_age_days: int | None = None


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
    sales_evidence: dict[tuple[str, str, str], WfsSalesEvidence] | None = None,
    *,
    as_of: date | None = None,
    max_stale_days: int = 14,
) -> WfsDetectionSummary:
    """Compare resolved actual rates with exact account/store/MSKU standards.

    The three monetary metrics are deliberately separate. Current Product
    Management fees applied to historical orders are estimates, not claim amounts.
    """

    standard_by_key: dict[tuple[str, str, str], WfsStandardFee] = {}

    for standard_item in standard_fees:
        key = (
            standard_item.source_account_ref,
            standard_item.store_id,
            standard_item.msku,
        )
        if key in standard_by_key:
            raise ValueError("WFS_DUPLICATE_STANDARD_IDENTITY")
        if standard_item.unit_fee <= 0 or not standard_item.unit_fee.is_finite():
            raise ValueError("WFS_INVALID_STANDARD_FEE")
        standard_by_key[key] = standard_item

    seen_actual: set[tuple[str, str, str]] = set()
    candidates: list[WfsAnomalyCandidate] = []
    missing_standard = 0
    insufficient_samples = 0
    normal = 0
    sales_evidence = sales_evidence or {}
    detection_date = as_of or datetime.now(UTC).date()

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

        matched_standard = standard_by_key.get(key)
        if matched_standard is None or matched_standard.calculation_status != "ok":
            missing_standard += 1
            continue

        if not is_wfs_overcharge(
            actual_unit_fee=actual.unit_fee,
            standard_unit_fee=matched_standard.unit_fee,
        ):
            normal += 1
            continue

        diff = actual.unit_fee - matched_standard.unit_fee
        sales = sales_evidence.get(key)
        historical_units = sales.historical_units if sales is not None else None
        if actual.order_samples:
            amounts = calculate_wfs_amounts(
                actual.order_samples,
                standard_unit_fee=matched_standard.unit_fee,
                actual_unit_fee=actual.unit_fee,
                historical_units=historical_units,
            )
            legacy_estimate = amounts.legacy_estimate
            theoretical = amounts.theoretical_overcharge
            net_difference = amounts.net_sample_difference
        else:
            # Compatibility for pre-evidence callers. Persisted/live detection
            # always supplies order samples and therefore uses the exact formula.
            theoretical = (diff * actual.sample_units).quantize(MONEY, rounding=ROUND_HALF_UP)
            net_difference = theoretical
            legacy_estimate = (
                (diff * historical_units).quantize(MONEY, rounding=ROUND_HALF_UP)
                if historical_units is not None
                else None
            )
        evidence_age_days = (
            (detection_date - actual.latest_settlement_date).days
            if actual.latest_settlement_date is not None
            else None
        )
        future_evidence = evidence_age_days is not None and evidence_age_days < 0
        stale = evidence_age_days is None or evidence_age_days > max_stale_days
        sales_complete = sales is not None and sales.coverage_status == "complete"
        standard_confirmed = matched_standard.source != "product_management_default_unconfirmed"
        evidence_status = (
            "STALE"
            if stale
            else "FUTURE_EVIDENCE"
            if future_evidence
            else "OVERCHARGE_CANDIDATE"
            if sales_complete and standard_confirmed and actual.fee_scope_status == "verified_wfs"
            else "REVIEW_REQUIRED"
        )

        candidates.append(
            WfsAnomalyCandidate(
                source_account_ref=actual.source_account_ref,
                store_id=actual.store_id,
                msku=actual.msku,
                actual_unit_fee=actual.unit_fee,
                standard_unit_fee=matched_standard.unit_fee,
                unit_overcharge=diff,
                sample_units=actual.sample_units,
                sample_orders=actual.fee_orders,
                mode_count=actual.mode_count,
                estimated_sample_overcharge=theoretical,
                historical_units=historical_units,
                sales_start_date=sales.sales_start_date if sales is not None else None,
                sales_end_date=sales.sales_end_date if sales is not None else None,
                legacy_estimated_overcharge=legacy_estimate,
                theoretical_overcharge=theoretical,
                net_sample_difference=net_difference,
                latest_settlement_date=actual.latest_settlement_date,
                evidence_status=evidence_status,
                case_eligible=evidence_status == "OVERCHARGE_CANDIDATE",
                standard_source=matched_standard.source,
                rule_version=matched_standard.rule_version,
                sales_coverage_status=(sales.coverage_status if sales is not None else "missing"),
                sales_coverage_reason=(
                    sales.coverage_reason if sales is not None else "sales_evidence_missing"
                ),
                sales_coverage_start_date=(
                    sales.coverage_start_date if sales is not None else None
                ),
                sales_coverage_end_date=(sales.coverage_end_date if sales is not None else None),
                sales_source_watermark=(sales.source_watermark if sales is not None else None),
                fee_scope_status=actual.fee_scope_status,
                evidence_age_days=evidence_age_days,
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
