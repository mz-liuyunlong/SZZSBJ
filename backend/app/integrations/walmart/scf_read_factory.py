"""SZZSBJ Walmart read-only API factory.

The server may call SCF with temporary Tencent identity, but it never reads
Walmart credentials, Walmart tokens, or store-specific SSM secrets.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Protocol

from app.integrations.walmart.routed_scf import create_scoped_client
from app.integrations.walmart.tenc_sts_identity import CachedScfAssumeRoleIdentity
from app.integrations.walmart.tencent_api import TemporaryTencentIdentity, TencentApiClient
from app.integrations.walmart.unified_api import WalmartReadAPI, load_unified_registry


class IdentityProvider(Protocol):
    def get_identity(self) -> TemporaryTencentIdentity: ...


class RefreshingScfApi(TencentApiClient):
    """Request fresh-or-cached account B identity for each SCF invocation."""

    def __init__(self, provider: IdentityProvider) -> None:
        self._provider = provider

    def request(self, service: str, payload: dict[str, Any]) -> dict[str, Any]:
        if service != "scf":
            raise ValueError("SCF_ONLY")
        return TencentApiClient(self._provider.get_identity()).request("scf", payload)


def make_walmart_read_api(
    *,
    allowed_stores: frozenset[str],
    approved_read_keys: frozenset[str],
    function_by_store: Mapping[str, str],
    cvm_role: str,
    target_role_arn: str,
    function_qualifier: str = "stable",
    identity_provider: IdentityProvider | None = None,
) -> WalmartReadAPI:
    """Construct a WalmartReadAPI for independently authorized store scope.

    The caller MUST source allowed_stores from verified server-side
    authorization, never from untrusted request data.  Production must use a
    reviewed immutable function version alias, not $LATEST.
    """
    if not allowed_stores or not approved_read_keys:
        raise ValueError("WALMART_APPROVAL_MISSING")
    if not function_qualifier or function_qualifier == "$LATEST":
        raise ValueError("WALMART_STABLE_VERSION_REQUIRED")
    provider = identity_provider or CachedScfAssumeRoleIdentity(
        cvm_role=cvm_role,
        target_role_arn=target_role_arn,
    )
    registry = load_unified_registry(approved_read_keys)
    client = create_scoped_client(
        registry,
        allowed_stores=allowed_stores,
        function_by_store=function_by_store,
        cloud_api=RefreshingScfApi(provider),
        function_qualifier=function_qualifier,
    )
    return WalmartReadAPI(client)
