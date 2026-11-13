"""WFS 费用明细页面的「同步」按钮：建一条任务中心运行记录，交给现有队列执行。

锁（Rocky 2026-11-13）：按一次 90 分钟内不能再按；最近一次同步失败，60 分钟内不能按；
正在跑的时候也不能按。按钮的人按 action:finance:wfs-fees:sync 权限放（未分配前只有管理员）。
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.integration_sync.models import IntegrationSyncRun, IntegrationSyncRunWorkItem
from app.modules.integration_sync.repository import IntegrationSyncRepository
from app.modules.integration_sync.schemas import TriggerRequest
from app.modules.integration_sync.service import IntegrationSyncService
from app.modules.integration_sync.tasks import TaskDispatchError, dispatch_sync_run
from app.modules.integration_sync.wfs_report_catalog import (
    WFS_REPORT_PROVIDER,
    WFS_REPORT_SOURCE_REF,
    WFS_REPORT_SYNC_SPEC,
)
from app.modules.wfs_fees.schemas import WfsFeeSyncData, WfsFeeSyncStoreError
from app.modules.wfs_fees.sync_jobs import FAILURE_LOCK, MANUAL_LOCK

SPEC = WFS_REPORT_SYNC_SPEC
ACTIVE = ("queued", "running")


class WfsSyncNotConfiguredError(Exception):
    pass


class WfsSyncUnavailableError(Exception):
    pass


class WfsSyncLockedError(Exception):
    def __init__(self, data: WfsFeeSyncData) -> None:
        super().__init__("WFS_FEE_SYNC_LOCKED")
        self.data = data


def _runs() -> Any:
    return select(IntegrationSyncRun).where(
        IntegrationSyncRun.provider == WFS_REPORT_PROVIDER,
        IntegrationSyncRun.interface_key == SPEC.interface_key,
    )


def sync_status(session: Session, *, now: datetime | None = None) -> WfsFeeSyncData:
    now = now or datetime.now(UTC)
    run = session.scalars(_runs().order_by(IntegrationSyncRun.queued_at.desc()).limit(1)).first()
    if run is None:
        return WfsFeeSyncData()
    success = session.scalars(
        _runs()
        .where(IntegrationSyncRun.status == "succeeded")
        .order_by(IntegrationSyncRun.finished_at.desc())
        .limit(1)
    ).first()
    manual = session.scalars(
        _runs()
        .where(IntegrationSyncRun.trigger_type == "manual")
        .order_by(IntegrationSyncRun.queued_at.desc())
        .limit(1)
    ).first()
    locks: list[tuple[datetime, str]] = []
    if manual is not None and manual.queued_at + MANUAL_LOCK > now:
        locks.append((manual.queued_at + MANUAL_LOCK, "manual"))
    if run.status == "failed" and run.finished_at and run.finished_at + FAILURE_LOCK > now:
        locks.append((run.finished_at + FAILURE_LOCK, "failed"))
    locked_until, lock_reason = max(locks) if locks else (None, None)
    if run.status in ACTIVE:
        lock_reason = "running"
    failed_stores = [
        WfsFeeSyncStoreError(store_code=item.scope_key or "", error_code=item.error_code or "")
        for item in session.scalars(
            select(IntegrationSyncRunWorkItem)
            .where(
                IntegrationSyncRunWorkItem.run_id == run.id,
                IntegrationSyncRunWorkItem.status == "failed",
            )
            .order_by(IntegrationSyncRunWorkItem.ordinal)
        )
    ]
    return WfsFeeSyncData(
        run_id=run.id,
        status=run.status,
        trigger=run.trigger_type,
        started_at=run.started_at,
        finished_at=run.finished_at,
        error_code=run.error_code,
        records_written=run.records_written,
        last_success_at=success.finished_at if success else None,
        locked_until=locked_until,
        lock_reason=lock_reason,
        failed_stores=failed_stores,
    )


def start_sync(
    session: Session, *, actor: str, request_id: str, now: datetime | None = None
) -> WfsFeeSyncData:
    """在跑 / 在锁定时间内：不开新的，抛 WfsSyncLockedError（带当前状态和解锁时间）。"""
    current = sync_status(session, now=now)
    if current.lock_reason is not None:
        raise WfsSyncLockedError(current)
    repository = IntegrationSyncRepository(session)
    interface = repository.get_interface_by_key(WFS_REPORT_PROVIDER, SPEC.interface_key)
    config = (
        repository.get_config_by_scope(interface.id, WFS_REPORT_SOURCE_REF)
        if interface is not None
        else None
    )
    if (
        interface is None
        or not interface.outbound_enabled
        or config is None
        or not config.is_enabled
    ):
        raise WfsSyncNotConfiguredError
    created = IntegrationSyncService(session).create_manual_run(
        config.id,
        TriggerRequest(reason="财务手动同步 WFS 费用报表"),
        actor_ref=actor,
        request_id=request_id,
        account_refs=frozenset({WFS_REPORT_SOURCE_REF}),
    )
    try:
        dispatch_sync_run(created.run_id)
    except TaskDispatchError as exc:
        raise WfsSyncUnavailableError from exc
    return sync_status(session, now=now)
