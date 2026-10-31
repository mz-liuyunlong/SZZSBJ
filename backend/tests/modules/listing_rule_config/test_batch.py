from datetime import date
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import UUID

from sqlalchemy.orm import Session

from app.modules.listing_rule_config import batch as batch_module
from app.modules.listing_rule_config.batch import ListingEvaluationBatchService
from app.modules.listing_rule_config.schemas import ListingGradeRuleConfig


class _ScalarRows:
    def __init__(self, rows) -> None:
        self.rows = rows

    def all(self):
        return self.rows


def _listing(value: int):
    return SimpleNamespace(
        id=UUID(int=value),
        source_account_ref="synthetic-account",
        store_id="synthetic-store",
        item_id=f"synthetic-item-{value}",
        msku=None,
    )


def test_batch_uses_keyset_pagination_and_one_fixed_rule(monkeypatch) -> None:
    session = MagicMock(spec=Session)
    run = SimpleNamespace(
        processed_listings=0,
        grade_candidate_count=0,
        lifecycle_candidate_count=0,
        blocked_count=0,
        total_listings=2,
        error_code=None,
    )
    session.get.side_effect = [run, run]
    session.scalars.side_effect = [
        _ScalarRows([_listing(1)]),
        _ScalarRows([_listing(2)]),
        _ScalarRows([]),
    ]
    calls = []

    class FakeEvaluator:
        def __init__(self, _session) -> None:
            pass

        def evaluate_page(self, **kwargs):
            calls.append(kwargs)
            value = SimpleNamespace(
                missing_evidence=[],
                current_lifecycle="启动期",
                current_grade=None,
                lifecycle_candidate="启动期",
                grade_candidate=None,
                valid_short=0,
                valid_medium=0,
                weighted_margin_percent=None,
                valid_stock_days_30=0,
                observed_stock_days_7=0,
                low_stock_days_7=0,
                prior_effective_stock=False,
                currently_archived=False,
                rule_version=7,
                rule_source="database",
            )
            return {listing.id: value for listing in kwargs["listings"]}

    monkeypatch.setattr(batch_module, "ListingEvaluationPreviewService", FakeEvaluator)
    config = ListingGradeRuleConfig()
    ListingEvaluationBatchService(session)._evaluate_pages(
        run_id=UUID(int=99),
        cutoff=date(2026, 1, 15),
        batch_size=1,
        config=config,
        rule_version=7,
    )

    statements = [call.args[0] for call in session.scalars.call_args_list]
    assert all("OFFSET" not in str(statement).upper() for statement in statements)
    assert "WHERE" in str(statements[1]).upper()
    assert [call["rule_version"] for call in calls] == [7, 7]
    assert all(call["config"] is config for call in calls)
    assert run.processed_listings == 2
