"""Regression checks for SZZSBJ NP formalization, scope, pagination and security."""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace

import pytest
from sqlalchemy.engine import make_url


def test_manual_identity_applied_before_limit():
    from app.modules.new_products import unified_publish as u

    class Source:
        def scalars(self, stmt):
            self.sql = str(stmt.compile(compile_kwargs={"literal_binds": True}))
            return SimpleNamespace(
                all=lambda: [
                    SimpleNamespace(
                        source_account_ref="acc-a", store_id="store-a", item_id="123", id="id-a"
                    )
                ]
            )

    source = Source()
    rows = u._eligible_rows(source, {"123"}, limit=1, manual_identity=("acc-a", "store-a", "123"))
    assert rows[0]["key"] == ("acc-a", "store-a", "123")
    assert "source_account_ref = 'acc-a'" in source.sql
    assert "store_id = 'store-a'" in source.sql
    assert "item_id = '123'" in source.sql
    assert "LIMIT 2" in source.sql


def test_candidate_paging_does_not_raise_at_501():
    from app.modules.new_products import unified_publish as u

    class Source:
        def scalars(self, stmt):
            self.sql = str(stmt)
            return SimpleNamespace(
                all=lambda: [
                    SimpleNamespace(source_account_ref="a", store_id="s", item_id=f"{i:06}", id=i)
                    for i in range(501)
                ]
            )

    rows = u._eligible_rows(Source(), None, limit=500)
    assert len(rows) == 501  # The 501st entry is a has-more witness, not a failure.


def test_daily_job_paginates_all_828(monkeypatch):
    from app.db import session as dbsession
    from app.modules.new_products import read_source
    from app.modules.new_products import unified_publish as u

    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("SZZSBJ_PR337_UNIFIED_PUBLISH_ENABLED", "1")
    monkeypatch.setenv("SZZSBJ_PR337_UNIFIED_PRODUCTION_WRITE_APPROVED", "1")
    monkeypatch.setattr(dbsession, "get_engine", lambda: object())

    def source_generator():
        yield object()

    monkeypatch.setattr(read_source, "get_new_product_read_session", source_generator)

    class FakeSession:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def rollback(self):
            pass

    monkeypatch.setattr(u, "Session", FakeSession)
    calls = []

    def fake_publish(_source, _target, **kwargs):
        calls.append(kwargs.get("after"))
        if len(calls) == 1:
            return {
                "products": 500,
                "written": 500,
                "has_more": True,
                "next_after": ["a", "s", "000499"],
                "catalog_state": "VERIFIED_LABELS",
            }
        return {
            "products": 328,
            "written": 328,
            "has_more": False,
            "next_after": None,
            "catalog_state": "VERIFIED_LABELS",
        }

    monkeypatch.setattr(u, "publish_unified", fake_publish)
    result = u.execute_unified_job(limit=500, apply=True)
    assert result["products"] == 828
    assert result["written"] == 828
    assert result["pages"] == 2
    assert calls == [None, ("a", "s", "000499")]


def test_formal_candidates_scan_beyond_5000():
    from app.modules.new_products import evaluation_workflow as w

    regs = [
        SimpleNamespace(source_account_ref="a", store_id="s", item_id=f"{i:06}")
        for i in range(5001)
    ]
    pairs = [(r, SimpleNamespace()) for r in regs]

    class FakeSession:
        def __init__(self):
            self.calls = 0

        def execute(self, stmt):
            self.calls += 1
            pos = (self.calls - 1) * 500
            return SimpleNamespace(all=lambda: pairs[pos : pos + 500])

    got = list(w._iter_formal_candidates(FakeSession()))
    assert len(got) == 5001
    assert got[-1][0].item_id == "005000"


def test_local_production_tunnel_bypass_removed(monkeypatch):
    from app.db import session as dbsession
    from app.modules.new_products import unified_publish as u

    monkeypatch.setenv("APP_ENV", "local")
    monkeypatch.setenv("SZZSBJ_PR337_UNIFIED_PUBLISH_ENABLED", "1")
    monkeypatch.setenv("SZZSBJ_NP_MANUAL_SERVER_WRITE_APPROVED", "1")
    monkeypatch.setattr(
        dbsession,
        "get_engine",
        lambda: SimpleNamespace(
            url=make_url("postgresql+psycopg://u:p@127.0.0.1:15437/szzsbj_app")
        ),
    )
    with pytest.raises(PermissionError, match="PR337_WRITE_TARGET_NOT_LOCAL_DEV_OR_HYBRID"):
        u.execute_unified_job(
            item_ids={"123"}, limit=1, apply=True, auto_only=True, manual_identity=("a", "s", "123")
        )


def test_manual_completion_only_after_persisted_formal_trigger(monkeypatch):
    from app.modules.new_products import evaluation_workflow as w
    from app.modules.new_products import unified_publish as u

    monkeypatch.setattr(w, "_cutoff", lambda: date(2026, 11, 17))
    registry = SimpleNamespace(
        id="registry-id", source_account_ref="acc", store_id="store", item_id="123"
    )
    perf = SimpleNamespace(
        grade=None,
        score=None,
        first_wfs_available_date_la=date(2026, 11, 1),
        sold_out_evidence_status=None,
        first_batch_sold_out_date_la=None,
        data_coverage_json={
            "auto_dimension_scores": {
                "dimensions": {
                    "speed": "5",
                    "ad": "5",
                    "profit": "5",
                    "trust": "5",
                }
            },
            "new_products_score_facts_v2": {"ad_status": "active"},
        },
    )
    monkeypatch.setattr(w, "_registry", lambda *args, **kwargs: registry)
    monkeypatch.setattr(w, "_performance", lambda *args, **kwargs: perf)
    monkeypatch.setattr(w, "_protected", lambda *args, **kwargs: False)
    monkeypatch.setattr(w, "_verified_proof", lambda *_: {"proof": "verified"})
    monkeypatch.setattr(w, "_config", lambda *_: ({}, 1))
    monkeypatch.setattr(w, "_ready", lambda *_: (True, []))
    monkeypatch.setattr(w, "ActionEvent", lambda **kwargs: kwargs)
    monkeypatch.setattr(u, "execute_unified_job", lambda **kwargs: {"written": 1, "reconciled": 0})

    def fake_finalize(*args, **kwargs):
        # First invocation: complete evidence but no persisted trigger.
        return {"published": 0}

    monkeypatch.setattr(w, "finalize_automatic", fake_finalize)

    class Session:
        def __init__(self):
            self.events = []

        def rollback(self):
            pass

        def expire_all(self):
            pass

        def add(self, event):
            self.events.append(event)

        def commit(self):
            pass

    db = Session()
    listing = SimpleNamespace(first_wfs_available_date_la=date(2026, 11, 1))
    result = w.calculate_once(db, "acc", "store", "123", "actor", listing)
    assert result["status"] == "incomplete"
    assert result["missing"]

    def successful_finalize(*args, **kwargs):
        proof = w._verified_proof(perf)
        perf.data_coverage_json = {
            **perf.data_coverage_json,
            "evaluation_formal_trigger": {"status": "completed", "proof_hash": w._sha(proof)},
        }
        return {"published": 1}

    monkeypatch.setattr(w, "finalize_automatic", successful_finalize)
    result = w.calculate_once(db, "acc", "store", "123", "actor", listing)
    assert result["status"] == "completed"
    assert not result["missing"]


def test_before_fourteen_days_manual_does_not_claim_formal(monkeypatch):
    from app.modules.new_products import evaluation_workflow as w
    from app.modules.new_products import unified_publish as u

    monkeypatch.setattr(w, "_cutoff", lambda: date(2026, 11, 5))
    registry = SimpleNamespace(
        id="registry-id", source_account_ref="a", store_id="s", item_id="123"
    )
    perf = SimpleNamespace(
        grade=None,
        score=None,
        first_wfs_available_date_la=date(2026, 11, 1),
        sold_out_evidence_status=None,
        first_batch_sold_out_date_la=None,
        data_coverage_json={
            "auto_dimension_scores": {
                "dimensions": {
                    "speed": "4",
                    "ad": "4",
                    "profit": "4",
                    "trust": "4",
                }
            },
            "new_products_score_facts_v2": {"ad_status": "active"},
        },
    )
    monkeypatch.setattr(w, "_registry", lambda *args, **kwargs: registry)
    monkeypatch.setattr(w, "_performance", lambda *args, **kwargs: perf)
    monkeypatch.setattr(w, "_protected", lambda *args, **kwargs: False)
    monkeypatch.setattr(w, "ActionEvent", lambda **kwargs: kwargs)
    monkeypatch.setattr(u, "execute_unified_job", lambda **kwargs: {"written": 1})
    monkeypatch.setattr(
        w, "finalize_automatic", lambda *_a, **_k: pytest.fail("must not finalize early")
    )

    class Session:
        def rollback(self):
            pass

        def expire_all(self):
            pass

        def add(self, obj):
            pass

        def commit(self):
            pass

    result = w.calculate_once(
        Session(),
        "a",
        "s",
        "123",
        "actor",
        SimpleNamespace(first_wfs_available_date_la=date(2026, 11, 1)),
    )
    assert result["status"] == "incomplete"
    assert any("14天" in item for item in result["missing"])
