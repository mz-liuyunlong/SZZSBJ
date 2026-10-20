from datetime import date
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.modules.warehouse_wfs import auto_detection_runner as runner
from app.modules.warehouse_wfs.store_discovery import WfsSettlementStore


def store(number):
    return WfsSettlementStore(
        source_account_ref="primary",
        store_id=str(number),
        store_name=f"Store {number}",
        sid="",
    )


def fake_result(anomalies=1):
    detection = SimpleNamespace(
        anomalies=anomalies,
        missing_standard=0,
    )
    return SimpleNamespace(
        collected_pages=2,
        collected_rows=30,
        unresolved_listings=0,
        result=SimpleNamespace(detection=detection),
    )


def make_session():
    session = MagicMock()
    session.__enter__.return_value = session
    return session


def test_all_stores_succeed(monkeypatch):
    monkeypatch.setattr(
        runner,
        "run_wfs_read_only_detection",
        lambda *args, **kwargs: fake_result(),
    )
    summary = runner.run_wfs_batch_read_only(
        session_factory=make_session,
        fetch_page=lambda *_: {},
        stores=(store(1), store(2)),
        detection_date=date(2026, 10, 19),
    )
    assert summary.stores_succeeded == 2
    assert summary.stores_failed == 0
    assert summary.anomalies == 2


def test_one_store_failure_isolated(monkeypatch):
    def detect(_session, *, store, **kwargs):
        if store.store_id == "1":
            raise RuntimeError("provider unavailable")
        return fake_result(2)

    monkeypatch.setattr(runner, "run_wfs_read_only_detection", detect)
    summary = runner.run_wfs_batch_read_only(
        session_factory=make_session,
        fetch_page=lambda *_: {},
        stores=(store(1), store(2)),
        detection_date=date(2026, 10, 19),
    )
    assert summary.stores_failed == 1
    assert summary.stores_succeeded == 1
    assert summary.anomalies == 2
    assert summary.stores[0].anomalies == 0
    assert summary.stores[0].status == "failed"


def test_request_cap(monkeypatch):
    def detect(_session, *, fetch_page, **kwargs):
        fetch_page("interface", {})
        fetch_page("interface", {})
        return fake_result()

    monkeypatch.setattr(runner, "run_wfs_read_only_detection", detect)
    summary = runner.run_wfs_batch_read_only(
        session_factory=make_session,
        fetch_page=lambda *_: {},
        stores=(store(1),),
        detection_date=date(2026, 10, 19),
        max_pages_per_store=1,
    )
    assert summary.stores_failed == 1
    assert summary.anomalies == 0


def test_duplicate_stores_rejected():
    with pytest.raises(ValueError):
        runner.run_wfs_batch_read_only(
            session_factory=make_session,
            fetch_page=lambda *_: {},
            stores=(store(1), store(1)),
            detection_date=date(2026, 10, 19),
        )


def test_store_limit_rejected():
    with pytest.raises(ValueError):
        runner.run_wfs_batch_read_only(
            session_factory=make_session,
            fetch_page=lambda *_: {},
            stores=(store(1), store(2)),
            detection_date=date(2026, 10, 19),
            max_stores=1,
        )
