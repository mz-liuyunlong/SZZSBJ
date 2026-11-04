"""Regression checks for new-product advertising ratio and missing attribution."""

from __future__ import annotations

from datetime import date
from typing import Any

from app.modules.new_product_workflow.metrics import read_sku_metrics
from app.modules.new_product_workflow.rules import DEFAULT_RULES


class _Result:
    def __init__(self, row: dict[str, Any]) -> None:
        self.row = row

    def mappings(self) -> _Result:
        return self

    def one(self) -> dict[str, Any]:
        return self.row


class _Session:
    def __init__(
        self,
        *,
        attributed_currency: str | None = "USD",
        missing_financial_currencies: int = 0,
        missing_ad_currencies: int = 0,
        ad_days: int = 30,
    ) -> None:
        self.queries: list[str] = []
        self.attributed_currency = attributed_currency
        self.missing_financial_currencies = missing_financial_currencies
        self.missing_ad_currencies = missing_ad_currencies
        self.ad_days = ad_days

    def execute(self, statement: Any, params: dict[str, Any]) -> _Result:
        sql = str(statement)
        self.queries.append(sql)
        if "FROM mart_order_profit_sku_day" in sql:
            days = (params["end"] - params["start"]).days
            return _Result(
                {
                    "observed_days": days,
                    "sales_qty": 200,
                    "orders": 180,
                    "sales_amount": 1000,
                    "ad_spend": 100,
                    "profit": 200,
                    "complete_cost_days": days,
                    "currencies": 1,
                    "sales_currencies": 1,
                    "sales_currency": "USD",
                    "profit_currency": "USD",
                    "missing_currency_rows": self.missing_financial_currencies,
                }
            )
        if "FROM fact_walmart_ad_item_sp_daily" in sql:
            return _Result(
                {
                    "clicks": 80,
                    "attributed_spend": 100,
                    "attributed_sales": 400,
                    "spend_currencies": 1,
                    "attributed_currencies": 1 if self.attributed_currency else 0,
                    "spend_currency": "USD",
                    "attributed_currency": self.attributed_currency,
                    "missing_ad_currency_rows": self.missing_ad_currencies,
                    "ad_days": self.ad_days,
                }
            )
        if "FROM mart_listing_management_current" in sql:
            return _Result(
                {
                    "available": 90,
                    "wfs_available": 50,
                    "listing_count": 1,
                    "refreshed_at": None,
                }
            )
        raise AssertionError(f"Unexpected query: {sql}")


def test_acos_uses_attributed_sales_not_total_sales() -> None:
    session = _Session()
    data = read_sku_metrics(
        session,
        account="test-account",
        sku="TEST-SKU",
        market_score=8,
        rule_version=1,
        rules=DEFAULT_RULES,
        as_of=date(2026, 11, 1),
    )
    period = data["periods"]["30"]
    assert period["acos"] == 25
    assert period["ad_spend_ratio"] == 10
    assert period["attributed_sales"] == 400
    assert period["complete"] is True
    assert period["missing_days"] == 0
    assert period["data_issues"] == []
    assert data["score"]["status"] == "provisional"
    assert any("ad.attributed_sales_amount" in sql for sql in session.queries)


def test_launch_uses_verified_first_window_not_latest_rolling_period() -> None:
    session = _Session()
    data = read_sku_metrics(
        session,
        account="test-account",
        sku="TEST-SKU",
        market_score=8,
        rule_version=1,
        rules=DEFAULT_RULES,
        as_of=date(2026, 11, 1),
        start_date=date(2026, 8, 1),
    )
    assert data["verified_start_date"] == "2026-08-01"
    assert data["launch"] == {"status": "awaiting_approved_rules", "result": None}
    assert len(session.queries) == 9  # 3 rolling windows, 1 launch window and inventory


def test_candidate_failure_does_not_become_a_formal_launch_failure() -> None:
    session = _Session()
    data = read_sku_metrics(
        session,
        account="test-account",
        sku="TEST-SKU",
        market_score=8,
        rule_version=1,
        rules={**DEFAULT_RULES, "min_sales": 1000},
        as_of=date(2026, 11, 1),
        start_date=date(2026, 8, 1),
    )
    assert data["launch"] == {"status": "awaiting_approved_rules", "result": None}


def test_unknown_attribution_currency_never_produces_an_acos_score() -> None:
    session = _Session(attributed_currency=None)
    data = read_sku_metrics(
        session,
        account="test-account",
        sku="TEST-SKU",
        market_score=8,
        rule_version=1,
        rules=DEFAULT_RULES,
        as_of=date(2026, 11, 1),
    )
    period = data["periods"]["30"]
    assert period["acos"] is None
    assert period["ad_spend_ratio"] == 10
    assert period["complete"] is False
    assert "attributed_acos_unavailable" in period["data_issues"]
    assert data["score"]["status"] == "insufficient_data"


def test_currency_null_rows_block_aggregation_even_if_distinct_currency_is_one() -> None:
    for session in (
        _Session(missing_financial_currencies=1),
        _Session(missing_ad_currencies=1),
    ):
        data = read_sku_metrics(
            session,
            account="test-account",
            sku="TEST-SKU",
            market_score=8,
            rule_version=1,
            rules=DEFAULT_RULES,
            as_of=date(2026, 11, 1),
        )
        period = data["periods"]["30"]
        assert period["complete"] is False
        assert data["score"]["status"] == "insufficient_data"
        if session.missing_financial_currencies:
            assert "financial_currency_unverified" in period["data_issues"]
            assert period["revenue"] is None
        else:
            assert "attributed_acos_unavailable" in period["data_issues"]
            assert period["acos"] is None


def test_sparse_ad_fact_days_cannot_masquerade_as_full_coverage() -> None:
    data = read_sku_metrics(
        _Session(ad_days=2),
        account="test-account",
        sku="TEST-SKU",
        market_score=8,
        rule_version=1,
        rules=DEFAULT_RULES,
        as_of=date(2026, 11, 1),
    )
    assert data["periods"]["30"]["complete"] is False
    assert "ad_coverage_unverified" in data["periods"]["30"]["data_issues"]
