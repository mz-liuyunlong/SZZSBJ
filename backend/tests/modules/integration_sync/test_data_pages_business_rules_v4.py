import inspect
from datetime import date

from app.modules.integration_sync.data_pages_business_rules_v2 import (
    DataPagesRealSyncRunner as PageCompletenessRunner,
)
from app.modules.integration_sync.data_pages_business_rules_v4 import (
    DataPagesRealSyncRunner,
    _order_matches_refund_identifiers,
    _refund_purchase_query_dates,
)


def test_refund_purchase_query_dates_cover_local_day_and_following_china_day() -> None:
    rows = [
        {"purchaseTimeLocale": "2026-08-31 23:30:00"},
        {"purchaseTimeLocale": "2026-07-16 12:00:00"},
        {"purchaseTimeLocale": None},
    ]

    assert _refund_purchase_query_dates(rows) == (
        date(2026, 7, 16),
        date(2026, 7, 17),
        date(2026, 8, 31),
        date(2026, 9, 1),
    )


def test_order_matches_refund_identifiers_by_platform_order_no() -> None:
    row = {
        "reference_no": "customer-elsewhere",
        "item_info": [{"platform_order_no": "purchase-123"}],
    }

    assert _order_matches_refund_identifiers(
        row,
        {"purchase-123"},
        {"customer-123"},
    )


def test_order_matches_refund_identifiers_by_reference_no() -> None:
    row = {
        "reference_no": "customer-123",
        "item_info": [{"platform_order_no": "purchase-elsewhere"}],
    }

    assert _order_matches_refund_identifiers(
        row,
        {"purchase-123"},
        {"customer-123"},
    )


def test_order_matches_refund_identifiers_rejects_unrelated_order() -> None:
    row = {
        "reference_no": "other-customer",
        "item_info": [{"platform_order_no": "other-purchase"}],
    }

    assert not _order_matches_refund_identifiers(
        row,
        {"purchase-123"},
        {"customer-123"},
    )


def test_daily_sales_scope_includes_positive_ads_and_refund_only_keys() -> None:
    source = inspect.getsource(PageCompletenessRunner._refresh_daily_sales_mart)

    assert "having sum(coalesce(ad_spend_amount,0))>0" in source
    assert '"select business_date_la,source_account_ref,store_id,item_id from r),"' in source
    assert "sale_stat_union_positive_ad_spend_union_refund" in source


def test_v4_uses_shared_refund_aware_daily_sales_refresh() -> None:
    assert "_refresh_daily_sales_mart" not in DataPagesRealSyncRunner.__dict__
