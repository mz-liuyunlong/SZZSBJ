"""Failed assessment page and approval guards; no real database or external API."""

import json
import sys
from contextlib import contextmanager
from copy import deepcopy
from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.core.api import ApiError
from app.modules.new_products import evaluation_workflow as wf
from app.modules.new_products import risk_display
from app.modules.new_products.evaluation_policy import evaluation_status
from app.modules.new_products.service import NewProductService


@pytest.mark.parametrize(
    "grade,blocked,allowed",
    [
        ("A", False, True),
        ("B", False, True),
        ("C", False, True),
        ("S", False, True),
        ("D", False, False),
        ("Pass", False, False),
        ("A", True, False),
    ],
)
def test_manual_conclusion_respects_frozen_grade_and_risk(grade, blocked, allowed):
    coverage = {
        "evaluation_final_snapshot": {"risk_evaluation": {"recommend_not_pass": blocked}},
        "evaluation_grade_confirmation_v1": {"status": "confirmed"},
    }
    perf = SimpleNamespace(grade=grade)
    if allowed:
        wf._validate_review_pass(perf, coverage, "passed")
    else:
        with pytest.raises(ApiError) as ex:
            wf._validate_review_pass(perf, coverage, "passed")
        assert ex.value.code == "NP_ASSESSMENT_REVIEW_GRADE_BLOCKED"


def test_pending_grade_cannot_be_changed_to_pass():
    with pytest.raises(ApiError) as ex:
        wf._validate_review_pass(
            SimpleNamespace(grade="A"),
            {"evaluation_grade_confirmation_v1": {"status": "pending"}},
            "passed",
        )
    assert ex.value.code == "NP_ASSESSMENT_GRADE_UNCONFIRMED"


class Result:
    def __init__(self, rows):
        self.rows = rows

    def mappings(self):
        return self

    def all(self):
        return self.rows

    def first(self):
        return self.rows[0] if self.rows else None


def test_page_reuses_one_bounded_review_lookup(monkeypatch):
    monkeypatch.setattr(NewProductService, "_config", lambda self: ({}, 1))
    monkeypatch.setattr(risk_display, "build_saved_risk_display", lambda *a, **kw: {"rules": []})
    records, entries = [], []
    for i, (grade, blocked, decision, expected) in enumerate(
        [
            ("B", False, "failed", "manual_decision"),
            ("D", False, "failed", "grade_limit"),
            ("Pass", True, "failed", "risk_limit"),
            ("A", False, "passed", None),
        ]
    ):
        a, store, item = "acct", "store", str(i)
        records.append(
            {
                "a": a,
                "s": store,
                "i": item,
                "registry_id": str(uuid4()),
                "grade": grade,
                "score": Decimal("7.50"),
                "first_wfs_available_date_la": date(2026, 11, 1),
                "first_batch_sold_out_date_la": None,
                "sold_out_evidence_status": None,
                "listing_date_la": None,
                "frozen_suggested_qty": None,
                "review_status": "rejected" if expected else None,
                "review_id": "review" if expected else None,
                "review_request_reason": "复核申请真实说明" if expected else None,
                "review_decision_reason": "审批真实原因" if expected else None,
                "review_reason_type": "manual_decision_change" if expected else None,
                "data_coverage_json": {
                    "operator_assessment_v1": {
                        "decision": decision,
                        "reason": "原测评理由",
                        "confirmed_at": "2026-11-20T00:00:00+00:00",
                    },
                    "evaluation_grade_confirmation_v1": {"status": "confirmed"},
                    "evaluation_final_snapshot": {
                        "grade": grade,
                        "total": "7.50",
                        "risk_evaluation": {"recommend_not_pass": blocked},
                    },
                },
            }
        )
        entries.append(
            {
                "listing": {"source_account_ref": a, "store_id": store, "item_id": item},
                "evaluation": {},
                "facts": {},
            }
        )

    class Session:
        def __init__(self):
            self.calls = []

        def execute(self, stmt, params):
            self.calls.append((str(stmt), params))
            return Result(records)

    db = Session()
    result = wf.decorate_page(db, {"items": entries})["items"]
    assert len(db.calls) == 1
    sql, params = db.calls[0]
    assert sql.count("FROM app_approval_requests") == 1
    assert "LEFT JOIN LATERAL" in sql and "a.source_account_ref=w.a" in sql
    assert len(json.loads(params["wants"])) == 4
    for row, kind in zip(
        result, [("manual_decision"), "grade_limit", "risk_limit", None], strict=True
    ):
        if kind:
            info = row["failed_assessment_info"]
            assert info["reason_kind"] == kind
            assert info["review_decision_reason"] == "审批真实原因"
            assert row["evaluation_decision"]["reason"] == "原测评理由"
            assert info["manual_pass_allowed"] == (kind == "manual_decision")
        else:
            assert "failed_assessment_info" not in row


def test_data_review_can_be_requested_for_failed_b_grade(monkeypatch):
    reg = SimpleNamespace(id=uuid4())
    perf = SimpleNamespace(
        grade="B",
        score=Decimal("7.2"),
        rule_version_id=None,
        calculated_at=None,
        first_wfs_available_date_la=date(2026, 11, 1),
        data_coverage_json={"operator_assessment_v1": {"decision": "failed", "reason": "人工判断"}},
    )
    monkeypatch.setattr(wf, "_lock", lambda *a: None)
    monkeypatch.setattr(wf, "_registry", lambda *a, **kw: reg)
    monkeypatch.setattr(wf, "_performance", lambda *a, **kw: perf)
    monkeypatch.setattr(wf, "_protected", lambda *a: False)
    monkeypatch.setattr(wf, "ActionEvent", lambda **kw: kw)

    class Session:
        def __init__(self):
            self.writes = []
            self.commits = 0

        def scalar(self, *a, **kw):
            return None

        def execute(self, stmt, params):
            self.writes.append((str(stmt), params))

        def add(self, obj):
            self.writes.append(obj)

        def commit(self):
            self.commits += 1

    db = Session()
    response = wf.submit_review(
        db,
        {"acct"},
        "acct",
        "store",
        "item",
        "actor",
        "calculation_error",
        "真实评分数据需要纠错",
        "",
    )
    assert response["status"] == "submitted" and db.commits == 1
    assert perf.data_coverage_json["operator_assessment_v1"]["decision"] == "failed"
    assert perf.grade == "B"
    assert any(
        "INSERT INTO app_approval_requests" in x[0] for x in db.writes if isinstance(x, tuple)
    )


def test_formal_recheck_archives_then_reopens_and_rolls_back_on_failure(monkeypatch):
    from app.modules.new_products import unified_publish

    key = ("acct", "store", "item")
    first = date(2026, 11, 1)
    cutoff = date(2026, 11, 15)
    approval_id = uuid4()
    original = {
        "operator_assessment_v1": {"decision": "failed", "reason": "原人工结论", "revision": 1},
        "evaluation_final_snapshot": {
            "grade": "B",
            "total": "7.2",
            "risk_evaluation": {"manual_selected": ["无"]},
        },
        "evaluation_grade_confirmation_v1": {"status": "confirmed"},
        "evaluation_recheck_required": {
            "approval_id": str(approval_id),
            "status": "awaiting_verified_source_correction",
        },
        "operator_score_correction_v1": {"revision": 2},
        "evaluation_operating_archive_v1": {"daily": {"rows": [1]}},
    }
    perf = SimpleNamespace(
        grade="B",
        score=Decimal("7.2"),
        process_status="assessment_complete",
        first_wfs_available_date_la=first,
        data_coverage_json=deepcopy(original),
    )
    reg = SimpleNamespace(
        source_account_ref=key[0], store_id=key[1], item_id=key[2], is_currently_tagged=True
    )
    old_proof = {"authority_cutoff_la": str(cutoff), "facts": {"elapsed_days": 16, "paid": 5}}
    new_proof = {"authority_cutoff_la": str(cutoff), "facts": {"elapsed_days": 16, "paid": 6}}
    monkeypatch.setattr(
        wf,
        "_verified_proof",
        lambda p: old_proof if p.data_coverage_json.get("operator_assessment_v1") else new_proof,
    )
    monkeypatch.setattr(wf, "_cutoff", lambda: date(2026, 11, 25))
    monkeypatch.setattr(wf, "_config", lambda s: ({}, 1))
    monkeypatch.setattr(
        wf, "evaluate", lambda *args: {"grade": "A", "total": "8.2", "dimensions": {}}
    )
    monkeypatch.setattr(NewProductService, "_listing", lambda *a, **kw: object())
    monkeypatch.setattr(wf, "ActionEvent", lambda **kw: kw)
    monkeypatch.setitem(
        sys.modules,
        "app.modules.new_products.pr337_daily_pipeline",
        SimpleNamespace(load_scoped_campaign_catalog=lambda *a: ({}, "complete", 0)),
    )

    def candidate(source, db, keys, cut):
        assert keys == [key] and cut == cutoff
        return {
            key: {
                "facts": {"first_wfs_available_date_la": first, "elapsed_days": 25},
                "rule_version": 1,
                "evaluation": {},
            }
        }

    monkeypatch.setattr(unified_publish, "_candidate_scores", candidate)
    monkeypatch.setattr(
        unified_publish, "load_ad_snapshots", lambda *a, **kw: {key: {"status": "complete"}}
    )

    def save_one(db, identity, ads, score, **kw):
        assert identity == key and kw["auto_only"] and kw["cutoff"] == cutoff
        assert score["facts"]["elapsed_days"] == 16
        assert perf.grade is None and "operator_assessment_v1" not in perf.data_coverage_json
        return "reconciled"

    monkeypatch.setattr(unified_publish, "_save_one", save_one)

    class Session:
        def __init__(self):
            self.commits = 0
            self.rollbacks = 0
            self.events = []

        def scalar(self, *a, **kw):
            return SimpleNamespace(score=7, version=1)

        def flush(self):
            pass

        @contextmanager
        def begin_nested(self):
            old = deepcopy(perf.__dict__)
            try:
                yield
            except Exception:
                perf.__dict__.clear()
                perf.__dict__.update(old)
                raise

        def rollback(self):
            self.rollbacks += 1

        def commit(self):
            self.commits += 1

        def execute(self, *a, **kw):
            pass

        def add(self, obj):
            self.events.append(obj)

    def publish_fail(*a, **kw):
        raise ApiError(code="RISK_UNVERIFIED", status_code=409, message="risk proof incomplete")

    monkeypatch.setattr(wf, "publish_after_market", publish_fail)
    db = Session()
    approval = {"id": approval_id}
    with pytest.raises(ApiError):
        wf._recheck_formal_v2(db, object(), {"acct"}, approval, reg, perf, "actor")
    assert (
        perf.grade == "B"
        and perf.data_coverage_json == original
        and db.commits == 0
        and db.rollbacks == 1
    )

    def publish_ok(*a, **kw):
        assert kw["risk_conditions"] == ["无"]
        perf.grade = "A"
        perf.score = Decimal("8.2")
        perf.data_coverage_json = {
            **perf.data_coverage_json,
            "evaluation_final_snapshot": {
                "grade": "A",
                "total": "8.2",
                "risk_evaluation": {"manual_selected": ["无"]},
            },
            "evaluation_grade_confirmation_v1": {"status": "pending"},
        }
        return {"grade": "A"}

    monkeypatch.setattr(wf, "publish_after_market", publish_ok)
    result = wf._recheck_formal_v2(db, object(), {"acct"}, approval, reg, perf, "actor")
    assert result["next_status"] == "待等级确认" and db.commits == 1
    cov = perf.data_coverage_json
    assert cov["evaluation_recheck_history_v2"][0]["coverage"] == original
    assert cov["operator_assessment_history_v1"][-1] == original["operator_assessment_v1"]
    assert (
        "operator_assessment_v1" not in cov
        and "operator_score_correction_v1" not in cov
        and "evaluation_operating_archive_v1" not in cov
    )
    assert cov["evaluation_recheck_required"]["status"] == "completed"
    assert (
        evaluation_status(
            listing_date=first, first_wfs=first, coverage=cov, grade=perf.grade, total=perf.score
        )
        == "待等级确认"
    )


@pytest.mark.parametrize(
    "grade,actor,decision,expect_error",
    [
        ("B", "leader", "approved", None),
        ("B", "leader", "rejected", None),
        ("D", "leader", "approved", "NP_ASSESSMENT_REVIEW_GRADE_BLOCKED"),
        ("B", "operator", "approved", "NP_EVAL_SELF_REVIEW"),
    ],
)
def test_manual_review_approval_only_updates_verdict(
    monkeypatch, grade, actor, decision, expect_error
):
    reg = SimpleNamespace(id=uuid4(), source_account_ref="acct", store_id="store", item_id="item")
    previous = {"decision": "failed", "reason": "原原因", "revision": 1}
    final = {"grade": grade, "total": "7.2", "risk_evaluation": {"recommend_not_pass": False}}
    coverage = {
        "operator_assessment_v1": deepcopy(previous),
        "evaluation_final_snapshot": deepcopy(final),
        "evaluation_grade_confirmation_v1": {"status": "confirmed"},
    }
    perf = SimpleNamespace(grade=grade, score=Decimal("7.2"), data_coverage_json=deepcopy(coverage))
    approval = {
        "source_account_ref": "acct",
        "business_ref": str(reg.id),
        "applicant_id": "operator",
        "status": "submitted",
        "version": 1,
        "reason": "人工复核有充分证据支持重新考虑产品",
        "snapshot": {
            "grade": grade,
            "score": "7.2",
            "proof_hash": wf._sha(coverage),
            "review_reason_type": "manual_decision_change",
            "operator_decision_before": deepcopy(previous),
            "operator_decision_requested": "passed",
        },
    }
    monkeypatch.setattr(wf, "_performance", lambda *a, **kw: perf)
    monkeypatch.setattr(wf, "_protected", lambda *a: False)
    monkeypatch.setattr(wf, "ActionEvent", lambda **kw: kw)

    class Session:
        def __init__(self):
            self.commits = 0
            self.writes = []

        def scalar(self, *a, **kw):
            return reg

        def execute(self, stmt, params):
            if str(stmt).lstrip().startswith("SELECT * FROM app_approval_requests"):
                return Result([approval])
            self.writes.append(str(stmt))
            return SimpleNamespace(rowcount=1)

        def add(self, obj):
            self.writes.append(obj)

        def commit(self):
            self.commits += 1

    db = Session()
    if expect_error:
        with pytest.raises(ApiError) as exc:
            wf.decide_review(db, {"acct"}, uuid4(), actor, decision, "认真核验审批原因", 1)
        assert exc.value.code == expect_error and not db.writes and db.commits == 0
    else:
        result = wf.decide_review(db, {"acct"}, uuid4(), actor, decision, "认真核验审批原因", 1)
        assert result["status"] == decision and db.commits == 1
        assert (
            perf.grade == grade
            and perf.score == Decimal("7.2")
            and perf.data_coverage_json["evaluation_final_snapshot"] == final
        )
        if decision == "approved":
            assert perf.data_coverage_json["operator_assessment_v1"]["decision"] == "passed"
            assert perf.data_coverage_json["operator_assessment_history_v1"] == [previous]
        else:
            assert perf.data_coverage_json == coverage
        assert all(
            "biz_new_product_purchase_applications" not in x
            for x in db.writes
            if isinstance(x, str)
        )
