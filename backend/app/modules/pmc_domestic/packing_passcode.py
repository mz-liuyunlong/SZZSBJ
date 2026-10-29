"""Required confirmation; route permissions and authenticated actor govern access."""

import hashlib
import hmac
import os
import time
from urllib.parse import urlsplit

from redis import Redis
from redis.exceptions import RedisError

from app.core.api import ApiError

_RESERVE = """
local n = tonumber(redis.call('GET', KEYS[1]) or '0')
if n >= 10 then return 0 end
local value = redis.call('INCR', KEYS[1])
if value == 1 then redis.call('EXPIRE', KEYS[1], 1200) end
return 1
"""
_RELEASE = """
if tonumber(redis.call('GET', KEYS[1]) or '0') > 0 then
  return redis.call('DECR', KEYS[1])
end
return 0
"""


def _limiter():
    url = os.environ.get("CELERY_BROKER_URL", "")
    if urlsplit(url).scheme not in {"redis", "rediss"}:
        raise ApiError(code="PASSCODE_LIMITER_UNAVAILABLE", status_code=503)
    return Redis.from_url(url, socket_connect_timeout=2, socket_timeout=2)


def verify_domestic_passcode(operator_name, passcode, actor_id):
    if not (passcode or "").strip():
        raise ApiError(code="PASSCODE_REQUIRED", status_code=422)
    # Keep PMC-only confirmation configuration out of the shared Settings schema.
    expected = os.environ.get("PMC_DOMESTIC_PASSCODE_SHA256", "").strip().lower()
    if len(expected) != 64 or any(c not in "0123456789abcdef" for c in expected):
        raise ApiError(code="PASSCODE_UNSET", status_code=503)
    actor_key = hashlib.sha256(str(actor_id).encode()).hexdigest()
    key = f"pmc:packing:passcode:{actor_key}:{int(time.time()) // 600}"
    try:
        client = _limiter()
        # Reserve atomically before verification across all workers. Successful
        # confirmations release their reservation; failed attempts remain counted.
        if not client.eval(_RESERVE, 1, key):
            raise ApiError(code="PASSCODE_LOCKED", status_code=429)
        digest = hashlib.sha256(passcode.encode("utf-8")).hexdigest()
        if not hmac.compare_digest(digest, expected):
            raise ApiError(code="PASSCODE_REJECTED", status_code=403, message="口令不对")
        client.eval(_RELEASE, 1, key)
    except RedisError:
        raise ApiError(code="PASSCODE_LIMITER_UNAVAILABLE", status_code=503) from None
