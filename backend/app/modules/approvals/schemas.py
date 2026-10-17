"""Public schemas for the common approval workbench."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

ApprovalTab = Literal["pending", "approved", "rejected", "legacy"]
ApprovalView = Literal["mine", "created", "all"]
ApprovalDecision = Literal["approved", "rejected", "info_required"]
ApprovalStatus = Literal[
    "submitted", "info_required", "approved", "rejected", "withdrawn", "legacy_unverified"
]
ApprovalRisk = Literal["low", "medium", "high"]


class StrictSchema(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)


class ApprovalQuery(StrictSchema):
    tab: ApprovalTab = "pending"
    view: ApprovalView = "mine"
    approval_type: str | None = None
    risk_level: ApprovalRisk | None = None
    keyword: Annotated[str, StringConstraints(max_length=128)] = ""
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=50, ge=1, le=200)


class ApprovalItem(StrictSchema):
    id: str
    version: int
    approval_type: str
    business_ref: str
    title: str
    source_account_ref: str
    applicant_id: str | None
    status: ApprovalStatus
    risk_level: ApprovalRisk
    amount: str | None
    currency_code: str | None
    submitted_at: datetime | None
    reviewed_at: datetime | None
    reviewed_by: str | None
    reason: str
    can_review: bool = False
    requires_verification: bool = False


class ApprovalListData(StrictSchema):
    items: list[ApprovalItem]


class ApprovalMeta(StrictSchema):
    total: int
    page: int
    page_size: int


class ApprovalSummary(StrictSchema):
    pending: int
    high_risk: int
    info_required: int
    approved: int
    legacy_unverified: int = 0


class ApprovalEventRead(StrictSchema):
    event_type: str
    actor_id: str
    note: str | None
    created_at: datetime


class ApprovalDetail(ApprovalItem):
    evidence: str | None = None
    snapshot: dict[str, Any]
    current_case: dict[str, Any] | None
    data_changed: bool
    can_supplement: bool = False
    events: list[ApprovalEventRead]


class ApprovalDecisionWrite(StrictSchema):
    decision: ApprovalDecision
    note: Annotated[str, StringConstraints(strip_whitespace=True, max_length=4000)] = ""
    expected_version: int = Field(ge=1)


class ApprovalSupplementWrite(StrictSchema):
    note: Annotated[str, StringConstraints(strip_whitespace=True, min_length=5, max_length=4000)]
    evidence: Annotated[str, StringConstraints(strip_whitespace=True, max_length=4000)] = ""
    expected_version: int = Field(ge=1)


class ApprovalSubmitResult(StrictSchema):
    approval_id: str
    created: bool


class LegacyReattestationWrite(StrictSchema):
    reason_type: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=64)
    ]
    reason: Annotated[str, StringConstraints(strip_whitespace=True, min_length=5, max_length=4000)]
    evidence: Annotated[str, StringConstraints(strip_whitespace=True, max_length=4000)] = ""


class ApprovalRuleWrite(StrictSchema):
    expected_version: int = Field(ge=1)
    required_steps: int = Field(ge=1, le=5)
    due_hours: int = Field(ge=1, le=8760)
    allows_bulk: bool = False


class BulkDecisionWrite(StrictSchema):
    approval_ids: list[str] = Field(min_length=1, max_length=20)
    expected_versions: dict[str, int]
    note: Annotated[str, StringConstraints(strip_whitespace=True, min_length=5, max_length=4000)]


class GenericApprovalWrite(StrictSchema):
    approval_type: Literal["purchase_exception", "finance_exception", "access_change", "operations_plan_ack"]
    source_ref: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=128)
    ]
    source_account_ref: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=128)
    ]
    reason: Annotated[str, StringConstraints(strip_whitespace=True, min_length=5, max_length=4000)]
    evidence: Annotated[str, StringConstraints(strip_whitespace=True, max_length=4000)] = ""
