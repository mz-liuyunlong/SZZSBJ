"""Typed WFS preparation contracts. No approval or external execution fields are accepted."""

from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import Field, field_validator

from app.modules.pmc_domestic.packing_schemas import ListingChoice
from app.modules.pmc_domestic.warehouse_schemas import Strict, WarehouseCommand, WarehouseOrderRead


class PendingFilter(Strict):
    store_id: str | None = Field(default=None, max_length=64)
    keyword: str = Field(default="", max_length=200)
    only_test: bool = False
    arrangement: Literal["all", "ready", "partial", "done"] = "all"
    creation_result: Literal[
        "all",
        "none",
        "in_progress",
        "succeeded",
        "failed",
        "partial",
        "unknown",
    ] = "all"
    completed_from: date | None = None
    completed_to: date | None = None

    @field_validator("completed_to")
    @classmethod
    def completed_range(cls, value, info):
        start = info.data.get("completed_from")
        if value is not None and start is not None and value < start:
            raise ValueError("completed_to must be on or after completed_from")
        return value


class PendingQuery(PendingFilter):
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=200)


class PendingRow(Strict):
    order: WarehouseOrderRead
    business_test: bool
    occupied_line_ids: list[UUID]
    available_line_ids: list[UUID]
    blocked_reasons: list[str]
    can_edit: bool
    total_boxes: int = 0
    occupied_boxes: int = 0
    available_boxes: int = 0
    available_units: int = 0


class PendingList(Strict):
    items: list[PendingRow]
    total: int


class StoreOption(Strict):
    value: str
    label: str


class PendingOptions(Strict):
    stores: list[StoreOption]


class PendingSummary(Strict):
    completed: int
    ready: int
    test: int
    waiting: int
    no_box: int
    filled_not_done: int
    available_boxes: int
    available_units: int


class Selection(Strict):
    order_id: UUID
    expected_version: int = Field(strict=True, ge=1)
    expected_box_version: int = Field(strict=True, ge=1)
    box_line_ids: list[UUID] = Field(min_length=1, max_length=20)


class ReturnAddress(Strict):
    address_line1: str = Field(min_length=1, max_length=200)
    city: str = Field(min_length=1, max_length=100)
    state_code: str = Field(pattern=r"^[A-Z]{2}$")
    postal_code: str = Field(pattern=r"^\d{5}(-\d{4})?$")
    country_code: Literal["US"] = "US"

    @field_validator("address_line1", "city")
    @classmethod
    def nonblank(cls, value):
        if not value.strip():
            raise ValueError("address must not be blank")
        return value.strip()


class DraftCommand(Strict):
    source_account_ref: str = Field(min_length=1, max_length=128)
    idempotency_key: UUID
    selections: list[Selection] = Field(min_length=1, max_length=100)
    return_address: ReturnAddress
    its: bool = Field(default=False, strict=True)


class DraftRead(Strict):
    id: UUID
    number: str
    status: Literal["pending"]
    store_id: str
    business_test: bool
    payload: dict
    actor_uid: str
    created_at: datetime


class DraftResult(Strict):
    drafts: list[DraftRead]


class IdentityOptions(Strict):
    listings: list[ListingChoice]


class IdentityCommand(WarehouseCommand):
    expected_box_version: int = Field(strict=True, ge=1)
    target_store_id: str = Field(min_length=1, max_length=64)
    target_item_id: str = Field(min_length=1, max_length=64)
    listing_version: str = Field(pattern=r"^[a-f0-9]{64}$")
    reason: str = Field(min_length=2, max_length=500)

    @field_validator("reason")
    @classmethod
    def nonblank(cls, value):
        if len(value.strip()) < 2:
            raise ValueError("reason required")
        return value.strip()
