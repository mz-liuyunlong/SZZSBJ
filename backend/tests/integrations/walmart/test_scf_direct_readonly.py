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
        key="wfs_inventory",
        method=method,
        path=path,
        query={"limit": 1},
        body=body,
        is_write=method != "GET",
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


@pytest.mark.parametrize(
    "denied",
    [
        request("POST", "/v3/fulfillment/inbound-shipments", body={"x": 1}),
        request("DELETE", "/v3/fulfillment/inbound-shipments/abc"),
        request("PATCH", "/v3/fulfillment/inbound-shipments/abc"),
        request("GET", "https://example.com/v3/wfs/inventory"),
        request("GET", "/v3/../token"),
    ],
)
def test_no_write_and_no_arbitrary_destination(denied):
    resolver = FakeResolver()
    transport = WalmartDirectReadOnlyTransport(bound_store="HK2613", secret_resolver=resolver)
    with pytest.raises(TransportRejected):
        transport.execute(store_code="HK2613", request=denied)
    assert not resolver.stores  # denied before credential access


def review_items_request(*, body=None, key="review_accelerator_items", is_write=False):
    return PreparedRequest(
        key=key,
        method="POST",
        path="/v3/growth/reviews-accelerator/items",
        query={"scrollId": "*"},
        body=body,
        is_write=is_write,
    )


def test_direct_transport_allows_the_reviewed_read_semantic_post_with_empty_body(monkeypatch):
    """Review Accelerator items: POST, empty JSON object, scrollId only — nothing else."""
    resolver = FakeResolver()
    seen = []
    real_client = httpx.Client

    def handler(req):
        seen.append((req.method, str(req.url), req.content))
        if req.url.path == "/v3/token":
            return httpx.Response(200, json={"access_token": "opaque"})
        return httpx.Response(200, json={"items": [{"sku": "x", "reviewsCollected": 3}]})

    monkeypatch.setattr(
        httpx,
        "Client",
        lambda **kwargs: real_client(transport=httpx.MockTransport(handler), **kwargs),
    )
    transport = WalmartDirectReadOnlyTransport(bound_store="HK2613", secret_resolver=resolver)
    status, payload = transport.execute(store_code="HK2613", request=review_items_request(body={}))
    assert status == 200 and payload["items"][0]["reviewsCollected"] == 3
    method, url, content = seen[-1]
    assert method == "POST"
    assert url == (
        "https://marketplace.walmartapis.com/v3/growth/reviews-accelerator/items?scrollId=%2A"
    )
    assert content == b"{}"  # pinned empty object, never caller bytes


@pytest.mark.parametrize(
    "denied",
    [
        review_items_request(body=None),  # no body → not the reviewed shape
        review_items_request(body=["x"]),  # body must be the contract-validated object
        review_items_request(body="raw"),
        review_items_request(body={}, is_write=True),  # contract flagged as write
        review_items_request(body={}, key="wfs_inbound_preview"),  # other POSTs stay denied
        review_items_request(body={}, key="sem_campaign_create"),  # writes never
        request("POST", "/v3/growth/reviews-accelerator/items", body={}),  # wrong key
    ],
)
def test_other_posts_and_bodies_stay_denied(denied):
    resolver = FakeResolver()
    transport = WalmartDirectReadOnlyTransport(bound_store="HK2613", secret_resolver=resolver)
    with pytest.raises(TransportRejected, match="WALMART_DIRECT_WRITE_DENIED"):
        transport.execute(store_code="HK2613", request=denied)
    assert not resolver.stores


def test_direct_transport_rejects_other_store():
    resolver = FakeResolver()
    with pytest.raises(TransportRejected, match="WALMART_STORE_NOT_AUTHORIZED"):
        WalmartDirectReadOnlyTransport(bound_store="HK2613", secret_resolver=resolver).execute(
            store_code="CN2603", request=request()
        )
    assert resolver.stores == []


def test_v3_provider_error_preserves_status_without_secrets(monkeypatch):
    real_client = httpx.Client

    def handler(req):
        if req.url.path == "/v3/token":
            return httpx.Response(200, json={"access_token": "opaque"})
        return httpx.Response(404, json={"code": "NOT_FOUND"})

    monkeypatch.setattr(
        httpx,
        "Client",
        lambda **kwargs: real_client(transport=httpx.MockTransport(handler), **kwargs),
    )
    status, error = WalmartDirectReadOnlyTransport(
        bound_store="HK2613",
        secret_resolver=FakeResolver(),
        pass_provider_errors=True,
    ).execute(store_code="HK2613", request=request())
    assert (status, error) == (404, {"code": "NOT_FOUND"})


def report_download_request():
    return PreparedRequest(
        key="report_download",
        method="GET",
        path="/v3/reports/downloadReport",
        query={"requestId": "req-1"},
        body=None,
        is_write=False,
        response_kind="zip",
    )


def _client_with(monkeypatch, handler):
    real_client = httpx.Client
    monkeypatch.setattr(
        httpx,
        "Client",
        lambda **kwargs: real_client(transport=httpx.MockTransport(handler), **kwargs),
    )


def test_read_semantic_post_sends_the_contract_validated_body(monkeypatch):
    """Second batch: a read-semantic POST forwards the validated dict (re-serialized)."""
    seen = []

    def handler(req):
        seen.append((req.method, req.url.path, req.content))
        if req.url.path == "/v3/token":
            return httpx.Response(200, json={"access_token": "opaque"})
        return httpx.Response(200, json={"requestId": "req-1", "requestStatus": "RECEIVED"})

    _client_with(monkeypatch, handler)
    transport = WalmartDirectReadOnlyTransport(bound_store="HK2613", secret_resolver=FakeResolver())
    status, payload = transport.execute(
        store_code="HK2613",
        request=PreparedRequest(
            key="report_request_create",
            method="POST",
            path="/v3/reports/reportRequests",
            query={"reportType": "SETTLEMENT", "reportVersion": "v1"},
            body={"dataStartTime": "2026-10-01T00:00:00Z"},
            is_write=False,
        ),
    )
    assert status == 200 and payload["requestId"] == "req-1"
    assert seen[-1][0] == "POST" and seen[-1][2] == b'{"dataStartTime":"2026-10-01T00:00:00Z"}'


def test_report_zip_is_fetched_from_the_same_host_and_returned_base64(monkeypatch):
    import base64

    seen = []
    zip_bytes = b"PK\x03\x04" + b"0" * 100

    def handler(req):
        seen.append((req.method, str(req.url), dict(req.headers)))
        if req.url.path == "/v3/token":
            return httpx.Response(200, json={"access_token": "opaque"})
        if req.url.path == "/v3/reports/downloadReport":
            return httpx.Response(
                200,
                json={
                    "requestId": "req-1",
                    "downloadURL": "https://marketplace.walmartapis.com/v3/reports/dl/x?sig=1",
                },
            )
        assert req.url.path == "/v3/reports/dl/x"
        return httpx.Response(200, content=zip_bytes)

    _client_with(monkeypatch, handler)
    transport = WalmartDirectReadOnlyTransport(bound_store="HK2613", secret_resolver=FakeResolver())
    status, payload = transport.execute(store_code="HK2613", request=report_download_request())
    assert status == 200 and payload["content_type"] == "application/zip"
    assert base64.b64decode(payload["data_base64"]) == zip_bytes
    assert payload["request_id"] == "req-1" and payload["payload_bytes"] == len(zip_bytes)
    assert payload["download_host"] == "marketplace.walmartapis.com"
    # the pre-signed download carries no access token
    assert "WM_SEC.ACCESS_TOKEN" not in seen[-1][2]
    assert [m for m, _u, _h in seen] == ["POST", "GET", "GET"]


@pytest.mark.parametrize(
    "download, code",
    [
        ({"requestId": "r"}, "WALMART_REPORT_DOWNLOAD_URL_MISSING"),
        ({"downloadURL": "https://files.example.com/v3/x"}, "DOWNLOAD_HOST_DENIED"),
        ({"downloadURL": "http://marketplace.walmartapis.com/v3/x"}, "DOWNLOAD_HOST_DENIED"),
        ({"downloadURL": "https://marketplace.walmartapis.com/other/x"}, "DOWNLOAD_HOST_DENIED"),
        ({"downloadURL": "https://marketplace.walmartapis.com/v3/notzip"}, "RESPONSE_INVALID"),
        ({"downloadURL": "https://marketplace.walmartapis.com/v3/huge"}, "RESPONSE_TOO_LARGE"),
    ],
)
def test_report_zip_download_refuses_other_hosts_sizes_and_shapes(monkeypatch, download, code):
    from app.integrations.walmart import direct_readonly_transport as module

    monkeypatch.setattr(module, "MAX_ZIP_RESPONSE_BYTES", 64)

    def handler(req):
        if req.url.path == "/v3/token":
            return httpx.Response(200, json={"access_token": "opaque"})
        if req.url.path == "/v3/reports/downloadReport":
            return httpx.Response(200, json=download)
        if req.url.path == "/v3/huge":
            return httpx.Response(200, content=b"PK" + b"0" * 200)
        return httpx.Response(200, content=b"not a zip")

    _client_with(monkeypatch, handler)
    transport = WalmartDirectReadOnlyTransport(bound_store="HK2613", secret_resolver=FakeResolver())
    with pytest.raises(TransportRejected, match=code):
        transport.execute(store_code="HK2613", request=report_download_request())


def test_zip_response_kind_is_get_only():
    transport = WalmartDirectReadOnlyTransport(bound_store="HK2613", secret_resolver=FakeResolver())
    bad = PreparedRequest(
        key="report_request_create",
        method="POST",
        path="/v3/reports/reportRequests",
        query={},
        body={},
        is_write=False,
        response_kind="zip",
    )
    with pytest.raises(TransportRejected, match="WALMART_OPERATION_INVALID"):
        transport.execute(store_code="HK2613", request=bad)
