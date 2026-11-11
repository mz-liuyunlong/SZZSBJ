"""回款对账（PR-2）接口的请求 / 返回结构。不含订单号、买家信息。"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

ReviewKind = Literal["review1_pass", "review2_pass", "review2_reject"]


class PeriodKey(BaseModel):
    store_id: str = Field(pattern=r"^[0-9]{1,32}$")
    report_key: str = Field(min_length=1, max_length=64)


class PayoutFollowRead(BaseModel):
    content: str
    case_no: str | None
    next_follow_date: date | None
    actor: str
    created_at: datetime


class PayoutPeriodRead(BaseModel):
    """一个店铺的一期账单 + 到账、审核、跟进。"""

    store_id: str
    store_code: str
    store_name: str | None
    report_key: str
    report_date: date
    period_start_date: date | None
    period_end_date: date | None
    currency_code: str | None
    payable_amount: Decimal
    period_status: str
    pay_state: str
    anomaly: bool
    # 配上的到账流水在日记账里已作废：这一期按没到账算，请撤销配对
    arrival_voided: bool = False
    arrived_amount: Decimal | None = None
    diff: Decimal | None = None
    arrived_date: date | None = None
    line_uid: str | None = None
    match_id: UUID | None = None
    match_method: str | None = None
    match_size: int = 0
    account_key: str | None = None
    account_name: str | None = None
    org: str | None = None
    payee: str | None = None
    stage: str
    stage_reason: str | None = None
    follow_count: int = 0
    latest_follow: PayoutFollowRead | None = None


class PayoutPeriodListData(BaseModel):
    items: list[PayoutPeriodRead]
    today: date
    recon_start: date
    # 现在点「自动配对」能配上的期数（不写库，只算）
    auto_ready: int = 0
    limit: int = 2000
    truncated: bool = False


class PayoutReviewEventRead(BaseModel):
    kind: str
    reason: str | None
    actor: str
    created_at: datetime


class PayoutMatchHistoryRead(BaseModel):
    match_id: UUID
    line_uid: str
    method: str
    payable_amount: Decimal
    created_by: str
    created_at: datetime
    undone_at: datetime | None
    undone_by: str | None
    undo_reason: str | None


class PayoutPeriodDetailData(BaseModel):
    period: PayoutPeriodRead
    amounts_by_type: dict[str, str]
    reviews: list[PayoutReviewEventRead]
    follow_ups: list[PayoutFollowRead]
    matches: list[PayoutMatchHistoryRead]


class PayoutLineRead(BaseModel):
    """日记账的一笔到账（给手动配对选）。"""

    line_uid: str
    account_key: str
    account_name: str
    business_date: date
    amount: Decimal
    currency_code: str
    counterparty_name: str
    description: str
    matched: bool
    # 日记账里已另有用途（已剔除 / 已内部配对 / 已拆分 / 已分类 Xxx）：不自动配，手动配时提示
    journal_hint: str | None = None


class PayoutLineListData(BaseModel):
    items: list[PayoutLineRead]
    limit: int = 2000
    truncated: bool = False


class PayoutAutoMatchData(BaseModel):
    matched_periods: int
    matched_lines: int


class PayoutManualMatchRequest(BaseModel):
    line_uid: str = Field(min_length=1, max_length=16)
    periods: list[PeriodKey] = Field(min_length=1, max_length=4)
    note: str | None = Field(default=None, max_length=500)


class PayoutUnmatchRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=500)


class PayoutMatchData(BaseModel):
    match_id: UUID
    periods: int


class PayoutReviewRequest(BaseModel):
    kind: ReviewKind
    periods: list[PeriodKey] = Field(min_length=1, max_length=500)
    reason: str | None = Field(default=None, max_length=500)


class PayoutReviewSkipped(BaseModel):
    store_id: str
    report_key: str
    reason: str


class PayoutReviewData(BaseModel):
    done: int
    skipped: list[PayoutReviewSkipped]


class PayoutFollowRequest(PeriodKey):
    content: str = Field(min_length=1, max_length=2000)
    case_no: str | None = Field(default=None, max_length=128)
    next_follow_date: date | None = None


class PayoutAccountRead(BaseModel):
    id: UUID
    store_id: str
    store_code: str
    account_key: str
    account_name: str
    org: str
    payee: str
    effective_from: date
    effective_to: date | None
    is_active: bool
    change_reason: str | None
    updated_by: str
    updated_at: datetime


class PayoutAccountOption(BaseModel):
    account_key: str
    account_name: str
    org: str
    currency_code: str


class PayoutStoreOption(BaseModel):
    store_id: str
    store_code: str
    store_name: str | None


class PayoutAccountListData(BaseModel):
    items: list[PayoutAccountRead]
    accounts: list[PayoutAccountOption]
    stores: list[PayoutStoreOption]


class PayoutAccountCreateRequest(BaseModel):
    store_id: str = Field(pattern=r"^[0-9]{1,32}$")
    account_key: str = Field(min_length=1, max_length=64)
    payee: str = Field(default="", max_length=255)
    effective_from: date
    reason: str | None = Field(default=None, max_length=500)


class PayoutAccountUpdateRequest(BaseModel):
    account_key: str = Field(min_length=1, max_length=64)
    payee: str = Field(default="", max_length=255)
    reason: str | None = Field(default=None, max_length=500)
