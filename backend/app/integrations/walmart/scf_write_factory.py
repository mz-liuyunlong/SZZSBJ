"""SZZSBJ Walmart write API factory (WFS inbound-shipment operations).

Mirrors ``scf_read_factory`` but uses bridge protocol v2 so the caller receives
Walmart's error body on a rejected write and the PDF bytes for label calls. The server
still never sees Walmart credentials; the per-store SCF function re-authorizes every
call and must itself be deployed in ``owner-approved-read-write`` mode.
"""

from __future__ import annotations

from collections.abc import Mapping

from app.integrations.walmart.routed_scf import create_scoped_client
from app.integrations.walmart.scf_read_factory import IdentityProvider, RefreshingScfApi
from app.integrations.walmart.tenc_sts_identity import CachedScfAssumeRoleIdentity
from app.integrations.walmart.unified_api import WalmartWriteAPI, load_unified_registry
from app.integrations.walmart.wfs_write_catalog import WFS_WRITE_KEYS


def make_walmart_write_api(
    *,
    allowed_stores: frozenset[str],
    approved_write_keys: frozenset[str],
    function_by_store: Mapping[str, str],
    cvm_role: str,
    target_role_arn: str,
    function_qualifier: str = "stable",
    identity_provider: IdentityProvider | None = None,
) -> WalmartWriteAPI:
    """Construct a WalmartWriteAPI for an independently authorized store scope.

    The caller MUST source allowed_stores from verified server-side authorization and
    approved_write_keys from owner configuration (never from request data). Production
    must use a reviewed immutable function version alias, not $LATEST.
    """
    if not allowed_stores or not approved_write_keys:
        raise ValueError("WALMART_APPROVAL_MISSING")
    if approved_write_keys - WFS_WRITE_KEYS:
        raise ValueError("WALMART_APPROVED_OPERATION_UNKNOWN")
    if not function_qualifier or function_qualifier == "$LATEST":
        raise ValueError("WALMART_STABLE_VERSION_REQUIRED")
    provider = identity_provider or CachedScfAssumeRoleIdentity(
        cvm_role=cvm_role,
        target_role_arn=target_role_arn,
    )
    registry = load_unified_registry(approved_write_keys=approved_write_keys)
    client = create_scoped_client(
        registry,
        allowed_stores=allowed_stores,
        function_by_store=function_by_store,
        cloud_api=RefreshingScfApi(provider),
        function_qualifier=function_qualifier,
        bridge_version=2,
    )
    return WalmartWriteAPI(client)
