"""Contract tests: financial exceptions must never suppress healthy SKU rows."""

from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock

from sqlalchemy import text

from app.modules.integration_sync.data_pages_finance_partial_isolation import (
    record_sample_dispute,
    reserve_unallocated_sem_lines,
    reset_sample_dispute_current,
)


def test_sem_unallocated_lines_reconcile_in_same_transaction() -> None:
    session = MagicMock()
    session.execute.return_value.scalar_one.return_value = Decimal("36.61")

    result = reserve_unallocated_sem_lines(
        session,
        source_account_ref="synthetic",
        business_date=date(2026, 8, 2),
    )

    assert result == Decimal("36.61")
    assert session.execute.call_count == 3
    calls = session.execute.call_args_list
    assert "is_current=false" in str(calls[0].args[0])
    assert "on conflict" in str(calls[1].args[0])
    assert "sum(spend_amount_usd)" in str(calls[2].args[0])
    for call in calls:
        assert call.args[1] == {"account": "synthetic", "day": date(2026, 8, 2)}


def test_sample_dispute_is_keyed_to_exact_item_and_msku() -> None:
    session = MagicMock()
    params = dict(
        source_account_ref="synthetic",
        business_date=date(2026, 8, 11),
        store_id="store",
        item_id="20257773836",
        msku="YC00202-1A",
        sample_qty=Decimal("4"),
        sales_qty=Decimal("2"),
        sample_amount=Decimal("51.96"),
        sales_amount=Decimal("25.98"),
    )
    reset_sample_dispute_current(
        session, source_account_ref="synthetic", business_date=params["business_date"]
    )
    record_sample_dispute(session, **params)
    assert session.execute.call_count == 2
    assert "is_current=false" in str(session.execute.call_args_list[0].args[0])
    sql, values = session.execute.call_args_list[1].args
    assert "on conflict" in str(sql)
    assert values["item"] == "20257773836"
    assert values["msku"] == "YC00202-1A"
    assert values["sample_qty"] - values["sales_qty"] == 2
    assert values["sample_amount"] - values["sales_amount"] == Decimal("25.98")


def test_unallocated_ledger_preserves_exact_source_row_and_negative_credits() -> None:
    from app.modules.integration_sync import data_pages_finance_partial_isolation as module

    query = str(module._RESERVE_SQL)
    assert "task_id,row_index" in query
    assert "raw_hash" in query
    assert "NEGATIVE_CREDIT_REVIEW" in query
    assert "CAMPAIGN_ID_AMBIGUOUS" in query
    assert "LISTING_NOT_FOUND" in query
    assert "is_current=true" in query
    assert "on conflict" in query


def test_business_rule_does_not_abort_day_for_one_sample_item() -> None:
    import inspect
    from app.modules.integration_sync.data_pages_business_rules_v2 import DataPagesRealSyncRunner

    src = inspect.getsource(DataPagesRealSyncRunner._refresh_daily_sales_mart)
    assert "sample_disputed = sample_qty > gross_qty or sample_amount > gross_sales" in src
    assert "record_sample_dispute(" in src
    assert "if not sample_disputed" in src
    assert 'missing.append("sample_exceeds_salestat_pending_review")' in src
    assert "reserve_unallocated_sem_lines(" in src
    assert "booked_sem + reserved_sem" in src
    assert "DATA_PAGES_SEM_SPEND_UNATTRIBUTED" in src
    assert "DATA_PAGES_CONFIRMED_SAMPLE_EXCEEDS_SALESTAT" not in src
