"""Five cards and exact detail filters, without changing assessment decisions."""

from datetime import date

from app.modules.new_products import performance_list_scope as scope


def test_stage_counts_and_exact_filters(monkeypatch):
    cases = [
        ("待到货", None, None, False, "待到货"),
        ("测评中", None, None, False, "测评中"),
        ("待市场评分", None, None, False, "待市场评分"),
        ("待等级确认", None, None, False, "待等级确认"),
        ("待测评确认", None, None, False, "待测评确认"),
        ("测评通过", None, None, False, "待申请采购"),
        ("测评通过", "submitted", None, False, "采购审批中"),
        ("测评通过", "approved", None, False, "采购已批准"),
        ("测评通过", "rejected", None, False, "采购已驳回"),
        ("测评未通过", None, None, False, "测评未通过"),
        ("测评未通过", None, "submitted", False, "复核审批中"),
        ("测评未通过", None, "info_required", False, "复核审批中"),
        ("测评未通过", None, "approved", True, "待重新核算"),
        ("测评未通过", None, "rejected", False, "复核已驳回"),
        ("测评未通过", None, "approved", False, "测评未通过"),
        ("待等级确认", "rejected", "rejected", False, "待等级确认"),
    ]
    rows = []
    for i, (base, purchase, review, recheck, expected) in enumerate(cases):
        first_wfs = date(2026, 11, 1) if base != "待到货" else None
        assert scope.flow_status(base, purchase, review, recheck, first_wfs=first_wfs) == expected
        rows.append(
            {
                "identity": ("a", "store", str(i)),
                "status": base,
                "flow_status": expected,
                "first_wfs": first_wfs,
                "grade": "pending",
                "owner": "A",
            }
        )
    # Listing has a launch date, but no verified first WFS availability.
    assert scope.flow_status("测评中", first_wfs=None) == "待到货"
    rows.append(
        {
            "identity": ("a", "store", "16"),
            "status": "测评中",
            "first_wfs": None,
            "grade": "pending",
            "owner": "A",
        }
    )
    monkeypatch.setattr(scope, "scoped_projection", lambda *_, **_kw: rows)
    # This fixture already supplies the resolved workflow states.
    monkeypatch.setattr(scope, "_attach_flow_statuses", lambda *_args, **_kwargs: None)
    accounts = frozenset({"a"})
    got = scope.summary(None, None, accounts)
    assert got["stage_counts"] == {
        "all": 17,
        "evaluating": 1,
        "pending": 4,
        "passed": 4,
        "failed": 6,
    }
    assert sum(x["count"] for x in got["flow_status_options"]) == 17
    assert {x["value"]: x["count"] for x in got["flow_status_options"]}["待到货"] == 2
    assert scope.matching_identities(None, None, accounts, statuses="flow:待到货") == [
        ("a", "store", "0"),
        ("a", "store", "16"),
    ]
    assert len(scope.matching_identities(None, None, accounts)) == 17
    for key, statuses in scope._FLOW_GROUPS.items():
        param = ",".join("flow:" + s for s in statuses)
        assert (
            len(scope.matching_identities(None, None, accounts, statuses=param))
            == got["stage_counts"][key]
        )
    assert len(scope.matching_identities(None, None, accounts, statuses="测评未通过")) == 6
    assert len(scope.matching_identities(None, None, accounts, statuses="flow:测评未通过")) == 2
    assert scope.matching_identities(None, None, accounts, statuses="flow:采购已驳回") == [
        ("a", "store", "8")
    ]
    assert scope.matching_identities(None, None, accounts, statuses="__none__") == []
