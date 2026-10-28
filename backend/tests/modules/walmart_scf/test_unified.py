"""Offline tests of store mapping, approval and bounded pagination."""

import json

import pytest

from app.core.api import ApiError
from app.integrations.walmart.client import WalmartResult
from app.modules.walmart_scf import paging, unified


class Gateway:
    def __init__(self, payloads=None):
        self.calls = []
        self.payloads = list(payloads or [{"inventory": []}])

    def call(self, store_code, operation, *, params=None):
        self.calls.append((store_code, operation, params))
        return WalmartResult(200, self.payloads.pop(0))


def setup(monkeypatch):
    monkeypatch.setenv("SZZSBJ_WALMART_SCF_READ_ENABLED", "1")
    monkeypatch.setenv(
        "SZZSBJ_WALMART_SCF_ACCOUNT_STORE_MAP",
        json.dumps({"account-a": "HK2613", "account-b": "HK2612"}),
    )
    monkeypatch.setenv("SZZSBJ_WALMART_SCF_APPROVED_READ_KEYS", "wfs_inventory")


def test_off_by_default(monkeypatch):
    monkeypatch.delenv("SZZSBJ_WALMART_SCF_READ_ENABLED", raising=False)
    with pytest.raises(ApiError, match="WALMART_SCF_READ_DISABLED"):
        unified.approved_read(
            source_account_ref="account-a",
            verified_source_account_scope=frozenset({"account-a"}),
            operation="wfs_inventory",
        )


def test_account_mapping_and_scope(monkeypatch):
    setup(monkeypatch)
    client = Gateway()
    unified.approved_read(
        source_account_ref="account-a",
        verified_source_account_scope=frozenset({"account-a"}),
        operation="wfs_inventory",
        params={"limit": 1},
        gateway=client,
    )
    assert client.calls == [("HK2613", "wfs_inventory", {"limit": 1})]
    with pytest.raises(ApiError, match="DATA_SCOPE_DENIED"):
        unified.approved_read(
            source_account_ref="account-b",
            verified_source_account_scope=frozenset({"account-a"}),
            operation="wfs_inventory",
            gateway=client,
        )
    assert len(client.calls) == 1


def test_operation_denied(monkeypatch):
    setup(monkeypatch)
    client = Gateway()
    with pytest.raises(ApiError, match="WALMART_OPERATION_NOT_APPROVED"):
        unified.approved_read(
            source_account_ref="account-a",
            verified_source_account_scope=frozenset({"account-a"}),
            operation="orders_list",
            gateway=client,
        )
    assert not client.calls


def test_secret_response_blocked(monkeypatch):
    setup(monkeypatch)
    client = Gateway([{"client_secret": "dummy"}])
    with pytest.raises(ApiError, match="WALMART_SCF_READ_UNAVAILABLE"):
        unified.approved_read(
            source_account_ref="account-a",
            verified_source_account_scope=frozenset({"account-a"}),
            operation="wfs_inventory",
            gateway=client,
        )


def test_offset_paging(monkeypatch):
    setup(monkeypatch)
    client = Gateway(
        [{"inventory": [{"id": "1"}, {"id": "2"}]}, {"inventory": [{"id": "3"}]}]
    )
    records = paging.collect_offset_pages(
        source_account_ref="account-a",
        verified_source_account_scope=frozenset({"account-a"}),
        operation="wfs_inventory",
        items_path=("inventory",),
        page_size=2,
        gateway=client,
    )
    assert len(records) == 3
    assert [x[2] for x in client.calls] == [
        {"limit": 2, "offset": 0},
        {"limit": 2, "offset": 2},
    ]


def test_no_partial_pages(monkeypatch):
    setup(monkeypatch)
    client = Gateway([{"inventory": [{"id": "1"}, {"id": "2"}]}])
    with pytest.raises(ApiError, match="WALMART_PAGE_LIMIT_REACHED"):
        paging.collect_offset_pages(
            source_account_ref="account-a",
            verified_source_account_scope=frozenset({"account-a"}),
            operation="wfs_inventory",
            items_path=("inventory",),
            page_size=2,
            max_pages=1,
            gateway=client,
        )
