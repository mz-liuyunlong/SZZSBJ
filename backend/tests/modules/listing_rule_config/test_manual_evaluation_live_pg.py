"""Opt-in manual diagnostic audit test against disposable PostgreSQL."""

import os
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import Request
from sqlalchemy import create_engine, select
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from app.core.auth import Principal
from app.modules.data_pages.models import ListingManagementCurrentMart
from app.modules.listing_rule_config import preview_router, tasks
from app.modules.listing_rule_config.models import (
    ListingEvaluationManualRequest,
    ListingEvaluationRun,
)

pytestmark = pytest.mark.skipif(
    not os.getenv("LISTING_LIVE_TEST_DATABASE_URL"),
    reason="Requires a disposable PostgreSQL database migrated to current head",
)


def test_manual_request_runs_only_for_unchanged_global_scope(monkeypatch) -> None:
    url = make_url(os.environ["LISTING_LIVE_TEST_DATABASE_URL"])
    assert os.getenv("APP_ENV") == "test"
    assert url.database and url.database.startswith("pr277_listing_")
    assert url.query.get("host", "").startswith("/tmp/szzsbj-pr277-pg.")
    engine = create_engine(url)

    def enabled():
        return SimpleNamespace(listing_evaluation_manual_enabled=True)

    monkeypatch.setattr(preview_router, "get_settings", enabled)
    monkeypatch.setattr(tasks, "get_settings", enabled)
    monkeypatch.setattr(tasks, "get_engine", lambda: engine)
    monkeypatch.setattr(preview_router.manual_diagnostic, "apply_async", lambda **_kw: None)

    def diagnostic(self, *, schedule_date_cn, cutoff_date_la, **_kwargs):
        run = ListingEvaluationRun(
            schedule_date_cn=schedule_date_cn,
            cutoff_date_la=cutoff_date_la,
            status="succeeded",
            rule_version=1,
            attempt_count=uuid4().int % 1_000_000_000,
        )
        self.session.add(run)
        self.session.commit()
        return run.id

    monkeypatch.setattr(tasks.ListingEvaluationBatchService, "run_daily_diagnostic", diagnostic)
    request_id = None
    try:
        with Session(engine) as session:
            accounts = frozenset(
                session.scalars(
                    select(ListingManagementCurrentMart.source_account_ref).distinct()
                ).all()
            )
            assert accounts
            result = preview_router.request_manual_evaluation(
                request=Request(
                    {
                        "type": "http",
                        "method": "POST",
                        "path": "/api/listings/evaluation-runs/manual",
                        "headers": [],
                    }
                ),
                _payload=preview_router.ManualEvaluationRequest(
                    confirmation="CONFIRM_LISTING_CALCULATE_ALL"
                ),
                session=session,
                account_refs=accounts,
                principal=Principal(user_id=f"synthetic-{uuid4()}"),
            )
            request_id = result.data.id
            assert result.data.status == "queued"
        tasks.manual_diagnostic.run(str(request_id))
        with Session(engine) as session:
            stored = session.get(ListingEvaluationManualRequest, request_id)
            assert stored is not None
            assert stored.status == "succeeded"
            assert stored.run_id is not None
            assert session.get(ListingEvaluationRun, stored.run_id).status == "succeeded"
            assert stored.finished_at <= datetime.now(UTC)
        monkeypatch.setattr(tasks, "rule_is_due", lambda *_args: True)
        monkeypatch.setattr(
            tasks,
            "get_settings",
            lambda: SimpleNamespace(
                listing_evaluation_scheduler_enabled=True,
                listing_evaluation_publish_enabled=True,
            ),
        )
        monkeypatch.setattr(
            tasks.ListingEvaluationPublisher,
            "publish_run",
            lambda *_args, **_kwargs: (_ for _ in ()).throw(
                AssertionError("manual diagnostic must never publish on a later beat tick")
            ),
        )
        tasks.scheduler_tick.run()
    finally:
        if request_id is not None:
            with Session(engine) as session:
                stored = session.get(ListingEvaluationManualRequest, request_id)
                if stored is not None:
                    run_id = stored.run_id
                    session.delete(stored)
                    session.flush()
                    if run_id is not None:
                        session.delete(session.get(ListingEvaluationRun, run_id))
                    session.commit()
        engine.dispose()
