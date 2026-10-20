"""Fail-closed, idempotent WFS anomaly case insertion."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.modules.warehouse_wfs.anomaly_detection import WfsAnomalyCandidate
from app.modules.warehouse_wfs.models import WfsFeeAnomalyCase


class WfsCaseWriteError(ValueError):
    """Safe case-persistence error."""


@dataclass(frozen=True)
class WfsCaseWriteResult:
    action: str
    case_id: UUID | None


def build_wfs_case_insert(
    *,
    item_id: str,
    candidate: WfsAnomalyCandidate,
):
    """Create an insert-only statement; never update existing cases."""
    if not item_id or not item_id.strip():
        raise WfsCaseWriteError("WFS_ITEM_ID_REQUIRED")

    if not all((
        candidate.source_account_ref,
        candidate.store_id,
        candidate.msku,
    )):
        raise WfsCaseWriteError("WFS_INVALID_CASE_IDENTITY")

    if (
        candidate.actual_unit_fee <= 0
        or candidate.standard_unit_fee <= 0
        or candidate.unit_overcharge <= 0
        or candidate.actual_unit_fee - candidate.standard_unit_fee
        != candidate.unit_overcharge
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
        affected_units=0,
        affected_units_source=None,
        estimated_recover_amount=Decimal("0"),
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
) -> WfsCaseWriteResult:
    """Insert only with explicit authorization; never commit internally.

    The caller owns the transaction and must verify listing identity first.
    Existing cases are preserved via ON CONFLICT DO NOTHING.
    """
    build_wfs_case_insert(
        item_id=item_id,
        candidate=candidate,
    )

    if not execute:
        return WfsCaseWriteResult(action="dry_run", case_id=None)

    raise WfsCaseWriteError("WFS_CASE_EXECUTION_NOT_ENABLED")
