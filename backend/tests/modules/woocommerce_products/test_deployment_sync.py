"""Isolated Woo deployment-slice contracts. No real upstream or database writes."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4

import pytest

from app.modules.woocommerce_config.service import WooCommerceConfigError
from app.modules.woocommerce_products import catalog, task_center
from app.modules.woocommerce_products.service import (
    ListingIdentity,
    ListingLookup,
    lookup_listing_links,
)


def test_store_refs_are_namespaced_and_canonical():
    value = uuid4()
    assert task_center.parse_store_ref(task_center.store_ref(value)) == value
    with pytest.raises(WooCommerceConfigError):
        task_center.parse_store_ref(str(value))


def test_contract_matches_only_woo_read_catalog():
    interface = SimpleNamespace(
        provider="woocommerce",
        interface_key="woocommerceProducts",
        method="GET",
        handler_key=task_center.HANDLER_KEY,
        endpoint_path=task_center.ENDPOINT,
        request_kind="offset_page",
    )
    assert task_center.is_woo_interface(interface)
    interface.method = "POST"
    assert not task_center.is_woo_interface(interface)


def test_incremental_pagination_parameters_and_window_validation():
    start = datetime(2026, 11, 27, 0, 0, tzinfo=UTC)
    end = start + timedelta(days=1)
    item = {
        "id": 1,
        "name": "Synthetic",
        "price": "10.00",
        "date_modified_gmt": "2026-11-27T12:00:00",
    }

    def fake(host, addresses, key, secret, path):
        if "settings/" in path:
            return {"value": "USD"}, None, None
        params = parse_qs(urlsplit(path).query)
        assert params["modified_after"] == [start.isoformat()]
        assert params["modified_before"] == [end.isoformat()]
        assert params["dates_are_gmt"] == ["true"]
        return [item], "1", "1"

    with (
        patch.object(catalog, "_resolve_public_ips", return_value=["8.8.8.8"]),
        patch.object(catalog, "request_json", side_effect=fake),
    ):
        assert (
            len(
                catalog.fetch_catalog(
                    "https://example.com",
                    "fake-key",
                    "fake-secret",
                    modified_after=start,
                    modified_before=end,
                )[1]
            )
            == 1
        )
        item["date_modified_gmt"] = "2026-11-26T00:00:00"
        with pytest.raises(WooCommerceConfigError, match="WINDOW_NOT_HONORED"):
            catalog.fetch_catalog(
                "https://example.com",
                "fake-key",
                "fake-secret",
                modified_after=start,
                modified_before=end,
            )


def test_incremental_empty_window_valid():
    start = datetime(2026, 11, 27, tzinfo=UTC)
    with (
        patch.object(catalog, "_resolve_public_ips", return_value=["8.8.8.8"]),
        patch.object(
            catalog, "request_json", side_effect=[({"value": "USD"}, None, None), ([], "0", "0")]
        ),
    ):
        assert catalog.fetch_catalog(
            "https://example.com",
            "fake-key",
            "fake-secret",
            modified_after=start,
            modified_before=start + timedelta(hours=1),
        ) == ("USD", [])


def test_window_retry_does_not_drift_and_manual_is_full():
    a = datetime(2026, 11, 27, tzinfo=UTC)
    b = a + timedelta(hours=1)
    run = SimpleNamespace(trigger_type="retry", window_start=a, window_end=b)
    assert task_center.freeze_window(None, run) == (a, b)
    run.trigger_type = "manual"
    assert task_center.freeze_window(None, run)[0] is None


def test_schedule_overlap_and_periodic_full_reconciliation():
    now = datetime.now(UTC).replace(microsecond=0)
    run = SimpleNamespace(trigger_type="schedule", source_account_ref="woo:test")

    class Session:
        def __init__(self, values):
            self.values = iter(values)

        def scalar(self, _):
            return next(self.values)

    last = now - timedelta(hours=1)
    start, end = task_center.freeze_window(Session([now - timedelta(days=1), last]), run)
    assert start == last - task_center.OVERLAP and end >= now
    assert task_center.freeze_window(Session([now - timedelta(days=8), last]), run)[0] is None
    assert task_center.freeze_window(Session([None, None]), run)[0] is None


def test_empty_links_no_database_and_exact_key_validation():
    assert lookup_listing_links(None, []) == []
    i = ListingIdentity(source_account_ref="A", store_id="00001", item_id="00002")
    assert ListingLookup(identities=[i]).identities[0].item_id == "00002"
    with pytest.raises(ValueError):
        ListingIdentity(source_account_ref="", store_id="S", item_id="I")
