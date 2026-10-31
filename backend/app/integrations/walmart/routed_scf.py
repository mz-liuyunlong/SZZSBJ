"""Store-bound Tencent SCF routing for SZZSBJ's unified Walmart Client.

Each store must have its own protected SCF function and isolated SSM role.
No fallback to another store's function, no shared generic function default.
"""

from __future__ import annotations

from collections.abc import Mapping

from app.integrations.walmart.client import WalmartClient, WalmartResult
from app.integrations.walmart.contract_signing import ContractSigner
from app.integrations.walmart.contracts import ContractRegistry, PreparedRequest
from app.integrations.walmart.planner import STORE_ROUTES, WalmartPlanError
from app.integrations.walmart.scf_bridge import ProtectedScfBridge
from app.integrations.walmart.tencent_api import TencentApiClient
from app.integrations.walmart.tencent_scf import TencentScfInvoker


class RoutedScfGateway:
    def __init__(
        self,
        cloud_api: TencentApiClient,
        *,
        function_by_store: Mapping[str, str],
        function_qualifier: str = "stable",
        bridge_version: int = 1,
        signer: ContractSigner | None = None,
    ) -> None:
        if not function_by_store or any(store not in STORE_ROUTES for store in function_by_store):
            raise WalmartPlanError("WALMART_ROUTE_CONFIG_INVALID")
        if len(set(function_by_store.values())) != len(function_by_store):
            raise WalmartPlanError("WALMART_SHARED_FUNCTION_FORBIDDEN")
        self._gateways = {
            store: ProtectedScfBridge(
                TencentScfInvoker(
                    cloud_api,
                    function_name=name,
                    qualifier=function_qualifier,
                ),
                version=bridge_version,
                signer=signer,
            )
            for store, name in function_by_store.items()
        }

    def execute(
        self,
        *,
        store_code: str,
        request: PreparedRequest,
        approval_ref: str | None,
        actor: Mapping[str, str] | None = None,
    ) -> WalmartResult:
        gateway = self._gateways.get(store_code)
        if gateway is None:
            raise WalmartPlanError("WALMART_STORE_GATEWAY_UNAVAILABLE")
        reply = gateway.execute(
            store_code=store_code,
            request=request,
            approval_ref=approval_ref,
            actor=actor,
        )
        return WalmartResult(
            status_code=reply.status_code,
            data=reply.data,
            provider_error=reply.provider_error,
            content_type=reply.content_type,
            pdf=reply.pdf,
        )


def create_scoped_client(
    registry: ContractRegistry,
    *,
    allowed_stores: frozenset[str],
    function_by_store: Mapping[str, str],
    cloud_api: TencentApiClient,
    function_qualifier: str = "stable",
    bridge_version: int = 1,
    signer: ContractSigner | None = None,
) -> WalmartClient:
    """Caller must pass an independently verified trusted principal store scope."""
    gateway = RoutedScfGateway(
        cloud_api,
        function_by_store=function_by_store,
        function_qualifier=function_qualifier,
        bridge_version=bridge_version,
        signer=signer,
    )
    return WalmartClient(
        registry,
        allowed_stores=allowed_stores,
        configured_stores=frozenset(function_by_store),
        gateway=gateway,
    )
