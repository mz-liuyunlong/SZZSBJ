"""Fail-closed, idempotent WFS anomaly case insertion."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import cast
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session
from sqlalchemy.sql.dml import ReturningInsert

from app.modules.warehouse_wfs.anomaly_detection import WfsAnomalyCandidate
from app.modules.warehouse_wfs.models import WfsFeeAnomalyCase, WfsFeeDetectionEvidence


class WfsCaseWriteError(ValueError):
    """Safe case-persistence error."""


@dataclass(frozen=True)
class WfsCaseWriteResult:
    action: str
    case_id: UUID | None


def record_wfs_detection_evidence(
    session: Session,
    *,
    collection_id: UUID,
    item_id: str,
    candidate: WfsAnomalyCandidate,
    case_id: UUID | None,
    business_as_of_date: date,
    detected_at: datetime,
    persist: bool,
    is_backtest: bool = False,
) -> UUID | None:
    """Append one immutable evidence snapshot; previews/backtests write nothing."""

    if not persist or is_backtest:
        return None
    evidence_id = uuid4()
    statement = (
        insert(WfsFeeDetectionEvidence)
        .values(
            id=evidence_id,
            collection_id=collection_id,
            case_id=case_id,
            source_account_ref=candidate.source_account_ref,
            store_id=candidate.store_id,
            item_id=item_id,
            msku=candidate.msku,
            actual_unit_fee=candidate.actual_unit_fee,
            standard_unit_fee=candidate.standard_unit_fee,
            unit_fee_diff=candidate.unit_overcharge,
            sample_units=candidate.sample_units,
            sample_orders=candidate.sample_orders,
            mode_count=candidate.mode_count,
            historical_units=candidate.historical_units,
            sales_start_date=candidate.sales_start_date,
            sales_end_date=candidate.sales_end_date,
            sales_coverage_status=candidate.sales_coverage_status,
            sales_coverage_reason=candidate.sales_coverage_reason,
            sales_coverage_start_date=candidate.sales_coverage_start_date,
            sales_coverage_end_date=candidate.sales_coverage_end_date,
            sales_source_watermark=candidate.sales_source_watermark,
            legacy_estimated_overcharge=candidate.legacy_estimated_overcharge,
            theoretical_overcharge=candidate.theoretical_overcharge,
            net_sample_difference=candidate.net_sample_difference,
            latest_settlement_date=candidate.latest_settlement_date,
            evidence_status=candidate.evidence_status,
            fee_scope_status=candidate.fee_scope_status,
            standard_fee_source=candidate.standard_source,
            rule_version=candidate.rule_version[:64],
            business_as_of_date=business_as_of_date,
            detected_at=detected_at,
            is_backtest=False,
            created_at=detected_at,
        )
        .on_conflict_do_nothing(
            index_elements=["collection_id", "item_id", "msku"],
        )
        .returning(WfsFeeDetectionEvidence.id)
    )
    return cast(UUID | None, session.execute(statement).scalar_one_or_none())


def build_wfs_case_insert(
    *,
    item_id: str,
    candidate: WfsAnomalyCandidate,
) -> ReturningInsert[tuple[UUID]]:
    """Create an insert-only statement; never update existing cases."""
    if not item_id or not item_id.strip():
        raise WfsCaseWriteError("WFS_ITEM_ID_REQUIRED")

    if not all(
        (
            candidate.source_account_ref,
            candidate.store_id,
            candidate.msku,
        )
    ):
        raise WfsCaseWriteError("WFS_INVALID_CASE_IDENTITY")

    if (
        candidate.actual_unit_fee <= 0
        or candidate.standard_unit_fee <= 0
        or candidate.unit_overcharge <= 0
        or candidate.actual_unit_fee - candidate.standard_unit_fee != candidate.unit_overcharge
    ):
        raise WfsCaseWriteError("WFS_INVALID_FEE_DIFFERENCE")

    now = datetime.now(UTC)
    case_id = uuid4()

    statement = insert(WfsFeeAnomalyCase).values(
        id=case_id,
        source_kind="future_lingxing_profit_order",
        platform="walmart",
        source_account_ref=candidate.source_account_ref,
        store_id=candidate.store_id,
        item_id=item_id.strip(),
        msku=candidate.msku,
        currency_code="USD",
        manual_unit_fee=candidate.standard_unit_fee,
        actual_unit_fee=candidate.actual_unit_fee,
        unit_fee_diff=candidate.unit_overcharge,
        fee_source="lingxing_profit_order",
        fee_calculated_at=now,
        calculation_version=candidate.rule_version[:64],
        status="pending_confirm",
        priority="medium",
        severity="medium",
        first_alert_at=now,
        status_changed_at=now,
        status_changed_by="wfs_auto_detection",
        updated_by="wfs_auto_detection",
        created_at=now,
        updated_at=now,
        affected_units=(
            int(candidate.historical_units) if candidate.historical_units is not None else 0
        ),
        affected_units_source=(
            "mart_daily_sales_item_day_lifetime" if candidate.historical_units is not None else None
        ),
        affected_sales_start_date=candidate.sales_start_date,
        affected_sales_end_date=candidate.sales_end_date,
        estimated_recover_amount=candidate.legacy_estimated_overcharge or Decimal("0"),
        estimate_formula="modal_fee_diff_x_lifetime_sales",
        estimate_calculated_at=now,
        valid_sample_units=candidate.sample_units,
        valid_fee_orders=candidate.sample_orders,
        mode_count=candidate.mode_count,
        theoretical_overcharge_amount=candidate.theoretical_overcharge,
        net_sample_difference_amount=candidate.net_sample_difference,
        latest_settlement_date=candidate.latest_settlement_date,
        detection_status=candidate.evidence_status,
        data_freshness_status=(
            "stale"
            if candidate.evidence_status == "STALE"
            else "invalid"
            if candidate.evidence_status == "FUTURE_EVIDENCE"
            else "current"
            if candidate.evidence_status == "OVERCHARGE_CANDIDATE"
            else "review_required"
        ),
        standard_fee_source=candidate.standard_source,
        detected_at=now,
        claim_amount=None,
        recovered_amount=Decimal("0"),
        archive_review_status="none",
        is_deleted=False,
    )

    return statement.on_conflict_do_nothing(
        index_elements=[
            "source_account_ref",
            "store_id",
            "item_id",
            "msku",
        ],
    ).returning(WfsFeeAnomalyCase.id)


def create_wfs_case(
    session: Session,
    *,
    item_id: str,
    candidate: WfsAnomalyCandidate,
    execute: bool = False,
    detect_enabled: bool = False,
    case_create_enabled: bool = False,
) -> WfsCaseWriteResult:
    """Insert only with explicit authorization; never commit internally.

    The caller owns the transaction and must verify listing identity first.
    Existing cases are preserved via ON CONFLICT DO NOTHING.
    """
    build_wfs_case_insert(
        item_id=item_id,
        candidate=candidate,
    )

    existing_id = session.scalar(
        select(WfsFeeAnomalyCase.id).where(
            WfsFeeAnomalyCase.source_account_ref == candidate.source_account_ref,
            WfsFeeAnomalyCase.store_id == candidate.store_id,
            WfsFeeAnomalyCase.item_id == item_id.strip(),
            WfsFeeAnomalyCase.msku == candidate.msku,
        )
    )
    if existing_id is not None:
        return WfsCaseWriteResult(action="already_exists", case_id=existing_id)

    if not candidate.case_eligible:
        return WfsCaseWriteResult(action="review_required", case_id=None)

    if not execute:
        return WfsCaseWriteResult(action="dry_run", case_id=None)

    if not detect_enabled or not case_create_enabled:
        raise WfsCaseWriteError("WFS_CASE_EXECUTION_NOT_ENABLED")

    case_id = session.execute(
        build_wfs_case_insert(item_id=item_id, candidate=candidate)
    ).scalar_one_or_none()
    return WfsCaseWriteResult(
        action="created" if case_id is not None else "already_exists",
        case_id=case_id,
    )
