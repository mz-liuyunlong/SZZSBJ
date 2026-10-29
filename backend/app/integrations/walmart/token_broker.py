"""Owner-controlled SCF token broker for the pre-existing per-store SSH workers.

This module MUST run only inside the protected SCF role. It must never be
imported into the SZZSBJ public API server or a developer-controlled worker.
The Walmart client secret never crosses the SCF boundary.
"""

from __future__ import annotations

import base64
import os
import re
from collections.abc import Callable
from typing import Any

import httpx

from app.integrations.walmart.https_transport import ClientCredentials

_STORE = re.compile(r"^(?:HK|CN)[0-9]{4}$")
_TOKEN_URL = "https://marketplace.walmartapis.com/v3/token"
_MAX_TOKEN_BYTES = 16384


class TokenBrokerRejected(RuntimeError):
    """Non-secret failure code."""


def issue_store_token(
    event: object,
    *,
    bound_store: str,
    secret_resolver: Any,
    post: Callable[..., Any] | None = None,
) -> dict[str, Any]:
    """Issue only the bound store's short-lived token to a trusted SCF invoker.

    The caller MUST authenticate/authorize SCF Invoke via restricted CAM policy.
    An untrusted HTTP trigger or Function URL must never be attached to this
    handler. Tokens are sensitive and must never be logged or persisted.
    """
    if not _STORE.fullmatch(bound_store):
        raise TokenBrokerRejected("TOKEN_STORE_BINDING_INVALID")
    if not isinstance(event, dict) or set(event) != {"version", "operation", "store_code"}:
        raise TokenBrokerRejected("TOKEN_REQUEST_INVALID")
    if event["version"] != 1 or event["operation"] != "issue_store_token":
        raise TokenBrokerRejected("TOKEN_REQUEST_INVALID")
    if event["store_code"] != bound_store:
        raise TokenBrokerRejected("TOKEN_CROSS_STORE_DENIED")
    credentials: ClientCredentials = secret_resolver.get_store_credentials(bound_store)
    authorization = base64.b64encode(
        (credentials.client_id + ":" + credentials.client_secret).encode("utf-8")
    ).decode("ascii")
    headers = {
        "Authorization": "Basic " + authorization,
        "Accept": "application/json",
        "WM_SVC.NAME": "Walmart Marketplace",
    }
    try:
        if post is None:
            with httpx.Client(timeout=12.0, trust_env=False, follow_redirects=False) as client:
                response = client.post(
                    _TOKEN_URL, data={"grant_type": "client_credentials"}, headers=headers
                )
        else:
            response = post(_TOKEN_URL, data={"grant_type": "client_credentials"}, headers=headers)
        if response.status_code != 200 or len(response.content) > _MAX_TOKEN_BYTES:
            raise TokenBrokerRejected("TOKEN_PROVIDER_UNAVAILABLE")
        data = response.json()
        token = data.get("access_token") if isinstance(data, dict) else None
        expires = data.get("expires_in") if isinstance(data, dict) else None
        if (
            not isinstance(token, str)
            or not token
            or len(token) > 8192
            or type(expires) is not int
            or not 1 <= expires <= 900
        ):
            raise TokenBrokerRejected("TOKEN_RESPONSE_INVALID")
        return {
            "success": True,
            "operation": "issue_store_token",
            "store_code": bound_store,
            "access_token": token,
            "expires_in": expires,
        }
    except TokenBrokerRejected:
        raise
    except Exception:
        raise TokenBrokerRejected("TOKEN_PROVIDER_UNAVAILABLE") from None


def scf_token_handler(event: object, context: object) -> dict[str, Any]:
    """Separate owner-deployed SCF entrypoint. NEVER expose via public trigger."""
    del context
    if os.getenv("SZZSBJ_WALMART_TOKEN_BROKER_ENABLED") != "1":
        return {"success": False, "status": "TOKEN_BROKER_DISABLED"}
    store = os.getenv("SZZSBJ_WALMART_BOUND_STORE", "")
    try:
        # Lazy import isolates the SSM secret resolver from the main server.
        from app.integrations.walmart.tencent_api import TemporaryTencentIdentity, TencentApiClient
        from app.integrations.walmart.tencent_ssm import TencentSsmResolver

        resolver = TencentSsmResolver(
            TencentApiClient(TemporaryTencentIdentity.from_environment()),
            approved_stores=frozenset({store}),
            version=os.getenv("SZZSBJ_WALMART_SECRET_VERSION", "v1"),
        )
        return issue_store_token(event, bound_store=store, secret_resolver=resolver)
    except Exception:
        return {"success": False, "status": "TOKEN_BROKER_UNAVAILABLE"}
