"""SCF runtime setup tests; never invoke SSM or Walmart."""
from __future__ import annotations

import json

import pytest

from app.integrations.walmart.scf_runtime import ReadOnlyStorePolicy, main_handler


def test_default_runtime_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SZZSBJ_WALMART_LIVE_MODE", raising=False)
    assert main_handler({"operation": "marketplace_call"}, None) == {
        "success": False,
        "status": "WALMART_LIVE_DISABLED",
    }


def test_health_needs_no_credentials() -> None:
    assert main_handler({"operation": "health"}, None)["status"] == (
        "SAFE_RUNTIME_AVAILABLE"
    )


def test_missing_store_binding_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SZZSBJ_WALMART_LIVE_MODE", "owner-approved-read-only")
    monkeypatch.delenv("SZZSBJ_WALMART_BOUND_STORE", raising=False)
    assert main_handler({}, None)["status"] == "WALMART_STORE_BINDING_MISSING"


def test_missing_proxy_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SZZSBJ_WALMART_LIVE_MODE", "owner-approved-read-only")
    monkeypatch.setenv("SZZSBJ_WALMART_BOUND_STORE", "CN2502")
    monkeypatch.setenv("SZZSBJ_WALMART_APPROVED_READ_KEYS", "wfs_inventory")
    monkeypatch.setenv("SZZSBJ_WALMART_PRIVATE_PROXIES", json.dumps({}))
    assert main_handler({}, None)["status"] == "WALMART_RUNTIME_UNAVAILABLE"


def test_unapproved_cross_store_and_write_rejected() -> None:
    policy = ReadOnlyStorePolicy("HK2615", frozenset({"wfs_inventory"}))
    assert policy.authorize(
        store_code="HK2615",
        operation_key="wfs_inventory",
        is_write=False,
        approval_ref=None,
    )
    assert not policy.authorize(
        store_code="CN2502",
        operation_key="wfs_inventory",
        is_write=False,
        approval_ref=None,
    )
    assert not policy.authorize(
        store_code="HK2615",
        operation_key="wfs_inventory",
        is_write=True,
        approval_ref="owner-ticket",
    )
