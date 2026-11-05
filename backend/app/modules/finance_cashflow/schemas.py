from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

MoneyText = Decimal


class CashflowFileResult(BaseModel):
    file_id: UUID | None = None
    file_name: str
    sha256: str
    size: int
    status: str  # parsed / rejected
    reject_reason: str | None = None
    duplicate_of_file: bool = False
    account_keys: list[str] = Field(default_factory=list)
    detected_note: str = ""
    rows_parsed: int = 0
    rows_new: int = 0
    rows_duplicate: int = 0
    declared_range_from: date | None = None
    declared_range_to: date | None = None
    balance_chain_ok: bool | None = None
    warnings: list[str] = Field(default_factory=list)


class CashflowUploadData(BaseModel):
    import_id: UUID
    file: CashflowFileResult


class CashflowImportRead(BaseModel):
    import_id: UUID
    uploader: str
    status: str
    created_at: datetime
    voided_at: datetime | None = None
    void_reason: str | None = None
    files: list[CashflowFileResult] = Field(default_factory=list)


class CashflowImportListData(BaseModel):
    items: list[CashflowImportRead]
    total: int
    page: int
    page_size: int


class CashflowVoidRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=500)


class CashflowVoidData(BaseModel):
    import_id: UUID
    lines_affected: int


class CashflowAccountRead(BaseModel):
    account_key: str
    display_name: str
    entity: str
    currency_code: str
    kind: str
    provider: str
    account_no_last4: str
    is_active: bool
    line_count: int = 0
    last_file_name: str | None = None
    cover_from: date | None = None
    cover_to: date | None = None
    cover_source: str | None = None  # 表头 / 首末笔


class CashflowCategoryRead(BaseModel):
    code: str
    big: str
    name: str
    is_internal: bool
    is_exclude: bool


class CashflowFxRateRead(BaseModel):
    month: str
    currency_code: str
    my_rate: Decimal | None


class CashflowLinePartRead(BaseModel):
    amount: Decimal
    category_code: str | None = None
    # 有值 = 手续费行（「确认记为手续费」切出来的），值是手续费层，如 fee / payoneer。
    fee_layer: str | None = None
    # 拆分行自己的摘要 / 备注（set_part_text），空 = 沿用整笔的。
    description: str | None = None
    memo: str | None = None


class CashflowLineRead(BaseModel):
    line_uid: str
    account_key: str
    business_date: date
    month: str
    time: str | None = None
    currency_code: str
    amount: Decimal
    amount_cny: Decimal | None = None
    # 折人民币用的汇率和来源：payoneer = 派安盈实际到账；
    # lingxing = 领星当月汇率；pending = 提现等月结单。
    fx_rate: Decimal | None = None
    fx_source: str = ""
    balance_after: Decimal | None = None
    description: str
    memo: str
    counterparty_name: str
    counterparty_account_last4: str
    source_ref: str
    file_row_order: int
    category_code: str | None = None
    category_source: str = ""
    pair_id: str | None = None
    flags: list[str] = Field(default_factory=list)
    refs: list[str] = Field(default_factory=list)
    exclude_amount: Decimal | None = None
    exclude_reason: str | None = None
    list_excluded_cny: Decimal = Decimal("0")
    stage: str = "todo"
    stage_reason: str | None = None
    review_note: str | None = None
    # 人工改过的摘要 / 备注；null = 没改，显示银行原文（description / memo）。
    manual_description: str | None = None
    manual_memo: str | None = None
    parts: list[CashflowLinePartRead] | None = None
    manual_pair: str | None = None
    auto_exclude_reason: str | None = None
    version: int = 0
    # 还没挂单的流水：金额和日期对得上的审批单号，等财务选。
    approval_candidates: list[str] = Field(default_factory=list)


class CashflowLineListData(BaseModel):
    items: list[CashflowLineRead]
    total: int
    page: int
    page_size: int


class CashflowAnomalyRead(BaseModel):
    type: str
    account_key: str
    date: str
    message: str
    amount: Decimal | None = None
    # amount 的币种：剔除清单异常是 CNY，其他是流水的币种。
    currency_code: str
    line_uid: str | None = None


class CashflowLineEventRequest(BaseModel):
    kind: str = Field(max_length=32)
    payload: dict[str, Any] = Field(default_factory=dict)
    reason: str | None = Field(default=None, max_length=500)
    expected_version: int = Field(ge=0)
    idempotency_key: str | None = Field(default=None, max_length=128)


class CashflowLineEventData(BaseModel):
    line_uid: str
    stage: str
    stage_reason: str | None = None
    version: int
    auto_reset: bool = False
    replayed: bool = False


class CashflowApprovalItemRead(BaseModel):
    content: str = ""
    amount: Decimal | None = None
    category: str = ""


class CashflowApprovalFileRead(BaseModel):
    source: str
    what: str = ""
    item: int = 0
    is_image: bool = False
    title: str = ""


class CashflowApprovalRecordRead(BaseModel):
    node: str = ""
    act: str = ""
    who: str = ""
    time: str = ""
    note: str = ""
    files: int = 0


class CashflowApprovalCommentRead(BaseModel):
    who: str = ""
    time: str = ""
    note: str = ""


class CashflowApprovalPaidRead(BaseModel):
    line_uid: str
    amount_cny: Decimal


class CashflowApprovalRead(BaseModel):
    serial: str
    kind: str
    status: str
    status_text: str
    state: str
    started_at: str = ""
    completed_at: str = ""
    handled_at: str = ""
    applicant: str = ""
    reason: str = ""
    amount: Decimal | None = None
    currency_code: str = "CNY"
    amount_cny: Decimal | None = None
    pay_method: str = ""
    invoice: str = ""
    payee: str = ""
    bank: str = ""
    last4: str = ""
    fee_category: str = ""
    related_serial: str = ""
    items: list[CashflowApprovalItemRead] = Field(default_factory=list)
    attachments: list[CashflowApprovalFileRead] = Field(default_factory=list)
    records: list[CashflowApprovalRecordRead] = Field(default_factory=list)
    comments: list[CashflowApprovalCommentRead] = Field(default_factory=list)
    paid: list[CashflowApprovalPaidRead] = Field(default_factory=list)
    paid_sum: Decimal = Decimal("0")
    fetched_at: datetime | None = None


class CashflowApprovalSyncData(BaseModel):
    run_id: UUID | None = None
    status: str = "never"  # never / queued / running / succeeded / failed
    started_at: datetime | None = None
    finished_at: datetime | None = None
    error_code: str | None = None
    records_seen: int = 0
    records_written: int = 0
    last_success_at: datetime | None = None
