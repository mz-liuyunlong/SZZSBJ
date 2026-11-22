"""0094 advertisement authority: categorical evidence and guarded ingestion."""

from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import UUID

from app.modules.new_products.ad_catalog_sync import _items, ingest_batch
from app.modules.new_products.rules import DEFAULT_PARAMETERS, DEFAULT_WEIGHTS
from app.modules.new_products.scoring import evaluate
from app.modules.new_products.unified_ad_evidence import ad_snapshot, campaign_kind


def test_real_lingxing_data_list_exposes_complete_payload():
    item = {
        "advertiserId": "574861",
        "campaignId": "6135050",
        "adGroupId": "7821560",
        "adItemId": "123",
        "itemId": "20968517371",
        "campaignAndTargetingType": "sponsoredProducts+auto",
        "entityCreateAt": "2026-11-12",
        "adSpend": "0",
        "numAdsShown": "79",
        "numAdsClicks": "0",
        "extraFutureField": {"preserve": True},
    }
    assert _items({"data": {"list": [item]}}) == [item]
    assert campaign_kind(item["campaignAndTargetingType"]) == "auto"
    assert _items({"data": {"list": []}}) == []


def test_ad_snapshot_observed_zero_spend_is_not_missing():
    ad = {
        "advertiser_id": "574861",
        "campaign_id": "6135050",
        "source_rows": 3,
        "invalid_rows": 0,
        "spend": Decimal("0"),
        "clicks": 0,
        "impressions": 79,
        "orders": 0,
        "attributed_sales": Decimal("0"),
    }
    result = ad_snapshot(
        [ad],
        {("574861", "6135050"): "auto"},
        first=date(2026, 11, 2),
        cutoff=date(2026, 11, 19),
        sales_revenue=Decimal("100"),
    )
    assert result["status"] == "complete"
    assert result["facts"]["auto_ad_spend_usd"] == "0"
    assert result["facts"]["ad_total_impressions"] == "79"


def test_verified_zero_spend_delivery_receives_zero_score_not_missing():
    from copy import deepcopy

    f = {
        "market_score": 7,
        "first_order_day": 3,
        "elapsed_days": 14,
        "effective_orders_14d": 10,
        "valid_orders_14d": 10,
        "valid_units_14d": 10,
        "trust_order_units_ratio_pct": Decimal("100"),
        "ad_status": "active",
        "ad_impressions": 79,
        "ad_spend_usd": Decimal("0"),
        "ad_clicks": 0,
        "ad_orders": 0,
        "ad_revenue_usd": Decimal("0"),
        "roi": Decimal("1"),
        "gross_margin_pct": Decimal("20"),
    }
    cfg = {
        "weights": deepcopy(DEFAULT_WEIGHTS),
        "confirmedScoring": deepcopy(DEFAULT_PARAMETERS),
        "gradeBands": {
            "S": [9, 10],
            "A": [8, 8.99],
            "B": [7, 7.99],
            "C": [6, 6.99],
            "D": [0, 5.99],
        },
        "penalties": [],
        "vetoes": [],
        "riskConditions": {},
    }
    result = evaluate(f, cfg, 1)
    assert result["dimensions"]["ad"] == "0"
    f["ad_impressions"] = None
    assert evaluate(f, cfg, 1)["dimensions"]["ad"] is None


class Rows:
    def __init__(self, values):
        self.values = values

    def mappings(self):
        return self

    def one(self):
        return self.values[0]

    def first(self):
        return self.values[0] if self.values else None

    def __iter__(self):
        return iter(self.values)


class FakeSource:
    def __init__(self, blobs):
        self.blobs = blobs
        self.sql = []

    def execute(self, statement, params):
        sql = str(statement)
        self.sql.append(sql)
        assert "payload_json::text" not in sql
        assert "lingxing-data-pages-walmart-ad-item-sp-list-v1" in params["policy"]
        return Rows(self.blobs[: params["limit"]])


class FakeTarget:
    def __init__(self):
        self.sql = []
        self.cursor = {"last_received_at": None, "last_blob_id": None}

    def execute(self, statement, params=None):
        sql = str(statement)
        self.sql.append(sql)
        if "FOR UPDATE" in sql:
            return Rows([self.cursor])
        if "SELECT last_received_at,last_blob_id" in sql:
            return Rows([self.cursor])
        return Rows([])


def test_ingest_preview_is_read_only_and_keeps_source_payload():
    blob = {
        "id": UUID("00000000-0000-0000-0000-000000000001"),
        "received_at": datetime(2026, 11, 19, tzinfo=UTC),
        "payload_json": {
            "data": {
                "list": [
                    {
                        "advertiserId": "574861",
                        "campaignId": "6135050",
                        "adGroupId": "7821560",
                        "adItemId": "9",
                        "itemId": "20968517371",
                        "campaignAndTargetingType": "sponsoredProducts+auto",
                        "adSpend": "0",
                        "allFieldFuture": ["kept"],
                    }
                ],
            },
        },
    }
    source, target = FakeSource([blob]), FakeTarget()
    result = ingest_batch(source, target, apply=False)
    assert result["blobs"] == 1
    assert result["history_rows"] == 1
    assert result["item_evidence"] == 1
    assert all("INSERT INTO" not in sql for sql in target.sql)


def test_malformed_payload_fails_without_advancing_cursor():
    source = FakeSource(
        [
            {
                "id": UUID("00000000-0000-0000-0000-000000000001"),
                "received_at": datetime(2026, 11, 19, tzinfo=UTC),
                "payload_json": {"data": {"unexpected": []}},
            }
        ]
    )
    target = FakeTarget()
    import pytest

    with pytest.raises(ValueError, match="SOURCE_SHAPE_UNVERIFIED"):
        ingest_batch(source, target, apply=True)
    assert not any("UPDATE biz_walmart_ad_ingest_cursor" in x for x in target.sql)
