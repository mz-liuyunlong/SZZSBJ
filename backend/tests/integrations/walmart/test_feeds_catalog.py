"""Walmart feed monitoring contracts: offline only, no seller credentials."""

from __future__ import annotations

import pytest

from app.integrations.walmart.contracts import ContractError
from app.integrations.walmart.feeds_catalog import feed_monitor_registry


def test_feed_monitoring_disabled_by_default() -> None:
    registry = feed_monitor_registry()
    assert registry.keys() == ("feed_item_status", "feed_status_list")
    with pytest.raises(ContractError, match="WALMART_OPERATION_NOT_APPROVED"):
        registry.prepare("feed_status_list")


def test_feed_status_list_filters() -> None:
    registry = feed_monitor_registry(approved_keys=frozenset({"feed_status_list"}))
    req = registry.prepare("feed_status_list", params={"limit": 50, "offset": 0})
    assert req.method == "GET"
    assert req.path == "/v3/feeds"
    assert req.query == {"limit": 50, "offset": 0}
    with pytest.raises(ContractError, match="WALMART_PARAM_NOT_ALLOWED"):
        registry.prepare("feed_status_list", params={"feedType": "MP_ITEM"})


def test_feed_item_status_path_encoding() -> None:
    registry = feed_monitor_registry(approved_keys=frozenset({"feed_item_status"}))
    req = registry.prepare(
        "feed_item_status",
        params={"feedId": "123@AU", "includeDetails": True, "offset": 0, "limit": 50},
    )
    assert req.path == "/v3/feeds/123%40AU"
    assert req.is_write is False


def test_feed_monitoring_rejects_unknown_or_oversized_args() -> None:
    registry = feed_monitor_registry(approved_keys=frozenset({"feed_item_status"}))
    with pytest.raises(ContractError, match="WALMART_FIELD_INVALID"):
        registry.prepare("feed_item_status", params={"feedId": "123", "limit": 51})
    with pytest.raises(ContractError, match="WALMART_PARAM_REQUIRED"):
        registry.prepare("feed_item_status")
    with pytest.raises(ContractError, match="WALMART_PARAM_NOT_ALLOWED"):
        registry.prepare("feed_item_status", params={"feedId": "123", "url": "bad"})
