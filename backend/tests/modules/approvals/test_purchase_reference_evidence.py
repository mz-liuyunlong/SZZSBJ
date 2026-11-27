"""As-submitted purchase evidence: no HTTP, credentials, network, or database writes."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from app.modules.approvals.purchase_reference_evidence import purchase_reference_evidence


class ReadOnlySession:
    def __init__(self, events):
        self.events = events

    def scalar(self, _stmt):
        return SimpleNamespace(
            config_json={
                "weights": {"market": 15, "speed": 30, "ad": 20, "profit": 25, "trust": 10}
            }
        )

    def scalars(self, _stmt):
        return SimpleNamespace(all=lambda: self.events)


def application():
    now = datetime(2026, 11, 20, 12, tzinfo=UTC)
    dims = {"market": "7", "speed": "6", "ad": "2", "profit": "3", "trust": "4.6"}
    return SimpleNamespace(
        source_account_ref="a",
        store_id="s",
        item_id="20858150090",
        created_at=now,
        score_rule_version=12,
        score_snapshot={
            "evaluation": {"dimensions": dims, "total": "6", "grade": "C", "risk": []},
            "facts": {},
            "score_correction": {
                "system": {"dimensions": {**dims, "speed": "4.6", "profit": "0"}},
                "effective": {"dimensions": dims},
                "history": [
                    {
                        "dimension": "speed",
                        "before": "4.6",
                        "after": "6",
                        "reason": "周期修正",
                        "at": now.isoformat(),
                    },
                    {
                        "dimension": "profit",
                        "before": "0",
                        "after": "3",
                        "reason": "修正利润口径",
                        "at": now.isoformat(),
                    },
                ],
            },
        },
    )


def market_event(now, risk, ids, none):
    return SimpleNamespace(
        event_type="market_score",
        source_account_ref="a",
        store_id="s",
        item_id="20858150090",
        created_at=now - timedelta(seconds=1),
        id="1",
        payload_json={
            "score": 7,
            "reason": "已核实竞品价格",
            "risk_conditions": risk,
            "competitor_ids": ids,
            "no_competitors": none,
        },
    )


def test_preserves_historical_system_and_effective_scores():
    app = application()
    result = purchase_reference_evidence(
        ReadOnlySession([market_event(app.created_at, ["资金占用率高"], ["1234"], False)]), app
    )
    assert result["effective_dimensions"]["speed"] == "6"
    assert result["system_dimensions"]["speed"] == "4.6"
    assert result["weights"]["speed"] == 30
    assert result["correction_history"][1]["reason"] == "修正利润口径"
    assert result["manual_risks"] == ["资金占用率高"]
    assert result["competitor_ids"] == ["1234"]
    assert result["manual_conclusion"] is None  # Never fabricate a human conclusion from C-grade


def test_explicit_none_is_distinct_from_unknown():
    app = application()
    yes = purchase_reference_evidence(
        ReadOnlySession([market_event(app.created_at, ["无"], [], True)]), app
    )
    missing = purchase_reference_evidence(ReadOnlySession([]), app)
    assert yes["manual_risks"] == ["无"]
    assert yes["no_competitors"] is True
    assert missing["manual_risks"] is None
    assert missing["no_competitors"] is None


# NP_PURCHASE_SCORE_GRADE_EVIDENCE_V1


def test_missing_correction_is_not_claimed_unchanged():
    app = application()
    app.score_snapshot.pop("score_correction")
    result = purchase_reference_evidence(ReadOnlySession([]), app)
    assert all(value is None for value in result["system_dimensions"].values())
    assert result["system_grade"] is None
    assert result["effective_grade"] == "C"
    assert result["correction_history"] == []


def test_frozen_grade_and_per_edit_grade_evidence():
    app = application()
    correction = app.score_snapshot["score_correction"]
    correction["system"]["grade"] = "D"
    correction["history"][0].update(
        before_grade="D", effective_grade="C", before_total="5", effective_total="6"
    )
    result = purchase_reference_evidence(ReadOnlySession([]), app)
    assert result["system_grade"] == "D"
    assert result["effective_grade"] == "C"
    assert result["correction_history"][0]["before_grade"] == "D"
    assert result["correction_history"][0]["after_grade"] == "C"


def _historical_audit(app):
    def event(kind, payload, seconds):
        return SimpleNamespace(
            event_type=kind,
            payload_json=payload,
            created_at=app.created_at - timedelta(seconds=seconds),
        )

    return [
        event(
            "grade_confirmed",
            {
                "status": "confirmed",
                "rule_version": 12,
                "correction_revision": 2,
                "effective_grade": "C",
                "effective_total": "6",
            },
            1,
        ),
        event(
            "score_correction_saved",
            {
                "revision": 2,
                "dimension": "profit",
                "system_score": "0",
                "before": "0",
                "after": "3",
                "reason": "profit",
                "effective_grade": "C",
            },
            2,
        ),
        event(
            "score_correction_saved",
            {
                "revision": 1,
                "dimension": "speed",
                "system_score": "4.6",
                "before": "4.6",
                "after": "6",
                "reason": "speed",
                "effective_grade": "D",
            },
            3,
        ),
    ]


def test_historical_audit_recovers_complete_revision_chain_but_not_unknown_grade():
    app = application()
    app.score_snapshot.pop("score_correction")
    result = purchase_reference_evidence(ReadOnlySession(_historical_audit(app)), app)
    assert result["system_dimensions"]["speed"] == "4.6"
    assert result["system_dimensions"]["profit"] == "0"
    assert len(result["correction_history"]) == 2
    assert result["system_grade"] is None
    assert result["correction_history"][1]["after_grade"] == "C"
    assert result["correction_history"][0]["before_grade"] is None


def test_incomplete_or_inconsistent_historical_chain_fails_closed():
    app = application()
    app.score_snapshot.pop("score_correction")
    events = _historical_audit(app)
    for bad in (events[:2], [events[0], events[1], events[1], events[2]]):
        result = purchase_reference_evidence(ReadOnlySession(bad), app)
        assert result["system_dimensions"]["speed"] is None
        assert result["correction_history"] == []
    events[1].payload_json["after"] = "4"
    result = purchase_reference_evidence(ReadOnlySession(events), app)
    assert result["system_dimensions"]["profit"] is None


def test_original_grade_recovers_only_from_matching_locked_confirmation():
    app = application()
    correction = app.score_snapshot.pop("score_correction")
    correction.update(revision=2)
    correction["system"]["grade"] = "D"
    events = _historical_audit(app)
    record = events[0].payload_json
    record.update(actor_id="operator", confirmed_at="2026-11-20T11:59:59+00:00", market_version=1)
    final = {
        **app.score_snapshot["evaluation"],
        "rule_version": 12,
        "grade_before_confirmation_v1": {**correction["system"], "total": "5"},
    }
    coverage = {
        "evaluation_grade_confirmation_v1": dict(record),
        "evaluation_final_snapshot": final,
        "operator_score_correction_v1": correction,
    }

    class LockedSession(ReadOnlySession):
        def scalar(self, stmt):
            if "data_coverage_json" in str(stmt):
                return coverage
            return super().scalar(stmt)

    result = purchase_reference_evidence(LockedSession(events), app)
    assert result["system_grade"] == "D"
    coverage["evaluation_grade_confirmation_v1"]["confirmed_at"] = "later"
    result = purchase_reference_evidence(LockedSession(events), app)
    assert result["system_grade"] is None


def test_purchase_service_freezes_correction_and_grade_snapshot():
    from copy import deepcopy
    from decimal import Decimal
    from unittest.mock import MagicMock

    from app.modules.new_products.service import NewProductService

    app = application()
    correction = deepcopy(app.score_snapshot["score_correction"])
    correction["revision"] = 2
    correction["system"]["grade"] = "D"
    original = {**correction["system"], "total": "5"}
    final = {
        **app.score_snapshot["evaluation"],
        "rule_version": 12,
        "grade_before_confirmation_v1": original,
    }
    marker = {"status": "confirmed", "correction_revision": 2, "effective_grade": "C"}
    coverage = {
        "evaluation_final_snapshot": final,
        "evaluation_grade_confirmation_v1": marker,
        "operator_assessment_v1": {"decision": "passed"},
        "operator_score_correction_v1": correction,
        "evaluation_operating_archive_v1": {"rule_version": 12, "suggested_qty": 100},
    }
    perf = SimpleNamespace(grade="C", score=Decimal("6"), data_coverage_json=coverage)
    db = MagicMock()
    db.scalar.side_effect = [perf, None]
    service = NewProductService.__new__(NewProductService)
    service.db = db
    service._listing = MagicMock()
    service._final_decisions = MagicMock(return_value={})
    service.write_repo = MagicMock()
    service.write_repo.active_purchase.return_value = False
    service._config = MagicMock(return_value=({}, 12))
    service._event = MagicMock()
    body = SimpleNamespace(
        source_account_ref="a",
        store_id="s",
        item_id="i",
        requested_qty=100,
        reason="",
        expected_rule_version=12,
    )
    service.purchase(frozenset({"a"}), body, "operator")
    frozen = db.add.call_args.args[0].score_snapshot
    assert frozen["score_correction"] == correction
    assert frozen["grade_before_confirmation"]["grade"] == "D"
    assert frozen["evaluation"]["grade"] == "C"
    correction["history"].clear()
    assert len(frozen["score_correction"]["history"]) == 2


# NP_PURCHASE_SCORE_HOVER_HEADER_V2


def test_header_totals_are_read_from_frozen_snapshot_only():
    app = application()
    correction = app.score_snapshot["score_correction"]
    correction["system"].update(grade="D", total="5.40")
    result = purchase_reference_evidence(ReadOnlySession([]), app)
    assert result["system_total"] == "5.40"
    assert result["effective_total"] == "6"
    correction["system"].pop("total")
    result = purchase_reference_evidence(ReadOnlySession([]), app)
    assert result["system_total"] is None


def test_verified_history_resolves_actor_display_name_without_exposing_id_as_name():
    app = application()
    history = app.score_snapshot["score_correction"]["history"]
    history[0]["actor_id"] = "1"
    history[1]["actor_id"] = "2"

    class NamedSession(ReadOnlySession):
        def execute(self, stmt, params):
            assert params == {"actor_ids": [1, 2]}
            assert "password" not in str(stmt).lower()
            return SimpleNamespace(
                mappings=lambda: SimpleNamespace(all=lambda: [{"id": 1, "actor_name": "运营人员"}])
            )

    result = purchase_reference_evidence(NamedSession([]), app)
    assert result["correction_history"][0]["actor_name"] == "运营人员"
    assert result["correction_history"][1]["actor_name"] is None
