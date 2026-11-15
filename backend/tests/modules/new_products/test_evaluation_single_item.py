"""Contract tests: calculate one scoped Item ID, without new job infrastructure."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pytest


def test_no_task_table_or_new_celery_request():
    root = Path(__file__).resolve().parents[3]
    workflow = (root / "app/modules/new_products/evaluation_workflow.py").read_text()
    assert "biz_new_product_evaluation_jobs" not in workflow
    assert "send_task(" not in workflow
    assert "def calculate_once(" in workflow


@pytest.mark.parametrize(
    "outcomes, expected",
    [
        ({"written": 1}, "completed"),
        ({"STORE_MART_WATERMARK_PENDING": 1}, "incomplete"),
    ],
)
def test_single_item_calculation_scoped_and_fail_closed(monkeypatch, outcomes, expected):
    from app.modules.new_products import evaluation_workflow as wf
    from app.modules.new_products import pr337_daily_db as daily

    requested = []

    def fake_run_daily(session, *, apply, cutoff_la, identity_filter):
        requested.append((apply, cutoff_la, identity_filter))
        return {"status": "applied", "outcomes": outcomes}

    monkeypatch.setattr(daily, "run_daily", fake_run_daily)
    monkeypatch.setattr(wf, "_cutoff", lambda: date(2026, 11, 10))
    monkeypatch.setattr(wf, "_lock", lambda *_: None)
    registry = SimpleNamespace(
        id="registry-id", source_account_ref="acc", store_id="store", item_id="item"
    )
    performance = SimpleNamespace(grade=None, score=None, data_coverage_json={})
    monkeypatch.setattr(wf, "_registry", lambda *args, **kwargs: registry)
    monkeypatch.setattr(wf, "_performance", lambda *args, **kwargs: performance)
    monkeypatch.setattr(wf, "_protected", lambda *args, **kwargs: False)
    monkeypatch.setattr(wf, "_verified_proof", lambda *_: {"orders": 1})
    monkeypatch.setattr(wf, "_config", lambda *_: ({}, 0))
    monkeypatch.setattr(wf, "_ready", lambda *_: (True, []))
    completed = []
    monkeypatch.setattr(wf, "_set_formal", lambda *args, **kwargs: completed.append(True) or True)
    monkeypatch.setattr(wf, "ActionEvent", lambda **kwargs: kwargs)

    class Session:
        def __init__(self):
            self.events = []
            self.commits = 0
            self.expired = False

        def expire_all(self):
            self.expired = True

        def scalar(self, *args, **kwargs):
            return None

        def add(self, x):
            self.events.append(x)

        def commit(self):
            self.commits += 1

    db = Session()
    listing = SimpleNamespace(first_wfs_available_date_la=date(2026, 11, 3))
    out = wf.calculate_once(db, "acc", "store", "item", "operator", listing)
    assert requested == [(True, date(2026, 11, 10), ("acc", "store", "item"))]
    assert out["status"] == expected
    assert out["item_id"] == "item"
    assert bool(completed) == (expected == "completed")
    assert db.expired and db.commits == 1
    assert len(db.events) == 1
