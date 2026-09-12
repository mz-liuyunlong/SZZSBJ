from datetime import datetime
from enum import StrEnum
from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

Nonblank128 = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=128)]
Reason = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1000)]


class StrictSchema(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True, hide_input_in_errors=True)


class TriggerType(StrEnum):
    MANUAL = "manual"
    SCHEDULE = "schedule"
    RETRY = "retry"
    BACKFILL = "backfill"
    IMPORT = "import"


class RunStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELED = "canceled"


class RequestKind(StrEnum):
    OFFSET_PAGE = "offset_page"
    ID_BATCH_PAGE = "id_batch_page"


class ReadMeta(StrictSchema):
    source: Literal["new_system_postgresql"] = "new_system_postgresql"
    source_objects: list[str]
    freshness_at: datetime | None = None
    page: int | None = None
    page_size: int | None = None
    total: int | None = None


class PageQuery(StrictSchema):
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)


class InterfaceListQuery(PageQuery):
    provider: Annotated[str, StringConstraints(max_length=32)] | None = None
    enabled: bool | None = None


class IntegrationInterfaceRead(StrictSchema):
    id: UUID
    provider: str
    interface_key: str
    display_name: str
    method: str
    request_kind: RequestKind
    contract_version: str
    outbound_enabled: bool


class InterfaceListData(StrictSchema):
    items: list[IntegrationInterfaceRead]


class SyncConfigListQuery(PageQuery):
    provider: Annotated[str, StringConstraints(max_length=32)] | None = None
    interface_key: Nonblank128 | None = None
    enabled: bool | None = None


class SyncConfigRead(StrictSchema):
    id: UUID
    interface_id: UUID
    source_account_ref: str
    is_enabled: bool
    schedule_enabled: bool
    schedule_cron: str | None
    schedule_timezone: str
    page_size: int | None
    batch_size: int | None
    max_pages: int | None
    max_attempts: int
    retention_policy_id: UUID | None
    next_run_at: datetime | None
    last_scheduled_at: datetime | None
    created_at: datetime
    updated_at: datetime


class SyncConfigListData(StrictSchema):
    items: list[SyncConfigRead]


class SyncConfigUpdate(StrictSchema):
    is_enabled: bool | None = None
    schedule_enabled: bool | None = None
    schedule_cron: Annotated[str, StringConstraints(max_length=128)] | None = None
    page_size: int | None = Field(default=None, ge=1, le=10000)
    batch_size: int | None = Field(default=None, ge=1, le=10000)
    max_pages: int | None = Field(default=None, ge=1, le=10000)
    max_attempts: int | None = Field(default=None, ge=1, le=10)
    retention_policy_id: UUID | None = None

    @model_validator(mode="after")
    def require_change(self) -> Self:
        if not self.model_fields_set:
            raise ValueError("at least one field must be provided")
        if self.schedule_enabled is True and not self.schedule_cron:
            raise ValueError("schedule_cron is required when enabling a schedule")
        return self


class TriggerRequest(StrictSchema):
    reason: Reason
    idempotency_key: Annotated[str, StringConstraints(max_length=255)] | None = None


class BackfillRequest(TriggerRequest):
    window_start: datetime
    window_end: datetime

    @model_validator(mode="after")
    def validate_window(self) -> Self:
        if self.window_start.tzinfo is None or self.window_end.tzinfo is None:
            raise ValueError("backfill bounds must include a UTC offset")
        if self.window_end <= self.window_start:
            raise ValueError("window_end must be after window_start")
        return self


class SyncRunRead(StrictSchema):
    id: UUID
    config_id: UUID | None
    interface_id: UUID
    provider: str
    interface_key: str
    source_account_ref: str
    trigger_type: TriggerType
    status: RunStatus
    parent_run_id: UUID | None
    retry_of_run_id: UUID | None
    request_id: str | None
    queued_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    work_items_total: int
    work_items_succeeded: int
    work_items_failed: int
    records_seen: int
    records_written: int
    error_code: str | None
    error_message: str | None
    created_at: datetime


class SyncRunCreated(StrictSchema):
    run_id: UUID
    trigger_type: TriggerType
    status: RunStatus
    retry_of_run_id: UUID | None = None


class SyncRunListQuery(PageQuery):
    provider: Annotated[str, StringConstraints(max_length=32)] | None = None
    interface_key: Nonblank128 | None = None
    status: RunStatus | None = None
    trigger_type: TriggerType | None = None
    created_from: datetime | None = None
    created_to: datetime | None = None

    @model_validator(mode="after")
    def validate_range(self) -> Self:
        if self.created_from and self.created_to and self.created_to < self.created_from:
            raise ValueError("created_to must not precede created_from")
        return self


class SyncRunListData(StrictSchema):
    items: list[SyncRunRead]


class WorkItemListQuery(PageQuery):
    status: RunStatus | None = None
    request_kind: RequestKind | None = None


class WorkItemRead(StrictSchema):
    id: UUID
    run_id: UUID
    ordinal: int
    request_kind: RequestKind
    status: RunStatus
    attempt_count: int
    request_safe_params: dict[str, object]
    response_count: int | None
    error_code: str | None
    error_message: str | None
    started_at: datetime | None
    finished_at: datetime | None
    created_at: datetime


class WorkItemListData(StrictSchema):
    items: list[WorkItemRead]


class RawRequestMetadataRead(StrictSchema):
    id: UUID
    run_id: UUID
    work_item_id: UUID
    raw_blob_id: UUID
    request_kind: RequestKind
    attempt_no: int
    request_safe_params: dict[str, object]
    http_status: int | None
    provider_code: str | None
    is_success: bool
    response_count: int | None
    response_hash: str
    payload_bytes: int
    storage_mode: Literal["database", "archive"]
    archive_present: bool
    requested_at: datetime
    received_at: datetime


class RawRequestMetadataListData(StrictSchema):
    items: list[RawRequestMetadataRead]
