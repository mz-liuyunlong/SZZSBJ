from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

Nonblank = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=255)]
CaseStatus = Literal["pending_confirm", "following", "archive_pending", "archived", "recovered"]
CaseStatusLabel = Literal["未开Case", "已开Case", "跟进中", "已追回", "驳回", "已关闭"]
Priority = Literal["high", "medium", "low"]
PriorityLabel = Literal["高", "中", "低"]
ArchiveReviewStatus = Literal["none", "pending", "approved", "rejected"]
ArchiveDecision = Literal["approved", "rejected"]


class StrictSchema(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)


class WfsFeeCaseQuery(StrictSchema):
    start_date: date | None = None
    end_date: date | None = None
    store_id: Nonblank | None = None
    owner_ref: Nonblank | None = None
    status: CaseStatus | None = None
    archive_review_status: ArchiveReviewStatus | None = None
    priority: Priority | None = None
    keyword: Annotated[str, StringConstraints(strip_whitespace=True, max_length=128)] = ""
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=100, ge=1, le=500)


class WfsFeeCaseRead(StrictSchema):
    id: str
    source_kind: str
    source_case_ref: str | None
    legacy_case_id: int | None
    legacy_status: str | None
    legacy_updated_at: datetime | None
    last_mirrored_at: datetime | None

    platform: str
    source_account_ref: str
    store_id: str
    item_id: str
    msku: str
    store_name_snapshot: str | None
    local_sku_snapshot: str | None
    product_name_snapshot: str | None
    owner_ref: str | None
    owner_name_snapshot: str | None

    currency_code: str
    manual_unit_fee: Decimal
    actual_unit_fee: Decimal
    unit_fee_diff: Decimal
    fee_source: str
    fee_source_ref: str | None
    fee_calculated_at: datetime | None
    calculation_version: str | None

    affected_units: int
    affected_sales_start_date: date | None
    affected_sales_end_date: date | None
    affected_units_source: str | None
    estimated_recover_amount: Decimal
    pending_recover_amount: Decimal

    claim_amount: Decimal | None
    recovered_amount: Decimal
    recovered_at: datetime | None

    status: CaseStatus
    priority: Priority
    severity: Priority
    status_changed_at: datetime | None
    status_changed_by: str | None
    first_alert_at: datetime | None
    case_opened_at: datetime | None
    done_at: datetime | None
    archived_at: datetime | None

    case_nos: str | None
    follow_log: str | None
    latest_follow_note: str | None
    log_updated_at: datetime | None
    next_follow_at: date | None
    follow_count: int
    last_follow_by: str | None
    last_follow_at: datetime | None
    walmart_response_summary: str | None
    last_rejection_reason: str | None
    evidence_summary: str | None

    archive_requested_by: str | None
    archive_requested_at: datetime | None
    archive_reason_type: str | None
    archive_reason: str | None
    archive_evidence: str | None
    archive_review_status: ArchiveReviewStatus
    archive_reviewed_by: str | None
    archive_reviewed_at: datetime | None
    archive_review_note: str | None

    reason: str | None
    remark: str | None
    internal_note: str | None
    created_at: datetime
    updated_at: datetime
    updated_by: str | None


class WfsFeeCaseListData(StrictSchema):
    items: list[WfsFeeCaseRead]


class WfsFeeCaseMeta(StrictSchema):
    page: int
    page_size: int
    total: int


# Compatibility response used by the existing frontend shell. The values are read
# from formal WFS cases, not from Daily Sales MART rows.
class WfsFeeAlertQuery(StrictSchema):
    start_date: date | None = None
    end_date: date | None = None
    store_id: Nonblank | None = None
    owner_ref: Nonblank | None = None
    status: CaseStatus | CaseStatusLabel | None = None
    keyword: Annotated[str, StringConstraints(strip_whitespace=True, max_length=128)] = ""
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=100, ge=1, le=500)


class WfsFeeAlertRead(StrictSchema):
    id: str
    business_date_la: date
    store_id: str
    store_name: str | None
    owner_ref: str | None
    item_id: str
    msku: str
    local_sku: str | None
    product_name: str | None
    order_count: Decimal
    sales_qty: Decimal
    cost_quantity: Decimal
    expected_fee_amount: Decimal | None
    actual_fee_amount: Decimal | None
    variance_amount: Decimal | None
    variance_rate: Decimal | None
    expected_unit_amount: Decimal | None
    actual_unit_amount: Decimal | None
    status: CaseStatusLabel
    case_no: str | None
    reason: str | None
    priority: PriorityLabel
    claim_amount: Decimal | None
    recovered_amount: Decimal
    pending_recovery_amount: Decimal
    case_opened_at: datetime | None
    next_follow_at: date | None
    latest_follow: str | None


class WfsFeeAlertListData(StrictSchema):
    items: list[WfsFeeAlertRead]


class WfsFeeAlertMeta(StrictSchema):
    page: int
    page_size: int
    total: int


class WfsFeeCaseFollowWrite(StrictSchema):
    case_nos: Annotated[str, StringConstraints(strip_whitespace=True, max_length=1000)] = ""
    latest_follow_note: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=4000)
    ]
    next_follow_at: date | None = None
    walmart_response_summary: Annotated[
        str, StringConstraints(strip_whitespace=True, max_length=4000)
    ] = ""
    evidence_summary: Annotated[str, StringConstraints(strip_whitespace=True, max_length=4000)] = ""


class WfsFeeArchiveRequestWrite(StrictSchema):
    archive_reason_type: Nonblank
    archive_reason: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=5, max_length=4000)
    ]
    archive_evidence: Annotated[str, StringConstraints(strip_whitespace=True, max_length=4000)] = ""


class WfsFeeArchiveReviewWrite(StrictSchema):
    decision: ArchiveDecision
    archive_review_note: Annotated[
        str, StringConstraints(strip_whitespace=True, max_length=4000)
    ] = ""


class WfsFeeRecoveredWrite(StrictSchema):
    recovered_amount: Decimal = Field(ge=0, max_digits=14, decimal_places=2)
    claim_amount: Decimal | None = Field(default=None, ge=0, max_digits=14, decimal_places=2)
    latest_follow_note: Annotated[
        str, StringConstraints(strip_whitespace=True, max_length=4000)
    ] = ""


class WfsFeeCaseWrite(StrictSchema):
    """Compatibility payload for the existing WFS follow modal."""

    status: CaseStatusLabel
    case_no: Annotated[str, StringConstraints(strip_whitespace=True, max_length=1000)] = ""
    reason: Annotated[str, StringConstraints(strip_whitespace=True, max_length=1000)] = ""
    priority: PriorityLabel = "中"
    claim_amount: Decimal | None = Field(default=None, ge=0, max_digits=18, decimal_places=4)
    recovered_amount: Decimal = Field(default=Decimal("0"), ge=0, max_digits=18, decimal_places=4)
    case_opened_at: datetime | None = None
    next_follow_at: date | None = None
    latest_follow: Annotated[str, StringConstraints(strip_whitespace=True, max_length=4000)] = ""


class WfsFeeLegacySyncResult(StrictSchema):
    execute: bool
    legacy_total: int
    matched_identities: int
    unmatched_identities: int
    ambiguous_identities: int
    duplicate_identities: int
    invalid_values: int
    protected_cases: int
    existing_cases: int
    will_insert: int
    will_update: int
    inserted_or_updated: int
    status_breakdown: dict[str, int]


class WfsFeeLegacyCompareResult(StrictSchema):
    compared: int
    matched: int
    only_in_legacy: int
    only_in_formal: int
    actual_fee_diff: int
    manual_fee_diff: int
    affected_units_diff: int
    estimated_recover_diff: int
