import hashlib
from datetime import timedelta
from uuid import UUID, uuid4

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.modules.integration_sync.handlers.lingxing_batch_product_info import (
    LingxingBatchGetProductInfoSyncHandler,
)
from app.modules.integration_sync.models import (
    IntegrationSyncLock,
    IntegrationSyncRun,
    IntegrationSyncRunEvent,
    utc_now,
)
from app.modules.integration_sync.repository import IntegrationSyncRepository


class SyncRunExecutionService:
    """Durable claim/lock skeleton; V1 handlers make no provider request."""

    def __init__(self, session: Session) -> None:
        self.session = session
        self.repository = IntegrationSyncRepository(session)

    def execute(self, run_id: UUID) -> None:
        run = self.repository.get_run_for_update(run_id)
        if run is None or run.status != "queued":
            return
        interface = self.repository.get_interface(run.interface_id)
        if interface is None:
            self._fail(run, "SYNC_INTERFACE_NOT_FOUND")
            return
        now = utc_now()
        existing_lock = self.repository.get_lock_for_interface(run.provider, run.interface_key)
        if existing_lock is not None:
            if existing_lock.expires_at > now:
                self.session.rollback()
                return
            stale_run = self.repository.get_run_for_update(existing_lock.run_id)
            if stale_run is not None and stale_run.status == "running":
                stale_run.status = "failed"
                stale_run.finished_at = now
                stale_run.error_code = "SYNC_LOCK_LEASE_EXPIRED"
                stale_run.error_message = "同步锁租约已过期"
                self._event(
                    stale_run.id,
                    "running",
                    "failed",
                    "SYNC_LOCK_LEASE_EXPIRED",
                )
            self.repository.delete_lock(existing_lock)
        token = uuid4().hex
        lease = IntegrationSyncLock(
            id=uuid4(),
            provider=run.provider,
            interface_key=run.interface_key,
            run_id=run.id,
            lock_token_hash=hashlib.sha256(token.encode()).hexdigest(),
            acquired_at=now,
            heartbeat_at=now,
            expires_at=now + timedelta(minutes=5),
        )
        try:
            self.repository.add_lock(lease)
            run.status = "running"
            run.started_at = now
            self._event(run.id, "queued", "running", "SYNC_RUN_STARTED")
            self.session.commit()
        except IntegrityError:
            self.session.rollback()
            return
        try:
            if interface.handler_key != LingxingBatchGetProductInfoSyncHandler.handler_key:
                self._fail(run, "SYNC_HANDLER_NOT_EXECUTABLE")
            else:
                ids = self.repository.list_active_lingxing_sku_ids(run.source_account_ref)
                if not ids:
                    self._fail(run, "SYNC_IDENTITY_SET_EMPTY")
                else:
                    plan = LingxingBatchGetProductInfoSyncHandler().build_plan(
                        run_id=run.id,
                        source_account_ref=run.source_account_ref,
                        lingxing_sku_ids=ids,
                        batch_size=self.repository.batch_size_for_run(run) or 100,
                    )
                    self.repository.add_work_items(plan.work_items)
                    self.repository.add_batch_items(plan.batch_items)
                    run.work_items_total = len(plan.work_items)
                    self._fail(run, "SYNC_OUTBOUND_NOT_AUTHORIZED")
        except Exception:
            self.session.rollback()
            recovered = self.repository.get_run_for_update(run_id)
            if recovered is not None and recovered.status == "running":
                self._fail(recovered, "SYNC_EXECUTION_FAILED")
            raise
        finally:
            current_lock = self.repository.get_lock_for_run(run_id)
            if current_lock is not None:
                self.repository.delete_lock(current_lock)
                self.session.commit()

    def _fail(self, run: IntegrationSyncRun, error_code: str) -> None:
        run.status = "failed"
        run.finished_at = utc_now()
        run.error_code = error_code
        run.error_message = "同步执行未启用"
        self._event(run.id, "running", "failed", error_code)
        self.session.commit()

    def _event(self, run_id: UUID, from_status: str, to_status: str, message_code: str) -> None:
        self.repository.add_event(
            IntegrationSyncRunEvent(
                run_id=run_id,
                sequence_no=self.repository.next_event_sequence(run_id),
                event_type="state_transition",
                from_status=from_status,
                to_status=to_status,
                message_code=message_code,
                safe_details=None,
                occurred_at=utc_now(),
                actor_ref="worker",
            )
        )
