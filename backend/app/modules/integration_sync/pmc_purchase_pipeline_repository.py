"""Purchase-only persistence and a connection-held lock spanning stage commits."""

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import Engine, func, select, text
from sqlalchemy.engine import Connection
from sqlalchemy.orm import Session

from app.modules.integration_sync.models import (
    IntegrationInterface,
    IntegrationSyncConfig,
    IntegrationSyncRun,
    IntegrationSyncRunWorkItem,
    utc_now,
)
from app.modules.integration_sync.pmc_purchase_pipeline_catalog import (
    PURCHASE_PIPELINE_CRON,
    PURCHASE_PIPELINE_HANDLER,
    PURCHASE_PIPELINE_KEY,
    PURCHASE_PIPELINE_PATH,
    PURCHASE_SOURCE_KEYS,
)

# One lock for purchase feeds: the existing provider/interface running constraint
# and token budget are shared across accounts. No other business uses this lock.
PURCHASE_LOCK_ID = 730271901


@contextmanager
def purchase_connection(engine: Engine) -> Iterator[Connection | None]:
    """Pin writes to the lock connection so a lost lock also stops publication."""
    if engine.dialect.name != "postgresql":
        raise RuntimeError("SYNC_PURCHASE_POSTGRESQL_REQUIRED")
    with engine.connect() as connection:
        acquired = connection.scalar(
            text("SELECT pg_try_advisory_lock(:key)"), {"key": PURCHASE_LOCK_ID}
        )
        connection.commit()
        if not acquired:
            yield None
            return
        try:
            yield connection
        finally:
            connection.rollback()
            try:
                connection.execute(
                    text("SELECT pg_advisory_unlock(:key)"), {"key": PURCHASE_LOCK_ID}
                )
                connection.commit()
            except Exception:
                # Never return a possibly still locked physical connection to the pool.
                connection.invalidate()
                raise


class PurchasePipelineRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def config_for(self, key: str, account: str) -> IntegrationSyncConfig | None:
        return self.session.scalar(
            select(IntegrationSyncConfig)
            .join(IntegrationInterface)
            .where(
                IntegrationInterface.provider == "lingxing",
                IntegrationInterface.interface_key == key,
                IntegrationSyncConfig.source_account_ref == account,
            )
        )

    def watermark(self, account: str) -> datetime | None:
        return self.session.scalar(
            select(func.max(IntegrationSyncRun.window_end)).where(
                IntegrationSyncRun.provider == "lingxing",
                IntegrationSyncRun.interface_key == PURCHASE_PIPELINE_KEY,
                IntegrationSyncRun.source_account_ref == account,
                IntegrationSyncRun.status == "succeeded",
            )
        )

    def recover_interrupted(self) -> list[UUID]:
        """Only call while holding the exclusive purchase connection lock."""
        parents = self.session.scalars(
            select(IntegrationSyncRun).where(
                IntegrationSyncRun.provider == "lingxing",
                IntegrationSyncRun.interface_key == PURCHASE_PIPELINE_KEY,
                IntegrationSyncRun.status == "running",
            )
        ).all()
        for parent in parents:
            children = self.session.scalars(
                select(IntegrationSyncRun).where(
                    IntegrationSyncRun.parent_run_id == parent.id,
                    IntegrationSyncRun.status.in_(("running", "queued")),
                )
            ).all()
            for run in (parent, *children):
                run.status = "failed"
                run.finished_at = utc_now()
                run.error_code = "SYNC_PURCHASE_INTERRUPTED"
                run.error_message = "采购同步进程中断，请重试完整任务"
                for work in self.session.scalars(
                    select(IntegrationSyncRunWorkItem).where(
                        IntegrationSyncRunWorkItem.run_id == run.id,
                        IntegrationSyncRunWorkItem.status == "running",
                    )
                ):
                    work.status = "failed"
                    work.finished_at = utc_now()
                    work.error_code = run.error_code
                    run.work_items_failed += 1
        return [parent.id for parent in parents]

    def fail_unfinished_children(self, parent: IntegrationSyncRun) -> None:
        for child in self.session.scalars(
            select(IntegrationSyncRun).where(
                IntegrationSyncRun.parent_run_id == parent.id,
                IntegrationSyncRun.status.in_(("queued", "running")),
            )
        ):
            child.status = "failed"
            child.finished_at = utc_now()
            child.error_code = "SYNC_PURCHASE_INTERRUPTED"
            child.error_message = "采购子任务未正常完成，请从统一任务重试"
            for work in self.session.scalars(
                select(IntegrationSyncRunWorkItem).where(
                    IntegrationSyncRunWorkItem.run_id == child.id,
                    IntegrationSyncRunWorkItem.status == "running",
                )
            ):
                work.status = "failed"
                work.finished_at = utc_now()
                work.error_code = child.error_code
                child.work_items_failed += 1

    def register(self, account: str) -> IntegrationSyncConfig:
        """Register disabled config; do not enable external source calls or schedules."""
        sources = [self.config_for(key, account) for key in PURCHASE_SOURCE_KEYS]
        if any(config is None for config in sources):
            raise ValueError("SYNC_PURCHASE_SOURCE_CONFIG_MISSING")
        active = self.session.scalar(
            select(IntegrationSyncRun.id)
            .where(
                IntegrationSyncRun.provider == "lingxing",
                IntegrationSyncRun.interface_key.in_(
                    (*PURCHASE_SOURCE_KEYS, PURCHASE_PIPELINE_KEY)
                ),
                IntegrationSyncRun.source_account_ref == account,
                IntegrationSyncRun.status.in_(("queued", "running")),
            )
            .limit(1)
        )
        if active is not None:
            raise ValueError("SYNC_PURCHASE_RUN_ACTIVE")
        interface = self.session.scalar(
            select(IntegrationInterface).where(
                IntegrationInterface.provider == "lingxing",
                IntegrationInterface.interface_key == PURCHASE_PIPELINE_KEY,
            )
        )
        if interface is None:
            interface = IntegrationInterface(
                id=uuid4(),
                provider="lingxing",
                interface_key=PURCHASE_PIPELINE_KEY,
                display_name="采购看板同步",
                method="POST",
                endpoint_path=PURCHASE_PIPELINE_PATH,
                request_kind="offset_page",
                handler_key=PURCHASE_PIPELINE_HANDLER,
                # This is an internal dispatch gate, never an external-call authorization.
                contract_version="v1",
                outbound_enabled=True,
            )
            self.session.add(interface)
            self.session.flush()
        config = self.config_for(PURCHASE_PIPELINE_KEY, account)
        if config is None:
            config = IntegrationSyncConfig(
                id=uuid4(),
                interface_id=interface.id,
                source_account_ref=account,
                is_enabled=False,
                schedule_enabled=False,
                schedule_cron=PURCHASE_PIPELINE_CRON,
                schedule_timezone="UTC",
                page_size=500,
                max_pages=1000,
                max_attempts=3,
            )
            self.session.add(config)
        # Keep source metadata/history and outbound authorization; parent owns scheduling.
        for source in sources:
            if source is not None:
                source.schedule_enabled = False
                source.next_run_at = None
        return config
