"""Offline scheduler tests: eight selected stores, legacy mapping compatibility, fail-closed."""

import json
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from app.integrations.walmart.remote_dispatch import REMOTE_COLLECTION_STORES
from app.modules.walmart_remote.schedule import eligible_schedule, queue_due_stores


def test_twice_weekly_pacific_schedule():
    assert eligible_schedule(datetime(2026, 10, 28, 16, 0, tzinfo=UTC)) == "20261028"
    assert eligible_schedule(datetime(2026, 10, 31, 16, 0, tzinfo=UTC)) == "20261031"
    assert eligible_schedule(datetime(2026, 10, 29, 16, 0, tzinfo=UTC)) is None
    assert eligible_schedule(datetime(2026, 10, 28, 15, 0, tzinfo=UTC)) is None
    assert eligible_schedule(datetime(2026, 10, 28, 18, 0, tzinfo=UTC)) == "20261028"


@pytest.mark.parametrize("include_cn2502", [False, True])
def test_schedules_eight_only_with_eight_or_nine_store_identity_map(
    monkeypatch, include_cn2502
):
    stores = sorted(REMOTE_COLLECTION_STORES)
    mapping = {str(index): store for index, store in enumerate(stores, start=1)}
    if include_cn2502:
        mapping["99"] = "CN2502"
    routes = {
        store: {
            "ssh_host": "wmt-" + store.lower(),
            "worker_path": "/opt/szzsbj/walmart/run_worker.py",
        }
        for store in stores
    }
    monkeypatch.setenv("SZZSBJ_WALMART_REMOTE_COLLECTION_ENABLED", "1")
    monkeypatch.setenv("SZZSBJ_WALMART_REMOTE_SCHEDULE_ENABLED", "1")
    monkeypatch.setenv("SZZSBJ_WALMART_REMOTE_APPROVED_STORES", ",".join(stores))
    monkeypatch.setenv("SZZSBJ_WALMART_REMOTE_ROUTES", json.dumps(routes))
    monkeypatch.setenv("SZZSBJ_WALMART_SCF_STORE_ID_MAP", json.dumps(mapping))

    session = MagicMock()
    session.scalars.return_value.all.return_value = [
        SimpleNamespace(
            store_id=store_id,
            store_name=store + "-Walmart",
            source_account_ref="account-test",
        )
        for store_id, store in mapping.items()
        if store in REMOTE_COLLECTION_STORES
    ]
    session.scalar.return_value = None

    def assign_ids():
        for job in session.add_all.call_args.args[0]:
            job.id = uuid4()

    session.flush.side_effect = assign_ids
    ids = queue_due_stores(session, now=datetime(2026, 10, 28, 16, 0, tzinfo=UTC))
    jobs = session.add_all.call_args.args[0]
    assert len(ids) == len(stores)
    assert {job.store_code for job in jobs} == REMOTE_COLLECTION_STORES
    assert all("CN2502" not in job.request_key for job in jobs)


def test_does_not_schedule_with_missing_approved_store(monkeypatch):
    stores = sorted(REMOTE_COLLECTION_STORES)
    routes = {
        store: {
            "ssh_host": "wmt-" + store.lower(),
            "worker_path": "/opt/szzsbj/walmart/run_worker.py",
        }
        for store in stores
    }
    monkeypatch.setenv("SZZSBJ_WALMART_REMOTE_COLLECTION_ENABLED", "1")
    monkeypatch.setenv("SZZSBJ_WALMART_REMOTE_SCHEDULE_ENABLED", "1")
    monkeypatch.setenv("SZZSBJ_WALMART_REMOTE_APPROVED_STORES", "HK2613")
    monkeypatch.setenv("SZZSBJ_WALMART_REMOTE_ROUTES", json.dumps(routes))
    monkeypatch.setenv(
        "SZZSBJ_WALMART_SCF_STORE_ID_MAP",
        json.dumps({str(i): s for i, s in enumerate(stores, 1)}),
    )
    session = MagicMock()
    assert queue_due_stores(session, now=datetime(2026, 10, 28, 16, 0, tzinfo=UTC)) == []
    session.scalars.assert_not_called()


def test_missing_routes_do_not_raise_from_scheduler(monkeypatch):
    monkeypatch.setenv("SZZSBJ_WALMART_REMOTE_COLLECTION_ENABLED", "1")
    monkeypatch.setenv("SZZSBJ_WALMART_REMOTE_SCHEDULE_ENABLED", "1")
    monkeypatch.delenv("SZZSBJ_WALMART_REMOTE_ROUTES", raising=False)
    session = MagicMock()
    assert queue_due_stores(session, now=datetime(2026, 10, 28, 16, 0, tzinfo=UTC)) == []
    session.scalars.assert_not_called()
