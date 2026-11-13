"""任务中心同步任务：WFS 费用报表（沃尔玛接口）→ WFS 费用明细。

手动（页面「同步」按钮）、定时（任务中心，建议每小时）、重试都走这里。
一次运行：读远程采集落下的入库货件明细 → 给到期的每店 × 每类 × 每期排任务 →
逐店上传执行器跑「查已有请求 / 下单 / 查状态 / 下载」→ 导入费用明细。
每店一条分步记录；一家店失败不影响别的店，但整次运行记失败（任务中心标红、页面提示）。
"""

from __future__ import annotations

import logging
import os
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.api import ApiError
from app.integrations.walmart import wfs_report_runner as runner
from app.integrations.walmart.remote_dispatch import DispatchRejected
from app.modules.integration_sync.models import (
    IntegrationInterface,
    IntegrationSyncRun,
    IntegrationSyncRunWorkItem,
    utc_now,
)
from app.modules.integration_sync.repository import IntegrationSyncRepository
from app.modules.integration_sync.wfs_report_catalog import (
    WFS_REPORT_PROVIDER,
    WFS_REPORT_SYNC_SPEC,
)
from app.modules.walmart_remote.store_mapping import remote_store_mapping
from app.modules.wfs_fees.sync_jobs import RemoteRun, StoreRef, SyncOutcome, WfsReportSync

logger = logging.getLogger("app.integration_sync.wfs_fee_reports")

SPEC = WFS_REPORT_SYNC_SPEC
EXECUTABLE_TRIGGERS = frozenset({"manual", "schedule", "retry"})
Executor = Callable[[StoreRef, dict[str, Any]], RemoteRun]


class WfsReportSyncError(RuntimeError):
    """固定错误码，不带远端输出。"""


@dataclass(slots=True)
class WfsReportSyncResult:
    run_id: UUID
    status: str
    outcome: SyncOutcome | None = None


def approved_stores() -> list[StoreRef]:
    """已批准、有路由、有店铺 ID 的店；哪一项缺了都不跑。"""
    routes = runner.approved_routes()
    try:
        mapping = remote_store_mapping()
    except ApiError:
        raise DispatchRejected("REMOTE_STORE_MAPPING_INVALID") from None
    stores = [
        StoreRef(store_id=store_id, store_code=code)
        for store_id, code in sorted(mapping.items(), key=lambda item: item[1])
        if code in routes
    ]
    if not stores:
        raise DispatchRejected("REMOTE_STORE_NOT_APPROVED")
    return stores


def remote_executor(run_id: UUID) -> Executor:
    routes = runner.approved_routes()
    local_root = Path(tempfile.gettempdir()) / "szzsbj-wfs-reports"

    def execute(store: StoreRef, plan: dict[str, Any]) -> RemoteRun:
        result = runner.run_plan(
            route=routes[store.store_code],
            run_id=f"wfs-{run_id.hex[:12]}-{store.store_code.lower()}",
            plan=plan,
            token_supplier=runner.store_token_supplier(store.store_code),
            local_root=local_root,
        )
        return RemoteRun(result.results, result.files_dir, result.local_dir, result.exit_code)

    return execute


def archive_root() -> Path | None:
    raw = os.getenv("SZZSBJ_WALMART_REMOTE_ARCHIVE_ROOT", "")
    return Path(raw) if raw else None


# 测试和本地预览可以换掉；正式环境只用远端执行。
executor_factory: Callable[[UUID], Executor] = remote_executor
stores_factory: Callable[[], list[StoreRef]] = approved_stores
archive_root_factory: Callable[[], Path | None] = archive_root


class WalmartWfsFeeReportsHandler:
    handler_key = SPEC.handler_key

    def __init__(self, session: Session) -> None:
        self.session = session
        self.repository = IntegrationSyncRepository(session)

    def execute(
        self, run: IntegrationSyncRun, interface: IntegrationInterface
    ) -> WfsReportSyncResult:
        try:
            self._preflight(run, interface)
            stores = stores_factory()
            execute = executor_factory(run.id)
        except (WfsReportSyncError, DispatchRejected) as error:
            return self._fail(run, str(error))
        try:
            run.status = "running"
            run.started_at = utc_now()
            self.session.commit()
        except IntegrityError:
            # 同一个任务已经有一次在跑（运行表的唯一约束）：这次直接记失败，不重入。
            self.session.rollback()
            recovered = self.repository.get_run_for_update(run.id)
            if recovered is None:
                raise WfsReportSyncError("SYNC_WFS_REPORTS_RUN_MISSING") from None
            return self._fail(recovered, "SYNC_WFS_REPORTS_ALREADY_RUNNING")
        now = datetime.now(UTC)
        try:
            outcome = WfsReportSync(self.session).run(
                stores,
                now,
                manual=run.trigger_type == "manual",
                actor=run.requested_by or "system",
                run_id=run.id,
                execute=execute,
                archive_root=archive_root_factory(),
            )
        except Exception:
            self.session.rollback()
            logger.exception("wfs_fee_reports_failed run_id=%s", run.id)
            return self._fail(run, "SYNC_WFS_REPORTS_FAILED")
        for ordinal, item in enumerate(outcome.stores, start=1):
            self.repository.add_work_items(
                [
                    IntegrationSyncRunWorkItem(
                        id=uuid4(),
                        run_id=run.id,
                        ordinal=ordinal,
                        request_kind=SPEC.request_kind,
                        scope_key=item.store.store_code,
                        status="failed" if item.error else "succeeded",
                        attempt_count=1,
                        offset_value=0,
                        length_value=SPEC.default_page_size,
                        request_safe_params={
                            "store": item.store.store_code,
                            "imported": item.imported,
                            "pending": item.pending,
                            "failed_jobs": item.failed_jobs,
                        },
                        response_count=item.imported,
                        error_code=item.error,
                        started_at=now,
                        finished_at=utc_now(),
                    )
                ]
            )
            run.work_items_total += 1
            if item.error:
                run.work_items_failed += 1
            else:
                run.work_items_succeeded += 1
        run.records_seen = sum(i.imported + i.pending + i.failed_jobs for i in outcome.stores)
        run.records_written = sum(item.imported for item in outcome.stores)
        summary = (
            f"imported={run.records_written} inbound_items={outcome.inbound_items} "
            + " ".join(outcome.errors)
        ).strip()[:1000]
        if outcome.errors:
            run.status = "failed"
            run.error_code = "SYNC_WFS_REPORTS_STORE_FAILED"
        else:
            run.status = "succeeded"
        run.error_message = summary
        run.finished_at = utc_now()
        self.session.commit()
        logger.info("wfs_fee_reports_finished run_id=%s status=%s", run.id, run.status)
        return WfsReportSyncResult(run_id=run.id, status=run.status, outcome=outcome)

    def _preflight(self, run: IntegrationSyncRun, interface: IntegrationInterface) -> None:
        if (
            run.trigger_type not in EXECUTABLE_TRIGGERS
            or run.provider != WFS_REPORT_PROVIDER
            or run.interface_key != SPEC.interface_key
            or interface.handler_key != SPEC.handler_key
            or not interface.outbound_enabled
            or run.config_id is None
        ):
            raise WfsReportSyncError("SYNC_WFS_REPORTS_NOT_AUTHORIZED")
        config = self.repository.get_config(run.config_id, frozenset({run.source_account_ref}))
        if config is None or not config.is_enabled:
            raise WfsReportSyncError("SYNC_WFS_REPORTS_CONFIG_DISABLED")

    def _fail(self, run: IntegrationSyncRun, error_code: str) -> WfsReportSyncResult:
        run.status = "failed"
        run.error_code = error_code[:128]
        run.error_message = "WFS fee report sync failed"
        run.finished_at = utc_now()
        self.session.commit()
        logger.warning("wfs_fee_reports_failed run_id=%s error_code=%s", run.id, error_code)
        return WfsReportSyncResult(run_id=run.id, status="failed")
