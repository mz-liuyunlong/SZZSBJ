from datetime import UTC, datetime
from unittest.mock import MagicMock
from uuid import uuid4

from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Session

from app.modules.integration_sync.repository import IntegrationSyncRepository


def _sql(statement: object) -> str:
    return str(
        statement.compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )


def test_dashboard_queries_latest_and_today_counts_with_scope() -> None:
    session = MagicMock(spec=Session)
    session.scalars.return_value.all.return_value = []
    session.execute.return_value.all.return_value = []
    repo = IntegrationSyncRepository(session)

    latest, counts = repo.task_dashboard(
        frozenset({"synthetic-scope"}),
        datetime(2026, 10, 26, tzinfo=UTC),
        datetime(2026, 10, 27, tzinfo=UTC),
    )

    assert latest == []
    assert counts == []
    latest_sql = _sql(session.scalars.call_args.args[0])
    count_sql = _sql(session.execute.call_args.args[0])
    assert "synthetic-scope" in latest_sql
    assert "synthetic-scope" in count_sql
    assert "row_number" in latest_sql.lower()
    assert "coalesce" in count_sql.lower()


def test_pending_refund_mart_query_is_account_scoped() -> None:
    session = MagicMock(spec=Session)
    run_id = uuid4()
    session.execute.return_value.all.return_value = [
        ("synthetic-scope", "2026-08-04", run_id)
    ]
    repo = IntegrationSyncRepository(session)

    result = repo.refund_mart_pending_days(frozenset({"synthetic-scope"}))

    assert result == [("synthetic-scope", "2026-08-04", run_id)]
    sql = _sql(session.execute.call_args.args[0])
    assert "synthetic-scope" in sql
    assert "SYNC_REFUND_MART_PENDING" in sql
    assert "SYNC_REFUND_MART_VALIDATED" in sql
