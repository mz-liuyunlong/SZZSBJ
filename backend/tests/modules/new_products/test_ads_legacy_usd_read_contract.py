"""PR337: legacy USD SP attribution read contracts. No database writes."""

from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from types import SimpleNamespace

from app.modules.new_products.bulk_read import _ADS_SQL
from app.modules.new_products.repository import NewProductRepository
from app.modules.new_products.rules import DEFAULT_PARAMETERS, DEFAULT_WEIGHTS
from app.modules.new_products.scoring import evaluate


def _assert_usd_guard(sql):
    compact = " ".join(str(sql).split()).replace("( ", "(").replace(" )", ")")
    assert "attributed_sales_amount IS NULL" in compact
    assert "attributed_orders IS NULL" in compact
    assert "ad_spend_currency_code IS DISTINCT FROM 'USD'" in compact
    assert "COALESCE(NULLIF(BTRIM(" in compact
    assert "attributed_sales_currency_code" in compact
    assert "ad_spend_currency_code) IS DISTINCT FROM 'USD'" in compact


def test_batch_sql_requires_usd_spend_and_preserves_missing_attribution_rejection():
    _assert_usd_guard(_ADS_SQL)


def test_single_sql_preserves_currency_and_source_fact_guards():
    class Session:
        statement = None
        params = None

        def execute(self, statement, params):
            self.statement = str(statement)
            self.params = params
            return SimpleNamespace(
                mappings=lambda: SimpleNamespace(
                    one=lambda: {
                        "n": 15,
                        "incomplete": 0,
                        "spend": Decimal("6.19"),
                        "clicks": 13,
                        "orders": Decimal("1"),
                        "revenue": Decimal("20.99"),
                        "latest_sync": None,
                    }
                )
            )

    session = Session()
    repo = object.__new__(NewProductRepository)
    repo.session = session
    result = repo.ads(
        "primary", "110711149920800256", "20874815556", date(2026, 11, 9), date(2026, 11, 14)
    )
    _assert_usd_guard(session.statement)
    assert result["orders"] == 1
    assert result["revenue"] == Decimal("20.99")
    assert session.params["item"] == "20874815556"
    assert session.params["start"] == date(2026, 11, 9)


def test_default_formula_reproduces_ad_and_trust_scores_without_changing_weights():
    facts = {
        "ad_status": "active",
        "ad_spend_usd": Decimal("6.19"),
        "ad_clicks": 13,
        "ad_orders": 1,
        "ad_revenue_usd": Decimal("20.99"),
        "valid_units_14d": 1,
        "valid_orders_14d": 1,
        "single_unit_orders_14d": 1,
    }
    cfg = {
        "weights": DEFAULT_WEIGHTS,
        "confirmedScoring": DEFAULT_PARAMETERS,
        "gradeBands": {
            "S": [9, 10],
            "A": [8, 8.99],
            "B": [7, 7.99],
            "C": [6, 6.99],
            "D": [0, 5.99],
        },
        "vetoes": [],
    }
    dimensions = evaluate(facts, cfg, 0)["dimensions"]
    assert Decimal(dimensions["ad"]).quantize(Decimal(".01"), rounding=ROUND_HALF_UP) == Decimal(
        "9.04"
    )
    assert Decimal(dimensions["trust"]).quantize(Decimal(".01"), rounding=ROUND_HALF_UP) == Decimal(
        "4.30"
    )


def test_missing_attribution_is_not_silently_turned_into_zero():
    cfg = {
        "weights": DEFAULT_WEIGHTS,
        "confirmedScoring": DEFAULT_PARAMETERS,
        "gradeBands": {
            "S": [9, 10],
            "A": [8, 8.99],
            "B": [7, 7.99],
            "C": [6, 6.99],
            "D": [0, 5.99],
        },
        "vetoes": [],
    }
    missing_revenue = {
        "ad_status": "active",
        "ad_spend_usd": Decimal("6.19"),
        "ad_clicks": 13,
        "ad_orders": 1,
        "ad_revenue_usd": None,
    }
    assert evaluate(missing_revenue, cfg, 0)["dimensions"]["ad"] is None
    missing_singles = {
        "valid_units_14d": 1,
        "valid_orders_14d": 1,
        "single_unit_orders_14d": None,
    }
    assert evaluate(missing_singles, cfg, 0)["dimensions"]["trust"] is None
