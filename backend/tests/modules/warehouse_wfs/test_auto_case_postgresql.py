"""Real PostgreSQL coverage for insert-only WFS automatic case persistence.

The suite is opt-in and refuses every target except the dedicated local CI
database/user pair. It never connects to an application database.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import date
from decimal import Decimal
from threading import Barrier
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy import Engine, create_engine, func, inspect, select, text
from sqlalchemy.engine import URL
from sqlalchemy.orm import Session
from sqlalchemy.pool import NullPool

from app.core.config import Settings, SettingsError, get_test_database_url
from app.modules.warehouse_wfs.anomaly_detection import WfsAnomalyCandidate
from app.modules.warehouse_wfs.auto_case_writer import WfsCaseWriteError, create_wfs_case
from app.modules.warehouse_wfs.models import WfsFeeAnomalyCase

_DATABASE = "wfs_auto_case_ci"
_USERNAME = "wfs_auto_case_ci"
_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})
_ACCOUNT_PREFIX = "wfs-auto-case-pg-"


def _validated_database_url() -> URL:
    if os.environ.get("WFS_AUTO_CASE_POSTGRES_TESTS") != "1":
        pytest.skip("requires the dedicated WFS auto-case PostgreSQL test database")
    try:
        url = get_test_database_url(Settings())  # type: ignore[call-arg]
    except (SettingsError, ValidationError) as exc:
        pytest.fail(str(exc), pytrace=False)
    if (
        url.host not in _HOSTS
        or url.database != _DATABASE
        or url.username != _USERNAME
        or url.query
    ):
        pytest.fail("refusing unexpected WFS auto-case database target", pytrace=False)
    return url


@pytest.fixture
def engine() -> Iterator[Engine]:
    engine = create_engine(
        _validated_database_url(),
        poolclass=NullPool,
        hide_parameters=True,
    )
    with engine.connect() as connection:
        assert connection.execute(text("select current_database(), current_user")).one() == (
            _DATABASE,
            _USERNAME,
        )
    _delete_synthetic_cases(engine)
    try:
        yield engine
    finally:
        _delete_synthetic_cases(engine)
        engine.dispose()


def _delete_synthetic_cases(engine: Engine) -> None:
    with engine.begin() as connection:
        connection.execute(
            text("delete from ops_wfs_fee_anomaly_cases where source_account_ref like :prefix"),
            {"prefix": f"{_ACCOUNT_PREFIX}%"},
        )


def candidate(
    identity: str,
    *,
    case_eligible: bool = True,
    standard_source: str = "product_management_confirmed_rule",
) -> WfsAnomalyCandidate:
    return WfsAnomalyCandidate(
        source_account_ref=f"{_ACCOUNT_PREFIX}{identity}",
        store_id="store-a",
        msku="MSKU-A",
        actual_unit_fee=Decimal("6.95"),
        standard_unit_fee=Decimal("6.55"),
        unit_overcharge=Decimal("0.40"),
        sample_units=Decimal("38"),
        sample_orders=32,
        estimated_sample_overcharge=Decimal("15.20"),
        standard_source=standard_source,
        rule_version="synthetic-v1",
        mode_count=32,
        historical_units=Decimal("87"),
        sales_start_date=date(2026, 7, 3),
        sales_end_date=date(2026, 9, 22),
        legacy_estimated_overcharge=Decimal("34.80"),
        theoretical_overcharge=Decimal("15.20"),
        net_sample_difference=Decimal("0.99"),
        latest_settlement_date=date(2026, 10, 17),
        evidence_status="OVERCHARGE_CANDIDATE" if case_eligible else "REVIEW_REQUIRED",
        case_eligible=case_eligible,
        sales_coverage_status="complete" if case_eligible else "partial",
        sales_coverage_reason="synthetic_verified_window",
        sales_coverage_start_date=date(2026, 7, 3),
        sales_coverage_end_date=date(2026, 10, 17),
        sales_source_watermark="synthetic-watermark",
        fee_scope_status="verified_wfs" if case_eligible else "unverified",
        evidence_age_days=9,
    )


def _create_enabled(session: Session, identity: str) -> UUID | None:
    return create_wfs_case(
        session,
        item_id=f"item-{identity}",
        candidate=candidate(identity),
        execute=True,
        detect_enabled=True,
        case_create_enabled=True,
    ).case_id


def _seed_existing_case(
    session: Session,
    identity: str,
    *,
    source_kind: str,
    status: str,
    owner_ref: str,
    archive_review_status: str = "none",
    recovered_amount: Decimal = Decimal("0"),
) -> WfsFeeAnomalyCase:
    row = WfsFeeAnomalyCase(
        id=uuid4(),
        source_kind=source_kind,
        source_case_ref=f"synthetic-{identity}",
        platform="walmart",
        source_account_ref=f"{_ACCOUNT_PREFIX}{identity}",
        store_id="store-a",
        item_id=f"item-{identity}",
        msku="MSKU-A",
        owner_ref=owner_ref,
        currency_code="USD",
        manual_unit_fee=Decimal("6.55"),
        actual_unit_fee=Decimal("6.95"),
        unit_fee_diff=Decimal("0.40"),
        fee_source="synthetic_manual_evidence",
        status=status,
        priority="high",
        severity="high",
        affected_units=7,
        estimated_recover_amount=Decimal("2.80"),
        recovered_amount=recovered_amount,
        archive_review_status=archive_review_status,
        follow_count=3,
        reopen_count=2,
        latest_follow_note="synthetic human note",
        updated_by="synthetic-human",
        is_deleted=False,
    )
    session.add(row)
    session.flush()
    return row


def test_wfs_case_projection_executes_on_postgresql(engine: Engine) -> None:
    """Compile list and detail projections against real PostgreSQL, without case reads."""
    from app.modules.warehouse_wfs.service import WfsFeeAlertService

    projection = WfsFeeAlertService(Session(engine))._case_select_sql()
    with engine.connect() as connection:
        connection.execute(
            text(
                projection + " where false order by case status "
                "when 'following' then 1 else 2 end, "
                "estimated_recover_amount desc, updated_at desc limit 0"
            )
        ).all()
        connection.execute(
            text(projection + " where false and id=:case_id"),
            {"case_id": "00000000-0000-0000-0000-000000000000"},
        ).all()


def test_postgresql_schema_has_0061_columns_and_unique_case_identity(engine: Engine) -> None:
    schema = inspect(engine)
    assert {
        "valid_sample_units",
        "valid_fee_orders",
        "mode_count",
        "theoretical_overcharge_amount",
        "net_sample_difference_amount",
        "latest_settlement_date",
        "detection_status",
        "data_freshness_status",
        "standard_fee_source",
        "detected_at",
    } <= {column["name"] for column in schema.get_columns("ops_wfs_fee_anomaly_cases")}
    assert {
        tuple(constraint["column_names"])
        for constraint in schema.get_unique_constraints("ops_wfs_fee_anomaly_cases")
    } >= {("source_account_ref", "store_id", "item_id", "msku")}
    assert {
        "missing_store_count",
        "wfs_scope_status",
    } <= {column["name"] for column in schema.get_columns("gov_wfs_settlement_collections")}


def test_first_insert_replay_and_full_rollback(engine: Engine) -> None:
    with Session(engine) as session:
        first_id = _create_enabled(session, "first")
        session.commit()
        replay = create_wfs_case(
            session,
            item_id="item-first",
            candidate=candidate("first"),
            execute=True,
            detect_enabled=True,
            case_create_enabled=True,
        )
        session.commit()

    assert first_id is not None
    assert replay.action == "already_exists"
    assert replay.case_id == first_id
    with Session(engine) as session:
        assert (
            session.scalar(
                select(func.count())
                .select_from(WfsFeeAnomalyCase)
                .where(WfsFeeAnomalyCase.source_account_ref == f"{_ACCOUNT_PREFIX}first")
            )
            == 1
        )

    with Session(engine) as session:
        assert _create_enabled(session, "rollback") is not None
        session.flush()
        session.rollback()
    with Session(engine) as session:
        assert (
            session.scalar(
                select(func.count())
                .select_from(WfsFeeAnomalyCase)
                .where(WfsFeeAnomalyCase.source_account_ref == f"{_ACCOUNT_PREFIX}rollback")
            )
            == 0
        )


def test_concurrent_insert_creates_exactly_one_case(engine: Engine) -> None:
    barrier = Barrier(2)

    def write_once() -> str:
        with Session(engine) as session:
            barrier.wait()
            result = create_wfs_case(
                session,
                item_id="item-concurrent",
                candidate=candidate("concurrent"),
                execute=True,
                detect_enabled=True,
                case_create_enabled=True,
            )
            session.commit()
            return result.action

    with ThreadPoolExecutor(max_workers=2) as executor:
        actions = sorted(
            future.result(timeout=10) for future in [executor.submit(write_once) for _ in range(2)]
        )

    assert actions == ["already_exists", "created"]
    with Session(engine) as session:
        assert (
            session.scalar(
                select(func.count())
                .select_from(WfsFeeAnomalyCase)
                .where(WfsFeeAnomalyCase.source_account_ref == f"{_ACCOUNT_PREFIX}concurrent")
            )
            == 1
        )


@pytest.mark.parametrize(
    ("identity", "source_kind", "status", "archive_review_status", "recovered_amount"),
    [
        ("manual", "manual", "following", "none", Decimal("0")),
        ("legacy", "legacy_mirror", "pending_confirm", "none", Decimal("0")),
        ("archived", "manual", "archived", "approved", Decimal("0")),
        ("recovered", "manual", "recovered", "none", Decimal("12.34")),
        ("approval", "manual", "archive_pending", "pending", Decimal("0")),
    ],
)
def test_existing_human_and_legacy_lifecycle_is_never_overwritten(
    engine: Engine,
    identity: str,
    source_kind: str,
    status: str,
    archive_review_status: str,
    recovered_amount: Decimal,
) -> None:
    with Session(engine) as session:
        existing = _seed_existing_case(
            session,
            identity,
            source_kind=source_kind,
            status=status,
            owner_ref="human-owner",
            archive_review_status=archive_review_status,
            recovered_amount=recovered_amount,
        )
        existing_id = existing.id
        session.commit()
        result = create_wfs_case(
            session,
            item_id=f"item-{identity}",
            candidate=candidate(identity),
            execute=True,
            detect_enabled=True,
            case_create_enabled=True,
        )
        session.commit()
        preserved = session.get(WfsFeeAnomalyCase, existing_id)

    assert result.action == "already_exists"
    assert preserved is not None
    assert preserved.source_kind == source_kind
    assert preserved.status == status
    assert preserved.owner_ref == "human-owner"
    assert preserved.archive_review_status == archive_review_status
    assert preserved.recovered_amount == recovered_amount
    assert preserved.follow_count == 3
    assert preserved.latest_follow_note == "synthetic human note"


def test_all_automatic_write_gates_fail_closed(engine: Engine) -> None:
    with Session(engine) as session:
        dry_run = create_wfs_case(
            session,
            item_id="item-dry",
            candidate=candidate("dry"),
        )
        incomplete = create_wfs_case(
            session,
            item_id="item-incomplete",
            candidate=candidate("incomplete", case_eligible=False),
            execute=True,
            detect_enabled=True,
            case_create_enabled=True,
        )
        unconfirmed = create_wfs_case(
            session,
            item_id="item-unconfirmed",
            candidate=replace(
                candidate("unconfirmed", case_eligible=False),
                standard_source="product_management_default_unconfirmed",
            ),
            execute=True,
            detect_enabled=True,
            case_create_enabled=True,
        )
        with pytest.raises(WfsCaseWriteError, match="WFS_CASE_EXECUTION_NOT_ENABLED"):
            create_wfs_case(
                session,
                item_id="item-detect-off",
                candidate=candidate("detect-off"),
                execute=True,
                detect_enabled=False,
                case_create_enabled=True,
            )
        with pytest.raises(WfsCaseWriteError, match="WFS_CASE_EXECUTION_NOT_ENABLED"):
            create_wfs_case(
                session,
                item_id="item-case-off",
                candidate=candidate("case-off"),
                execute=True,
                detect_enabled=True,
                case_create_enabled=False,
            )
        session.rollback()

    assert dry_run.action == "dry_run"
    assert incomplete.action == "review_required"
    assert unconfirmed.action == "review_required"
    with Session(engine) as session:
        assert (
            session.scalar(
                select(func.count())
                .select_from(WfsFeeAnomalyCase)
                .where(WfsFeeAnomalyCase.source_account_ref.like(f"{_ACCOUNT_PREFIX}%"))
            )
            == 0
        )
