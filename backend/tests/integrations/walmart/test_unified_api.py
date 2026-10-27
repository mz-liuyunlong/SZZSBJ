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


def test_live_probe_verifies_nonempty_wfs_data_without_exposing_records(
    monkeypatch, capsys
) -> None:
    from app.integrations.walmart import server_probe

    class NonemptyGateway:
        def execute(self, *, store_code, request, approval_ref):
            assert store_code == "HK2615"
            assert request.key == "wfs_inventory"
            return WalmartResult(
                status_code=200,
                data={"payload": {"inventory": [{"sku": "private-fixture-SKU"}]}},
            )

    registry = load_unified_registry(frozenset({"wfs_inventory"}))
    client = WalmartClient(
        registry,
        allowed_stores=frozenset({"HK2615"}),
        gateway=NonemptyGateway(),
    )
    monkeypatch.setattr(server_probe, "create_scoped_client", lambda *args, **kwargs: client)
    monkeypatch.setenv("SZZSBJ_WALMART_APPROVED_READ_KEYS", "wfs_inventory")
    monkeypatch.setenv("SZZSBJ_WALMART_LIVE_MODE", "owner-approved-read-only")
    monkeypatch.setenv("SZZSBJ_WALMART_ALLOW_PROBE", "1")
    monkeypatch.setenv("SZZSBJ_WALMART_TEST_STORE", "HK2615")
    monkeypatch.setenv("SZZSBJ_WALMART_SCF_FUNCTION_BY_STORE", '{"HK2615":"synthetic-function"}')
    assert (
        server_probe.main(
            ["--store", "HK2615", "--operation", "wfs_inventory", "--live", "--require-data"]
        )
        == 0
    )
    output = capsys.readouterr().out
    assert '"token_exchange": "VERIFIED_BY_SUCCESSFUL_GET"' in output
    assert '"data_status": "NONEMPTY"' in output
    assert '"record_count": 1' in output
    assert "private-fixture-SKU" not in output


def test_live_probe_empty_list_is_not_data_success(monkeypatch, capsys) -> None:
    from app.integrations.walmart import server_probe

    registry = load_unified_registry(frozenset({"wfs_inventory"}))
    client = WalmartClient(
        registry,
        allowed_stores=frozenset({"HK2615"}),
        gateway=FakeGateway(),
    )
    monkeypatch.setattr(server_probe, "create_scoped_client", lambda *args, **kwargs: client)
    monkeypatch.setenv("SZZSBJ_WALMART_APPROVED_READ_KEYS", "wfs_inventory")
    monkeypatch.setenv("SZZSBJ_WALMART_LIVE_MODE", "owner-approved-read-only")
    monkeypatch.setenv("SZZSBJ_WALMART_ALLOW_PROBE", "1")
    monkeypatch.setenv("SZZSBJ_WALMART_TEST_STORE", "HK2615")
    monkeypatch.setenv("SZZSBJ_WALMART_SCF_FUNCTION_BY_STORE", '{"HK2615":"synthetic-function"}')
    assert (
        server_probe.main(
            ["--store", "HK2615", "--operation", "wfs_inventory", "--live", "--require-data"]
        )
        == 3
    )
    output = capsys.readouterr().out
    assert '"status": "DATA_NOT_VERIFIED"' in output
    assert '"data_status": "EMPTY"' in output
    assert '"record_count": 0' in output


def test_response_count_does_not_treat_unknown_shape_as_verified() -> None:
    from app.integrations.walmart.server_probe import _response_record_count

    assert _response_record_count({"payload": {"inventory": [{"sku": "fixture"}]}}) == 1
    assert _response_record_count({"payload": {"inventory": []}}) == 0
    assert _response_record_count({"metadata": {"total": 10}}) is None
    assert _response_record_count({"data": ["unverified-scalar"]}) is None
