"""Direct-public v3 SCF compatibility: explicit opt-in, read-only and store-bound."""

import httpx
import pytest

from app.integrations.walmart import scf_runtime
from app.integrations.walmart.contracts import PreparedRequest
from app.integrations.walmart.direct_readonly_transport import WalmartDirectReadOnlyTransport
from app.integrations.walmart.https_transport import ClientCredentials, TransportRejected


class FakeResolver:
    def __init__(self):
        self.stores = []

    def get_store_credentials(self, store_code):
        self.stores.append(store_code)
        return ClientCredentials("test-id", "test-secret")


def request(method="GET", path="/v3/wfs/inventory", *, body=None):
    return PreparedRequest(
        key="wfs_inventory", method=method, path=path,
        query={"limit": 1}, body=body, is_write=method != "GET",
    )


def test_opt_in_reuses_existing_readonly_direct_egress(monkeypatch):
    monkeypatch.setenv("SZZSBJ_WALMART_EGRESS_MODE", "direct-public-readonly")
    monkeypatch.setenv("SZZSBJ_WALMART_DIRECT_PUBLIC_APPROVED", "1")
    monkeypatch.delenv("SZZSBJ_WALMART_PRIVATE_PROXIES", raising=False)
    resolver = FakeResolver()
    value = scf_runtime._transport_from_env(
        store="HK2613", secrets=resolver, signed=True, write_mode=False
    )
    assert isinstance(value, WalmartDirectReadOnlyTransport)
    with pytest.raises(ValueError, match="WALMART_DIRECT_WRITE_DENIED"):
        scf_runtime._transport_from_env(
            store="HK2613", secrets=resolver, signed=True, write_mode=True
        )
    monkeypatch.setenv("SZZSBJ_WALMART_DIRECT_PUBLIC_APPROVED", "0")
    with pytest.raises(ValueError, match="WALMART_DIRECT_WRITE_DENIED"):
        scf_runtime._transport_from_env(
            store="HK2613", secrets=resolver, signed=False, write_mode=False
        )


def test_direct_transport_can_call_approved_get_without_proxy(monkeypatch):
    resolver = FakeResolver()
    seen = []
    real_client = httpx.Client

    def handler(req):
        seen.append((req.method, str(req.url), dict(req.headers)))
        if req.url.path == "/v3/token":
            return httpx.Response(200, json={"access_token": "opaque"})
        return httpx.Response(200, json={"items": [{"id": 1}]})

    def client_factory(**kwargs):
        assert kwargs["trust_env"] is False and kwargs["follow_redirects"] is False
        assert "proxy" not in kwargs
        return real_client(transport=httpx.MockTransport(handler), **kwargs)

    monkeypatch.setattr(httpx, "Client", client_factory)
    transport = WalmartDirectReadOnlyTransport(
        bound_store="HK2613", secret_resolver=resolver, pass_provider_errors=True
    )
    status, payload = transport.execute(store_code="HK2613", request=request())
    assert status == 200 and payload["items"][0]["id"] == 1
    assert resolver.stores == ["HK2613"]
    assert [x[0] for x in seen] == ["POST", "GET"]
    assert all("marketplace.walmartapis.com" in x[1] for x in seen)


@pytest.mark.parametrize("denied", [
    request("POST", "/v3/fulfillment/inbound-shipments", body={"x": 1}),
    request("DELETE", "/v3/fulfillment/inbound-shipments/abc"),
    request("PATCH", "/v3/fulfillment/inbound-shipments/abc"),
    request("GET", "https://example.com/v3/wfs/inventory"),
    request("GET", "/v3/../token"),
])
def test_no_write_and_no_arbitrary_destination(denied):
    resolver = FakeResolver()
    transport = WalmartDirectReadOnlyTransport(
        bound_store="HK2613", secret_resolver=resolver
    )
    with pytest.raises(TransportRejected):
        transport.execute(store_code="HK2613", request=denied)
    assert not resolver.stores  # denied before credential access


def test_direct_transport_rejects_other_store():
    resolver = FakeResolver()
    with pytest.raises(TransportRejected, match="WALMART_STORE_NOT_AUTHORIZED"):
        WalmartDirectReadOnlyTransport(
            bound_store="HK2613", secret_resolver=resolver
        ).execute(store_code="CN2603", request=request())
    assert resolver.stores == []


def test_v3_provider_error_preserves_status_without_secrets(monkeypatch):
    real_client = httpx.Client

    def handler(req):
        if req.url.path == "/v3/token":
            return httpx.Response(200, json={"access_token": "opaque"})
        return httpx.Response(404, json={"code": "NOT_FOUND"})

    monkeypatch.setattr(
        httpx, "Client",
        lambda **kwargs: real_client(transport=httpx.MockTransport(handler), **kwargs),
    )
    status, error = WalmartDirectReadOnlyTransport(
        bound_store="HK2613", secret_resolver=FakeResolver(),
        pass_provider_errors=True,
    ).execute(store_code="HK2613", request=request())
    assert (status, error) == (404, {"code": "NOT_FOUND"})
