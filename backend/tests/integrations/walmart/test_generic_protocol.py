"""Offline v4 tests: no real cloud identities, Walmart calls or database access."""

from __future__ import annotations

import copy
import json
import time
from collections.abc import Mapping
from typing import Any

import httpx
import pytest

from app.integrations.walmart import scf_runtime
from app.integrations.walmart.contract_signing import ContractSigner, ContractVerifier
from app.integrations.walmart.contracts import ContractError, ContractRegistry
from app.integrations.walmart.generic_client import WalmartGenericClient, make_generic_client
from app.integrations.walmart.generic_executor import execute_generic_event
from app.integrations.walmart.generic_protocol import MAX_EVENT_BYTES, prepare_generic
from app.integrations.walmart.generic_transport import WalmartGenericTransport
from app.integrations.walmart.https_transport import ClientCredentials, TransportRejected
from app.integrations.walmart.planner import STORE_ROUTES
from app.integrations.walmart.scf_bridge import GatewayRejected
from app.integrations.walmart.tencent_api import (
    MAX_SCF_RESPONSE_BYTES,
    TemporaryTencentIdentity,
    TencentApiClient,
    TencentApiRejected,
)
from app.integrations.walmart.tencent_scf import TencentScfInvoker

STORE = "CN2601"
FUNCTION = "szzsbj-walmart-cn2601-executor"
PATH = "/v3/unregistered/future-api"
FAKE_CLIENT_ID = "synthetic-client-identifier"
FAKE_CLIENT_SECRET = "synthetic-client-secret-value"
FAKE_TOKEN = "synthetic-access-token-value"


class Secrets:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def get_store_credentials(self, store_code: str) -> ClientCredentials:
        self.calls.append(store_code)
        assert store_code == STORE
        return ClientCredentials(FAKE_CLIENT_ID, FAKE_CLIENT_SECRET)


@pytest.fixture
def signer() -> ContractSigner:
    return ContractSigner.generate(kid="generic-test", registry=ContractRegistry(()))


def verifier(signer: ContractSigner) -> ContractVerifier:
    return ContractVerifier.from_env_json(
        json.dumps({signer.kid: signer.public_key_b64()}),
        bound_store=STORE,
        bound_function=FUNCTION,
    )


class LocalInvoker:
    def __init__(self, signer: ContractSigner, transport: WalmartGenericTransport) -> None:
        self.verifier = verifier(signer)
        self.transport = transport
        self.events: list[dict[str, Any]] = []

    def invoke(self, payload: Mapping[str, Any]) -> Mapping[str, Any]:
        self.events.append(dict(payload))
        return execute_generic_event(
            payload, verifier=self.verifier, store=STORE, transport=self.transport
        )


def make_local(
    signer: ContractSigner, handler: Any
) -> tuple[WalmartGenericClient, LocalInvoker, Secrets]:
    secrets = Secrets()

    def http(request: httpx.Request) -> httpx.Response:
        assert request.url.host == "marketplace.walmartapis.com"
        if request.url.path == "/v3/token":
            assert request.method == "POST"
            return httpx.Response(200, json={"access_token": FAKE_TOKEN})
        return handler(request)

    transport = WalmartGenericTransport(
        bound_store=STORE, secret_resolver=secrets, transport=httpx.MockTransport(http)
    )
    invoker = LocalInvoker(signer, transport)
    return (
        WalmartGenericClient(signer=signer, routes={STORE: (FUNCTION, invoker)}),
        invoker,
        secrets,
    )


@pytest.mark.parametrize("method", ["GET", "POST", "PUT", "PATCH", "DELETE"])
def test_new_operation_requires_no_registration_or_approval(
    signer: ContractSigner, method: str
) -> None:
    body = None if method == "GET" else {"arbitraryFutureField": [1, "value"]}

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == method
        assert request.url.path == PATH
        assert request.url.params.get_list("filter") == ["a", "b"]
        assert request.headers["WM_SEC.ACCESS_TOKEN"] == FAKE_TOKEN
        assert "authorization" not in request.headers
        if body is not None:
            assert json.loads(request.content) == body
        return httpx.Response(200, json={"result": "ok"})

    client, invoker, secrets = make_local(signer, handler)
    result = client.call(STORE, method, PATH, query={"filter": ["a", "b"]}, body=body)
    assert result.status_code == 200
    assert result.data == {"result": "ok"}
    assert result.request_id == invoker.events[0]["auth"]["request_id"]
    assert "approval_ref" not in invoker.events[0]
    assert "contract" not in invoker.events[0]
    assert secrets.calls == [STORE]


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("method", "DELETE"),
        ("path", "/v3/different"),
        ("query", {"tampered": 1}),
        ("body", {"tampered": 1}),
        ("accept", "pdf"),
        ("store_code", "CN2603"),
        ("function_name", "different-function"),
        ("version", 3),
    ],
)
def test_tampered_event_rejected_before_ssm(signer: ContractSigner, key: str, value: Any) -> None:
    _, invoker, secrets = make_local(signer, lambda _: httpx.Response(200, json={}))
    event = signer.sign_generic(store_code=STORE, function_name=FUNCTION, method="POST", path=PATH)
    event[key] = value
    result = invoker.invoke(event)
    assert result["success"] is False
    assert secrets.calls == []


def test_expiry_replay_and_wrong_store(signer: ContractSigner) -> None:
    client, invoker, secrets = make_local(signer, lambda _: httpx.Response(200, json={}))
    expired = signer.sign_generic(
        store_code=STORE,
        function_name=FUNCTION,
        method="GET",
        path=PATH,
        issued_at=int(time.time()) - 500,
    )
    assert invoker.invoke(expired)["status"] == "WALMART_SIGNATURE_EXPIRED"
    forged = signer.sign_generic(store_code=STORE, function_name=FUNCTION, method="GET", path=PATH)
    forged["auth"]["sig"] = "not-a-signature"
    assert invoker.invoke(forged)["success"] is False
    with pytest.raises(GatewayRejected, match="WALMART_STORE_GATEWAY_UNAVAILABLE"):
        client.call("CN2603", "GET", PATH)
    assert secrets.calls == []
    client.call(STORE, "POST", PATH)
    replay = copy.deepcopy(invoker.events[-1])
    assert invoker.invoke(replay)["status"] == "WALMART_SIGNATURE_REPLAYED"
    assert secrets.calls == [STORE]


@pytest.mark.parametrize(
    "path",
    [
        "https://other.example/v3/items",
        "//other.example/v3/items",
        "/v3/../items",
        "/v3/%2e%2e/items",
        "/v3/items%2fabc",
        "/v3/%252e%252e/items",
        "/v3/token",
        "/v3/%74oken",
        "/v3/items?redirect=other",
        "/v3/items#fragment",
    ],
)
def test_bad_path(path: str) -> None:
    with pytest.raises(ContractError, match="WALMART_OPERATION_INVALID"):
        prepare_generic("GET", path, {}, None, "json")


def test_shape_limits_and_reserved_credentials() -> None:
    with pytest.raises(ContractError, match="WALMART_REQUEST_TOO_LARGE"):
        prepare_generic("POST", PATH, {}, {"value": "a" * MAX_EVENT_BYTES}, "json")
    with pytest.raises(ContractError, match="WALMART_PARAMS_INVALID"):
        prepare_generic("GET", PATH, {"WM_SEC.ACCESS_TOKEN": "fake"}, None, "json")
    with pytest.raises(ContractError, match="WALMART_OPERATION_INVALID"):
        prepare_generic("CONNECT", PATH, {}, None, "json")
    assert prepare_generic("GET", "/v3/items/a%20b", {}, None, "json").path.endswith("a%20b")


def test_provider_errors_empty_response_and_pdf(signer: ContractSigner) -> None:
    response = httpx.Response(422, json={"errors": [{"message": "invalid item"}]})
    client, _, _ = make_local(signer, lambda _: response)
    result = client.call(STORE, "PATCH", PATH, body={"price": 1})
    assert result.status_code == 422
    assert result.provider_error == {"errors": [{"message": "invalid item"}]}
    response = httpx.Response(204)
    assert client.call(STORE, "DELETE", PATH).data is None
    response = httpx.Response(200, content=b"%PDF-1.4 synthetic")
    assert client.call(STORE, "POST", PATH, response_kind="pdf").pdf == response.content


@pytest.mark.parametrize(
    ("cloud_result", "expected"),
    [
        (
            {"success": False, "status": "WALMART_RESPONSE_TOO_LARGE"},
            "REJECTED:WALMART_RESPONSE_TOO_LARGE",
        ),
        ({"success": False, "status": "WALMART_TOKEN_REJECTED"}, "REJECTED:WALMART_TOKEN_REJECTED"),
        ({"success": False, "status": "secret=abc"}, "REJECTED$"),
        ({"success": False, "status": "WALMART_x"}, "REJECTED$"),
        ({"success": False, "status": "WALMART_" + "A" * 65}, "REJECTED$"),
        ({"success": False, "status": 500}, "REJECTED$"),
        ({"success": False}, "REJECTED$"),
        ("not a mapping", "REJECTED$"),
    ],
)
def test_cloud_failure_code_passthrough_only_for_plain_codes(
    signer: ContractSigner, cloud_result: Any, expected: str
) -> None:
    class CloudFails:
        def invoke(self, payload: Mapping[str, Any]) -> Any:
            return cloud_result

    client = WalmartGenericClient(signer=signer, routes={STORE: (FUNCTION, CloudFails())})
    with pytest.raises(GatewayRejected, match="^WALMART_GATEWAY_" + expected):
        client.call(STORE, "GET", PATH)


def test_zip_download_uses_no_token_and_validates_host(signer: ContractSigner) -> None:
    target = "https://marketplace.walmartapis.com/v3/download/report?sig=fake"
    archive = b"PK" + b"x" * (2 * 1024 * 1024)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v3/download/report":
            assert request.headers.get("WM_SEC.ACCESS_TOKEN") is None
            assert request.headers.get("authorization") is None
            return httpx.Response(200, content=archive)
        return httpx.Response(200, json={"downloadURL": target, "requestId": "report-1"})

    client, invoker, _ = make_local(signer, handler)
    result = client.call(STORE, "GET", PATH, response_kind="zip")
    assert result.zip_bytes == archive
    assert result.report_request_id == "report-1"
    target = "https://other.example/v3/download/report"
    event = signer.sign_generic(
        store_code=STORE, function_name=FUNCTION, method="GET", path=PATH, response_kind="zip"
    )
    assert invoker.invoke(event)["status"] == "WALMART_REPORT_DOWNLOAD_HOST_DENIED"


@pytest.mark.parametrize(
    "value", [FAKE_CLIENT_ID, FAKE_CLIENT_SECRET, FAKE_TOKEN, {"access_token": "other"}]
)
def test_provider_credential_echo_blocked(signer: ContractSigner, value: Any) -> None:
    _, invoker, _ = make_local(signer, lambda _: httpx.Response(400, json={"error": value}))
    event = signer.sign_generic(store_code=STORE, function_name=FUNCTION, method="POST", path=PATH)
    result = invoker.invoke(event)
    assert result == {"success": False, "status": "WALMART_RESPONSE_SENSITIVE"}


def test_redirect_not_followed(signer: ContractSigner) -> None:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        return httpx.Response(302, headers={"Location": "https://other.example/"})

    client, _, _ = make_local(signer, handler)
    assert client.call(STORE, "GET", PATH).status_code == 302
    assert len(calls) == 1


def test_runtime_v4_ignores_legacy_business_modes(
    signer: ContractSigner, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SZZSBJ_WALMART_BOUND_STORE", STORE)
    monkeypatch.setenv("SZZSBJ_WALMART_FUNCTION_NAME", FUNCTION)
    monkeypatch.setenv("SZZSBJ_WALMART_LIVE_MODE", "owner-approved-read-only")
    monkeypatch.setenv("SZZSBJ_WALMART_MAX_RISK", "read")
    monkeypatch.setenv("SZZSBJ_WALMART_APPROVED_READ_KEYS", "")
    monkeypatch.setenv("SZZSBJ_WALMART_EGRESS_MODE", "direct-public-readonly")
    monkeypatch.setenv("SZZSBJ_WALMART_DIRECT_PUBLIC_APPROVED", "1")
    monkeypatch.setenv(
        "SZZSBJ_WALMART_CONTRACT_PUBLIC_KEYS", json.dumps({signer.kid: signer.public_key_b64()})
    )
    monkeypatch.delenv("SZZSBJ_WALMART_REPLAY_DIR", raising=False)
    monkeypatch.delenv("SZZSBJ_WALMART_REPLAY_REDIS_URL", raising=False)
    secrets = Secrets()
    requests: list[str] = []

    def http(request: httpx.Request) -> httpx.Response:
        requests.append(request.method)
        if request.url.path == "/v3/token":
            return httpx.Response(200, json={"access_token": FAKE_TOKEN})
        return httpx.Response(200, json={"ok": True})

    def transport_factory(**kwargs: Any) -> WalmartGenericTransport:
        assert kwargs["bound_store"] == STORE
        return WalmartGenericTransport(
            bound_store=STORE, secret_resolver=secrets, transport=httpx.MockTransport(http)
        )

    monkeypatch.setattr(scf_runtime, "WalmartGenericTransport", transport_factory)
    event = signer.sign_generic(store_code=STORE, function_name=FUNCTION, method="PUT", path=PATH)
    result = scf_runtime.main_handler(event, None)
    assert result["success"] is True
    assert requests == ["POST", "PUT"]
    assert secrets.calls == [STORE]
    legacy = {"version": 1, "operation": "marketplace_call", "method": "PUT"}
    assert scf_runtime.main_handler(legacy, None)["success"] is False
    assert requests == ["POST", "PUT"]


def test_all_nine_store_routes_and_no_shared_function(
    signer: ContractSigner, tmp_path: Any
) -> None:
    keyfile = tmp_path / "synthetic.pem"
    keyfile.write_bytes(signer.private_pem())
    env = {
        "SZZSBJ_WALMART_SCF_STORE_ID_MAP": json.dumps(
            {f"synthetic-{i}": store for i, store in enumerate(STORE_ROUTES)}
        ),
        "SZZSBJ_WALMART_SCF_CVM_ROLE": "synthetic-role",
        "SZZSBJ_WALMART_SCF_TARGET_ROLE_ARN": "qcs::cam::uin/1:roleName/synthetic-role",
        "SZZSBJ_WALMART_CONTRACT_SIGNING_KEY_ID": signer.kid,
        "SZZSBJ_WALMART_CONTRACT_SIGNING_KEY_FILE": str(keyfile),
    }
    client = make_generic_client(environ=env)
    assert len(client._routes) == 9
    assert set(client._routes) == set(STORE_ROUTES)
    assert {v[0] for v in client._routes.values()} == {
        f"szzsbj-walmart-{s.lower()}-executor" for s in STORE_ROUTES
    }


def test_scf_outer_and_inner_response_limits() -> None:
    result = {"data": "x" * (2 * 1024 * 1024)}

    def http(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json={"Response": {"Result": {"InvokeResult": 0, "RetMsg": json.dumps(result)}}}
        )

    identity = TemporaryTencentIdentity("synthetic-id", "synthetic-key", "synthetic-token")
    transport = httpx.MockTransport(http)
    old = TencentApiClient(identity, transport=transport)
    with pytest.raises(TencentApiRejected, match="TC_RESPONSE_TOO_LARGE"):
        old.request("scf", {})
    new = TencentApiClient(identity, transport=transport, scf_response_limit=MAX_SCF_RESPONSE_BYTES)
    invoker = TencentScfInvoker(new, function_name=FUNCTION, result_limit=6 * 1024 * 1024)
    assert invoker.invoke({"test": True}) == result
    with pytest.raises(TencentApiRejected, match="TC_RESPONSE_TOO_LARGE"):
        new.request("ssm", {})


def test_transport_wrong_store_before_credentials() -> None:
    secrets = Secrets()
    transport = WalmartGenericTransport(bound_store=STORE, secret_resolver=secrets)
    with pytest.raises(TransportRejected, match="WALMART_STORE_NOT_AUTHORIZED"):
        transport.execute(
            store_code="CN2603", request=prepare_generic("GET", PATH, {}, None, "json")
        )
    assert secrets.calls == []
