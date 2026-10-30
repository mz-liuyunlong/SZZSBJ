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
    # A reviewed production adapter must replace this dependency explicitly.
    # The existing shared Walmart read SDK must not be widened to allow writes.
    return DisabledGateway()
