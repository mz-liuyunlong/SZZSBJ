import logging
from collections.abc import Mapping
from datetime import datetime
from typing import Literal, cast
from uuid import UUID, uuid4

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.api import ApiError, ErrorCode
from app.modules.integration_sync.handlers.lingxing_batch_product_info import ordered_id_hash
from app.modules.integration_sync.models import (
    IntegrationSyncConfig,
    IntegrationSyncRun,
    IntegrationSyncRunEvent,
    IntegrationSyncRunWorkItem,
    LingxingProductInfoBatchItem,
    utc_now,
)
from app.modules.integration_sync.repository import IntegrationSyncRepository
from app.modules.integration_sync.scheduler import (
    ScheduleExpressionError,
    next_cron_instant,
    validate_cron_expression,
)
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
SYNC_PRODUCTLIST_ONLY = "SYNC_PRODUCTLIST_ONLY"
SYNC_PRODUCTLIST_MANUAL_ONLY = "SYNC_PRODUCTLIST_MANUAL_ONLY"
SYNC_PRODUCTINFO_RETRY_PLAN_INVALID = "SYNC_PRODUCTINFO_RETRY_PLAN_INVALID"
SYNC_PRODUCTINFO_BACKFILL_NOT_SUPPORTED = "SYNC_PRODUCTINFO_BACKFILL_NOT_SUPPORTED"

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
        if schedule_enabled:
            interface = self.repository.get_interface(config.interface_id)
            if (
                interface is not None
                and interface.provider == "lingxing"
                and interface.interface_key == "productList"
            ):
                raise ApiError(code=SYNC_PRODUCTLIST_MANUAL_ONLY, status_code=409)

        schedule_changed = "schedule_enabled" in values or "schedule_cron" in values
        schedule_now = utc_now()
        if "schedule_cron" in values and schedule_cron:
            try:
                validate_cron_expression(str(schedule_cron))
            except ScheduleExpressionError:
                raise ApiError(
                    code=ErrorCode.VALIDATION_ERROR,
                    status_code=422,
                ) from None

        persist_values = dict(values)
        if schedule_changed:
            if schedule_enabled:
                try:
                    persist_values["next_run_at"] = next_cron_instant(
                        str(schedule_cron),
                        schedule_now,
                    )
                except ScheduleExpressionError:
                    raise ApiError(
                        code=ErrorCode.VALIDATION_ERROR,
                        status_code=422,
                    ) from None
            else:
                persist_values["next_run_at"] = None

        try:
            self.repository.update_config(config, persist_values)
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
            productlist_only=True,
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
        if source.provider == "lingxing" and source.interface_key == "productList":
            raise ApiError(code=SYNC_PRODUCTLIST_MANUAL_ONLY, status_code=409)
        if source.status not in {RunStatus.FAILED, RunStatus.CANCELED}:
            raise ApiError(code=SYNC_RUN_NOT_RETRYABLE, status_code=409)
        if source.provider == "lingxing" and source.interface_key == "batchGetProductInfo":
            if getattr(source, "error_code", None) == "PRODUCT_INFO_ANOMALY_BREAKER_TRIPPED":
                raise ApiError(code=SYNC_RUN_NOT_RETRYABLE, status_code=409)
            return self._create_productinfo_retry_run(
                source,
                payload,
                actor_ref=actor_ref,
                request_id=request_id,
            )
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

    def _create_productinfo_retry_run(
        self,
        source: IntegrationSyncRun,
        payload: TriggerRequest,
        *,
        actor_ref: str,
        request_id: str,
    ) -> SyncRunCreated:
        source_work_items = self.repository.list_work_items_for_run(source.id)
        failed_work_items = [item for item in source_work_items if item.status == "failed"]
        if not failed_work_items:
            raise ApiError(code=SYNC_RUN_NOT_RETRYABLE, status_code=409)

        source_batch_items = self.repository.list_batch_items_for_run(source.id)
        batch_items_by_work_id: dict[UUID, list[LingxingProductInfoBatchItem]] = {}
        for item in source_batch_items:
            batch_items_by_work_id.setdefault(item.work_item_id, []).append(item)

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
        existing = self.repository.find_run_by_idempotency(run.idempotency_key)
        if existing is not None:
            return self._created(existing)

        try:
            self.repository.add_run(run)
            copied_work_items: list[IntegrationSyncRunWorkItem] = []
            copied_batch_items: list[LingxingProductInfoBatchItem] = []

            for source_work in failed_work_items:
                members = sorted(
                    batch_items_by_work_id.get(source_work.id, []),
                    key=lambda item: item.item_ordinal,
                )
                product_ids = [item.lingxing_sku_id for item in members]
                if (
                    source_work.request_kind != "id_batch_page"
                    or source_work.batch_no is None
                    or source_work.id_count is None
                    or source_work.id_hash is None
                    or len(members) != source_work.id_count
                    or [item.item_ordinal for item in members] != list(range(len(members)))
                    or len(set(product_ids)) != len(product_ids)
                    or ordered_id_hash(product_ids) != source_work.id_hash
                ):
                    raise ApiError(
                        code=SYNC_PRODUCTINFO_RETRY_PLAN_INVALID,
                        status_code=409,
                    )

                copied_work = IntegrationSyncRunWorkItem(
                    id=uuid4(),
                    run_id=run.id,
                    ordinal=source_work.ordinal,
                    request_kind="id_batch_page",
                    status="queued",
                    attempt_count=0,
                    batch_no=source_work.batch_no,
                    id_count=source_work.id_count,
                    id_hash=source_work.id_hash,
                    request_safe_params=dict(source_work.request_safe_params),
                )
                copied_work_items.append(copied_work)
                for member in members:
                    copied_batch_items.append(
                        LingxingProductInfoBatchItem(
                            id=uuid4(),
                            run_id=run.id,
                            work_item_id=copied_work.id,
                            source_account_ref=member.source_account_ref,
                            batch_no=member.batch_no,
                            item_ordinal=member.item_ordinal,
                            lingxing_sku_id=member.lingxing_sku_id,
                            raw_request_ref_id=None,
                            item_status="queued",
                        )
                    )

            self.repository.add_work_items(copied_work_items)
            self.repository.add_batch_items(copied_batch_items)
            run.work_items_total = len(copied_work_items)
            self.repository.add_event(
                IntegrationSyncRunEvent(
                    run_id=run.id,
                    sequence_no=1,
                    event_type="state_transition",
                    from_status=None,
                    to_status=RunStatus.QUEUED.value,
                    message_code="SYNC_RUN_QUEUED",
                    safe_details={"retry_failed_work_items": len(copied_work_items)},
                    occurred_at=utc_now(),
                    actor_ref=actor_ref,
                )
            )
            self.session.commit()
        except ApiError:
            self.session.rollback()
            raise
        except IntegrityError:
            self.session.rollback()
            raise ApiError(code=SYNC_RUN_ALREADY_RUNNING, status_code=409) from None
        except Exception:
            self.session.rollback()
            raise

        return self._created(run)

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
        productlist_only: bool = False,
    ) -> SyncRunCreated:
        config = self._require_config(config_id, account_refs)
        interface = self.repository.get_interface(config.interface_id)
        if interface is None:
            raise ApiError(code=ErrorCode.NOT_FOUND, status_code=404)
        if not config.is_enabled or not interface.outbound_enabled:
            raise ApiError(code=SYNC_INTERFACE_DISABLED, status_code=409)
        is_productlist = (
            interface.provider == "lingxing"
            and interface.interface_key == "productList"
            and interface.method == "POST"
            and interface.endpoint_path == "/erp/sc/routing/data/local_inventory/productList"
            and interface.request_kind == "offset_page"
        )
        is_productinfo = (
            interface.provider == "lingxing"
            and interface.interface_key == "batchGetProductInfo"
            and interface.method == "POST"
            and interface.endpoint_path
            == "/erp/sc/routing/data/local_inventory/batchGetProductInfo"
            and interface.request_kind == "id_batch_page"
        )
        if productlist_only and not (is_productlist or is_productinfo):
            raise ApiError(code=SYNC_PRODUCTLIST_ONLY, status_code=409)
        if is_productlist and (trigger is not TriggerType.MANUAL or config.schedule_enabled):
            raise ApiError(code=SYNC_PRODUCTLIST_MANUAL_ONLY, status_code=409)
        if is_productinfo and trigger is TriggerType.BACKFILL:
            raise ApiError(
                code=SYNC_PRODUCTINFO_BACKFILL_NOT_SUPPORTED,
                status_code=409,
            )
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
        return self._persist_queued_run(run, actor_ref, record_event=not is_productlist)

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

    def _persist_queued_run(
        self,
        run: IntegrationSyncRun,
        actor_ref: str,
        *,
        record_event: bool = True,
    ) -> SyncRunCreated:
        if (
            run.id is not None
            and self.repository.find_run_by_idempotency(run.idempotency_key) is run
        ):
            return self._created(run)
        try:
            self.repository.add_run(run)
            if record_event:
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
