"""Never fabricate advertising spend or attributed-sales currency."""

from __future__ import annotations

from app.modules.integration_sync.data_pages_real_sync import (
    _explicit_ad_amount_currency,
    _explicit_ad_spend_currency,
)


def test_explicit_source_currency_only() -> None:
    assert _explicit_ad_spend_currency({}) is None
    assert _explicit_ad_amount_currency({}, attributed=True) is None
    assert _explicit_ad_spend_currency({"adSpendCurrencyCode": "usd"}) == "USD"
    assert _explicit_ad_amount_currency(
        {"attributedSalesCurrencyCode": "usd"}, attributed=True
    ) == "USD"
    assert _explicit_ad_amount_currency(
        {"currencyCode": "USD"}, attributed=True
    ) == "USD"
    assert _explicit_ad_spend_currency({"adSpendCurrencyCode": "unknown"}) is None
    assert _explicit_ad_amount_currency(
        {"attributedSalesCurrencyCode": "unknown"}, attributed=True
    ) is None
