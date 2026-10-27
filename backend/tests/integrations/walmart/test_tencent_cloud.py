"""Tencent TC3 / SSM / SCF mocked tests. No external API calls."""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

from app.integrations.walmart.tencent_api import (
    TemporaryTencentIdentity,
    TencentApiClient,
    TencentApiRejected,
    tc3_headers,
)
from app.integrations.walmart.tencent_scf import ScfInvokeRejected, TencentScfInvoker
from app.integrations.walmart.tencent_ssm import SsmRejected, TencentSsmResolver


def fake_identity() -> TemporaryTencentIdentity:
    return TemporaryTencentIdentity("fixture-id", "fixture-key", "fixture-session")


def test_tc3_headers_signed_but_never_print_credentials() -> None:
    identity = fake_identity()
    headers = tc3_headers("scf", b"{}", identity, region="ap-guangzhou", timestamp=1700000000)
    assert headers["X-TC-Action"] == "Invoke"
    assert headers["X-TC-Version"] == "2018-04-16"
    assert "Signature=" in headers["Authorization"]
    assert "fixture-key" not in repr(identity)
    with pytest.raises(TencentApiRejected, match="TC_SERVICE_NOT_ALLOWED"):
        tc3_headers("other", b"{}", identity, region="ap-guangzhou", timestamp=1)


def test_tencent_transport_action_allowlist() -> None:
    calls: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if request.headers["X-TC-Action"] == "GetSecretValue":
            body: dict[str, Any] = {"Response": {"SecretString": "{}"}}
        else:
            body = {"Response": {"Result": {"InvokeResult": 0, "RetMsg": "{}"}}}
        return httpx.Response(200, json=body)

    client = TencentApiClient(fake_identity(), transport=httpx.MockTransport(respond))
    assert client.request("ssm", {"SecretName": "fixture", "VersionId": "v1"})
    assert client.request("scf", {"FunctionName": "fixture"})
    assert len(calls) == 2
    assert calls[0].url.host == "ssm.tencentcloudapi.com"
    assert calls[1].url.host == "scf.tencentcloudapi.com"
    with pytest.raises(TencentApiRejected, match="TC_SERVICE_NOT_ALLOWED"):
        client.request("other", {})


class FakeTencentApi:
    def __init__(self, response: dict[str, Any]) -> None:
        self.response = response
        self.requests: list[tuple[str, dict[str, Any]]] = []

    def request(self, service: str, payload: dict[str, Any]) -> dict[str, Any]:
        self.requests.append((service, payload))
        return self.response


def test_ssm_resolves_exact_store_secret_only() -> None:
    api = FakeTencentApi(
        {
            "SecretString": json.dumps(
                {
                    "WALMART_CLIENT_ID": "synthetic-id",
                    "WALMART_CLIENT_SECRET": "synthetic-secret",
                    "WALMART_MARKET": "us",
                }
            )
        }
    )
    secret = resolver.get_store_credentials("HK2615")
    assert secret.client_id == "synthetic-id"
    assert "synthetic-secret" not in repr(secret)
    assert api.requests == [("ssm", {"SecretName": "walmart-HK2615", "VersionId": "v1"})]
    with pytest.raises(SsmRejected, match="SSM_STORE_FORBIDDEN"):
        resolver.get_store_credentials("CN2502")


def test_scf_invokes_with_client_context() -> None:
    api = FakeTencentApi(
        {
            "Result": {
                "InvokeResult": 0,
                "RetMsg": json.dumps({"success": True, "store_code": "HK2615"}),
            }
        }

    )
    assert invoker.invoke({"operation": "health"})["success"] is True
    service, payload = api.requests[0]
    assert service == "scf"
    assert payload["InvocationType"] == "RequestResponse"
    assert json.loads(payload["ClientContext"]) == {"operation": "health"}
    assert payload["LogType"] == "None"


def test_scf_rejects_provider_errors_without_data_leak() -> None:
    api = FakeTencentApi({"Result": {"InvokeResult": 1, "RetMsg": "sensitive"}})
    invoker = TencentScfInvoker(api, function_name="szzsbj-walmart-prod-executor")
    with pytest.raises(ScfInvokeRejected, match="SCF_INVOKE_FAILED"):
        invoker.invoke({"operation": "health"})
