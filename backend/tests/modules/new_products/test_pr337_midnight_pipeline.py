"""LA-midnight scoring and independent SKU projection scheduling contracts."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from app.modules.new_products.la_midnight_schedule import LosAngelesMidnightSchedule

LA = ZoneInfo("America/Los_Angeles")


def test_los_angeles_midnight_not_fixed_utc_hour():
    # Winter 00:00 PST is 08:00 UTC, summer 00:00 PDT is 07:00 UTC.
    for y, m, d, hour in [(2026, 1, 15, 8), (2026, 7, 15, 7)]:
        now = datetime(y, m, d, 0, 0, tzinfo=LA)
        last = now - timedelta(days=1)
        schedule = LosAngelesMidnightSchedule(nowfun=lambda now=now: now)
        assert schedule.remaining_estimate(last.astimezone(UTC)) == timedelta(0)
        assert now.astimezone(UTC).hour == hour


def test_dst_transitions_keep_local_midnight():
    for now in [
        datetime(2026, 3, 8, 0, 1, tzinfo=LA),
        datetime(2026, 11, 1, 0, 1, tzinfo=LA),
    ]:
        s = LosAngelesMidnightSchedule(nowfun=lambda now=now: now)
        next_target = now.astimezone(UTC) + s.remaining_estimate(now)
        local = next_target.astimezone(LA)
        assert (local.hour, local.minute) == (0, 0)
        assert local.date() == now.date() + timedelta(days=1)


def test_campaign_source_is_bounded_and_policy_scoped():
    from app.modules.new_products.pr337_daily_pipeline import _CATALOG

    sql = str(_CATALOG)
    assert "biz_walmart_ad_campaign_catalog" in sql
    assert "campaign_kind" in sql
    assert "classification_conflict" in sql
    assert "LIMIT :limit" in sql
    assert "payload_json::text" not in sql


def test_bounded_catalog_no_labels_does_not_fabricate_auto_or_manual():
    from datetime import date

    from app.modules.new_products.pr337_daily_pipeline import (
        _CATALOG,
        load_scoped_campaign_catalog,
    )

    class FakeRows:
        def mappings(self):
            return iter([])

    class FakeSource:
        def execute(self, statement, params):
            assert statement is _CATALOG
            assert params["limit"] == 200001
            return FakeRows()

    catalog, status, count = load_scoped_campaign_catalog(FakeSource(), date(2026, 11, 14))
    assert catalog == ({}, False)
    assert status == "NO_VERIFIED_TYPES"
    assert count == 0


def test_unknown_campaign_types_preserve_totals_not_auto_manual():
    from datetime import date
    from decimal import Decimal

    from app.modules.new_products.unified_ad_evidence import ad_snapshot

    snap = ad_snapshot(
        [
            {
                "advertiser_id": "a",
                "campaign_id": "c",
                "invalid_rows": 0,
                "spend": "1.50",
                "clicks": 2,
                "impressions": 5,
                "orders": 1,
                "attributed_sales": "10",
            }
        ],
        {},
        first=date(2026, 11, 1),
        cutoff=date(2026, 11, 14),
        sales_revenue=Decimal("50"),
        mapping_truncated=False,
    )
    assert snap["status"] == "classification_incomplete"
    assert snap["facts"]["ad_total_spend_usd"] == "1.50"
    assert "auto_ad_spend_usd" not in snap["facts"]
    assert "manual_ad_spend_usd" not in snap["facts"]


def test_exactly_one_scoring_schedule_even_with_legacy_flags(monkeypatch):
    from app.celery_app import create_celery_app

    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("SZZSBJ_NEW_PRODUCTS_DAILY_ENABLED", "1")
    monkeypatch.setenv("SZZSBJ_NEW_PRODUCT_TRUST_SYNC_ENABLED", "1")
    monkeypatch.setenv("SZZSBJ_NEW_PRODUCT_TRUST_MIN_CALCULATED_AT", "2026-11-15T00:00:00Z")
    monkeypatch.setenv("SZZSBJ_PR337_UNIFIED_PUBLISH_ENABLED", "1")
    monkeypatch.setenv("SZZSBJ_PR337_UNIFIED_PRODUCTION_WRITE_APPROVED", "1")
    monkeypatch.delenv("SZZSBJ_SKU_PROGRESS_REFRESH_ENABLED", raising=False)
    celery = create_celery_app(broker_url="memory://", require_broker=False)
    names = {
        k: v
        for k, v in celery.conf.beat_schedule.items()
        if "new-product" in k or v["task"].startswith("new_products.")
    }
    assert set(names) == {"new-products-la-midnight", "new-products-sku-progress-refresh"}
    assert names["new-products-la-midnight"]["task"] == "new_products.daily_score_tick"
    assert isinstance(names["new-products-la-midnight"]["schedule"], LosAngelesMidnightSchedule)
    assert names["new-products-sku-progress-refresh"] == {
        "task": "new_products.sku_progress_refresh",
        "schedule": 600.0,
    }

    monkeypatch.setenv("SZZSBJ_SKU_PROGRESS_REFRESH_ENABLED", "0")
    celery = create_celery_app(broker_url="memory://", require_broker=False)
    names = {
        k: v
        for k, v in celery.conf.beat_schedule.items()
        if "new-product" in k or v["task"].startswith("new_products.")
    }
    assert set(names) == {"new-products-la-midnight"}
    assert names["new-products-la-midnight"]["task"] == "new_products.daily_score_tick"
    assert isinstance(names["new-products-la-midnight"]["schedule"], LosAngelesMidnightSchedule)
