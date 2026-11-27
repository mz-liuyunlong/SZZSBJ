"""Strictly read-only Walmart HTTPS transport for the already approved direct-public SCF.

This intentionally supports the existing SZZSBJ direct-public-readonly deployment,
not a new write capability. TLS validation is mandatory; proxy env variables are
ignored; the remote host and base path cannot be supplied by the caller.
"""

from __future__ import annotations

import base64
from typing import Any
from urllib.parse import urlsplit
from uuid import uuid4

import httpx

from app.integrations.walmart.contract_signing import READ_SEMANTIC_NON_GET_KEYS
from app.integrations.walmart.contracts import PreparedRequest
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
    _has_sensitive_keys,
)

# On-request report ZIPs come back inside the function response (base64), so the raw file is
# capped well under the SCF 6MB response limit: ~1MB per settlement month in 2026-10 probes.
MAX_ZIP_RESPONSE_BYTES = 3 * 1024 * 1024 + 512 * 1024
_WALMART_HOSTNAME = urlsplit(WALMART_HOST).hostname


class WalmartDirectReadOnlyTransport:
    """Outbound HTTPS direct to Walmart; rejects writes before requesting a token."""

    def __init__(
        self,
        *,
        bound_store: str,
        secret_resolver: SecretResolver,
        timeout: float = 12.0,
        pass_provider_errors: bool = False,
    ) -> None:
        self._store = bound_store
        self._secrets = secret_resolver
        self._timeout = timeout
        self._pass_provider_errors = pass_provider_errors

    def execute(self, *, store_code: str, request: PreparedRequest) -> tuple[int, Any]:
        if store_code != self._store:
            raise TransportRejected("WALMART_STORE_NOT_AUTHORIZED")
        # A signed contract can authorize many reads, but cannot override the
        # operating mode: reject every non-GET even if it claims is_write=False.
        # Reviewed exception (READ_SEMANTIC_NON_GET_KEYS): a POST query whose contract pins
        # the body to a JSON object of documented filter keys (validated by ``prepare``);
        # the transport only accepts a dict body for those keys. Any other method, a body on
        # a GET, a non-dict body or a contract flagged as write is refused.
        read_semantic_post = (
            request.method == "POST"
            and request.key in READ_SEMANTIC_NON_GET_KEYS
            and isinstance(request.body, dict)
        )
        if request.is_write or (
            not read_semantic_post and (request.method != "GET" or request.body is not None)
        ):
            raise TransportRejected("WALMART_DIRECT_WRITE_DENIED")
        if (
            not request.path.startswith("/v3/")
            or "//" in request.path
            or ".." in request.path
            or any(char in request.path for char in ("?", "#", "\\", "\r", "\n"))
        ):
            raise TransportRejected("WALMART_OPERATION_INVALID")
        if not isinstance(request.query, dict) and not hasattr(request.query, "items"):
            raise TransportRejected("WALMART_OPERATION_INVALID")
        if request.response_kind not in ("json", "pdf", "zip"):
            raise TransportRejected("WALMART_OPERATION_INVALID")
        if request.response_kind == "zip" and request.method != "GET":
            raise TransportRejected("WALMART_OPERATION_INVALID")
        try:
            credentials = self._secrets.get_store_credentials(store_code)
            if not credentials.client_id or not credentials.client_secret:
                raise TransportRejected("WALMART_SECRET_UNAVAILABLE")
            basic = base64.b64encode(
                (credentials.client_id + ":" + credentials.client_secret).encode("utf-8")
            ).decode("ascii")
            with httpx.Client(
                timeout=self._timeout, follow_redirects=False, trust_env=False
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
                    token = _bounded_json(response, MAX_TOKEN_RESPONSE_BYTES).get("access_token")
                if not isinstance(token, str) or not token:
                    raise TransportRejected("WALMART_TOKEN_INVALID")
                wants_pdf = request.response_kind == "pdf"
                with client.stream(
                    "POST" if read_semantic_post else "GET",
                    WALMART_HOST + request.path,
                    params=dict(request.query),
                    # The contract-validated object re-serialized here; never raw caller bytes.
                    json=dict(request.body) if read_semantic_post else None,
                    headers={
                        "WM_SEC.ACCESS_TOKEN": token,
                        "WM_SVC.NAME": "Walmart Marketplace",
                        "WM_QOS.CORRELATION_ID": str(uuid4()),
                        "WM_MARKET": "US",
                        "Accept": "application/pdf" if wants_pdf else "application/json",
                    },
                ) as response:
                    if not 200 <= response.status_code < 300:
                        if not self._pass_provider_errors:
                            raise TransportRejected("WALMART_HTTP_ERROR")
                        error = _bounded_json_or_text(response, MAX_ERROR_RESPONSE_BYTES)
                        if _has_sensitive_keys(error):
                            raise TransportRejected("WALMART_RESPONSE_SENSITIVE")
                        return response.status_code, error
                    if wants_pdf:
                        payload = _bounded_bytes(response, MAX_PDF_RESPONSE_BYTES)
                        if not payload.startswith(b"%PDF"):
                            raise TransportRejected("WALMART_RESPONSE_INVALID")
                        return response.status_code, {
                            "content_type": "application/pdf",
                            "data_base64": base64.b64encode(payload).decode("ascii"),
                        }
                    data = _bounded_json(response, MAX_RESPONSE_BYTES)
                    if not isinstance(data, (dict, list)):
                        raise TransportRejected("WALMART_RESPONSE_INVALID")
                    if _has_sensitive_keys(data):
                        raise TransportRejected("WALMART_RESPONSE_SENSITIVE")
                    if request.response_kind == "zip":
                        return self._fetch_report_zip(client, response.status_code, data)
                    return response.status_code, data
        except TransportRejected:
            raise
        except Exception:
            raise TransportRejected("WALMART_TRANSPORT_FAILURE") from None

    @staticmethod
    def _fetch_report_zip(client: httpx.Client, status: int, data: Any) -> tuple[int, Any]:
        """Follow the ``downloadURL`` Walmart put in the JSON answer and return the ZIP bytes.

        Same host only, https only, under ``/v3/``, no redirects, size-capped, must start with
        the ZIP magic. The download link is pre-signed by Walmart, so no token header is sent.
        """
        url = data.get("downloadURL") if isinstance(data, dict) else None
        if not isinstance(url, str) or not url:
            raise TransportRejected("WALMART_REPORT_DOWNLOAD_URL_MISSING")
        parts = urlsplit(url)
        if (
            parts.scheme != "https"
            or parts.hostname != _WALMART_HOSTNAME
            or not parts.path.startswith("/v3/")
            or ".." in parts.path
        ):
            raise TransportRejected("WALMART_REPORT_DOWNLOAD_HOST_DENIED")
        with client.stream(
            "GET", url, headers={"Accept": "*/*", "WM_QOS.CORRELATION_ID": str(uuid4())}
        ) as download:
            if download.status_code != 200:
                raise TransportRejected("WALMART_REPORT_DOWNLOAD_FAILED")
            payload = _bounded_bytes(download, MAX_ZIP_RESPONSE_BYTES)
        if not payload.startswith(b"PK"):
            raise TransportRejected("WALMART_RESPONSE_INVALID")
        return status, {
            "content_type": "application/zip",
            "request_id": data.get("requestId") if isinstance(data, dict) else None,
            "download_host": parts.hostname,
            "payload_bytes": len(payload),
            "data_base64": base64.b64encode(payload).decode("ascii"),
        }
