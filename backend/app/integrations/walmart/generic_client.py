"""Trusted backend-only generic Walmart client; never expose it as a public proxy."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import replace
from functools import lru_cache
from typing import Any

from app.integrations.walmart.contract_signing import ContractSigner
from app.integrations.walmart.contracts import ContractError, ContractRegistry
from app.integrations.walmart.gateway import (
    DEFAULT_SIGNING_KEY_FILE,
    ENV_CVM_ROLE,
    ENV_SIGNING_KEY_FILE,
    ENV_SIGNING_KEY_ID,
    ENV_TARGET_ROLE_ARN,
    reviewed_store_id_map,
)
from app.integrations.walmart.generic_protocol import VERSION
from app.integrations.walmart.scf_bridge import (
    CloudInvoker,
    GatewayRejected,
    SafeResult,
    decode_safe_result,
)
from app.integrations.walmart.scf_read_factory import IdentityProvider, RefreshingScfApi
from app.integrations.walmart.tenc_sts_identity import CachedScfAssumeRoleIdentity
from app.integrations.walmart.tencent_api import MAX_SCF_RESPONSE_BYTES
from app.integrations.walmart.tencent_scf import TencentScfInvoker


class WalmartGenericClient:
    """Use only in trusted server code after the existing business scope is resolved."""

    def __init__(
        self,
        *,
        signer: ContractSigner,
        routes: Mapping[str, tuple[str, CloudInvoker]],
    ) -> None:
        if not routes or len({route[0] for route in routes.values()}) != len(routes):
            raise GatewayRejected("WALMART_ROUTE_CONFIG_INVALID")
        self._signer = signer
        self._routes = dict(routes)

    def call(
        self,
        store_code: str,
        method: str,
        path: str,
        *,
        query: Mapping[str, Any] | None = None,
        body: Any = None,
        response_kind: str = "json",
    ) -> SafeResult:
        route = self._routes.get(store_code)
        if route is None:
            raise GatewayRejected("WALMART_STORE_GATEWAY_UNAVAILABLE")
        function, invoker = route
        try:
            event = self._signer.sign_generic(
                store_code=store_code,
                function_name=function,
                method=method,
                path=path,
                query=query,
                body=body,
                response_kind=response_kind,
            )
        except ContractError as error:
            raise GatewayRejected(str(error)) from None
        try:
            result = invoker.invoke(event)
        except Exception:
            # Never retry an ambiguous write automatically.
            raise GatewayRejected("WALMART_GATEWAY_UNAVAILABLE") from None
        if not isinstance(result, Mapping) or result.get("success") is not True:
            raise GatewayRejected("WALMART_GATEWAY_REJECTED")
        request_id = event["auth"]["request_id"]
        if (
            result.get("protocol") != VERSION
            or result.get("store_code") != store_code
            or result.get("request_id") != request_id
        ):
            raise GatewayRejected("WALMART_GATEWAY_SCOPE_MISMATCH")
        code = result.get("status_code")
        if type(code) is not int or not 100 <= code <= 599:
            raise GatewayRejected("WALMART_PROVIDER_NOT_SUCCESSFUL")
        return replace(
            decode_safe_result(result, code=code, response_kind=response_kind),
            request_id=request_id,
        )


def make_generic_client(
    *,
    environ: Mapping[str, str] | None = None,
    identity_provider: IdentityProvider | None = None,
    function_qualifier: str = "stable",
) -> WalmartGenericClient:
    """Reuse configured store mappings, signing key and Invoke-only cloud identity."""
    env = os.environ if environ is None else environ
    mapping = reviewed_store_id_map(env)
    role = env.get(ENV_CVM_ROLE, "").strip()
    arn = env.get(ENV_TARGET_ROLE_ARN, "").strip()
    kid = env.get(ENV_SIGNING_KEY_ID, "").strip()
    if not mapping or not role or not arn or not kid:
        raise GatewayRejected("WALMART_GATEWAY_CONFIG_INVALID")
    if not function_qualifier or function_qualifier == "$LATEST":
        raise GatewayRejected("WALMART_STABLE_VERSION_REQUIRED")
    signer = ContractSigner.from_pem_file(
        env.get(ENV_SIGNING_KEY_FILE, DEFAULT_SIGNING_KEY_FILE).strip(),
        kid=kid,
        registry=ContractRegistry(()),
    )
    provider = identity_provider or CachedScfAssumeRoleIdentity(cvm_role=role, target_role_arn=arn)
    api = RefreshingScfApi(provider, scf_response_limit=MAX_SCF_RESPONSE_BYTES)
    routes: dict[str, tuple[str, CloudInvoker]] = {}
    for store in mapping.values():
        function = f"szzsbj-walmart-{store.lower()}-executor"
        routes[store] = (
            function,
            TencentScfInvoker(
                api,
                function_name=function,
                qualifier=function_qualifier,
                result_limit=6 * 1024 * 1024,
            ),
        )
    return WalmartGenericClient(signer=signer, routes=routes)


@lru_cache(maxsize=1)
def get_generic_client() -> WalmartGenericClient:
    return make_generic_client()


def call_walmart(
    store_code: str,
    method: str,
    path: str,
    *,
    query: Mapping[str, Any] | None = None,
    body: Any = None,
    response_kind: str = "json",
) -> SafeResult:
    """Canonical internal entry point; no per-operation registration."""
    return get_generic_client().call(
        store_code, method, path, query=query, body=body, response_kind=response_kind
    )
