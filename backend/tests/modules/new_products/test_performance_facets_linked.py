"""Linked facets: full scoped rows, self-exclusion and correction-grade membership."""

from app.modules.new_products import performance_list_scope as scope


def test_linked_facets_keep_global_cards_and_exclude_own_filter(monkeypatch):
    rows = [
        {"identity": ("a", "s", "1"), "status": "待等级确认", "owner": "A", "grade": "B"},
        {"identity": ("a", "s", "2"), "status": "待测评确认", "owner": "A", "grade": "C"},
        {"identity": ("a", "s", "3"), "status": "待等级确认", "owner": "B", "grade": "B"},
        {"identity": ("a", "s", "4"), "status": "测评通过", "owner": "A", "grade": "B"},
        {
            "identity": ("a", "s", "5"),
            "status": "待等级确认",
            "owner": "A",
            "grade": "B",
            "keyword_match": False,
        },
    ]
    monkeypatch.setattr(scope, "_first_wfs_projection", lambda *a, **k: rows)
    monkeypatch.setattr(scope, "_attach_flow_statuses", lambda *a, **k: None)
    result = scope.summary(
        None,
        None,
        frozenset({"a"}),
        phase="pending",
        statuses="flow:待等级确认",
        owners="A",
        ratings="B",
        keyword="matched",
    )
    assert result["stage_counts"]["all"] == 5
    assert result["stage_counts"]["pending"] == 4
    assert {r["value"]: r["count"] for r in result["owner_options"]} == {"A": 1, "B": 1}
    assert sum(r["count"] for r in result["rating_options"]) == 1
    assert sum(r["count"] for r in result["flow_status_options"]) == 1
    assert scope.matching_identities(
        None,
        None,
        frozenset({"a"}),
        statuses="flow:待测评确认",
        ratings="C",
    ) == [("a", "s", "2")]


def test_status_facet_excludes_itself_and_owner_facet_preserves_selected_zero():
    rows = [
        {"status": "待等级确认", "owner": "A", "grade": "C"},
        {"status": "待测评确认", "owner": "B", "grade": "C"},
    ]
    flows, owners, ratings = scope._facet_counts(
        rows,
        phase="pending",
        statuses="flow:待等级确认",
        owners="Z",
        ratings="C",
        owner_keyword="",
    )
    assert not flows and not ratings
    assert owners == {"A": 1, "Z": 0}
    flows, _, _ = scope._facet_counts(
        rows,
        phase="pending",
        statuses="flow:待等级确认",
        owners="",
        ratings="C",
        owner_keyword="",
    )
    assert flows == {"待等级确认": 1, "待测评确认": 1}


def test_pending_grade_uses_same_verified_overlay(monkeypatch):
    from app.modules.new_products import score_corrections

    def apply(row, block, config, *, risk_evaluation, require_risk):
        assert risk_evaluation == {"verified": True} and require_risk
        row["evaluation"]["grade"] = "B"
        return True

    monkeypatch.setattr(score_corrections, "overlay", apply)
    proof = {
        "grade": "D",
        "score": "5.4",
        "score_correction": {},
        "correction_final": {
            "grade": "D",
            "dimensions": {},
            "rule_version": 2,
            "risk_evaluation": {"verified": True},
        },
    }
    assert scope._pending_effective_grade(proof, {}) == "B"
    monkeypatch.setattr(score_corrections, "overlay", lambda *a, **k: False)
    assert scope._pending_effective_grade(proof, {}) == "D"


def test_real_saved_overlay_keeps_risk_caps():
    dimensions = dict.fromkeys(("market", "speed", "ad", "profit", "trust"), "5")
    base = {
        "grade": "D",
        "total": "5.0000",
        "dimensions": dimensions,
        "rule_version": 2,
        "ad_excluded": False,
    }
    block = {"revision": 1, "system": base, "overrides": {"profit": "9.00"}, "history": []}
    risk = {
        "base_grade": "D",
        "effective_grade": "D",
        "rule_version": 2,
        "risk_hits": [],
        "manual_selected": ["无"],
    }
    final = {**base, "risk_evaluation": risk}
    proof = {"grade": "D", "score": "5.0000", "score_correction": block, "correction_final": final}
    config = {
        "weights": {"market": 15, "speed": 30, "ad": 20, "profit": 25, "trust": 10},
        "gradeBands": {
            "S": [9, 10],
            "A": [8, 8.99],
            "B": [7, 7.99],
            "C": [6, 6.99],
            "D": [0, 5.99],
        },
    }
    assert scope._pending_effective_grade(proof, config) == "C"
    risk["manual_selected"] = ["风险"]
    risk["risk_hits"] = [{"source": "manual", "name": "风险", "limit": "D"}]
    assert scope._pending_effective_grade(proof, config) == "D"
    final["risk_evaluation"] = None
    assert scope._pending_effective_grade(proof, config) == "D"
