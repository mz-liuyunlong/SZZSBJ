"""HTTPS-only Walmart transport for a separately authorized cloud executor.

This module does not acquire or expose SSM secrets. Credentials must be injected
by an owner-controlled secret resolver inside the protected SCF runtime.
All network traffic requires a dedicated private CONNECT proxy. No direct
network fallback, redirect following, arbitrary host or local proxy discovery.
"""

from __future__ import annotations

import base64
import ipaddress
import json
import logging
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Protocol
from urllib.parse import urlsplit
from uuid import uuid4

import httpx

from app.integrations.walmart.contracts import PreparedRequest

WALMART_HOST = "https://marketplace.walmartapis.com"
MAX_RESPONSE_BYTES = 1024 * 1024
MAX_TOKEN_RESPONSE_BYTES = 16 * 1024
_PRIVATE_NETS = tuple(
    ipaddress.ip_network(network) for network in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16")
)


class TransportRejected(RuntimeError):
    """Never return remote provider body, headers, token or credentials."""


@dataclass(frozen=True, slots=True, repr=False)
class ClientCredentials:
    client_id: str
    client_secret: str

    def __repr__(self) -> str:
        return "ClientCredentials([REDACTED])"


class SecretResolver(Protocol):
    def get_store_credentials(self, store_code: str) -> ClientCredentials: ...


def _private_proxy(url: str) -> str:
    try:
        parsed = urlsplit(url)
        if parsed.scheme != "http" or not parsed.hostname or not parsed.port:
            raise ValueError
        if parsed.username or parsed.password or parsed.path or parsed.query or parsed.fragment:
            raise ValueError
        if parsed.port < 1 or parsed.port > 65535:
            raise ValueError
        address = ipaddress.ip_address(parsed.hostname)
        if address.version != 4 or not any(address in network for network in _PRIVATE_NETS):
            raise ValueError
        return url
    except (ValueError, AttributeError):
        raise TransportRejected("WALMART_PRIVATE_EGRESS_REQUIRED") from None


class WalmartHttpsTransport:
    """Runs under the cloud security owner only; never in the public API route.

    The proxy owner must enforce private network admission, dedicated egress IP,
    and CONNECT restricted to marketplace.walmartapis.com:443. This transport
    verifies Walmart TLS using the OS trust store and does not trust env proxies.
    """

    def __init__(
        self,
        *,
        proxy_by_store: Mapping[str, str],
        secret_resolver: SecretResolver,
        timeout: float = 12.0,
    ) -> None:
        self._proxies = {store: _private_proxy(url) for store, url in proxy_by_store.items()}
        self._secrets = secret_resolver
        self._timeout = timeout
        logging.getLogger("httpx").setLevel(logging.WARNING)

    def execute(self, *, store_code: str, request: PreparedRequest) -> tuple[int, Any]:
        proxy = self._proxies.get(store_code)
        if proxy is None:
            raise TransportRejected("WALMART_PRIVATE_EGRESS_REQUIRED")
        if not request.path.startswith("/v3/") or "//" in request.path or ".." in request.path:
            raise TransportRejected("WALMART_OPERATION_INVALID")
        if request.method not in {"GET", "POST", "PUT", "PATCH", "DELETE"}:
            raise TransportRejected("WALMART_OPERATION_INVALID")
        try:
            credentials = self._secrets.get_store_credentials(store_code)
            if not credentials.client_id or not credentials.client_secret:
                raise TransportRejected("WALMART_SECRET_UNAVAILABLE")
            encoded = base64.b64encode(
                f"{credentials.client_id}:{credentials.client_secret}".encode()
            ).decode()
            with httpx.Client(
                proxy=proxy, timeout=self._timeout, follow_redirects=False, trust_env=False
            ) as client:
                with client.stream(
                    "POST",
                    WALMART_HOST + "/v3/token",
                    data={"grant_type": "client_credentials"},
                    headers={
                        "Authorization": "Basic " + encoded,
                        "Accept": "application/json",
                        "WM_SVC.NAME": "Walmart Marketplace",
                        "WM_QOS.CORRELATION_ID": str(uuid4()),
                    },
                ) as token_response:
                    if token_response.status_code != 200:
                        raise TransportRejected("WALMART_TOKEN_REJECTED")
                    token_data = _bounded_json(token_response, MAX_TOKEN_RESPONSE_BYTES)
                token = token_data.get("access_token")
                if not isinstance(token, str) or not token:
                    raise TransportRejected("WALMART_TOKEN_INVALID")
                kwargs: dict[str, Any] = {
                    "params": dict(request.query),
                    "headers": {
                        "WM_SEC.ACCESS_TOKEN": token,
                        "WM_SVC.NAME": "Walmart Marketplace",
                        "WM_QOS.CORRELATION_ID": str(uuid4()),
                        "WM_MARKET": "US",
                        "Accept": "application/json",
                    },
                }
                if request.body is not None:
                    kwargs["json"] = request.body
                with client.stream(
                    request.method, WALMART_HOST + request.path, **kwargs
                ) as response:
                    if response.status_code < 200 or response.status_code >= 300:
                        raise TransportRejected("WALMART_HTTP_ERROR")
                    result = _bounded_json(response, MAX_RESPONSE_BYTES)
                if not isinstance(result, (dict, list)):
                    raise TransportRejected("WALMART_RESPONSE_INVALID")
                if _has_sensitive_keys(result):
                    raise TransportRejected("WALMART_RESPONSE_SENSITIVE")
                return response.status_code, result
        except TransportRejected:
            raise
        except Exception:
            raise TransportRejected("WALMART_TRANSPORT_FAILURE") from None


def _bounded_json(response: httpx.Response, limit: int) -> Any:
    """Bound in-memory JSON before parsing; never expose provider response text."""
    size = 0
    chunks: list[bytes] = []
    for chunk in response.iter_bytes():
        size += len(chunk)
        if size > limit:
            raise TransportRejected("WALMART_RESPONSE_TOO_LARGE")
        chunks.append(chunk)
    try:
        return json.loads(b"".join(chunks))
    except (ValueError, UnicodeDecodeError):
        raise TransportRejected("WALMART_RESPONSE_INVALID") from None


def _has_sensitive_keys(value: Any, depth: int = 0) -> bool:
    if depth > 20:
        return True
    if isinstance(value, dict):
        for key, item in value.items():
            key_name = "".join(ch for ch in str(key).lower() if ch.isalnum())
            if key_name in {"accesstoken", "refreshtoken", "clientsecret", "authorization"}:
                return True
            if _has_sensitive_keys(item, depth + 1):
                return True
    elif isinstance(value, list):
        return len(value) > 10000 or any(_has_sensitive_keys(item, depth + 1) for item in value)
    return False
