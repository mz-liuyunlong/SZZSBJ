"""Returns read contracts only; no approval/reject/refund requests."""

from __future__ import annotations

import pytest

from app.integrations.walmart.contracts import ContractError
from app.integrations.walmart.returns_catalog import returns_read_registry


def test_returns_registry_is_read_only_and_disabled_by_default() -> None:
    registry = returns_read_registry()
    assert set(registry.keys()) == {"returns_list", "return_get"}
    assert all(not registry.get(key).enabled for key in registry.keys())
    with pytest.raises(ContractError, match="WALMART_OPERATION_NOT_APPROVED"):
        registry.prepare("returns_list")


def test_returns_list_filters_and_bounds() -> None:
    registry = returns_read_registry(approved_keys=frozenset({"returns_list"}))
    req = registry.prepare(
        "returns_list",
        params={"status": "COMPLETED", "returnType": "REFUND", "isWFSEnabled": "Y", "limit": 200},
    )
    assert req.path == "/v3/returns"
    assert req.is_write is False
    with pytest.raises(ContractError, match="WALMART_FIELD_INVALID"):
        registry.prepare("returns_list", params={"status": "REFUNDED"})
    with pytest.raises(ContractError, match="WALMART_FIELD_INVALID"):
        registry.prepare("returns_list", params={"limit": 201})
    with pytest.raises(ContractError, match="WALMART_PARAM_NOT_ALLOWED"):
        registry.prepare("returns_list", params={"url": "https://example.invalid"})


def test_return_detail_path_and_write_not_registered() -> None:
    registry = returns_read_registry(approved_keys=frozenset({"return_get"}))
    req = registry.prepare("return_get", params={"returnOrderId": "RMA/123"})
    assert req.path == "/v3/returns/RMA%2F123"
    assert req.is_write is False
    with pytest.raises(ContractError, match="WALMART_API_NOT_REGISTERED"):
        registry.prepare("refund", allow_writes=True)
