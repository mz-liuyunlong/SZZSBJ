"""Explicit external-operation port. No mock or write-enabled fallback in application code.

``get_creation_gateway`` returns the reviewed production adapter
(``walmart_gateway.WalmartCreationGateway``) only when the owner set ``WFS_CREATION_MODE``
to probe / single / batch *and* the unified Walmart gateway can be built from the server
configuration; otherwise it returns ``DisabledGateway`` carrying the reason.

The one exception is the local simulator (``local_simulator``): only on APP_ENV=local with the
local database and ``WFS_CREATION_MODE`` unset. A simulator switch set anywhere else raises
here instead of falling back to Walmart.
"""

import logging
from functools import lru_cache
from typing import Protocol

from app.core.api import ApiError
from app.modules.pmc_wfs.creation_config import MODE_REASONS, creation_mode

logger = logging.getLogger("szzsbj.pmc_wfs.gateway")


class CreationGateway(Protocol):
    enabled: bool
    preview_enabled: bool
    reason: str | None

    def validate(self, snapshot: dict) -> None: ...
    def create(self, ticket_id: str, snapshot: dict, allocation: dict) -> list: ...
    def reconcile(self, ticket_id: str, snapshot: dict) -> list | None: ...
    def label(self, shipment_id: str, snapshot: dict, cartons: int | None = None) -> bytes: ...
    def preview(self, snapshot: dict) -> dict: ...


class DisabledGateway:
    enabled = False
    preview_enabled = False

    def __init__(self, reason: str | None = None) -> None:
        self.reason = reason or MODE_REASONS["off"]

    def validate(self, snapshot: dict) -> None:
        raise ApiError(
            code="WFS_EXECUTION_DISABLED",
            status_code=503,
            message=f"{self.reason}；未创建货件，也未占用箱子",
        )

    def preview(self, snapshot: dict) -> dict:
        self.validate(snapshot)
        return {}

    def probe(self, store_id: str) -> dict:
        self.validate({})
        return {}


@lru_cache(maxsize=4)
def _production_gateway(mode: str):
    from app.db.session import get_session_factory
    from app.integrations.walmart.gateway import reviewed_store_id_map
    from app.modules.pmc_wfs.walmart_gateway import WalmartCreationGateway
    from app.modules.walmart_scf.persistence import build_production_gateway

    walmart = build_production_gateway(get_session_factory())
    return WalmartCreationGateway(walmart, mode=mode, store_map=reviewed_store_id_map())


def get_creation_gateway() -> CreationGateway:
    from app.modules.pmc_wfs import local_simulator

    if local_simulator.simulator_active():  # raises SimulatorRefused outside local
        return local_simulator.LocalSimulatorGateway()
    mode = creation_mode()
    if mode == "off":
        return DisabledGateway()
    try:
        return _production_gateway(mode)
    except Exception as error:  # configuration problems surface as a reason, never a write
        code = getattr(error, "code", None) or type(error).__name__
        logger.warning("WFS creation gateway unavailable: %s", code)
        return DisabledGateway(f"Walmart 通道配置不可用（{code}），请联系管理员")
