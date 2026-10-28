"""Walmart read API factory tests, with synthetic SCF responses only."""

from __future__ import annotations

import json

import pytest

from app.integrations.walmart.scf_read_factory import make_walmart_read_api
from app.integrations.walmart.tencent_api import TemporaryTencentIdentity


class Provider:
    def get_identity(self) -> TemporaryTencentIdentity:
        return TemporaryTencentIdentity("fake-id", "fake-secret", "fake-token")


def test_factory_scopes_store_operation_and_function(monkeypatch) -> None:
    from app.integrations.walmart import scf_read_factory

    calls: list[tuple[str, str]] = []

    def fake_request(self, service, payload):
        assert service == "scf"
        calls.append((payload["FunctionName"], payload["Qualifier"]))
        event = json.loads(payload["ClientContext"])
        assert "client_secret" not in event
        return {
            "Result": {
                "InvokeResult": 0,
                "RetMsg": json.dumps(
                    {
                        "success": True,
                        "store_code": event["store_code"],
                        "api_key": event["api_key"],
                        "status_code": 200,
                        "data": {"inventory": []},
                    }
                ),
            }
        }

    monkeypatch.setattr(scf_read_factory.TencentApiClient, "request", fake_request)
    api = make_walmart_read_api(
        allowed_stores=frozenset({"HK2613"}),
        approved_read_keys=frozenset({"wfs_inventory"}),
        function_by_store={"HK2613": "szzsbj-walmart-hk2613-executor"},
        cvm_role="SZZSBJ-CVM-SCF-Invoker",
        target_role_arn=(
            "qcs::cam::uin/100013426561:roleName/SZZSBJ-CrossAccount-SCF-Invoker"
        ),
        identity_provider=Provider(),
    )
    assert api.call("HK2613", "wfs_inventory", params={"limit": 1}).status_code == 200
    assert calls == [("szzsbj-walmart-hk2613-executor", "stable")]
    with pytest.raises(ValueError, match="WALMART_STORE_FORBIDDEN"):
        api.call("HK2612", "wfs_inventory", params={"limit": 1})
    with pytest.raises(ValueError, match="WALMART_OPERATION_NOT_APPROVED"):
        api.call("HK2613", "items_list", params={"limit": 1})
    assert len(calls) == 1


def test_factory_rejects_latest_qualifier() -> None:
    with pytest.raises(ValueError, match="WALMART_STABLE_VERSION_REQUIRED"):
        make_walmart_read_api(
            allowed_stores=frozenset({"HK2613"}),
            approved_read_keys=frozenset({"wfs_inventory"}),
            function_by_store={"HK2613": "szzsbj-walmart-hk2613-executor"},
            cvm_role="SZZSBJ-CVM-SCF-Invoker",
            target_role_arn=(
                "qcs::cam::uin/100013426561:roleName/SZZSBJ-CrossAccount-SCF-Invoker"
            ),
            function_qualifier="$LATEST",
            identity_provider=Provider(),
        )
