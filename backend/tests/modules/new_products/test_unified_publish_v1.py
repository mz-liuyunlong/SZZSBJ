"""Unified publisher: no ad-only scheduling, fail closed for missing proof."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from app.modules.new_products.unified_ad_evidence import (
    ad_snapshot,
    campaign_kind,
    verified_campaign_map,
)
from app.modules.new_products.unified_publish import local_target_approved, permission_to_write


def row(advertiser_id="31", campaign_id="101", spend="10", orders=2, clicks=20, impressions=100):
    return dict(
        advertiser_id=advertiser_id,
        campaign_id=campaign_id,
        source_rows=1,
        invalid_rows=0,
        spend=Decimal(spend),
        orders=orders,
        clicks=clicks,
        impressions=impressions,
        attributed_sales=Decimal(orders) * 10,
    )


def test_original_campaign_targeting_type_is_required():
    assert campaign_kind("sponsoredProducts+auto") == "auto"
    assert campaign_kind("sponsoredProducts+manual") == "manual"
    assert campaign_kind("video+manual") == "manual"
    assert campaign_kind("sponsoredProducts") is None
    assert campaign_kind("random+auto") is None
    mapping, conflicts = verified_campaign_map(
        [
            {
                "advertiserId": "31",
                "data": {
                    "list": [
                        {"campaignId": "101", "campaignAndTargetingType": "sponsoredProducts+auto"},
                        {
                            "campaignId": "102",
                            "campaignAndTargetingType": "sponsoredProducts+manual",
                        },
                    ]
                },
            },
        ]
    )
    assert mapping == {("31", "101"): "auto", ("31", "102"): "manual"}
    assert not conflicts


def test_conflicting_source_campaign_fails_closed():
    mapping, conflicts = verified_campaign_map(
        [
            {
                "advertiserId": "31",
                "data": [
                    {"campaignId": "101", "campaignAndTargetingType": "sponsoredProducts+auto"},
                    {"campaignId": "101", "campaignAndTargetingType": "sponsoredProducts+manual"},
                ],
            }
        ]
    )
    assert not mapping
    assert conflicts == {("31", "101")}


def test_complete_snapshot_splits_total_without_double_counting():
    result = ad_snapshot(
        [row(), row(campaign_id="102", spend="30", orders=3, clicks=60, impressions=300)],
        {("31", "101"): "auto", ("31", "102"): "manual"},
        first=date(2026, 10, 1),
        cutoff=date(2026, 11, 14),
        sales_revenue=Decimal("100"),
    )
    assert result["status"] == "complete"
    f = result["facts"]
    assert f["ad_total_spend_usd"] == "40"
    assert f["auto_ad_spend_usd"] == "10"
    assert f["manual_ad_spend_usd"] == "30"
    assert f["ad_total_spend_ratio_pct"] == "40.0"
    assert f["auto_ad_spend_ratio_pct"] == "10.0"
    assert f["manual_ad_spend_ratio_pct"] == "30.0"
    assert f["ad_total_clicks"] == "80"
    assert f["ad_total_orders"] == "5"


def test_missing_classification_does_not_invent_manual_amount():
    result = ad_snapshot(
        [row(), row(campaign_id="102", spend="20")],
        {("31", "101"): "auto"},
        first=date(2026, 10, 1),
        cutoff=date(2026, 11, 14),
        sales_revenue=None,
    )
    assert result["status"] == "classification_incomplete"
    assert result["facts"]["ad_total_spend_usd"] == "30"
    assert "auto_ad_spend_usd" not in result["facts"]
    assert "manual_ad_spend_usd" not in result["facts"]


def test_missing_currency_invalid_row_and_wfs_do_not_create_zeros():
    invalid = row()
    invalid["invalid_rows"] = 1
    result = ad_snapshot(
        [invalid],
        {("31", "101"): "auto"},
        first=date(2026, 10, 1),
        cutoff=date(2026, 11, 14),
        sales_revenue=None,
    )
    assert result["status"] == "invalid_source_currency_or_metrics"
    assert result["facts"] == {}
    result = ad_snapshot([], {}, first=None, cutoff=date(2026, 11, 14), sales_revenue=None)
    assert result["status"] == "missing_wfs_date"
    assert result["facts"] == {}
    result = ad_snapshot(
        [], {}, first=date(2026, 10, 1), cutoff=date(2026, 11, 14), sales_revenue=None
    )
    assert result["status"] == "no_source_rows_unverified"
    assert result["facts"] == {}


def test_local_write_needs_explicit_flag_and_production_extra_approval(monkeypatch):
    monkeypatch.setenv("APP_ENV", "local")
    monkeypatch.delenv("SZZSBJ_PR337_UNIFIED_PUBLISH_ENABLED", raising=False)
    assert permission_to_write() is False
    monkeypatch.setenv("SZZSBJ_PR337_UNIFIED_PUBLISH_ENABLED", "1")
    assert permission_to_write() is True
    monkeypatch.setenv("APP_ENV", "production")
    assert permission_to_write() is False
    monkeypatch.setenv("SZZSBJ_PR337_UNIFIED_PRODUCTION_WRITE_APPROVED", "1")
    assert permission_to_write() is True


def test_publisher_has_no_request_scans_or_independent_ad_task():
    from pathlib import Path

    root = Path(__file__).parents[3] / "app"
    celery = (root / "celery_app.py").read_text()
    router = (root / "modules/new_products/router.py").read_text()
    assert "new_products.ad_display_daily" not in celery + router
    assert "new_products.performance_unified_publish" in celery + router
    assert "new-products.ad_display" not in celery + router


def test_local_write_target_rejects_production_tunnel():
    assert local_target_approved("szzsbj_hybrid", "127.0.0.1")
    assert local_target_approved("szzsbj_dev", "localhost")
    assert not local_target_approved("szzsbj_app", "127.0.0.1")
    assert not local_target_approved("szzsbj_dev", "42.193.254.170")


def test_unified_dry_run_scoped_advertiser_source_and_missing_types(monkeypatch):
    """Dry run never scans RAW JSON as text; absent labels remain unknown."""
    from types import SimpleNamespace

    from app.modules.new_products import unified_ad_evidence, unified_publish

    key = ("primary", "110711146247224320", "20858150090")
    cutoff = date(2026, 11, 14)
    first = date(2026, 10, 1)

    class Rows:
        def __init__(self, records):
            self.records = records

        def mappings(self):
            return self.records

    class Source:
        def __init__(self, has_labels):
            self.has_labels = has_labels
            self.sql = []

        def execute(self, statement, params):
            sql = str(statement)
            self.sql.append(sql)
            assert "payload_json::text" not in sql
            if "FROM ods_api_raw_blobs" in sql:
                assert "gov_raw_retention_policies" in sql
                assert "lingxing-data-pages-walmart-advertiser-list-v1" in sql
                assert "b.created_at >= :since" in sql
                assert "b.payload_bytes BETWEEN 1 AND :max_payload_bytes" in sql
                assert params["row_limit"] == 1501
                if not self.has_labels:
                    return Rows([])
                return Rows(
                    [
                        {
                            "payload_json": {
                                "advertiserId": "31",
                                "data": [
                                    {
                                        "campaignId": "101",
                                        "campaignAndTargetingType": "sponsoredProducts+auto",
                                    }
                                ],
                            }
                        }
                    ]
                )
            if "JOIN fact_walmart_ad_item_sp_daily" in sql:
                return Rows(
                    [
                        {
                            "account": key[0],
                            "store": key[1],
                            "item": key[2],
                            "advertiser_id": "31",
                            "campaign_id": "101",
                            "source_rows": 1,
                            "invalid_rows": 0,
                            "spend": Decimal("10"),
                            "clicks": 20,
                            "impressions": 100,
                            "orders": 2,
                            "attributed_sales": Decimal("20"),
                        }
                    ]
                )
            if "LEFT JOIN mart_daily_sales_item_day" in sql:
                return Rows(
                    [
                        {
                            "account": key[0],
                            "store": key[1],
                            "item": key[2],
                            "n": 1,
                            "invalid": 0,
                            "revenue": Decimal("100"),
                        }
                    ]
                )
            raise AssertionError(f"Unexpected SQL: {sql[:90]}")

    class Target:
        def scalars(self, statement):
            return SimpleNamespace(
                all=lambda: [
                    SimpleNamespace(
                        source_account_ref=key[0],
                        store_id=key[1],
                        item_id=key[2],
                    )
                ]
            )

        def commit(self):
            raise AssertionError("Read-only preview cannot commit")

    monkeypatch.setattr(
        unified_publish,
        "_eligible_rows",
        lambda source, item_ids, limit: [{"key": key, "registry_id": "fake"}],
    )
    monkeypatch.setattr(
        unified_publish,
        "_candidate_scores",
        lambda source, target, keys, cutoff: {
            item: {"facts": {"first_wfs_available_date_la": first}, "evaluation": None}
            for item in keys
        },
    )

    def reject_legacy(*args, **kwargs):
        raise AssertionError("Legacy unscoped catalog was called")

    monkeypatch.setattr(unified_ad_evidence, "load_campaign_catalog", reject_legacy)
    for has_labels in (True, False):
        source = Source(has_labels)
        summary = unified_publish.publish_unified(
            source,
            Target(),
            item_ids={key[2]},
            limit=1,
            cutoff=cutoff,
            apply=False,
        )
        assert summary["dry_run"] is True
        assert summary["written"] == 0
        assert summary["catalog_rows"] == int(has_labels)
        assert len(source.sql) == 3
        sample = summary["samples"][0]
        assert sample["ad_total_spend_usd"] == "10"
        if has_labels:
            assert summary["catalog_state"] == "VERIFIED_LABELS"
            assert sample["ad_status"] == "complete"
            assert sample["auto_ad_spend_usd"] == "10"
            assert sample["manual_ad_spend_usd"] == "0"
        else:
            assert summary["catalog_state"] == "NO_VERIFIED_TYPES"
            assert sample["ad_status"] == "classification_incomplete"
            assert sample["auto_ad_spend_usd"] is None
            assert sample["manual_ad_spend_usd"] is None
