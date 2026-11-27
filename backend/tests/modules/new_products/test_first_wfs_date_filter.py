"""Inclusive LA first-WFS dates, exact identity, global summary and filters."""

from datetime import date

import pytest

from app.core.api import ApiError
from app.modules.new_products import performance_list_scope as scope


@pytest.fixture
def projected(monkeypatch):
    rows = [
        {
            "identity": ("a", "store1", "100"),
            "first_wfs": date(2026, 11, 1),
            "launch_day": date(2026, 10, 1),
            "status": "测评中",
            "grade": "pending",
            "owner": "A",
        },
        {
            "identity": ("a", "store2", "100"),
            "first_wfs": date(2026, 11, 15),
            "launch_day": date(2026, 10, 1),
            "status": "测评通过",
            "grade": "A",
            "owner": "B",
        },
        {
            "identity": ("a", "store1", "101"),
            "first_wfs": date(2026, 11, 16),
            "launch_day": date(2026, 11, 1),
            "status": "测评通过",
            "grade": "A",
            "owner": "B",
        },
        {
            "identity": ("a", "store1", "102"),
            "first_wfs": None,
            "launch_day": date(2026, 11, 1),
            "status": "待到货",
            "grade": "pending",
            "owner": "A",
        },
        {
            "identity": ("b", "store1", "100"),
            "first_wfs": date(2026, 11, 1),
            "launch_day": date(2026, 11, 1),
            "status": "测评通过",
            "grade": "A",
            "owner": "B",
        },
    ]
    monkeypatch.setattr(
        scope,
        "scoped_projection",
        lambda source, db, accounts, **_kwargs: [
            row for row in rows if row["identity"][0] in accounts
        ],
    )
    # No procurement records in this date-filter fixture.
    monkeypatch.setattr(scope, "_attach_flow_statuses", lambda *_args, **_kwargs: None)
    return frozenset({"a"})


def test_default_preserves_unknown_and_all_dates(projected):
    assert scope.summary(None, None, projected)["counts"]["all"] == 4
    assert len(scope.matching_identities(None, None, projected)) == 4


def test_inclusive_range_excludes_unknown_and_other_account(projected):
    dates = {"start_date": date(2026, 11, 1), "end_date": date(2026, 11, 15)}
    ids = scope.matching_identities(None, None, projected, **dates)
    assert ids == [("a", "store1", "100"), ("a", "store2", "100")]
    summary = scope.summary(None, None, projected, **dates)
    assert summary["counts"]["all"] == 2
    assert summary["counts"]["passed"] == 1
    assert summary["counts"]["evaluating"] == 1
    assert sum(row["count"] for row in summary["owner_options"]) == 2
    assert sum(row["count"] for row in summary["rating_options"]) == 2


def test_combined_filters_and_single_day(projected):
    dates = {"start_date": date(2026, 11, 15), "end_date": date(2026, 11, 15)}
    assert scope.matching_identities(
        None, None, projected, owners="B", ratings="A", statuses="测评通过", **dates
    ) == [("a", "store2", "100")]
    assert scope.matching_identities(None, None, projected, statuses="测评中", **dates) == []


@pytest.mark.parametrize(
    "start,end",
    [(date(2026, 11, 2), None), (None, date(2026, 11, 2)), (date(2026, 11, 2), date(2026, 11, 1))],
)
def test_invalid_range_rejected_before_read(monkeypatch, start, end):
    def fail(*args, **kwargs):
        raise AssertionError("invalid range queried the source")

    monkeypatch.setattr(scope, "scoped_projection", fail)
    for fn in (scope.summary, scope.matching_identities):
        with pytest.raises(ApiError):
            fn(None, None, frozenset({"a"}), start_date=start, end_date=end)
