"""资金 汇率页面的「手动同步」按钮：建一条任务中心运行记录，交给现有队列执行。"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.finance_cashflow.schemas import CashflowApprovalSyncData
from app.modules.integration_sync.fx_catalog import FX_RATE_SYNC_SPEC
from app.modules.integration_sync.models import IntegrationSyncConfig, IntegrationSyncRun
from app.modules.integration_sync.repository import IntegrationSyncRepository
from app.modules.integration_sync.schemas import TriggerRequest
from app.modules.integration_sync.service import IntegrationSyncService
from app.modules.integration_sync.tasks import TaskDispatchError, dispatch_sync_run

PROVIDER = "lingxing"
SPEC = FX_RATE_SYNC_SPEC
ACTIVE = ("queued", "running")


class FxSyncNotConfiguredError(Exception):
    pass


class FxSyncUnavailableError(Exception):
    pass


def _runs() -> Any:
    return select(IntegrationSyncRun).where(
        IntegrationSyncRun.provider == PROVIDER,
        IntegrationSyncRun.interface_key == SPEC.interface_key,
    )


def latest_fx_sync(session: Session) -> CashflowApprovalSyncData:
    run = session.scalars(_runs().order_by(IntegrationSyncRun.queued_at.desc()).limit(1)).first()
    if run is None:
        return CashflowApprovalSyncData()
    success = session.scalars(
        _runs()
        .where(IntegrationSyncRun.status == "succeeded")
        .order_by(IntegrationSyncRun.finished_at.desc())
        .limit(1)
    ).first()
    return CashflowApprovalSyncData(
        run_id=run.id,
        status=run.status,
        started_at=run.started_at,
        finished_at=run.finished_at,
        error_code=run.error_code,
        records_seen=run.records_seen,
        records_written=run.records_written,
        last_success_at=success.finished_at if success else None,
    )


def start_fx_sync(session: Session, *, actor: str, request_id: str) -> CashflowApprovalSyncData:
    """已经有一次在跑就不再开新的，直接返回它的状态。"""
    running = session.scalars(_runs().where(IntegrationSyncRun.status.in_(ACTIVE)).limit(1)).first()
    if running is not None:
        return latest_fx_sync(session)
    interface = IntegrationSyncRepository(session).get_interface_by_key(
        PROVIDER, SPEC.interface_key
    )
    config = (
        session.scalars(
            select(IntegrationSyncConfig).where(
                IntegrationSyncConfig.interface_id == interface.id,
                IntegrationSyncConfig.is_enabled.is_(True),
            )
        ).first()
        if interface is not None and interface.outbound_enabled
        else None
    )
    if config is None:
        raise FxSyncNotConfiguredError
    created = IntegrationSyncService(session).create_manual_run(
        config.id,
        TriggerRequest(reason="财务手动同步汇率"),
        actor_ref=actor,
        request_id=request_id,
        account_refs=frozenset({config.source_account_ref}),
    )
    try:
        dispatch_sync_run(created.run_id)
    except TaskDispatchError as exc:
        raise FxSyncUnavailableError from exc
    return latest_fx_sync(session)
