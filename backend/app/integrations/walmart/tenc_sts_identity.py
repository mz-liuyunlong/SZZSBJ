"""CVM role -> cross-account STS -> temporary SCF-only identity.

Only Tencent temporary credentials are handled here, never Walmart credentials.
Credentials remain in process memory and are never logged or serialized.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import re
import threading
import time
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

import httpx

from app.integrations.walmart.tencent_api import TemporaryTencentIdentity

_METADATA_BASE = "http://metadata.tencentyun.com/latest/meta-data/cam/security-credentials/"
_STS_URL = "https://sts.tencentcloudapi.com/"
_SESSION_NAME = "SZZSBJ-WalmartScfCaller"


class TencentStsIdentityError(RuntimeError):
    """Stable error code; no upstream response body or secret values."""


class CachedScfAssumeRoleIdentity:
    """Fetch account-B credentials and refresh them before expiry.

    This class does not persist credentials or run an asynchronous job. It
    requires an approved CVM role and a cross-account STS trust relationship.
    """

    def __init__(
        self,
        *,
        cvm_role: str,
        target_role_arn: str,
        duration_seconds: int = 1800,
        refresh_before_seconds: int = 300,
        transport: httpx.BaseTransport | None = None,
        clock: Callable[[], float] = time.time,
    ) -> None:
        if not re.fullmatch(r"[A-Za-z0-9_.-]{1,128}", cvm_role):
            raise TencentStsIdentityError("STS_CONFIG_INVALID")
        if not re.fullmatch(
            r"qcs::cam::uin/[0-9]+:roleName/[A-Za-z0-9_.-]{1,128}",
            target_role_arn,
        ):
            raise TencentStsIdentityError("STS_CONFIG_INVALID")
        if not 900 <= duration_seconds <= 7200:
            raise TencentStsIdentityError("STS_CONFIG_INVALID")
        if not 60 <= refresh_before_seconds < 900:
            raise TencentStsIdentityError("STS_CONFIG_INVALID")

        self._cvm_role = cvm_role
        self._target_role_arn = target_role_arn
        self._duration_seconds = duration_seconds
        self._refresh_before_seconds = refresh_before_seconds
        self._transport = transport
        self._clock = clock
        self._lock = threading.Lock()
        self._cached: TemporaryTencentIdentity | None = None
        self._expires_at = 0

    def get_identity(self) -> TemporaryTencentIdentity:
        with self._lock:
            now = int(self._clock())
            if self._cached is not None and now + self._refresh_before_seconds < self._expires_at:
                return self._cached
            identity, expires_at = self._refresh()
            if now + self._refresh_before_seconds >= expires_at:
                raise TencentStsIdentityError("STS_EXPIRES_TOO_SOON")
            self._cached = identity
            self._expires_at = expires_at
            return identity

    def _refresh(self) -> tuple[TemporaryTencentIdentity, int]:
        return self._assume_role(self._load_cvm_identity())

    def _load_cvm_identity(self) -> TemporaryTencentIdentity:
        try:
            with httpx.Client(
                timeout=5.0,
                transport=self._transport,
                trust_env=False,
                follow_redirects=False,
            ) as client:
                response = client.get(_METADATA_BASE + self._cvm_role)
                response.raise_for_status()
                if len(response.content) > 16384:
                    raise ValueError
                item = response.json()
            if not isinstance(item, dict) or item.get("Code") != "Success":
                raise ValueError
            identity_values = (item["TmpSecretId"], item["TmpSecretKey"], item["Token"])
            expires_at = item["ExpiredTime"]
            if not all(isinstance(value, str) and value for value in identity_values):
                raise ValueError
            if type(expires_at) is not int or expires_at <= int(self._clock()) + 60:
                raise ValueError
            return TemporaryTencentIdentity(*identity_values)
        except Exception:
            raise TencentStsIdentityError("CVM_IDENTITY_UNAVAILABLE") from None

    def _assume_role(self, cvm: TemporaryTencentIdentity) -> tuple[TemporaryTencentIdentity, int]:
        timestamp = int(self._clock())
        day = datetime.fromtimestamp(timestamp, timezone.utc).strftime("%Y-%m-%d")
        scope = f"{day}/sts/tc3_request"
        body = json.dumps(
            {
                "RoleArn": self._target_role_arn,
                "RoleSessionName": _SESSION_NAME,
                "DurationSeconds": self._duration_seconds,
            },
            separators=(",", ":"),
        ).encode("utf-8")
        content_type = "application/json; charset=utf-8"
        canonical = (
            "POST\n/\n\n"
            f"content-type:{content_type}\n"
            "host:sts.tencentcloudapi.com\n\n"
            "content-type;host\n" + hashlib.sha256(body).hexdigest()
        )
        to_sign = (
            f"TC3-HMAC-SHA256\n{timestamp}\n{scope}\n"
            + hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        )

        def sign(key: bytes, value: str) -> bytes:
            return hmac.new(key, value.encode("utf-8"), hashlib.sha256).digest()

        secret = sign(
            sign(sign(("TC3" + cvm.secret_key).encode("utf-8"), day), "sts"),
            "tc3_request",
        )
        signature = hmac.new(secret, to_sign.encode("utf-8"), hashlib.sha256).hexdigest()
        headers = {
            "Content-Type": content_type,
            "X-TC-Action": "AssumeRole",
            "X-TC-Version": "2018-08-13",
            "X-TC-Region": "ap-guangzhou",
            "X-TC-Timestamp": str(timestamp),
            "X-TC-Token": cvm.session_token,
            "Authorization": (
                f"TC3-HMAC-SHA256 Credential={cvm.secret_id}/{scope}, "
                f"SignedHeaders=content-type;host, Signature={signature}"
            ),
        }
        try:
            with httpx.Client(
                timeout=15.0,
                transport=self._transport,
                trust_env=False,
                follow_redirects=False,
            ) as client:
                response = client.post(_STS_URL, headers=headers, content=body)
                response.raise_for_status()
                if len(response.content) > 16384:
                    raise ValueError
                envelope: dict[str, Any] = response.json()["Response"]
            if "Error" in envelope:
                raise ValueError
            creds = envelope["Credentials"]
            values = (creds["TmpSecretId"], creds["TmpSecretKey"], creds["Token"])
            expires_at = envelope["ExpiredTime"]
            if not all(isinstance(value, str) and value for value in values):
                raise ValueError
            if type(expires_at) is not int:
                raise ValueError
            return TemporaryTencentIdentity(*values), expires_at
        except Exception:
            raise TencentStsIdentityError("STS_ASSUME_ROLE_UNAVAILABLE") from None
