"""Four-item local preview must not be silently replaced by saved-only list."""

from __future__ import annotations

from unittest.mock import Mock

import pytest

from app.modules.new_products.service import NewProductService, local_preview_item_ids


@pytest.mark.parametrize(
    ("flags", "expected"),
    [
        (
            {
                "APP_ENV": "local",
                "PR337_LOCAL_PREVIEW_ITEM_IDS": "",
                "SZZSBJ_NEW_PRODUCT_SAVED_LIST_ONLY": "1",
            },
            "saved",
        ),
        (
            {
                "APP_ENV": "local",
                "PR337_LOCAL_PREVIEW_ITEM_IDS": "1,2,3,4",
                "SZZSBJ_NEW_PRODUCT_SAVED_LIST_ONLY": "1",
            },
            "legacy",
        ),
        (
            {
                "APP_ENV": "local",
                "PR337_LOCAL_PREVIEW_ITEM_IDS": "1,2,3,4",
                "SZZSBJ_NEW_PRODUCT_SAVED_LIST_ONLY": "0",
            },
            "legacy",
        ),
        (
            {
                "APP_ENV": "local",
                "PR337_LOCAL_PREVIEW_ITEM_IDS": "",
                "SZZSBJ_NEW_PRODUCT_SAVED_LIST_ONLY": "0",
            },
            "legacy",
        ),
        (
            {
                "APP_ENV": "production",
                "PR337_LOCAL_PREVIEW_ITEM_IDS": "",
                "SZZSBJ_NEW_PRODUCT_SAVED_LIST_ONLY": "1",
            },
            "legacy",
        ),
    ],
)
def test_preview_route_scope(monkeypatch, flags, expected):
    for name in ("APP_ENV", "PR337_LOCAL_PREVIEW_ITEM_IDS", "SZZSBJ_NEW_PRODUCT_SAVED_LIST_ONLY"):
        monkeypatch.delenv(name, raising=False)
    for key, value in flags.items():
        monkeypatch.setenv(key, value)
    service = NewProductService.__new__(NewProductService)
    service._list_saved = Mock(return_value="saved")
    service._list_legacy_live = Mock(return_value="legacy")
    result = service.list(frozenset({"primary"}), object())
    assert result == expected
    assert service._list_saved.call_count == int(expected == "saved")
    assert service._list_legacy_live.call_count == int(expected == "legacy")


def test_production_preview_rejected_by_existing_source_guard(monkeypatch):
    from app.core.api import ApiError

    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("PR337_LOCAL_PREVIEW_ITEM_IDS", "1,2,3,4")
    with pytest.raises(ApiError):
        local_preview_item_ids()


def test_preview_rejects_invalid_item_list(monkeypatch):
    from app.core.api import ApiError

    monkeypatch.setenv("APP_ENV", "local")
    monkeypatch.setenv("PR337_LOCAL_PREVIEW_ITEM_IDS", "123,123,789,456")
    with pytest.raises(ApiError):
        local_preview_item_ids()
