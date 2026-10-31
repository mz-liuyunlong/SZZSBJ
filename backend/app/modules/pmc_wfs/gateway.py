"""Explicit external-operation port. No mock or write-enabled fallback in application code."""

from typing import Protocol

from app.core.api import ApiError


class CreationGateway(Protocol):
    enabled: bool

    def validate(self, snapshot: dict) -> None: ...
    def create(self, ticket_id: str, snapshot: dict, allocation: dict) -> list[str]: ...
    def reconcile(self, ticket_id: str, snapshot: dict) -> list[str] | None: ...
    def label(self, shipment_id: str, snapshot: dict) -> bytes: ...
    def preview(self, snapshot: dict) -> dict: ...


class DisabledGateway:
    enabled = False

    def validate(self, snapshot: dict) -> None:
        raise ApiError(
            code="WFS_EXECUTION_DISABLED",
            status_code=503,
            message="Walmart 创建能力尚未启用；未创建货件，也未占用箱子",
        )


def get_creation_gateway() -> CreationGateway:
    """Disabled unless the owner-configured Walmart SCF adapter is switched on by env.

    See ``walmart_gateway.build_gateway_from_env`` (WFS_WALMART_GATEWAY=scf plus the
    WALMART_SCF_* / WALMART_*_KEYS variables). Writes still go through the reviewed
    ``WalmartWriteAPI`` with an approval_ref per call; the read SDK is not widened.
    """
    from app.db.session import get_session_factory
    from app.modules.pmc_wfs.walmart_gateway import build_gateway_from_env

    return build_gateway_from_env(get_session_factory())
