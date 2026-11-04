"""Read-only actual-mart reconciliation and fail-closed source checks."""

from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock

from app.modules.new_product_workflow.reconciliation import reconcile_new_product_source


def _mock_session() -> MagicMock:
    records = [
        {
            "listing_rows": 2,
            "stores": 2,
            "store_item_pairs": 2,
            "item_ids": 2,
            "first_listing_date": date(2026, 8, 1),
            "missing_listing_start_rows": 0,
        },
        {
            "days": 29,
            "recorded_zero_days": 4,
            "qty": 60,
            "orders": 55,
            "sales_amount": 700,
            "gross_profit": 140,
            "missing_cost_rows": 1,
            "missing_currency_rows": 0,
            "revenue_currency_count": 1,
            "profit_currency_count": 1,
            "revenue_currency": "USD",
            "profit_currency": "USD",
        },
        {
            "rows": 38,
            "days": 29,
            "store_item_pairs": 2,
            "qty": 59,
            "orders": 55,
            "sales_amount": 695,
            "currency_count": 1,
            "missing_currency_rows": 0,
        },
        {
            "candidate_rows": 15,
            "matched_rows": 14,
            "unmatched_rows": 1,
            "observed_ad_days": 12,
            "spend_without_currency": 0,
            "attributed_without_currency": 3,
            "spend_currency_count": 1,
            "attributed_currency_count": 0,
            "spend_currency": "USD",
            "attributed_currency": None,
            "ad_spend": 40,
            "attributed_sales": 200,
        },
    ]
    session = MagicMock()
    results = []
    for record in records:
        result = MagicMock()
        result.mappings.return_value.one.return_value = record
        results.append(result)
    session.execute.side_effect = results
    return session


def test_reconciliation_never_converts_missing_days_or_currency_into_verified_data() -> None:
    session = _mock_session()
    report = reconcile_new_product_source(
        session,
        account="SYNTH-ACCOUNT",
        sku="SYNTH-SKU",
        start=date(2026, 10, 1),
        end=date(2026, 10, 31),
        include_financial_values=True,
    )
    assert report["status"] == "blocked"
    assert report["zero_sales_days_verification"] == "source_publication_ledger_not_proven"
    assert report["sales"]["recorded_zero_days"] == 4
    assert report["mapping"]["stores"] == 2
    assert "sales_qty_sku_vs_item_mart_mismatch" in report["issues"]
    assert "attributed_sales_currency_missing" in report["issues"]
    assert "sales_amount_sku_vs_item_mart_mismatch" in report["issues"]
    assert "financial_cost_coverage_incomplete" in report["issues"]
    assert report["finance"]["roas"] is None
    for call in session.execute.call_args_list:
        query, params = call.args
        assert "source_account_ref" in str(query)
        assert params["account"] == "SYNTH-ACCOUNT"
        assert "INSERT " not in str(query).upper()
        assert "DELETE " not in str(query).upper()


def test_reconciliation_finance_is_not_visible_to_unprivileged_readers() -> None:
    report = reconcile_new_product_source(
        _mock_session(),
        account="SYNTH-ACCOUNT",
        sku="SYNTH-SKU",
        start=date(2026, 10, 1),
        end=date(2026, 10, 31),
        include_financial_values=False,
    )
    assert report["finance"] == {"visibility": "restricted"}
    assert report["read_only"] is True
