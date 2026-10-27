"""Transport tests: fake HTTP client, no DNS, SSM, or Walmart I/O."""

from __future__ import annotations

from typing import Any

import httpx
import pytest

from app.integrations.walmart.contracts import PreparedRequest
from app.integrations.walmart.https_transport import (
    ClientCredentials,
    TransportRejected,
    WalmartHttpsTransport,
)


class FakeSecretResolver:
    def get_store_credentials(self, store_code: str) -> ClientCredentials:
        assert store_code == "HK2615"
        return ClientCredentials(client_id="fake-id", client_secret="fake-secret")


class FakeResponse:
    def __init__(self, status: int, value: dict[str, Any]) -> None:
        self.status_code = status
        self._value = value
        self.content = b"{}"

    def json(self) -> dict[str, Any]:
        return self._value


class FakeClient:
    instances: list[FakeClient] = []

    def __init__(self, **kwargs: Any) -> None:
        self.kwargs = kwargs
        self.calls: list[tuple[str, str, dict[str, Any]]] = []
        self.instances.append(self)

    def __enter__(self) -> FakeClient:
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def post(self, url: str, **kwargs: Any) -> FakeResponse:
        self.calls.append(("POST", url, kwargs))
        return FakeResponse(200, {"access_token": "synthetic-token"})

    def request(self, method: str, url: str, **kwargs: Any) -> FakeResponse:
        self.calls.append((method, url, kwargs))
        return FakeResponse(200, {"items": []})


def fake_request() -> PreparedRequest:
    return PreparedRequest(
        key="listItems",
        method="GET",
        path="/v3/items",
        query={"limit": 20},
        body=None,
        is_write=False,
    )


def test_private_proxy_and_token_isolation(monkeypatch: pytest.MonkeyPatch) -> None:
    FakeClient.instances.clear()
    monkeypatch.setattr(httpx, "Client", FakeClient)
    transport = WalmartHttpsTransport(
        proxy_by_store={"HK2615": "http://10.3.4.5:3128"},
        secret_resolver=FakeSecretResolver(),
    )
    status, data = transport.execute(store_code="HK2615", request=fake_request())
    assert status == 200
    assert data == {"items": []}
    client = FakeClient.instances[0]
    assert client.kwargs["proxy"] == "http://10.3.4.5:3128"
    assert client.kwargs["trust_env"] is False
    assert client.kwargs["follow_redirects"] is False
    assert [call[1] for call in client.calls] == [
        "https://marketplace.walmartapis.com/v3/token",
        "https://marketplace.walmartapis.com/v3/items",
    ]
    assert "WM_SEC.ACCESS_TOKEN" in client.calls[1][2]["headers"]


def test_missing_store_proxy_rejected_before_credentials() -> None:
    transport = WalmartHttpsTransport(
        proxy_by_store={"HK2615": "http://10.3.4.5:3128"},
        secret_resolver=FakeSecretResolver(),
    )
    with pytest.raises(TransportRejected, match="WALMART_PRIVATE_EGRESS_REQUIRED"):
        transport.execute(store_code="CN2502", request=fake_request())


@pytest.mark.parametrize(
    "url",
    [
        "http://43.135.153.225:3128",
        "https://10.2.3.4:3128",
        "http://localhost:3128",
        "http://127.0.0.1:3128",
        "http://user:password@10.1.2.3:3128",
        "http://10.1.2.3:3128/path",
    ],
)
def test_unsafe_proxy_rejected(url: str) -> None:
    with pytest.raises(TransportRejected, match="WALMART_PRIVATE_EGRESS_REQUIRED"):
        WalmartHttpsTransport(
            proxy_by_store={"HK2615": url},
            secret_resolver=FakeSecretResolver(),
        )


def test_no_arbitrary_hosts(monkeypatch: pytest.MonkeyPatch) -> None:
    FakeClient.instances.clear()
    monkeypatch.setattr(httpx, "Client", FakeClient)
    transport = WalmartHttpsTransport(
        proxy_by_store={"HK2615": "http://10.2.3.4:3128"},
        secret_resolver=FakeSecretResolver(),
    )
    req = PreparedRequest(
        key="bad",
        method="GET",
        path="//localhost/private",
        query={},
        body=None,
        is_write=False,
    )
    with pytest.raises(TransportRejected, match="WALMART_OPERATION_INVALID"):
        transport.execute(store_code="HK2615", request=req)
    assert FakeClient.instances == []


def test_credentials_repr_is_redacted() -> None:
    assert "fake-secret" not in repr(
        ClientCredentials(client_id="fake-id", client_secret="fake-secret")
    )
