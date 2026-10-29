"""Exception center contracts; auto-detection is stubbed in M1."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import Field

from app.modules.pmc_domestic.warehouse_schemas import Strict

RuleFamily = Literal[
    "create_long_unshipped",
    "arrival_overdue",
    "arrival_no_receiving",
    "receiving_incomplete",
    "closed_shortage_damage",
    "appeal_deadline",
]
Severity = Literal["HIGH", "MEDIUM", "LOW"]
CaseStatus = Literal["OPEN", "IN_PROGRESS", "WAITING_EXTERNAL", "RESOLVED", "CLOSED"]
KeywordField = Literal["shipment", "pk", "summary", "platform_case"]
EventAction = Literal["note", "resolve", "close", "reopen", "mark_waiting"]
SortField = Literal["first_detected_at", "due_at"]
SortDir = Literal["asc", "desc"]


class ExceptionFilter(Strict):
    store_id: str | None = Field(default=None, max_length=64)
    shipment_id: str | None = Field(default=None, max_length=128)
    rule_family: RuleFamily | None = None
    status: CaseStatus | None = None
    severity: Severity | None = None
    assignee_user_id: str | None = Field(default=None, max_length=128)
    keyword: str = Field(default="", max_length=200)
    keyword_field: KeywordField = "shipment"
    only_test: bool = False
    due_soon: bool = False


class ExceptionQuery(ExceptionFilter):
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=200)
    sort_by: SortField = "first_detected_at"
    sort_dir: SortDir = "desc"


class ExceptionRow(Strict):
    id: UUID
    shipment_id: str
    shipment_row_id: str | None = None
    rule_family: RuleFamily
    rule_label: str
    severity: Severity
    status: CaseStatus
    status_label: str
    summary: str
    store_id: str
    store_name: str | None = None
    pk: str | None = None
    sku: str | None = None
    item_id: str | None = None
    gtin: str | None = None
    msku: str | None = None
    assignee_user_id: str | None = None
    platform_case_ref: str | None = None
    due_at: datetime | None = None
    due_basis: str | None = None
    qty_variance: int | None = None
    business_test: bool
    first_detected_at: datetime
    version: int
    rule_version: str
    lingxing_data_status: Literal["PENDING"] = "PENDING"


class ExceptionList(Strict):
    items: list[ExceptionRow]
    total: int


class ExceptionSummary(Strict):
    open_shipments: int
    open_cases: int
    due_soon_cases: int


class StoreOption(Strict):
    value: str
    label: str


class ExceptionOptions(Strict):
    stores: list[StoreOption]
    assignees: list[str]


class TimelineItem(Strict):
    id: UUID
    kind: Literal["detection", "action"]
    action_type: str | None = None
    actor_uid: str | None = None
    message: str
    payload: dict = Field(default_factory=dict)
    created_at: datetime


class ExceptionDetail(ExceptionRow):
    evidence: dict = Field(default_factory=dict)
    timeline: list[TimelineItem]
    quantity_reconciliation_note: str
    lingxing_updated_at: datetime | None = None


class AssignCommand(Strict):
    assignee_user_id: str = Field(min_length=1, max_length=128)
    expected_version: int = Field(ge=1)


class CaseEventCommand(Strict):
    action: EventAction
    expected_version: int = Field(ge=1)
    note: str = Field(default="", max_length=4000)
    reason: str = Field(default="", max_length=2000)
    platform_case_ref: str | None = Field(default=None, max_length=128)
