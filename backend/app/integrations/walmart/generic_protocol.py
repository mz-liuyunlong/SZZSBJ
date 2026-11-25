"""Protocol v4: signed internal Marketplace requests, independent of business catalogs.

Only trusted backend code may sign requests. The SCF verifies the entire envelope,
store/function binding, freshness and replay before resolving credentials. This is
not an HTTP route or a business permission/approval service.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from typing import Any
from urllib.parse import unquote

from app.integrations.walmart.contracts import ContractError, PreparedRequest, canonical_json

VERSION = 4
OPERATION = "marketplace_generic_call"
METHODS = frozenset({"GET", "POST", "PUT", "PATCH", "DELETE"})
RESPONSE_KINDS = frozenset({"json", "pdf", "zip"})
# Tencent Invoke ClientContext limit; the entire signed event must fit.
MAX_EVENT_BYTES = 65536
MAX_RESULT_BYTES = 5 * 1024 * 1024 + 512 * 1024
EVENT_FIELDS = frozenset(
    {
        "version",
        "operation",
        "store_code",
        "function_name",
        "method",
        "path",
        "query",
        "body",
        "accept",
        "auth",
    }
)
AUTH_FIELDS = frozenset({"kid", "request_id", "issued_at", "expires_at", "sig"})
_SEGMENT = re.compile(r"(?:[A-Za-z0-9._~-]|%[A-Fa-f0-9]{2})+")
_RESTRICTED_QUERY = frozenset(
    {
        "authorization",
        "wmsecaccesstoken",
        "host",
        "cookie",
        "clientsecret",
        "clientid",
        "accesstoken",
        "refreshtoken",
    }
)


def validate_path(path: Any) -> str:
    """Only relative Marketplace paths; no URL authority, traversal or token endpoint."""
    if not isinstance(path, str) or not path.startswith("/v3/") or len(path) > 8192:
        raise ContractError("WALMART_OPERATION_INVALID")
    segments = path[4:].split("/")
    for segment in segments:
        if not _SEGMENT.fullmatch(segment):
            raise ContractError("WALMART_OPERATION_INVALID")
        try:
            decoded = unquote(segment, encoding="utf-8", errors="strict")
        except UnicodeError:
            raise ContractError("WALMART_OPERATION_INVALID") from None
        if (
            decoded in (".", "..")
            or any(c in decoded for c in "/\\%?#")
            or any(ord(c) < 32 or ord(c) == 127 for c in decoded)
        ):
            raise ContractError("WALMART_OPERATION_INVALID")
    if unquote(segments[0]).casefold() == "token":
        raise ContractError("WALMART_OPERATION_INVALID")
    return path


def _scalar(value: Any) -> bool:
    return value is None or type(value) in (str, int, float, bool)


def prepare_generic(method: Any, path: Any, query: Any, body: Any, accept: Any) -> PreparedRequest:
    """Validate transport shape only, without a business API registry or schema."""
    if not isinstance(method, str) or method not in METHODS:
        raise ContractError("WALMART_OPERATION_INVALID")
    if not isinstance(accept, str) or accept not in RESPONSE_KINDS:
        raise ContractError("WALMART_OPERATION_INVALID")
    path = validate_path(path)
    if not isinstance(query, Mapping):
        raise ContractError("WALMART_PARAMS_INVALID")
    for key, value in query.items():
        if not isinstance(key, str) or not key:
            raise ContractError("WALMART_PARAMS_INVALID")
        normalized = "".join(c for c in key.lower() if c.isalnum())
        if normalized in _RESTRICTED_QUERY:
            raise ContractError("WALMART_PARAMS_INVALID")
        if not (
            _scalar(value) or (isinstance(value, list) and all(_scalar(item) for item in value))
        ):
            raise ContractError("WALMART_PARAMS_INVALID")
    try:
        # Freeze JSON values before signing; the transmitted request uses this exact snapshot.
        encoded = canonical_json({"query": dict(query), "body": body})
        if len(encoded) > MAX_EVENT_BYTES:
            raise ContractError("WALMART_REQUEST_TOO_LARGE")
        normalized_body = json.loads(encoded)
    except (UnicodeError, RecursionError):
        raise ContractError("WALMART_CANONICAL_JSON_INVALID") from None
    return PreparedRequest(
        key="generic",
        method=method,
        path=path,
        query=normalized_body["query"],
        body=normalized_body["body"],
        is_write=method != "GET",
        response_kind=accept,
    )


def signing_bytes(event: Mapping[str, Any]) -> bytes:
    """Domain separation and full-envelope authentication; only sig is excluded."""
    if set(event) != EVENT_FIELDS or type(event.get("version")) is not int:
        raise ContractError("WALMART_EVENT_INVALID")
    if event["version"] != VERSION or event["operation"] != OPERATION:
        raise ContractError("WALMART_EVENT_INVALID")
    auth = event.get("auth")
    if not isinstance(auth, Mapping) or set(auth) != AUTH_FIELDS:
        raise ContractError("WALMART_SIGNATURE_INVALID")
    unsigned = dict(event)
    unsigned["auth"] = {k: v for k, v in auth.items() if k != "sig"}
    try:
        if len(canonical_json(dict(event))) > MAX_EVENT_BYTES:
            raise ContractError("WALMART_REQUEST_TOO_LARGE")
        return b"SZZSBJ-WALMART-GENERIC-V4\n" + canonical_json(unsigned)
    except (UnicodeError, RecursionError):
        raise ContractError("WALMART_CANONICAL_JSON_INVALID") from None
