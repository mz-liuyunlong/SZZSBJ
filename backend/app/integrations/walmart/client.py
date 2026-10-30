"""SZZSBJ-facing Walmart SDK facade.

No real transport is bundled. Only owner-approved gateway implementations may
execute requests, and gateway MUST re-authorize store and operation independently.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Protocol

from app.integrations.walmart.contracts import ContractRegistry, PreparedRequest
from app.integrations.walmart.planner import STORE_ROUTES, WalmartPlanError


@dataclass(frozen=True, slots=True)
class WalmartResult:
    status_code: int
    data: Any
    # Write path (bridge protocol v2): Walmart's error body on a non-2xx answer, and the
    # decoded PDF for label operations. Read callers never see these populated.
    provider_error: Any = None
    content_type: str = "application/json"
    pdf: bytes | None = None

    @property
    def ok(self) -> bool:
        return 200 <= self.status_code < 300


class ProtectedGateway(Protocol):
    """Protected remote execution contract; no credential or token response."""

    def execute(
        self, *, store_code: str, request: PreparedRequest, approval_ref: str | None
    ) -> WalmartResult: ...


class WalmartClient:
    """A uniform API entry point, disabled until a protected gateway is provided."""

    def __init__(
        self,
        registry: ContractRegistry,
        *,
        allowed_stores: frozenset[str] = frozenset(),
        configured_stores: frozenset[str] = frozenset(),
        gateway: ProtectedGateway | None = None,
    ) -> None:
        self.registry = registry
        self.allowed_stores = allowed_stores
        self.configured_stores = configured_stores
        self.gateway = gateway

    def prepare(
        self,
        store_code: str,
        operation: str,
        *,
        params: Mapping[str, Any] | None = None,
        body: Any = None,
        allow_writes: bool = False,
    ) -> PreparedRequest:
        self._validate_store(store_code)
        return self.registry.prepare(operation, params=params, body=body, allow_writes=allow_writes)

    def call(
        self,
        store_code: str,
        operation: str,
        *,
        params: Mapping[str, Any] | None = None,
        body: Any = None,
        allow_writes: bool = False,
        approval_ref: str | None = None,
    ) -> WalmartResult:
        self._validate_store(store_code)
        request = self.registry.prepare(
            operation, params=params, body=body, allow_writes=allow_writes
        )
        if request.is_write and not approval_ref:
            raise WalmartPlanError("WALMART_WRITE_APPROVAL_REQUIRED")
        if self.gateway is None:
            raise WalmartPlanError("WALMART_PROTECTED_GATEWAY_UNAVAILABLE")
        return self.gateway.execute(
            store_code=store_code, request=request, approval_ref=approval_ref
        )

    def _validate_store(self, store_code: str) -> None:
        if store_code not in STORE_ROUTES:
            raise WalmartPlanError("WALMART_STORE_UNKNOWN")
        if store_code not in self.allowed_stores:
            raise WalmartPlanError("WALMART_STORE_FORBIDDEN")
        # CN2502 is eligible but cannot run without its own egress.
        if STORE_ROUTES[store_code][1] is None and store_code not in self.configured_stores:
            raise WalmartPlanError("WALMART_EXIT_UNAVAILABLE")
