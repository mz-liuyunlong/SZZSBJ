"""Offline tests only: never contact STS, SCF, SSM or Walmart."""

from __future__ import annotations

import pytest

from app.core.api import ApiError
from app.integrations.walmart.client import WalmartResult
from app.modules.walmart_scf import service


class FakeGateway:
    def __init__(self, *, data: object | None = None) -> None:
        self.calls: list[tuple[str, str, dict[str, int]]] = []
        self.data = {"inventory": []} if data is None else data

    def call(self, store_code: str, operation: str, *, params: dict) -> WalmartResult:
        self.calls.append((store_code, operation, params))
        return WalmartResult(status_code=200, data=self.data)


def configured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SZZSBJ_WALMART_SCF_READ_ENABLED", "1")
    monkeypatch.setenv("SZZSBJ_WALMART_SCF_APPROVED_STORES", "HK2612,HK2613")
    service._configured_gateway.cache_clear()


def test_disabled_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SZZSBJ_WALMART_SCF_READ_ENABLED", raising=False)
    with pytest.raises(ApiError, match="WALMART_SCF_READ_DISABLED"):
        service.read_wfs_inventory(
            store_code="HK2613", verified_source_account_scope=frozenset({"HK2613"})
        )


def test_cross_store_forbidden_before_network(monkeypatch: pytest.MonkeyPatch) -> None:
    configured(monkeypatch)
    fake = FakeGateway()
    with pytest.raises(ApiError, match="DATA_SCOPE_DENIED"):
        service.read_wfs_inventory(
            store_code="HK2612",
            verified_source_account_scope=frozenset({"HK2613"}),
            gateway=fake,
        )
    assert fake.calls == []


def test_unapproved_store_forbidden(monkeypatch: pytest.MonkeyPatch) -> None:
    configured(monkeypatch)
    fake = FakeGateway()
    with pytest.raises(ApiError, match="DATA_SCOPE_DENIED"):
        service.read_wfs_inventory(
            store_code="CN2601",
            verified_source_account_scope=frozenset({"CN2601"}),
            gateway=fake,
        )
    assert fake.calls == []


def test_read_only_wfs_inventory(monkeypatch: pytest.MonkeyPatch) -> None:
    configured(monkeypatch)
    fake = FakeGateway()
    result = service.read_wfs_inventory(
        store_code="HK2613",
        verified_source_account_scope=frozenset({"HK2613"}),
        limit=1,
        gateway=fake,
    )
    assert result.status_code == 200
    assert fake.calls == [("HK2613", "wfs_inventory", {"limit": 1})]


@pytest.mark.parametrize("limit", [0, 101, True, -1])
def test_invalid_limit_denied(monkeypatch: pytest.MonkeyPatch, limit: object) -> None:
    configured(monkeypatch)
    fake = FakeGateway()
    with pytest.raises(ApiError, match="VALIDATION_ERROR"):
        service.read_wfs_inventory(
            store_code="HK2613",
            verified_source_account_scope=frozenset({"HK2613"}),
            limit=limit,  # type: ignore[arg-type]
            gateway=fake,
        )
    assert fake.calls == []


def test_secret_response_denied(monkeypatch: pytest.MonkeyPatch) -> None:
    configured(monkeypatch)
    fake = FakeGateway(data={"access_token": "dummy"})
    with pytest.raises(ApiError, match="WALMART_SCF_READ_UNAVAILABLE"):
        service.read_wfs_inventory(
            store_code="HK2613",
            verified_source_account_scope=frozenset({"HK2613"}),
            gateway=fake,
        )


def test_missing_owner_config_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    configured(monkeypatch)
    monkeypatch.delenv("SZZSBJ_WALMART_SCF_CVM_ROLE", raising=False)
    monkeypatch.delenv("SZZSBJ_WALMART_SCF_TARGET_ROLE_ARN", raising=False)
    with pytest.raises(ApiError, match="WALMART_SCF_READ_UNAVAILABLE"):
        service.read_wfs_inventory(
            store_code="HK2613",
            verified_source_account_scope=frozenset({"HK2613"}),
        )
