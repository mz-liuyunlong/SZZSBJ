from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.orm import Session

from app.modules.integration_sync.models import IntegrationSyncRun, IntegrationSyncRunEvent
from app.modules.integration_sync.repository import IntegrationSyncRepository


class IntegrationSchedulerService:
    """Bounded due-config claim; V1 does not calculate future cron instants."""

    def __init__(self, session: Session) -> None:
        self.session = session
        self.repository = IntegrationSyncRepository(session)

    def create_due_runs(self, *, limit: int = 100) -> list[UUID]:
        if not 1 <= limit <= 100:
            raise ValueError("scheduler batch limit is invalid")
        now = datetime.now(UTC)
        configs = self.repository.list_due_configs(now, limit=limit)
        run_ids: list[UUID] = []
        try:
            for config in configs:
                interface = self.repository.get_interface(config.interface_id)
                if interface is None or not interface.outbound_enabled:
                    continue
                if config.next_run_at is None:
                    continue
                key = f"schedule:{config.id}:{config.next_run_at.isoformat()}"
                if self.repository.find_run_by_idempotency(key) is not None:
                    continue
                run = IntegrationSyncRun(
                    config_id=config.id,
                    interface_id=interface.id,
                    provider=interface.provider,
                    interface_key=interface.interface_key,
                    source_account_ref=config.source_account_ref,
                    trigger_type="schedule",
                    status="queued",
                    idempotency_key=key,
                    reason="scheduled_sync",
                    queued_at=now,
                    work_items_total=0,
                    work_items_succeeded=0,
                    work_items_failed=0,
                    records_seen=0,
                    records_written=0,
                )
                self.repository.add_run(run)
                self.repository.add_event(
                    IntegrationSyncRunEvent(
                        run_id=run.id,
                        sequence_no=1,
                        event_type="state_transition",
                        from_status=None,
                        to_status="queued",
                        message_code="SYNC_RUN_QUEUED",
                        safe_details=None,
                        occurred_at=now,
                        actor_ref="scheduler",
                    )
                )
                config.last_scheduled_at = now
                config.next_run_at = None
                run_ids.append(run.id)
            self.session.commit()
        except Exception:
            self.session.rollback()
            raise
        return run_ids
