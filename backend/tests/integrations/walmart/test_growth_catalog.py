"""Review Accelerator item list: the one reviewed read-semantic POST (empty body only)."""

from __future__ import annotations

import pytest

from app.integrations.walmart.contract_signing import READ_SEMANTIC_NON_GET_KEYS, risk_for
from app.integrations.walmart.contracts import ContractError
from app.integrations.walmart.growth_catalog import (
    REVIEW_ACCELERATOR_ITEMS_KEY,
    REVIEW_ACCELERATOR_ITEMS_PATH,
    growth_read_registry,
)
from app.integrations.walmart.unified_api import load_unified_registry, reviewed_registry

KEY = REVIEW_ACCELERATOR_ITEMS_KEY


def test_growth_registry_has_one_operation_disabled_by_default() -> None:
    registry = growth_read_registry()
    assert set(registry.keys()) == {KEY}
    operation = registry.get(KEY)
    assert (operation.method, operation.path) == ("POST", REVIEW_ACCELERATOR_ITEMS_PATH)
    assert operation.enabled is False and operation.is_write is False
    with pytest.raises(ContractError, match="WALMART_OPERATION_NOT_APPROVED"):
        registry.prepare(KEY, body={})
    with pytest.raises(ContractError, match="WALMART_APPROVED_OPERATION_UNKNOWN"):
        growth_read_registry(approved_keys=frozenset({"review_accelerator_enroll"}))


def test_items_accepts_only_scroll_id_and_an_empty_body() -> None:
    registry = growth_read_registry(approved_keys=frozenset({KEY}))
    request = registry.prepare(KEY, params={"scrollId": "*"}, body={})
    assert (request.method, request.path) == ("POST", REVIEW_ACCELERATOR_ITEMS_PATH)
    assert dict(request.query) == {"scrollId": "*"} and request.body == {}
    assert request.is_write is False
    # Body is pinned: no filters, no missing body, no arrays.
    with pytest.raises(ContractError, match="WALMART_BODY_FIELD_NOT_ALLOWED"):
        registry.prepare(KEY, params={"scrollId": "*"}, body={"status": "ENROLLED"})
    with pytest.raises(ContractError):
        registry.prepare(KEY, params={"scrollId": "*"}, body=None)
    with pytest.raises(ContractError):
        registry.prepare(KEY, params={"scrollId": "*"}, body=[])
    with pytest.raises(ContractError, match="WALMART_PARAM_NOT_ALLOWED"):
        registry.prepare(KEY, params={"scrollId": "*", "limit": 10}, body={})


def test_risk_is_read_on_both_sides_and_registered_in_reviewed_registry() -> None:
    assert READ_SEMANTIC_NON_GET_KEYS == frozenset({KEY})
    assert risk_for("POST", KEY) == "read"
    assert risk_for("POST", "wfs_inbound_preview") == "write"
    assert risk_for("PUT", KEY) == "read"  # key-based exception; the contract pins POST anyway
    operation = reviewed_registry().get(KEY)
    assert operation.family == "growth" and operation.permission == "action:walmart:growth:read"
    assert operation.risk == "read"
    unified = load_unified_registry(frozenset({KEY}))
    assert unified.get(KEY).enabled is True and unified.get(KEY).is_write is False
