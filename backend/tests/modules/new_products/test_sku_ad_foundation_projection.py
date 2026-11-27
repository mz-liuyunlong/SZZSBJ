from datetime import UTC, datetime
from decimal import Decimal

import pytest

from app.modules.new_products import sku_ad_foundation_projection as p


def test_productlist_development_date_and_redaction():
    row = {
        "id": 123,
        "sku": "S",
        "create_time": 1541575627,
        "update_time": 0,
        "open_status": 0,
        "cg_price": "2.30",
        "token": "secret-value",
        "future_field": {"x": [1, 2]},
    }
    snap, quotes, tiers, countries = p.project_sku(row, "productList")
    assert snap["source_created_at"] == datetime.fromtimestamp(1541575627, UTC)
    assert snap["source_updated_at"] is None
    assert snap["source_open_status"] == 0
    assert snap["source_purchase_price_amount"] == Decimal("2.30")
    assert snap["payload_json"]["future_field"] == row["future_field"]
    assert snap["payload_json"]["token"] == "[REDACTED]"
    assert (
        snap["source_payload_hash"]
        == p.project_sku(dict(reversed(list(row.items()))), "productList")[0]["source_payload_hash"]
    )
    assert not quotes and not tiers and not countries


def test_supplier_tiers_and_country_fields():
    row = {
        "id": "1",
        "supplier_quote": [
            {
                "psq_id": 2,
                "supplier_id": 5,
                "supplier_name": "A",
                "cg_price": "3.00",
                "quotes": [
                    {
                        "currency": "CNY",
                        "is_tax": 1,
                        "tax_rate": "0.13",
                        "step_prices": [
                            {"moq": 0, "price": "2.50", "price_with_tax": "2.825"},
                            {"moq": 100, "price": "2.20"},
                        ],
                    }
                ],
            }
        ],
        "product_logistics_relation": [
            {"US_cg_transport_costs": "2.10", "US_currency": "USD", "GB_bg_tax_rate": "0.2"}
        ],
    }
    snap, quotes, tiers, countries = p.project_sku(row, "batchGetProductInfo")
    assert len(quotes) == 1 and len(tiers) == 2 and len(countries) == 2
    assert tiers[0]["moq"] == 0 and tiers[1]["moq"] == 100
    assert all(t["supplier_quote_id"] == quotes[0]["id"] for t in tiers)
    assert tiers[0]["price_with_tax_amount"] == Decimal("2.825")
    assert {x["country_code"] for x in countries} == {"GB", "US"}
    assert snap["payload_json"] == row


def test_bad_numeric_does_not_invent_value():
    assert p.number("NaN", 18, 4) is None
    assert p.number("1e10000", 18, 4) is None
    assert p.number("0.1234567", 18, 4) is None
    assert p.integer(True) is None
    assert p.epoch_seconds(1541575627000) is None
    snap, *_ = p.project_sku({"id": "1", "cg_price": "invalid"}, "productList")
    assert snap["source_purchase_price_amount"] is None
    assert snap["payload_json"]["cg_price"] == "invalid"


def test_ad_extension_preserves_all_raw_and_zero():
    row = {
        "advertiserId": "1",
        "campaignId": "2",
        "adGroupId": "3",
        "adItemId": "4",
        "itemId": "5",
        "campaignStatus": "enabled",
        "adGroupStatus": "enabled",
        "adStatus": "enabled",
        "reviewStatus": "approved",
        "bid": "0.85",
        "suggestedBid": None,
        "aov": "0",
        "cpa": "2.5",
        "ntbRevenue": "0",
        "appliedTemplate": [],
        "futureMetric": "x",
    }
    config, metrics = p.project_ad(row)
    assert config["bid_amount"] == Decimal("0.85")
    assert config["suggested_bid_amount"] is None
    assert metrics["aov_amount"] == 0 and metrics["cpa_amount"] == Decimal("2.5")
    assert config["payload_json"] == metrics["payload_json"] == row
    assert config["applied_template_json"] == []
    with pytest.raises(ValueError, match="IDENTITY_INCOMPLETE"):
        p.project_ad({**row, "itemId": None})


def test_shapes_and_duplicates():
    row = {"id": 1}
    assert p.sku_payload_rows({"data": [row]}, "productList") == [row]
    assert p.sku_payload_rows({"productList": {"data": [row]}}, "productList") == [row]
    with pytest.raises(ValueError, match="MEMBERSHIP_INVALID"):
        p.sku_payload_rows({"data": [row, row]}, "batchGetProductInfo")
    for data in ([row], {"list": [row]}, {"rows": [row]}, {"data": [row]}):
        assert p.ad_payload_rows({"data": data}) == [row]


def test_mappings_match_0100_columns():
    for fields in p.SKU_FIELDS.values():
        assert set(fields.values()) <= set(p.models.LingxingSkuSourceSnapshot_table.c.keys())
    assert set(p.AD_CONFIG_FIELDS.values()) <= set(
        p.models.WalmartAdItemConfigExtension_table.c.keys()
    )
    assert set(p.AD_METRIC_FIELDS.values()) <= set(
        p.models.WalmartAdItemDailyExtension_table.c.keys()
    )


def test_listing_ad_status_requires_verified_coverage_and_freshness():
    now = datetime(2026, 11, 27, tzinfo=UTC)
    earlier = datetime(2026, 11, 26, tzinfo=UTC)
    row = dict(
        source_observed_at=now,
        source_account_status_raw="1",
        campaign_status_raw="live",
        ad_group_status_raw="enabled",
        ad_status_raw="enabled",
        review_status_raw="approved",
    )
    kw = dict(
        coverage_verified=True,
        account_mapping_verified=True,
        observed_after=earlier,
        checked_at=now,
    )
    assert p.evaluate_listing_ad_status([row], **kw)[0] is True
    assert p.evaluate_listing_ad_status([dict(row, ad_status_raw="disabled")], **kw)[0] is False
    assert p.evaluate_listing_ad_status([dict(row, review_status_raw=None)], **kw)[0] is None
    assert (
        p.evaluate_listing_ad_status([row], **dict(kw, account_mapping_verified=False))[0] is None
    )
    assert p.evaluate_listing_ad_status([], **dict(kw, coverage_verified=False))[0] is None
    assert (
        p.evaluate_listing_ad_status(
            [dict(row, source_observed_at=datetime(2026, 11, 1, tzinfo=UTC))], **kw
        )[0]
        is None
    )
