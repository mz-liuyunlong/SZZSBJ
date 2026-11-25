"""Walmart HTTPS transport for v4, with no business method/key allowlist.

Uses the existing per-store SSM resolver and approved egress configuration.
Only the transport owns Walmart credentials; provider errors are bounded and
checked for credential material before returning to the main server.
"""

from __future__ import annotations

import base64
import json
import logging
from typing import Any
from urllib.parse import urlsplit
from uuid import uuid4

import httpx

from app.integrations.walmart.contracts import PreparedRequest
from app.integrations.walmart.generic_protocol import prepare_generic, validate_path
from app.integrations.walmart.https_transport import (
    MAX_ERROR_RESPONSE_BYTES,
    MAX_PDF_RESPONSE_BYTES,
    MAX_RESPONSE_BYTES,
    MAX_TOKEN_RESPONSE_BYTES,
    WALMART_HOST,
    SecretResolver,
    TransportRejected,
    _bounded_bytes,
    _bounded_json,
    _bounded_json_or_text,
    _private_proxy,
)
from app.integrations.walmart.scf_bridge import _contains_secret_key

MAX_ZIP_BYTES = 3 * 1024 * 1024 + 512 * 1024


def _reject_credentials(value: Any, secrets: tuple[str, ...]) -> None:
    if _contains_secret_key(value):
        raise TransportRejected("WALMART_RESPONSE_SENSITIVE")
    # Check values, including textual provider errors, against the actual credentials.
    # Never include the matched value in the exception.

    def check(item: Any) -> bool:
        if isinstance(item, str):
            return any(secret in item for secret in secrets if secret)
        if isinstance(item, bytes):
            return any(secret.encode() in item for secret in secrets if secret)
        if isinstance(item, dict):
            return any(check(k) or check(v) for k, v in item.items())
        if isinstance(item, list):
            return any(check(v) for v in item)
        return False

    if check(value):
        raise TransportRejected("WALMART_RESPONSE_SENSITIVE")


class WalmartGenericTransport:
    def __init__(
        self,
        *,
        bound_store: str,
        secret_resolver: SecretResolver,
        proxy: str | None = None,
        timeout: float = 12.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._store = bound_store
        self._secrets = secret_resolver
        self._proxy = _private_proxy(proxy) if proxy is not None else None
        self._timeout = timeout
        self._transport = transport
        logging.getLogger("httpx").setLevel(logging.WARNING)
        logging.getLogger("httpcore").setLevel(logging.WARNING)

    def execute(self, *, store_code: str, request: PreparedRequest) -> tuple[int, Any]:
        if store_code != self._store:
            raise TransportRejected("WALMART_STORE_NOT_AUTHORIZED")
        # Defense in depth: validate only the generic transport shape, not operation keys.
        request = prepare_generic(
            request.method, request.path, request.query, request.body, request.response_kind
        )
        try:
            credentials = self._secrets.get_store_credentials(store_code)
            if not credentials.client_id or not credentials.client_secret:
                raise TransportRejected("WALMART_SECRET_UNAVAILABLE")
            basic = base64.b64encode(
                f"{credentials.client_id}:{credentials.client_secret}".encode()
            ).decode("ascii")
            with httpx.Client(
                proxy=self._proxy,
                timeout=self._timeout,
                transport=self._transport,
                follow_redirects=False,
                trust_env=False,
            ) as client:
                with client.stream(
                    "POST",
                    WALMART_HOST + "/v3/token",
                    data={"grant_type": "client_credentials"},
                    headers={
                        "Authorization": "Basic " + basic,
                        "Accept": "application/json",
                        "WM_SVC.NAME": "Walmart Marketplace",
                        "WM_QOS.CORRELATION_ID": str(uuid4()),
                    },
                ) as response:
                    if response.status_code != 200:
                        raise TransportRejected("WALMART_TOKEN_REJECTED")
                    token_data = _bounded_json(response, MAX_TOKEN_RESPONSE_BYTES)
                token = token_data.get("access_token") if isinstance(token_data, dict) else None
                if not isinstance(token, str) or not token:
                    raise TransportRejected("WALMART_TOKEN_INVALID")
                secrets = (credentials.client_id, credentials.client_secret, basic, token)
                kwargs: dict[str, Any] = {
                    "params": dict(request.query),
                    "headers": {
                        "WM_SEC.ACCESS_TOKEN": token,
                        "WM_SVC.NAME": "Walmart Marketplace",
                        "WM_QOS.CORRELATION_ID": str(uuid4()),
                        "WM_MARKET": "US",
                        "Accept": (
                            "application/pdf"
                            if request.response_kind == "pdf"
                            else "application/json"
                        ),
                    },
                }
                if request.body is not None:
                    kwargs["json"] = request.body
                with client.stream(
                    request.method, WALMART_HOST + request.path, **kwargs
                ) as response:
                    status = response.status_code
                    if not 200 <= status < 300:
                        data = _bounded_json_or_text(response, MAX_ERROR_RESPONSE_BYTES)
                    elif request.response_kind == "pdf":
                        pdf = _bounded_bytes(response, MAX_PDF_RESPONSE_BYTES)
                        if not pdf.startswith(b"%PDF"):
                            raise TransportRejected("WALMART_RESPONSE_INVALID")
                        _reject_credentials(pdf, secrets)
                        data = {
                            "content_type": "application/pdf",
                            "data_base64": base64.b64encode(pdf).decode("ascii"),
                        }
                    else:
                        raw = _bounded_bytes(response, MAX_RESPONSE_BYTES)
                        if not raw and request.response_kind == "json":
                            return status, None
                        try:
                            data = json.loads(raw)
                        except (ValueError, UnicodeError):
                            raise TransportRejected("WALMART_RESPONSE_INVALID") from None
                _reject_credentials(data, secrets)
                if 200 <= status < 300 and request.response_kind == "zip":
                    data = self._download_zip(client, data, secrets)
                return status, data
        except TransportRejected:
            raise
        except Exception:
            raise TransportRejected("WALMART_TRANSPORT_FAILURE") from None

    @staticmethod
    def _download_zip(client: httpx.Client, data: Any, secrets: tuple[str, ...]) -> dict[str, Any]:
        url = data.get("downloadURL") if isinstance(data, dict) else None
        if not isinstance(url, str) or not url:
            raise TransportRejected("WALMART_REPORT_DOWNLOAD_URL_MISSING")
        parts = urlsplit(url)
        if (
            parts.scheme != "https"
            or parts.hostname != urlsplit(WALMART_HOST).hostname
            or parts.port not in (None, 443)
            or parts.username is not None
            or parts.password is not None
            or parts.fragment
        ):
            raise TransportRejected("WALMART_REPORT_DOWNLOAD_HOST_DENIED")
        # Reject token/unsafe paths, including encoded traversal, before following the link.
        try:
            validate_path(parts.path)
        except ValueError:
            raise TransportRejected("WALMART_REPORT_DOWNLOAD_HOST_DENIED") from None
        # Walmart pre-signed download URL: no Walmart credential/header is forwarded.
        with client.stream("GET", url, headers={"Accept": "*/*"}) as response:
            if response.status_code != 200:
                raise TransportRejected("WALMART_REPORT_DOWNLOAD_FAILED")
            blob = _bounded_bytes(response, MAX_ZIP_BYTES)
        if not blob.startswith(b"PK"):
            raise TransportRejected("WALMART_RESPONSE_INVALID")
        _reject_credentials(blob, secrets)
        result = {
            "content_type": "application/zip",
            "request_id": data.get("requestId"),
            "data_base64": base64.b64encode(blob).decode("ascii"),
        }
        _reject_credentials(result, secrets)
        return result
