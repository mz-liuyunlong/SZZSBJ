"""New-product fast list: status is authoritative and permission-scope safe."""

from datetime import date

from app.modules.new_products.evaluation_policy import evaluation_status
from app.modules.new_products.performance_list_scope import matching_identities, summary


def test_status_is_not_promoted_by_nonfinal_dimension_scores():
    assert (
        evaluation_status(
            listing_date=date(2026, 11, 1),
            first_wfs=date(2026, 11, 1),
            coverage={"auto_dimension_scores": {"dimensions": {"ad": "10"}}},
            grade=None,
            total=None,
        )
        == "测评中"
    )


def test_market_status_requires_formal_completed_trigger():
    assert (
        evaluation_status(
            listing_date=date(2026, 11, 1),
            first_wfs=date(2026, 11, 1),
            coverage={
                "auto_dimension_scores": {},
                "evaluation_formal_trigger": {"status": "completed"},
            },
            grade=None,
            total=None,
        )
        == "待市场评分"
    )


def test_no_account_scope_returns_no_projection_and_no_query():
    class Never:
        def execute(self, *_a, **_kw):
            raise AssertionError("query leaked without account scope")

        def scalar(self, *_a, **_kw):
            raise AssertionError("query leaked without account scope")

    n = Never()
    got = summary(n, n, frozenset())
    assert got["counts"] == {"all": 0, "evaluating": 0, "market": 0, "passed": 0, "failed": 0}
    assert matching_identities(n, n, frozenset(), statuses="测评中") == []
