"""Domestic packing passphrase check. The hash stays in server settings, never in the client."""

import hashlib
import hmac
import time
from threading import Lock

from app.core.api import ApiError
from app.core.config import get_settings

APPROVER_NAMES = frozenset({"吴贤玲"})
_WINDOW_SECONDS = 600
_FAILURE_LIMIT = 10
_failures: dict[str, list[float]] = {}
_lock = Lock()


def reset_passcode_failures() -> None:
    with _lock:
        _failures.clear()


def verify_domestic_passcode(
    operator_name: str | None, passcode: str | None, actor_id: str
) -> None:
    now = time.monotonic()
    with _lock:
        recent = [stamp for stamp in _failures.get(actor_id, []) if now - stamp < _WINDOW_SECONDS]
        _failures[actor_id] = recent
        if len(recent) >= _FAILURE_LIMIT:
            raise ApiError(
                code="PASSCODE_LOCKED",
                status_code=429,
                message="口令错误次数过多，请 10 分钟后再试",
                details={"reason": "PASSCODE_LOCKED"},
            )
    configured = get_settings().pmc_domestic_passcode_sha256
    expected = configured.get_secret_value().split()[0].strip().lower() if configured else ""
    if len(expected) != 64:
        raise ApiError(
            code="PASSCODE_UNSET",
            status_code=503,
            message="服务器尚未设置国内仓口令",
            details={"reason": "PASSCODE_UNSET"},
        )
    digest = hashlib.sha256((passcode or "").encode("utf-8")).hexdigest()
    if not hmac.compare_digest(digest, expected):
        with _lock:
            _failures.setdefault(actor_id, []).append(now)
        raise ApiError(
            code="PASSCODE_REJECTED",
            status_code=403,
            message="口令不对",
            details={"reason": "PASSCODE_REJECTED"},
        )
    name = (operator_name or "").strip()
    if name not in APPROVER_NAMES:
        raise ApiError(
            code="OPERATOR_NOT_ALLOWED",
            status_code=403,
            message="国内仓打包单目前只能由吴贤玲提交",
            details={"reason": "OPERATOR_NOT_ALLOWED"},
        )
