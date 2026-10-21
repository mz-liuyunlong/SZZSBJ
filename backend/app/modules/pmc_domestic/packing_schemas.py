"""Packing approval contract; unknown source measurements remain null."""

from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)


class PackingFilter(Strict):
    store_id: list[str] = Field(default_factory=list, max_length=50)
    overdue: Literal["all", "overdue", "not_overdue"] = "all"
    arrival: Literal["all", "full", "partial", "none", "unknown"] = "all"
    keyword: str = Field(default="", max_length=200)
    created_from: date | None = None
    created_to: date | None = None

    @model_validator(mode="after")
    def dates(self):
        if self.created_from and self.created_to and self.created_from > self.created_to:
            raise ValueError("invalid date range")
        return self


class PackingQuery(PackingFilter):
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=50, ge=1, le=200)
    sort: Literal["created_desc", "created_asc"] = "created_desc"


class Candidate(Strict):
    id: UUID
    candidate_version: str
    source_account_ref: str
    warehouse_id: str
    publication_id: UUID
    board_id: UUID
    inbound_order_sn: str
    sku: str
    product_name: str | None
    store_id: str | None
    store_name: str | None
    item_id: str | None
    gtin: str | None
    msku: str | None
    purchase_order_sns: list[str]
    arrival_purchased: int | None
    arrival_received: int | None = None
    arrival_pending: int | None = None
    arrival_status: Literal["unknown"] = "unknown"
    customs_default: bool = False
    customs_default_src: Literal["default", "product_remark", "purchase_remark"] = "default"
    customs_proof: dict | None = None
    waiting_days: int | None = None
    history_complete: bool = False
    origin: Literal["automatic", "manual"] = "automatic"
    manual_reason: str | None = None
    source_store_id: str | None = None
    manual_customs: Literal["default", "declare", "skip"] | None = None
    manual_rwh: str | None = None
    candidate_created_on: date | None
    overdue: bool | None
    stock_balance: int | None
    available_quantity: int | None
    default_quantity: int | None
    can_approve: bool
    blocked_reasons: list[str]
    source_observed_at: datetime


class CandidateList(Strict):
    items: list[Candidate]
    total: int


class PackingSummary(Strict):
    pending: int
    overdue: int
    blocked: int
    approved: int
    rejected: int


class PackingCommand(Strict):
    source_account_ref: str = Field(min_length=1, max_length=128)
    warehouse_id: Literal["16168"] = "16168"
    candidate_version: str = Field(pattern=r"^[a-f0-9]{64}$")
    idempotency_key: UUID


class ApproveCommand(PackingCommand):
    qty: int = Field(strict=True, ge=1, le=1000000)
    customs: Literal["default", "declare", "skip"] = "default"
    is_test: Literal[True] = True
    rwh: str | None = Field(default=None, max_length=128)
    target_store_id: str | None = Field(default=None, min_length=1, max_length=64)
    target_item_id: str | None = Field(default=None, min_length=1, max_length=64)
    listing_version: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    edit_reason: str | None = Field(default=None, min_length=2, max_length=500)


class RejectCommand(PackingCommand):
    note: str = Field(min_length=1, max_length=500)

    @model_validator(mode="after")
    def reason(self):
        self.note = self.note.strip()
        if not self.note:
            raise ValueError("reason required")
        return self


class OrderRead(Strict):
    id: UUID
    candidate_id: UUID
    pk: str | None
    status: Literal["approved", "rejected", "voided"]
    qty: int | None
    version: int
    is_test: bool
    customs_value: bool | None
    customs_src: str
    rwh: str | None
    actor_uid: str
    note: str | None
    created_at: datetime
    snapshot: Candidate
    source_snapshot: Candidate | None = None
    voided_at: datetime | None = None
    void_note: str | None = None


class OrderList(Strict):
    items: list[OrderRead]
    total: int


class PackingOption(Strict):
    value: str
    label: str


class PackingOptions(Strict):
    stores: list[PackingOption]
    local_verification_only: bool = True
    manual_enabled: bool = False


class EventRead(Strict):
    id: UUID
    event_kind: str
    actor_uid: str
    order_version: int
    occurred_at: datetime
    note: str | None


class EventList(Strict):
    items: list[EventRead]


class ListingChoice(Strict):
    store_id: str
    store_name: str | None
    item_id: str
    gtin: str | None
    msku: str | None
    listing_version: str
    cross_store: bool


class EditOptions(Strict):
    candidate: Candidate
    listings: list[ListingChoice]
    cross_store_proof_available: bool = False


class ManualCommand(Strict):
    source_account_ref: str = Field(min_length=1, max_length=128)
    warehouse_id: Literal["16168"] = "16168"
    board_id: UUID
    source_version: str = Field(pattern=r"^[a-f0-9]{64}$")
    target_store_id: str = Field(min_length=1, max_length=64)
    target_item_id: str = Field(min_length=1, max_length=64)
    listing_version: str = Field(pattern=r"^[a-f0-9]{64}$")
    qty: int = Field(strict=True, ge=1, le=1000000)
    customs: Literal["default", "declare", "skip"] = "default"
    rwh: str | None = Field(default=None, max_length=128)
    reason: str = Field(min_length=2, max_length=500)
    idempotency_key: UUID

    @model_validator(mode="after")
    def reason_not_blank(self):
        self.reason = self.reason.strip()
        if len(self.reason) < 2:
            raise ValueError("reason required")
        return self


class ManualSubmitted(Strict):
    id: UUID
    status: Literal["pending"] = "pending"
