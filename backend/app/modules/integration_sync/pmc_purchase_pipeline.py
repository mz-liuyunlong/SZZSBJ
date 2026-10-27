"""One governed purchase run: collect all sources, publish DWD, then refresh DWS."""

from datetime import UTC, date, datetime, time, timedelta
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

from sqlalchemy import Engine
from sqlalchemy.orm import Session

from app.modules.integration_sync.handlers.lingxing_pmc_purchase_sync import PMC_PURCHASE_HANDLERS
from app.modules.integration_sync.models import (
    IntegrationInterface,
    IntegrationSyncConfig,
    IntegrationSyncRun,
    IntegrationSyncRunWorkItem,
    utc_now,
)
from app.modules.integration_sync.pmc_purchase_pipeline_catalog import (
    PURCHASE_PIPELINE_HANDLER,
    PURCHASE_PIPELINE_KEY,
    PURCHASE_SOURCE_KEYS,
)
from app.modules.integration_sync.pmc_purchase_pipeline_repository import (
    PurchasePipelineRepository,
    purchase_connection,
)
from app.modules.integration_sync.repository import IntegrationSyncRepository
from app.modules.pmc_purchase.publisher import PmcPurchaseDwdPublisher
from app.modules.pmc_purchase.refresh import PmcPurchaseDwsRefresher

EARLIEST_DATE = date(2026, 8, 1)
SOURCE_TIMEZONE = ZoneInfo("Asia/Shanghai")


class PurchasePipelineError(ValueError):
    """Only stable, non-sensitive failure codes owned by this orchestrator."""


def purchase_windows(start: date, end: date) -> list[tuple[date, date]]:
    """Source contracts use inclusive calendar dates and a maximum 90-day span."""
    if start < EARLIEST_DATE or end < start:
        raise PurchasePipelineError("SYNC_PURCHASE_WINDOW_INVALID")
    windows = []
    while start <= end:
        finish = min(start + timedelta(days=89), end)
        windows.append((start, finish))
        start = finish + timedelta(days=1)
    return windows


def execute_purchase_pipeline(engine: Engine, run_id: UUID) -> None:
    with purchase_connection(engine) as connection:
        if connection is None:
            # Move contention to the back of recovery, so this purchase run cannot
            # starve unrelated queued tasks in the existing one-per-tick dispatcher.
            with Session(engine) as session:
                run = IntegrationSyncRepository(session).get_run_for_update(run_id)
                if run is not None and run.status == "queued":
                    run.queued_at = utc_now()
                    session.commit()
            return
        with Session(bind=connection) as session:
            repository = PurchasePipelineRepository(session)
            repository.recover_interrupted()
            session.commit()
            PurchasePipeline(session).execute(run_id)


def recover_purchase_pipeline(engine: Engine) -> list[UUID]:
    """The scheduler can recover a crashed manual run even with schedules disabled."""
    with purchase_connection(engine) as connection:
        if connection is None:
            return []
        with Session(bind=connection) as session:
            recovered = PurchasePipelineRepository(session).recover_interrupted()
            session.commit()
            return recovered


class PurchasePipeline:
    """Requires the purchase advisory lock; separate stage commits preserve evidence."""

    def __init__(self, session: Session) -> None:
        self.session = session
        self.repository = PurchasePipelineRepository(session)
        self.sync = IntegrationSyncRepository(session)

    def execute(self, run_id: UUID) -> None:
        run = self.sync.get_run_for_update(run_id)
        if run is None or run.status != "queued":
            return
        stage: IntegrationSyncRunWorkItem | None = None
        try:
            sources = self._preflight(run)
            self._set_window(run)
            assert run.window_start is not None and run.window_end is not None
            windows = purchase_windows(run.window_start.date(), run.window_end.date())
            run.status = "running"
            run.started_at = utc_now()
            run.work_items_total = len(windows) * len(sources) + 2
            self.session.commit()
            ordinal = 0
            for key, source, interface in sources:
                for start, end in windows:
                    ordinal += 1
                    stage = None
                    stage = self._stage(run, ordinal, key, start, end)
                    self._collect(run, stage, source, interface, start, end)
                    self._finish_stage(run, stage)
            stage = None
            stage = self._stage(run, ordinal + 1, "publish_dwd")
            PmcPurchaseDwdPublisher(self.session).publish(source_account_ref=run.source_account_ref)
            self._finish_stage(run, stage)
            stage = None
            stage = self._stage(run, ordinal + 2, "refresh_dws")
            PmcPurchaseDwsRefresher(self.session).refresh(
                source_account_ref=run.source_account_ref,
                today=utc_now().astimezone(ZoneInfo("Asia/Taipei")).date(),
            )
            self._finish_stage(run, stage)
            stage = None
            # The succeeded parent window is the ONLY incremental watermark.
            run.status = "succeeded"
            run.finished_at = utc_now()
            self.session.commit()
        except Exception as error:
            self.session.rollback()
            run = self.sync.get_run_for_update(run_id)
            if run is None:
                raise
            self.repository.fail_unfinished_children(run)
            if stage is not None:
                stage.status = "failed"
                stage.finished_at = utc_now()
                stage.error_code = "SYNC_PURCHASE_STAGE_FAILED"
                stage.error_message = "采购同步阶段失败，请查看子任务日志后重试"
                run.work_items_failed += 1
            run.status = "failed"
            run.finished_at = utc_now()
            run.error_code = (
                str(error)
                if isinstance(error, PurchasePipelineError)
                else "SYNC_PURCHASE_PIPELINE_FAILED"
            )
            run.error_message = "采购看板未完成刷新，请查看阶段日志"
            self.session.commit()

    def _preflight(
        self,
        run: IntegrationSyncRun,
    ) -> list[tuple[str, IntegrationSyncConfig, IntegrationInterface]]:
        config = self.repository.config_for(PURCHASE_PIPELINE_KEY, run.source_account_ref)
        interface = self.sync.get_interface(run.interface_id)
        if (
            run.provider != "lingxing"
            or run.interface_key != PURCHASE_PIPELINE_KEY
            or run.trigger_type not in {"manual", "schedule", "retry"}
            or config is None
            or config.id != run.config_id
            or not config.is_enabled
            or interface is None
            or interface.handler_key != PURCHASE_PIPELINE_HANDLER
            or not interface.outbound_enabled
            or (run.trigger_type == "schedule" and not config.schedule_enabled)
        ):
            raise PurchasePipelineError("SYNC_PURCHASE_PIPELINE_DISABLED")
        sources = []
        for key in PURCHASE_SOURCE_KEYS:
            source = self.repository.config_for(key, run.source_account_ref)
            item = self.sync.get_interface(source.interface_id) if source else None
            if source is None or item is None or not item.outbound_enabled:
                raise PurchasePipelineError("SYNC_PURCHASE_SOURCE_DISABLED")
            if item.handler_key != PMC_PURCHASE_HANDLERS[key].handler_key:
                raise PurchasePipelineError("SYNC_PURCHASE_SOURCE_CONTRACT_INVALID")
            spec = PMC_PURCHASE_HANDLERS[key].spec
            policy = self.sync.get_retention_policy(spec.retention_policy_key)
            if (
                item.endpoint_path != spec.endpoint_path
                or item.method != "POST"
                or policy is None
                or not policy.is_active
                or source.retention_policy_id != policy.id
            ):
                raise PurchasePipelineError("SYNC_PURCHASE_SOURCE_CONTRACT_INVALID")
            sources.append((key, source, item))
        return sources

    def _set_window(self, run: IntegrationSyncRun) -> None:
        if run.window_start is not None or run.window_end is not None:
            if run.window_start is None or run.window_end is None:
                raise PurchasePipelineError("SYNC_PURCHASE_WINDOW_REQUIRED")
            return  # Retry preserves the exact failed window.
        watermark = self.repository.watermark(run.source_account_ref)
        start = (
            max(EARLIEST_DATE, watermark.date() - timedelta(days=1)) if watermark else EARLIEST_DATE
        )
        end = utc_now().astimezone(SOURCE_TIMEZONE).date()
        run.window_start = datetime.combine(start, time.min, UTC)
        run.window_end = datetime.combine(end, time.min, UTC)

    def _stage(
        self,
        run: IntegrationSyncRun,
        ordinal: int,
        name: str,
        start: date | None = None,
        end: date | None = None,
    ) -> IntegrationSyncRunWorkItem:
        # Existing work-item schema is reused as a bounded orchestration step.
        work = IntegrationSyncRunWorkItem(
            id=uuid4(),
            run_id=run.id,
            ordinal=ordinal,
            request_kind="offset_page",
            offset_value=ordinal - 1,
            length_value=1,
            status="running",
            attempt_count=1,
            request_safe_params={
                "stage": name,
                "start_date": str(start) if start else None,
                "end_date": str(end) if end else None,
            },
            started_at=utc_now(),
        )
        self.session.add(work)
        self.session.commit()
        return work

    def _collect(
        self,
        run: IntegrationSyncRun,
        work: IntegrationSyncRunWorkItem,
        source: IntegrationSyncConfig,
        interface: IntegrationInterface,
        start: date,
        end: date,
    ) -> None:
        child = IntegrationSyncRun(
            id=uuid4(),
            config_id=source.id,
            interface_id=interface.id,
            provider="lingxing",
            interface_key=interface.interface_key,
            source_account_ref=run.source_account_ref,
            trigger_type="manual",
            status="queued",
            parent_run_id=run.id,
            idempotency_key=f"purchase:{run.id}:{work.ordinal}",
            requested_by=run.requested_by,
            request_id=run.request_id,
            reason="purchase_board_pipeline",
            queued_at=utc_now(),
            window_start=datetime.combine(start, time.min, UTC),
            window_end=datetime.combine(end, time.min, UTC),
        )
        self.session.add(child)
        work.request_safe_params = {**work.request_safe_params, "child_run_id": str(child.id)}
        self.session.commit()
        PMC_PURCHASE_HANDLERS[interface.interface_key](
            self.session,
            pipeline_parent_id=run.id,
        ).execute(child, interface)
        if child.status != "succeeded":
            work.error_code = child.error_code
            raise PurchasePipelineError("SYNC_PURCHASE_SOURCE_FAILED")
        work.response_count = child.records_written
        run.records_seen += child.records_seen
        run.records_written += child.records_written

    def _finish_stage(self, run: IntegrationSyncRun, work: IntegrationSyncRunWorkItem) -> None:
        work.status = "succeeded"
        work.finished_at = utc_now()
        run.work_items_succeeded += 1
        self.session.commit()
