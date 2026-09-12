import logging
from collections.abc import Mapping
from datetime import datetime
from typing import Literal, cast
from uuid import UUID, uuid4

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.api import ApiError, ErrorCode
from app.modules.integration_sync.models import (
    IntegrationSyncConfig,
    IntegrationSyncRun,
    IntegrationSyncRunEvent,
    utc_now,
)
from app.modules.integration_sync.repository import IntegrationSyncRepository
from app.modules.integration_sync.schemas import (
    BackfillRequest,
    IntegrationInterfaceRead,
    InterfaceListData,
    InterfaceListQuery,
    RawRequestMetadataListData,
    RawRequestMetadataRead,
    RequestKind,
    RunStatus,
    SyncConfigListData,
    SyncConfigListQuery,
    SyncConfigRead,
    SyncConfigUpdate,
    SyncRunCreated,
    SyncRunListData,
    SyncRunListQuery,
    SyncRunRead,
    TriggerRequest,
    TriggerType,
    WorkItemListData,
    WorkItemListQuery,
    WorkItemRead,
)

SYNC_INTERFACE_DISABLED = "SYNC_INTERFACE_DISABLED"
SYNC_RUN_NOT_RETRYABLE = "SYNC_RUN_NOT_RETRYABLE"
SYNC_RUN_ALREADY_RUNNING = "SYNC_RUN_ALREADY_RUNNING"

audit_logger = logging.getLogger("app.audit.integration_sync")


class IntegrationSyncService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.repository = IntegrationSyncRepository(session)

    def list_interfaces(self, query: InterfaceListQuery) -> tuple[InterfaceListData, int]:
        rows, total = self.repository.list_interfaces(
            provider=query.provider,
            enabled=query.enabled,
            page=query.page,
            page_size=query.page_size,
        )
        return (
            InterfaceListData(items=[IntegrationInterfaceRead.model_validate(row) for row in rows]),
            total,
        )

    def list_configs(
        self, query: SyncConfigListQuery, account_refs: frozenset[str]
    ) -> tuple[SyncConfigListData, int]:
        rows, total = self.repository.list_configs(
            account_refs=account_refs,
            provider=query.provider,
            interface_key=query.interface_key,
            enabled=query.enabled,
            page=query.page,
            page_size=query.page_size,
        )
        return (
            SyncConfigListData(items=[SyncConfigRead.model_validate(row) for row in rows]),
            total,
        )

    def update_config(
        self,
        config_id: UUID,
        payload: SyncConfigUpdate,
        account_refs: frozenset[str],
        *,
        actor_ref: str,
        request_id: str,
    ) -> SyncConfigRead:
        config = self._require_config(config_id, account_refs)
        values = payload.model_dump(exclude_unset=True)
        schedule_enabled = values.get("schedule_enabled", config.schedule_enabled)
        schedule_cron = values.get("schedule_cron", config.schedule_cron)
        if schedule_enabled and not schedule_cron:
            raise ApiError(code=ErrorCode.VALIDATION_ERROR, status_code=422)
        try:
            self.repository.update_config(config, values)
            self.session.commit()
        except IntegrityError:
            self.session.rollback()
            raise ApiError(code=ErrorCode.VALIDATION_ERROR, status_code=422) from None
        field_names = ",".join(changed_field_names(values))
        audit_logger.info(
            "integration_sync_config_updated actor_ref=%s request_id=%s "
            "config_id=%s reason=config_update before_fields=%s after_fields=%s",
            actor_ref,
            request_id,
            config_id,
            field_names,
            field_names,
        )
        return SyncConfigRead.model_validate(config)

    def create_manual_run(
        self,
        config_id: UUID,
        payload: TriggerRequest,
        *,
        actor_ref: str,
        request_id: str,
        account_refs: frozenset[str],
    ) -> SyncRunCreated:
        return self._create_config_run(
            config_id,
            trigger=TriggerType.MANUAL,
            payload=payload,
            actor_ref=actor_ref,
            request_id=request_id,
            account_refs=account_refs,
        )

    def create_backfill_run(
        self,
        config_id: UUID,
        payload: BackfillRequest,
        *,
        actor_ref: str,
        request_id: str,
        account_refs: frozenset[str],
    ) -> SyncRunCreated:
        return self._create_config_run(
            config_id,
            trigger=TriggerType.BACKFILL,
            payload=payload,
            actor_ref=actor_ref,
            request_id=request_id,
            account_refs=account_refs,
            window_start=payload.window_start,
            window_end=payload.window_end,
        )

    def create_retry_run(
        self,
        source_run_id: UUID,
        payload: TriggerRequest,
        *,
        actor_ref: str,
        request_id: str,
        account_refs: frozenset[str],
    ) -> SyncRunCreated:
        source = self._require_run(source_run_id, account_refs)
        if source.status not in {RunStatus.FAILED, RunStatus.CANCELED}:
            raise ApiError(code=SYNC_RUN_NOT_RETRYABLE, status_code=409)
        run = self._new_run(
            config_id=source.config_id,
            interface_id=source.interface_id,
            provider=source.provider,
            interface_key=source.interface_key,
            source_account_ref=source.source_account_ref,
            trigger=TriggerType.RETRY,
            payload=payload,
            actor_ref=actor_ref,
            request_id=request_id,
            parent_run_id=source.id,
            retry_of_run_id=source.id,
            window_start=source.window_start,
            window_end=source.window_end,
        )
        return self._persist_queued_run(run, actor_ref)

    def list_runs(
        self, query: SyncRunListQuery, account_refs: frozenset[str]
    ) -> tuple[SyncRunListData, int]:
        rows, total = self.repository.list_runs(
            account_refs=account_refs,
            provider=query.provider,
            interface_key=query.interface_key,
            status=query.status.value if query.status else None,
            trigger_type=query.trigger_type.value if query.trigger_type else None,
            created_from=query.created_from,
            created_to=query.created_to,
            page=query.page,
            page_size=query.page_size,
        )
        return SyncRunListData(items=[SyncRunRead.model_validate(row) for row in rows]), total

    def get_run(self, run_id: UUID, account_refs: frozenset[str]) -> SyncRunRead:
        return SyncRunRead.model_validate(self._require_run(run_id, account_refs))

    def list_work_items(
        self,
        run_id: UUID,
        query: WorkItemListQuery,
        account_refs: frozenset[str],
    ) -> tuple[WorkItemListData, int]:
        self._require_run(run_id, account_refs)
        rows, total = self.repository.list_work_items(
            run_id=run_id,
            status=query.status.value if query.status else None,
            request_kind=query.request_kind.value if query.request_kind else None,
            page=query.page,
            page_size=query.page_size,
        )
        return WorkItemListData(items=[WorkItemRead.model_validate(row) for row in rows]), total

    def list_raw_request_refs(
        self,
        run_id: UUID,
        *,
        page: int,
        page_size: int,
        account_refs: frozenset[str],
    ) -> tuple[RawRequestMetadataListData, int]:
        self._require_run(run_id, account_refs)
        rows, total = self.repository.list_raw_request_refs(
            run_id=run_id, page=page, page_size=page_size
        )
        items = [
            RawRequestMetadataRead(
                id=ref.id,
                run_id=ref.run_id,
                work_item_id=ref.work_item_id,
                raw_blob_id=ref.raw_blob_id,
                request_kind=RequestKind(ref.request_kind),
                attempt_no=ref.attempt_no,
                request_safe_params=ref.request_safe_params,
                http_status=ref.http_status,
                provider_code=ref.provider_code,
                is_success=ref.is_success,
                response_count=ref.response_count,
                response_hash=blob.response_hash,
                payload_bytes=blob.payload_bytes,
                storage_mode=cast(Literal["database", "archive"], blob.storage_mode),
                archive_present=blob.archive_uri is not None,
                requested_at=ref.requested_at,
                received_at=ref.received_at,
            )
            for ref, blob in rows
        ]
        return RawRequestMetadataListData(items=items), total

    def _create_config_run(
        self,
        config_id: UUID,
        *,
        trigger: TriggerType,
        payload: TriggerRequest,
        actor_ref: str,
        request_id: str,
        account_refs: frozenset[str],
        window_start: datetime | None = None,
        window_end: datetime | None = None,
    ) -> SyncRunCreated:
        config = self._require_config(config_id, account_refs)
        interface = self.repository.get_interface(config.interface_id)
        if interface is None:
            raise ApiError(code=ErrorCode.NOT_FOUND, status_code=404)
        if not config.is_enabled or not interface.outbound_enabled:
            raise ApiError(code=SYNC_INTERFACE_DISABLED, status_code=409)
        run = self._new_run(
            config_id=config.id,
            interface_id=interface.id,
            provider=interface.provider,
            interface_key=interface.interface_key,
            source_account_ref=config.source_account_ref,
            trigger=trigger,
            payload=payload,
            actor_ref=actor_ref,
            request_id=request_id,
            window_start=window_start,
            window_end=window_end,
        )
        return self._persist_queued_run(run, actor_ref)

    def _new_run(
        self,
        *,
        config_id: UUID | None,
        interface_id: UUID,
        provider: str,
        interface_key: str,
        source_account_ref: str,
        trigger: TriggerType,
        payload: TriggerRequest,
        actor_ref: str,
        request_id: str,
        parent_run_id: UUID | None = None,
        retry_of_run_id: UUID | None = None,
        window_start: datetime | None = None,
        window_end: datetime | None = None,
    ) -> IntegrationSyncRun:
        idempotency_key = payload.idempotency_key or f"{trigger.value}:{uuid4()}"
        existing = self.repository.find_run_by_idempotency(idempotency_key)
        if existing is not None:
            if existing.source_account_ref != source_account_ref:
                raise ApiError(code=ErrorCode.NOT_FOUND, status_code=404)
            return existing
        return IntegrationSyncRun(
            config_id=config_id,
            interface_id=interface_id,
            provider=provider,
            interface_key=interface_key,
            source_account_ref=source_account_ref,
            trigger_type=trigger.value,
            status=RunStatus.QUEUED.value,
            parent_run_id=parent_run_id,
            retry_of_run_id=retry_of_run_id,
            idempotency_key=idempotency_key,
            requested_by=actor_ref,
            request_id=request_id,
            reason=payload.reason,
            window_start=window_start,
            window_end=window_end,
            queued_at=utc_now(),
            work_items_total=0,
            work_items_succeeded=0,
            work_items_failed=0,
            records_seen=0,
            records_written=0,
        )

    def _persist_queued_run(self, run: IntegrationSyncRun, actor_ref: str) -> SyncRunCreated:
        if (
            run.id is not None
            and self.repository.find_run_by_idempotency(run.idempotency_key) is run
        ):
            return self._created(run)
        try:
            self.repository.add_run(run)
            self.repository.add_event(
                IntegrationSyncRunEvent(
                    run_id=run.id,
                    sequence_no=1,
                    event_type="state_transition",
                    from_status=None,
                    to_status=RunStatus.QUEUED.value,
                    message_code="SYNC_RUN_QUEUED",
                    safe_details=None,
                    occurred_at=utc_now(),
                    actor_ref=actor_ref,
                )
            )
            self.session.commit()
        except IntegrityError:
            self.session.rollback()
            raise ApiError(code=SYNC_RUN_ALREADY_RUNNING, status_code=409) from None
        return self._created(run)

    @staticmethod
    def _created(run: IntegrationSyncRun) -> SyncRunCreated:
        return SyncRunCreated(
            run_id=run.id,
            trigger_type=TriggerType(run.trigger_type),
            status=RunStatus(run.status),
            retry_of_run_id=run.retry_of_run_id,
        )

    def _require_config(
        self, config_id: UUID, account_refs: frozenset[str]
    ) -> IntegrationSyncConfig:
        config = self.repository.get_config(config_id, account_refs)
        if config is None:
            raise ApiError(code=ErrorCode.NOT_FOUND, status_code=404)
        return config

    def _require_run(self, run_id: UUID, account_refs: frozenset[str]) -> IntegrationSyncRun:
        run = self.repository.get_run(run_id, account_refs)
        if run is None:
            raise ApiError(code=ErrorCode.NOT_FOUND, status_code=404)
        return run


def changed_field_names(values: Mapping[str, object]) -> list[str]:
    """Return audit-safe field names only; values remain outside logs/events."""
    return sorted(values)
