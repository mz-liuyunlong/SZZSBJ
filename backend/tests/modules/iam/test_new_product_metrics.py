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
        missing_spend_currencies: int = 0,
        spend_currency: str = "USD",
        sem_ad_spend: int = 0,
        missing_sem_mart_rows: int = 0,
        ad_days: int | None = None,
        investment_cost_missing: int = 0,
        sales_currency: str = "USD",
        purchase_cost_total: int = 150,
    ) -> None:
        self.queries: list[str] = []
        self.attributed_currency = attributed_currency
        self.missing_financial_currencies = missing_financial_currencies
        self.missing_ad_currencies = missing_ad_currencies
        self.missing_spend_currencies = missing_spend_currencies
        self.spend_currency = spend_currency
        self.sem_ad_spend = sem_ad_spend
        self.missing_sem_mart_rows = missing_sem_mart_rows
        self.ad_days = ad_days
        self.investment_cost_missing = investment_cost_missing
        self.sales_currency = sales_currency
        self.purchase_cost_total = purchase_cost_total

    def execute(self, statement: Any, params: dict[str, Any]) -> _Result:
        sql = str(statement)
        self.queries.append(sql)
        if "AS first_order_date" in sql:
            return _Result(
                {
                    "first_order_date": date(2026, 8, 3),
                    "sales_7d": 21,
                    "sales_10d": 30,
                    "sales_20d": 60,
                    "coverage_7d": 7,
                    "coverage_10d": 10,
                    "coverage_20d": 20,
                }
            )
        if "FROM mart_order_profit_sku_day" in sql:
            days = (params["end"] - params["start"]).days
            return _Result(
                {
                    "observed_days": days,
                    "sales_qty": 200,
                    "orders": 180,
                    "sales_amount": 1000,
                    "sp_ad_spend": 100,
                    "sem_ad_spend": self.sem_ad_spend,
                    "missing_sp_mart_rows": 0,
                    "missing_sem_mart_rows": self.missing_sem_mart_rows,
                    "profit": 200,
                    "purchase_cost_total": self.purchase_cost_total,
                    "first_leg_cost_total": 50,
                    "missing_investment_cost_rows": self.investment_cost_missing,
                    "complete_cost_days": days,
                    "currencies": 1,
                    "sales_currencies": 1,
                    "sales_currency": self.sales_currency,
                    "profit_currency": self.sales_currency,
                    "missing_currency_rows": self.missing_financial_currencies,
                }
            )
        if "FROM fact_walmart_ad_item_sp_daily" in sql:
            return _Result(
                {
                    "clicks": 80,
                    "attributed_spend": 100,
                    "attributed_sales": 400,
                    "attributed_orders": 15,
                    "impressions": 4000,
                    "spend_currencies": 1,
                    "attributed_currencies": 1 if self.attributed_currency else 0,
                    "spend_currency": self.spend_currency,
                    "attributed_currency": self.attributed_currency,
                    "missing_spend_currency_rows": self.missing_spend_currencies,
                    "missing_ad_currency_rows": self.missing_ad_currencies,
                    "ad_days": (
                        self.ad_days
                        if self.ad_days is not None
                        else (params["end"] - params["start"]).days
                    ),
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
    assert period["cpc"] == 1.25
    assert period["cvr"] == 18.75
    assert period["roi"] == 1
    assert period["roi_status"] == "daily_sales_operating_roi"
    assert period["roas"] == 4
    assert period["ad_spend_ratio"] == 10
    assert period["attributed_sales"] == 400
    assert period["complete"] is True
    assert period["missing_days"] == 0
    assert period["data_issues"] == []
    assert data["score"]["status"] == "provisional"
    assert any("ad.attributed_sales_amount" in sql for sql in session.queries)


def test_total_ad_spend_includes_sem_without_double_deducting_existing_profit() -> None:
    session = _Session(sem_ad_spend=25)
    result = read_sku_metrics(
        session,
        account="test-account",
        sku="TEST-SKU",
        market_score=8,
        rule_version=1,
        rules=DEFAULT_RULES,
        as_of=date(2026, 11, 1),
    )
    for key in ("30", "60", "90"):
        period = result["periods"][key]
        assert period["sp_ad_spend"] == 100
        assert period["sem_ad_spend"] == 25
        assert period["ad_spend"] == 125
        assert period["ad_spend_ratio"] == 12.5
        assert period["profit"] == 200  # already net of both components in Daily Sales
        assert period["margin"] == 20
        assert period["acos"] == 25  # SP attribution only, never SEM


def test_unknown_sem_currency_never_fabricates_total_spend_or_ratio() -> None:
    session = _Session(sem_ad_spend=25, missing_sem_mart_rows=1)
    period = read_sku_metrics(
        session,
        account="test-account",
        sku="TEST-SKU",
        market_score=8,
        rule_version=1,
        rules=DEFAULT_RULES,
        as_of=date(2026, 11, 1),
    )["periods"]["30"]
    assert period["ad_spend"] is None
    assert period["ad_spend_ratio"] is None
    assert period["sp_ad_spend"] == 100
    assert period["sem_ad_spend"] is None
    assert "sem_ad_spend_currency_unverified" in period["data_issues"]
    assert period["profit"] == 200


def test_operating_roi_requires_verified_cost_and_usd_currency() -> None:
    for session in (
        _Session(investment_cost_missing=1),
        _Session(sales_currency="EUR", spend_currency="EUR"),
        _Session(purchase_cost_total=-50),
    ):
        period = read_sku_metrics(
            session,
            account="test-account",
            sku="TEST-SKU",
            market_score=8,
            rule_version=1,
            rules=DEFAULT_RULES,
            as_of=date(2026, 11, 1),
        )["periods"]["30"]
        assert period["roi"] is None
        assert period["roi_status"] == "daily_sales_cost_or_coverage_unverified"


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
    assert len(session.queries) == 10  # 3 windows, launch window, milestones and inventory
    assert data["order_milestones"]["days_to_first_order"] == 2
    assert data["order_milestones"]["sales_7d"] == 21


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


def test_daily_sales_spend_stays_visible_when_ad_fact_currency_is_unverified() -> None:
    missing_attribution = read_sku_metrics(
        _Session(attributed_currency=None),
        account="test-account",
        sku="TEST-SKU",
        market_score=8,
        rule_version=1,
        rules=DEFAULT_RULES,
        as_of=date(2026, 11, 1),
    )["periods"]["30"]
    assert missing_attribution["acos"] is None
    assert missing_attribution["ad_spend_ratio"] == 10
    assert missing_attribution["cpc"] == 1.25

    for session in (
        _Session(missing_spend_currencies=1),
        _Session(spend_currency="EUR"),
    ):
        period = read_sku_metrics(
            session,
            account="test-account",
            sku="TEST-SKU",
            market_score=8,
            rule_version=1,
            rules=DEFAULT_RULES,
            as_of=date(2026, 11, 1),
        )["periods"]["30"]
        assert period["ad_spend_ratio"] == 10
        assert period["ad_spend"] == 100
        assert period["cpc"] is None
        assert "ad_fact_spend_currency_unverified" in period["data_issues"]


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
