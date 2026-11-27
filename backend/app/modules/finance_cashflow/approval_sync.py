"""日记账页面的「同步审批单」按钮：建一条任务中心运行记录，交给现有队列执行。"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.finance_cashflow.schemas import CashflowApprovalSyncData
from app.modules.integration_sync.finance_approval_catalog import (
    FINANCE_APPROVAL_PROVIDER,
    FINANCE_APPROVAL_SOURCE_REF,
    FINANCE_APPROVAL_SYNC_SPEC,
)
from app.modules.integration_sync.models import IntegrationSyncRun
from app.modules.integration_sync.repository import IntegrationSyncRepository
from app.modules.integration_sync.schemas import TriggerRequest
from app.modules.integration_sync.service import IntegrationSyncService
from app.modules.integration_sync.tasks import TaskDispatchError, dispatch_sync_run

SPEC = FINANCE_APPROVAL_SYNC_SPEC
ACTIVE = ("queued", "running")


class ApprovalSyncNotConfiguredError(Exception):
    pass


class ApprovalSyncUnavailableError(Exception):
    pass


def _runs() -> Any:
    return select(IntegrationSyncRun).where(
        IntegrationSyncRun.provider == FINANCE_APPROVAL_PROVIDER,
        IntegrationSyncRun.interface_key == SPEC.interface_key,
    )


def latest_sync(session: Session) -> CashflowApprovalSyncData:
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


def start_sync(session: Session, *, actor: str, request_id: str) -> CashflowApprovalSyncData:
    """已经有一次在跑就不再开新的，直接返回它的状态。"""
    running = session.scalars(_runs().where(IntegrationSyncRun.status.in_(ACTIVE)).limit(1)).first()
    if running is not None:
        return latest_sync(session)
    repository = IntegrationSyncRepository(session)
    interface = repository.get_interface_by_key(FINANCE_APPROVAL_PROVIDER, SPEC.interface_key)
    config = (
        repository.get_config_by_scope(interface.id, FINANCE_APPROVAL_SOURCE_REF)
        if interface is not None
        else None
    )
    if config is None or not config.is_enabled:
        raise ApprovalSyncNotConfiguredError
    created = IntegrationSyncService(session).create_manual_run(
        config.id,
        TriggerRequest(reason="财务手动同步审批单"),
        actor_ref=actor,
        request_id=request_id,
        account_refs=frozenset({FINANCE_APPROVAL_SOURCE_REF}),
    )
    try:
        dispatch_sync_run(created.run_id)
    except TaskDispatchError as exc:
        raise ApprovalSyncUnavailableError from exc
    return latest_sync(session)
