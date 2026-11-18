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
    "dimensions, outcome, expected",
    [
        ({"speed": "2", "ad": "3", "profit": "4", "trust": "5"}, {"reconciled": 1}, "incomplete"),
        ({"speed": "2", "ad": None, "profit": "4", "trust": "5"}, {"reconciled": 1}, "incomplete"),
    ],
)
def test_single_item_manual_uses_unified_v2_without_formal_grade(
    monkeypatch, dimensions, outcome, expected
):
    from app.modules.new_products import evaluation_workflow as wf
    from app.modules.new_products import unified_publish

    requested = []

    def fake_job(*, item_ids, limit, apply, auto_only, manual_identity):
        assert manual_identity == ("acc", "store", "item")
        requested.append((item_ids, limit, apply, auto_only))
        return outcome

    monkeypatch.setattr(unified_publish, "execute_unified_job", fake_job)
    monkeypatch.setattr(wf, "_cutoff", lambda: date(2026, 11, 14))
    reg = SimpleNamespace(id="id")
    perf = SimpleNamespace(
        grade=None,
        score=None,
        first_wfs_available_date_la=date(2026, 11, 3),
        sold_out_evidence_status=None,
        first_batch_sold_out_date_la=None,
        data_coverage_json={
            "auto_dimension_scores": {"dimensions": dimensions, "missing": []},
            "new_products_score_facts_v2": {"ad_status": "active"},
        },
    )
    monkeypatch.setattr(wf, "_registry", lambda *args, **kwargs: reg)
    monkeypatch.setattr(wf, "_performance", lambda *args, **kwargs: perf)
    monkeypatch.setattr(wf, "_protected", lambda *args, **kwargs: False)
    monkeypatch.setattr(wf, "ActionEvent", lambda **kwargs: kwargs)

    class Session:
        events = []

        def rollback(self):
            pass

        def expire_all(self):
            pass

        def add(self, event):
            self.events.append(event)

        def commit(self):
            pass

    listing = SimpleNamespace(first_wfs_available_date_la=date(2026, 11, 3))
    got = wf.calculate_once(Session(), "acc", "store", "item", "operator", listing)
    assert requested == [({"item"}, 1, True, True)]
    assert got["status"] == expected
    assert got["trigger"] == "manual_auto_only"
    assert got["item_id"] == "item"
    assert not hasattr(perf, "process_status")
