from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, JsonValue, StringConstraints, model_validator

SchemaVersion = Literal["walmart-monitor.raw.v1"]
Canonical128 = Annotated[str, StringConstraints(min_length=1, max_length=128)]
Canonical200 = Annotated[str, StringConstraints(min_length=1, max_length=200)]
BoundedText = Annotated[str, StringConstraints(min_length=1, max_length=255)]
Sha256Text = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]

MAX_COMPRESSED_ARTIFACT_BYTES = 10 * 1024 * 1024
MAX_UNCOMPRESSED_ARTIFACT_BYTES = 25 * 1024 * 1024
MAX_ARTIFACT_BASE64_CHARS = ((MAX_COMPRESSED_ARTIFACT_BYTES + 2) // 3) * 4


class MonitorSchema(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)


class MonitorProducer(MonitorSchema):
    instance_id: Canonical128
    check_id: Canonical128
    run_id: Canonical128 | None = None


class MonitorTarget(MonitorSchema):
    source_account_ref: Canonical128
    store_id: Canonical128
    item_id: Canonical128
    store_name: str | None = Field(default=None, max_length=255)
    sku: str | None = Field(default=None, max_length=255)
    msku: str | None = Field(default=None, max_length=255)
    owner: str | None = Field(default=None, max_length=255)
    product_name: str | None = Field(default=None, max_length=2_000)
    product_category: str | None = Field(default=None, max_length=2_000)
    wfs_inventory: JsonValue | None = None
    monitoring_eligible: bool


class MonitorSourcePayload(MonitorSchema):
    kind: BoundedText
    content_type: Annotated[str, StringConstraints(min_length=1, max_length=128)]
    compression: Literal["gzip"]
    sha256: Sha256Text
    byte_size: int = Field(ge=0, le=MAX_UNCOMPRESSED_ARTIFACT_BYTES)
    stored_byte_size: int = Field(ge=1, le=MAX_COMPRESSED_ARTIFACT_BYTES)
    data_base64: str = Field(min_length=1, max_length=MAX_ARTIFACT_BASE64_CHARS)


class MonitorAttempt(MonitorSchema):
    attempt_no: int = Field(ge=1, le=20)
    provider: Annotated[str, StringConstraints(min_length=1, max_length=64)]
    outcome: Annotated[str, StringConstraints(min_length=1, max_length=64)]
    source_payloads: list[MonitorSourcePayload] = Field(default_factory=list, max_length=10)


class MonitorFinalObservation(MonitorSchema):
    outcome: Annotated[str, StringConstraints(min_length=1, max_length=64)]
    data_source: str | None = Field(default=None, max_length=64)
    error_code: str | None = Field(default=None, max_length=128)
    duration_ms: int | None = Field(default=None, ge=0)
    parsed_result: dict[str, JsonValue]


class WalmartMonitorRawEventRequest(MonitorSchema):
    schema_version: SchemaVersion
    event_id: Canonical200
    captured_at: datetime
    requested_provider: Annotated[str, StringConstraints(min_length=1, max_length=64)]
    producer: MonitorProducer
    targets: list[MonitorTarget] = Field(min_length=1, max_length=100)
    attempts: list[MonitorAttempt] = Field(min_length=1, max_length=20)
    final_observation: MonitorFinalObservation

    @model_validator(mode="after")
    def validate_event_contract(self) -> Self:
        if self.captured_at.tzinfo is None or self.captured_at.utcoffset() is None:
            raise ValueError("captured_at must include an explicit UTC offset")

        canonical_values = (
            self.event_id,
            self.producer.instance_id,
            self.producer.check_id,
            *(value for value in (self.producer.run_id,) if value is not None),
            *(target.source_account_ref for target in self.targets),
            *(target.store_id for target in self.targets),
            *(target.item_id for target in self.targets),
        )
        if any(value != value.strip() for value in canonical_values):
            raise ValueError("identity values must be canonical")

        attempt_numbers = [attempt.attempt_no for attempt in self.attempts]
        if len(attempt_numbers) != len(set(attempt_numbers)):
            raise ValueError("attempt_no must be unique within an event")
        return self


class WalmartMonitorRawEventAccepted(MonitorSchema):
    id: UUID
    event_id: str
    accepted: Literal[True] = True
    duplicate: bool
    received_at: datetime
