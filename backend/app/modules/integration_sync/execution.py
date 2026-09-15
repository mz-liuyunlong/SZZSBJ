import hashlib
from datetime import timedelta
from uuid import UUID, uuid4

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.modules.integration_sync.handlers.lingxing_batch_product_info import (
    BatchPlan,
    LingxingBatchGetProductInfoSyncHandler,
)
from app.modules.integration_sync.handlers.lingxing_product_info_executor import (
    PRODUCT_INFO_BATCH_SIZE,
    LingxingProductInfoExecutor,
    product_info_client,
)
from app.modules.integration_sync.handlers.lingxing_product_list_sync import (
    LingxingProductListSyncHandler,
)
from app.modules.integration_sync.models import (
    IntegrationSyncLock,
    IntegrationSyncRun,
    IntegrationSyncRunEvent,
    utc_now,
)
from app.modules.integration_sync.product_info_runner import ProductInfoOneTimeRunError
from app.modules.integration_sync.repository import IntegrationSyncRepository

LOCK_LEASE_DURATION = timedelta(minutes=5)


class SyncRunExecutionService:
    """Durable governed execution for supported integration runs."""

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
        if run.provider == "lingxing" and run.interface_key == "productList":
            LingxingProductListSyncHandler(self.session).execute(run, interface)
            return

        is_productinfo = (
            run.provider == "lingxing"
            and run.interface_key == "batchGetProductInfo"
            and interface.handler_key == LingxingBatchGetProductInfoSyncHandler.handler_key
        )
        if is_productinfo:
            if not interface.outbound_enabled:
                self._fail(run, "SYNC_INTERFACE_DISABLED")
                return
            if run.trigger_type not in {"manual", "schedule", "retry"}:
                self._fail(run, "SYNC_TRIGGER_NOT_EXECUTABLE")
                return
            if run.config_id is None:
                self._fail(run, "SYNC_CONFIG_NOT_FOUND")
                return
            config = self.repository.get_config(
                run.config_id,
                frozenset({run.source_account_ref}),
            )
            if config is None:
                self._fail(run, "SYNC_CONFIG_NOT_FOUND")
                return
            if not config.is_enabled:
                self._fail(run, "SYNC_CONFIG_DISABLED")
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
            expires_at=now + LOCK_LEASE_DURATION,
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
                return

            plan = self.load_or_freeze_product_info_plan(run)
            if plan is None:
                return

            with product_info_client() as client:
                LingxingProductInfoExecutor(
                    self.session,
                    client=client,
                    heartbeat=lambda: self._heartbeat_lock(run.id),
                ).execute_existing_run(
                    run=run,
                    plan=plan,
                )
        except ProductInfoOneTimeRunError as error:
            self.session.rollback()
            recovered = self.repository.get_run_for_update(run_id)
            if recovered is not None and recovered.status == "running":
                self._fail(recovered, _safe_error_code(error))
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

    def load_or_freeze_product_info_plan(
        self,
        run: IntegrationSyncRun,
    ) -> BatchPlan | None:
        """Return persisted plan, freezing active identity membership exactly once."""
        work_items = self.repository.list_work_items_for_run(run.id)
        batch_items = self.repository.list_batch_items_for_run(run.id)

        if work_items or batch_items:
            if not work_items or not batch_items:
                self._fail(run, "SYNC_FROZEN_PLAN_INVALID")
                return None
            run.work_items_total = len(work_items)
            return BatchPlan(tuple(work_items), tuple(batch_items))

        ids = self.repository.list_active_lingxing_sku_ids(run.source_account_ref)
        if not ids:
            self._fail(run, "SYNC_IDENTITY_SET_EMPTY")
            return None

        batch_size = self.repository.batch_size_for_run(run) or PRODUCT_INFO_BATCH_SIZE
        if not 1 <= batch_size <= PRODUCT_INFO_BATCH_SIZE:
            self._fail(run, "SYNC_BATCH_SIZE_INVALID")
            return None

        plan = LingxingBatchGetProductInfoSyncHandler().build_plan(
            run_id=run.id,
            source_account_ref=run.source_account_ref,
            lingxing_sku_ids=ids,
            batch_size=batch_size,
        )
        try:
            self.repository.add_work_items(plan.work_items)
            self.repository.add_batch_items(plan.batch_items)
            run.work_items_total = len(plan.work_items)
            self.session.commit()
        except Exception:
            self.session.rollback()
            raise
        return plan

    def _heartbeat_lock(self, run_id: UUID) -> None:
        # Renew before outbound/provider publication work so another worker
        # cannot mistake a healthy long-running run for an expired lease.
        lock = self.repository.get_lock_for_run_for_update(run_id)
        if lock is None:
            raise ProductInfoOneTimeRunError("SYNC_LOCK_LEASE_LOST")
        now = utc_now()
        lock.heartbeat_at = now
        lock.expires_at = now + LOCK_LEASE_DURATION
        self.session.commit()

    def _fail(self, run: IntegrationSyncRun, error_code: str) -> None:
        from_status = run.status
        run.status = "failed"
        run.finished_at = utc_now()
        run.error_code = error_code
        run.error_message = "同步执行失败"
        self._event(run.id, from_status, "failed", error_code)
        self.session.commit()

    def _event(
        self,
        run_id: UUID,
        from_status: str | None,
        to_status: str,
        message_code: str,
    ) -> None:
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


def _safe_error_code(error: Exception) -> str:
    code = str(error)
    return code if code.isupper() and len(code) <= 128 else "SYNC_EXECUTION_FAILED"
