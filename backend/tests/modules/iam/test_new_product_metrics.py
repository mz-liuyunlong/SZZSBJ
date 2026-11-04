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
    def __init__(self, *, attributed_currency: str | None = "USD") -> None:
        self.queries: list[str] = []
        self.attributed_currency = attributed_currency

    def execute(self, statement: Any, params: dict[str, Any]) -> _Result:
        sql = str(statement)
        self.queries.append(sql)
        if "FROM mart_order_profit_sku_day" in sql:
            days = (params["end"] - params["start"]).days
            return _Result({
                "observed_days": days,
                "sales_qty": 200,
                "orders": 180,
                "sales_amount": 1000,
                "ad_spend": 100,
                "profit": 200,
                "complete_cost_days": days,
                "currencies": 1,
            })
        if "FROM fact_walmart_ad_item_sp_daily" in sql:
            return _Result({
                "clicks": 80,
                "attributed_spend": 100,
                "attributed_sales": 400,
                "spend_currencies": 1,
                "attributed_currencies": 1 if self.attributed_currency else 0,
                "spend_currency": "USD",
                "attributed_currency": self.attributed_currency,
                "ad_days": 30,
            })
        if "FROM mart_listing_management_current" in sql:
            return _Result({
                "available": 90,
                "wfs_available": 50,
                "listing_count": 1,
                "refreshed_at": None,
            })
        raise AssertionError(f"Unexpected query: {sql}")


def test_acos_uses_attributed_sales_not_total_sales() -> None:
    session = _Session()
    data = read_sku_metrics(
        session, account="test-account", sku="TEST-SKU",
        market_score=8, rule_version=1, rules=DEFAULT_RULES,
        as_of=date(2026, 11, 1),
    )
    period = data["periods"]["30"]
    assert period["acos"] == 25
    assert period["ad_spend_ratio"] == 10
    assert period["attributed_sales"] == 400
    assert period["complete"] is True
    assert data["score"]["status"] == "evaluated"
    assert any("ad.attributed_sales_amount" in sql for sql in session.queries)


def test_unknown_attribution_currency_never_produces_an_acos_score() -> None:
    session = _Session(attributed_currency=None)
    data = read_sku_metrics(
        session, account="test-account", sku="TEST-SKU",
        market_score=8, rule_version=1, rules=DEFAULT_RULES,
        as_of=date(2026, 11, 1),
    )
    period = data["periods"]["30"]
    assert period["acos"] is None
    assert period["ad_spend_ratio"] == 10
    assert period["complete"] is False
    assert data["score"]["status"] == "insufficient_data"
