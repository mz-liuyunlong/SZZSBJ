"""Safety contract for zero-paid sample identity and SaleStat finance isolation."""

from datetime import date
from unittest.mock import MagicMock

from app.modules.integration_sync.data_pages_business_rules import DataPagesRealSyncRunner


def _runner(
    rows: list[dict[str, object]] | None = None,
) -> tuple[DataPagesRealSyncRunner, MagicMock]:
    session = MagicMock()
    session.execute.return_value.mappings.return_value.one.return_value = (
        rows[0]
        if rows
        else {
            "listing_count": 1,
            "listing_id": "item-a",
            "sales_count": 0,
            "sales_id": None,
        }
    )
    session.execute.return_value.scalar_one.return_value = 0
    runner = DataPagesRealSyncRunner(
        session=session,
        client=None,
        source_account_ref="synthetic-account",
        business_date=date(2026, 10, 17),
        page_size=100,
        campaign_type="SP",
        max_advertisers=1,
    )
    return runner, session


def test_unique_listing_can_resolve_zero_paid_sample_when_salestat_absent() -> None:
    runner, _ = _runner()
    assert runner._hotfix_unique_sample_item_id("store-a", "msku-a", "sku-a") == "item-a"


def test_conflicting_salestat_identity_does_not_get_auto_approved() -> None:
    runner, _ = _runner([
        {
            "listing_count": 1,
            "listing_id": "item-a",
            "sales_count": 1,
            "sales_id": "item-b",
        }
    ])
    assert runner._hotfix_unique_sample_item_id("store-a", "msku-a", "sku-a") is None


def test_ambiguous_listing_identity_stays_unresolved() -> None:
    runner, _ = _runner([
        {
            "listing_count": 2,
            "listing_id": "item-a",
            "sales_count": 0,
            "sales_id": None,
        }
    ])
    assert runner._hotfix_unique_sample_item_id("store-a", "msku-a", "sku-a") is None


def test_auto_verified_sample_does_not_require_salestat_or_current_order_fact() -> None:
    runner, session = _runner()
    runner._resolve_sample_items()
    queries = [str(call.args[0]) for call in session.execute.call_args_list]
    approval = next(query for query in queries if "set is_valid_sample=true" in query)
    assert "order_total_amount=0" in approval
    assert "is_cancelled=false" in approval
    assert "fact_walmart_sales_item_daily" not in approval
    assert "fact_walmart_order_items" not in approval
    assert "dim_walmart_listings" in approval
    assert "source_order_line_id is not null" in approval
