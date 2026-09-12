from collections.abc import Mapping, Sequence
from datetime import datetime
from uuid import UUID

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.modules.integration_sync.models import (
    ApiRawBlob,
    ApiRawRequestRef,
    DataLineage,
    IntegrationInterface,
    IntegrationInterfaceDependency,
    IntegrationSyncConfig,
    IntegrationSyncLock,
    IntegrationSyncRun,
    IntegrationSyncRunEvent,
    IntegrationSyncRunWorkItem,
    LingxingProductInfoBatchItem,
    LingxingProductListSkuRef,
    ParseJob,
    RawRetentionPolicy,
)
from app.modules.sku_detail.models import LingxingSkuIdentity


class IntegrationSyncRepository:
    """Persistence only: callers own commit/rollback and task dispatch."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def list_interfaces(
        self, *, provider: str | None, enabled: bool | None, page: int, page_size: int
    ) -> tuple[list[IntegrationInterface], int]:
        statement = select(IntegrationInterface)
        if provider is not None:
            statement = statement.where(IntegrationInterface.provider == provider)
        if enabled is not None:
            statement = statement.where(IntegrationInterface.outbound_enabled == enabled)
        return self._page(
            statement.order_by(
                IntegrationInterface.provider,
                IntegrationInterface.interface_key,
                IntegrationInterface.id,
            ),
            page,
            page_size,
        )

    def list_configs(
        self,
        *,
        account_refs: frozenset[str],
        provider: str | None,
        interface_key: str | None,
        enabled: bool | None,
        page: int,
        page_size: int,
    ) -> tuple[list[IntegrationSyncConfig], int]:
        statement = (
            select(IntegrationSyncConfig)
            .join(IntegrationInterface)
            .where(IntegrationSyncConfig.source_account_ref.in_(account_refs))
        )
        if provider is not None:
            statement = statement.where(IntegrationInterface.provider == provider)
        if interface_key is not None:
            statement = statement.where(IntegrationInterface.interface_key == interface_key)
        if enabled is not None:
            statement = statement.where(IntegrationSyncConfig.is_enabled == enabled)
        return self._page(
            statement.order_by(IntegrationSyncConfig.updated_at.desc(), IntegrationSyncConfig.id),
            page,
            page_size,
        )

    def get_config(
        self, config_id: UUID, account_refs: frozenset[str]
    ) -> IntegrationSyncConfig | None:
        return self.session.scalar(
            select(IntegrationSyncConfig).where(
                IntegrationSyncConfig.id == config_id,
                IntegrationSyncConfig.source_account_ref.in_(account_refs),
            )
        )

    def get_interface(self, interface_id: UUID) -> IntegrationInterface | None:
        return self.session.get(IntegrationInterface, interface_id)

    def get_interface_by_key(
        self, provider: str, interface_key: str
    ) -> IntegrationInterface | None:
        return self.session.scalar(
            select(IntegrationInterface).where(
                IntegrationInterface.provider == provider,
                IntegrationInterface.interface_key == interface_key,
            )
        )

    def get_retention_policy(self, policy_key: str) -> RawRetentionPolicy | None:
        return self.session.scalar(
            select(RawRetentionPolicy).where(
                RawRetentionPolicy.policy_key == policy_key,
                RawRetentionPolicy.is_active.is_(True),
            )
        )

    def add_catalog_record[ModelT](self, record: ModelT) -> ModelT:
        self.session.add(record)
        self.session.flush()
        return record

    def has_dependency(self, source_id: UUID, target_id: UUID) -> bool:
        return (
            self.session.scalar(
                select(IntegrationInterfaceDependency.id).where(
                    IntegrationInterfaceDependency.source_interface_id == source_id,
                    IntegrationInterfaceDependency.target_interface_id == target_id,
                )
            )
            is not None
        )

    def update_config(
        self, config: IntegrationSyncConfig, values: Mapping[str, object]
    ) -> IntegrationSyncConfig:
        for name, value in values.items():
            setattr(config, name, value)
        self.session.flush()
        return config

    def get_run(self, run_id: UUID, account_refs: frozenset[str]) -> IntegrationSyncRun | None:
        return self.session.scalar(
            select(IntegrationSyncRun).where(
                IntegrationSyncRun.id == run_id,
                IntegrationSyncRun.source_account_ref.in_(account_refs),
            )
        )

    def get_run_for_update(self, run_id: UUID) -> IntegrationSyncRun | None:
        return self.session.scalar(
            select(IntegrationSyncRun).where(IntegrationSyncRun.id == run_id).with_for_update()
        )

    def batch_size_for_run(self, run: IntegrationSyncRun) -> int | None:
        if run.config_id is None:
            return None
        return self.session.scalar(
            select(IntegrationSyncConfig.batch_size).where(
                IntegrationSyncConfig.id == run.config_id
            )
        )

    def find_run_by_idempotency(self, idempotency_key: str) -> IntegrationSyncRun | None:
        return self.session.scalar(
            select(IntegrationSyncRun).where(IntegrationSyncRun.idempotency_key == idempotency_key)
        )

    def add_run(self, run: IntegrationSyncRun) -> IntegrationSyncRun:
        self.session.add(run)
        self.session.flush()
        return run

    def list_runs(
        self,
        *,
        account_refs: frozenset[str],
        provider: str | None,
        interface_key: str | None,
        status: str | None,
        trigger_type: str | None,
        created_from: datetime | None,
        created_to: datetime | None,
        page: int,
        page_size: int,
    ) -> tuple[list[IntegrationSyncRun], int]:
        statement = select(IntegrationSyncRun).where(
            IntegrationSyncRun.source_account_ref.in_(account_refs)
        )
        filters = (
            (IntegrationSyncRun.provider, provider),
            (IntegrationSyncRun.interface_key, interface_key),
            (IntegrationSyncRun.status, status),
            (IntegrationSyncRun.trigger_type, trigger_type),
        )
        for column, value in filters:
            if value is not None:
                statement = statement.where(column == value)
        if created_from is not None:
            statement = statement.where(IntegrationSyncRun.created_at >= created_from)
        if created_to is not None:
            statement = statement.where(IntegrationSyncRun.created_at <= created_to)
        return self._page(
            statement.order_by(IntegrationSyncRun.created_at.desc(), IntegrationSyncRun.id),
            page,
            page_size,
        )

    def list_work_items(
        self,
        *,
        run_id: UUID,
        status: str | None,
        request_kind: str | None,
        page: int,
        page_size: int,
    ) -> tuple[list[IntegrationSyncRunWorkItem], int]:
        statement = select(IntegrationSyncRunWorkItem).where(
            IntegrationSyncRunWorkItem.run_id == run_id
        )
        if status is not None:
            statement = statement.where(IntegrationSyncRunWorkItem.status == status)
        if request_kind is not None:
            statement = statement.where(IntegrationSyncRunWorkItem.request_kind == request_kind)
        return self._page(
            statement.order_by(IntegrationSyncRunWorkItem.ordinal, IntegrationSyncRunWorkItem.id),
            page,
            page_size,
        )

    def list_raw_request_refs(
        self, *, run_id: UUID, page: int, page_size: int
    ) -> tuple[list[tuple[ApiRawRequestRef, ApiRawBlob]], int]:
        base = (
            select(ApiRawRequestRef, ApiRawBlob)
            .join(ApiRawBlob, ApiRawBlob.id == ApiRawRequestRef.raw_blob_id)
            .where(ApiRawRequestRef.run_id == run_id)
        )
        total = self.session.scalar(
            select(func.count())
            .select_from(ApiRawRequestRef)
            .where(ApiRawRequestRef.run_id == run_id)
        )
        rows = self.session.execute(
            base.order_by(ApiRawRequestRef.requested_at, ApiRawRequestRef.id)
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).all()
        return [(row[0], row[1]) for row in rows], int(total or 0)

    def add_event(self, event: IntegrationSyncRunEvent) -> IntegrationSyncRunEvent:
        self.session.add(event)
        self.session.flush()
        return event

    def add_lock(self, lock: IntegrationSyncLock) -> IntegrationSyncLock:
        self.session.add(lock)
        self.session.flush()
        return lock

    def get_lock_for_run(self, run_id: UUID) -> IntegrationSyncLock | None:
        return self.session.scalar(
            select(IntegrationSyncLock).where(IntegrationSyncLock.run_id == run_id)
        )

    def get_lock_for_interface(
        self, provider: str, interface_key: str
    ) -> IntegrationSyncLock | None:
        return self.session.scalar(
            select(IntegrationSyncLock)
            .where(
                IntegrationSyncLock.provider == provider,
                IntegrationSyncLock.interface_key == interface_key,
            )
            .with_for_update()
        )

    def delete_lock(self, lock: IntegrationSyncLock) -> None:
        self.session.delete(lock)
        self.session.flush()

    def next_event_sequence(self, run_id: UUID) -> int:
        current = self.session.scalar(
            select(func.max(IntegrationSyncRunEvent.sequence_no)).where(
                IntegrationSyncRunEvent.run_id == run_id
            )
        )
        return int(current or 0) + 1

    def add_work_items(
        self, items: Sequence[IntegrationSyncRunWorkItem]
    ) -> list[IntegrationSyncRunWorkItem]:
        self.session.add_all(items)
        self.session.flush()
        return list(items)

    def add_batch_items(
        self, items: Sequence[LingxingProductInfoBatchItem]
    ) -> list[LingxingProductInfoBatchItem]:
        self.session.add_all(items)
        self.session.flush()
        return list(items)

    def add_raw_blob(self, blob: ApiRawBlob) -> ApiRawBlob:
        self.session.add(blob)
        self.session.flush()
        return blob

    def find_blob_by_hash(self, response_hash: str) -> ApiRawBlob | None:
        return self.session.scalar(
            select(ApiRawBlob).where(ApiRawBlob.response_hash == response_hash)
        )

    def add_raw_request_ref(self, ref: ApiRawRequestRef) -> ApiRawRequestRef:
        self.session.add(ref)
        self.session.flush()
        return ref

    def get_raw_request_ref(self, ref_id: UUID) -> ApiRawRequestRef | None:
        return self.session.get(ApiRawRequestRef, ref_id)

    def add_productlist_refs(
        self, refs: Sequence[LingxingProductListSkuRef]
    ) -> list[LingxingProductListSkuRef]:
        self.session.add_all(refs)
        self.session.flush()
        return list(refs)

    def add_parse_job(self, job: ParseJob) -> ParseJob:
        self.session.add(job)
        self.session.flush()
        return job

    def add_lineage(self, entries: Sequence[DataLineage]) -> list[DataLineage]:
        self.session.add_all(entries)
        self.session.flush()
        return list(entries)

    def list_active_lingxing_sku_ids(self, source_account_ref: str) -> list[str]:
        return list(
            self.session.scalars(
                select(LingxingSkuIdentity.lingxing_sku_id)
                .where(
                    LingxingSkuIdentity.provider == "lingxing",
                    LingxingSkuIdentity.source_account_ref == source_account_ref,
                    LingxingSkuIdentity.is_active.is_(True),
                )
                .order_by(LingxingSkuIdentity.lingxing_sku_id)
            ).all()
        )

    def get_lingxing_identity(
        self, source_account_ref: str, lingxing_sku_id: str
    ) -> LingxingSkuIdentity | None:
        return self.session.scalar(
            select(LingxingSkuIdentity).where(
                LingxingSkuIdentity.provider == "lingxing",
                LingxingSkuIdentity.source_account_ref == source_account_ref,
                LingxingSkuIdentity.lingxing_sku_id == lingxing_sku_id,
            )
        )

    def add_identity(self, identity: LingxingSkuIdentity) -> LingxingSkuIdentity:
        self.session.add(identity)
        self.session.flush()
        return identity

    def deactivate_absent_identities(
        self,
        *,
        source_account_ref: str,
        observed_ids: set[str],
        run_id: UUID,
        inactive_at: datetime,
    ) -> int:
        identities = self.session.scalars(
            select(LingxingSkuIdentity).where(
                LingxingSkuIdentity.provider == "lingxing",
                LingxingSkuIdentity.source_account_ref == source_account_ref,
                LingxingSkuIdentity.is_active.is_(True),
            )
        ).all()
        changed = 0
        for identity in identities:
            if identity.lingxing_sku_id not in observed_ids:
                identity.is_active = False
                identity.last_seen_run_id = run_id
                identity.inactive_at = inactive_at
                changed += 1
        self.session.flush()
        return changed

    def list_due_configs(self, now: datetime, *, limit: int) -> list[IntegrationSyncConfig]:
        return list(
            self.session.scalars(
                select(IntegrationSyncConfig)
                .where(
                    IntegrationSyncConfig.is_enabled.is_(True),
                    IntegrationSyncConfig.schedule_enabled.is_(True),
                    IntegrationSyncConfig.next_run_at.is_not(None),
                    IntegrationSyncConfig.next_run_at <= now,
                )
                .order_by(IntegrationSyncConfig.next_run_at, IntegrationSyncConfig.id)
                .with_for_update(skip_locked=True)
                .limit(limit)
            ).all()
        )

    def _page[ModelT](
        self, statement: Select[tuple[ModelT]], page: int, page_size: int
    ) -> tuple[list[ModelT], int]:
        count_statement = select(func.count()).select_from(statement.order_by(None).subquery())
        total = int(self.session.scalar(count_statement) or 0)
        values = self.session.scalars(
            statement.offset((page - 1) * page_size).limit(page_size)
        ).all()
        return list(values), total
