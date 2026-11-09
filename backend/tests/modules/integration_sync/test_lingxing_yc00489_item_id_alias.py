from datetime import date
from decimal import Decimal

import pytest

from app.modules.integration_sync.data_pages_real_sync import (
    DataPagesRealSyncError,
    _normalize_yc00489_sale_rows,
)


def _sale(
    item_id: str,
    result_type: int,
    value: str,
    *,
    store: str = "110711146247224320",
    msku: str = "YC00489-1A",
) -> dict[str, object]:
    return {
        "sid": store,
        "platform_product_id": item_id,
        "msku": msku,
        "sku": "YC00489",
        "_result_type": result_type,
        "volumeTotal": value,
    }


def _normalize(
    rows: list[dict[str, object]],
    *,
    day: date = date(2026, 11, 3),
    account: str = "primary",
) -> list[dict[str, object]]:
    return _normalize_yc00489_sale_rows(
        rows,
        source_account_ref=account,
        business_date=day,
    )


def test_old_id_only_becomes_canonical_for_all_three_salestat_metrics() -> None:
    rows = [
        _sale("20738507814", 1, "2"),
        _sale("20738507814", 2, "2"),
        _sale("20738507814", 3, "49.98"),
    ]
    normalized = _normalize(rows)
    assert len(normalized) == 3
    assert {row["platform_product_id"] for row in normalized} == {"20769904287"}
    assert {row["_result_type"]: Decimal(str(row["volumeTotal"])) for row in normalized} == {
        1: Decimal("2"),
        2: Decimal("2"),
        3: Decimal("49.98"),
    }
    assert rows[0]["platform_product_id"] == "20738507814"


def test_old_and_new_id_identical_values_are_not_added_together() -> None:
    rows = []
    for metric, value in ((1, "2"), (2, "2"), (3, "49.98")):
        rows.extend(
            (_sale("20738507814", metric, value), _sale("20769904287", metric, value))
        )
    normalized = _normalize(rows)
    assert len(normalized) == 3
    assert {row["platform_product_id"] for row in normalized} == {"20769904287"}
    total = sum(
        Decimal(str(row["volumeTotal"]))
        for row in normalized
        if row["_result_type"] == 3
    )
    assert total == Decimal("49.98")


@pytest.mark.parametrize("metric", [1, 2, 3])
def test_conflicting_id_values_fail_closed(metric: int) -> None:
    rows = [_sale("20738507814", metric, "2"), _sale("20769904287", metric, "3")]
    with pytest.raises(
        DataPagesRealSyncError, match="DATA_PAGES_YC00489_ALIAS_METRIC_CONFLICT"
    ):
        _normalize(rows)


def test_wrong_msku_on_old_id_is_rejected() -> None:
    with pytest.raises(
        DataPagesRealSyncError, match="DATA_PAGES_YC00489_ALIAS_MSKU_MISMATCH"
    ):
        _normalize([_sale("20738507814", 1, "2", msku="OTHER-1A")])


def test_other_products_and_stores_keep_original_values() -> None:
    other_store = _sale("20738507814", 1, "5", store="different-store")
    other_product = _sale("other-id", 1, "7")
    rows = [other_store, other_product]
    assert _normalize(rows) == rows


def test_rule_is_scoped_to_primary_account_and_date() -> None:
    rows = [_sale("20738507814", 1, "2")]
    assert _normalize(rows, day=date(2026, 8, 23)) == rows
    assert _normalize(rows, account="other-account") == rows


def test_single_canonical_row_is_left_at_same_metric_value() -> None:
    rows = [_sale("20769904287", 1, "3")]
    normalized = _normalize(rows)
    assert len(normalized) == 1
    assert normalized[0]["volumeTotal"] == "3"
