from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


def utc_now() -> datetime:
    return datetime.now(UTC)


RUN_STATUSES = "'queued', 'running', 'succeeded', 'failed', 'canceled'"
WORK_STATUSES = RUN_STATUSES
TRIGGER_TYPES = "'manual', 'schedule', 'retry', 'backfill', 'import'"
REQUEST_KINDS = "'offset_page', 'id_batch_page'"


class IntegrationInterface(Base):
    __tablename__ = "gov_integration_interfaces"
    __table_args__ = (
        UniqueConstraint("provider", "interface_key"),
        UniqueConstraint("provider", "method", "endpoint_path"),
        CheckConstraint("method = 'POST'", name="method_post"),
        CheckConstraint(f"request_kind IN ({REQUEST_KINDS})", name="request_kind"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    interface_key: Mapped[str] = mapped_column(String(128), nullable=False)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    method: Mapped[str] = mapped_column(String(10), nullable=False)
    endpoint_path: Mapped[str] = mapped_column(Text, nullable=False)
    request_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    handler_key: Mapped[str] = mapped_column(String(128), nullable=False)
    contract_version: Mapped[str] = mapped_column(String(64), nullable=False)
    outbound_enabled: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=text("false"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )


class IntegrationInterfaceDependency(Base):
    __tablename__ = "gov_integration_interface_dependencies"
    __table_args__ = (
        UniqueConstraint(
            "source_interface_id",
            "target_interface_id",
            "dependency_type",
            "dependency_key",
        ),
        CheckConstraint("source_interface_id <> target_interface_id", name="different_interfaces"),
        CheckConstraint("dependency_type = 'requires_sku_ids'", name="dependency_type"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    source_interface_id: Mapped[UUID] = mapped_column(
        ForeignKey("gov_integration_interfaces.id", ondelete="RESTRICT"), nullable=False
    )
    target_interface_id: Mapped[UUID] = mapped_column(
        ForeignKey("gov_integration_interfaces.id", ondelete="RESTRICT"), nullable=False
    )
    dependency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    dependency_type: Mapped[str] = mapped_column(String(64), nullable=False)
    is_required: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )


class RawRetentionPolicy(Base):
    __tablename__ = "gov_raw_retention_policies"
    __table_args__ = (
        UniqueConstraint("policy_key"),
        CheckConstraint("hot_retention_days >= 0", name="hot_retention_days"),
        CheckConstraint(
            "archive_after_days IS NULL OR archive_after_days >= 0", name="archive_days"
        ),
        CheckConstraint("delete_after_days IS NULL OR delete_after_days >= 0", name="delete_days"),
        CheckConstraint(
            "delete_after_days IS NULL OR archive_after_days IS NULL "
            "OR delete_after_days >= archive_after_days",
            name="delete_after_archive",
        ),
        CheckConstraint(
            "NOT archive_required OR archive_after_days IS NOT NULL",
            name="archive_required_threshold",
        ),
        Index(
            "uq_gov_raw_retention_policy_scope",
            text("coalesce(provider, '')"),
            text("coalesce(interface_key, '')"),
            unique=True,
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    policy_key: Mapped[str] = mapped_column(String(128), nullable=False)
    provider: Mapped[str | None] = mapped_column(String(32))
    interface_key: Mapped[str | None] = mapped_column(String(128))
    hot_retention_days: Mapped[int] = mapped_column(Integer, nullable=False)
    archive_after_days: Mapped[int | None] = mapped_column(Integer)
    delete_after_days: Mapped[int | None] = mapped_column(Integer)
    archive_required: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    legal_hold: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )


class IntegrationSyncConfig(Base):
    __tablename__ = "gov_integration_sync_configs"
    __table_args__ = (
        UniqueConstraint("interface_id", "source_account_ref"),
        CheckConstraint("page_size IS NULL OR page_size BETWEEN 1 AND 10000", name="page_size"),
        CheckConstraint("batch_size IS NULL OR batch_size BETWEEN 1 AND 10000", name="batch_size"),
        CheckConstraint("max_pages IS NULL OR max_pages BETWEEN 1 AND 10000", name="max_pages"),
        CheckConstraint("max_attempts BETWEEN 1 AND 10", name="max_attempts"),
        CheckConstraint(
            "NOT schedule_enabled OR (schedule_cron IS NOT NULL AND schedule_timezone = 'UTC')",
            name="schedule_contract",
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    interface_id: Mapped[UUID] = mapped_column(
        ForeignKey("gov_integration_interfaces.id", ondelete="RESTRICT"), nullable=False
    )
    source_account_ref: Mapped[str] = mapped_column(String(128), nullable=False)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    schedule_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    schedule_cron: Mapped[str | None] = mapped_column(String(128))
    schedule_timezone: Mapped[str] = mapped_column(
        String(64), default="UTC", server_default=text("'UTC'"), nullable=False
    )
    page_size: Mapped[int | None] = mapped_column(Integer)
    batch_size: Mapped[int | None] = mapped_column(Integer)
    max_pages: Mapped[int | None] = mapped_column(Integer)
    max_attempts: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    retention_policy_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("gov_raw_retention_policies.id", ondelete="RESTRICT")
    )
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )


class IntegrationSyncRun(Base):
    __tablename__ = "gov_integration_sync_runs"
    __table_args__ = (
        UniqueConstraint("idempotency_key"),
        CheckConstraint(f"trigger_type IN ({TRIGGER_TYPES})", name="trigger_type"),
        CheckConstraint(f"status IN ({RUN_STATUSES})", name="status"),
        CheckConstraint(
            "work_items_total >= 0 AND work_items_succeeded >= 0 "
            "AND work_items_failed >= 0 AND records_seen >= 0 AND records_written >= 0",
            name="nonnegative_counters",
        ),
        CheckConstraint(
            "window_end IS NULL OR window_start IS NULL OR window_end >= window_start",
            name="window_order",
        ),
        CheckConstraint(
            "finished_at IS NULL OR started_at IS NULL OR finished_at >= started_at",
            name="execution_time_order",
        ),
        Index(
            "uq_gov_integration_sync_runs_running",
            "provider",
            "interface_key",
            unique=True,
            postgresql_where=text("status = 'running'"),
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    config_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("gov_integration_sync_configs.id", ondelete="RESTRICT")
    )
    interface_id: Mapped[UUID] = mapped_column(
        ForeignKey("gov_integration_interfaces.id", ondelete="RESTRICT"), nullable=False
    )
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    interface_key: Mapped[str] = mapped_column(String(128), nullable=False)
    source_account_ref: Mapped[str] = mapped_column(String(128), nullable=False)
    trigger_type: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    parent_run_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("gov_integration_sync_runs.id", ondelete="RESTRICT")
    )
    retry_of_run_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("gov_integration_sync_runs.id", ondelete="RESTRICT")
    )
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False)
    requested_by: Mapped[str | None] = mapped_column(String(255))
    request_id: Mapped[str | None] = mapped_column(String(128))
    reason: Mapped[str | None] = mapped_column(Text)
    window_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    window_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    queued_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    work_items_total: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    work_items_succeeded: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    work_items_failed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    records_seen: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    records_written: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(128))
    error_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )


class IntegrationSyncRunEvent(Base):
    __tablename__ = "gov_integration_sync_run_events"
    __table_args__ = (
        UniqueConstraint("run_id", "sequence_no"),
        CheckConstraint(
            f"from_status IS NULL OR from_status IN ({RUN_STATUSES})", name="from_status"
        ),
        CheckConstraint(f"to_status IS NULL OR to_status IN ({RUN_STATUSES})", name="to_status"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    run_id: Mapped[UUID] = mapped_column(
        ForeignKey("gov_integration_sync_runs.id", ondelete="RESTRICT"), nullable=False
    )
    sequence_no: Mapped[int] = mapped_column(Integer, nullable=False)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    from_status: Mapped[str | None] = mapped_column(String(32))
    to_status: Mapped[str | None] = mapped_column(String(32))
    message_code: Mapped[str] = mapped_column(String(128), nullable=False)
    safe_details: Mapped[dict[str, object] | None] = mapped_column(JSONB)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    actor_ref: Mapped[str | None] = mapped_column(String(255))


class IntegrationSyncLock(Base):
    __tablename__ = "gov_integration_sync_locks"
    __table_args__ = (
        UniqueConstraint("provider", "interface_key"),
        UniqueConstraint("run_id"),
        CheckConstraint("char_length(lock_token_hash) = 64", name="token_hash"),
        CheckConstraint("expires_at > acquired_at", name="lease_time_order"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    interface_key: Mapped[str] = mapped_column(String(128), nullable=False)
    run_id: Mapped[UUID] = mapped_column(
        ForeignKey("gov_integration_sync_runs.id", ondelete="RESTRICT"), nullable=False
    )
    lock_token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    acquired_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    heartbeat_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )


class IntegrationSyncRunWorkItem(Base):
    __tablename__ = "gov_integration_sync_run_work_items"
    __table_args__ = (
        UniqueConstraint("run_id", "ordinal"),
        CheckConstraint(f"request_kind IN ({REQUEST_KINDS})", name="request_kind"),
        CheckConstraint(f"status IN ({WORK_STATUSES})", name="status"),
        CheckConstraint("ordinal >= 1 AND attempt_count >= 0", name="positive_order_attempt"),
        CheckConstraint("response_count IS NULL OR response_count >= 0", name="response_count"),
        CheckConstraint(
            "(request_kind = 'offset_page' AND offset_value IS NOT NULL AND length_value > 0 "
            "AND batch_no IS NULL AND id_count IS NULL AND id_hash IS NULL) OR "
            "(request_kind = 'id_batch_page' AND offset_value IS NULL AND length_value IS NULL "
            "AND batch_no > 0 AND id_count > 0 AND char_length(id_hash) = 64)",
            name="request_kind_columns",
        ),
        Index(
            "uq_gov_sync_work_offset",
            "run_id",
            "request_kind",
            "offset_value",
            unique=True,
            postgresql_where=text("request_kind = 'offset_page'"),
        ),
        Index(
            "uq_gov_sync_work_batch",
            "run_id",
            "request_kind",
            "batch_no",
            unique=True,
            postgresql_where=text("request_kind = 'id_batch_page'"),
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    run_id: Mapped[UUID] = mapped_column(
        ForeignKey("gov_integration_sync_runs.id", ondelete="RESTRICT"), nullable=False
    )
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    request_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    offset_value: Mapped[int | None] = mapped_column(Integer)
    length_value: Mapped[int | None] = mapped_column(Integer)
    batch_no: Mapped[int | None] = mapped_column(Integer)
    id_count: Mapped[int | None] = mapped_column(Integer)
    id_hash: Mapped[str | None] = mapped_column(String(64))
    request_safe_params: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    response_count: Mapped[int | None] = mapped_column(Integer)
    error_code: Mapped[str | None] = mapped_column(String(128))
    error_message: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )


class ApiRawBlob(Base):
    __tablename__ = "ods_api_raw_blobs"
    __table_args__ = (
        UniqueConstraint("response_hash"),
        CheckConstraint("char_length(response_hash) = 64", name="response_hash"),
        CheckConstraint("payload_bytes >= 0", name="payload_bytes"),
        CheckConstraint("storage_mode IN ('database', 'archive')", name="storage_mode"),
        CheckConstraint(
            "(storage_mode = 'database' AND payload_json IS NOT NULL) OR "
            "(storage_mode = 'archive' AND archive_uri IS NOT NULL)",
            name="storage_payload",
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    response_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    payload_json: Mapped[object | None] = mapped_column(JSONB)
    payload_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    content_type: Mapped[str] = mapped_column(String(128), nullable=False)
    storage_mode: Mapped[str] = mapped_column(String(16), nullable=False)
    archive_uri: Mapped[str | None] = mapped_column(Text)
    retention_policy_id: Mapped[UUID] = mapped_column(
        ForeignKey("gov_raw_retention_policies.id", ondelete="RESTRICT"), nullable=False
    )
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    payload_deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )


class ApiRawRequestRef(Base):
    __tablename__ = "ods_api_raw_request_refs"
    __table_args__ = (
        UniqueConstraint("work_item_id", "attempt_no"),
        CheckConstraint(f"request_kind IN ({REQUEST_KINDS})", name="request_kind"),
        CheckConstraint("attempt_no >= 1", name="attempt_no"),
        CheckConstraint("response_count IS NULL OR response_count >= 0", name="response_count"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    run_id: Mapped[UUID] = mapped_column(
        ForeignKey("gov_integration_sync_runs.id", ondelete="RESTRICT"), nullable=False
    )
    work_item_id: Mapped[UUID] = mapped_column(
        ForeignKey("gov_integration_sync_run_work_items.id", ondelete="RESTRICT"), nullable=False
    )
    raw_blob_id: Mapped[UUID] = mapped_column(
        ForeignKey("ods_api_raw_blobs.id", ondelete="RESTRICT"), nullable=False
    )
    request_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    attempt_no: Mapped[int] = mapped_column(Integer, nullable=False)
    request_safe_params: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    http_status: Mapped[int | None] = mapped_column(Integer)
    provider_code: Mapped[str | None] = mapped_column(String(64))
    is_success: Mapped[bool] = mapped_column(Boolean, nullable=False)
    response_count: Mapped[int | None] = mapped_column(Integer)
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )


class LingxingProductListSkuRef(Base):
    __tablename__ = "ods_lingxing_productlist_sku_refs"
    __table_args__ = (
        UniqueConstraint("raw_request_ref_id", "source_item_ordinal"),
        UniqueConstraint("run_id", "source_account_ref", "lingxing_sku_id"),
        CheckConstraint("char_length(trim(lingxing_sku_id)) > 0", name="nonblank_sku_id"),
        CheckConstraint("source_item_ordinal >= 0", name="source_item_ordinal"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    run_id: Mapped[UUID] = mapped_column(
        ForeignKey("gov_integration_sync_runs.id", ondelete="RESTRICT"), nullable=False
    )
    raw_request_ref_id: Mapped[UUID] = mapped_column(
        ForeignKey("ods_api_raw_request_refs.id", ondelete="RESTRICT"), nullable=False
    )
    source_account_ref: Mapped[str] = mapped_column(String(128), nullable=False)
    lingxing_sku_id: Mapped[str] = mapped_column(String(255), nullable=False)
    source_item_ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )


class LingxingProductInfoBatchItem(Base):
    __tablename__ = "ods_lingxing_product_info_batch_items"
    __table_args__ = (
        UniqueConstraint("run_id", "source_account_ref", "lingxing_sku_id"),
        UniqueConstraint("work_item_id", "item_ordinal"),
        CheckConstraint(f"item_status IN ({WORK_STATUSES})", name="item_status"),
        CheckConstraint("batch_no > 0 AND item_ordinal >= 0", name="batch_ordinal"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    run_id: Mapped[UUID] = mapped_column(
        ForeignKey("gov_integration_sync_runs.id", ondelete="RESTRICT"), nullable=False
    )
    work_item_id: Mapped[UUID] = mapped_column(
        ForeignKey("gov_integration_sync_run_work_items.id", ondelete="RESTRICT"), nullable=False
    )
    source_account_ref: Mapped[str] = mapped_column(String(128), nullable=False)
    batch_no: Mapped[int] = mapped_column(Integer, nullable=False)
    item_ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    lingxing_sku_id: Mapped[str] = mapped_column(String(255), nullable=False)
    raw_request_ref_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("ods_api_raw_request_refs.id", ondelete="RESTRICT")
    )
    item_status: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )


class ParseJob(Base):
    __tablename__ = "gov_parse_jobs"
    __table_args__ = (
        UniqueConstraint("raw_request_ref_id", "parser_key", "parser_version"),
        CheckConstraint(f"status IN ({WORK_STATUSES})", name="status"),
        CheckConstraint("target_layer = 'DWD'", name="target_layer"),
        CheckConstraint(
            "records_seen >= 0 AND records_written >= 0 AND records_rejected >= 0",
            name="nonnegative_counters",
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    run_id: Mapped[UUID] = mapped_column(
        ForeignKey("gov_integration_sync_runs.id", ondelete="RESTRICT"), nullable=False
    )
    raw_request_ref_id: Mapped[UUID] = mapped_column(
        ForeignKey("ods_api_raw_request_refs.id", ondelete="RESTRICT"), nullable=False
    )
    parser_key: Mapped[str] = mapped_column(String(128), nullable=False)
    parser_version: Mapped[str] = mapped_column(String(64), nullable=False)
    target_layer: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    records_seen: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    records_written: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    records_rejected: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(128))
    error_message: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )


class DataLineage(Base):
    __tablename__ = "gov_data_lineage"
    __table_args__ = (
        UniqueConstraint(
            "raw_request_ref_id",
            "target_table",
            "target_record_id",
            "target_field",
            "source_path",
            "transform_version",
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    run_id: Mapped[UUID] = mapped_column(
        ForeignKey("gov_integration_sync_runs.id", ondelete="RESTRICT"), nullable=False
    )
    parse_job_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("gov_parse_jobs.id", ondelete="RESTRICT")
    )
    raw_request_ref_id: Mapped[UUID] = mapped_column(
        ForeignKey("ods_api_raw_request_refs.id", ondelete="RESTRICT"), nullable=False
    )
    raw_blob_id: Mapped[UUID] = mapped_column(
        ForeignKey("ods_api_raw_blobs.id", ondelete="RESTRICT"), nullable=False
    )
    source_path: Mapped[str] = mapped_column(String(512), nullable=False)
    target_table: Mapped[str] = mapped_column(String(128), nullable=False)
    target_record_id: Mapped[str] = mapped_column(String(128), nullable=False)
    target_field: Mapped[str] = mapped_column(String(128), nullable=False)
    transform_key: Mapped[str] = mapped_column(String(128), nullable=False)
    transform_version: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
