"""Unified Walmart read SDK tests. Strictly offline; no secrets/network."""

from __future__ import annotations

import hashlib
import json
from datetime import date

import pytest

from app.integrations.walmart.client import WalmartClient, WalmartResult
from app.integrations.walmart.unified_api import (
    WalmartIntegrationError,
    WalmartReadAPI,
    capability_summary,
    load_unified_registry,
)


class FakeGateway:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def execute(self, *, store_code: str, request: object, approval_ref: str | None):
        self.calls.append(request.key)
        return WalmartResult(
            status_code=200, data={"payload": {"inventory": []}, "headers": {"totalCount": 0}}
        )


def test_catalog_is_not_an_approval() -> None:
    registry = load_unified_registry()
    summary = capability_summary(registry)
    assert summary["source_capabilities"] == 192
    assert summary["physical_endpoints"] == 143
    assert summary["historical_categories"] == {"read": 120, "write": 71, "auth": 1}
    assert summary["approved_read_operations"] == 0
    client = WalmartClient(registry, allowed_stores=frozenset({"HK2615"}))
    with pytest.raises(ValueError, match="WALMART_OPERATION_NOT_APPROVED"):
        WalmartReadAPI(client).prepare("HK2615", "wfs_inventory")


def test_approved_contract_executes_via_fake_gateway() -> None:
    fake = FakeGateway()
    registry = load_unified_registry(frozenset({"wfs_inventory"}))
    client = WalmartClient(registry, allowed_stores=frozenset({"HK2615"}), gateway=fake)
    api = WalmartReadAPI(client)
    assert api.prepare("HK2615", "wfs_inventory", params={"limit": 1}).method == "GET"
    assert api.call("HK2615", "wfs_inventory").status_code == 200
    assert fake.calls == ["wfs_inventory"]
    result = api.original_worker(
        "HK2615",
        endpoints=("wfs_inventory",),
        from_date=date(2026, 10, 1),
        to_date=date(2026, 10, 2),
    )
    assert result["manifest"]["status"] == "SUCCESS"
    assert "SHA256SUMS" in result["artifacts"]


def test_custom_reviewed_openapi_is_hash_pinned(tmp_path) -> None:
    file = tmp_path / "official.json"
    file.write_text(
        json.dumps(
            {
                "openapi": "3.0.3",
                "paths": {
                    "/v3/test/read": {
                        "get": {
                            "operationId": "officialRead",
                            "parameters": [
                                {"name": "cursor", "in": "query", "schema": {"type": "string"}}
                            ],
                        }
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    digest = hashlib.sha256(file.read_bytes()).hexdigest()
    registry = load_unified_registry(
        frozenset({"officialRead"}),
        contract_file=str(file),
        contract_sha256=digest,
    )
    client = WalmartClient(registry, allowed_stores=frozenset({"HK2615"}))
    assert WalmartReadAPI(client).prepare(
        "HK2615", "officialRead", params={"cursor": "NEXT"}
    ).query == {"cursor": "NEXT"}
    with pytest.raises(ValueError, match="WALMART_PARAM_NOT_ALLOWED"):
        WalmartReadAPI(client).prepare("HK2615", "officialRead", params={"unreviewed": "x"})
    with pytest.raises(WalmartIntegrationError, match="CONTRACT_SNAPSHOT_CHANGED"):
        load_unified_registry(
            frozenset({"officialRead"}),
            contract_file=str(file),
            contract_sha256="0" * 64,
        )


def test_snapshot_write_cannot_be_approved(tmp_path) -> None:
    file = tmp_path / "official.json"
    file.write_text(
        json.dumps(
            {
                "openapi": "3.0.3",
                "paths": {"/v3/items": {"post": {"operationId": "upsertItems"}}},
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(WalmartIntegrationError, match="WALMART_WRITE_NOT_AUTHORIZED"):
        load_unified_registry(
            frozenset({"upsertItems"}),
            contract_file=str(file),
            contract_sha256=hashlib.sha256(file.read_bytes()).hexdigest(),
        )


def test_unknown_key_fails_closed() -> None:
    with pytest.raises(WalmartIntegrationError, match="WALMART_APPROVED_OPERATION_UNKNOWN"):
        load_unified_registry(frozenset({"unregistered_operation"}))


def test_offline_probe_never_needs_cloud_identity(monkeypatch, capsys) -> None:
    from app.integrations.walmart.server_probe import main

    monkeypatch.delenv("SZZSBJ_WALMART_APPROVED_READ_KEYS", raising=False)
    assert main([]) == 0
    assert '"source_capabilities": 192' in capsys.readouterr().out
    monkeypatch.setenv("SZZSBJ_WALMART_APPROVED_READ_KEYS", "wfs_inventory")
    assert main(["--store", "HK2615", "--operation", "wfs_inventory"]) == 0
    assert "PREPARED_NO_NETWORK" in capsys.readouterr().out
    assert main(["--store", "HK2615", "--operation", "wfs_inventory", "--live"]) == 2
