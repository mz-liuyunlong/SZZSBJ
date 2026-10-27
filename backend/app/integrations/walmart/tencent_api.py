"""Restricted Tencent Cloud TC3 API transport for SCF Invoke and SSM GetSecretValue.

Runtime credentials are injected by the owner-controlled environment. No static
keys, logging of headers, arbitrary API host, or action escalation is permitted.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo
from typing import Any

import httpx

_ENDPOINTS = {
    "ssm": ("ssm.tencentcloudapi.com", "GetSecretValue", "2019-09-23"),
    "scf": ("scf.tencentcloudapi.com", "Invoke", "2018-04-16"),
}
MAX_BYTES = 1024 * 1024


class TencentApiRejected(RuntimeError):
    """Stable code, never expose provider body or credential contents."""


@dataclass(frozen=True, slots=True, repr=False)
class TemporaryTencentIdentity:
    secret_id: str
    secret_key: str
    session_token: str

    def __repr__(self) -> str:
        return "TemporaryTencentIdentity([REDACTED])"

    @classmethod
    def from_environment(cls) -> TemporaryTencentIdentity:
        return cls(
            os.getenv("TENCENTCLOUD_SECRETID", ""),
            os.getenv("TENCENTCLOUD_SECRETKEY", ""),
            os.getenv("TENCENTCLOUD_SESSIONTOKEN", ""),
        )


def _hmac(key: bytes, text: str) -> bytes:
    return hmac.new(key, text.encode("utf-8"), hashlib.sha256).digest()


def tc3_headers(
    service: str,
    body: bytes,
    identity: TemporaryTencentIdentity,
    *,
    region: str,
    timestamp: int,
) -> dict[str, str]:
    if service not in _ENDPOINTS:
        raise TencentApiRejected("TC_SERVICE_NOT_ALLOWED")
    if not identity.secret_id or not identity.secret_key or not identity.session_token:
        raise TencentApiRejected("TC_IDENTITY_NOT_CONFIGURED")
    if region != "ap-guangzhou":
        raise TencentApiRejected("TC_REGION_NOT_ALLOWED")
    host, action, version = _ENDPOINTS[service]
    day = datetime.fromtimestamp(timestamp, ZoneInfo("UTC")).strftime("%Y-%m-%d")
    scope = f"{day}/{service}/tc3_request"
    content_type = "application/json; charset=utf-8"
    request = (
        "POST\n/\n\n"
        + f"content-type:{content_type}\nhost:{host}\n\n"
        + "content-type;host\n"
        + hashlib.sha256(body).hexdigest()
    )
    to_sign = (
        f"TC3-HMAC-SHA256\n{timestamp}\n{scope}\n" + hashlib.sha256(request.encode()).hexdigest()
    )
    secret = _hmac(
        _hmac(_hmac(("TC3" + identity.secret_key).encode(), day), service), "tc3_request"
    )

    signature = hmac.new(secret, to_sign.encode(), hashlib.sha256).hexdigest()
    return {
        "Content-Type": content_type,
        "Authorization": (
            f"TC3-HMAC-SHA256 Credential={identity.secret_id}/{scope}, "
            f"SignedHeaders=content-type;host, Signature={signature}"
        ),
        "X-TC-Action": action,
        "X-TC-Version": version,
        "X-TC-Region": region,
        "X-TC-Timestamp": str(timestamp),
        "X-TC-Token": identity.session_token,
    }


class TencentApiClient:
    """One allowlisted Tencent action per service, with bounded responses."""

    def __init__(
        self,
        identity: TemporaryTencentIdentity,
        *,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._identity = identity
        self._transport = transport

    def request(self, service: str, payload: dict[str, Any]) -> dict[str, Any]:
        if service not in _ENDPOINTS:
            raise TencentApiRejected("TC_SERVICE_NOT_ALLOWED")
        body = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode()
        if len(body) > MAX_BYTES:
            raise TencentApiRejected("TC_REQUEST_TOO_LARGE")
        host = _ENDPOINTS[service][0]
        headers = tc3_headers(
            service, body, self._identity, region="ap-guangzhou", timestamp=int(time.time())
        )
        try:
            with httpx.Client(
                timeout=12.0, transport=self._transport, trust_env=False, follow_redirects=False
            ) as client:
                response = client.post(f"https://{host}/", content=body, headers=headers)
                response.raise_for_status()
                if len(response.content) > MAX_BYTES:
                    raise TencentApiRejected("TC_RESPONSE_TOO_LARGE")
                response_data = response.json()
            item = response_data["Response"]
            if not isinstance(item, dict) or "Error" in item:
                raise TencentApiRejected("TC_REMOTE_REJECTED")
            return item
        except TencentApiRejected:
            raise
        except Exception:
            raise TencentApiRejected("TC_TRANSPORT_ERROR") from None
