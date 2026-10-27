"""Regression coverage for refund retry date recovery on PostgreSQL.

This query previously emitted SELECT DISTINCT ... ORDER BY two separately bound
JSON keys, rejected by PostgreSQL even when both keys are "business_date".
"""
from datetime import date
from unittest.mock import Mock
from uuid import uuid4

from sqlalchemy.dialects import postgresql

from app.modules.integration_sync.repository import IntegrationSyncRepository


def test_refund_retry_dates_are_sorted_and_deduplicated() -> None:
    session = Mock()
    session.scalars.return_value.all.return_value = [
        "2026-10-25",
        "2026-10-21",
        "2026-10-25",
        None,
        "2026-10-22",
    ]
    source_run_id = uuid4()

    result = IntegrationSyncRepository(session).refund_capture_business_dates(
        source_run_id, "account-a"
    )

    assert result == (date(2026, 10, 21), date(2026, 10, 22), date(2026, 10, 25))
    statement = session.scalars.call_args.args[0]
    compiled = statement.compile(dialect=postgresql.dialect())
    sql = str(compiled).upper()
    assert "SELECT DISTINCT" not in sql
    assert "ORDER BY" not in sql
    assert "GOV_INTEGRATION_SYNC_RUN_EVENTS" in sql
    assert "GOV_INTEGRATION_SYNC_RUNS" in sql
    assert "SOURCE_ACCOUNT_REF" in sql
    assert "INTERFACE_KEY" in sql
    assert "MESSAGE_CODE" in sql
    parameters = tuple(compiled.params.values())
    assert source_run_id in parameters
    assert "account-a" in parameters
    assert "walmartReturnOrderList" in parameters
    assert "SYNC_REFUND_FACTS_COMMITTED" in parameters


def test_refund_retry_dates_are_empty_when_capture_events_absent() -> None:
    session = Mock()
    session.scalars.return_value.all.return_value = []

    result = IntegrationSyncRepository(session).refund_capture_business_dates(
        uuid4(), "account-a"
    )

    assert result == ()


def test_refund_retry_uses_requested_account_scope() -> None:
    session = Mock()
    session.scalars.return_value.all.return_value = ["2026-10-25"]

    IntegrationSyncRepository(session).refund_capture_business_dates(
        uuid4(), "account-b"
    )

    statement = session.scalars.call_args.args[0]
    compiled = statement.compile(dialect=postgresql.dialect())
    assert "account-b" in tuple(compiled.params.values())
    assert "account-a" not in tuple(compiled.params.values())
